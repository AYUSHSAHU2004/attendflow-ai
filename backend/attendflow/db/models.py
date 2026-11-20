"""SQLAlchemy tables.

Two groups:
- Source data, one table per CSV (employees, timecards, schedule, leave_records,
  leave_balances, holidays). Only `db/seed.py` (demo reset), `fixes/apply.py` (approved
  fixes) and `ingest/punches.py` (new device punches, insert only) may write to them; tests
  enforce this.
- Case tables: exceptions, audit_log, tool_calls, settings, scheduler_runs.

All times are plain local wall-clock times ("timestamp without time zone"), like the CSVs.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Stable constraint names, so Alembic migrations are predictable.
NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

EXCEPTION_STATUSES = (
    "open",
    "awaiting_worker",
    "awaiting_supervisor",
    "resolved",
    "rejected",
    "escalated",
)
ACTORS = ("system", "agent", "worker", "supervisor", "admin", "device")
# Shared by every writer that numbers new punches (fixes/apply.py, ingest/punches.py), so
# two transactions never pick the same next punch ID.
PUNCH_ID_LOCK = 42_001


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)
    type_annotation_map = {dict[str, Any]: JSONB, list[Any]: JSONB}


# ------------------------------------------------------------------ source data (CSV tables)


class EmployeeRow(Base):
    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint(_in("role", ("worker", "supervisor", "payroll_admin")), "role"),
    )

    employee_id: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20))
    team: Mapped[str] = mapped_column(String(50))
    supervisor_id: Mapped[str | None] = mapped_column(ForeignKey("employees.employee_id"))

    email: Mapped[str | None] = mapped_column(String(254), deferred=True)
    password_hash: Mapped[str | None] = mapped_column(Text, deferred=True)


Index("uq_employees_email_lower", func.lower(EmployeeRow.email), unique=True)


class AuthSessionRow(Base):
    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.employee_id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class PunchRow(Base):
    """One clock punch. Never deleted or overwritten: a correction voids the old row and
    adds a new one with source='correction', both pointing at the exception."""

    __tablename__ = "timecards"
    __table_args__ = (
        CheckConstraint(_in("type", ("in", "out", "break_start", "break_end")), "type"),
        CheckConstraint(_in("source", ("device", "app", "correction")), "source"),
        Index("ix_timecards_employee_ts", "employee_id", "timestamp"),
    )

    punch_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.employee_id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    type: Mapped[str] = mapped_column(String(12))
    source: Mapped[str] = mapped_column(String(12))
    device_id: Mapped[str] = mapped_column(String(50))
    location: Mapped[str] = mapped_column(String(100))
    voided: Mapped[bool] = mapped_column(Boolean, default=False)
    voided_by_exception: Mapped[str | None] = mapped_column(String(80))
    created_by_exception: Mapped[str | None] = mapped_column(String(80))


class ScheduleEntryRow(Base):
    __tablename__ = "schedule"
    __table_args__ = (UniqueConstraint("employee_id", "date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.employee_id"))
    date: Mapped[date] = mapped_column(Date)
    shift_start: Mapped[time] = mapped_column(Time(timezone=False))
    shift_end: Mapped[time] = mapped_column(Time(timezone=False))


class LeaveRecordRow(Base):
    __tablename__ = "leave_records"
    __table_args__ = (
        UniqueConstraint("employee_id", "date"),
        CheckConstraint(_in("leave_type", ("sick", "casual", "earned")), "leave_type"),
        CheckConstraint(_in("duration", ("full", "half")), "duration"),
        CheckConstraint(_in("status", ("approved", "pending", "rejected")), "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.employee_id"))
    date: Mapped[date] = mapped_column(Date)
    leave_type: Mapped[str] = mapped_column(String(10))
    duration: Mapped[str] = mapped_column(String(4))
    status: Mapped[str] = mapped_column(String(10))
    certificate_uploaded: Mapped[bool] = mapped_column(Boolean, default=False)
    # DB only (not in the CSV): set when an approved fix turns the day into unpaid time off.
    unpaid: Mapped[bool] = mapped_column(Boolean, default=False)


class LeaveBalanceRow(Base):
    __tablename__ = "leave_balances"

    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.employee_id"), primary_key=True)
    leave_type: Mapped[str] = mapped_column(String(10), primary_key=True)
    total_per_year: Mapped[float] = mapped_column(Float)
    used: Mapped[float] = mapped_column(Float)


class HolidayRow(Base):
    __tablename__ = "holidays"
    __table_args__ = (CheckConstraint(_in("type", ("national", "company", "optional")), "type"),)

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(10))


# ------------------------------------------------------------------ case tables


class ExceptionRow(Base):
    """One timecard exception. `id` is the engine's stable exception_id (natural key), so
    running detection twice never creates duplicates."""

    __tablename__ = "exceptions"
    __table_args__ = (
        CheckConstraint(_in("status", EXCEPTION_STATUSES), "status"),
        CheckConstraint(_in("severity", ("low", "medium", "high")), "severity"),
        CheckConstraint(_in("kind", ("breach", "risk")), "kind"),
        CheckConstraint("no_reply_stage BETWEEN 0 AND 3", "no_reply_stage"),
        Index("ix_exceptions_status", "status"),
        Index("ix_exceptions_employee", "employee_id"),
        Index("ix_exceptions_policy", "policy_id"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.employee_id"))
    date: Mapped[date] = mapped_column(Date)
    policy_id: Mapped[str] = mapped_column(String(4))
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(6))
    kind: Mapped[str] = mapped_column(String(6))
    status: Mapped[str] = mapped_column(String(20))
    auto_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    details: Mapped[dict[str, Any]]
    evidence: Mapped[list[Any]]
    fix_options: Mapped[list[Any]]
    proposed_fix: Mapped[dict[str, Any] | None]
    investigation_case: Mapped[dict[str, Any] | None]
    worker_recheck: Mapped[dict[str, Any] | None]
    applied_fix: Mapped[dict[str, Any] | None]  # the option a human approved (or auto-resolve)
    # Hash of the engine facts the stored investigation saw (cases/facts.py). The scheduler
    # investigates again only when the facts changed since.
    investigated_facts_hash: Mapped[str | None] = mapped_column(String(64))
    # Phase 12: a person undid the auto-resolve. Set once, never cleared: the case is never
    # auto-resolved again and the scheduler leaves it to people.
    auto_resolve_undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    auto_resolve_undone_by: Mapped[str | None] = mapped_column(String(8))
    # Phase 13: the no-reply ladder (cases/no_reply.py). Stage 0 none, 1 reminder sent,
    # 2 the supervisor was brought in, 3 the payroll admin was brought in. Each *_at is set
    # once per worker wait; a new wait (ask again, or a No that still needs the time) or
    # any worker reply resets the ladder. `no_reply_wait_since` is when the current wait
    # for the worker began (the question's sent_at, or the No reply's replied_at).
    no_reply_stage: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    no_reply_wait_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    no_reply_reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    no_reply_supervisor_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    no_reply_admin_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    no_reply_late_reply_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    # Phase 18: the ladder limits in force when the current wait began
    # ({"reminder_hours", "supervisor_hours", "admin_hours"}), so a settings change never
    # re-times a wait that is already running. None = no wait recorded (use the current).
    no_reply_limits: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    assigned_to: Mapped[str | None] = mapped_column(ForeignKey("employees.employee_id"))
    waiting_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    last_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))


class WorkerMessageRow(Base):
    __tablename__ = "worker_messages"
    __table_args__ = (
        CheckConstraint(_in("source", ("llm", "template")), "source"),
        Index("ix_worker_messages_recipient_id", "recipient_id"),
        Index("ix_worker_messages_exception_id", "exception_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    exception_id: Mapped[str] = mapped_column(ForeignKey("exceptions.id"))
    recipient_id: Mapped[str] = mapped_column(ForeignKey("employees.employee_id"))
    date: Mapped[date] = mapped_column(Date)
    message: Mapped[str] = mapped_column(Text)
    reply_prompt: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(8))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    confirmed: Mapped[bool | None] = mapped_column(Boolean)
    reply_text: Mapped[str | None] = mapped_column(Text)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    needs_actual_time: Mapped[bool] = mapped_column(Boolean, default=False)
    asked_fix: Mapped[dict[str, Any] | None]
    time_review: Mapped[dict[str, Any] | None]
    # Phase 13: the one reminder for this question (deterministic template, no LLM).
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    reminder_text: Mapped[str | None] = mapped_column(Text)


class PayrollSignoffRow(Base):
    __tablename__ = "payroll_signoffs"

    week_start: Mapped[date] = mapped_column(Date, primary_key=True)
    signed_by: Mapped[str] = mapped_column(ForeignKey("employees.employee_id"))
    signer_name: Mapped[str] = mapped_column(Text)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    note: Mapped[str | None] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64))
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))


class AuditLogRow(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint(_in("actor", ACTORS), "actor"),
        Index("ix_audit_log_exception", "exception_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    exception_id: Mapped[str | None] = mapped_column(ForeignKey("exceptions.id"))
    actor: Mapped[str] = mapped_column(String(12))
    actor_id: Mapped[str | None] = mapped_column(String(8))  # employee ID; null for system
    action: Mapped[str] = mapped_column(String(40))
    before: Mapped[dict[str, Any] | None]
    after: Mapped[dict[str, Any] | None]
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))


class ToolCallRow(Base):
    """One tool call made by the agent while investigating (written from Phase 5)."""

    __tablename__ = "tool_calls"
    __table_args__ = (
        UniqueConstraint("run_id", "step_no", "call_no"),
        Index("ix_tool_calls_exception_id", "exception_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    exception_id: Mapped[str] = mapped_column(ForeignKey("exceptions.id"))
    step_no: Mapped[int] = mapped_column(Integer)
    run_id: Mapped[str | None] = mapped_column(String(32))
    call_no: Mapped[int | None] = mapped_column(Integer)
    tool_name: Mapped[str] = mapped_column(Text)
    ok: Mapped[bool | None] = mapped_column(Boolean)
    duration_ms: Mapped[float | None] = mapped_column(Float)
    input: Mapped[dict[str, Any]]
    output: Mapped[dict[str, Any] | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))


class InvestigationJobRow(Base):
    __tablename__ = "investigation_jobs"
    __table_args__ = (
        CheckConstraint(_in("status", ("running", "completed", "failed")), "status"),
        Index(
            "ix_investigation_jobs_active_exception",
            "exception_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    exception_id: Mapped[str] = mapped_column(ForeignKey("exceptions.id"))
    status: Mapped[str] = mapped_column(String(12))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str | None] = mapped_column(String(40))


class SettingRow(Base):
    """App settings: the demo clock, the scheduler watermark and (Phase 18) the runtime
    overrides (`runtime_overrides`, runtime_settings.py). Policy limits stay in policy.json."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))


class SchedulerRunRow(Base):
    """One scheduler cycle and its summary. Times are real UTC: they describe the server's
    work, not the business day (which stays on the fixed demo clock)."""

    __tablename__ = "scheduler_runs"
    __table_args__ = (
        CheckConstraint(_in("trigger", ("schedule", "run_now")), "trigger"),
        CheckConstraint(_in("status", ("running", "completed", "failed")), "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trigger: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[dict[str, Any] | None]


SOURCE_TABLES = (
    EmployeeRow,
    PunchRow,
    ScheduleEntryRow,
    LeaveRecordRow,
    LeaveBalanceRow,
    HolidayRow,
)


class BriefingRow(Base):
    """Phase 17: one generated daily briefing (LLM or template) for one scope.

    `scope` is "all" (the payroll admin) or a supervisor's employee ID. `facts` is the
    code-built packet the text was checked against and `facts_hash` its hash, so a briefing
    is regenerated only when the facts change (or a person presses Refresh). `attempts`
    holds code-built check results only, never model text. `workflow_at` is the demo clock;
    `created_utc` is real time and drives the rate limits (the demo clock can jump).
    The briefing never changes any data.
    """

    __tablename__ = "briefings"
    __table_args__ = (
        CheckConstraint(_in("source", ("llm", "template")), "source"),
        CheckConstraint(_in("trigger", ("refresh", "scheduler")), "trigger"),
        Index("ix_briefings_scope_id", "scope", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(8))
    facts_hash: Mapped[str] = mapped_column(String(64))
    facts: Mapped[dict[str, Any]]
    content: Mapped[dict[str, Any]]
    source: Mapped[str] = mapped_column(String(8))
    reason: Mapped[str] = mapped_column(String(40))
    attempts: Mapped[list[Any]]
    llm_calls: Mapped[int] = mapped_column(SmallInteger)
    model: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    trigger: Mapped[str] = mapped_column(String(10))
    requested_by: Mapped[str | None] = mapped_column(String(8))
    workflow_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    created_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WorkerQuestionRow(Base):
    """Phase 20: one question a worker asked the employee Q&A, and the answer shown.

    Visible only to the asker (their own history) and the payroll admin. `kind` is
    "answer" or "refusal"; `source` says who wrote the text (llm, template or refusal).
    `attempts` holds code-built check codes, call stages and token counts only, never model
    text; a rejected draft is never stored. `facts_hash` identifies the facts packet the
    answer was checked against (the packet itself is not kept). `workflow_at` is the demo
    clock; `created_utc` is real time and drives the rate limits. Retention: see
    docs/PROGRESS.md Phase 20 (a demo reset clears the table).
    """

    __tablename__ = "worker_questions"
    __table_args__ = (
        CheckConstraint(_in("kind", ("answer", "refusal")), "kind"),
        CheckConstraint(_in("source", ("llm", "template", "refusal")), "source"),
        Index("ix_worker_questions_employee_id", "employee_id", "id"),
        Index("ix_worker_questions_created_utc", "created_utc"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.employee_id"))
    question: Mapped[str] = mapped_column(Text)
    intents: Mapped[list[Any]]
    plan_source: Mapped[str] = mapped_column(String(10))
    kind: Mapped[str] = mapped_column(String(8))
    source: Mapped[str] = mapped_column(String(8))
    reason: Mapped[str] = mapped_column(String(40))
    refusal_code: Mapped[str | None] = mapped_column(String(20))
    answer: Mapped[str] = mapped_column(Text)
    sources: Mapped[list[Any]]
    facts_hash: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[list[Any]]
    llm_calls: Mapped[int] = mapped_column(SmallInteger)
    model: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    workflow_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    created_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
