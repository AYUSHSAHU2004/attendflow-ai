"""Phase 12, engine side: which P2/P7 cases may close without a person.

Limits come from policy.json (P2 duplicate_window_minutes 5, P7 grace_minutes 10); the
boundaries are tested just inside and just outside. Anything unclear (chained taps, other
devices or sites, a second clock-in, a P17 punch review) stays open for a person, and no
other policy is ever auto-resolved.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from attendflow.engine.auto_resolve import is_candidate
from attendflow.policy.models import AUTO_RESOLVABLE, PolicyConfig
from tests.conftest import DATA_DIR
from tests.engine_helpers import POLICY, day_shift, only, policy_with, run

MON = "2026-04-13"
SHIFT = [(MON, "09:00", "18:00")]


def _p2(punches, **kw):
    return only(run(punches, SHIFT, **kw), "P2")


def _p7(punches, **kw):
    return only(run(punches, SHIFT, **kw), "P7")


def _rest(day=MON):
    return day_shift(day)[1:]  # lunch and clock-out of a normal day


def _auto(exc) -> dict:
    return exc.details["auto_resolve"]


# ---------------------------------------------------------------- limits come from policy.json


def test_limits_used_are_the_ones_in_policy_json():
    raw = json.loads((DATA_DIR / "policy.json").read_text(encoding="utf-8"))
    assert (
        POLICY.number("P2", "duplicate_window_minutes")
        == raw["policies"]["P2"]["params"]["duplicate_window_minutes"]
    )
    assert POLICY.number("P7", "grace_minutes") == raw["policies"]["P7"]["params"]["grace_minutes"]
    assert [p for p, r in raw["policies"].items() if r["auto_resolve"]] == ["P2", "P7"]


# ---------------------------------------------------------------- P2 boundaries


def test_p2_taps_exactly_at_the_window_auto_resolve():
    (exc,) = _p2([(f"{MON}T09:00:00", "in"), (f"{MON}T09:05:00", "in"), *_rest()])
    assert exc.status == "auto_resolved"
    assert _auto(exc) == {
        "basis": "2 'in' taps 5 min apart, within the 5 min duplicate window",
        "eligible": True,
        "held_because": [],
    }
    assert [o.option_id for o in exc.fix_options] == ["void_duplicate"]
    assert exc.fix_options[0].params == {"punch_ids": ["P0002"]}


def test_p2_one_second_outside_the_window_is_not_a_duplicate_at_all():
    assert _p2([(f"{MON}T09:00:00", "in"), (f"{MON}T09:05:01", "in"), *_rest()]) == []


def test_p2_window_follows_policy_json():
    policy = policy_with({("P2", "duplicate_window_minutes"): 2})
    taps = [(f"{MON}T09:00:00", "in"), (f"{MON}T09:03:00", "in"), *_rest()]
    assert _p2(taps, policy=policy) == []
    assert _p2(taps)[0].status == "auto_resolved"


# ---------------------------------------------------------------- P2 held for a person


def test_p2_chained_taps_spanning_more_than_the_window_are_held():
    taps = [(f"{MON}T09:00:00", "in"), (f"{MON}T09:04:00", "in"), (f"{MON}T09:08:00", "in")]
    (exc,) = _p2([*taps, *_rest()])
    assert exc.status == "open"
    assert _auto(exc)["eligible"] is False
    assert _auto(exc)["held_because"] == [
        "the taps span 8 min, more than the 5 min window (chained taps)"
    ]


def test_p2_taps_from_two_devices_are_held():
    taps = [(f"{MON}T09:00:00", "in"), (f"{MON}T09:02:00", "in", "E001", {"device_id": "G2"})]
    (exc,) = _p2([*taps, *_rest()])
    assert exc.status == "open"
    assert _auto(exc)["held_because"] == ["the taps came from different devices"]


def test_p2_taps_from_two_locations_are_held():
    taps = [(f"{MON}T09:00:00", "in"), (f"{MON}T09:02:00", "in", "E001", {"location": "Other"})]
    (exc,) = _p2([*taps, *_rest()])
    assert exc.status == "open"
    assert "the taps came from different locations" in _auto(exc)["held_because"]


def test_p2_tap_under_punch_review_is_held():
    # Another worker taps the same terminal in the same second: P17 reviews P0001.
    taps = [
        (f"{MON}T09:00:00", "in"),
        (f"{MON}T09:02:00", "in"),
        (f"{MON}T09:00:00", "in", "E002"),
    ]
    result = run([*taps, *_rest()], SHIFT)
    assert only(result, "P17")
    (exc,) = [e for e in only(result, "P2") if e.employee_id == "E001"]
    assert exc.status == "open"
    assert _auto(exc)["held_because"] == ["a tap is also under punch review (P17)"]


def test_p2_switched_off_in_policy_json_is_held_with_the_reason():
    policy = policy_with({("P2", "auto_resolve"): False})
    (exc,) = _p2([(f"{MON}T09:00:00", "in"), (f"{MON}T09:02:00", "in"), *_rest()], policy=policy)
    assert exc.status == "open"
    assert _auto(exc)["held_because"] == ["auto_resolve is off for P2 in policy.json"]


# ---------------------------------------------------------------- P7 boundaries


@pytest.mark.parametrize(
    ("clock_in", "expected"),
    [
        ("09:00:00", None),  # on time: nothing at all
        ("09:00:01", "auto_resolved"),
        ("09:10:00", "auto_resolved"),  # exactly at the grace limit
        ("09:10:01", "open"),  # just outside: a real late arrival for a person
    ],
)
def test_p7_grace_boundaries(clock_in, expected):
    found = _p7([(f"{MON}T{clock_in}", "in"), *_rest()])
    if expected is None:
        assert found == []
        return
    (exc,) = found
    assert exc.status == expected
    if expected == "auto_resolved":
        assert _auto(exc)["eligible"] is True
        assert "within the 10 min grace" in _auto(exc)["basis"]
    else:
        assert not is_candidate(exc)  # beyond grace: never a candidate
        assert [o.option_id for o in exc.fix_options] == ["accept_reason", "record_as_late"]


def test_p7_grace_follows_policy_json():
    policy = policy_with({("P7", "grace_minutes"): 5})
    (exc,) = _p7([(f"{MON}T09:07:00", "in"), *_rest()], policy=policy)
    assert exc.status == "open" and not is_candidate(exc)


def test_p7_with_two_clock_ins_is_held():
    punches = [(f"{MON}T09:05:00", "in"), (f"{MON}T09:30:00", "in"), *_rest()]
    (exc,) = _p7(punches)
    assert exc.status == "open"
    assert _auto(exc)["held_because"] == ["the shift has 2 clock-ins"]


def test_p7_clock_in_under_punch_review_is_held():
    punches = [(f"{MON}T09:05:00", "in"), (f"{MON}T09:05:00", "in", "E002"), *_rest()]
    result = run(punches, SHIFT)
    assert only(result, "P17")
    (exc,) = [e for e in only(result, "P7") if e.employee_id == "E001"]
    assert exc.status == "open"
    assert _auto(exc)["held_because"] == ["the clock-in is under punch review (P17)"]


def test_p7_switched_off_creates_nothing_within_grace():
    policy = policy_with({("P7", "auto_resolve"): False})
    assert _p7([(f"{MON}T09:05:00", "in"), *_rest()], policy=policy) == []


# ---------------------------------------------------------------- never other policies


def test_policy_json_cannot_turn_on_auto_resolve_for_another_policy():
    raw = json.loads((DATA_DIR / "policy.json").read_text(encoding="utf-8"))
    raw["policies"]["P3"]["auto_resolve"] = True
    with pytest.raises(ValidationError, match=r"only allowed for \['P2', 'P7'\], not for \['P3'\]"):
        PolicyConfig.model_validate(raw)


def test_demo_run_auto_resolves_only_allowed_and_eligible_cases():
    from datetime import datetime

    from attendflow.data import load_dataset
    from attendflow.engine import run_engine

    result = run_engine(load_dataset(DATA_DIR), POLICY, datetime(2026, 4, 16, 8, 0))
    auto = [e for e in result.exceptions if e.status == "auto_resolved"]
    assert [e.exception_id for e in auto] == ["P2-E005-2026-04-13-P0003"]
    for exc in result.exceptions:
        if exc.status == "auto_resolved":
            assert exc.policy_id in AUTO_RESOLVABLE and _auto(exc)["eligible"] is True
        if exc.policy_id not in AUTO_RESOLVABLE:
            assert "auto_resolve" not in exc.details
