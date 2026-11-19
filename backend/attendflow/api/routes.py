"""API endpoints. Thin: validate input, call the case service, shape the output."""

from __future__ import annotations

import hmac
from collections.abc import Iterator
from datetime import date
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from attendflow import __version__, demo_clock
from attendflow.api.schemas import (
    EMPLOYEE_ID,
    POLICY_ID,
    ActorType,
    AdminCaseOut,
    AdminOverviewOut,
    AdminSort,
    ApproveIn,
    ApproveOut,
    AskWorkerIn,
    AuditEntryOut,
    AuditListOut,
    AutoResolveMetricOut,
    DemoClockIn,
    DemoClockOut,
    DemoPunchIn,
    DemoResetOut,
    DetectionRunOut,
    EditIn,
    ErrorResponse,
    EscalateIn,
    ExceptionDetailOut,
    ExceptionListOut,
    ExceptionOut,
    HealthOut,
    InvestigationJobOut,
    NoReplyFilter,
    PunchAcceptedOut,
    PunchIn,
    RejectIn,
    SchedulerCycleOut,
    SchedulerStatusOut,
    SeedOut,
    Severity,
    SupervisorCaseOut,
    SupervisorQueueOut,
    TeamAutoFixesOut,
    ToolCallListOut,
    ToolCallOut,
    UndoIn,
    UndoOut,
    WorkerInboxOut,
    WorkerReplyIn,
    WorkerReplyOut,
    WorkerTimeIn,
)
from attendflow.cases import admin, auto_fix, service, supervisor
from attendflow.cases.transitions import Status
from attendflow.clock import Clock
from attendflow.config import Settings
from attendflow.data.loader import DataValidationError
from attendflow.db.models import AuditLogRow, EmployeeRow, ExceptionRow, ToolCallRow
from attendflow.db.seed import seed_from_csv
from attendflow.errors import (
    AppError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
    UnauthorizedError,
)
from attendflow.ingest.punches import PunchInput, Via, ingest_punch
from attendflow.policy.models import PolicyConfig, load_policy_text
from attendflow.scheduler.cycle import set_watermark
from attendflow.scheduler.runner import Scheduler

router = APIRouter(prefix="/api")
# DEMO_MODE only: create_app() includes this router only when ATTENDFLOW_DEMO_MODE=true, so
# with demo mode off these endpoints do not exist at all (404). Phase 22 checklist.
demo_router = APIRouter(prefix="/api/admin/demo", tags=["demo"])


def _errors(*codes: int) -> dict:
    return {c: {"model": ErrorResponse} for c in codes}


# ---------------------------------------------------------------- dependencies


def get_session(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()  # rolls back anything not committed


def get_policy(request: Request) -> PolicyConfig:
    return request.app.state.policy


def get_clock(request: Request) -> Clock:
    return request.app.state.clock


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


SessionDep = Annotated[Session, Depends(get_session)]
PolicyDep = Annotated[PolicyConfig, Depends(get_policy)]
ClockDep = Annotated[Clock, Depends(get_clock)]
ActorId = Annotated[
    str,
    Header(
        alias="X-Actor-Id",
        pattern=EMPLOYEE_ID,
        description="Employee ID of the person acting (no login yet), e.g. E101 for Ravi",
    ),
]


# ---------------------------------------------------------------- system


@router.get("/health", response_model=HealthOut, tags=["system"], summary="Health check")
def health(request: Request, session: SessionDep, clock: ClockDep, policy: PolicyDep):
    try:
        session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001 - any DB failure means "unreachable"
        db_ok = False
    body = HealthOut(
        status="ok" if db_ok else "degraded",
        database="ok" if db_ok else "unreachable",
        as_of=clock.now(),
        policy_version=policy.version,
        version=__version__,
    )
    if not db_ok:
        return JSONResponse(status_code=503, content=body.model_dump(mode="json"))
    return body


@router.post(
    "/seed",
    response_model=SeedOut,
    tags=["system"],
    summary="Reset the demo: wipe all tables and reload the CSVs",
    description="Destructive. Disabled when ATTENDFLOW_ENABLE_SEED=false "
    "(must be off or protected on a deployed server).",
    responses=_errors(403, 422),
)
def seed(
    request: Request, session: SessionDep, settings: Annotated[Settings, Depends(get_settings_dep)]
):
    if not settings.enable_seed:
        raise ForbiddenError("seeding is disabled on this server", code="seed_disabled")
    try:
        with session.begin():
            counts = seed_from_csv(session, settings.data_dir)
    except DataValidationError as exc:
        raise AppError(
            "the demo CSVs are invalid; nothing was changed",
            code="invalid_data",
            details=exc.errors,
        ) from exc
    request.app.state.logger.info("demo data seeded", extra={"event": "seed", **counts})
    return SeedOut(message="Demo data loaded. Run detection next.", counts=counts)


@router.post(
    "/detection/run",
    response_model=DetectionRunOut,
    tags=["detection"],
    summary="Run the rule engine on the database and save the exceptions",
    description="Idempotent: exceptions are upserted by their stable ID.",
    responses=_errors(409),
)
def run_detection(
    session: SessionDep,
    policy: PolicyDep,
    clock: ClockDep,
    settings: Annotated[Settings, Depends(get_settings_dep)],
):
    summary = service.run_detection(
        session, policy, clock, auto_resolve=settings.auto_resolve_enabled
    )
    return DetectionRunOut(**summary.__dict__)


# ---------------------------------------------------------------- exceptions


@router.get(
    "/exceptions",
    response_model=ExceptionListOut,
    tags=["exceptions"],
    summary="List exceptions",
)
def list_exceptions(
    session: SessionDep,
    status: Status | None = None,
    employee_id: Annotated[str | None, Query(pattern=EMPLOYEE_ID)] = None,
    policy_id: Annotated[str | None, Query(pattern=POLICY_ID)] = None,
    assigned_to: Annotated[str | None, Query(pattern=EMPLOYEE_ID)] = None,
):
    stmt = select(ExceptionRow)
    if status:
        stmt = stmt.where(ExceptionRow.status == status)
    if employee_id:
        stmt = stmt.where(ExceptionRow.employee_id == employee_id)
    if policy_id:
        stmt = stmt.where(ExceptionRow.policy_id == policy_id)
    if assigned_to:
        stmt = stmt.where(ExceptionRow.assigned_to == assigned_to)
    stmt = stmt.order_by(
        ExceptionRow.employee_id,
        ExceptionRow.date,
        func.length(ExceptionRow.policy_id),
        ExceptionRow.policy_id,
        ExceptionRow.id,
    )
    rows = session.scalars(stmt).all()
    return ExceptionListOut(count=len(rows), items=[ExceptionOut.model_validate(r) for r in rows])


def _audit_for(session: Session, exception_id: str) -> list[AuditEntryOut]:
    rows = session.scalars(
        select(AuditLogRow).where(AuditLogRow.exception_id == exception_id).order_by(AuditLogRow.id)
    ).all()
    return [AuditEntryOut.model_validate(r) for r in rows]


def _detail(session: Session, row: ExceptionRow) -> ExceptionDetailOut:
    base = ExceptionOut.model_validate(row).model_dump()
    return ExceptionDetailOut(
        **base, investigation_case=row.investigation_case, audit_trail=_audit_for(session, row.id)
    )


@router.get(
    "/exceptions/{exception_id}",
    response_model=ExceptionDetailOut,
    tags=["exceptions"],
    summary="One exception with its audit trail",
    responses=_errors(404),
)
def get_exception(exception_id: str, session: SessionDep):
    row = session.get(ExceptionRow, exception_id)
    if row is None:
        raise NotFoundError(f"exception {exception_id} not found", code="exception_not_found")
    return _detail(session, row)


@router.post(
    "/exceptions/{exception_id}/investigate",
    response_model=InvestigationJobOut,
    status_code=202,
    tags=["exceptions"],
    responses=_errors(403, 404, 422),
)
def start_investigation(
    exception_id: str,
    actor: ActorId,
    request: Request,
    response: Response,
    background: BackgroundTasks,
):
    jobs = request.app.state.investigation_jobs
    job, created = jobs.start(exception_id, actor)
    if created:
        background.add_task(jobs.run, job.id)
    response.headers["Location"] = f"/api/exceptions/{exception_id}/investigate/{job.id}"
    return job


@router.get(
    "/exceptions/{exception_id}/investigate/{job_id}",
    response_model=InvestigationJobOut,
    tags=["exceptions"],
    responses=_errors(403, 404, 422),
)
def poll_investigation(exception_id: str, job_id: str, actor: ActorId, request: Request):
    return request.app.state.investigation_jobs.get(exception_id, job_id, actor)


_DECISION_ERRORS = _errors(403, 404, 409, 422)


def _approved(
    session: Session, policy: PolicyConfig, clock: Clock, row: ExceptionRow, settings: Settings
):
    exception_id = row.id
    detection = service.detect_after_fix(
        session, policy, clock, exception_id, auto_resolve=settings.auto_resolve_enabled
    )
    with session.begin():
        fresh = session.get(ExceptionRow, exception_id, populate_existing=True)
        detail = _detail(session, fresh)
    return ApproveOut(**detail.model_dump(), detection=detection)


@router.post(
    "/exceptions/{exception_id}/approve",
    response_model=ApproveOut,
    tags=["decisions"],
    summary="Approve a fix option: applies it and resolves the exception (one transaction)",
    description="Supervisors and the payroll admin only, and only the assignee. After a fix "
    "that changed data, detection re-runs so new exceptions it created appear as open cases.",
    responses=_DECISION_ERRORS,
)
def approve(
    exception_id: str,
    body: ApproveIn,
    actor_id: ActorId,
    session: SessionDep,
    policy: PolicyDep,
    clock: ClockDep,
    settings: Annotated[Settings, Depends(get_settings_dep)],
):
    row = service.approve(
        session,
        policy,
        clock,
        exception_id=exception_id,
        actor_id=actor_id,
        option_id=body.option_id,
        reason=body.reason,
        without_worker=body.without_worker,
        confirm_time_without_worker=body.confirm_time_without_worker,
    )
    return _approved(session, policy, clock, row, settings)


@router.post(
    "/exceptions/{exception_id}/edit",
    response_model=ApproveOut,
    tags=["decisions"],
    summary="Approve a fix option with changed params (validated before anything is saved)",
    responses=_DECISION_ERRORS,
)
def edit(
    exception_id: str,
    body: EditIn,
    actor_id: ActorId,
    session: SessionDep,
    policy: PolicyDep,
    clock: ClockDep,
    settings: Annotated[Settings, Depends(get_settings_dep)],
):
    row = service.approve(
        session,
        policy,
        clock,
        exception_id=exception_id,
        actor_id=actor_id,
        option_id=body.option_id,
        reason=body.reason,
        params=body.params,
        without_worker=body.without_worker,
        confirm_time_without_worker=body.confirm_time_without_worker,
    )
    return _approved(session, policy, clock, row, settings)


@router.post(
    "/exceptions/{exception_id}/reject",
    response_model=ExceptionDetailOut,
    tags=["decisions"],
    summary="Reject: a supervisor's reject escalates to the payroll admin; "
    "the admin's reject is final",
    responses=_DECISION_ERRORS,
)
def reject(
    exception_id: str, body: RejectIn, actor_id: ActorId, session: SessionDep, clock: ClockDep
):
    row = service.reject(
        session, clock, exception_id=exception_id, actor_id=actor_id, reason=body.reason
    )
    return _detail(session, row)


@router.post(
    "/exceptions/{exception_id}/escalate",
    response_model=ExceptionDetailOut,
    tags=["decisions"],
    summary="Send the case to the payroll admin without rejecting the fix",
    description="Only the assignee (a supervisor); workers get 403 supervisor_only. The case "
    "becomes escalated and assigned to the payroll admin, with the reason in the audit log. "
    "No data changes. Used after the no-reply ladder brought the supervisor in (Phase 13), "
    "or whenever the supervisor cannot decide.",
    responses=_DECISION_ERRORS,
)
def escalate(
    exception_id: str, body: EscalateIn, actor_id: ActorId, session: SessionDep, clock: ClockDep
):
    row = service.escalate(
        session, clock, exception_id=exception_id, actor_id=actor_id, reason=body.reason
    )
    return _detail(session, row)


@router.post(
    "/exceptions/{exception_id}/undo",
    response_model=UndoOut,
    tags=["decisions"],
    summary="Undo an auto-resolve: restore the rows, reopen the case for people",
    description="The payroll admin may undo any auto-resolved case; a supervisor only their "
    "own team's (else 403 not_assigned); workers get 403 supervisor_only. The rows the "
    "auto-resolve changed go back to their stored 'before' values through fixes/apply.py. "
    "409 undo_conflict when a stored row (or this worker's punches that day, by another "
    "fix) changed since: nothing changes except an undo_refused audit row. 409 "
    "not_auto_resolved / already_undone / undo_unavailable (no snapshot). The case "
    "becomes open with the worker's supervisor and is never auto-resolved or handled by "
    "the scheduler again.",
    responses=_errors(403, 404, 409, 422),
)
def undo(
    exception_id: str,
    body: UndoIn,
    actor_id: ActorId,
    session: SessionDep,
    policy: PolicyDep,
    clock: ClockDep,
    settings: Annotated[Settings, Depends(get_settings_dep)],
):
    _row, restored = service.undo_auto_resolve(
        session, policy, clock, exception_id=exception_id, actor_id=actor_id, reason=body.reason
    )
    detection = service.detect_after_fix(
        session,
        policy,
        clock,
        exception_id,
        auto_resolve=settings.auto_resolve_enabled,
        changed=bool(restored),
        after="undo",
    )
    with session.begin():
        fresh = session.get(ExceptionRow, exception_id, populate_existing=True)
        detail = _detail(session, fresh)
    return UndoOut(**detail.model_dump(), restored=restored, detection=detection)


@router.post(
    "/exceptions/{exception_id}/ask-worker",
    response_model=ExceptionDetailOut,
    tags=["decisions"],
    summary="Hand the case to the worker to confirm what happened",
    responses=_DECISION_ERRORS,
)
def ask_worker(
    exception_id: str,
    body: AskWorkerIn,
    actor_id: ActorId,
    session: SessionDep,
    clock: ClockDep,
    settings: Annotated[Settings, Depends(get_settings_dep)],
):
    row = service.ask_worker(
        session, clock, settings, exception_id=exception_id, actor_id=actor_id, note=body.note
    )
    return _detail(session, row)


@router.post(
    "/exceptions/{exception_id}/worker-reply",
    response_model=WorkerReplyOut,
    response_model_exclude_none=True,
    tags=["decisions"],
    summary="Record the worker's Yes or No and return a receipt",
    responses=_DECISION_ERRORS,
)
def worker_reply(
    exception_id: str,
    body: WorkerReplyIn,
    actor_id: ActorId,
    session: SessionDep,
    clock: ClockDep,
    policy: PolicyDep,
    settings: Annotated[Settings, Depends(get_settings_dep)],
):
    message = service.worker_reply(
        session,
        clock,
        settings,
        policy,
        exception_id=exception_id,
        actor_id=actor_id,
        confirmed=body.confirmed,
        text=body.text,
    )
    return message


@router.post(
    "/exceptions/{exception_id}/worker-confirm-time",
    response_model=WorkerReplyOut,
    response_model_exclude_none=True,
    tags=["worker"],
    responses=_DECISION_ERRORS,
)
def worker_confirm_time(
    exception_id: str, actor_id: ActorId, session: SessionDep, clock: ClockDep, policy: PolicyDep
):
    return service.submit_worker_time(
        session, clock, policy, exception_id=exception_id, actor_id=actor_id
    )


@router.post(
    "/exceptions/{exception_id}/worker-manual-time",
    response_model=WorkerReplyOut,
    response_model_exclude_none=True,
    tags=["worker"],
    responses=_DECISION_ERRORS,
)
def worker_manual_time(
    exception_id: str,
    body: WorkerTimeIn,
    actor_id: ActorId,
    session: SessionDep,
    clock: ClockDep,
    policy: PolicyDep,
):
    return service.submit_worker_time(
        session,
        clock,
        policy,
        exception_id=exception_id,
        actor_id=actor_id,
        time=body.time,
        actual_date=body.actual_date,
    )


@router.get(
    "/worker/messages",
    response_model=WorkerInboxOut,
    response_model_exclude_none=True,
    tags=["worker"],
    summary="Questions and pending follow-ups for the worker",
    responses=_errors(403, 422),
)
def worker_messages(actor_id: ActorId, session: SessionDep, clock: ClockDep):
    with session.begin():
        return service.worker_inbox(session, actor_id, clock)


# ---------------------------------------------------------------- supervisor


@router.get(
    "/supervisor/queue",
    response_model=SupervisorQueueOut,
    tags=["supervisor"],
    summary="Cases waiting for the caller's decision",
    description="A supervisor sees their own team's cases assigned to them that are "
    "awaiting_supervisor, or open with an investigation routed to the supervisor, plus "
    "escalated cases assigned to them. The payroll admin sees escalated cases assigned to "
    "them. Cases still waiting for the worker's actual time never appear, unless the "
    "no-reply ladder brought the supervisor in (then `no_reply` says how long the worker "
    "has been silent). Workers get 403. "
    "Sorted by severity (high first), then date, then ID.",
    responses=_errors(403, 422),
)
def supervisor_queue(actor_id: ActorId, session: SessionDep, clock: ClockDep):
    with session.begin():
        items = supervisor.queue(session, actor_id, clock.now())
    return SupervisorQueueOut(count=len(items), items=items)


@router.get(
    "/supervisor/cases/{exception_id}",
    response_model=SupervisorCaseOut,
    tags=["supervisor"],
    summary="The case card: issue, policy, evidence, worker reply, re-check and fix options",
    description="Only the assignee (a supervisor or the payroll admin) may open it. Evidence "
    "rows of other workers are left out and their names are redacted. Every text is stored "
    "data or built by code; this endpoint never calls the LLM.",
    responses=_errors(403, 404, 422),
)
def supervisor_case(
    exception_id: str,
    actor_id: ActorId,
    session: SessionDep,
    policy: PolicyDep,
    clock: ClockDep,
    settings: Annotated[Settings, Depends(get_settings_dep)],
):
    sections = load_policy_text(settings.data_dir / "policy.md")
    with session.begin():
        return supervisor.case_card(
            session,
            policy,
            sections,
            exception_id=exception_id,
            actor_id=actor_id,
            now=clock.now(),
        )


@router.get(
    "/supervisor/auto-resolved",
    response_model=TeamAutoFixesOut,
    tags=["supervisor"],
    summary="Auto-resolved (and undone) P2/P7 cases for the caller's team",
    description="A supervisor sees their own team's; the payroll admin sees all. Each item "
    "says what was fixed, why code was allowed to close it, the policy text, and whether "
    "the caller may undo it. Workers get 403. Read-only; never calls the LLM.",
    responses=_errors(403, 422),
)
def supervisor_auto_resolved(
    actor_id: ActorId,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings_dep)],
):
    sections = load_policy_text(settings.data_dir / "policy.md")
    with session.begin():
        items = auto_fix.team_auto_fixes(session, sections, actor_id)
    return TeamAutoFixesOut(count=len(items), items=items)


# ---------------------------------------------------------------- payroll admin


@router.get(
    "/admin/metrics/auto-resolve",
    response_model=AutoResolveMetricOut,
    tags=["admin"],
    summary="X of Y exceptions resolved without a human (payroll admin only)",
    description="Counted by code from the database. X = auto-resolved and not undone. Y = "
    "exceptions that needed handling: all in the date range except those closed because "
    "the data changed (no_longer_detected), which are returned as closed_by_data_change. "
    "Optional date_from/date_to filter on the exception date.",
    responses=_errors(403, 422),
)
def auto_resolve_metric(
    actor_id: ActorId,
    session: SessionDep,
    policy: PolicyDep,
    settings: Annotated[Settings, Depends(get_settings_dep)],
    date_from: date | None = None,
    date_to: date | None = None,
):
    with session.begin():
        admin.require_admin(session, actor_id)
        return auto_fix.metric(
            session,
            policy,
            auto_resolve_enabled=settings.auto_resolve_enabled,
            date_from=date_from,
            date_to=date_to,
        )


@router.get(
    "/admin/exceptions",
    response_model=AdminOverviewOut,
    tags=["admin"],
    summary="Every exception, with counters (payroll admin only)",
    description="Only the payroll admin may call this; everyone else gets 403 admin_only. "
    "Counters are counted by the database over every exception and ignore the filters. "
    "`q` matches the employee name or ID (case-insensitive). Default sort: severity "
    "(high first), then date, then ID. Read-only; never calls the LLM.",
    responses=_errors(403, 422),
)
def admin_exceptions(
    actor_id: ActorId,
    session: SessionDep,
    clock: ClockDep,
    status: Status | None = None,
    policy_id: Annotated[str | None, Query(pattern=POLICY_ID)] = None,
    team: Annotated[str | None, Query(min_length=1, max_length=40)] = None,
    employee_id: Annotated[str | None, Query(pattern=EMPLOYEE_ID)] = None,
    severity: Severity | None = None,
    q: Annotated[str | None, Query(max_length=60)] = None,
    no_reply: Annotated[
        NoReplyFilter | None,
        Query(description="Cases the no-reply ladder touched (any) or at one stage"),
    ] = None,
    sort: AdminSort = "severity",
    limit: Annotated[int, Query(ge=1, le=admin.MAX_LIMIT)] = admin.DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    with session.begin():
        return admin.overview(
            session,
            actor_id,
            status=status,
            policy_id=policy_id,
            team=team,
            employee_id=employee_id,
            severity=severity,
            q=q,
            no_reply=no_reply,
            sort=sort,
            limit=limit,
            offset=offset,
            now=clock.now(),
        )


@router.get(
    "/admin/exceptions/{exception_id}",
    response_model=AdminCaseOut,
    tags=["admin"],
    summary="One case, read-only: evidence, investigation, worker reply, re-check, audit",
    description="Payroll admin only. The full audit trail is oldest first. Tool calls are "
    "listed with their arguments and outcome only (no tool output, prompts or keys). To "
    "investigate, use POST /api/exceptions/{id}/investigate; to decide an escalated case, "
    "use the supervisor card and decision endpoints.",
    responses=_errors(403, 404, 422),
)
def admin_exception(
    exception_id: str,
    actor_id: ActorId,
    session: SessionDep,
    policy: PolicyDep,
    clock: ClockDep,
    settings: Annotated[Settings, Depends(get_settings_dep)],
):
    sections = load_policy_text(settings.data_dir / "policy.md")
    with session.begin():
        return admin.detail(
            session,
            policy,
            sections,
            exception_id=exception_id,
            actor_id=actor_id,
            now=clock.now(),
        )


# ---------------------------------------------------------------- logs


@router.get("/audit-log", response_model=AuditListOut, tags=["logs"], summary="Audit log")
def audit_log(
    session: SessionDep,
    exception_id: str | None = None,
    actor: ActorType | None = None,
    actor_id: Annotated[str | None, Query(pattern=EMPLOYEE_ID)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
):
    stmt = select(AuditLogRow)
    if exception_id:
        stmt = stmt.where(AuditLogRow.exception_id == exception_id)
    if actor:
        stmt = stmt.where(AuditLogRow.actor == actor)
    if actor_id:
        stmt = stmt.where(AuditLogRow.actor_id == actor_id)
    rows = session.scalars(stmt.order_by(AuditLogRow.id).limit(limit)).all()
    return AuditListOut(count=len(rows), items=[AuditEntryOut.model_validate(r) for r in rows])


@router.get(
    "/tool-calls",
    response_model=ToolCallListOut,
    tags=["logs"],
    summary="Agent tool calls (filled from Phase 5)",
)
def tool_calls(
    session: SessionDep,
    exception_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
):
    stmt = select(ToolCallRow)
    if exception_id:
        stmt = stmt.where(ToolCallRow.exception_id == exception_id)
    rows = session.scalars(
        stmt.order_by(ToolCallRow.exception_id, ToolCallRow.id).limit(limit)
    ).all()
    return ToolCallListOut(count=len(rows), items=[ToolCallOut.model_validate(r) for r in rows])


# ---------------------------------------------------------------- device punches (Phase 11)


def _receive_punch(
    request: Request,
    session: Session,
    body: PunchIn,
    *,
    via: Via,
    requested_by: str | None,
) -> PunchAcceptedOut:
    """Store the punch (ingest module, own transaction, audited), then run detection for
    the worker's week in a second transaction that can fail without losing the punch."""
    state = request.app.state
    punch = ingest_punch(
        session,
        state.clock,
        state.settings,
        state.policy,
        PunchInput(
            employee_id=body.employee_id,
            timestamp=body.local_timestamp(),
            type=body.type,
            device_id=body.device_id,
            location=body.location,
        ),
        via=via,
        requested_by=requested_by,
    )
    detection = service.detect_after_punch(
        session,
        state.policy,
        state.clock,
        punch,
        auto_resolve=state.settings.auto_resolve_enabled,
    )
    return PunchAcceptedOut(punch=punch, detection=detection)


@router.post(
    "/punches",
    response_model=PunchAcceptedOut,
    status_code=201,
    tags=["device"],
    summary="Mock attendance device: record one punch",
    description="Authenticated by the `X-Device-Key` header (DEVICE_API_KEY), not by an "
    "actor. The timestamp is local time with no timezone and may not be after the as-of "
    "time. An exact duplicate is 409. The punch is written by the ingest module with a "
    "`punch_ingested` audit row; detection then runs for that worker's week. Uses no LLM.",
    responses=_errors(401, 409, 422, 503),
)
def receive_punch(
    body: PunchIn,
    request: Request,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings_dep)],
    device_key: Annotated[str | None, Header(alias="X-Device-Key")] = None,
):
    if not settings.device_api_key:
        raise ServiceUnavailableError(
            "the device API is not configured on this server (DEVICE_API_KEY)",
            code="device_api_not_configured",
        )
    if device_key is None or not hmac.compare_digest(
        device_key.encode("utf-8"), settings.device_api_key.encode("utf-8")
    ):
        raise UnauthorizedError("missing or wrong device key", code="invalid_device_key")
    return _receive_punch(request, session, body, via="device_api", requested_by=None)


# ---------------------------------------------------------------- scheduler (Phase 11)


def _scheduler(request: Request) -> Scheduler:
    return request.app.state.scheduler


def _require_admin(session: Session, actor_id: str) -> None:
    with session.begin():
        admin.require_admin(session, actor_id)


def _status(request: Request, session: Session) -> SchedulerStatusOut:
    settings = request.app.state.settings
    workers = []
    if settings.demo_mode:
        with session.begin():
            workers = [
                {"employee_id": e.employee_id, "name": e.name, "team": e.team}
                for e in session.scalars(
                    select(EmployeeRow)
                    .where(EmployeeRow.role == "worker")
                    .order_by(EmployeeRow.employee_id)
                )
            ]
    clock = request.app.state.clock
    return SchedulerStatusOut(
        **_scheduler(request).status(),
        as_of=clock.now(),
        clock=demo_clock.describe(clock, settings.demo_mode),
        no_reply={
            "enabled": settings.no_reply_escalation_enabled,
            "reminder_hours": settings.no_reply_reminder_hours,
            "supervisor_hours": settings.no_reply_supervisor_hours,
            "admin_hours": settings.no_reply_admin_hours,
        },
        demo_mode=settings.demo_mode,
        workers=workers,
    )


@router.get(
    "/admin/scheduler",
    response_model=SchedulerStatusOut,
    tags=["scheduler"],
    summary="Scheduler status and the last cycle's summary (payroll admin only)",
    responses=_errors(403, 422),
)
def scheduler_status(actor_id: ActorId, request: Request, session: SessionDep):
    _require_admin(session, actor_id)
    return _status(request, session)


@router.post(
    "/admin/scheduler/run-now",
    response_model=SchedulerCycleOut,
    tags=["scheduler"],
    summary="Run one scheduler cycle now and return its summary (payroll admin only)",
    description="Detection, then investigations of new cases and worker messages within "
    "the per-cycle limits. 409 scheduler_busy if a cycle is already running.",
    responses=_errors(403, 409, 422),
)
def scheduler_run_now(actor_id: ActorId, request: Request, session: SessionDep):
    _require_admin(session, actor_id)
    summary = _scheduler(request).run_once("run_now")
    if summary is None:
        raise ConflictError("a scheduler cycle is already running", code="scheduler_busy")
    return summary


@router.post(
    "/admin/scheduler/start",
    response_model=SchedulerStatusOut,
    tags=["scheduler"],
    summary="Start the timer (runtime only; a restart goes back to SCHEDULER_ENABLED)",
    description="Cases detected from now on count as new for the scheduler.",
    responses=_errors(403, 422),
)
def scheduler_start(actor_id: ActorId, request: Request, session: SessionDep):
    _require_admin(session, actor_id)
    _scheduler(request).start()
    return _status(request, session)


@router.post(
    "/admin/scheduler/stop",
    response_model=SchedulerStatusOut,
    tags=["scheduler"],
    summary="Stop the timer (a running cycle finishes first)",
    responses=_errors(403, 422),
)
def scheduler_stop(actor_id: ActorId, request: Request, session: SessionDep):
    _require_admin(session, actor_id)
    _scheduler(request).stop()
    return _status(request, session)


# ---------------------------------------------------------------- demo helpers (DEMO_MODE)


@demo_router.post(
    "/reset",
    response_model=DemoResetOut,
    summary="Demo only: reseed, run detection, and reset the scheduler's 'new case' mark",
    description="Exists only when ATTENDFLOW_DEMO_MODE=true. Payroll admin only. "
    "Destructive: wipes every table like POST /api/seed.",
    responses=_errors(403, 409, 422),
)
def demo_reset(actor_id: ActorId, request: Request, session: SessionDep):
    state = request.app.state
    _require_admin(session, actor_id)
    if _scheduler(request).busy:
        raise ConflictError("a scheduler cycle is running; try again", code="scheduler_busy")
    try:
        with session.begin():
            counts = seed_from_csv(session, state.settings.data_dir)
            demo_clock.reset(session, state.clock)  # back to the as-of time (Phase 13)
    except DataValidationError as exc:
        raise AppError(
            "the demo CSVs are invalid; nothing was changed",
            code="invalid_data",
            details=exc.errors,
        ) from exc
    detection = service.run_detection(
        session, state.policy, state.clock, auto_resolve=state.settings.auto_resolve_enabled
    )
    watermark = set_watermark(state.session_factory, state.clock, "demo_reset")
    state.logger.info("demo reset", extra={"event": "demo_reset", **counts})
    return DemoResetOut(
        seed=SeedOut(message="Demo data loaded and detection run.", counts=counts),
        detection=DetectionRunOut(**detection.__dict__),
        watermark_audit_id=watermark,
        clock=demo_clock.describe(state.clock, True),
    )


@demo_router.post(
    "/punch",
    response_model=PunchAcceptedOut,
    status_code=201,
    summary="Demo only: send a simulated device punch",
    description="Exists only when ATTENDFLOW_DEMO_MODE=true. Payroll admin only. Goes "
    "through the same ingest module and checks as POST /api/punches, so the device key "
    "never has to be in the browser. Audited with via=demo_simulator.",
    responses=_errors(403, 409, 422),
)
def demo_punch(body: DemoPunchIn, actor_id: ActorId, request: Request, session: SessionDep):
    _require_admin(session, actor_id)
    return _receive_punch(request, session, body, via="demo_simulator", requested_by=actor_id)


@demo_router.get(
    "/clock",
    response_model=DemoClockOut,
    summary="Demo only: the demo clock (now, the data cut-off, the offset)",
    description="Exists only when ATTENDFLOW_DEMO_MODE=true. Payroll admin only.",
    responses=_errors(403, 422),
)
def demo_clock_get(actor_id: ActorId, request: Request, session: SessionDep):
    _require_admin(session, actor_id)
    return demo_clock.describe(request.app.state.clock, True)


@demo_router.post(
    "/clock",
    response_model=DemoClockOut,
    summary="Demo only: move the demo clock forward (shows the no-reply timeouts)",
    description="Exists only when ATTENDFLOW_DEMO_MODE=true. Payroll admin only. Forward "
    "only, at most 14 days past the as-of time (422 clock_limit), audited as "
    "demo_clock_moved. Moves `now` (row stamps, timeouts) but never the data cut-off, so "
    "detection is unchanged. It runs nothing: the next scheduler cycle (or Run scheduler "
    "now) applies the timeouts. A demo reset puts it back to the as-of time.",
    responses=_errors(403, 409, 422),
)
def demo_clock_move(body: DemoClockIn, actor_id: ActorId, request: Request, session: SessionDep):
    _require_admin(session, actor_id)
    clock = request.app.state.clock
    demo_clock.move(session, clock, body.hours, actor_id)
    return demo_clock.describe(clock, True, hint=demo_clock.HINT)
