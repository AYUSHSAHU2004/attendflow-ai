"""Pydantic models for the params of every data-changing fix action.

The engine builds the params; a supervisor may change them with "edit". Either way they
are validated here before anything is written. Decision-only actions (approve overtime,
holiday pay, ...) change no data, so for them an edit may only change values, never add
or remove keys, and numbers stay numbers (see validate_decision_params).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from attendflow.data.schemas import LeaveType, LocalDate, LocalTime, LocalTimestamp


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class DayAmount(Params):
    date: LocalDate
    days: float = Field(gt=0, le=1)


class SetClockParams(Params):
    timestamp: LocalTimestamp
    worked_hours_after_fix: float | None = None  # shown to the human; recomputed by detection


class AddPunchesParams(Params):
    clock_in: LocalTimestamp
    clock_out: LocalTimestamp

    @model_validator(mode="after")
    def _order(self) -> AddPunchesParams:
        if self.clock_out <= self.clock_in:
            raise ValueError("clock_out must be after clock_in")
        return self


class PunchIdsParams(Params):
    punch_ids: list[str] = Field(min_length=1)


class RejectUnscheduledParams(PunchIdsParams):
    date: LocalDate


class PunchChange(Params):
    punch_id: str
    timestamp: LocalTimestamp


class EditPunchesParams(PunchIdsParams):
    # The engine only lists which punches may change; the new times come from the
    # supervisor's edit (or, later, from the worker's confirmed reply).
    changes: list[PunchChange] = Field(default_factory=list)

    @model_validator(mode="after")
    def _changes_in_scope(self) -> EditPunchesParams:
        if not self.changes:
            raise ValueError(
                "edit_punches needs the new times: use edit with params.changes = "
                '[{"punch_id": ..., "timestamp": ...}]'
            )
        outside = [c.punch_id for c in self.changes if c.punch_id not in self.punch_ids]
        if outside:
            raise ValueError(f"punch(es) {outside} are not part of this fix option")
        if len({c.punch_id for c in self.changes}) != len(self.changes):
            raise ValueError("each punch may be changed only once")
        return self


class CorrectPunchParams(Params):
    """Replace one wrong punch (P3: the clock-out) with the time the worker confirms."""

    punch_id: str
    timestamp: LocalTimestamp
    worked_hours_after_fix: float | None = None  # shown to the human; recomputed by detection


class AddBreakParams(Params):
    break_start: LocalTimestamp
    break_end: LocalTimestamp
    worked_hours_after_fix: float | None = None

    @model_validator(mode="after")
    def _order(self) -> AddBreakParams:
        if self.break_end <= self.break_start:
            raise ValueError("break_end must be after break_start")
        return self


class MoveShiftParams(Params):
    """Move an upcoming shift (P6). current_* guard against a schedule that changed."""

    date: LocalDate
    current_start: LocalTime
    current_end: LocalTime
    new_start: LocalTime
    new_end: LocalTime

    @model_validator(mode="after")
    def _non_zero(self) -> MoveShiftParams:
        if self.new_start == self.new_end:
            raise ValueError("new_start and new_end must differ")
        return self


class ShiftCut(Params):
    date: LocalDate
    scheduled_hours: float = Field(gt=0)
    new_hours: float = Field(ge=0)
    cut_hours: float | None = None  # recomputed from scheduled_hours - new_hours

    @model_validator(mode="after")
    def _within_shift(self) -> ShiftCut:
        if self.new_hours > self.scheduled_hours:
            raise ValueError("new_hours cannot be more than scheduled_hours")
        self.cut_hours = round(self.scheduled_hours - self.new_hours, 2)
        return self


class ReduceScheduleParams(Params):
    total_cut_hours: float | None = None  # recomputed from the cuts
    cuts: list[ShiftCut] = Field(min_length=1)

    @model_validator(mode="after")
    def _total(self) -> ReduceScheduleParams:
        self.total_cut_hours = round(sum(c.cut_hours or 0 for c in self.cuts), 2)
        return self


class DateParams(Params):
    date: LocalDate


class LeaveDayParams(Params):
    date: LocalDate
    leave_type: LeaveType
    days: float = Field(gt=0, le=1)


class ConvertFullDayParams(Params):
    date: LocalDate
    leave_type: LeaveType


class SplitPaidUnpaidParams(Params):
    leave_type: LeaveType
    paid: list[DayAmount] = Field(default_factory=list)
    unpaid: list[DayAmount] = Field(min_length=1)


class MoveLeaveTypeParams(Params):
    from_type: LeaveType
    to_type: LeaveType
    days: list[DayAmount] = Field(min_length=1)

    @model_validator(mode="after")
    def _different(self) -> MoveLeaveTypeParams:
        if self.from_type == self.to_type:
            raise ValueError("from_type and to_type must differ")
        return self


class RejectLeaveDaysParams(Params):
    leave_type: LeaveType
    days: list[DayAmount] | None = None
    dates: list[LocalDate] | None = None
    as_: Literal["unpaid"] | None = Field(default=None, alias="as")

    @model_validator(mode="after")
    def _one_shape(self) -> RejectLeaveDaysParams:
        if not self.days and not self.dates:
            raise ValueError("give the leave days to reject in 'days' or 'dates'")
        return self

    def all_dates(self) -> list[date]:
        return [d.date for d in self.days] if self.days else list(self.dates or [])


# Action -> params model. An action missing here is decision-only.
DATA_ACTIONS: dict[str, type[Params]] = {
    "set_clock_in": SetClockParams,
    "set_clock_out": SetClockParams,
    "add_punches": AddPunchesParams,
    "void_punches": PunchIdsParams,
    "edit_punches": EditPunchesParams,
    "reject_unscheduled_work": RejectUnscheduledParams,
    "reduce_scheduled_hours": ReduceScheduleParams,
    "give_rest_day": DateParams,
    "record_leave": LeaveDayParams,
    "cancel_leave": LeaveDayParams,
    "convert_to_full_day_leave": ConvertFullDayParams,
    "split_paid_unpaid_leave": SplitPaidUnpaidParams,
    "move_leave_type": MoveLeaveTypeParams,
    "reject_leave_days": RejectLeaveDaysParams,
    "correct_clock_out": CorrectPunchParams,
    "add_break": AddBreakParams,
    "move_shift": MoveShiftParams,
}

DECISION_ACTIONS = frozenset(
    {
        "approve_overtime",
        "approve_unscheduled_work",
        "mark_unpaid_absence",
        "holiday_pay",
        "comp_off",
        "approve_exception",
        "request_certificate",
        "approve_without_certificate",
        "mark_unpaid_hours",
        "confirm_punches_valid",
        "record_missed_break",
        "record_short_rest",
        "accept_reason",
        "record_lateness",
    }
)

# Decision-only actions that must carry a note: the param that holds it. An empty note is
# filled from the approve reason; if both are empty, approve is refused.
REQUIRED_NOTE = {
    "record_missed_break": "follow_up",
    "record_short_rest": "reason",
    "accept_reason": "reason",
}


class FixParamsError(ValueError):
    def __init__(self, message: str, errors: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.errors = errors or []


def _json_kind(v: Any) -> str:
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int | float):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "list"
    if isinstance(v, dict):
        return "object"
    return "null"


def validate_decision_params(original: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    added = sorted(set(params) - set(original))
    if added:
        raise FixParamsError(f"unknown param(s) {added}; allowed: {sorted(original)}")
    for key, value in params.items():
        want, got = _json_kind(original[key]), _json_kind(value)
        if want != got:
            raise FixParamsError(f"param {key!r} must be a {want}, got a {got}")
        if got == "number" and value < 0:
            raise FixParamsError(f"param {key!r} cannot be negative")
    return params


MIN_NOTE_LENGTH = 3


def validate_required_note(action: str, params: dict[str, Any]) -> None:
    key = REQUIRED_NOTE.get(action)
    if key is not None and len(str(params.get(key) or "").strip()) < MIN_NOTE_LENGTH:
        raise FixParamsError(
            f"{action} needs a {key.replace('_', '-')} note of at least {MIN_NOTE_LENGTH} "
            "characters: send it as the approve reason",
            [{"loc": key, "msg": f"must be at least {MIN_NOTE_LENGTH} characters"}],
        )


def parse_params(action: str, original: dict[str, Any], params: dict[str, Any]) -> Params | dict:
    """Validate merged params for `action`. Returns a model (data actions) or the dict."""
    model = DATA_ACTIONS.get(action)
    if model is None:
        if action not in DECISION_ACTIONS:
            raise FixParamsError(f"no applier for fix action {action!r}")
        checked = validate_decision_params(original, params)
        validate_required_note(action, checked)
        return checked
    try:
        return model.model_validate(params)
    except ValidationError as exc:
        errors = [
            {"loc": ".".join(str(p) for p in e["loc"]), "msg": e["msg"]} for e in exc.errors()
        ]
        raise FixParamsError(f"invalid params for {action}", errors) from exc


def params_json(parsed: Params | dict) -> dict[str, Any]:
    if isinstance(parsed, Params):
        return parsed.model_dump(mode="json", by_alias=True, exclude_none=True)
    return parsed
