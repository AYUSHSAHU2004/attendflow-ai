"""Case service: detection upsert and every human decision on an exception.

Each public function runs in ONE database transaction (`with session.begin()`): the
status change, any data change from fixes/apply.py and the audit row are saved together
or not at all.

Who may act: the person in `assigned_to` (it always names whose turn it is):
- open / awaiting_supervisor -> the worker's supervisor
- awaiting_worker            -> the worker
- escalated                  -> the payroll admin (after a supervisor reject or escalate,
                                or the no-reply ladder, Phase 13)

Two times (Phase 13, clock.py): rows are stamped with clock.now(); every data cut-off
(detection, fixes, worker time checks) uses data_as_of(clock), which never moves.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from attendflow.cases import no_reply, time_extraction, time_review
from attendflow.cases.facts import CONTENT_FIELDS
from attendflow.cases.supervisor import require_reviewer, time_label
from attendflow.cases.transitions import WAITING, check_transition
from attendflow.cases.worker_message import (
    generate_worker_message,
    validate_worker_message,
    worker_facts,
)
from attendflow.clock import Clock, data_as_of
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
from attendflow.fixes.apply import apply_auto_resolve, apply_fix, punches_fixed_by_others
from attendflow.fixes.apply import undo_auto_resolve as apply_undo
from attendflow.fixes.params import REQUIRED_NOTE, FixParamsError, params_json, parse_params
from attendflow.policy.models import PolicyConfig

log = logging.getLogger("attendflow.cases")

ROLE_TO_ACTOR = {"worker": "worker", "supervisor": "supervisor", "payroll_admin": "admin"}
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
    auto_resolve_held: int = 0
    closed_no_longer_detected: list[str] = field(default_factory=list)
    by_policy: dict[str, int] = field(default_factory=dict)
    exception_ids: list[str] = field(default_factory=list)
    created_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DetectionScope:
    """Limit a detection run's writes to one worker's dates (the engine still runs on all
    data, which is cheap). Used after a device punch."""

    employee_id: str
    start: date
    end: date

    def covers(self, employee_id: str, day: date) -> bool:
        return employee_id == self.employee_id and self.start <= day <= self.end


def punch_scope(employee_id: str, stamp: datetime) -> DetectionScope:
    """The Mon-Sun week of a punch. A punch after midnight can belong to the previous
    day's night shift (P15), so the scope starts at the week of the day before."""
    day = stamp.date()
    start = day - timedelta(days=1)
    start -= timedelta(days=start.weekday())
    end = day + timedelta(days=6 - day.weekday())
    return DetectionScope(employee_id, start, end)


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


def run_detection(
    session: Session,
    policy: PolicyConfig,
    clock: Clock,
    scope: DetectionScope | None = None,
    *,
    auto_resolve: bool = True,
) -> DetectionSummary:
    """Run the rule engine on the database and upsert exceptions by their stable ID.

    With a `scope`, only that worker's exceptions dated inside it are created, refreshed or
    closed; everything else is left for the next full run. `auto_resolve` is the
    AUTO_RESOLVE_ENABLED kill switch.

    - New exception -> inserted as open, assigned to the worker's supervisor. If the engine
      allows auto-resolve (P2/P7 only, engine/auto_resolve.py) and the kill switch is on,
      it is stored as resolved with auto_resolved=true and its data change applied
      through fixes/apply.py, all audit-logged. A candidate the engine or the kill switch
      holds stays open with an `auto_resolve_held` audit row saying why. Only NEW rows are
      ever auto-resolved, so an undone case (same stable ID) never is again.
    - Still open -> numbers refreshed (audit row only if something changed).
    - In progress, resolved or rejected -> left alone (a human is on it or has decided).
    - Open but no longer found -> resolved by the system ("no longer detected").
    """
    with session.begin():
        ds = load_dataset_from_db(session)
        if not ds.employees:
            raise ConflictError("no data loaded: call POST /api/seed first", code="not_seeded")
        as_of = data_as_of(clock)
        result = run_engine(ds, policy, as_of)
        found = [
            e for e in result.exceptions if scope is None or scope.covers(e.employee_id, e.date)
        ]
        supervisors = {e.employee_id: e.supervisor_id for e in ds.employees}
        stmt = select(ExceptionRow).with_for_update()
        if scope is not None:
            stmt = stmt.where(
                ExceptionRow.employee_id == scope.employee_id,
                ExceptionRow.date.between(scope.start, scope.end),
            )
        existing = {r.id: r for r in session.scalars(stmt).all()}
        summary = DetectionSummary(
            as_of=as_of.isoformat(timespec="seconds"),
            policy_version=result.policy_version,
            found=len(found),
            by_policy=dict(
                sorted(
                    Counter(e.policy_id for e in found).items(),
                    key=lambda kv: int(kv[0][1:]),
                )
            ),
            exception_ids=[e.exception_id for e in found],
        )

        for exc in found:
            row = existing.pop(exc.exception_id, None)
            if row is None:
                row = _new_row(exc, supervisors.get(exc.employee_id), clock)
                session.add(row)
                session.flush()
                summary.created += 1
                summary.created_ids.append(row.id)
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
                if exc.status == "auto_resolved" and auto_resolve:
                    _auto_resolve(session, row, policy, clock)
                    summary.auto_resolved += 1
                elif "auto_resolve" in exc.details:
                    held = list(exc.details["auto_resolve"].get("held_because") or [])
                    if exc.status == "auto_resolved":
                        held = ["auto-resolve is switched off (AUTO_RESOLVE_ENABLED=false)"]
                    _audit(
                        session,
                        clock,
                        exception_id=row.id,
                        actor="system",
                        action="auto_resolve_held",
                        after={"policy_id": row.policy_id, "held_because": held},
                        reason="Not auto-resolved: " + "; ".join(held) + ".",
                    )
                    summary.auto_resolve_held += 1
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
    """Require a confirmed time record for P1 and confirmation for other flagged options."""
    reviewed = (row.worker_recheck or {}).get("proposed_fix") or {}
    if reviewed.get("option_id") == option["option_id"]:
        return
    if row.policy_id == "P1":
        raise ConflictError(
            "the worker must confirm the punch time first", code="worker_not_confirmed"
        )
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
    if row.auto_resolve_undone_at is not None:  # belt and braces: never re-close an undone case
        raise ConflictError(f"{row.id} was undone by a person", code="auto_resolve_undone")
    before = _state(row)
    basis = (row.details.get("auto_resolve") or {}).get("basis")
    fix = apply_auto_resolve(session, row, policy, data_as_of(clock))
    check_transition(row.status, "resolved", action="auto_resolve")
    _set_status(row, "resolved", clock, row.assigned_to)
    row.auto_resolved = True
    row.applied_fix = {**fix, "basis": basis}
    _audit(
        session,
        clock,
        exception_id=row.id,
        actor="system",
        action="auto_resolve",
        before=before,
        after={
            **_state(row),
            "policy_id": row.policy_id,
            "basis": basis,
            "changes": fix["changes"],
            "guarded_rows": fix["guarded_rows"],
        },
        reason=f"{row.policy_id} may auto-resolve (policy.json) and the engine's numbers are "
        f"within policy: {basis}.",
    )


# ------------------------------------------------------------------ undo (Phase 12)

# Audit actions whose `after` lists data changes (approve/edit in applied_fix.changes).
DATA_CHANGE_ACTIONS = ("approve", "edit_and_approve", "auto_resolve", "auto_resolve_undone")


def require_undo_permission(session: Session, row: ExceptionRow, actor: EmployeeRow) -> None:
    """The payroll admin may undo any case; a supervisor only their own team's."""
    if actor.role == "payroll_admin":
        return
    worker = session.get(EmployeeRow, row.employee_id)
    if worker is None or worker.supervisor_id != actor.employee_id:
        raise ForbiddenError(
            f"{actor.employee_id} cannot undo {row.id}: {row.employee_id} is not on their team",
            code="not_assigned",
            details={"supervisor_id": worker.supervisor_id if worker else None},
        )


def _later_fix_conflicts(session: Session, row: ExceptionRow) -> list[dict[str, Any]]:
    """Another case's audited fix touched this worker's punches on the same shift date
    (the day and the next morning, as for corrections) after this auto-resolve."""
    since = session.scalar(
        select(func.max(AuditLogRow.id)).where(
            AuditLogRow.exception_id == row.id, AuditLogRow.action == "auto_resolve"
        )
    )
    owners = punches_fixed_by_others(session, row)
    if not owners or since is None:
        return []
    later = session.scalars(
        select(AuditLogRow.exception_id)
        .where(
            AuditLogRow.id > since,
            AuditLogRow.exception_id.in_(owners),
            AuditLogRow.action.in_(DATA_CHANGE_ACTIONS),
        )
        .distinct()
    ).all()
    return [{"exception_id": eid, "punch_ids": sorted(owners[eid])} for eid in sorted(later)]


def undo_auto_resolve(
    session: Session,
    policy: PolicyConfig,
    clock: Clock,
    *,
    exception_id: str,
    actor_id: str,
    reason: str,
) -> tuple[ExceptionRow, list[dict[str, Any]]]:
    """A person undoes an auto-resolved case: the rows go back to their "before" snapshot
    (through fixes/apply.py), the case is open again with the worker's supervisor, and it is
    marked so it is never auto-resolved or auto-handled by the scheduler again.

    Refused with 409 `undo_conflict` (or `undo_unavailable`) when the data changed since;
    then nothing changes except one `undo_refused` audit row in its own transaction."""
    try:
        with session.begin():
            actor = require_reviewer(session, actor_id)
            row = _get_for_update(session, exception_id)
            require_undo_permission(session, row, actor)
            if row.auto_resolve_undone_at is not None:
                raise ConflictError(
                    f"{row.id} was already undone; it is decided by people now",
                    code="already_undone",
                )
            if not row.auto_resolved:
                raise ConflictError(f"{row.id} was not auto-resolved", code="not_auto_resolved")
            check_transition(row.status, "open", action="undo")
            undone_fix = row.applied_fix
            if (undone_fix or {}).get("changes"):
                later = _later_fix_conflicts(session, row)
                if later:
                    raise ConflictError(
                        "another case's fix changed this worker's punches on that day after "
                        "the auto-resolve; decide this case by hand instead",
                        code="undo_conflict",
                        details={"later_fixes": later},
                    )
            changes = apply_undo(session, row, policy, data_as_of(clock))
            before = _state(row)
            worker = session.get(EmployeeRow, row.employee_id)
            _set_status(row, "open", clock, worker.supervisor_id if worker else row.assigned_to)
            row.auto_resolved = False
            row.applied_fix = None
            row.auto_resolve_undone_at = clock.now()
            row.auto_resolve_undone_by = actor.employee_id
            _audit(
                session,
                clock,
                exception_id=row.id,
                actor=ROLE_TO_ACTOR[actor.role],
                actor_id=actor.employee_id,
                action="auto_resolve_undone",
                before={**before, "applied_fix": undone_fix},
                after={**_state(row), "policy_id": row.policy_id, "changes": changes},
                reason=reason,
            )
    except ConflictError as exc:
        if exc.code in ("undo_conflict", "undo_unavailable"):
            _audit_refused_undo(session, clock, exception_id, actor_id, reason, exc)
        raise
    log.info(
        "auto-resolve undone",
        extra={
            "event": "auto_resolve_undone",
            "exception_id": exception_id,
            "actor_id": actor_id,
            "data_changes": len(changes),
        },
    )
    return row, changes


def _audit_refused_undo(
    session: Session, clock: Clock, exception_id: str, actor_id: str, reason: str, exc: AppError
) -> None:
    try:
        with session.begin():
            actor = session.get(EmployeeRow, actor_id)
            _audit(
                session,
                clock,
                exception_id=exception_id,
                actor=ROLE_TO_ACTOR.get(actor.role, "system") if actor else "system",
                actor_id=actor_id,
                action="undo_refused",
                after={"code": exc.code, "message": exc.message, "details": exc.details},
                reason=reason,
            )
    except Exception:  # noqa: BLE001 - the refusal itself must still reach the caller
        log.exception("could not audit the refused undo")


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


MIN_WITHOUT_WORKER_REASON = 10


def _without_worker_check(
    row: ExceptionRow, option: dict, reason: str | None, confirm_time: bool
) -> dict[str, Any]:
    """Phase 13: deciding without the worker is allowed only after the ladder brought a
    reviewer in (stage 2 or 3), with a reason, and with an explicit tick for a time."""
    stage = row.no_reply_stage or no_reply.NONE
    if stage < no_reply.WITH_SUPERVISOR:
        raise ConflictError(
            "deciding without the worker is possible only after the worker missed the reply "
            "deadline and the case came to you",
            code="no_reply_not_escalated",
            details={"no_reply_stage": stage},
        )
    text = (reason or "").strip()
    if len(text) < MIN_WITHOUT_WORKER_REASON:
        raise InvalidFixError(
            f"give a reason of at least {MIN_WITHOUT_WORKER_REASON} characters for deciding "
            "without the worker",
            code="reason_required",
        )
    if option["action"] in time_review.TIME_ACTIONS and not confirm_time:
        raise InvalidFixError(
            "tick “I'm confirming this time without the worker's reply” to set a punch time",
            code="time_confirmation_required",
        )
    return {
        "reason": text,
        "no_reply_stage": stage,
        "hours_without_reply": no_reply.hours_text(
            (row.no_reply_admin_at or row.no_reply_supervisor_at) - no_reply.wait_start(row)
        )
        if row.no_reply_supervisor_at and no_reply.wait_start(row)
        else None,
        "time": None,
        "time_source": None,
    }


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
    without_worker: bool = False,
    confirm_time_without_worker: bool = False,
) -> ExceptionRow:
    """Approve one fix option (edit = approve with changed params). Applies the data change,
    resolves the exception and writes the audit row in one transaction.

    `without_worker` (Phase 13): decide on the evidence after the worker missed the reply
    deadline (no-reply stage 2 or 3 only). It needs a reason of MIN_WITHOUT_WORKER_REASON+
    characters; an option that sets a punch time also needs `confirm_time_without_worker`.
    The worker-confirmation check is skipped, never the time validation, and the fix is
    still applied by fixes/apply.py. Audited as its own `decided_without_worker` row."""
    edited = params is not None
    action_name = "edit" if edited else "approve"
    with session.begin():
        actor = require_reviewer(session, actor_id)
        row = _get_for_update(session, exception_id)
        check_transition(row.status, "resolved", action=action_name)
        _require_assignee(row, actor, action_name)
        option = _find_option(row, option_id)
        reviewed = (row.worker_recheck or {}).get("proposed_fix") or {}
        confirmed_params = (
            reviewed.get("params") if reviewed.get("option_id") == option_id else None
        )
        default_params = confirmed_params if confirmed_params is not None else option["params"]
        merged = {**default_params, **(params or {})}
        note_key = REQUIRED_NOTE.get(option["action"])
        if note_key and not str(merged.get(note_key) or "").strip() and reason:
            merged[note_key] = reason.strip()
        try:
            parsed = parse_params(option["action"], option["params"], merged)
        except FixParamsError as exc:
            raise InvalidFixError(str(exc), code="invalid_params", details=exc.errors) from exc

        without = None
        if without_worker:
            without = _without_worker_check(row, option, reason, confirm_time_without_worker)
            stamp = params_json(parsed).get("timestamp")
            if option["action"] in time_review.TIME_ACTIONS and stamp:
                without["time"] = stamp
                prefilled = (default_params or {}).get("timestamp")
                same = bool(prefilled) and datetime.fromisoformat(
                    str(prefilled)
                ) == datetime.fromisoformat(str(stamp))
                without["time_source"] = "prefilled" if same else "edited"
        if row.policy_id == "P1" and option["action"] == "set_clock_out" and (edited or without):
            proposed_stamp = datetime.fromisoformat(params_json(parsed)["timestamp"])
            ctx = time_review.context(session, row, policy, data_as_of(clock))
            if proposed_stamp > data_as_of(clock):
                raise InvalidFixError("the punch time is in the future", code="punch_in_future")
            if ctx is not None:
                try:
                    ctx.resolve(proposed_stamp.strftime("%H:%M"), proposed_stamp.date())
                except ValueError as exc:
                    raise InvalidFixError(str(exc), code="punch_outside_shift") from None
        if without is None:
            _require_worker_confirmation(session, row, option)
        if row.policy_id == "P1" and confirmed_params is not None:
            # Phase 8: a P1 time is approved as the worker confirmed it; a new time needs
            # the worker again. (P3 corrections may still be edited after a Yes.)
            if params_json(parsed).get("timestamp") != confirmed_params.get("timestamp"):
                raise ConflictError(
                    "the worker must confirm the changed punch time",
                    code="worker_not_confirmed",
                    details={"confirmed_timestamp": confirmed_params.get("timestamp")},
                )
        before = {**_state(row), "option_id": option_id, "params": default_params}
        changes = apply_fix(session, row, option["action"], parsed, policy, data_as_of(clock))
        _set_status(row, "resolved", clock, row.assigned_to)
        row.applied_fix = {
            "option_id": option_id,
            "action": option["action"],
            "label": time_label(option, params_json(parsed)),
            "params": params_json(parsed),
            "edited": edited,
            "changes": changes,
            "approved_by": actor.employee_id,
            "params_before": default_params,
        }
        if without is not None:
            without["decided_at"] = clock.now().isoformat()
            row.applied_fix["without_worker"] = without
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
        if without is not None:
            _audit(
                session,
                clock,
                exception_id=row.id,
                actor=ROLE_TO_ACTOR[actor.role],
                actor_id=actor.employee_id,
                action="decided_without_worker",
                after={"option_id": option_id, **without},
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


def detect_after_fix(
    session: Session,
    policy: PolicyConfig,
    clock: Clock,
    exception_id: str,
    *,
    auto_resolve: bool = True,
    changed: bool | None = None,
    after: str = "fix",
) -> dict[str, Any]:
    """After an approved fix (or an undo, `after="undo"`) that changed data: run detection
    so that exceptions the change created appear as new open cases. Runs in its own
    transaction, after the decision was saved. Detection upserts by stable ID, so it never
    duplicates a case. If it fails, the decision stands and the next detection run picks
    the change up. `changed` overrides the "did it change data" test (undo clears
    applied_fix, so the caller says)."""
    with session.begin():
        row = session.get(ExceptionRow, exception_id)
        if changed is None:
            changed = bool(row and (row.applied_fix or {}).get("changes"))
        employee_id = row.employee_id if row else None
    if not changed:
        return {"ran": False, "new_exception_ids": [], "closed_exception_ids": [], "error": None}
    try:
        summary = run_detection(session, policy, clock, auto_resolve=auto_resolve)
    except Exception as exc:  # noqa: BLE001 - detection must never undo an approval
        log.exception(
            f"detection after {after} failed",
            extra={"event": f"post_{after}_detection_failed", "exception_id": exception_id},
        )
        message = (
            f"Detection did not run after the {after}; the next detection run will pick it up."
        )
        try:
            with session.begin():
                _audit(
                    session,
                    clock,
                    exception_id=exception_id,
                    actor="system",
                    action=f"post_{after}_detection_failed",
                    reason=f"{message} ({type(exc).__name__})",
                )
        except Exception:  # noqa: BLE001
            log.exception("could not audit the failed detection run")
        return {
            "ran": False,
            "new_exception_ids": [],
            "closed_exception_ids": [],
            "error": message,
        }
    with session.begin():
        ids = summary.created_ids + summary.closed_no_longer_detected
        owners = dict(
            session.execute(
                select(ExceptionRow.id, ExceptionRow.employee_id).where(ExceptionRow.id.in_(ids))
            ).all()
        )
        new_ids = [i for i in summary.created_ids if owners.get(i) == employee_id]
        closed = [i for i in summary.closed_no_longer_detected if owners.get(i) == employee_id]
        _audit(
            session,
            clock,
            exception_id=exception_id,
            actor="system",
            action=f"post_{after}_detection",
            after={"new_exception_ids": new_ids, "closed_exception_ids": closed},
            reason=(
                "Detection re-ran after the approved fix changed data."
                if after == "fix"
                else f"Detection re-ran after the {after} changed data."
            ),
        )
    return {
        "ran": True,
        "new_exception_ids": new_ids,
        "closed_exception_ids": closed,
        "error": None,
    }


def detect_after_punch(
    session: Session,
    policy: PolicyConfig,
    clock: Clock,
    punch: dict[str, Any],
    *,
    auto_resolve: bool = True,
) -> dict[str, Any]:
    """After a device punch was stored: detection for that worker's week, in its own
    transaction. The punch is already committed; if detection fails it stays, the failure
    is logged and audited, and the next full run (or scheduler cycle) picks it up."""
    stamp = datetime.fromisoformat(punch["timestamp"])
    scope = punch_scope(punch["employee_id"], stamp)
    scope_out = {
        "employee_id": scope.employee_id,
        "start": scope.start.isoformat(),
        "end": scope.end.isoformat(),
    }
    try:
        summary = run_detection(session, policy, clock, scope, auto_resolve=auto_resolve)
    except Exception as exc:  # noqa: BLE001 - detection must never lose the punch
        log.exception(
            "detection after punch failed",
            extra={"event": "post_punch_detection_failed", "punch_id": punch["punch_id"]},
        )
        message = "Detection did not run after the punch; the next run will pick it up."
        try:
            with session.begin():
                _audit(
                    session,
                    clock,
                    exception_id=None,
                    actor="system",
                    action="post_punch_detection_failed",
                    after={"punch_id": punch["punch_id"], "scope": scope_out},
                    reason=f"{message} ({type(exc).__name__})",
                )
        except Exception:  # noqa: BLE001
            log.exception("could not audit the failed detection run")
        return {
            "ran": False,
            "scope": scope_out,
            "new_exception_ids": [],
            "closed_exception_ids": [],
            "updated": 0,
            "error": message,
        }
    result = {
        "ran": True,
        "scope": scope_out,
        "new_exception_ids": summary.created_ids,
        "closed_exception_ids": summary.closed_no_longer_detected,
        "updated": summary.updated,
        "error": None,
    }
    with session.begin():
        _audit(
            session,
            clock,
            exception_id=None,
            actor="system",
            action="post_punch_detection",
            after={"punch_id": punch["punch_id"], **result},
            reason="Detection re-ran for the worker's week after a device punch.",
        )
    return result


def reject(
    session: Session, clock: Clock, *, exception_id: str, actor_id: str, reason: str
) -> ExceptionRow:
    """Supervisor reject -> escalated to the payroll admin. Assignee's reject of an
    escalated case -> rejected (final). No data changes either way."""
    with session.begin():
        actor = require_reviewer(session, actor_id)
        row = _get_for_update(session, exception_id)
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


MIN_ESCALATE_REASON = 10


def escalate(
    session: Session, clock: Clock, *, exception_id: str, actor_id: str, reason: str
) -> ExceptionRow:
    """Phase 13: the supervisor sends a case to the payroll admin without rejecting the
    fix ("I can't decide this"). Only the assignee; no data changes."""
    with session.begin():
        actor = require_reviewer(session, actor_id)
        row = _get_for_update(session, exception_id)
        check_transition(row.status, "escalated", action="escalate")
        _require_assignee(row, actor, "escalate")
        admin = _payroll_admin(session)
        if actor.employee_id == admin.employee_id:
            raise ConflictError("the payroll admin decides escalated cases", code="already_payroll")
        before = {**_state(row), "no_reply_stage": row.no_reply_stage}
        _set_status(row, "escalated", clock, admin.employee_id)
        _audit(
            session,
            clock,
            exception_id=row.id,
            actor=ROLE_TO_ACTOR[actor.role],
            actor_id=actor.employee_id,
            action="escalate_to_admin",
            before=before,
            after=_state(row),
            reason=reason,
        )
    log.info(
        "exception escalated",
        extra={"event": "escalate_to_admin", "exception_id": exception_id, "actor_id": actor_id},
    )
    return row


def _worker_handoff(session: Session, row: ExceptionRow, actor_id: str | None) -> EmployeeRow:
    """actor_id None = the scheduler acting as "system" (no reviewer or assignee check; the
    investigation's code-owned route must still say the worker is next)."""
    if actor_id is not None:
        actor = require_reviewer(session, actor_id)
    check_transition(row.status, "awaiting_worker", action="ask_worker")
    if actor_id is not None:
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
    actor_id: str | None,
    note: str | None = None,
) -> ExceptionRow:
    """Phrase a verified question and save it with the worker handoff.

    actor_id None means the scheduler sends it automatically (audited as actor "system").
    It changes no timecard data, only who the case waits for."""
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
        before = {**_state(row), "no_reply_stage": row.no_reply_stage}
        _set_status(row, "awaiting_worker", clock, row.employee_id)
        row.worker_recheck = None
        no_reply.start_wait(row, clock.now())  # a new question = a new wait (Phase 13)
        message = WorkerMessageRow(
            exception_id=row.id,
            recipient_id=row.employee_id,
            date=row.date,
            message=draft.text,
            source=draft.source,
            reply_prompt=facts.reply_prompt,
            sent_at=clock.now(),
            asked_fix=time_review.asked_fix(row),
        )
        session.add(message)
        session.flush()
        _audit(
            session,
            clock,
            exception_id=row.id,
            actor=ROLE_TO_ACTOR[_actor(session, actor_id).role] if actor_id else "system",
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


def worker_inbox(session: Session, actor_id: str, clock: Clock) -> dict[str, Any]:
    """Open questions (with the reminder, if one was sent) plus plain notices: a question
    the supervisor now reviews (still answerable), one payroll now handles (closed), and
    a case decided without the worker's reply (Phase 13)."""
    actor = _actor(session, actor_id)
    if actor.role != "worker":
        raise ForbiddenError("only a worker can read their inbox", code="worker_inbox_only")
    latest_per_case = (
        select(func.max(WorkerMessageRow.id))
        .where(WorkerMessageRow.recipient_id == actor_id)
        .group_by(WorkerMessageRow.exception_id)
        .correlate(None)
    )
    waiting_for_worker = (ExceptionRow.status == "awaiting_worker") & (
        ExceptionRow.assigned_to == actor_id
    )
    late_allowed = (ExceptionRow.status == "awaiting_supervisor") & (
        ExceptionRow.no_reply_stage == no_reply.WITH_SUPERVISOR
    )
    rows = session.execute(
        select(WorkerMessageRow, ExceptionRow)
        .join(ExceptionRow, WorkerMessageRow.exception_id == ExceptionRow.id)
        .where(
            WorkerMessageRow.id.in_(latest_per_case),
            WorkerMessageRow.confirmed.is_not(True),
            ExceptionRow.employee_id == actor_id,
            waiting_for_worker | late_allowed,
        )
        .order_by(WorkerMessageRow.date, WorkerMessageRow.id)
    ).all()
    items = [
        {
            "exception_id": m.exception_id,
            "date": m.date,
            "message": m.message,
            "reply_prompt": m.reply_prompt,
            "needs_actual_time": m.needs_actual_time,
            "time_review": m.time_review,
            "reminder": (
                {"text": m.reminder_text, "sent_at": m.reminded_at} if m.reminded_at else None
            ),
            "status_note": (
                no_reply.WITH_SUPERVISOR_NOTE if row.status == "awaiting_supervisor" else None
            ),
        }
        for m, row in rows
    ]
    notices = []
    cases = session.scalars(
        select(ExceptionRow)
        .where(
            ExceptionRow.employee_id == actor_id,
            ExceptionRow.status.in_(("resolved", "escalated")),
        )
        .order_by(ExceptionRow.date, ExceptionRow.id)
    ).all()
    for row in cases:
        without = (row.applied_fix or {}).get("without_worker")
        if row.status == "resolved" and without:
            notices.append(
                {
                    "exception_id": row.id,
                    "date": row.date,
                    "kind": "decided_without_reply",
                    "title": no_reply.DECIDED_NOTE,
                    "text": f"{row.applied_fix.get('label')}.",
                    "reason": without.get("reason"),
                    "at": without.get("decided_at"),
                }
            )
        elif row.status == "escalated" and (row.no_reply_stage or 0) >= no_reply.WITH_SUPERVISOR:
            notices.append(
                {
                    "exception_id": row.id,
                    "date": row.date,
                    "kind": "with_payroll",
                    "title": "With payroll",
                    "text": no_reply.WITH_PAYROLL_NOTE,
                    "reason": None,
                    "at": row.no_reply_admin_at or row.updated_at,
                }
            )
    return {"items": items, "notices": notices}


def _worker_question(
    session: Session,
    exception_id: str,
    actor_id: str,
) -> tuple[ExceptionRow, EmployeeRow, WorkerMessageRow]:
    actor = _actor(session, actor_id)
    row = session.get(ExceptionRow, exception_id, with_for_update=True)
    if row is None or actor.role != "worker" or actor_id != row.employee_id:
        raise ForbiddenError("only the recipient can reply to this question", code="not_the_worker")
    # Phase 13: after the ladder brought the supervisor in, the worker may still answer
    # (a late reply resumes the normal flow). Once payroll has it, the question is closed.
    late = row.status == "awaiting_supervisor" and row.no_reply_stage == no_reply.WITH_SUPERVISOR
    if row.status == "escalated" and (row.no_reply_stage or 0) >= no_reply.WITH_SUPERVISOR:
        raise ConflictError(no_reply.WITH_PAYROLL_NOTE, code="handled_by_payroll")
    if row.status != "awaiting_worker" and not late:
        raise InvalidTransitionError(
            f"worker_reply: {row.id} is {row.status}, not waiting for the worker",
            details={
                "from": row.status,
                "to": "awaiting_supervisor",
                "allowed": ["awaiting_worker"],
            },
        )
    if not late:
        _require_assignee(row, actor, "reply to")
    message = session.scalar(
        select(WorkerMessageRow)
        .where(WorkerMessageRow.exception_id == row.id, WorkerMessageRow.recipient_id == actor_id)
        .order_by(WorkerMessageRow.id.desc())
        .limit(1)
    )
    if message is None:
        raise ConflictError("there is no unanswered question", code="no_open_worker_question")
    return row, actor, message


def _stop_ladder(
    session: Session, clock: Clock, row: ExceptionRow, actor: EmployeeRow, stage: int, how: str
) -> None:
    """Audit that the worker's answer stopped the no-reply ladder (Phase 13). `stage` is
    what no_reply.stop() returned; written after the reply's own audit row so the trail
    reads in order. A reply after the supervisor was brought in is recorded as late."""
    if stage == no_reply.NONE:
        return
    late = stage >= no_reply.WITH_SUPERVISOR
    _audit(
        session,
        clock,
        exception_id=row.id,
        actor="system",
        action="no_reply_ladder_stopped",
        after={"stage_before": stage, "late": late, "reply": how},
        reason=f"{actor.name} replied"
        + (" late, after the supervisor was brought in" if late else " after the reminder")
        + "; the no-reply ladder stopped.",
    )


def _to_supervisor(row: ExceptionRow, clock: Clock, supervisor_id: str | None, action: str) -> None:
    """Hand the case to the supervisor. A late reply finds it there already (Phase 13)."""
    if row.status != "awaiting_supervisor":
        check_transition(row.status, "awaiting_supervisor", action=action)
    _set_status(row, "awaiting_supervisor", clock, supervisor_id)


def _handoff_confirmed_time(
    session: Session,
    row: ExceptionRow,
    actor: EmployeeRow,
    message: WorkerMessageRow,
    clock: Clock,
    review: dict,
    source: str,
    approximate: bool = False,
) -> None:
    before = _state(row)
    confirmed_time = {**review, "source": source, "approximate": approximate}
    row.worker_recheck = confirmed_time
    row.proposed_fix = review["proposed_fix"]
    message.time_review = {
        "stage": "confirmed",
        "timestamp": review["timestamp"],
        "impact_note": review["impact_note"],
        "approximate": False,
    }
    message.needs_actual_time = False
    _to_supervisor(row, clock, actor.supervisor_id, "worker_time_confirmed")
    _audit(
        session,
        clock,
        exception_id=row.id,
        actor="worker",
        actor_id=actor.employee_id,
        action="worker_time_confirmed",
        before=before,
        after={
            **_state(row),
            **confirmed_time,
            "text": message.reply_text,
            "message_id": message.id,
        },
    )


def worker_reply(
    session: Session,
    clock: Clock,
    settings: Settings,
    policy: PolicyConfig,
    *,
    exception_id: str,
    actor_id: str,
    confirmed: bool,
    text: str | None,
) -> WorkerMessageRow:
    """Save the reply first. A model call never holds an exception row lock."""
    if not confirmed and not (text or "").strip():
        raise AppError("tell us what happened when answering No", code="reply_text_required")
    ctx = None
    with session.begin():
        row, actor, message = _worker_question(session, exception_id, actor_id)
        if message.replied_at is not None:
            raise ConflictError("there is no unanswered question", code="no_open_worker_question")
        before = _state(row)
        asked = message.asked_fix
        if asked is None and confirmed:
            # A legacy question can establish the proposal only if it asked the verified time.
            candidate = time_review.asked_fix(row)
            if candidate:
                try:
                    validate_worker_message(message.message, worker_facts(row, actor))
                except ValueError:
                    pass
                else:
                    asked = candidate
        message_id = message.id
        message.confirmed = confirmed
        message.reply_text = text
        message.replied_at = clock.now()
        message.needs_actual_time = not confirmed
        late = row.status == "awaiting_supervisor"
        stopped_at = no_reply.stop(row, clock.now())
        if confirmed:
            if asked:
                option = _find_option(row, asked["option_id"])
                stamp = datetime.fromisoformat(asked["params"]["timestamp"])
                review = time_review.recheck(session, row, option, stamp, policy, data_as_of(clock))
                _handoff_confirmed_time(session, row, actor, message, clock, review, "yes")
            elif row.policy_id == "P1":
                raise ConflictError(
                    "the question did not specify a verifiable time; answer No",
                    code="worker_time_required",
                )
            else:
                _to_supervisor(row, clock, actor.supervisor_id, "worker_reply")
        else:
            if late:  # a late No: back to the worker for the actual time (normal Phase 8)
                check_transition(row.status, "awaiting_worker", action="worker_reply")
                _set_status(row, "awaiting_worker", clock, actor.employee_id)
            no_reply.start_wait(row, clock.now())  # waiting for the time = a new wait
            row.updated_at = clock.now()
            option = time_review.clock_out_option(row, asked)
            if option:
                ctx = time_review.context(session, row, policy, data_as_of(clock))
            if ctx:
                message.time_review = {"stage": "manual", "approximate": False}
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
        _stop_ladder(session, clock, row, actor, stopped_at, "yes" if confirmed else "no")

    if ctx is None:
        return message
    assert text is not None
    extraction = time_extraction.extract(settings, text, ctx)
    with session.begin():
        row = _get_for_update(session, exception_id)
        message = session.get(WorkerMessageRow, message_id, populate_existing=True)
        if message is None:
            raise ConflictError("the question changed", code="no_open_worker_question")
        for rejected in extraction.rejected:
            _audit(
                session,
                clock,
                exception_id=row.id,
                actor="agent",
                action="worker_time_extraction_rejected",
                after={"message_id": message_id, **rejected},
            )
        diagnostic = extraction.diagnostic
        check_result = None
        if row.status == "awaiting_worker" and message.needs_actual_time and extraction.timestamp:
            try:
                option = time_review.clock_out_option(row, message.asked_fix)
                if (
                    option is None
                    or time_review.context(session, row, policy, data_as_of(clock)) != ctx
                ):
                    raise ConflictError("the shift context changed", code="case_changed")
                preview = time_review.recheck(
                    session, row, option, extraction.timestamp, policy, data_as_of(clock)
                )
                check_result = preview["result"]
                assert extraction.reply is not None
                message.time_review = {
                    "stage": "candidate",
                    "timestamp": preview["timestamp"],
                    "impact_note": preview["impact_note"],
                    "approximate": extraction.reply.approximate,
                }
            except AppError as exc:
                diagnostic = exc.message
        _audit(
            session,
            clock,
            exception_id=row.id,
            actor="agent",
            action="worker_time_extracted",
            reason=diagnostic,
            after={
                "message_id": message_id,
                "text": text,
                "extracted": extraction.reply.model_dump() if extraction.reply else None,
                "timestamp": extraction.timestamp.isoformat() if extraction.timestamp else None,
                "source": "llm",
                "recheck": check_result,
                "stage": (message.time_review or {}).get("stage"),
            },
        )
    return message


def submit_worker_time(
    session: Session,
    clock: Clock,
    policy: PolicyConfig,
    *,
    exception_id: str,
    actor_id: str,
    time: str | None = None,
    actual_date: date | None = None,
) -> WorkerMessageRow:
    with session.begin():
        row, actor, message = _worker_question(session, exception_id, actor_id)
        if not message.needs_actual_time:
            raise ConflictError(
                "this question is not waiting for an actual time", code="time_not_requested"
            )
        option = time_review.clock_out_option(row, message.asked_fix)
        ctx = time_review.context(session, row, policy, data_as_of(clock)) if option else None
        if option is None or ctx is None:
            raise ConflictError("this case has no clock-out option", code="time_not_supported")
        candidate = message.time_review or {}
        approximate = False
        if time is None:
            if candidate.get("stage") != "candidate":
                raise ConflictError(
                    "there is no extracted time to confirm", code="no_time_candidate"
                )
            stamp = datetime.fromisoformat(candidate["timestamp"])
            time, actual_date = stamp.strftime("%H:%M"), stamp.date()
            source = "llm"
            approximate = bool(candidate.get("approximate"))
        else:
            source = "manual"
        try:
            stamp = ctx.resolve(time, actual_date)
        except ValueError as exc:
            raise InvalidFixError(str(exc), code="invalid_time") from None
        review = time_review.recheck(session, row, option, stamp, policy, data_as_of(clock))
        stopped_at = no_reply.stop(row, clock.now())
        _handoff_confirmed_time(session, row, actor, message, clock, review, source, approximate)
        _stop_ladder(session, clock, row, actor, stopped_at, "time")
    return message
