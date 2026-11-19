"""Inputs and outputs of the read-only tools.

Written for an LLM reader: few fields, plain names, times as "HH:MM" local, hours as
numbers. Every output has `ok`; a failed call returns ToolErrorResult instead of raising,
so the model can read the error and try again.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from attendflow.data.schemas import LeaveType, LocalDate
from attendflow.fixes.params import (
    AddBreakParams,
    AddPunchesParams,
    CorrectPunchParams,
    EditPunchesParams,
    LeaveDayParams,
    MoveShiftParams,
    PunchIdsParams,
    ReduceScheduleParams,
    SetClockParams,
)

EmployeeIdIn = Annotated[
    str, Field(pattern=r"^E\d{3}$", description="Employee ID, e.g. E001", examples=["E001"])
]
DateIn = Annotated[LocalDate, Field(description="Date as YYYY-MM-DD, e.g. 2026-04-14")]


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ToolOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: Literal[True] = True


class ToolError(BaseModel):
    code: str
    message: str
    hint: str | None = None


class ToolErrorResult(BaseModel):
    ok: Literal[False] = False
    error: ToolError


class ToolInputError(Exception):
    """Raised inside a tool for input it cannot answer (unknown employee, ...). The runner
    turns it into a ToolErrorResult."""

    def __init__(self, code: str, message: str, hint: str | None = None):
        super().__init__(message)
        self.error = ToolError(code=code, message=message, hint=hint)


# ---------------------------------------------------------------- inputs


class EmployeeDayIn(ToolInput):
    employee_id: EmployeeIdIn
    date: DateIn


class LeaveBalanceIn(ToolInput):
    employee_id: EmployeeIdIn
    leave_type: LeaveType = Field(description="sick, casual or earned")


class PolicyIn(ToolInput):
    policy_id: str = Field(
        min_length=2, max_length=4, description="Policy ID P1 to P17, e.g. P3", examples=["P3"]
    )


# run_checks: the same {action, params} shape as a fix option, so the model can copy an
# option's action and params straight into a proposal (and then change a time).


class _Change(ToolInput):
    pass


class SetClockInChange(_Change):
    action: Literal["set_clock_in"]
    params: SetClockParams


class SetClockOutChange(_Change):
    action: Literal["set_clock_out"]
    params: SetClockParams


class CorrectClockOutChange(_Change):
    action: Literal["correct_clock_out"]
    params: CorrectPunchParams


class AddBreakChange(_Change):
    action: Literal["add_break"]
    params: AddBreakParams


class AddPunchesChange(_Change):
    action: Literal["add_punches"]
    params: AddPunchesParams


class VoidPunchesChange(_Change):
    action: Literal["void_punches"]
    params: PunchIdsParams


class EditPunchesChange(_Change):
    action: Literal["edit_punches"]
    params: EditPunchesParams


class MoveShiftChange(_Change):
    action: Literal["move_shift"]
    params: MoveShiftParams


class ReduceScheduleChange(_Change):
    action: Literal["reduce_scheduled_hours"]
    params: ReduceScheduleParams


class RecordLeaveChange(_Change):
    action: Literal["record_leave"]
    params: LeaveDayParams


class CancelLeaveChange(_Change):
    action: Literal["cancel_leave"]
    params: LeaveDayParams


ProposedChange = Annotated[
    SetClockInChange
    | SetClockOutChange
    | CorrectClockOutChange
    | AddBreakChange
    | AddPunchesChange
    | VoidPunchesChange
    | EditPunchesChange
    | MoveShiftChange
    | ReduceScheduleChange
    | RecordLeaveChange
    | CancelLeaveChange,
    Field(discriminator="action"),
]


class RunChecksIn(ToolInput):
    employee_id: EmployeeIdIn
    date: DateIn = Field(description="The shift date the change is for (YYYY-MM-DD)")
    proposed_change: ProposedChange = Field(
        description="A data change in the same {action, params} shape as a fix option. "
        "Timestamps are local, e.g. 2026-04-14T19:30."
    )


# ---------------------------------------------------------------- outputs


class ScheduleOut(ToolOutput):
    employee_id: str
    date: str
    scheduled: bool
    start: str | None = None
    end: str | None = None
    ends_next_day: bool | None = None
    planned_hours: float | None = Field(None, description="Length minus the planned unpaid lunch")
    holiday: str | None = None
    note: str | None = None


class LeaveOut(ToolOutput):
    employee_id: str
    date: str
    on_leave: bool
    leave_type: str | None = None
    duration: Literal["full", "half"] | None = None
    status: Literal["approved", "pending"] | None = None
    certificate: bool | None = None
    note: str | None = None


class LeaveBalanceOut(ToolOutput):
    employee_id: str
    leave_type: str
    year: int
    total_per_year: float
    used: float
    pending_days: float
    balance: float = Field(description="total_per_year - used")
    balance_after_pending: float


class PunchOut(BaseModel):
    id: str
    time: str
    type: Literal["in", "out", "break_start", "break_end"]
    source: Literal["device", "app", "correction"]
    duplicate: bool | None = None  # a P2 duplicate tap not yet voided


class ShiftOut(BaseModel):
    scheduled: str | None = None
    status: str
    clock_in: str | None = None
    clock_out: str | None = None
    break_minutes: float
    worked_hours: float | None = None
    punches: list[PunchOut]


class PunchesOut(ToolOutput):
    employee_id: str
    date: str
    shifts: list[ShiftOut]
    note: str | None = None


class PolicyOut(ToolOutput):
    policy_id: str
    title: str
    text: str = Field(description="The policy.md section, word for word")
    limits: dict[str, Any] = Field(description="The params from policy.json")


class Finding(BaseModel):
    policy_id: str
    kind: Literal["breach", "risk"] | None = None
    date: str
    reason: str
    numbers: dict[str, float] | None = None


class RunChecksOut(ToolOutput):
    employee_id: str
    week: str
    verdict: str
    new_violations: list[Finding]
    resolved: list[Finding]
    still_open: list[Finding]
    day_worked_hours: float | None = None
    week_projected_hours: float
    weekly_limit_hours: float
