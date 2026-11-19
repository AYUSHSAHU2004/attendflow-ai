"""The payroll admin's view: every exception, counters, and a read-only case detail.

Only the payroll admin (role `payroll_admin`, E201 in the demo) may call these; everyone
else gets 403 `admin_only`. Nothing here calls the LLM or writes data. Every text is
stored data or built by code. Acting on an escalated case reuses the supervisor card and
the decision endpoints (Phase 9); investigating reuses the investigate job (Phase 6).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from attendflow.activity.trace import result_summary
from attendflow.cases import no_reply as ladder
from attendflow.cases.auto_fix import auto_fix_info
from attendflow.cases.selection import NO_REPLY_STAGES, active_cases, scope_cases, stuck_cases
from attendflow.cases.supervisor import (
    SEVERITY_RANK,
    _policy_section,
    card_options,
)
from attendflow.db.models import (
    AuditLogRow,
    EmployeeRow,
    ExceptionRow,
    InvestigationJobRow,
    ToolCallRow,
    WorkerMessageRow,
)
from attendflow.errors import ForbiddenError, NotFoundError
from attendflow.policy.models import PolicyConfig

ADMIN_ROLE = "payroll_admin"
STATUSES = (
    "open",
    "awaiting_worker",
    "awaiting_supervisor",
    "escalated",
    "resolved",
    "rejected",
)
SORTS = ("severity", "date", "employee", "updated")
DEFAULT_LIMIT = 200
MAX_LIMIT = 500


# ------------------------------------------------------------------ permission


def require_admin(session: Session, actor_id: str) -> EmployeeRow:
    actor = session.get(EmployeeRow, actor_id)
    if actor is None:
        raise ForbiddenError(f"unknown actor {actor_id}", code="unknown_actor")
    if actor.role != ADMIN_ROLE:
        raise ForbiddenError(
            "only the payroll admin can open the admin view",
            code="admin_only",
            details={"actor_id": actor_id, "role": actor.role},
        )
    return actor


# ------------------------------------------------------------------ counters


def counters(
    session: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    supervisor_id: str | None = None,
) -> dict[str, int]:
    """The admin tiles use the global counts. The dashboard passes its case scope."""
    stmt = select(
        func.count().label("total"),
        *(func.count().filter(ExceptionRow.status == status).label(status) for status in STATUSES),
        func.count().filter(ExceptionRow.auto_resolved).label("auto_resolved"),
        func.count().filter(stuck_cases()).label("stuck"),
    ).select_from(ExceptionRow)
    scoped = scope_cases(
        stmt, date_from=date_from, date_to=date_to, supervisor_id=supervisor_id
    )
    return dict(session.execute(scoped).mappings().one())


# ------------------------------------------------------------------ overview


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _order(sort: str):
    severity = case(
        *((ExceptionRow.severity == name, rank) for name, rank in SEVERITY_RANK.items()),
        else_=9,
    )
    tail = (ExceptionRow.date, ExceptionRow.id)
    if sort == "date":
        return (ExceptionRow.date, severity, ExceptionRow.id)
    if sort == "employee":
        return (EmployeeRow.name, ExceptionRow.date, severity, ExceptionRow.id)
    if sort == "updated":
        return (ExceptionRow.updated_at.desc(), severity, *tail)
    return (severity, *tail)


def overview(
    session: Session,
    actor_id: str,
    *,
    status: str | None = None,
    policy_id: str | None = None,
    team: str | None = None,
    employee_id: str | None = None,
    severity: str | None = None,
    q: str | None = None,
    no_reply: str | None = None,
    active_only: bool = False,
    auto_resolved: bool | None = None,
    supervisor_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort: str = "severity",
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    now: datetime | None = None,
) -> dict[str, Any]:
    actor = require_admin(session, actor_id)
    employees = {e.employee_id: e for e in session.scalars(select(EmployeeRow))}

    stmt = scope_cases(
        select(ExceptionRow).join(EmployeeRow, EmployeeRow.employee_id == ExceptionRow.employee_id),
        date_from=date_from,
        date_to=date_to,
        supervisor_id=supervisor_id,
    )
    if active_only:
        stmt = stmt.where(active_cases())
    if auto_resolved is not None:
        stmt = stmt.where(ExceptionRow.auto_resolved == auto_resolved)
    if status:
        stmt = stmt.where(ExceptionRow.status == status)
    if policy_id:
        stmt = stmt.where(ExceptionRow.policy_id == policy_id)
    if team:
        stmt = stmt.where(func.lower(EmployeeRow.team) == team.lower())
    if employee_id:
        stmt = stmt.where(ExceptionRow.employee_id == employee_id)
    if severity:
        stmt = stmt.where(ExceptionRow.severity == severity)
    if no_reply == "any":
        stmt = stmt.where(stuck_cases())
    elif no_reply == "waiting":
        stmt = stmt.where(
            ExceptionRow.status == "awaiting_worker", ExceptionRow.no_reply_stage == 0,
        )
    elif no_reply in NO_REPLY_STAGES:
        stmt = stmt.where(ExceptionRow.no_reply_stage == NO_REPLY_STAGES[no_reply])
    if q and q.strip():
        pattern = _like(q.strip())
        stmt = stmt.where(
            or_(
                EmployeeRow.name.ilike(pattern, escape="\\"),
                ExceptionRow.employee_id.ilike(pattern, escape="\\"),
            )
        )
    matched = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.scalars(stmt.order_by(*_order(sort)).limit(limit).offset(offset)).all()

    items = []
    for row in rows:
        worker = employees[row.employee_id]
        assignee = employees.get(row.assigned_to) if row.assigned_to else None
        inv = row.investigation_case or {}
        items.append(
            {
                "exception_id": row.id,
                "employee_id": row.employee_id,
                "employee_name": worker.name,
                "team": worker.team,
                "date": row.date,
                "policy_id": row.policy_id,
                "title": row.title,
                "summary": row.summary,
                "severity": row.severity,
                "kind": row.kind,
                "status": row.status,
                "auto_resolved": row.auto_resolved,
                "auto_resolve_undone": row.auto_resolve_undone_at is not None,
                "assigned_to": row.assigned_to,
                "assigned_to_name": assignee.name if assignee else None,
                "investigated": bool(inv),
                "who_to_ask": inv.get("who_to_ask"),
                "investigation_fallback": bool(inv.get("fallback")) if inv else None,
                "needs_your_decision": _needs_decision(row, actor),
                "updated_at": row.updated_at,
                "no_reply": ladder.info(row, now or row.updated_at, worker.name),
            }
        )
    return {
        "counters": counters(session),
        "matched": matched,
        "limit": limit,
        "offset": offset,
        "items": items,
        "filter_options": _filter_options(session, employees),
    }


def _needs_decision(row: ExceptionRow, actor: EmployeeRow) -> bool:
    return row.status == "escalated" and row.assigned_to == actor.employee_id


def _filter_options(session: Session, employees: dict[str, EmployeeRow]) -> dict[str, Any]:
    """Values present in the stored exceptions, so every filter choice can match."""
    pairs = session.execute(
        select(ExceptionRow.employee_id, ExceptionRow.policy_id).distinct()
    ).all()
    employee_ids = sorted({eid for eid, _ in pairs})
    policies = sorted({pid for _, pid in pairs}, key=lambda p: int(p[1:]))
    return {
        "statuses": list(STATUSES),
        "policy_ids": policies,
        "teams": sorted({employees[eid].team for eid in employee_ids}),
        "employees": [
            {"employee_id": eid, "name": employees[eid].name, "team": employees[eid].team}
            for eid in sorted(employee_ids, key=lambda e: employees[e].name)
        ],
        "severities": list(SEVERITY_RANK),
        "no_reply": [*ladder.FILTERS, "waiting"],
    }


# ------------------------------------------------------------------ audit summaries


def _name(employees: dict[str, EmployeeRow], eid: str | None) -> str:
    if not eid:
        return "nobody"
    e = employees.get(eid)
    return e.name if e else eid


def _state_text(state: dict | None, employees: dict[str, EmployeeRow]) -> str | None:
    if not state or "status" not in state:
        return None
    text = str(state["status"]).replace("_", " ")
    if "assigned_to" in state:
        text += f", with {_name(employees, state.get('assigned_to'))}"
    return text


def _hhmm(stamp: str | None) -> str | None:
    return stamp[11:16] if stamp and len(stamp) >= 16 else None


def audit_summary(entry: AuditLogRow, employees: dict[str, EmployeeRow]) -> str:
    """One plain line per audit row, built from stored fields only."""
    after = entry.after or {}
    action = entry.action
    if action == "detected":
        return "Found by the rule engine."
    if action == "updated_by_detection":
        return "Detection refreshed the numbers."
    if action == "options_added":
        return "Detection added fix options."
    if action == "no_longer_detected":
        return "Closed: detection no longer finds it."
    if action == "auto_resolve":
        basis = after.get("basis")
        return f"Auto-resolved by the system: {basis}." if basis else "Auto-resolved by policy."
    if action == "auto_resolve_held":
        held = "; ".join(after.get("held_because") or []) or "not allowed"
        return f"Not auto-resolved ({held}); left for a person."
    if action == "auto_resolve_undone":
        who = _name(employees, entry.actor_id)
        restored = len(after.get("changes") or [])
        data = f", {restored} punch(es) restored" if restored else ", no data to restore"
        return f"{who} undid the auto-resolve{data}; the case is open again."
    if action == "undo_refused":
        return f"Undo refused, nothing changed: {after.get('message') or after.get('code')}."
    if action == "post_undo_detection":
        new = after.get("new_exception_ids") or []
        return (
            f"Detection re-ran after the undo; new exceptions: {', '.join(new)}."
            if new
            else "Detection re-ran after the undo; no new exceptions."
        )
    if action == "structured_investigation_started":
        return "Investigation started (read-only tools)."
    if action == "structured_investigation_finished":
        steps = after.get("tool_steps", 0)
        return f"Investigation finished ({after.get('reason')}, {steps} tool calls)."
    if action == "structured_model_failed":
        cause = after.get("diagnostic")
        return f"The model call failed: {cause}" if cause else "The model call failed."
    if action == "structured_draft_rejected":
        cause = after.get("diagnostic")
        text = "The model's draft failed code validation"
        return f"{text}: {cause}" if cause else f"{text}."
    if action == "investigation_case_stored":
        if after.get("fallback"):
            return f"Investigation stored from the engine template ({after.get('reason')})."
        return "Investigation stored; the model's draft passed code validation."
    if action == "ask_worker":
        if entry.actor == "system":
            return "The scheduler asked the worker to confirm (automatic)."
        return "Asked the worker to confirm."
    if action == "auto_investigation_started":
        return "The scheduler started an investigation (automatic)."
    if action == "auto_investigation_finished":
        how = "engine template" if after.get("fallback") else "validated model draft"
        return f"Automatic investigation finished ({how}); next: {after.get('who_to_ask')}."
    if action == "worker_message_sent":
        source = "the template" if after.get("source") == "template" else "the LLM (validated)"
        return f"Message to the worker written by {source}."
    if action == "worker_reply":
        if after.get("confirmed"):
            return "Worker answered Yes."
        return f"Worker answered No: “{after.get('text') or ''}”"
    if action == "worker_time_extraction_rejected":
        return "Model output for the reply was rejected by validation."
    if action == "worker_time_extracted":
        stamp = _hhmm(after.get("timestamp"))
        if stamp and after.get("stage") == "candidate":
            return f"Time read from the reply: {stamp} (the worker must confirm it)."
        return "No usable time read from the reply; the worker gets the manual time field."
    if action == "worker_time_confirmed":
        stamp = _hhmm(after.get("timestamp"))
        how = {"yes": "by answering Yes", "llm": "from the extracted time", "manual": "typed in"}
        approx = ", approximate" if after.get("approximate") else ""
        return f"Worker confirmed {stamp} ({how.get(after.get('source'), 'confirmed')}{approx})."
    if action in ("approve", "edit_and_approve"):
        fix = after.get("applied_fix") or {}
        verb = "Edited and approved" if action == "edit_and_approve" else "Approved"
        return f"{verb}: {fix.get('label') or fix.get('option_id') or 'fix'}."
    if action == "post_fix_detection":
        new = after.get("new_exception_ids") or []
        return (
            f"Detection re-ran; new exceptions: {', '.join(new)}."
            if new
            else ("Detection re-ran; no new exceptions.")
        )
    if action == "post_fix_detection_failed":
        return "Detection after the fix failed; the next run picks it up."
    if action == "reject_and_escalate":
        return f"Rejected and sent to {_name(employees, after.get('assigned_to'))}."
    if action == "reject":
        return "Rejected (final). No data changed."
    if action == "no_reply_reminder":
        return "No reply yet: the system sent one reminder (template)."
    if action == "no_reply_to_supervisor":
        hours = after.get("hours_without_reply")
        to = _name(employees, after.get("assigned_to"))
        return f"No reply for {hours}: brought in {to}. Nothing was changed."
    if action == "no_reply_to_admin":
        to = _name(employees, after.get("assigned_to"))
        return f"The supervisor did not act in time: sent to {to}. Nothing was changed."
    if action == "no_reply_ladder_stopped":
        when = (
            "late, after the supervisor was brought in"
            if after.get("late")
            else "after the reminder"
        )
        return f"The worker replied ({when}); the no-reply steps stopped."
    if action == "decided_without_worker":
        how = {"prefilled": ", time as prefilled", "edited": ", time edited"}.get(
            after.get("time_source") or "", ""
        )
        who = _name(employees, entry.actor_id)
        return f"{who} decided without the worker's reply{how}."
    if action == "escalate_to_admin":
        return f"Escalated to {_name(employees, after.get('assigned_to'))} (no decision made)."
    if action == "demo_clock_moved":
        return f"Demo clock moved forward {after.get('hours')} h."
    return action.replace("_", " ").capitalize() + "."


def _audit_entry(entry: AuditLogRow, employees: dict[str, EmployeeRow]) -> dict[str, Any]:
    return {
        "id": entry.id,
        "created_at": entry.created_at,
        "actor": entry.actor,
        "actor_id": entry.actor_id,
        "actor_name": _name(employees, entry.actor_id) if entry.actor_id else None,
        "action": entry.action,
        "summary": audit_summary(entry, employees),
        "reason": entry.reason,
        "before_summary": _state_text(entry.before, employees),
        "after_summary": _state_text(entry.after, employees),
    }


# ------------------------------------------------------------------ detail


def _tool_call(call: ToolCallRow) -> dict[str, Any]:
    output = call.output or {}
    error = output.get("error") if isinstance(output.get("error"), dict) else None
    return {
        "run_id": call.run_id,
        "step_no": call.step_no,
        "call_no": call.call_no,
        "tool_name": call.tool_name,
        "input": call.input,
        "ok": call.ok,
        "error_code": error.get("code") if error else None,
        "duration_ms": call.duration_ms,
        "result_summary": result_summary(call.tool_name, call.ok, call.output),
    }


def _message(m: WorkerMessageRow) -> dict[str, Any]:
    return {
        "id": m.id,
        "sent_at": m.sent_at,
        "source": m.source,
        "message": m.message,
        "reply_prompt": m.reply_prompt,
        "confirmed": m.confirmed,
        "reply_text": m.reply_text,
        "replied_at": m.replied_at,
        "needs_actual_time": m.needs_actual_time,
        "time_review": m.time_review,
        "reminded_at": m.reminded_at,
        "reminder_text": m.reminder_text,
    }


def detail(
    session: Session,
    policy: PolicyConfig,
    sections: dict[str, str],
    *,
    exception_id: str,
    actor_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    actor = require_admin(session, actor_id)
    row = session.get(ExceptionRow, exception_id)
    if row is None:
        raise NotFoundError(f"exception {exception_id} not found", code="exception_not_found")
    employees = {e.employee_id: e for e in session.scalars(select(EmployeeRow))}
    worker = employees[row.employee_id]
    messages = session.scalars(
        select(WorkerMessageRow)
        .where(WorkerMessageRow.exception_id == row.id)
        .order_by(WorkerMessageRow.id)
    ).all()
    audit = session.scalars(
        select(AuditLogRow).where(AuditLogRow.exception_id == row.id).order_by(AuditLogRow.id)
    ).all()
    calls = session.scalars(
        select(ToolCallRow).where(ToolCallRow.exception_id == row.id).order_by(ToolCallRow.id)
    ).all()
    job = session.scalars(
        select(InvestigationJobRow)
        .where(InvestigationJobRow.exception_id == row.id)
        .order_by(InvestigationJobRow.started_at.desc(), InvestigationJobRow.id.desc())
    ).first()
    title, rule = _policy_section(sections, row.policy_id)
    inv = row.investigation_case
    return {
        "exception_id": row.id,
        "status": row.status,
        "assigned_to": row.assigned_to,
        "assigned_to_name": _name(employees, row.assigned_to) if row.assigned_to else None,
        "needs_your_decision": _needs_decision(row, actor),
        "can_investigate": row.status == "open",
        "auto_resolved": row.auto_resolved,
        "auto_fix": auto_fix_info(session, row, sections, employees, actor),
        "employee": {"employee_id": worker.employee_id, "name": worker.name, "team": worker.team},
        "date": row.date,
        "policy_id": row.policy_id,
        "title": row.title,
        "summary": row.summary,
        "severity": row.severity,
        "kind": row.kind,
        "details": row.details,
        "policy": {
            "policy_id": row.policy_id,
            "title": title,
            "rule": rule,
            "cited_text": (inv or {}).get("policy_text_cited") or rule,
        },
        "evidence": row.evidence,
        "options": card_options(row, policy, messages[-1] if messages else None, worker.name),
        "investigation": inv,
        "latest_job": (
            {"id": job.id, "status": job.status, "reason": job.reason} if job is not None else None
        ),
        "worker_messages": [_message(m) for m in messages],
        "recheck": row.worker_recheck,
        "applied_fix": row.applied_fix,
        "audit_trail": [_audit_entry(a, employees) for a in audit],
        "tool_calls": [_tool_call(c) for c in calls],
        "no_reply": ladder.info(row, now or row.updated_at, worker.name),
    }
