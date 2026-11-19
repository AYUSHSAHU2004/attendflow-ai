"""Phase 4: fix options for P3, P4, P6 and P7, built by the engine from facts only."""

from __future__ import annotations

import typing
from datetime import datetime

import pytest

from attendflow.engine.models import ACTION_INFO, FixAction, FixOption
from attendflow.fixes.params import DATA_ACTIONS, DECISION_ACTIONS, REQUIRED_NOTE
from tests.engine_helpers import day_shift, only, run

MON, TUE, WED, THU = "2026-04-13", "2026-04-14", "2026-04-15", "2026-04-16"
LATE_LUNCH = ("18:00", "19:00")


def by_id(exc) -> dict[str, FixOption]:
    return {o.option_id: o for o in exc.fix_options}


@pytest.fixture(scope="module")
def demo(dataset):
    from attendflow.engine import run_engine
    from tests.engine_helpers import POLICY

    return run_engine(dataset, POLICY, datetime(2026, 4, 16, 8, 0))


def demo_exc(result, exception_id):
    return next(e for e in result.exceptions if e.exception_id == exception_id)


# ---------------------------------------------------------------- the action catalogue


def test_every_action_has_info_and_exactly_one_kind():
    actions = set(typing.get_args(FixAction))
    assert actions == set(ACTION_INFO)
    assert set(DATA_ACTIONS) | DECISION_ACTIONS == actions
    assert not set(DATA_ACTIONS) & DECISION_ACTIONS
    for action, (decision_only, description) in ACTION_INFO.items():
        assert decision_only == (action in DECISION_ACTIONS), action
        assert description


def test_decision_only_is_derived_and_cannot_be_faked():
    opt = FixOption(option_id="x", action="approve_overtime", label="x")
    assert opt.decision_only is True and opt.description
    assert FixOption(option_id="x", action="add_break", label="x").decision_only is False
    with pytest.raises(ValueError, match="decision_only"):
        FixOption(option_id="x", action="add_break", label="x", decision_only=True)


def test_every_demo_option_names_its_policy_and_has_a_description(demo):
    for exc in demo.exceptions:
        for opt in exc.fix_options:
            assert opt.policy_id == exc.policy_id
            assert opt.description
            assert opt.decision_only == (opt.action not in DATA_ACTIONS)


def test_every_open_demo_exception_has_options(demo):
    # P2 is the only policy without options (auto-resolve handles it).
    missing = [e.exception_id for e in demo.exceptions if e.status == "open" and not e.fix_options]
    assert missing == []


def test_required_notes_are_in_the_option_params(demo):
    for exc in demo.exceptions:
        for opt in exc.fix_options:
            if opt.action in REQUIRED_NOTE:
                assert opt.params[REQUIRED_NOTE[opt.action]] == ""


# ---------------------------------------------------------------- P3 (Meena)


def test_meena_p3_options(demo):
    exc = demo_exc(demo, "P3-E002-2026-04-13")
    opts = by_id(exc)
    assert list(opts) == ["approve_overtime", "correct_clock_out"]

    overtime = opts["approve_overtime"]
    assert overtime.decision_only and overtime.params == {"date": MON, "hours": 3.0}
    assert not overtime.requires_worker_confirmation

    fix = opts["correct_clock_out"]
    assert fix.action == "correct_clock_out" and not fix.decision_only
    assert fix.requires_worker_confirmation  # policy: never remove hours without the worker
    # 06:59:47 in + 9 h + 30 min break = 16:29:47 (shown 16:30): exactly the 9 h limit.
    assert fix.params == {
        "punch_id": "P0031",
        "timestamp": "2026-04-13T16:29:47",
        "worked_hours_after_fix": 9.0,
    }
    assert "16:30" in fix.label and "19:30" in fix.label


def test_p3_with_two_shifts_offers_only_overtime():
    punches = day_shift(MON, "06:00", "11:00", None) + day_shift(MON, "12:00", "18:00", None)
    (exc,) = only(run(punches), "P3")
    assert [o.option_id for o in exc.fix_options] == ["approve_overtime"]


def test_p3_limit_clock_out_skips_breaks_before_it():
    punches = day_shift(MON, "07:00", "19:00", ("10:00", "10:30"))
    (exc,) = only(run(punches, [(MON, "07:00", "19:00")]), "P3")
    assert by_id(exc)["correct_clock_out"].params["timestamp"] == f"{MON}T16:30:00"


# ---------------------------------------------------------------- P4 (Neha)


def test_neha_p4_options(demo):
    exc = demo_exc(demo, "P4-E004-2026-04-13")
    opts = by_id(exc)
    assert list(opts) == ["record_break", "record_missed_break"]
    brk = opts["record_break"]
    assert brk.action == "add_break" and brk.requires_worker_confirmation
    # 08:59:37-14:59:37: the middle is 11:59:37 -> 12:00 on whole minutes, 30 min long.
    assert brk.params == {
        "break_start": f"{MON}T12:00:00",
        "break_end": f"{MON}T12:30:00",
        "worked_hours_after_fix": 5.5,
    }
    missed = opts["record_missed_break"]
    assert missed.decision_only and missed.params["follow_up"] == ""
    assert "never hidden" in missed.description


# ---------------------------------------------------------------- P6 (synthetic)


def test_p6_risk_with_upcoming_shift_offers_move_to_earliest_start():
    punches = day_shift(WED, "14:00", "23:00", LATE_LUNCH)
    schedule = [(WED, "14:00", "23:00"), (THU, "07:00", "16:00")]
    (exc,) = only(run(punches, schedule, as_of=datetime(2026, 4, 16, 1, 0)), "P6")
    opts = by_id(exc)
    assert list(opts) == ["record_short_rest", "move_next_shift_later"]
    move = opts["move_next_shift_later"]
    assert move.action == "move_shift" and not move.decision_only
    # 23:00 + 11 h = 10:00; the shift keeps its 9 h length.
    assert move.params == {
        "date": THU,
        "current_start": "07:00",
        "current_end": "16:00",
        "new_start": "10:00",
        "new_end": "19:00",
    }
    assert opts["record_short_rest"].params == {"date": THU, "rest_hours": 8.0, "reason": ""}


def test_p6_earliest_start_rounds_up_to_the_minute():
    punches = [(f"{WED}T14:00:00", "in"), (f"{WED}T23:00:20", "out")]
    schedule = [(WED, "14:00", "23:00"), (THU, "07:00", "16:00")]
    (exc,) = only(run(punches, schedule, as_of=datetime(2026, 4, 16, 1, 0)), "P6")
    assert by_id(exc)["move_next_shift_later"].params["new_start"] == "10:01"


def test_p6_breach_only_records_the_reason():
    punches = day_shift(MON, "14:00", "23:00", LATE_LUNCH) + day_shift(TUE, "07:00", "16:00")
    schedule = [(MON, "14:00", "23:00"), (TUE, "07:00", "16:00")]
    (exc,) = only(run(punches, schedule), "P6")
    assert exc.kind == "breach"
    assert [o.option_id for o in exc.fix_options] == ["record_short_rest"]


def test_p6_no_move_when_it_would_change_the_shift_date():
    punches = [(f"{WED}T06:00:00", "in"), (f"{WED}T15:00:00", "out")]
    schedule = [(WED, "06:00", "15:00"), (THU, "00:30", "08:00")]
    as_of = datetime(2026, 4, 15, 16, 0)
    # 15:00 Wed + 11 h = 02:00 Thu: still Thursday, so the move is offered.
    (exc,) = only(run(punches, schedule, as_of=as_of), "P6")
    assert exc.date.isoformat() == THU
    assert by_id(exc)["move_next_shift_later"].params["new_start"] == "02:00"
    # With a 34 h minimum the earliest start is 01:00 Fri: the shift would change date (P15).
    (exc,) = only(run(punches, schedule, as_of=as_of, policy=_rest(34)), "P6")
    assert [o.option_id for o in exc.fix_options] == ["record_short_rest"]


def _rest(hours: float):
    from tests.engine_helpers import policy_with

    return policy_with({("P6", "min_rest_hours"): hours})


# ---------------------------------------------------------------- P7 (Karan + early leave)


def test_karan_p7_options_never_move_the_clock_in(demo):
    exc = demo_exc(demo, "P7-E006-2026-04-13-late")
    opts = by_id(exc)
    assert list(opts) == ["accept_reason", "record_as_late"]
    assert all(o.decision_only for o in opts.values())
    assert opts["accept_reason"].params == {
        "date": MON,
        "type": "late_arrival",
        "minutes": 90.0,
        "reason": "",
    }
    assert opts["record_as_late"].action == "record_lateness"
    # policy.md: no leave deduction, and the clock-in is never moved earlier.
    for exc in only(demo, "P7"):
        assert not {"set_clock_in", "edit_punches", "record_leave"} & {
            o.action for o in exc.fix_options
        }


def test_p7_early_leave_gets_the_same_decision_only_options():
    punches = [*day_shift(MON)[:-1], (f"{MON}T17:00:00", "out")]
    (exc,) = only(run(punches, [(MON, "09:00", "18:00")]), "P7")
    assert [o.option_id for o in exc.fix_options] == ["accept_reason", "record_as_early_leave"]
    assert exc.fix_options[0].params["type"] == "early_leave"
    assert exc.fix_options[0].params["minutes"] == 60


def test_p7_within_grace_has_only_the_confirm_option():
    # Phase 12: auto-resolved, but if a person undoes it they need one decision: confirm
    # it was within grace. No "record as late": policy.md says it is not counted as late.
    punches = [(f"{MON}T09:05:00", "in"), *day_shift(MON)[1:]]
    (exc,) = only(run(punches, [(MON, "09:00", "18:00")]), "P7")
    assert exc.status == "auto_resolved"
    assert [(o.option_id, o.action, o.decision_only) for o in exc.fix_options] == [
        ("confirm_within_grace", "confirm_within_grace", True)
    ]
