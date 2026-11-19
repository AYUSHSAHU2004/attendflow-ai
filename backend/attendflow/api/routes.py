"""API endpoints. Thin: validate input, call the case service, shape the output."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from attendflow import __version__
from attendflow.api.schemas import (
    EMPLOYEE_ID,
    POLICY_ID,
    ActorType,
    ApproveIn,
    AskWorkerIn,
    AuditEntryOut,
    AuditListOut,
    DetectionRunOut,
    EditIn,
    ErrorResponse,
    ExceptionDetailOut,
    ExceptionListOut,
    ExceptionOut,
    HealthOut,
    InvestigationJobOut,
    RejectIn,
    SeedOut,
    ToolCallListOut,
    ToolCallOut,
    WorkerReplyIn,
)
from attendflow.cases import service
from attendflow.cases.transitions import Status
from attendflow.clock import Clock
from attendflow.config import Settings
from attendflow.data.loader import DataValidationError
from attendflow.db.models import AuditLogRow, ExceptionRow, ToolCallRow
from attendflow.db.seed import seed_from_csv
from attendflow.errors import AppError, ForbiddenError, NotFoundError
from attendflow.policy.models import PolicyConfig

router = APIRouter(prefix="/api")


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
def run_detection(session: SessionDep, policy: PolicyDep, clock: ClockDep):
    summary = service.run_detection(session, policy, clock)
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


@router.post(
    "/exceptions/{exception_id}/approve",
    response_model=ExceptionDetailOut,
    tags=["decisions"],
    summary="Approve a fix option: applies it and resolves the exception (one transaction)",
    responses=_DECISION_ERRORS,
)
def approve(
    exception_id: str,
    body: ApproveIn,
    actor_id: ActorId,
    session: SessionDep,
    policy: PolicyDep,
    clock: ClockDep,
):
    row = service.approve(
        session,
        policy,
        clock,
        exception_id=exception_id,
        actor_id=actor_id,
        option_id=body.option_id,
        reason=body.reason,
    )
    return _detail(session, row)


@router.post(
    "/exceptions/{exception_id}/edit",
    response_model=ExceptionDetailOut,
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
    )
    return _detail(session, row)


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
    "/exceptions/{exception_id}/ask-worker",
    response_model=ExceptionDetailOut,
    tags=["decisions"],
    summary="Hand the case to the worker to confirm what happened",
    responses=_DECISION_ERRORS,
)
def ask_worker(
    exception_id: str, body: AskWorkerIn, actor_id: ActorId, session: SessionDep, clock: ClockDep
):
    row = service.ask_worker(
        session, clock, exception_id=exception_id, actor_id=actor_id, note=body.note
    )
    return _detail(session, row)


@router.post(
    "/exceptions/{exception_id}/worker-reply",
    response_model=ExceptionDetailOut,
    tags=["decisions"],
    summary="The worker's Yes/No + free text (placeholder: stored as-is until Phase 8)",
    responses=_DECISION_ERRORS,
)
def worker_reply(
    exception_id: str,
    body: WorkerReplyIn,
    actor_id: ActorId,
    session: SessionDep,
    clock: ClockDep,
):
    row = service.worker_reply(
        session,
        clock,
        exception_id=exception_id,
        actor_id=actor_id,
        confirmed=body.confirmed,
        text=body.text,
    )
    return _detail(session, row)


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
