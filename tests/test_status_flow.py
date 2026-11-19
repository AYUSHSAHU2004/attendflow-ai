"""Status flow and fix-param rules (pure code, no database)."""

from __future__ import annotations

import ast
import itertools
from pathlib import Path
from typing import get_args

import pytest

from attendflow.cases.transitions import ALLOWED, FINAL, can_transition, check_transition
from attendflow.config import REPO_ROOT
from attendflow.engine.models import FixAction
from attendflow.errors import InvalidTransitionError
from attendflow.fixes.apply import APPLIERS
from attendflow.fixes.params import (
    DATA_ACTIONS,
    DECISION_ACTIONS,
    FixParamsError,
    parse_params,
)

STATUSES = ["open", "awaiting_worker", "awaiting_supervisor", "resolved", "rejected", "escalated"]

EXPECTED = {
    ("open", "awaiting_worker"),
    ("open", "awaiting_supervisor"),
    ("open", "resolved"),
    ("open", "escalated"),
    ("awaiting_worker", "awaiting_supervisor"),
    ("awaiting_worker", "escalated"),
    ("awaiting_supervisor", "resolved"),
    ("awaiting_supervisor", "awaiting_worker"),
    ("awaiting_supervisor", "escalated"),
    ("escalated", "awaiting_supervisor"),
    ("escalated", "resolved"),
    ("escalated", "rejected"),
}


def test_status_list_matches_db_constraint():
    from attendflow.db.models import EXCEPTION_STATUSES

    assert sorted(ALLOWED) == sorted(EXCEPTION_STATUSES) == sorted(STATUSES)


@pytest.mark.parametrize("current,target", list(itertools.product(STATUSES, STATUSES)))
def test_every_transition_pair(current, target):
    assert can_transition(current, target) == ((current, target) in EXPECTED)


def test_final_statuses():
    assert FINAL == {"resolved", "rejected"}


def test_only_escalated_can_become_rejected():
    """A supervisor's reject escalates; only the escalated case's assignee ends it."""
    assert [s for s in STATUSES if can_transition(s, "rejected")] == ["escalated"]


def test_invalid_transition_error_is_clear():
    with pytest.raises(InvalidTransitionError) as err:
        check_transition("awaiting_worker", "resolved", action="approve")
    assert err.value.status_code == 409
    assert err.value.code == "invalid_transition"
    assert "awaiting_worker" in err.value.message and "resolved" in err.value.message
    assert err.value.details["allowed"] == ["awaiting_supervisor", "escalated"]

    with pytest.raises(InvalidTransitionError, match="final"):
        check_transition("rejected", "open")


# ---------------------------------------------------------------- fix actions


def test_every_fix_action_has_exactly_one_handler():
    actions = set(get_args(FixAction))
    assert set(DATA_ACTIONS) | DECISION_ACTIONS == actions
    assert not set(DATA_ACTIONS) & DECISION_ACTIONS
    assert set(APPLIERS) == set(DATA_ACTIONS)


def test_decision_params_cannot_add_keys_or_change_types():
    original = {"hours": 8.0}
    assert parse_params("approve_overtime", original, {"hours": 6}) == {"hours": 6}
    with pytest.raises(FixParamsError, match="unknown param"):
        parse_params("approve_overtime", original, {"hours": 8.0, "bonus": 1})
    with pytest.raises(FixParamsError, match="must be a number"):
        parse_params("approve_overtime", original, {"hours": "lots"})
    with pytest.raises(FixParamsError, match="negative"):
        parse_params("approve_overtime", original, {"hours": -1})


def test_edit_punches_needs_new_times_for_listed_punches():
    original = {"punch_ids": ["P0049", "P0055"]}
    with pytest.raises(FixParamsError):
        parse_params("edit_punches", original, original)
    with pytest.raises(FixParamsError):
        parse_params(
            "edit_punches",
            original,
            {**original, "changes": [{"punch_id": "P9999", "timestamp": "2026-04-15T13:00"}]},
        )
    ok = parse_params(
        "edit_punches",
        original,
        {**original, "changes": [{"punch_id": "P0055", "timestamp": "2026-04-15T13:00"}]},
    )
    assert ok.changes[0].punch_id == "P0055"


def test_clock_params_reject_timezones_and_bad_cuts():
    with pytest.raises(FixParamsError):
        parse_params("set_clock_out", {}, {"timestamp": "2026-04-14T18:00+05:30"})
    with pytest.raises(FixParamsError):
        parse_params(
            "reduce_scheduled_hours",
            {},
            {"cuts": [{"date": "2026-04-17", "scheduled_hours": 6, "new_hours": 7}]},
        )
    cut = parse_params(
        "reduce_scheduled_hours",
        {},
        {
            "total_cut_hours": 99,
            "cuts": [{"date": "2026-04-17", "scheduled_hours": 6, "new_hours": 2}],
        },
    )
    assert cut.total_cut_hours == 4  # recomputed, never trusted from input


# ---------------------------------------------------------------- write guard

BACKEND = REPO_ROOT / "backend" / "attendflow"
PROTECTED = {"PunchRow", "ScheduleEntryRow", "LeaveRecordRow", "LeaveBalanceRow"}
# models.py defines them, dataset.py only reads them, seed.py is the demo reset,
# apply.py is the one place approved fixes are written.
ALLOWED_MODULES = {"db/models.py", "db/dataset.py", "db/seed.py", "fixes/apply.py"}


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.Name | ast.Attribute):
            names.add(node.id if isinstance(node, ast.Name) else node.attr)
    return names


def test_only_apply_and_seed_touch_source_tables():
    """Nothing but fixes/apply.py (and the demo seed) may modify timecards and leave."""
    offenders = []
    for path in BACKEND.rglob("*.py"):
        rel = path.relative_to(BACKEND).as_posix()
        if rel in ALLOWED_MODULES or rel.startswith("db/migrations/"):
            continue
        used = _imported_names(path) & PROTECTED
        if used:
            offenders.append(f"{rel}: {sorted(used)}")
    assert not offenders, "source tables used outside fixes/apply.py: " + "; ".join(offenders)


def test_dataset_reader_never_writes():
    src = (BACKEND / "db" / "dataset.py").read_text(encoding="utf-8")
    for call in (".add(", ".delete(", ".execute(", "insert(", "update(", ".merge("):
        assert call not in src, f"db/dataset.py must be read-only, found {call!r}"


# ---------------------------------------------------------------- test database guard


@pytest.mark.parametrize("name", ["attendflow_test", "ci_test"])
def test_guard_accepts_test_databases(name):
    from tests.conftest import check_test_database_name

    check_test_database_name(name)


@pytest.mark.parametrize("name", ["attendflow", "postgres", "attendflow_test_copy", "", None])
def test_guard_refuses_other_databases(name):
    from tests.conftest import UnsafeTestDatabaseError, check_test_database_name

    with pytest.raises(UnsafeTestDatabaseError, match="_test"):
        check_test_database_name(name)
