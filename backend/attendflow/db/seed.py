"""Demo reset: wipe every table and load the CSVs again.

This is one of the two places allowed to write the source tables (the other is
fixes/apply.py). POST /api/seed calls it; it must be disabled or protected on a deployed
server (ATTENDFLOW_ENABLE_SEED=false, Phase 22).
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from attendflow.data.loader import Dataset, load_dataset
from attendflow.data.schemas import Punch, ScheduleRow
from attendflow.db.credentials import hash_password
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


def add_demo_week(ds: Dataset) -> None:
    """Add five short, complete shifts per worker to the preceding demo week."""
    workers = [row for row in ds.employees if row.role == "worker"]
    next_id = max((int(p.punch_id[1:]) for p in ds.punches), default=0) + 1
    for day in range(5):
        on = date(2026, 4, 6) + timedelta(days=day)
        for index, worker in enumerate(workers):
            start = datetime.combine(on, time(9)) + timedelta(minutes=index)
            end = start + timedelta(hours=4)
            ds.schedule.append(
                ScheduleRow(
                    employee_id=worker.employee_id,
                    date=on,
                    shift_start=start.time(),
                    shift_end=end.time(),
                )
            )
            for kind, stamp in (("in", start), ("out", end)):
                ds.punches.append(
                    Punch(
                        punch_id=f"P{next_id:04d}",
                        employee_id=worker.employee_id,
                        timestamp=stamp,
                        type=kind,
                        source="device",
                        device_id="GATE-01",
                        location="Warehouse 1 - Inbound Gate",
                    )
                )
                next_id += 1


def _demo_email(name: str, employee_id: str, used: set[str]) -> str:
    first = re.sub(r"[^a-z0-9]", "", name.split()[0].lower()) or employee_id.lower()
    email = f"{first}@demo.attendflow.test"
    if email in used:
        email = f"{first}-{employee_id.lower()}@demo.attendflow.test"
    used.add(email)
    return email


def seed_demo_once(
    session: Session, data_dir: Path, *, extra_week: bool, demo_password: str
) -> dict[str, int]:
    """Bootstrap an empty demo, or provision missing credentials on matching synthetic data."""
    session.execute(text("LOCK TABLE employees IN ACCESS EXCLUSIVE MODE"))
    existing = {row.employee_id: row for row in session.scalars(select(EmployeeRow))}
    if not existing:
        return seed_from_csv(session, data_dir, extra_week=extra_week, demo_password=demo_password)
    dataset = load_dataset(data_dir)
    if set(existing) != {row.employee_id for row in dataset.employees} or any(
        any(
            getattr(existing[row.employee_id], key) != value
            for key, value in row.model_dump().items()
        )
        for row in dataset.employees
    ):
        raise ValueError("Existing employees do not match the synthetic demo dataset")
    used: set[str] = set()
    provisioned = 0
    for employee in sorted(dataset.employees, key=lambda row: row.employee_id):
        row = existing[employee.employee_id]
        email = _demo_email(row.name, row.employee_id, used)
        if row.email is None:
            row.email = email
        if row.password_hash is None:
            row.password_hash = hash_password(demo_password)
            provisioned += 1
    return {"employees": len(existing), "credentials_provisioned": provisioned}


def seed_from_csv(
    session: Session,
    data_dir: Path,
    *,
    extra_week: bool = False,
    demo_password: str | None = None,
) -> dict[str, int]:
    """Validate the CSVs (all errors at once), then replace all data. Caller commits."""
    ds = load_dataset(data_dir)  # raises DataValidationError before anything is wiped
    if extra_week:
        add_demo_week(ds)
    truncate_all(session)

    # Supervisors first, so the supervisor_id foreign key is always satisfied.
    employees = sorted(ds.employees, key=lambda e: (e.supervisor_id is not None, e.employee_id))
    used: set[str] = set()
    for e in employees:
        row = EmployeeRow(**e.model_dump())
        if demo_password:
            row.email = _demo_email(row.name, row.employee_id, used)
            row.password_hash = hash_password(demo_password)
        session.add(row)
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
