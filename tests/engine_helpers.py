"""Small builders for synthetic engine fixtures (one worker, a few punches)."""

from __future__ import annotations

import json
from datetime import datetime

from attendflow.data import Dataset
from attendflow.data.schemas import Employee, Punch, ScheduleRow
from attendflow.engine import EngineResult, TimecardException, run_engine
from attendflow.policy import PolicyConfig, load_policy
from tests.conftest import DATA_DIR

POLICY = load_policy(DATA_DIR / "policy.json")
LATE_AS_OF = datetime(2026, 4, 20, 8, 0)  # after the whole demo week: everything is past


def policy_with(changes: dict[tuple[str, str], object]) -> PolicyConfig:
    """A copy of the real policy with some params (or auto_resolve) changed."""
    raw = json.loads((DATA_DIR / "policy.json").read_text(encoding="utf-8"))
    for (pid, name), value in changes.items():
        if name == "auto_resolve":
            raw["policies"][pid]["auto_resolve"] = value
        else:
            raw["policies"][pid]["params"][name] = value
    return PolicyConfig.model_validate(raw)


def make_dataset(
    punches: list[tuple[str, str]] | list[tuple[str, str, str]],
    schedule: list[tuple[str, str, str]] | list[tuple[str, str, str, str]] = (),
) -> Dataset:
    """punches: (timestamp, type[, employee]); schedule: (date, start, end[, employee]).
    The employee defaults to E001."""
    employees = [
        Employee(employee_id="E101", name="Sup", role="supervisor", team="T"),
        Employee(employee_id="E001", name="One", role="worker", team="T", supervisor_id="E101"),
        Employee(employee_id="E002", name="Two", role="worker", team="T", supervisor_id="E101"),
    ]
    punch_rows = [
        Punch.model_validate(
            {
                "punch_id": f"P{i:04d}",
                "employee_id": p[2] if len(p) > 2 else "E001",
                "timestamp": p[0],
                "type": p[1],
                "source": "device",
                "device_id": "GATE-01",
                "location": "Test",
            }
        )
        for i, p in enumerate(punches, start=1)
    ]
    schedule_rows = [
        ScheduleRow.model_validate(
            {
                "employee_id": s[3] if len(s) > 3 else "E001",
                "date": s[0],
                "shift_start": s[1],
                "shift_end": s[2],
            }
        )
        for s in schedule
    ]
    return Dataset(
        employees=employees,
        punches=punch_rows,
        schedule=schedule_rows,
        leave_records=[],
        leave_balances=[],
        holidays=[],
    )


def day_shift(day: str, start: str = "09:00", end: str = "18:00", lunch=("13:00", "14:00")):
    """Punches for one simple day shift. lunch=None means no break punches."""
    rows = [(f"{day}T{start}:00", "in")]
    if lunch:
        rows += [(f"{day}T{lunch[0]}:00", "break_start"), (f"{day}T{lunch[1]}:00", "break_end")]
    return [*rows, (f"{day}T{end}:00", "out")]


def run(
    punches,
    schedule=(),
    *,
    as_of: datetime = LATE_AS_OF,
    policy: PolicyConfig = POLICY,
    policies: list[str] | None = None,
) -> EngineResult:
    return run_engine(make_dataset(punches, schedule), policy, as_of, policies)


def only(result: EngineResult, policy_id: str) -> list[TimecardException]:
    return [e for e in result.exceptions if e.policy_id == policy_id]
