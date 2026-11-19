"""Phase 13: run the no-reply ladder (rules in cases/no_reply.py).

Called once per scheduler cycle (timer or "Run scheduler now", also with the timer off).
Each case is one transaction with its row locked, and the due step is computed again
under the lock, so a step can never fire twice. No step writes timecards, schedule or
leave data, applies a fix or calls the LLM: it only sends the template reminder, changes
who the case waits for, and writes the audit row (actor `system`).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from attendflow.cases import no_reply, service
from attendflow.cases.transitions import check_transition
from attendflow.clock import Clock
from attendflow.config import Settings
from attendflow.db.models import EmployeeRow, ExceptionRow, WorkerMessageRow
from attendflow.errors import AppError, ConflictError

log = logging.getLogger("attendflow.ladder")


def _candidates(session: Session) -> list[str]:
    return list(
        session.scalars(
            select(ExceptionRow.id)
            .where(
                ExceptionRow.auto_resolve_undone_at.is_(None),
                or_(
                    ExceptionRow.status == "awaiting_worker",
                    (ExceptionRow.status == "awaiting_supervisor")
                    & (ExceptionRow.no_reply_stage == no_reply.WITH_SUPERVISOR),
                ),
            )
            .order_by(ExceptionRow.id)
        )
    )


def _latest_question(session: Session, row: ExceptionRow) -> WorkerMessageRow | None:
    return session.scalars(
        select(WorkerMessageRow)
        .where(
            WorkerMessageRow.exception_id == row.id,
            WorkerMessageRow.recipient_id == row.employee_id,
        )
        .order_by(WorkerMessageRow.id.desc())
        .limit(1)
    ).first()


def _remind(session, clock, row, worker, limits, due_at, now) -> dict[str, Any]:
    message = _latest_question(session, row)
    if message is None:
        raise ConflictError("there is no question to remind about", code="no_question")
    text = no_reply.reminder_text(row, limits)
    message.reminded_at = now
    message.reminder_text = text
    row.no_reply_stage = no_reply.REMINDED
    row.no_reply_reminded_at = now
    row.updated_at = now
    since = no_reply.wait_start(row)
    service._audit(
        session,
        clock,
        exception_id=row.id,
        actor="system",
        action="no_reply_reminder",
        before={"no_reply_stage": no_reply.NONE},
        after={
            **service._state(row),
            "no_reply_stage": no_reply.REMINDED,
            "message_id": message.id,
            "wait_since": since.isoformat(),
            "due_at": due_at.isoformat(),
            "fired_at": now.isoformat(),
            "text": text,
        },
        reason=f"{worker.name} has not replied for {no_reply.hours_text(now - since)}; "
        "one reminder sent (template).",
    )
    return {"exception_id": row.id, "message_id": message.id}


def _to_supervisor(session, clock, row, worker, limits, due_at, now) -> dict[str, Any]:
    if not worker.supervisor_id:
        raise ConflictError(f"{worker.employee_id} has no supervisor", code="no_supervisor")
    before = {**service._state(row), "no_reply_stage": row.no_reply_stage}
    check_transition(row.status, "awaiting_supervisor", action="no_reply_to_supervisor")
    service._set_status(row, "awaiting_supervisor", clock, worker.supervisor_id)
    row.no_reply_stage = no_reply.WITH_SUPERVISOR
    row.no_reply_supervisor_at = now
    since = no_reply.wait_start(row)
    hours = no_reply.hours_text(now - since)
    service._audit(
        session,
        clock,
        exception_id=row.id,
        actor="system",
        action="no_reply_to_supervisor",
        before=before,
        after={
            **service._state(row),
            "no_reply_stage": no_reply.WITH_SUPERVISOR,
            "wait_since": since.isoformat(),
            "due_at": due_at.isoformat(),
            "fired_at": now.isoformat(),
            "hours_without_reply": hours,
        },
        reason=f"{worker.name} has not replied for {hours}. The supervisor can ask again, "
        "decide on the evidence, or escalate to payroll. Nothing was changed.",
    )
    return {"exception_id": row.id, "assigned_to": worker.supervisor_id}


def _to_admin(session, clock, row, worker, limits, due_at, now) -> dict[str, Any]:
    admin = service._payroll_admin(session)
    supervisor = session.get(EmployeeRow, row.assigned_to) if row.assigned_to else None
    before = {**service._state(row), "no_reply_stage": row.no_reply_stage}
    check_transition(row.status, "escalated", action="no_reply_to_admin")
    service._set_status(row, "escalated", clock, admin.employee_id)
    row.no_reply_stage = no_reply.WITH_ADMIN
    row.no_reply_admin_at = now
    who = supervisor.name if supervisor else "The supervisor"
    acted_hours = no_reply.hours_text(now - row.no_reply_supervisor_at)
    service._audit(
        session,
        clock,
        exception_id=row.id,
        actor="system",
        action="no_reply_to_admin",
        before=before,
        after={
            **service._state(row),
            "no_reply_stage": no_reply.WITH_ADMIN,
            "supervisor_id": supervisor.employee_id if supervisor else None,
            "supervisor_at": row.no_reply_supervisor_at.isoformat(),
            "due_at": due_at.isoformat(),
            "fired_at": now.isoformat(),
            "hours_without_reply": no_reply.hours_text(now - no_reply.wait_start(row)),
        },
        reason=f"{worker.name} did not reply and {who} has not acted for {acted_hours}. "
        "Sent to payroll with the full history. Nothing was changed.",
    )
    return {"exception_id": row.id, "assigned_to": admin.employee_id}


STEPS = {"remind": _remind, "supervisor": _to_supervisor, "admin": _to_admin}
SUMMARY_KEYS = {"remind": "reminded", "supervisor": "to_supervisor", "admin": "to_admin"}


def step_case(
    session: Session, clock: Clock, limits: no_reply.Limits, exception_id: str
) -> tuple[str, dict[str, Any]] | None:
    """Take the one due step for this case, if any. Its own transaction."""
    with session.begin():
        row = session.get(ExceptionRow, exception_id, with_for_update=True)
        if row is None:
            return None
        now: datetime = clock.now()
        due = no_reply.due_step(row, now, limits)
        if due is None:
            return None
        step, due_at = due
        worker = session.get(EmployeeRow, row.employee_id)
        result = STEPS[step](session, clock, row, worker, limits, due_at, now)
    log.info(
        "no-reply step",
        extra={"event": f"no_reply_{step}", "exception_id": exception_id, "stage": step},
    )
    return step, result


def run_ladder(sessions: sessionmaker[Session], settings: Settings, clock: Clock) -> dict[str, Any]:
    """One pass over every case waiting for a worker (or for a supervisor brought in by
    the ladder). Errors on one case are recorded and the pass goes on."""
    out: dict[str, Any] = {
        "enabled": settings.no_reply_escalation_enabled,
        "reminded": [],
        "to_supervisor": [],
        "to_admin": [],
        "errors": [],
    }
    if not settings.no_reply_escalation_enabled:
        return out
    limits = no_reply.Limits.from_settings(settings)
    with sessions() as session:
        ids = _candidates(session)
    for exception_id in ids:
        try:
            with sessions() as session:
                done = step_case(session, clock, limits, exception_id)
        except Exception as exc:  # noqa: BLE001 - one bad case never stops the pass
            log.exception(
                "no-reply step failed",
                extra={"event": "no_reply_step_failed", "exception_id": exception_id},
            )
            text = f"{exc.code}: {exc.message}" if isinstance(exc, AppError) else type(exc).__name__
            out["errors"].append(
                {"exception_id": exception_id, "step": "no_reply", "error": text[:300]}
            )
            continue
        if done is not None:
            step, _ = done
            out[SUMMARY_KEYS[step]].append(exception_id)
    return out
