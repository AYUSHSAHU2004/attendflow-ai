"""Phase 12: auto-resolve, as people see it, and the "resolved without a human" metric.

Read-only. Every text is stored data or built by code; nothing here calls the LLM.

- `auto_fix_info` explains one P2/P7 case: what was fixed, why code was allowed to close
  it (the engine's own numbers), the policy.md "Allowed fixes" line, who did it, whether
  and by whom it was undone, and whether the viewer may undo it now.
- `team_auto_fixes` lists them for a supervisor's team (the /supervisor page).
- `metric` computes X of Y from the database.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from attendflow.cases.selection import scope_cases
from attendflow.cases.supervisor import require_reviewer
from attendflow.db.models import AuditLogRow, EmployeeRow, ExceptionRow
from attendflow.engine.rules import to_minute
from attendflow.fixes.apply import AUTO_FIX_VERSION
from attendflow.policy.models import AUTO_RESOLVABLE, PolicyConfig

TYPE_WORD = {
    "in": "clock-in",
    "out": "clock-out",
    "break_start": "break start",
    "break_end": "break end",
}


def allowed_fix_text(sections: dict[str, str], policy_id: str) -> str:
    """The policy.md "**Allowed fixes:**" paragraph for a policy (verbatim, one line)."""
    text = sections.get(policy_id, "")
    for para in text.split("\n\n"):
        para = para.strip()
        if para.startswith("**Allowed fixes:**"):
            return " ".join(para.removeprefix("**Allowed fixes:**").split())
    return ""


def _change_line(change: dict[str, Any]) -> str:
    what = TYPE_WORD.get(change.get("type", ""), change.get("type", "punch"))
    raw = change.get("timestamp")
    stamp = to_minute(datetime.fromisoformat(raw)).strftime("%H:%M") if raw else "?"
    if change.get("op") == "void":
        return f"{change['punch_id']} {what} {stamp}: voided (kept in the database)"
    if change.get("op") == "restore":
        return f"{change['punch_id']} {what} {stamp}: restored (no longer voided)"
    return f"{change.get('punch_id')} {what} {stamp}: {change.get('op')}"


def _name(employees: dict[str, EmployeeRow], eid: str | None) -> str | None:
    if not eid:
        return None
    e = employees.get(eid)
    return e.name if e else eid


def can_undo(row: ExceptionRow, actor: EmployeeRow | None, team: dict[str, str | None]) -> bool:
    if actor is None or not row.auto_resolved or row.auto_resolve_undone_at is not None:
        return False
    if actor.role == "payroll_admin":
        return True
    return actor.role == "supervisor" and team.get(row.employee_id) == actor.employee_id


def auto_fix_info(
    session: Session,
    row: ExceptionRow,
    sections: dict[str, str],
    employees: dict[str, EmployeeRow],
    actor: EmployeeRow | None,
) -> dict[str, Any] | None:
    """None for a policy that can never auto-resolve, or a case that never was a candidate."""
    candidate = (row.details or {}).get("auto_resolve")
    if row.policy_id not in AUTO_RESOLVABLE or not (candidate or row.auto_resolved):
        return None
    audit = session.scalars(
        select(AuditLogRow)
        .where(
            AuditLogRow.exception_id == row.id,
            AuditLogRow.action.in_(
                ("auto_resolve", "auto_resolve_held", "auto_resolve_undone", "undo_refused")
            ),
        )
        .order_by(AuditLogRow.id)
    ).all()
    resolved = next((a for a in audit if a.action == "auto_resolve"), None)
    held = next((a for a in audit if a.action == "auto_resolve_held"), None)
    undone = next((a for a in reversed(audit) if a.action == "auto_resolve_undone"), None)
    refused = next((a for a in reversed(audit) if a.action == "undo_refused"), None)
    if row.auto_resolved:
        state = "auto_resolved"
    elif row.auto_resolve_undone_at is not None:
        state = "undone"
    elif held is not None:
        state = "held"
    else:
        return None
    if row.auto_resolved:
        fix = row.applied_fix
    else:  # undone: the auto-fix is kept in the undo audit row's "before"
        fix = (undone.before or {}).get("applied_fix") if undone else None
    changes = (fix or {}).get("changes") or []
    team = {eid: e.supervisor_id for eid, e in employees.items()}
    no_snapshot = row.auto_resolved and (fix or {}).get("snapshot_version") != AUTO_FIX_VERSION
    return {
        "state": state,
        "basis": (candidate or {}).get("basis") or (fix or {}).get("basis"),
        "held_because": list((held.after or {}).get("held_because") or []) if held else [],
        "policy_quote": allowed_fix_text(sections, row.policy_id),
        "changes": [_change_line(c) for c in changes],
        "data_changed": bool(changes),
        "resolved_by": "system" if resolved else None,
        "resolved_at": resolved.created_at if resolved else None,
        "undone_by": row.auto_resolve_undone_by,
        "undone_by_name": _name(employees, row.auto_resolve_undone_by),
        "undone_at": row.auto_resolve_undone_at,
        "undo_reason": undone.reason if undone else None,
        "can_undo": can_undo(row, actor, team) and not no_snapshot,
        "undo_unavailable_reason": (
            "Auto-resolved before undo existed (no snapshot). Run a demo reset."
            if no_snapshot
            else None
        ),
        "last_refusal": (
            {
                "at": refused.created_at,
                "by": refused.actor_id,
                "message": (refused.after or {}).get("message"),
            }
            if refused is not None and state == "auto_resolved"
            else None
        ),
    }


def team_auto_fixes(
    session: Session, sections: dict[str, str], actor_id: str
) -> list[dict[str, Any]]:
    """Auto-resolved and undone cases for the supervisor's team (the payroll admin: all)."""
    actor = require_reviewer(session, actor_id)
    employees = {e.employee_id: e for e in session.scalars(select(EmployeeRow))}
    stmt = select(ExceptionRow).where(
        ExceptionRow.policy_id.in_(AUTO_RESOLVABLE),
        ExceptionRow.auto_resolved | ExceptionRow.auto_resolve_undone_at.is_not(None),
    )
    rows = session.scalars(stmt.order_by(ExceptionRow.date, ExceptionRow.id)).all()
    if actor.role != "payroll_admin":
        rows = [r for r in rows if employees[r.employee_id].supervisor_id == actor.employee_id]
    items = []
    for row in rows:
        items.append(
            {
                "exception_id": row.id,
                "employee_id": row.employee_id,
                "employee_name": employees[row.employee_id].name,
                "date": row.date,
                "policy_id": row.policy_id,
                "title": row.title,
                "summary": row.summary,
                "status": row.status,
                "auto_fix": auto_fix_info(session, row, sections, employees, actor),
            }
        )
    return items


# ------------------------------------------------------------------ the headline metric


def metric(
    session: Session,
    policy: PolicyConfig,
    *,
    auto_resolve_enabled: bool,
    date_from: date | None = None,
    date_to: date | None = None,
    supervisor_id: str | None = None,
) -> dict[str, Any]:
    """X of Y resolved without a human, counted from the database.

    - X = exceptions closed by auto-resolve and not undone (`auto_resolved` is true; an
      undo sets it false, so undone cases count as human work).
    - Y = exceptions that needed handling: every stored exception in the date range,
      except those closed as `no_longer_detected` (the data changed and nobody had to act).
      Those are reported apart as `closed_by_data_change`.
    """
    stmt = scope_cases(
        select(ExceptionRow), date_from=date_from, date_to=date_to, supervisor_id=supervisor_id
    )
    rows = session.scalars(stmt).all()
    closed_ids = set(
        session.scalars(
            select(AuditLogRow.exception_id).where(AuditLogRow.action == "no_longer_detected")
        )
    )
    by_policy: dict[str, dict[str, int]] = {}
    x = y = closed = 0
    for row in rows:
        bucket = by_policy.setdefault(
            row.policy_id,
            {"needed_handling": 0, "auto_resolved": 0, "undone": 0, "closed_by_data_change": 0},
        )
        if row.status == "resolved" and row.id in closed_ids and not row.auto_resolved:
            closed += 1
            bucket["closed_by_data_change"] += 1
            continue
        y += 1
        bucket["needed_handling"] += 1
        if row.auto_resolved:
            x += 1
            bucket["auto_resolved"] += 1
        if row.auto_resolve_undone_at is not None:
            bucket["undone"] += 1
    return {
        "resolved_without_human": x,
        "needed_handling": y,
        "percent": round(100 * x / y, 1) if y else 0.0,
        "undone": sum(b["undone"] for b in by_policy.values()),
        "closed_by_data_change": closed,
        "date_from": date_from,
        "date_to": date_to,
        "auto_resolve_enabled": auto_resolve_enabled,
        "allowed_policies": [p for p in AUTO_RESOLVABLE if policy.policies[p].auto_resolve],
        "by_policy": [
            {"policy_id": pid, **counts}
            for pid, counts in sorted(by_policy.items(), key=lambda kv: int(kv[0][1:]))
        ],
    }
