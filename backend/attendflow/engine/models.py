"""Output models of the rule engine: shifts, exceptions and fix options.

All of these are built by plain code. Later phases hand them to the LLM to explain, but
the LLM never creates or changes them.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from attendflow.data.schemas import Punch, ScheduleRow

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
    "set_clock_in",
    "set_clock_out",
    "approve_overtime",
    "reduce_scheduled_hours",
]


class FixOption(EngineModel):
    """A fix the code can apply after a human approves it. Never applied by the LLM."""

    option_id: str
    action: FixAction
    label: str
    params: dict[str, Any] = Field(default_factory=dict)


class TimecardException(EngineModel):
    exception_id: str
    policy_id: str
    title: str
    employee_id: str
    date: date  # shift date; for P5 the Monday that starts the week
    severity: Literal["low", "medium", "high"]
    kind: Literal["breach", "risk"] = "breach"  # risk = forecast, has not happened yet
    status: Literal["open", "auto_resolved"] = "open"
    summary: str  # one line with the numbers, built by code
    details: dict[str, Any]  # the actual numbers and the limit used
    evidence: list[Punch] = Field(default_factory=list)
    fix_options: list[FixOption] = Field(default_factory=list)


class EngineResult(EngineModel):
    as_of: datetime
    policy_version: str
    shifts: list[Shift]
    exceptions: list[TimecardException]
    voided_punch_ids: list[str]  # P2 duplicates removed before grouping
    ignored_future_punches: int  # punches after as_of, ignored on purpose
