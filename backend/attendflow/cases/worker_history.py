"""Phase 17: "What happened to my case" for the worker. Read-only, worker-scoped, no LLM.

A worker sees only cases about themselves that they were asked about: each question,
their own answer, and the outcome in plain words built by code. Text from other people
is never shown, except the reason for a decision taken without the worker's reply,
which the inbox already shows (Phase 13). A supervisor's reject reason is not shown.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from attendflow.cases.no_reply import DECIDED_NOTE
from attendflow.db.models import EmployeeRow, ExceptionRow, WorkerMessageRow
from attendflow.errors import ForbiddenError
from attendflow.fixes.params import DECISION_ACTIONS


def _require_worker(session: Session, actor_id: str) -> EmployeeRow:
    actor = session.get(EmployeeRow, actor_id)
    if actor is None:
        raise ForbiddenError(f"unknown actor {actor_id}", code="unknown_actor")
    if actor.role != "worker":
        raise ForbiddenError("only a worker can read their history", code="worker_inbox_only")
    return actor


def outcome(row: ExceptionRow) -> dict[str, Any]:
    """The case's state in the worker's words (state key, text, optional reason)."""
    fix = row.applied_fix or {}
    label = str(fix.get("label") or "").rstrip(".")
    if row.status == "awaiting_worker":
        return {"state": "waiting_for_you", "text": "Waiting for your answer.", "reason": None}
    if row.status in {"open", "awaiting_supervisor"}:
        return {
            "state": "with_supervisor",
            "text": "Your supervisor is reviewing it.",
            "reason": None,
        }
    if row.status == "escalated":
        return {"state": "with_payroll", "text": "Payroll is reviewing it.", "reason": None}
    if row.status == "rejected":
        return {
            "state": "closed_no_change",
            "text": "Closed by payroll. Your record was not changed.",
            "reason": None,
        }
    if fix.get("without_worker"):
        return {
            "state": "decided_without_reply",
            "text": f"{DECIDED_NOTE}: {label}." if label else f"{DECIDED_NOTE}.",
            "reason": fix["without_worker"].get("reason"),
        }
    if label and fix.get("action") in DECISION_ACTIONS:
        return {"state": "decided", "text": f"Your supervisor decided: {label}.", "reason": None}
    if label:
        return {"state": "fixed", "text": f"Fixed: {label}.", "reason": None}
    return {
        "state": "closed_no_change",
        "text": "Closed. The records no longer show a problem.",
        "reason": None,
    }


def _answer(m: WorkerMessageRow) -> dict[str, Any] | None:
    if m.confirmed is None and not m.reply_text:
        return None
    review = m.time_review or {}
    stamp = review.get("timestamp") if review.get("stage") == "confirmed" else None
    return {
        "confirmed": m.confirmed,
        "text": m.reply_text,
        "time": stamp[11:16] if isinstance(stamp, str) and len(stamp) >= 16 else None,
        "replied_at": m.replied_at,
    }


def worker_history(session: Session, actor_id: str) -> dict[str, Any]:
    _require_worker(session, actor_id)
    rows = session.execute(
        select(WorkerMessageRow, ExceptionRow)
        .join(ExceptionRow, WorkerMessageRow.exception_id == ExceptionRow.id)
        .where(
            WorkerMessageRow.recipient_id == actor_id,
            ExceptionRow.employee_id == actor_id,
        )
        .order_by(WorkerMessageRow.id)
    ).all()
    cases: dict[str, dict[str, Any]] = {}
    for m, row in rows:
        item = cases.setdefault(
            row.id,
            {
                "exception_id": row.id,
                "date": row.date,
                "questions": [],
                "outcome": outcome(row),
                "updated_at": row.updated_at,
            },
        )
        item["questions"].append(
            {
                "asked_at": m.sent_at,
                "message": m.message,
                "reminded_at": m.reminded_at,
                "answer": _answer(m),
            }
        )
    items = sorted(cases.values(), key=lambda c: (c["date"], c["exception_id"]), reverse=True)
    return {"items": items}
