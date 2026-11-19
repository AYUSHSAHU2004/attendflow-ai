"""Pydantic row models for every CSV file.

Each model's field order is the CSV column order. Extra columns are forbidden, so for
example a stored "balance" column in leave_balances.csv fails validation (balance is
always computed in code as total_per_year - used).
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    model_validator,
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")
_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$")  # no offset allowed


def _parse_date(v: Any) -> date:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if not isinstance(v, str) or not _DATE_RE.match(v):
        raise ValueError(f"expected a date like 2026-04-13, got {v!r}")
    return date.fromisoformat(v)  # also rejects impossible dates like 2026-02-30


def _parse_time(v: Any) -> time:
    if isinstance(v, time):
        return v
    if not isinstance(v, str) or not _TIME_RE.match(v):
        raise ValueError(f"expected a time like 09:00, got {v!r}")
    return time.fromisoformat(v)


def _parse_timestamp(v: Any) -> datetime:
    if isinstance(v, datetime):
        if v.tzinfo is not None:
            raise ValueError("timestamp must be plain local time (no timezone)")
        return v
    if not isinstance(v, str) or not _TS_RE.match(v):
        raise ValueError(
            f"expected a local timestamp like 2026-04-13T09:00:00 (no timezone), got {v!r}"
        )
    return datetime.fromisoformat(v)


def _parse_yes_no(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v in ("yes", "no"):
        return v == "yes"
    raise ValueError(f"expected 'yes' or 'no', got {v!r}")


def _empty_to_none(v: Any) -> Any:
    return None if v == "" else v


# JSON output uses the same formats the CSVs use, so a dumped row loads back unchanged
# (the engine puts these rows in exception evidence, which the API will send as JSON).
LocalDate = Annotated[date, BeforeValidator(_parse_date)]
LocalTime = Annotated[
    time,
    BeforeValidator(_parse_time),
    PlainSerializer(lambda t: t.strftime("%H:%M"), return_type=str, when_used="json"),
]
LocalTimestamp = Annotated[
    datetime,
    BeforeValidator(_parse_timestamp),
    PlainSerializer(lambda ts: ts.isoformat(timespec="seconds"), return_type=str, when_used="json"),
]
YesNo = Annotated[
    bool,
    BeforeValidator(_parse_yes_no),
    PlainSerializer(lambda b: "yes" if b else "no", return_type=str, when_used="json"),
]
EmployeeId = Annotated[str, Field(pattern=r"^E\d{3}$")]
LeaveType = Literal["sick", "casual", "earned"]


class CsvRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class Employee(CsvRow):
    employee_id: EmployeeId
    name: str = Field(min_length=1)
    role: Literal["worker", "supervisor", "payroll_admin"]
    team: str = Field(min_length=1)
    supervisor_id: Annotated[EmployeeId | None, BeforeValidator(_empty_to_none)] = None


class Punch(CsvRow):
    punch_id: str = Field(pattern=r"^P\d{4,}$")
    employee_id: EmployeeId
    timestamp: LocalTimestamp
    type: Literal["in", "out", "break_start", "break_end"]
    source: Literal["device", "app"]
    device_id: str = Field(min_length=1)
    location: str = Field(min_length=1)


class ScheduleRow(CsvRow):
    employee_id: EmployeeId
    date: LocalDate
    shift_start: LocalTime
    shift_end: LocalTime

    @model_validator(mode="after")
    def _non_zero_length(self) -> ScheduleRow:
        if self.shift_start == self.shift_end:
            raise ValueError("shift_start and shift_end must differ")
        return self

    @property
    def crosses_midnight(self) -> bool:
        """A shift whose end is earlier than its start finishes on the next day."""
        return self.shift_end < self.shift_start


class LeaveRecord(CsvRow):
    employee_id: EmployeeId
    date: LocalDate
    leave_type: LeaveType
    duration: Literal["full", "half"]
    status: Literal["approved", "pending", "rejected"]
    certificate_uploaded: YesNo


class LeaveBalance(CsvRow):
    employee_id: EmployeeId
    leave_type: LeaveType
    total_per_year: float = Field(ge=0)
    used: float = Field(ge=0)


class Holiday(CsvRow):
    date: LocalDate
    name: str = Field(min_length=1)
    type: Literal["national", "company", "optional"]


# File name -> row model. Column order = model field order.
CSV_MODELS: dict[str, type[CsvRow]] = {
    "employees.csv": Employee,
    "timecards.csv": Punch,
    "schedule.csv": ScheduleRow,
    "leave_records.csv": LeaveRecord,
    "leave_balances.csv": LeaveBalance,
    "holidays.csv": Holiday,
}


def columns_for(model: type[CsvRow]) -> list[str]:
    return list(model.model_fields)
