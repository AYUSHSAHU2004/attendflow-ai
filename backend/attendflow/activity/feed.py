"""The Activity Center feed: one plain-language line per audit row, newest first.

Built only from `audit_log` (joined to the case and the employees). No second store and no
LLM: every sentence comes from a fixed template over stored fields. Times are workflow
times (`created_at`, from the demo clock), so the feed tells the story in demo time.

Who sees what (enforced here, not only in the UI):
- the payroll admin sees everything;
- a supervisor sees only rows of cases whose worker is on their team (rows without a case,
  such as device punches and demo clock moves, are payroll-only);
- workers and unknown actors get 403 (`supervisor_only`, the reviewer rule).

Never shown: before/after JSON, tool inputs or outputs, prompts, model diagnostics or
previews, message bodies, keys. `reason` is shown only for a person's own typed reason.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Literal

from sqlalchemy import Select, distinct, func, or_, select
from sqlalchemy.orm import Session

from attendflow.activity import autonomy
from attendflow.cases.admin import audit_summary
from attendflow.cases.selection import team_members
from attendflow.cases.supervisor import require_reviewer
from attendflow.db.models import AuditLogRow, EmployeeRow, ExceptionRow

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
Mode = Literal["all", "autonomous", "human"]

ACTOR_LABELS = {
    "system": "System",
    "agent": "LLM agent",
    "device": "Device",
    "worker": "Worker",
    "supervisor": "Supervisor",
    "admin": "Payroll admin",
}
# A person's own typed reason, safe to show. Every other `reason` may hold a model
# diagnostic or an internal message, so it is never shown.
HUMAN_REASON_ACTIONS = (
    "approve",
    "edit_and_approve",
    "decided_without_worker",
    "reject",
    "reject_and_escalate",
    "escalate_to_admin",
    "auto_resolve_undone",
    "payroll_signed_off",
    "payroll_reopened",
)
HUMAN_ACTORS = ("worker", "supervisor", "admin")
# Fixed sentences for rows whose detail sentence would echo a model diagnostic.
SAFE_TEXT = {
    "structured_model_failed": "The model call failed; the engine template is used if it "
    "keeps failing.",
    "structured_draft_rejected": "The model's draft failed code validation and was not used.",
    "worker_time_extraction_rejected": "Model output for the reply was rejected by validation.",
    "investigation_started": "Investigation started (read-only tools).",
    "investigation_finished": "Investigation finished.",
}


def _hhmm_day(stamp: str | None) -> str:
    try:
        when = datetime.fromisoformat(stamp or "")
    except ValueError:
        return "an unknown time"
    return when.strftime("%a %d %b %H:%M")


PUNCH_WORDS = {
    "in": "clock-in",
    "out": "clock-out",
    "break_start": "break start",
    "break_end": "break end",
}


BRIEFING_REASONS = {
    "validation_failed": "the LLM draft failed the checks",
    "llm_error": "the LLM call failed",
    "timeout": "the LLM call timed out",
    "llm_unavailable": "no LLM is configured",
    "llm_disabled": "the LLM briefing is switched off",
    "no_budget": "today's LLM budget is used up",
}


def _scope_words(after: dict, employees: dict[str, EmployeeRow]) -> str:
    scope = str(after.get("scope") or "")
    if scope == "all":
        return "all teams"
    who = employees.get(scope)
    return f"{who.team} team" if who else "one team"


def feed_sentence(entry: AuditLogRow, employees: dict[str, EmployeeRow]) -> str:
    """The plain sentence for one row. Deterministic, built from safe stored fields only."""
    if entry.action in SAFE_TEXT:
        return SAFE_TEXT[entry.action]
    after = entry.after or {}
    if entry.action == "payroll_signed_off":
        return f"Signed off attendance readiness for the week of {after['week_start']}."
    if entry.action == "payroll_reopened":
        return f"Reopened attendance readiness for the week of {after['week_start']}."
    if entry.action == "punch_ingested":
        who = employees.get(after.get("employee_id") or "")
        name = who.name if who else (after.get("employee_id") or "a worker")
        kind = PUNCH_WORDS.get(str(after.get("type")), "punch")
        device = after.get("device_id") or "A device"
        return f"{device} recorded a {kind} for {name} at {_hhmm_day(after.get('timestamp'))}."
    if entry.action == "post_punch_detection":
        new = after.get("new_exception_ids") or []
        closed = after.get("closed_exception_ids") or []
        parts = [f"new: {', '.join(new)}" if new else "nothing new"]
        if closed:
            parts.append(f"closed: {', '.join(closed)}")
        return f"Detection re-ran after the punch ({'; '.join(parts)})."
    if entry.action == "briefing_refresh_requested":
        return f"Asked for a fresh daily briefing ({_scope_words(after, employees)})."
    if entry.action == "briefing_generated":
        retry = " after one correction" if after.get("reason") == "validated_after_retry" else ""
        return (
            f"Wrote the daily briefing ({_scope_words(after, employees)}) from verified "
            f"facts; every check passed{retry}."
        )
    if entry.action == "briefing_fallback":
        why = BRIEFING_REASONS.get(str(after.get("reason")), "the LLM was not used")
        return f"Showed the template briefing ({_scope_words(after, employees)}): {why}."
    if entry.action == "post_punch_detection_failed":
        return "Detection after the punch failed; the next run picks it up."
    if entry.action == "post_undo_detection_failed":
        return "Detection after the undo failed; the next run picks it up."
    return audit_summary(entry, employees)


def _actor_name(entry: AuditLogRow, employees: dict[str, EmployeeRow]) -> str:
    if entry.actor_id and entry.actor_id in employees:
        return employees[entry.actor_id].name
    if entry.actor == "device":
        return (entry.after or {}).get("device_id") or "Punch device"
    if entry.actor == "agent":
        return "LLM agent"
    row = autonomy.capability_for(entry.action, entry.actor)
    if row is not None and row.actor_type == "llm_agent":
        return "Template (LLM fallback)"  # a system row of an LLM capability
    return row.performed_by if row is not None else ACTOR_LABELS[entry.actor]


def _scoped(
    stmt: Select,
    actor: EmployeeRow,
    *,
    policy_id: str | None,
    employee_id: str | None,
    exception_id: str | None,
    date_from: date | None,
    date_to: date | None,
) -> Select:
    stmt = stmt.outerjoin(ExceptionRow, AuditLogRow.exception_id == ExceptionRow.id).where(
        AuditLogRow.action.notin_(autonomy.HIDDEN_FROM_FEED)
    )
    if actor.role != "payroll_admin":
        stmt = stmt.where(ExceptionRow.employee_id.in_(team_members(actor.employee_id)))
    if policy_id:
        stmt = stmt.where(ExceptionRow.policy_id == policy_id)
    if exception_id:
        stmt = stmt.where(AuditLogRow.exception_id == exception_id)
    if employee_id:
        stmt = stmt.where(
            or_(
                ExceptionRow.employee_id == employee_id,
                AuditLogRow.after["employee_id"].astext == employee_id,
            )
        )
    if date_from:
        stmt = stmt.where(AuditLogRow.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        stmt = stmt.where(
            AuditLogRow.created_at < datetime.combine(date_to + timedelta(days=1), time.min)
        )
    return stmt


def feed(
    session: Session,
    actor_id: str,
    *,
    actor_type: str | None = None,
    mode: Mode = "all",
    policy_id: str | None = None,
    employee_id: str | None = None,
    exception_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    before_id: int | None = None,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    viewer = require_reviewer(session, actor_id)
    stmt = _scoped(
        select(AuditLogRow, ExceptionRow),
        viewer,
        policy_id=policy_id,
        employee_id=employee_id,
        exception_id=exception_id,
        date_from=date_from,
        date_to=date_to,
    )
    if actor_type:
        stmt = stmt.where(AuditLogRow.actor == actor_type)
    if mode == "autonomous":
        stmt = stmt.where(AuditLogRow.actor.in_(autonomy.AUTONOMOUS_AUDIT_ACTORS))
    elif mode == "human":
        stmt = stmt.where(AuditLogRow.actor.in_(HUMAN_ACTORS))
    if before_id is not None:
        stmt = stmt.where(AuditLogRow.id < before_id)
    rows = session.execute(stmt.order_by(AuditLogRow.id.desc()).limit(limit + 1)).all()
    more = len(rows) > limit
    rows = rows[:limit]
    employees = {e.employee_id: e for e in session.scalars(select(EmployeeRow))}
    items = [_item(entry, case, employees) for entry, case in rows]
    return {
        "viewer": {"employee_id": viewer.employee_id, "role": viewer.role},
        "items": items,
        "next_before_id": items[-1]["id"] if more and items else None,
    }


def _item(
    entry: AuditLogRow, case: ExceptionRow | None, employees: dict[str, EmployeeRow]
) -> dict[str, Any]:
    subject_id = case.employee_id if case else (entry.after or {}).get("employee_id")
    subject = employees.get(subject_id or "")
    capability = autonomy.capability_for(entry.action, entry.actor)
    show_reason = entry.actor in HUMAN_ACTORS and entry.action in HUMAN_REASON_ACTIONS
    return {
        "id": entry.id,
        "at": entry.created_at,
        "actor_type": entry.actor,
        "actor_label": ACTOR_LABELS[entry.actor],
        "actor_name": _actor_name(entry, employees),
        "autonomous": entry.actor in autonomy.AUTONOMOUS_AUDIT_ACTORS,
        "action": entry.action,
        "capability": capability.key if capability else None,
        "sentence": feed_sentence(entry, employees),
        "reason": entry.reason if show_reason else None,
        "case": (
            {
                "exception_id": case.id,
                "policy_id": case.policy_id,
                "date": case.date,
                "title": case.title,
                "status": case.status,
            }
            if case
            else None
        ),
        "employee": (
            {"employee_id": subject.employee_id, "name": subject.name, "team": subject.team}
            if subject
            else None
        ),
    }


SUMMARY_ACTIONS = {
    "investigated": ("investigation_case_stored",),
    "messages_sent": ("worker_message_sent",),
    "reminders_sent": ("no_reply_reminder",),
    "auto_resolved": ("auto_resolve",),
    "auto_resolves_undone": ("auto_resolve_undone",),
    "escalated_by_silence": ("no_reply_to_supervisor", "no_reply_to_admin"),
    "human_approvals": ("approve", "edit_and_approve"),
    "decided_without_worker": ("decided_without_worker",),
    "human_rejections": ("reject", "reject_and_escalate"),
    "device_punches": ("punch_ingested",),
}
# Counted as distinct cases rather than rows.
DISTINCT_CASES = ("investigated", "escalated_by_silence")


def summary(
    session: Session,
    actor_id: str,
    *,
    policy_id: str | None = None,
    employee_id: str | None = None,
    exception_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """Counts for the summary strip, computed by the database with the same scope and
    filters as the feed (actor type and autonomous/human do not apply)."""
    viewer = require_reviewer(session, actor_id)
    counts: dict[str, int] = {}
    for key, actions in SUMMARY_ACTIONS.items():
        what = (
            func.count(distinct(AuditLogRow.exception_id))
            if key in DISTINCT_CASES
            else func.count(AuditLogRow.id)
        )
        stmt = _scoped(
            select(what).select_from(AuditLogRow),
            viewer,
            policy_id=policy_id,
            employee_id=employee_id,
            exception_id=exception_id,
            date_from=date_from,
            date_to=date_to,
        ).where(AuditLogRow.action.in_(actions))
        counts[key] = session.scalar(stmt) or 0
    return {
        "date_from": date_from,
        "date_to": date_to,
        "counts": counts,
        "definitions": {key: list(actions) for key, actions in SUMMARY_ACTIONS.items()},
    }


def autonomy_table(session: Session, actor_id: str) -> dict[str, Any]:
    require_reviewer(session, actor_id)
    return {
        "items": [
            {
                "key": c.key,
                "title": c.title,
                "kind": c.kind,
                "actor_type": c.actor_type,
                "actor_label": autonomy.ACTOR_TYPE_LABELS[c.actor_type],
                "performed_by": c.performed_by,
                "approval": c.approval,
                "approval_label": autonomy.APPROVAL_LABELS[c.approval],
                "reversible": c.reversible,
                "reversible_label": autonomy.REVERSIBLE_LABELS[c.reversible],
                "guardrail": c.guardrail,
                "autonomous": c.autonomous,
                "audit_actions": list(c.audit_actions),
                "proof_tests": list(c.proof_tests),
            }
            for c in autonomy.CAPABILITIES
        ]
    }
