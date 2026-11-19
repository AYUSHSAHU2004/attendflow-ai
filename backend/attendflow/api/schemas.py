"""Request and response models of the API (these drive the OpenAPI docs at /docs)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from attendflow.agent.case import InvestigationCase
from attendflow.cases.transitions import Status
from attendflow.engine.models import ACTION_INFO
from attendflow.tools.models import Finding, RunChecksOut

ActorType = Literal["system", "agent", "worker", "supervisor", "admin", "device"]
EMPLOYEE_ID = r"^E\d{3}$"
POLICY_ID = r"^P\d{1,2}$"


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------------------------------------------------------------- errors


class ErrorBody(ApiModel):
    code: str = Field(examples=["invalid_transition"])
    message: str = Field(examples=["reject: the exception is already resolved (final)"])
    details: Any = None


class ErrorResponse(ApiModel):
    error: ErrorBody


# ---------------------------------------------------------------- system


class HealthOut(ApiModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unreachable"]
    as_of: datetime = Field(description="The demo 'now' (ATTENDFLOW_AS_OF), never the server clock")
    policy_version: str
    version: str


class SeedOut(ApiModel):
    message: str
    counts: dict[str, int]


class DetectionRunOut(ApiModel):
    as_of: str
    policy_version: str
    found: int = Field(description="Exceptions the engine found in this run")
    created: int
    updated: int = Field(description="Open exceptions whose numbers changed")
    unchanged: int
    options_added: int = Field(
        description="Cases already in progress that got fix options their policy lacked before"
    )
    auto_resolved: int
    closed_no_longer_detected: list[str]
    by_policy: dict[str, int]
    exception_ids: list[str]
    created_ids: list[str] = Field(
        default_factory=list, description="Exceptions this run stored for the first time"
    )


# ---------------------------------------------------------------- exceptions


class FixOptionOut(ApiModel):
    option_id: str
    action: str
    label: str
    description: str = ""
    params: dict[str, Any]
    decision_only: bool = Field(description="True = changes no timecard, schedule or leave data")
    policy_id: str | None = None
    requires_worker_confirmation: bool = Field(
        default=False, description="Approve is refused until the worker has confirmed (Yes)"
    )

    @model_validator(mode="before")
    @classmethod
    def _fill_from_action(cls, data: Any) -> Any:
        # Options stored before Phase 4 lack description/decision_only: derive them.
        if isinstance(data, dict) and data.get("action") in ACTION_INFO:
            decision_only, description = ACTION_INFO[data["action"]]
            data = {**data, "decision_only": decision_only}
            data.setdefault("description", description)
        return data


class WorkerRecheckOut(ApiModel):
    timestamp: str
    source: Literal["yes", "llm", "manual"]
    proposed_fix: dict[str, Any]
    result: RunChecksOut
    impact_note: str
    approximate: bool = Field(
        default=False, description="The worker confirmed an approximate time (e.g. '7:30ish')"
    )


class ExceptionOut(ApiModel):
    id: str = Field(examples=["P1-E001-2026-04-14"])
    employee_id: str
    date: date
    policy_id: str
    title: str
    summary: str
    severity: Literal["low", "medium", "high"]
    kind: Literal["breach", "risk"]
    status: Status
    auto_resolved: bool
    details: dict[str, Any]
    evidence: list[dict[str, Any]]
    fix_options: list[FixOptionOut]
    proposed_fix: dict[str, Any] | None
    worker_recheck: WorkerRecheckOut | None = None
    applied_fix: dict[str, Any] | None
    assigned_to: str | None = Field(description="Whose turn it is to act")
    waiting_since: datetime | None
    last_detected_at: datetime
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _option_policy(self) -> ExceptionOut:
        for opt in self.fix_options:
            if opt.policy_id is None:
                opt.policy_id = self.policy_id
            if self.policy_id == "P1":
                opt.requires_worker_confirmation = True
        return self


class ExceptionListOut(ApiModel):
    count: int
    items: list[ExceptionOut]


class AuditEntryOut(ApiModel):
    id: int
    exception_id: str | None
    actor: ActorType
    actor_id: str | None
    action: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    reason: str | None
    created_at: datetime


class ExceptionDetailOut(ExceptionOut):
    audit_trail: list[AuditEntryOut]
    investigation_case: InvestigationCase | None = None


class InvestigationJobOut(ApiModel):
    id: str
    exception_id: str
    status: Literal["running", "completed", "failed"]
    started_at: datetime
    deadline_at: datetime
    finished_at: datetime | None
    duration_ms: float | None
    reason: str | None


class AuditListOut(ApiModel):
    count: int
    items: list[AuditEntryOut]


class ToolCallOut(ApiModel):
    id: int
    exception_id: str
    step_no: int
    run_id: str | None
    call_no: int | None
    ok: bool | None
    duration_ms: float | None
    tool_name: str
    input: dict[str, Any]
    output: dict[str, Any] | None
    created_at: datetime


class ToolCallListOut(ApiModel):
    count: int
    items: list[ToolCallOut]


# ---------------------------------------------------------------- requests


class ApproveIn(RequestModel):
    option_id: str = Field(min_length=1, examples=["set_clock_out_to_scheduled_end"])
    reason: str | None = Field(default=None, max_length=1000)


class EditIn(RequestModel):
    option_id: str = Field(min_length=1, examples=["set_clock_out_to_scheduled_end"])
    params: dict[str, Any] = Field(
        min_length=1,
        description="Only the params to change; they are merged onto the option's params",
        examples=[{"timestamp": "2026-04-14T17:30"}],
    )
    reason: str = Field(min_length=3, max_length=1000, examples=["Amit left at 17:30"])


class RejectIn(RequestModel):
    reason: str = Field(
        min_length=10,
        max_length=1000,
        description="Why the fix is rejected (at least 10 characters, saved in the audit log)",
        examples=["The worker was on site all day"],
    )


class AskWorkerIn(RequestModel):
    note: str | None = Field(default=None, max_length=1000)


class WorkerReplyIn(RequestModel):
    confirmed: bool = Field(description="Yes/No: did it happen as described?")
    text: str | None = Field(default=None, max_length=2000, examples=["left around 7:30ish"])

    @model_validator(mode="after")
    def _no_needs_text(self) -> WorkerReplyIn:
        if self.text and "\x00" in self.text:
            raise ValueError("reply text must not contain null characters")
        if not self.confirmed and not self.text:
            raise ValueError("tell us what happened when answering No")
        return self


class WorkerTimeReviewOut(ApiModel):
    stage: Literal["candidate", "manual", "confirmed"]
    timestamp: str | None = None
    impact_note: str | None = None
    approximate: bool = False


class WorkerTimeIn(RequestModel):
    time: str = Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    actual_date: date | None = None


class WorkerMessageOut(ApiModel):
    exception_id: str
    date: date
    message: str
    reply_prompt: str
    needs_actual_time: bool
    time_review: WorkerTimeReviewOut | None = None


class WorkerReplyOut(ApiModel):
    exception_id: str
    confirmed: bool
    needs_actual_time: bool
    time_review: WorkerTimeReviewOut | None = None


class WorkerInboxOut(ApiModel):
    items: list[WorkerMessageOut]


# ---------------------------------------------------------------- supervisor


class PostFixDetectionOut(ApiModel):
    ran: bool = Field(description="False for decision-only fixes, or if detection failed")
    new_exception_ids: list[str] = Field(
        description="New open exceptions for this worker that the approved fix created"
    )
    closed_exception_ids: list[str]
    error: str | None = None


class ApproveOut(ExceptionDetailOut):
    detection: PostFixDetectionOut


class SupervisorQueueItemOut(ApiModel):
    exception_id: str
    employee_id: str
    employee_name: str
    date: date
    policy_id: str
    title: str
    summary: str
    severity: Literal["low", "medium", "high"]
    kind: Literal["breach", "risk"]
    status: Status
    waiting_since: datetime | None


class SupervisorQueueOut(ApiModel):
    count: int
    items: list[SupervisorQueueItemOut]


class CardEmployeeOut(ApiModel):
    employee_id: str
    name: str
    team: str


class CardPolicyOut(ApiModel):
    policy_id: str
    title: str
    rule: str
    cited_text: str = Field(description="The investigation's verbatim quote, else the rule")


class CardInvestigationOut(ApiModel):
    what_happened: str | None
    confidence: Literal["low", "medium", "high"] | None
    fallback: bool
    who_to_ask: Literal["worker", "supervisor", "hr"] | None
    next_action: str | None
    evidence: list[dict[str, Any]]


class CardWorkerOut(ApiModel):
    replied: bool
    confirmed: bool | None
    reply_text: str | None = Field(description="The worker's own words, unchanged")
    replied_at: datetime | None
    needs_actual_time: bool


class CardConfirmedTimeOut(ApiModel):
    timestamp: str
    approximate: bool
    source: Literal["yes", "llm", "manual"] | None
    option_id: str | None


class CardFieldOut(ApiModel):
    name: str
    kind: Literal["datetime", "date", "time", "number", "text", "fixed"]
    value: Any
    editable: bool
    locked_reason: str | None = None


class CardPunchOut(ApiModel):
    punch_id: str
    type: str | None
    timestamp: str | None


class CardConsequenceOut(ApiModel):
    source: Literal["worker_recheck", "investigation", "decision_only", "unchecked"]
    note: str = Field(description="Built by code from the stored re-check; never LLM text")
    creates_violations: bool
    new_violations: list[Finding]
    resolved: list[Finding]
    day_worked_hours: float | None
    week_projected_hours: float | None
    weekly_limit_hours: float | None


class CardOptionOut(ApiModel):
    option_id: str
    action: str
    label: str
    description: str
    params: dict[str, Any]
    decision_only: bool
    requires_worker_confirmation: bool
    worker_confirmed: bool
    note_field: str | None = Field(description="Decision-only options: the required note param")
    fields: list[CardFieldOut]
    punches: list[CardPunchOut] | None = Field(
        description="edit_punches: the punches whose times may be changed"
    )
    consequence: CardConsequenceOut


class SupervisorCaseOut(ApiModel):
    exception_id: str
    status: Status
    assigned_to: str | None
    employee: CardEmployeeOut
    date: date
    policy_id: str
    title: str
    summary: str
    severity: Literal["low", "medium", "high"]
    kind: Literal["breach", "risk"]
    details: dict[str, Any]
    policy: CardPolicyOut
    evidence: list[dict[str, Any]]
    other_workers_evidence_hidden: int
    investigation: CardInvestigationOut | None
    worker: CardWorkerOut | None
    confirmed_time: CardConfirmedTimeOut | None
    recheck: RunChecksOut | None
    options: list[CardOptionOut]
    applied_fix: dict[str, Any] | None
    min_note_length: int


# ---------------------------------------------------------------- payroll admin

Severity = Literal["low", "medium", "high"]
AdminSort = Literal["severity", "date", "employee", "updated"]


class AdminCountersOut(ApiModel):
    total: int
    open: int
    awaiting_worker: int
    awaiting_supervisor: int
    escalated: int
    resolved: int
    rejected: int
    auto_resolved: int = Field(description="Resolved by policy without a human (P2, P7 grace)")


class AdminListItemOut(ApiModel):
    exception_id: str
    employee_id: str
    employee_name: str
    team: str
    date: date
    policy_id: str
    title: str
    summary: str
    severity: Severity
    kind: Literal["breach", "risk"]
    status: Status
    auto_resolved: bool
    assigned_to: str | None
    assigned_to_name: str | None
    investigated: bool = Field(description="A stored investigation case exists")
    who_to_ask: Literal["worker", "supervisor", "hr"] | None
    investigation_fallback: bool | None = Field(
        description="True when the stored investigation is the engine template"
    )
    needs_your_decision: bool = Field(description="Escalated and assigned to the caller")
    updated_at: datetime


class AdminEmployeeOptionOut(ApiModel):
    employee_id: str
    name: str
    team: str


class AdminFilterOptionsOut(ApiModel):
    statuses: list[Status]
    policy_ids: list[str]
    teams: list[str]
    employees: list[AdminEmployeeOptionOut]
    severities: list[Severity]


class AdminOverviewOut(ApiModel):
    counters: AdminCountersOut = Field(description="Whole database; filters never apply")
    matched: int = Field(description="Exceptions matching the filters (before paging)")
    limit: int
    offset: int
    items: list[AdminListItemOut]
    filter_options: AdminFilterOptionsOut


class AdminAuditEntryOut(ApiModel):
    id: int
    created_at: datetime
    actor: ActorType
    actor_id: str | None
    actor_name: str | None
    action: str
    summary: str = Field(description="Built by code from the stored audit row")
    reason: str | None
    before_summary: str | None = Field(description="Status and assignee before, if recorded")
    after_summary: str | None = Field(description="Status and assignee after, if recorded")


class AdminToolCallOut(ApiModel):
    run_id: str | None
    step_no: int
    call_no: int | None
    tool_name: str
    input: dict[str, Any] = Field(description="Tool arguments: IDs, dates and proposed changes")
    ok: bool | None
    error_code: str | None
    duration_ms: float | None


class AdminWorkerMessageOut(ApiModel):
    id: int
    sent_at: datetime
    source: Literal["llm", "template"]
    message: str
    reply_prompt: str
    confirmed: bool | None
    reply_text: str | None = Field(description="The worker's own words, unchanged")
    replied_at: datetime | None
    needs_actual_time: bool
    time_review: dict[str, Any] | None


class AdminJobOut(ApiModel):
    id: str
    status: Literal["running", "completed", "failed"]
    reason: str | None


class AdminCaseOut(ApiModel):
    exception_id: str
    status: Status
    assigned_to: str | None
    assigned_to_name: str | None
    needs_your_decision: bool
    can_investigate: bool = Field(description="True while the case is open")
    auto_resolved: bool
    employee: CardEmployeeOut
    date: date
    policy_id: str
    title: str
    summary: str
    severity: Severity
    kind: Literal["breach", "risk"]
    details: dict[str, Any]
    policy: CardPolicyOut
    evidence: list[dict[str, Any]]
    options: list[CardOptionOut]
    investigation: InvestigationCase | None
    latest_job: AdminJobOut | None
    worker_messages: list[AdminWorkerMessageOut]
    recheck: WorkerRecheckOut | None
    applied_fix: dict[str, Any] | None
    audit_trail: list[AdminAuditEntryOut] = Field(description="Oldest first")
    tool_calls: list[AdminToolCallOut]


# ---------------------------------------------------------------- device punches (Phase 11)

LOCAL_TIMESTAMP = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$"
PunchType = Literal["in", "out", "break_start", "break_end"]


class PunchIn(RequestModel):
    """One punch from an attendance device. Times are plain local wall-clock times."""

    employee_id: str = Field(pattern=EMPLOYEE_ID, examples=["E004"])
    timestamp: str = Field(
        pattern=LOCAL_TIMESTAMP,
        description="Local time, no timezone, e.g. 2026-04-15T09:02 (seconds optional)",
        examples=["2026-04-15T09:02"],
    )
    type: PunchType
    source: Literal["device"] = "device"
    device_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        pattern=r"^[A-Za-z0-9._-]+$",
        description="Defaults to the worker's usual device",
    )
    location: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="One of the known locations; defaults to the worker's usual one",
    )

    @model_validator(mode="after")
    def _real_time(self):
        try:
            datetime.fromisoformat(self.timestamp)
        except ValueError as exc:
            raise ValueError(f"timestamp is not a real date and time: {self.timestamp}") from exc
        return self

    def local_timestamp(self) -> datetime:
        return datetime.fromisoformat(self.timestamp)


class DemoPunchIn(PunchIn):
    """A simulated device punch from the /admin demo panel (DEMO_MODE only)."""


class PunchOut(ApiModel):
    punch_id: str
    employee_id: str
    timestamp: str
    type: PunchType
    source: Literal["device"]
    device_id: str
    location: str


class DetectionScopeOut(ApiModel):
    employee_id: str
    start: date
    end: date


class PunchDetectionOut(ApiModel):
    ran: bool
    scope: DetectionScopeOut
    new_exception_ids: list[str]
    closed_exception_ids: list[str]
    updated: int
    error: str | None = Field(description="Set when detection failed; the punch is kept")


class PunchAcceptedOut(ApiModel):
    punch: PunchOut
    detection: PunchDetectionOut


# ---------------------------------------------------------------- scheduler (Phase 11)


class CycleInvestigationOut(ApiModel):
    exception_id: str
    job_id: str
    job_status: Literal["running", "completed", "failed"]
    reason: str | None
    fallback: bool = Field(description="True when the engine template was stored")
    who_to_ask: str | None
    duration_ms: float | None


class CycleErrorOut(ApiModel):
    exception_id: str | None
    step: Literal["detection", "investigate", "ask_worker"]
    error: str


class SchedulerCycleOut(ApiModel):
    cycle_id: int
    trigger: Literal["schedule", "run_now"]
    status: Literal["completed", "failed"]
    as_of: str
    started_at: str = Field(description="Real UTC time (operational)")
    finished_at: str | None
    duration_ms: float | None
    backlog: bool = Field(description="Whether cases detected before the watermark were processed")
    watermark_audit_id: int
    detection: Literal["ok", "failed"] | None
    detected: int
    new: int
    new_exception_ids: list[str]
    closed_exception_ids: list[str]
    investigated: list[CycleInvestigationOut]
    messages_sent: list[str]
    skipped_budget: list[str] = Field(description="New cases left for the next cycle")
    skipped_message_budget: list[str]
    skipped_backlog: int = Field(
        description="Cases detected before the scheduler started that it left alone"
    )
    errors: list[CycleErrorOut]


class WatermarkOut(ApiModel):
    audit_id: int
    set_by: Literal["scheduler_start", "demo_reset", "first_cycle"]
    set_at: str


class DemoWorkerOut(ApiModel):
    employee_id: str
    name: str
    team: str


class SchedulerStatusOut(ApiModel):
    enabled_setting: bool = Field(description="SCHEDULER_ENABLED at startup")
    running: bool = Field(description="The timer thread is running now")
    cycle_in_progress: bool
    interval_seconds: float
    investigations_per_cycle: int
    messages_per_cycle: int
    backlog: bool
    next_run_at: datetime | None
    overlaps_skipped: int
    watermark: WatermarkOut | None
    last_cycle: SchedulerCycleOut | None
    as_of: datetime = Field(description="The demo clock's 'now'; punches after it are refused")
    demo_mode: bool
    workers: list[DemoWorkerOut] = Field(
        description="Workers a simulated punch can be sent for (demo mode only, else empty)"
    )


class DemoResetOut(ApiModel):
    seed: SeedOut
    detection: DetectionRunOut
    watermark_audit_id: int
