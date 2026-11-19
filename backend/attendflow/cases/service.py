"""Case service: detection upsert and every human decision on an exception.

Each public function runs in ONE database transaction (`with session.begin()`): the
status change, any data change from fixes/apply.py and the audit row are saved together
or not at all.

Who may act: the person in `assigned_to` (it always names whose turn it is):
- open / awaiting_supervisor -> the worker's supervisor
- awaiting_worker            -> the worker
- escalated                  -> the payroll admin after a supervisor reject (or the
                                supervisor after a no-reply escalation, Phase 13)
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from attendflow.cases.transitions import WAITING, check_transition
from attendflow.cases.worker_message import generate_worker_message, worker_facts
from attendflow.clock import Clock
from attendflow.config import Settings
from attendflow.db.dataset import load_dataset_from_db
from attendflow.db.models import AuditLogRow, EmployeeRow, ExceptionRow, WorkerMessageRow
from attendflow.engine.engine import run_engine
from attendflow.engine.models import TimecardException
from attendflow.errors import (
    AppError,
    ConflictError,
    ForbiddenError,
    InvalidFixError,
    InvalidTransitionError,
    NotFoundError,
)
from attendflow.fixes.apply import apply_auto_resolve, apply_fix
from attendflow.fixes.params import REQUIRED_NOTE, FixParamsError, params_json, parse_params
from attendflow.policy.models import PolicyConfig

log = logging.getLogger("attendflow.cases")

ROLE_TO_ACTOR = {"worker": "worker", "supervisor": "supervisor", "payroll_admin": "admin"}
# Fields detection refreshes on an open exception.
CONTENT_FIELDS = ("title", "summary", "severity", "kind", "details", "evidence", "fix_options")
FINAL = ("resolved", "rejected")


# ------------------------------------------------------------------ helpers


def _audit(
    session: Session,
    clock: Clock,
    *,
    exception_id: str | None,
    actor: str,
    action: str,
    actor_id: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str | None = None,
) -> AuditLogRow:
    row = AuditLogRow(
        exception_id=exception_id,
        actor=actor,
        actor_id=actor_id,
        action=action,
        before=before,
        after=after,
        reason=reason,
        created_at=clock.now(),
    )
    session.add(row)
    return row


def _state(row: ExceptionRow) -> dict[str, Any]:
    return {
        "status": row.status,
        "assigned_to": row.assigned_to,
        "waiting_since": row.waiting_since.isoformat() if row.waiting_since else None,
    }


def _set_status(row: ExceptionRow, status: str, clock: Clock, assigned_to: str | None) -> None:
    now = clock.now()
    if status != row.status:
        row.waiting_since = now if status in WAITING else None
    row.status = status
    row.assigned_to = assigned_to
    row.updated_at = now


def _get_for_update(session: Session, exception_id: str) -> ExceptionRow:
    row = session.get(ExceptionRow, exception_id, with_for_update=True)
    if row is None:
        raise NotFoundError(f"exception {exception_id} not found", code="exception_not_found")
    return row


def _actor(session: Session, actor_id: str) -> EmployeeRow:
    emp = session.get(EmployeeRow, actor_id)
    if emp is None:
        raise ForbiddenError(f"unknown actor {actor_id}", code="unknown_actor")
    return emp


def _require_assignee(row: ExceptionRow, actor: EmployeeRow, action: str) -> None:
    if row.assigned_to != actor.employee_id:
        owner = row.assigned_to or "nobody"
        raise ForbiddenError(
            f"{actor.employee_id} cannot {action} {row.id}: it is assigned to {owner}",
            code="not_assigned",
            details={"assigned_to": row.assigned_to, "actor_id": actor.employee_id},
        )


def _payroll_admin(session: Session) -> EmployeeRow:
    admin = session.scalars(
        select(EmployeeRow)
        .where(EmployeeRow.role == "payroll_admin")
        .order_by(EmployeeRow.employee_id)
    ).first()
    if admin is None:
        raise ConflictError("no payroll admin in the employee data", code="no_payroll_admin")
    return admin


# ------------------------------------------------------------------ detection


@dataclass
class DetectionSummary:
    as_of: str
    policy_version: str
    found: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    options_added: int = 0
    auto_resolved: int = 0
    closed_no_longer_detected: list[str] = field(default_factory=list)
    by_policy: dict[str, int] = field(default_factory=dict)
    exception_ids: list[str] = field(default_factory=list)


def _content(exc: TimecardException) -> dict[str, Any]:
    data = exc.model_dump(mode="json")
    return {k: data[k] for k in CONTENT_FIELDS}


def _new_row(exc: TimecardException, supervisor_id: str | None, clock: Clock) -> ExceptionRow:
    now = clock.now()
    return ExceptionRow(
        id=exc.exception_id,
        employee_id=exc.employee_id,
        date=exc.date,
        policy_id=exc.policy_id,
        status="open",
        auto_resolved=False,
        proposed_fix=None,
        applied_fix=None,
        assigned_to=supervisor_id,
        waiting_since=None,
        last_detected_at=now,
        created_at=now,
        updated_at=now,
        **_content(exc),
    )


def run_detection(session: Session, policy: PolicyConfig, clock: Clock) -> DetectionSummary:
    """Run the rule engine on the database and upsert exceptions by their stable ID.

    - New exception -> inserted as open, assigned to the worker's supervisor. If the engine
      auto-resolved it (policy.json auto_resolve), it is stored as resolved with
      auto_resolved=true and its data change applied, all audit-logged.
    - Still open -> numbers refreshed (audit row only if something changed).
    - In progress, resolved or rejected -> left alone (a human is on it or has decided).
    - Open but no longer found -> resolved by the system ("no longer detected").
    """
    with session.begin():
        ds = load_dataset_from_db(session)
        if not ds.employees:
            raise ConflictError("no data loaded: call POST /api/seed first", code="not_seeded")
        as_of = clock.now()
        result = run_engine(ds, policy, as_of)
        supervisors = {e.employee_id: e.supervisor_id for e in ds.employees}
        existing = {r.id: r for r in session.scalars(select(ExceptionRow).with_for_update()).all()}
        summary = DetectionSummary(
            as_of=as_of.isoformat(timespec="seconds"),
            policy_version=result.policy_version,
            found=len(result.exceptions),
            by_policy=dict(
                sorted(
                    Counter(e.policy_id for e in result.exceptions).items(),
                    key=lambda kv: int(kv[0][1:]),
                )
            ),
            exception_ids=[e.exception_id for e in result.exceptions],
        )

        for exc in result.exceptions:
            row = existing.pop(exc.exception_id, None)
            if row is None:
                row = _new_row(exc, supervisors.get(exc.employee_id), clock)
                session.add(row)
                session.flush()
                summary.created += 1
                _audit(
                    session,
                    clock,
                    exception_id=row.id,
                    actor="system",
                    action="detected",
                    after={
                        **_state(row),
                        "severity": row.severity,
                        "kind": row.kind,
                        "summary": row.summary,
                    },
                )
                if exc.status == "auto_resolved":
                    _auto_resolve(session, row, policy, clock)
                    summary.auto_resolved += 1
                continue

            row.last_detected_at = clock.now()
            if row.status != "open":
                if row.status not in FINAL and not row.fix_options and exc.fix_options:
                    _add_options(session, row, exc, clock)
                    summary.options_added += 1
                else:
                    summary.unchanged += 1
                continue
            new = _content(exc)
            changed = {k: v for k, v in new.items() if getattr(row, k) != v}
            if not changed:
                summary.unchanged += 1
                continue
            before = {k: getattr(row, k) for k in changed}
            for k, v in changed.items():
                setattr(row, k, v)
            row.updated_at = clock.now()
            summary.updated += 1
            _audit(
                session,
                clock,
                exception_id=row.id,
                actor="system",
                action="updated_by_detection",
                before=before,
                after=changed,
            )

        for row in existing.values():  # stored but not found this time
            if row.status != "open":
                continue
            before = _state(row)
            check_transition(row.status, "resolved", action="close")
            _set_status(row, "resolved", clock, row.assigned_to)
            summary.closed_no_longer_detected.append(row.id)
            _audit(
                session,
                clock,
                exception_id=row.id,
                actor="system",
                action="no_longer_detected",
                before=before,
                after=_state(row),
                reason="Detection no longer finds this exception (the data was corrected).",
            )
    log.info(
        "detection run",
        extra={
            "event": "detection_run",
            "found": summary.found,
            "new": summary.created,
            "updated": summary.updated,
            "auto_resolved": summary.auto_resolved,
            "closed": len(summary.closed_no_longer_detected),
        },
    )
    return summary


def _add_options(session: Session, row: ExceptionRow, exc: TimecardException, clock: Clock) -> None:
    """A case a human is already working on, created before its policy had fix options
    (Phase 4 added them for P3, P4, P6, P7): add the options only. Status, assignee and
    the numbers the human has seen are left alone."""
    row.fix_options = _content(exc)["fix_options"]
    row.updated_at = clock.now()
    _audit(
        session,
        clock,
        exception_id=row.id,
        actor="system",
        action="options_added",
        after={"fix_options": [o["option_id"] for o in row.fix_options]},
        reason="Fix options for this policy were added after the case was opened.",
    )


def _require_worker_confirmation(session: Session, row: ExceptionRow, option: dict) -> None:
    """Options flagged requires_worker_confirmation (policy: the worker confirms first) can
    only be approved after the worker's latest reply on this case said Yes."""
    if not option.get("requires_worker_confirmation"):
        return
    reply = session.scalars(
        select(AuditLogRow)
        .where(AuditLogRow.exception_id == row.id, AuditLogRow.action == "worker_reply")
        .order_by(AuditLogRow.id.desc())
    ).first()
    if reply is None or not (reply.after or {}).get("confirmed"):
        raise ConflictError(
            f"{option['option_id']} needs the worker to confirm first: ask the worker, "
            "then approve after they reply Yes",
            code="worker_not_confirmed",
            details={"worker_replied": reply is not None},
        )


def _auto_resolve(session: Session, row: ExceptionRow, policy: PolicyConfig, clock: Clock) -> None:
    before = _state(row)
    changes = apply_auto_resolve(session, row, policy, clock.now())
    check_transition(row.status, "resolved", action="auto_resolve")
    _set_status(row, "resolved", clock, row.assigned_to)
    row.auto_resolved = True
    row.applied_fix = {"action": "auto_resolve", "policy_id": row.policy_id, "changes": changes}
    _audit(
        session,
        clock,
        exception_id=row.id,
        actor="system",
        action="auto_resolve",
        before=before,
        after={**_state(row), "changes": changes},
        reason=f"{row.policy_id} is set to auto_resolve in policy.json (low risk).",
    )


# ------------------------------------------------------------------ decisions


def _find_option(row: ExceptionRow, option_id: str) -> dict[str, Any]:
    if not row.fix_options:
        raise ConflictError(
            f"{row.id} has no fix options yet ({row.policy_id}); it can only be rejected",
            code="no_fix_options",
        )
    for opt in row.fix_options:
        if opt["option_id"] == option_id:
            return opt
    raise InvalidFixError(
        f"{row.id} has no fix option {option_id!r}",
        code="unknown_option",
        details={"available": [o["option_id"] for o in row.fix_options]},
    )


def approve(
    session: Session,
    policy: PolicyConfig,
    clock: Clock,
    *,
    exception_id: str,
    actor_id: str,
    option_id: str,
    reason: str | None = None,
    params: dict[str, Any] | None = None,
) -> ExceptionRow:
    """Approve one fix option (edit = approve with changed params). Applies the data change,
    resolves the exception and writes the audit row in one transaction."""
    edited = params is not None
    action_name = "edit" if edited else "approve"
    with session.begin():
        row = _get_for_update(session, exception_id)
        actor = _actor(session, actor_id)
        check_transition(row.status, "resolved", action=action_name)
        _require_assignee(row, actor, action_name)
        option = _find_option(row, option_id)
        _require_worker_confirmation(session, row, option)

        merged = {**option["params"], **(params or {})}
        note_key = REQUIRED_NOTE.get(option["action"])
        if note_key and not str(merged.get(note_key) or "").strip() and reason:
            merged[note_key] = reason.strip()
        try:
            parsed = parse_params(option["action"], option["params"], merged)
        except FixParamsError as exc:
            raise InvalidFixError(str(exc), code="invalid_params", details=exc.errors) from exc

        before = _state(row)
        changes = apply_fix(session, row, option["action"], parsed, policy, clock.now())
        _set_status(row, "resolved", clock, row.assigned_to)
        row.applied_fix = {
            "option_id": option_id,
            "action": option["action"],
            "label": option["label"],
            "params": params_json(parsed),
            "edited": edited,
            "changes": changes,
            "approved_by": actor.employee_id,
        }
        _audit(
            session,
            clock,
            exception_id=row.id,
            actor=ROLE_TO_ACTOR[actor.role],
            actor_id=actor.employee_id,
            action="edit_and_approve" if edited else "approve",
            before=before,
            after={**_state(row), "applied_fix": row.applied_fix},
            reason=reason,
        )
    log.info(
        "fix approved",
        extra={
            "event": action_name,
            "exception_id": exception_id,
            "actor_id": actor_id,
            "option_id": option_id,
            "data_changes": len(changes),
        },
    )
    return row


def reject(
    session: Session, clock: Clock, *, exception_id: str, actor_id: str, reason: str
) -> ExceptionRow:
    """Supervisor reject -> escalated to the payroll admin. Assignee's reject of an
    escalated case -> rejected (final). No data changes either way."""
    with session.begin():
        row = _get_for_update(session, exception_id)
        actor = _actor(session, actor_id)
        target = "rejected" if row.status == "escalated" else "escalated"
        check_transition(row.status, target, action="reject")
        _require_assignee(row, actor, "reject")
        before = _state(row)
        if target == "escalated":
            admin = _payroll_admin(session)
            _set_status(row, "escalated", clock, admin.employee_id)
            action = "reject_and_escalate"
        else:
            _set_status(row, "rejected", clock, row.assigned_to)
            action = "reject"
        _audit(
            session,
            clock,
            exception_id=row.id,
            actor=ROLE_TO_ACTOR[actor.role],
            actor_id=actor.employee_id,
            action=action,
            before=before,
            after=_state(row),
            reason=reason,
        )
    log.info(
        "exception rejected",
        extra={
            "event": action,
            "exception_id": exception_id,
            "actor_id": actor_id,
            "status": row.status,
        },
    )
    return row


def _worker_handoff(session: Session, row: ExceptionRow, actor_id: str) -> EmployeeRow:
    actor = _actor(session, actor_id)
    check_transition(row.status, "awaiting_worker", action="ask_worker")
    _require_assignee(row, actor, "ask the worker about")
    investigation = row.investigation_case
    if investigation is None:
        raise ConflictError(
            "investigate the case before asking the worker", code="investigation_required"
        )
    if investigation.get("who_to_ask") != "worker":
        raise ConflictError(
            "the investigation routes to someone else", code="worker_not_next_contact"
        )
    return _actor(session, row.employee_id)


def ask_worker(
    session: Session,
    clock: Clock,
    settings: Settings,
    *,
    exception_id: str,
    actor_id: str,
    note: str | None = None,
) -> ExceptionRow:
    """Phrase a verified question and save it with the worker handoff."""
    with session.begin():
        row = session.get(ExceptionRow, exception_id)
        if row is None:
            raise NotFoundError(f"exception {exception_id} not found", code="exception_not_found")
        worker = _worker_handoff(session, row, actor_id)
        facts = worker_facts(row, worker)
        investigation = row.investigation_case
    draft = generate_worker_message(settings, facts)

    with session.begin():
        row = _get_for_update(session, exception_id)
        worker = _worker_handoff(session, row, actor_id)
        if row.investigation_case != investigation or worker_facts(row, worker) != facts:
            raise ConflictError(
                "the case changed while preparing the question", code="case_changed"
            )
        before = _state(row)
        _set_status(row, "awaiting_worker", clock, row.employee_id)
        message = WorkerMessageRow(
            exception_id=row.id,
            recipient_id=row.employee_id,
            date=row.date,
            message=draft.text,
            source=draft.source,
            reply_prompt=facts.reply_prompt,
            sent_at=clock.now(),
        )
        session.add(message)
        session.flush()
        _audit(
            session,
            clock,
            exception_id=row.id,
            actor=ROLE_TO_ACTOR[_actor(session, actor_id).role],
            actor_id=actor_id,
            action="ask_worker",
            before=before,
            after=_state(row),
            reason=note,
        )
        _audit(
            session,
            clock,
            exception_id=row.id,
            actor="agent" if draft.source == "llm" else "system",
            action="worker_message_sent",
            after={
                "message_id": message.id,
                "source": draft.source,
                "duration_ms": draft.duration_ms,
            },
            reason=draft.diagnostic,
        )
    return row


def worker_inbox(session: Session, actor_id: str) -> list[WorkerMessageRow]:
    actor = _actor(session, actor_id)
    if actor.role != "worker":
        raise ForbiddenError("only a worker can read their inbox", code="worker_inbox_only")
    latest_per_case = (
        select(func.max(WorkerMessageRow.id))
        .where(WorkerMessageRow.recipient_id == actor_id)
        .group_by(WorkerMessageRow.exception_id)
        .correlate(None)
    )
    return list(
        session.scalars(
            select(WorkerMessageRow)
            .join(ExceptionRow, WorkerMessageRow.exception_id == ExceptionRow.id)
            .where(
                WorkerMessageRow.id.in_(latest_per_case),
                WorkerMessageRow.confirmed.is_not(True),
                ExceptionRow.employee_id == actor_id,
                ExceptionRow.assigned_to == actor_id,
                ExceptionRow.status == "awaiting_worker",
            )
            .order_by(WorkerMessageRow.date, WorkerMessageRow.id)
        )
    )


def worker_reply(
    session: Session,
    clock: Clock,
    *,
    exception_id: str,
    actor_id: str,
    confirmed: bool,
    text: str | None,
) -> WorkerMessageRow:
    """Yes routes to a supervisor. No stays with the worker for Phase 8."""
    if not confirmed and not (text or "").strip():
        raise AppError("tell us what happened when answering No", code="reply_text_required")
    with session.begin():
        actor = _actor(session, actor_id)
        row = session.get(ExceptionRow, exception_id, with_for_update=True)
        if row is None or actor.role != "worker" or actor_id != row.employee_id:
            raise ForbiddenError(
                "only the recipient can reply to this question", code="not_the_worker"
            )
        if row.status != "awaiting_worker":
            raise InvalidTransitionError(
                f"worker_reply: {row.id} is {row.status}, not waiting for the worker",
                details={
                    "from": row.status,
                    "to": "awaiting_supervisor",
                    "allowed": ["awaiting_worker"],
                },
            )
        _require_assignee(row, actor, "reply to")
        message = session.scalar(
            select(WorkerMessageRow)
            .where(
                WorkerMessageRow.exception_id == row.id, WorkerMessageRow.recipient_id == actor_id
            )
            .order_by(WorkerMessageRow.id.desc())
            .limit(1)
        )
        if message is None or message.replied_at is not None:
            raise ConflictError("there is no unanswered question", code="no_open_worker_question")

        before = _state(row)
        if confirmed:
            check_transition(row.status, "awaiting_supervisor", action="worker_reply")
            _set_status(row, "awaiting_supervisor", clock, actor.supervisor_id)
        else:
            row.updated_at = clock.now()
        message.confirmed = confirmed
        message.reply_text = text
        message.replied_at = clock.now()
        message.needs_actual_time = not confirmed
        _audit(
            session,
            clock,
            exception_id=row.id,
            actor="worker",
            actor_id=actor.employee_id,
            action="worker_reply",
            before=before,
            after={
                **_state(row),
                "confirmed": confirmed,
                "text": text,
                "needs_actual_time": message.needs_actual_time,
                "message_id": message.id,
            },
        )
    return message
