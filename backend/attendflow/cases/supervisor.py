"""The supervisor's queue and case card. Read-only; every text here is built by code.

Who sees what (X-Actor-Id):
- A supervisor sees cases of their own team that are assigned to them and ready for a
  decision: `awaiting_supervisor`, or `open` with a stored investigation that routes the
  case to the supervisor. Plus any `escalated` case assigned to them.
- The payroll admin sees only `escalated` cases assigned to them (full list: Phase 10).
- A case still waiting for the worker's actual time (`needs_actual_time`) never appears,
  unless the no-reply ladder brought the supervisor in (Phase 13): then it appears with
  a "worker has not replied" badge (`no_reply`).
- An open case whose auto-resolve a person undid (Phase 12) appears for the team supervisor.
- Workers get 403.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from attendflow.cases import no_reply
from attendflow.cases.time_review import TIME_ACTIONS
from attendflow.db.models import EmployeeRow, ExceptionRow, WorkerMessageRow
from attendflow.engine.models import ACTION_INFO
from attendflow.errors import ForbiddenError, NotFoundError
from attendflow.fixes.params import DECISION_ACTIONS, MIN_NOTE_LENGTH, REQUIRED_NOTE
from attendflow.policy.models import PolicyConfig
from attendflow.tools.models import RunChecksOut

REVIEWER_ROLES = ("supervisor", "payroll_admin")
SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
MIN_NOTE = MIN_NOTE_LENGTH
# Params the engine stores for display only; never edited by a human.
HIDDEN_PARAMS = {"worked_hours_after_fix"}

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$")
_TIME = re.compile(r"^\d{2}:\d{2}(?::\d{2})?$")


# ------------------------------------------------------------------ permissions


def require_reviewer(session: Session, actor_id: str) -> EmployeeRow:
    """Supervisor endpoints: only supervisors and the payroll admin (workers get 403)."""
    actor = session.get(EmployeeRow, actor_id)
    if actor is None:
        raise ForbiddenError(f"unknown actor {actor_id}", code="unknown_actor")
    if actor.role not in REVIEWER_ROLES:
        raise ForbiddenError(
            "only a supervisor or the payroll admin can do this",
            code="supervisor_only",
            details={"actor_id": actor_id, "role": actor.role},
        )
    return actor


def _pending_worker_time(session: Session, exception_ids: list[str]) -> set[str]:
    if not exception_ids:
        return set()
    rows = session.scalars(
        select(WorkerMessageRow)
        .where(WorkerMessageRow.exception_id.in_(exception_ids))
        .order_by(WorkerMessageRow.id)
    ).all()
    latest = {m.exception_id: m for m in rows}  # ordered by id: the last one wins
    return {eid for eid, m in latest.items() if m.needs_actual_time}


def in_queue(row: ExceptionRow, actor: EmployeeRow, team: dict[str, str | None]) -> bool:
    """Is this case waiting for this actor's decision? (needs_actual_time checked apart)"""
    if row.assigned_to != actor.employee_id:
        return False
    if row.status == "escalated":
        return True
    if actor.role != "supervisor" or team.get(row.employee_id) != actor.employee_id:
        return False
    if row.status == "awaiting_supervisor":
        return True
    if row.status != "open":
        return False
    # An open case whose auto-resolve a person undid (Phase 12) is the supervisor's to decide.
    if row.auto_resolve_undone_at is not None:
        return True
    # Open: only once an investigation routed it to the supervisor. A case routed to the
    # worker stays off the queue until the worker has replied.
    return (row.investigation_case or {}).get("who_to_ask") == "supervisor"


def queue(session: Session, actor_id: str, now: datetime) -> list[dict[str, Any]]:
    actor = require_reviewer(session, actor_id)
    employees = {e.employee_id: e for e in session.scalars(select(EmployeeRow))}
    team = {eid: e.supervisor_id for eid, e in employees.items()}
    rows = session.scalars(
        select(ExceptionRow).where(
            ExceptionRow.assigned_to == actor.employee_id,
            ExceptionRow.status.in_(("open", "awaiting_supervisor", "escalated")),
        )
    ).all()
    picked = [r for r in rows if in_queue(r, actor, team)]
    waiting = _pending_worker_time(session, [r.id for r in picked])
    # Brought in by the no-reply ladder: shown even if the worker said No without a time.
    picked = [
        r
        for r in picked
        if r.id not in waiting or (r.no_reply_stage or 0) >= no_reply.WITH_SUPERVISOR
    ]
    picked.sort(key=lambda r: (SEVERITY_RANK.get(r.severity, 9), r.date, r.id))
    items = []
    for row in picked:
        others = _others(employees, row.employee_id)
        items.append(
            {
                "exception_id": row.id,
                "employee_id": row.employee_id,
                "employee_name": employees[row.employee_id].name,
                "date": row.date,
                "policy_id": row.policy_id,
                "title": redact(row.title, others),
                "summary": redact(row.summary, others),
                "severity": row.severity,
                "kind": row.kind,
                "status": row.status,
                "waiting_since": row.waiting_since,
                "auto_resolve_undone": row.auto_resolve_undone_at is not None,
                "no_reply": no_reply.info(row, now, employees[row.employee_id].name),
            }
        )
    return items


# ------------------------------------------------------------------ redaction


def _others(employees: dict[str, EmployeeRow], keep: str) -> list[str]:
    """IDs and names of every other worker, longest first (so names match whole).
    Supervisors and the payroll admin are not redacted: they act on the case."""
    words = [
        w
        for eid, e in employees.items()
        if eid != keep and e.role == "worker"
        for w in (eid, e.name)
    ]
    return sorted(words, key=len, reverse=True)


def redact(value: Any, others: list[str]) -> Any:
    """Replace other employees' IDs and names with 'another worker' (P17 terminal clashes
    name the other workers; the card shows one worker's case only)."""
    if not others:
        return value
    if isinstance(value, str):
        pattern = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in others) + r")\b")
        return pattern.sub("another worker", value)
    if isinstance(value, list):
        return [redact(v, others) for v in value]
    if isinstance(value, dict):
        return {k: redact(v, others) for k, v in value.items()}
    return value


def own_evidence(row: ExceptionRow) -> tuple[list[dict], int]:
    kept = [e for e in row.evidence if e.get("employee_id") in (None, row.employee_id)]
    return kept, len(row.evidence) - len(kept)


# ------------------------------------------------------------------ consequence note


def _num(value: float) -> str:
    return f"{value:g}"


def _hhmm(stamp: str) -> str:
    return datetime.fromisoformat(stamp).strftime("%H:%M")


def time_label(option: dict, params: dict, flags: str | None = None) -> str:
    """The engine's label names its default time (e.g. 'scheduled shift end (18:00)').
    Once a worker confirmed or a supervisor edited the time, say the real one."""
    stamp = params.get("timestamp")
    if option["action"] not in TIME_ACTIONS or not stamp:
        return option["label"]
    which = "clock-in" if option["action"] == "set_clock_in" else "clock-out"
    verb = "Correct" if option["action"] == "correct_clock_out" else "Set"
    return f"{verb} {which} to {_hhmm(stamp)}" + (f" ({flags})" if flags else "")


def _change_phrase(option: dict, params: dict) -> str:
    stamp = params.get("timestamp")
    if stamp and option["action"] in {"set_clock_out", "correct_clock_out"}:
        return f"a {_hhmm(stamp)} clock-out"
    if stamp and option["action"] == "set_clock_in":
        return f"a {_hhmm(stamp)} clock-in"
    return "this fix"


def _finding(item: dict) -> str:
    when = item["date"]
    if item["policy_id"] in {"P5", "P16"}:
        when = f"week of {when}"
    kind = f" {item['kind']}" if item.get("kind") else ""
    return f"{item['policy_id']}{kind} ({when})"


def consequence_note(option: dict, params: dict, result: RunChecksOut, policy: PolicyConfig) -> str:
    """One plain sentence (or three) from a simulated re-check. Code only, no LLM."""
    new = {item.policy_id for item in result.new_violations}
    parts = []
    if result.day_worked_hours is not None:
        day = f"makes the day {_num(result.day_worked_hours)} h"
        if "P3" in new:
            day += f", over the {_num(policy.number('P3', 'max_hours_per_day'))} h limit (P3)"
        parts.append(day)
    week = f"projects {_num(result.week_projected_hours)} h for the week"
    if "P5" in new or result.week_projected_hours > result.weekly_limit_hours:
        week += f", over {_num(result.weekly_limit_hours)} h"
        week += " (P5)" if "P5" in new else ""
    parts.append(week)
    text = f"Approving {_change_phrase(option, params)} " + " and ".join(parts) + "."
    if result.resolved:
        text += " It resolves " + ", ".join(_finding(f.model_dump()) for f in result.resolved)
        text += "."
    if result.new_violations:
        count = len(result.new_violations)
        text += (
            f" Approving creates {count} new exception{'s' if count > 1 else ''}: "
            + ", ".join(_finding(f.model_dump()) for f in result.new_violations)
            + "."
        )
    else:
        text += " It creates no new exceptions."
    return text


def option_consequence(
    row: ExceptionRow, option: dict, params: dict, policy: PolicyConfig
) -> dict[str, Any]:
    recheck = row.worker_recheck or {}
    if (recheck.get("proposed_fix") or {}).get("option_id") == option["option_id"]:
        result = RunChecksOut.model_validate(recheck["result"])
        source = "worker_recheck"
    else:
        case = row.investigation_case or {}
        proposed = case.get("proposed_fix") or {}
        result = None
        if proposed.get("option_id") == option["option_id"] and case.get("validation_result"):
            result = RunChecksOut.model_validate(case["validation_result"])
            source = "investigation"
    if result is not None:
        return {
            "source": source,
            "note": consequence_note(option, params, result, policy),
            "creates_violations": bool(result.new_violations),
            "new_violations": [f.model_dump() for f in result.new_violations],
            "resolved": [f.model_dump() for f in result.resolved],
            "day_worked_hours": result.day_worked_hours,
            "week_projected_hours": result.week_projected_hours,
            "weekly_limit_hours": result.weekly_limit_hours,
        }
    if option["action"] in DECISION_ACTIONS:
        note = "Records a decision only. No timecard, schedule or leave data changes."
        source = "decision_only"
    else:
        note = "Not checked yet: investigate first to see what this change does."
        source = "unchecked"
    return {
        "source": source,
        "note": note,
        "creates_violations": False,
        "new_violations": [],
        "resolved": [],
        "day_worked_hours": None,
        "week_projected_hours": None,
        "weekly_limit_hours": None,
    }


# ------------------------------------------------------------------ options and fields


def _kind(value: Any) -> str:
    if isinstance(value, bool):
        return "fixed"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        if _STAMP.match(value):
            return "datetime"
        if _DATE.match(value):
            return "date"
        if _TIME.match(value):
            return "time"
        return "text"
    return "fixed"  # lists and objects are shown, not edited


def _fields(row: ExceptionRow, option: dict, params: dict, locked_reason: str | None) -> list:
    note_key = REQUIRED_NOTE.get(option["action"])
    fields = []
    for key, value in params.items():
        if key in HIDDEN_PARAMS or key == note_key:
            continue
        kind = _kind(value)
        locked = key == "timestamp" and locked_reason is not None
        fields.append(
            {
                "name": key,
                "kind": kind,
                "value": value,
                "editable": kind != "fixed" and not locked,
                "locked_reason": locked_reason if locked else None,
            }
        )
    return fields


def _editable_punches(row: ExceptionRow, option: dict) -> list[dict] | None:
    if option["action"] != "edit_punches":
        return None
    ids = option["params"].get("punch_ids") or []
    by_id = {e.get("punch_id"): e for e in row.evidence if e.get("punch_id")}
    return [
        {
            "punch_id": pid,
            "type": by_id.get(pid, {}).get("type"),
            "timestamp": by_id.get(pid, {}).get("timestamp"),
        }
        for pid in ids
    ]


def card_options(
    row: ExceptionRow,
    policy: PolicyConfig,
    reply: WorkerMessageRow | None,
    worker_name: str,
) -> list[dict[str, Any]]:
    recheck = row.worker_recheck or {}
    reviewed = recheck.get("proposed_fix") or {}
    approximate = bool(recheck.get("approximate"))
    # P1 needs a confirmed time record; other flagged options need the worker's latest Yes.
    said_yes = row.policy_id != "P1" and bool(reply and reply.replied_at and reply.confirmed)
    out = []
    for option in row.fix_options:
        decision_only, default_description = ACTION_INFO.get(
            option["action"], (option["action"] in DECISION_ACTIONS, "")
        )
        confirmed = reviewed.get("option_id") == option["option_id"]
        params = (
            {**option["params"], **(reviewed.get("params") or {})}
            if confirmed
            else dict(option["params"])
        )
        label = option["label"]
        locked_reason = None
        if confirmed and option["action"] in TIME_ACTIONS and params.get("timestamp"):
            flags = "worker-confirmed, approximate" if approximate else "worker-confirmed"
            label = time_label(option, params, flags)
            if row.policy_id == "P1":  # approve refuses any other P1 time (Phase 8)
                locked_reason = f"To change it, {worker_name} must confirm a new time."
        needs_worker = bool(option.get("requires_worker_confirmation")) or row.policy_id == "P1"
        out.append(
            {
                "option_id": option["option_id"],
                "action": option["action"],
                "label": label,
                "description": option.get("description") or default_description,
                "params": params,
                "decision_only": option.get("decision_only", decision_only),
                "requires_worker_confirmation": needs_worker,
                "worker_confirmed": confirmed or said_yes,
                "note_field": REQUIRED_NOTE.get(option["action"]),
                "fields": _fields(row, option, params, locked_reason),
                "punches": _editable_punches(row, option),
                "consequence": option_consequence(row, option, params, policy),
            }
        )
    return out


# ------------------------------------------------------------------ the card


def _policy_section(sections: dict[str, str], policy_id: str) -> tuple[str, str]:
    text = sections.get(policy_id, "")
    first, _, rest = text.partition("\n")
    # "## P1: Missing punch" -> "Missing punch" (the card shows the ID separately)
    title = first.removeprefix("## ").strip().removeprefix(f"{policy_id}:").strip()
    rule = next((p.strip() for p in rest.split("\n\n") if p.strip().startswith("**Rule:**")), "")
    return title, " ".join(rule.removeprefix("**Rule:**").split())


def case_card(
    session: Session,
    policy: PolicyConfig,
    sections: dict[str, str],
    *,
    exception_id: str,
    actor_id: str,
    now: datetime,
) -> dict[str, Any]:
    actor = require_reviewer(session, actor_id)
    row = session.get(ExceptionRow, exception_id)
    if row is None:
        raise NotFoundError(f"exception {exception_id} not found", code="exception_not_found")
    if row.assigned_to != actor.employee_id:
        raise ForbiddenError(
            f"{actor.employee_id} cannot open {row.id}: it is assigned to "
            f"{row.assigned_to or 'nobody'}",
            code="not_assigned",
            details={"assigned_to": row.assigned_to, "actor_id": actor.employee_id},
        )
    employees = {e.employee_id: e for e in session.scalars(select(EmployeeRow))}
    worker = employees[row.employee_id]
    others = _others(employees, row.employee_id)
    reply = session.scalars(
        select(WorkerMessageRow)
        .where(WorkerMessageRow.exception_id == row.id)
        .order_by(WorkerMessageRow.id.desc())
    ).first()
    case = row.investigation_case or {}
    title, rule = _policy_section(sections, row.policy_id)
    evidence, hidden = own_evidence(row)
    recheck = row.worker_recheck
    card = {
        "exception_id": row.id,
        "status": row.status,
        "assigned_to": row.assigned_to,
        "employee": {"employee_id": worker.employee_id, "name": worker.name, "team": worker.team},
        "date": row.date,
        "policy_id": row.policy_id,
        "title": redact(row.title, others),
        "summary": redact(row.summary, others),
        "severity": row.severity,
        "kind": row.kind,
        "details": redact(row.details, others),
        "policy": {
            "policy_id": row.policy_id,
            "title": title,
            "rule": rule,
            "cited_text": case.get("policy_text_cited") or rule,
        },
        "evidence": evidence,
        "other_workers_evidence_hidden": hidden,
        "investigation": redact(
            {
                "what_happened": case.get("what_happened"),
                "confidence": case.get("confidence"),
                "fallback": bool(case.get("fallback")),
                "who_to_ask": case.get("who_to_ask"),
                "next_action": case.get("next_action"),
                "evidence": case.get("evidence") or [],
            }
            if case
            else None,
            others,
        ),
        "worker": (
            {
                "replied": reply.replied_at is not None,
                "confirmed": reply.confirmed,
                "reply_text": reply.reply_text,
                "replied_at": reply.replied_at,
                "needs_actual_time": reply.needs_actual_time,
            }
            if reply is not None
            else None
        ),
        "confirmed_time": (
            {
                "timestamp": recheck["timestamp"],
                "approximate": bool(recheck.get("approximate")),
                "source": recheck.get("source"),
                "option_id": (recheck.get("proposed_fix") or {}).get("option_id"),
            }
            if recheck
            else None
        ),
        "recheck": recheck["result"] if recheck else None,
        "options": card_options(row, policy, reply, worker.name),
        "applied_fix": row.applied_fix,
        "min_note_length": MIN_NOTE,
        "no_reply": no_reply.info(row, now, worker.name),
    }
    return card
