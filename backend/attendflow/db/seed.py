"""Demo reset: wipe every table and load the CSVs again.

This is one of the two places allowed to write the source tables (the other is
fixes/apply.py). POST /api/seed calls it; it must be disabled or protected on a deployed
server (ATTENDFLOW_ENABLE_SEED=false, Phase 22).
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from attendflow.data.loader import load_dataset
from attendflow.db.models import (
    Base,
    EmployeeRow,
    HolidayRow,
    LeaveBalanceRow,
    LeaveRecordRow,
    PunchRow,
    ScheduleEntryRow,
)


def truncate_all(session: Session) -> None:
    names = ", ".join(t.name for t in Base.metadata.sorted_tables)
    session.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


def seed_from_csv(session: Session, data_dir: Path) -> dict[str, int]:
    """Validate the CSVs (all errors at once), then replace all data. Caller commits."""
    ds = load_dataset(data_dir)  # raises DataValidationError before anything is wiped
    truncate_all(session)

    # Supervisors first, so the supervisor_id foreign key is always satisfied.
    employees = sorted(ds.employees, key=lambda e: (e.supervisor_id is not None, e.employee_id))
    for e in employees:
        session.add(EmployeeRow(**e.model_dump()))
        session.flush()
    session.add_all(PunchRow(**p.model_dump()) for p in ds.punches)
    session.add_all(ScheduleEntryRow(**s.model_dump()) for s in ds.schedule)
    session.add_all(LeaveRecordRow(**r.model_dump()) for r in ds.leave_records)
    session.add_all(LeaveBalanceRow(**b.model_dump()) for b in ds.leave_balances)
    session.add_all(HolidayRow(**h.model_dump()) for h in ds.holidays)
    session.flush()
    return {
        "employees": len(ds.employees),
        "timecards": len(ds.punches),
        "schedule": len(ds.schedule),
        "leave_records": len(ds.leave_records),
        "leave_balances": len(ds.leave_balances),
        "holidays": len(ds.holidays),
    }
