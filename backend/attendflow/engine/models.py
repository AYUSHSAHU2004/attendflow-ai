"""Output models of the rule engine: shifts, exceptions and fix options.

All of these are built by plain code. Later phases hand them to the LLM to explain, but
the LLM never creates or changes them.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from attendflow.data.schemas import Holiday, LeaveBalance, LeaveRecord, Punch, ScheduleRow

# A source row an exception is based on. Punches come first; leave, balance, schedule and
# holiday rows are evidence for checks that are not about punches (P10, P11, P12, ...).
EvidenceRow = Punch | LeaveRecord | LeaveBalance | ScheduleRow | Holiday

ShiftStatus = Literal["complete", "in_progress", "missing_in", "missing_out"]


class EngineModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BreakPeriod(EngineModel):
    start: datetime
    end: datetime

    @property
    def minutes(self) -> float:
        return (self.end - self.start).total_seconds() / 60


class Shift(EngineModel):
    """One worked (or still running) shift, attributed to the date it started (P15)."""

    employee_id: str
    date: date
    schedule: ScheduleRow | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    punches: list[Punch]
    clock_in: Punch | None = None
    clock_out: Punch | None = None
    breaks: list[BreakPeriod] = Field(default_factory=list)
    status: ShiftStatus
    notes: list[str] = Field(default_factory=list)

    @property
    def is_scheduled(self) -> bool:
        return self.schedule is not None

    @property
    def break_minutes(self) -> float:
        return sum(b.minutes for b in self.breaks)

    @property
    def worked_hours(self) -> float | None:
        """Clock-in to clock-out minus breaks. None while either punch is missing."""
        if self.clock_in is None or self.clock_out is None:
            return None
        span = (self.clock_out.timestamp - self.clock_in.timestamp).total_seconds() / 60
        return (span - self.break_minutes) / 60


FixAction = Literal[
    # Phase 1
    "set_clock_in",
    "set_clock_out",
    "approve_overtime",
    "reduce_scheduled_hours",
    # Phase 2: schedule and holidays
    "approve_unscheduled_work",
    "reject_unscheduled_work",
    "add_punches",
    "mark_unpaid_absence",
    "record_leave",
    "holiday_pay",
    "comp_off",
    "give_rest_day",
    "approve_exception",
    # Phase 2: leave
    "cancel_leave",
    "void_punches",
    "edit_punches",
    "split_paid_unpaid_leave",
    "move_leave_type",
    "reject_leave_days",
    "request_certificate",
    "approve_without_certificate",
    "convert_to_full_day_leave",
    "mark_unpaid_hours",
    # Phase 2: punch review (P17)
    "confirm_punches_valid",
    # Phase 4: P3, P4, P6, P7
    "correct_clock_out",
    "add_break",
    "record_missed_break",
    "move_shift",
    "record_short_rest",
    "accept_reason",
    "record_lateness",
    # Phase 12: a person decides a P7 within-grace case (undone, or auto-resolve held)
    "confirm_within_grace",
]

# What each action does, in plain words. Used as the option description unless a check
# gives a more specific one. decision_only = the action changes no timecard, schedule or
# leave data (fixes/params.py DATA_ACTIONS must agree; a test checks it).
ACTION_INFO: dict[str, tuple[bool, str]] = {
    "set_clock_in": (False, "Adds a correction clock-in punch at the given time."),
    "set_clock_out": (False, "Adds a correction clock-out punch at the given time."),
    "approve_overtime": (True, "Records that the extra hours were authorised overtime."),
    "reduce_scheduled_hours": (
        False,
        "Shortens (or removes) the listed upcoming shifts. Worked hours are not touched.",
    ),
    "approve_unscheduled_work": (True, "Records that the unscheduled work is approved and paid."),
    "reject_unscheduled_work": (
        False,
        "Voids the unscheduled punches, so the hours are not paid. The punches are kept "
        "in the database as voided.",
    ),
    "add_punches": (False, "Adds a correction clock-in and clock-out for the shift."),
    "mark_unpaid_absence": (True, "Records the scheduled day as an unpaid absence."),
    "record_leave": (False, "Records a day of leave and takes it from the leave balance."),
    "holiday_pay": (True, "Records that the holiday work is paid as holiday pay."),
    "comp_off": (True, "Records a compensatory day off for the holiday work."),
    "give_rest_day": (False, "Removes the upcoming shift so the worker gets a rest day."),
    "approve_exception": (True, "Records an approved exception to the rule."),
    "cancel_leave": (False, "Cancels the leave and gives the days back to the balance."),
    "void_punches": (False, "Voids the listed punches. They stay in the database as voided."),
    "edit_punches": (
        False,
        "Replaces the listed punches with the times the worker confirms (old punches are "
        "voided, new ones added as corrections).",
    ),
    "split_paid_unpaid_leave": (
        False,
        "Keeps the leave days the balance covers as paid and marks the rest as unpaid.",
    ),
    "move_leave_type": (False, "Moves the extra leave days to another leave type with room."),
    "reject_leave_days": (False, "Rejects the listed leave days."),
    "request_certificate": (True, "Asks the worker to upload a medical certificate."),
    "approve_without_certificate": (True, "Approves the sick days without a certificate."),
    "convert_to_full_day_leave": (False, "Changes the half-day leave to a full day of leave."),
    "mark_unpaid_hours": (True, "Keeps the leave and records the missing hours as unpaid."),
    "confirm_punches_valid": (True, "Confirms the punches are valid. Nothing changes."),
    "correct_clock_out": (
        False,
        "Replaces a wrong clock-out with the time the worker confirms (the old punch is "
        "voided, a correction punch is added).",
    ),
    "add_break": (False, "Adds the break the worker confirms as two correction punches."),
    "record_missed_break": (
        True,
        "Records that no break was taken, with the follow-up. The breach stays visible.",
    ),
    "move_shift": (False, "Moves the upcoming shift later so the worker gets the full rest."),
    "record_short_rest": (True, "Records why the rest between shifts was short."),
    "accept_reason": (True, "Accepts the worker's reason for the late arrival or early leave."),
    "record_lateness": (True, "Records the late arrival or early leave as it happened."),
    "confirm_within_grace": (
        True,
        "Confirms the clock-in was within the grace period, so it is not late. Nothing changes.",
    ),
}


class FixOption(EngineModel):
    """A fix the code can apply after a human approves it. Never applied by the LLM.

    `decision_only` and the default `description` come from ACTION_INFO, never from the
    check, so they cannot disagree with what the applier really does. `policy_id` is set
    by make_exception() to the exception's policy.
    """

    option_id: str
    action: FixAction
    label: str
    description: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    decision_only: bool = False
    policy_id: str | None = None
    # Policy says the worker must confirm first (approve is refused until they have).
    requires_worker_confirmation: bool = False

    @model_validator(mode="before")
    @classmethod
    def _from_action(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("action") in ACTION_INFO:
            decision_only, description = ACTION_INFO[data["action"]]
            given = data.get("decision_only")
            if given is not None and given != decision_only:
                raise ValueError(
                    f"decision_only for {data['action']!r} is {decision_only}, not {given}"
                )
            data = {**data, "decision_only": decision_only}
            if not data.get("description"):
                data["description"] = description
        return data


class TimecardException(EngineModel):
    exception_id: str
    policy_id: str
    title: str
    employee_id: str
    date: date  # shift date; P5: the Monday of the week; P11/P12: first leave day
    severity: Literal["low", "medium", "high"]
    kind: Literal["breach", "risk"] = "breach"  # risk = forecast, has not happened yet
    status: Literal["open", "auto_resolved"] = "open"
    summary: str  # one line with the numbers, built by code
    details: dict[str, Any]  # the actual numbers and the limit used
    evidence: list[EvidenceRow] = Field(default_factory=list)
    fix_options: list[FixOption] = Field(default_factory=list)


class EngineResult(EngineModel):
    as_of: datetime
    policy_version: str
    shifts: list[Shift]
    exceptions: list[TimecardException]
    voided_punch_ids: list[str]  # P2 duplicates removed before grouping
    ignored_future_punches: int  # punches after as_of, ignored on purpose
