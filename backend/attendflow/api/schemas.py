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
    auto_resolve_held: int = Field(
        default=0,
        description="New P2/P7 cases left open for a person (unclear, or the kill switch is off)",
    )
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
    auto_resolve_undone_at: datetime | None = Field(
        default=None, description="Set when a person undid the auto-resolve (Phase 12)"
    )
    auto_resolve_undone_by: str | None = None
    no_reply_stage: int = Field(
        default=0,
        description="No-reply ladder (Phase 13): 0 none, 1 reminder sent, 2 supervisor "
        "brought in, 3 sent to payroll",
    )
    no_reply_wait_since: datetime | None = None
    no_reply_reminded_at: datetime | None = None
    no_reply_supervisor_at: datetime | None = None
    no_reply_admin_at: datetime | None = None
    no_reply_late_reply_at: datetime | None = None
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
    without_worker: bool = Field(
        default=False,
        description="Decide on the evidence without the worker's reply (Phase 13). Only "
        "after the no-reply ladder brought the case to you (stage 2 or 3); needs a reason of "
        "at least 10 characters",
    )
    confirm_time_without_worker: bool = Field(
        default=False,
        description="Required with without_worker for an option that sets a punch time: "
        "\"I'm confirming this time without the worker's reply\"",
    )


class EditIn(RequestModel):
    option_id: str = Field(min_length=1, examples=["set_clock_out_to_scheduled_end"])
    params: dict[str, Any] = Field(
        min_length=1,
        description="Only the params to change; they are merged onto the option's params",
        examples=[{"timestamp": "2026-04-14T17:30"}],
    )
    reason: str = Field(min_length=3, max_length=1000, examples=["Amit left at 17:30"])
    without_worker: bool = Field(
        default=False,
        description="Decide on the evidence without the worker's reply (Phase 13). Only "
        "after the no-reply ladder brought the case to you (stage 2 or 3); needs a reason of "
        "at least 10 characters",
    )
    confirm_time_without_worker: bool = Field(
        default=False,
        description="Required with without_worker for an option that sets a punch time: "
        "\"I'm confirming this time without the worker's reply\"",
    )


class RejectIn(RequestModel):
    reason: str = Field(
        min_length=10,
        max_length=1000,
        description="Why the fix is rejected (at least 10 characters, saved in the audit log)",
        examples=["The worker was on site all day"],
    )


class EscalateIn(RequestModel):
    reason: str = Field(
        min_length=10,
        max_length=1000,
        description="Why the case goes to payroll (at least 10 characters, saved in the audit)",
        examples=["The worker is on leave and I cannot verify the time"],
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


class WorkerReminderOut(ApiModel):
    text: str = Field(description="Deterministic template, never the LLM")
    sent_at: datetime


class WorkerMessageOut(ApiModel):
    exception_id: str
    date: date
    message: str
    reply_prompt: str
    needs_actual_time: bool
    time_review: WorkerTimeReviewOut | None = None
    reminder: WorkerReminderOut | None = None
    status_note: str | None = Field(
        default=None, description="Set when the supervisor now reviews it (still answerable)"
    )


class WorkerNoticeOut(ApiModel):
    exception_id: str
    date: date
    kind: Literal["decided_without_reply", "with_payroll"]
    title: str
    text: str
    reason: str | None = None
    at: datetime | None = None


class WorkerReplyOut(ApiModel):
    exception_id: str
    confirmed: bool
    needs_actual_time: bool
    time_review: WorkerTimeReviewOut | None = None


class WorkerInboxOut(ApiModel):
    items: list[WorkerMessageOut]
    notices: list[WorkerNoticeOut] = Field(
        default_factory=list, description="Plain notes about cases the worker can no longer answer"
    )


class WorkerAnswerOut(ApiModel):
    confirmed: bool | None = Field(description="Yes (true), No (false), or no choice yet")
    text: str | None = Field(default=None, description="The worker's own words, if any")
    time: str | None = Field(default=None, description="The time the worker confirmed (HH:MM)")
    replied_at: datetime | None = None


class WorkerHistoryQuestionOut(ApiModel):
    asked_at: datetime
    message: str
    reminded_at: datetime | None = None
    answer: WorkerAnswerOut | None = None


class WorkerOutcomeOut(ApiModel):
    state: Literal[
        "waiting_for_you",
        "with_supervisor",
        "with_payroll",
        "decided_without_reply",
        "decided",
        "fixed",
        "closed_no_change",
    ]
    text: str = Field(description="Built by code, in plain words")
    reason: str | None = Field(
        default=None, description="Only for a decision taken without the worker's reply"
    )


class WorkerHistoryItemOut(ApiModel):
    exception_id: str
    date: date
    questions: list[WorkerHistoryQuestionOut]
    outcome: WorkerOutcomeOut
    updated_at: datetime


class WorkerHistoryOut(ApiModel):
    items: list[WorkerHistoryItemOut]


# ---------------------------------------------------------------- briefing (Phase 17)


class BriefingBulletOut(ApiModel):
    text: str
    case_ids: list[str]


class BriefingSectionOut(ApiModel):
    key: Literal["needs_decision", "handled_on_its_own", "blocking_payroll", "watch"]
    title: str
    bullets: list[BriefingBulletOut]


class BriefingTeamLineOut(ApiModel):
    team: str
    text: str


class BriefingRefreshStateOut(ApiModel):
    allowed: bool
    reason: Literal["too_soon", "daily_cap"] | None = None
    retry_after_seconds: int | None = None
    calls_left_today: int
    llm_configured: bool = Field(description="An LLM key is set and BRIEFING_ENABLED is on")


class BriefingOut(ApiModel):
    scope: Literal["all", "team"]
    team: str | None = None
    source: Literal["llm", "template"]
    reason: str = Field(
        description="validated, validated_after_retry, validation_failed, llm_error, timeout, "
        "llm_unavailable, llm_disabled, no_budget, facts_changed or not_generated"
    )
    label: str
    stale: bool = Field(description="The facts changed since the stored briefing (or none yet)")
    stored: bool
    briefing_id: int | None = None
    headline: str
    sections: list[BriefingSectionOut]
    team_lines: list[BriefingTeamLineOut]
    generated_at: datetime = Field(description="Workflow time (demo clock)")
    facts_hash: str
    llm_calls: int
    latency_ms: float | None = None
    failed_checks: list[str] = Field(description="Codes of checks the LLM drafts failed")
    refresh: BriefingRefreshStateOut


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


NoReplyKey = Literal["reminded", "supervisor", "payroll_admin"]
NoReplyFilter = Literal["any", "reminded", "supervisor", "payroll_admin", "waiting"]


class NoReplyOut(ApiModel):
    """The no-reply ladder on one case (Phase 13). Built by code from stored times."""

    stage: int = Field(description="0 none (replied late), 1 reminder, 2 supervisor, 3 payroll")
    stage_key: NoReplyKey | None
    label: str
    note: str = Field(examples=["Neha Joshi has not replied for 26 h."])
    hours_without_reply: str | None
    wait_since: datetime | None
    reminded_at: datetime | None
    supervisor_at: datetime | None
    admin_at: datetime | None
    late_reply_at: datetime | None
    can_decide_without_worker: bool


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
    auto_resolve_undone: bool = Field(
        default=False, description="A person undid its auto-resolve; decide it by hand"
    )
    no_reply: NoReplyOut | None = Field(
        default=None, description="Set when the worker did not reply in time (Phase 13)"
    )


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


class TraceStepOut(ApiModel):
    step_no: int
    tool_name: str
    ok: bool | None
    result_summary: str


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
    no_reply: NoReplyOut | None = None
    can_decide: bool = Field(
        description="True only for the assignee. The team's supervisor may open the card "
        "read-only (Phase 14); every decision endpoint still requires the assignee."
    )
    trace: list[TraceStepOut] = Field(
        description="The latest investigation's tool calls: name, ok and a result line built "
        "by code (no arguments, raw outputs or prompts)"
    )


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
    stuck: int = Field(
        default=0,
        description="Not final and the no-reply ladder took at least one step (Phase 13)",
    )


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
    auto_resolve_undone: bool = Field(
        default=False, description="A person undid this case's auto-resolve (Phase 12)"
    )
    assigned_to: str | None
    assigned_to_name: str | None
    investigated: bool = Field(description="A stored investigation case exists")
    who_to_ask: Literal["worker", "supervisor", "hr"] | None
    investigation_fallback: bool | None = Field(
        description="True when the stored investigation is the engine template"
    )
    needs_your_decision: bool = Field(description="Escalated and assigned to the caller")
    updated_at: datetime
    no_reply: NoReplyOut | None = None


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
    no_reply: list[NoReplyFilter] = Field(
        default_factory=lambda: ["any", "reminded", "supervisor", "payroll_admin", "waiting"]
    )


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
    result_summary: str = Field(
        description="One line built by code from the tool output (Phase 14); never the raw output"
    )


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
    reminded_at: datetime | None = None
    reminder_text: str | None = None


class AdminJobOut(ApiModel):
    id: str
    status: Literal["running", "completed", "failed"]
    reason: str | None


class AutoFixRefusalOut(ApiModel):
    at: datetime
    by: str | None
    message: str | None


class AutoFixOut(ApiModel):
    """An auto-resolve as people see it. Every text is stored data or built by code."""

    state: Literal["auto_resolved", "undone", "held"] = Field(
        description="held = a candidate left open for a person (unclear, or switched off)"
    )
    basis: str | None = Field(description="Why code was allowed to close it (engine numbers)")
    held_because: list[str]
    policy_quote: str = Field(description='policy.md "Allowed fixes" for this policy, verbatim')
    changes: list[str] = Field(description="What the auto-resolve changed, one line per row")
    data_changed: bool
    resolved_by: Literal["system"] | None
    resolved_at: datetime | None
    undone_by: str | None
    undone_by_name: str | None
    undone_at: datetime | None
    undo_reason: str | None
    can_undo: bool = Field(description="The caller may undo it now")
    undo_unavailable_reason: str | None
    last_refusal: AutoFixRefusalOut | None


class AdminCaseOut(ApiModel):
    exception_id: str
    status: Status
    assigned_to: str | None
    assigned_to_name: str | None
    needs_your_decision: bool
    can_investigate: bool = Field(description="True while the case is open")
    auto_resolved: bool
    auto_fix: AutoFixOut | None = Field(
        default=None, description="P2/P7 only: the auto-resolve, why, and whether you may undo"
    )
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
    no_reply: NoReplyOut | None = None


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
    step: Literal["detection", "investigate", "ask_worker", "no_reply", "briefing"]
    error: str


class CycleNoReplyOut(ApiModel):
    enabled: bool = True
    reminded: list[str] = Field(default_factory=list)
    to_supervisor: list[str] = Field(default_factory=list)
    to_admin: list[str] = Field(default_factory=list)


class CycleBriefingOut(ApiModel):
    status: Literal["generated", "fallback", "skipped"]
    reason: str
    briefing_id: int | None = None
    llm_calls: int = 0


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
    skipped_undone: int = Field(
        default=0,
        description="Cases whose auto-resolve a person undid: never handled automatically",
    )
    no_reply: CycleNoReplyOut = Field(
        default_factory=CycleNoReplyOut, description="No-reply ladder steps (Phase 13)"
    )
    briefing: CycleBriefingOut | None = Field(
        default=None, description="Priya's scheduled daily briefing (Phase 17)"
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


class DemoClockOut(ApiModel):
    now: datetime = Field(description="The clock's 'now': stamps rows and drives timeouts")
    data_as_of: datetime = Field(
        description="The data cut-off (ATTENDFLOW_AS_OF); moving the demo clock never moves it"
    )
    offset_hours: float
    max_offset_hours: float
    movable: bool = Field(description="True only in demo mode")
    hint: str | None = None


class DemoClockIn(RequestModel):
    hours: float = Field(gt=0, le=336, description="Move the demo clock forward this much")


class NoReplySettingsOut(ApiModel):
    enabled: bool
    reminder_hours: float
    supervisor_hours: float
    admin_hours: float


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
    as_of: datetime = Field(description="The demo clock's 'now'")
    clock: DemoClockOut
    no_reply: NoReplySettingsOut
    demo_mode: bool
    workers: list[DemoWorkerOut] = Field(
        description="Workers a simulated punch can be sent for (demo mode only, else empty)"
    )


class DemoResetOut(ApiModel):
    seed: SeedOut
    detection: DetectionRunOut
    watermark_audit_id: int
    clock: DemoClockOut


# ---------------------------------------------------------------- auto-resolve (Phase 12)


class UndoIn(RequestModel):
    reason: str = Field(
        min_length=10,
        max_length=1000,
        description="Why the auto-resolve is undone (at least 10 characters, saved in the audit)",
        examples=["The worker says the second tap was a real re-entry"],
    )


class UndoOut(ExceptionDetailOut):
    restored: list[dict[str, Any]] = Field(description="Rows put back to their 'before' values")
    detection: PostFixDetectionOut


class TeamAutoFixItemOut(ApiModel):
    exception_id: str
    employee_id: str
    employee_name: str
    date: date
    policy_id: str
    title: str
    summary: str
    status: Status
    auto_fix: AutoFixOut | None


class TeamAutoFixesOut(ApiModel):
    count: int
    items: list[TeamAutoFixItemOut]


class MetricPolicyOut(ApiModel):
    policy_id: str
    needed_handling: int
    auto_resolved: int
    undone: int
    closed_by_data_change: int


class AutoResolveMetricOut(ApiModel):
    resolved_without_human: int = Field(description="X: closed by auto-resolve and not undone")
    needed_handling: int = Field(
        description="Y: exceptions that needed handling (all, minus closed_by_data_change)"
    )
    percent: float = Field(description="100 * X / Y, one decimal (0 when Y is 0)")
    undone: int = Field(description="Auto-resolves a person undid (counted as human work)")
    closed_by_data_change: int = Field(
        description="Closed as no_longer_detected: the data changed and nobody had to act. "
        "Not part of Y."
    )
    date_from: date | None
    date_to: date | None
    auto_resolve_enabled: bool = Field(description="The AUTO_RESOLVE_ENABLED kill switch")
    allowed_policies: list[str] = Field(description="Policies policy.json lets auto-resolve")
    by_policy: list[MetricPolicyOut]


class DashboardAgingOut(ApiModel):
    limits_hours: list[int]
    case_age: list[int]
    waiting_age: list[int]


class DashboardWorkloadOut(ApiModel):
    supervisor_id: str | None
    supervisor_name: str
    active: int
    awaiting_worker: int
    awaiting_supervisor: int


class DashboardOvertimeWorkerOut(ApiModel):
    employee_id: str
    employee_name: str
    worked_hours: float
    scheduled_remaining_hours: float
    projected_hours: float
    level: Literal["approaching", "at_limit", "projected_over", "already_over"]


class DashboardOvertimeOut(ApiModel):
    week_start: date
    week_end: date
    limit_hours: float
    warning_margin_hours: float
    workers: list[DashboardOvertimeWorkerOut]


class DashboardOut(ApiModel):
    scope: Literal["all", "team"]
    workflow_now: datetime
    active_total: int
    stuck: int
    by_status: dict[str, int]
    by_severity: dict[str, int]
    by_policy: dict[str, int]
    ladder: dict[str, int]
    aging: DashboardAgingOut
    workload: list[DashboardWorkloadOut]
    overtime: DashboardOvertimeOut
    auto_resolve: AutoResolveMetricOut


# ---------------------------------------------------------------- Phase 14: activity

FeedMode = Literal["all", "autonomous", "human"]


class ActivityCaseOut(ApiModel):
    exception_id: str
    policy_id: str
    date: date
    title: str
    status: Status


class ActivityEmployeeOut(ApiModel):
    employee_id: str
    name: str
    team: str | None


class ActivityItemOut(ApiModel):
    id: int
    at: datetime = Field(description="Workflow time (the demo clock), not server time")
    actor_type: ActorType
    actor_label: str
    actor_name: str = Field(description="The person, or which part of the system acted")
    autonomous: bool = Field(description="Done by the system, the LLM agent or a device")
    action: str
    capability: str | None = Field(description="The Autonomy Table row this belongs to")
    sentence: str = Field(description="Plain sentence from a fixed template; never LLM text")
    reason: str | None = Field(description="A person's own typed reason; null otherwise")
    case: ActivityCaseOut | None
    employee: ActivityEmployeeOut | None


class ActivityViewerOut(ApiModel):
    employee_id: str
    role: str


class ActivityFeedOut(ApiModel):
    viewer: ActivityViewerOut
    items: list[ActivityItemOut]
    next_before_id: int | None = Field(
        description="Pass as before_id for the next (older) page; null on the last page"
    )


class ActivityCountsOut(ApiModel):
    investigated: int = Field(description="Cases with a stored investigation")
    messages_sent: int
    reminders_sent: int
    auto_resolved: int
    auto_resolves_undone: int
    escalated_by_silence: int = Field(description="Cases the no-reply ladder handed on")
    human_approvals: int
    decided_without_worker: int
    human_rejections: int
    device_punches: int


class ActivitySummaryOut(ApiModel):
    date_from: date | None
    date_to: date | None
    counts: ActivityCountsOut
    definitions: dict[str, list[str]] = Field(description="The audit actions each count uses")


class AutonomyRowOut(ApiModel):
    key: str
    title: str
    kind: Literal["allowed", "never"]
    actor_type: Literal["code", "llm_agent", "system", "device", "human"]
    actor_label: str
    performed_by: str
    approval: Literal["none", "supervisor", "payroll_admin", "supervisor_or_payroll_admin"]
    approval_label: str
    reversible: Literal["yes_undo", "no", "not_applicable"]
    reversible_label: str
    guardrail: str
    autonomous: bool
    audit_actions: list[str]
    proof_tests: list[str]


class AutonomyTableOut(ApiModel):
    items: list[AutonomyRowOut]


# ---------------------------------------------------------------- payroll readiness

ReadinessStatus = Literal["ready", "ready_with_notes", "blocked"]


class ReadinessReasonOut(ApiModel):
    employee_id: str
    code: str
    message: str
    blocking: bool
    exception_ids: list[str]
    owner_id: str | None
    owner_name: str | None
    contact: Literal["worker", "supervisor", "hr"] | None


class ReadinessGroupOut(ApiModel):
    team: str
    status: ReadinessStatus
    reasons: list[ReadinessReasonOut]


class ReadinessWorkerOut(ReadinessGroupOut):
    employee_id: str
    employee_name: str
    worked_hours: float
    scheduled_remaining_hours: float
    projected_hours: float


class PayrollSignoffOut(ApiModel):
    signer_name: str
    signed_at: datetime
    note: str | None
    reopened_at: datetime | None
    stale: bool


class PayrollReadinessOut(ApiModel):
    week_start: date
    week_end: date
    evaluated_through: date
    data_cutoff: datetime
    closed: bool
    has_data: bool
    status: ReadinessStatus
    scope: Literal["all", "team"]
    can_sign: bool
    can_reopen: bool
    signoff: PayrollSignoffOut | None
    exception_counts: AdminCountersOut
    overtime_limit_hours: float
    reasons: list[ReadinessReasonOut]
    teams: list[ReadinessGroupOut]
    workers: list[ReadinessWorkerOut]


class PayrollSignoffIn(RequestModel):
    note: str | None = Field(default=None, max_length=500)


class PayrollReopenIn(RequestModel):
    reason: str = Field(min_length=10, max_length=500)
