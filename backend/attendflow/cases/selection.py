"""Shared filters for reporting on current exception state."""

from datetime import date
from typing import Any

from sqlalchemy import Select, and_, select

from attendflow.cases.no_reply import STAGE_KEYS
from attendflow.cases.transitions import ALLOWED, FINAL
from attendflow.db.models import EmployeeRow, ExceptionRow
from attendflow.errors import InvalidInputError

ACTIVE_STATUSES = tuple(status for status in ALLOWED if status not in FINAL)
NO_REPLY_STAGES = {key: stage for stage, key in STAGE_KEYS.items()}


def active_cases():
    return ExceptionRow.status.in_(ACTIVE_STATUSES)


def stuck_cases():
    return and_(active_cases(), ExceptionRow.no_reply_stage > 0)


def team_members(supervisor_id: str):
    return (
        select(EmployeeRow.employee_id)
        .where(EmployeeRow.supervisor_id == supervisor_id)
        .correlate(None)
    )


def validate_date_range(date_from: date | None, date_to: date | None) -> None:
    if date_from and date_to and date_from > date_to:
        raise InvalidInputError(
            "From date must be on or before To date", code="invalid_date_range"
        )


def scope_cases(
    stmt: Select[Any],
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    supervisor_id: str | None = None,
) -> Select[Any]:
    if date_from:
        stmt = stmt.where(ExceptionRow.date >= date_from)
    if date_to:
        stmt = stmt.where(ExceptionRow.date <= date_to)
    if supervisor_id:
        stmt = stmt.where(ExceptionRow.employee_id.in_(team_members(supervisor_id)))
    return stmt
