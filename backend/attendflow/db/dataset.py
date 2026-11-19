"""Read the source tables back into the engine's Dataset (read-only).

Detection runs on the database, not on the CSVs, so an approved fix shows up in the next
detection run. Voided punches are left out, exactly like the engine leaves out P2 taps.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from attendflow.data.loader import Dataset
from attendflow.data.schemas import (
    Employee,
    Holiday,
    LeaveBalance,
    LeaveRecord,
    Punch,
    ScheduleRow,
)
from attendflow.db.models import (
    EmployeeRow,
    HolidayRow,
    LeaveBalanceRow,
    LeaveRecordRow,
    PunchRow,
    ScheduleEntryRow,
)


def _fields(row: object, model: type) -> dict:
    return {name: getattr(row, name) for name in model.model_fields}


def load_schedule_day(session: Session, employee_id: str, day: date) -> ScheduleRow | None:
    row = session.scalar(
        select(ScheduleEntryRow).where(
            ScheduleEntryRow.employee_id == employee_id, ScheduleEntryRow.date == day
        )
    )
    return ScheduleRow.model_validate(_fields(row, ScheduleRow)) if row else None


def load_dataset_from_db(session: Session) -> Dataset:
    def rows(stmt):
        return session.scalars(stmt).all()

    return Dataset(
        employees=[
            Employee.model_validate(_fields(r, Employee))
            for r in rows(select(EmployeeRow).order_by(EmployeeRow.employee_id))
        ],
        punches=[
            Punch.model_validate(_fields(r, Punch))
            for r in rows(
                select(PunchRow)
                .where(PunchRow.voided.is_(False))
                .order_by(PunchRow.timestamp, PunchRow.punch_id)
            )
        ],
        schedule=[
            ScheduleRow.model_validate(_fields(r, ScheduleRow))
            for r in rows(
                select(ScheduleEntryRow).order_by(
                    ScheduleEntryRow.employee_id, ScheduleEntryRow.date
                )
            )
        ],
        leave_records=[
            LeaveRecord.model_validate(_fields(r, LeaveRecord))
            for r in rows(
                select(LeaveRecordRow).order_by(LeaveRecordRow.employee_id, LeaveRecordRow.date)
            )
        ],
        leave_balances=[
            LeaveBalance.model_validate(_fields(r, LeaveBalance))
            for r in rows(
                select(LeaveBalanceRow).order_by(
                    LeaveBalanceRow.employee_id, LeaveBalanceRow.leave_type
                )
            )
        ],
        holidays=[
            Holiday.model_validate(_fields(r, Holiday))
            for r in rows(select(HolidayRow).order_by(HolidayRow.date))
        ],
    )
