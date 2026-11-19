"""Request and response models of the API (these drive the OpenAPI docs at /docs)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from attendflow.cases.transitions import Status

ActorType = Literal["system", "agent", "worker", "supervisor", "admin"]
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
    auto_resolved: int
    closed_no_longer_detected: list[str]
    by_policy: dict[str, int]
    exception_ids: list[str]


# ---------------------------------------------------------------- exceptions


class FixOptionOut(ApiModel):
    option_id: str
    action: str
    label: str
    params: dict[str, Any]


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
    applied_fix: dict[str, Any] | None
    assigned_to: str | None = Field(description="Whose turn it is to act")
    waiting_since: datetime | None
    last_detected_at: datetime
    created_at: datetime
    updated_at: datetime


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


class AuditListOut(ApiModel):
    count: int
    items: list[AuditEntryOut]


class ToolCallOut(ApiModel):
    id: int
    exception_id: str
    step_no: int
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
    reason: str = Field(min_length=3, max_length=1000, examples=["The worker was on site"])


class AskWorkerIn(RequestModel):
    note: str | None = Field(default=None, max_length=1000)


class WorkerReplyIn(RequestModel):
    confirmed: bool = Field(description="Yes/No: did it happen as described?")
    text: str | None = Field(default=None, max_length=2000, examples=["left around 7:30ish"])
