"""Phase 13: the no-reply ladder rules and state. Plain code, no LLM, no database writes.

A case must never wait forever for a worker. While a case waits for the worker, the
ladder takes one step at a time (cases/ladder.py runs it from the scheduler cycle):

    stage 0 -> 1  reminder   the wait reached N hours (NO_REPLY_REMINDER_HOURS)
    stage 1 -> 2  supervisor the wait reached M hours (NO_REPLY_SUPERVISOR_HOURS); the
                             case goes awaiting_worker -> awaiting_supervisor
    stage 2 -> 3  payroll    the supervisor did not act within K hours of being brought
                             in (NO_REPLY_ADMIN_HOURS); awaiting_supervisor -> escalated

Rules:
- A step fires when its limit is reached (at the limit, never before). One step per case
  per check, never skipping one, so the worker always gets the reminder before anyone
  else is brought in, even if the demo clock jumps a whole day.
- Each step fires once per wait: the stage only goes up, and the time of each step is
  stored on the case (survives restarts).
- A worker reply stops the ladder. A No that still needs the actual time starts a new
  wait; so does the supervisor asking again.
- Silence never means Yes: no step changes timecards or applies a fix. Deciding without
  the worker is a separate, explicit, audited human action (approve `without_worker`).
- Every case waiting for the worker is covered, also ones asked by hand and backlog
  cases (the Phase 11 watermark does not apply). Undone auto-resolves are skipped.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from attendflow.config import Settings
from attendflow.db.models import ExceptionRow

Step = Literal["remind", "supervisor", "admin"]

NONE, REMINDED, WITH_SUPERVISOR, WITH_ADMIN = 0, 1, 2, 3
STAGE_KEYS = {REMINDED: "reminded", WITH_SUPERVISOR: "supervisor", WITH_ADMIN: "payroll_admin"}
STAGE_LABELS = {
    REMINDED: "Reminder sent",
    WITH_SUPERVISOR: "Supervisor brought in",
    WITH_ADMIN: "Sent to payroll",
}
FILTERS = ("any", "reminded", "supervisor", "payroll_admin")

REMINDER = (
    "Reminder: we still need your answer about {date}. If we don't hear from you by "
    "{deadline}, your supervisor will review it using the records."
)
WITH_SUPERVISOR_NOTE = "Your supervisor is now reviewing this. You can still answer."
WITH_PAYROLL_NOTE = "Payroll is handling this now. Please speak to your supervisor."
DECIDED_NOTE = "Decided without your reply"


@dataclass(frozen=True)
class Limits:
    reminder: timedelta
    supervisor: timedelta
    admin: timedelta

    @classmethod
    def from_settings(cls, settings: Settings) -> Limits:
        return cls(
            reminder=timedelta(hours=settings.no_reply_reminder_hours),
            supervisor=timedelta(hours=settings.no_reply_supervisor_hours),
            admin=timedelta(hours=settings.no_reply_admin_hours),
        )


def wait_start(row: ExceptionRow) -> datetime | None:
    return row.no_reply_wait_since or row.waiting_since


def due_step(row: ExceptionRow, now: datetime, limits: Limits) -> tuple[Step, datetime] | None:
    """The next step and when it was due, or None. Pure: reads the row, changes nothing."""
    if row.auto_resolve_undone_at is not None:
        return None
    stage = row.no_reply_stage or NONE
    if row.status == "awaiting_worker":
        since = wait_start(row)
        if since is None:
            return None
        if stage == NONE and now >= since + limits.reminder:
            return "remind", since + limits.reminder
        if stage == REMINDED and now >= since + limits.supervisor:
            return "supervisor", since + limits.supervisor
        return None
    if row.status == "awaiting_supervisor" and stage == WITH_SUPERVISOR:
        brought_in = row.no_reply_supervisor_at
        if brought_in is not None and now >= brought_in + limits.admin:
            return "admin", brought_in + limits.admin
    return None


# ------------------------------------------------------------------ state changes


def start_wait(row: ExceptionRow, since: datetime) -> None:
    """A new wait for the worker (a new question, or a No that still needs the time)."""
    row.no_reply_stage = NONE
    row.no_reply_wait_since = since
    row.no_reply_reminded_at = None
    row.no_reply_supervisor_at = None
    row.no_reply_admin_at = None
    row.no_reply_late_reply_at = None


def stop(row: ExceptionRow, now: datetime) -> int:
    """The worker replied: the ladder stops. Returns the stage it was at. A reply after
    the supervisor was brought in is recorded as late."""
    stage = row.no_reply_stage or NONE
    late = row.no_reply_late_reply_at
    start_wait(row, now)
    row.no_reply_wait_since = None
    row.no_reply_late_reply_at = now if stage >= WITH_SUPERVISOR else late
    return stage


# ------------------------------------------------------------------ text


def day_text(value: datetime | Any) -> str:
    return f"{value:%a} {value.day} {value:%b}"


def stamp_text(value: datetime) -> str:
    return f"{day_text(value)} {value:%H:%M}"


def hours_text(delta: timedelta) -> str:
    hours = max(0, int(delta.total_seconds() // 3600))
    return f"{hours} h"


def reminder_text(row: ExceptionRow, limits: Limits) -> str:
    since = wait_start(row)
    assert since is not None
    return REMINDER.format(date=day_text(row.date), deadline=stamp_text(since + limits.supervisor))


def info(row: ExceptionRow, now: datetime, worker_name: str | None = None) -> dict[str, Any] | None:
    """What people see about the ladder on one case (queue badge, card, admin), or None."""
    stage = row.no_reply_stage or NONE
    late = row.no_reply_late_reply_at
    if stage == NONE and late is None:
        return None
    since = wait_start(row)
    waiting = stage > NONE and row.status not in ("resolved", "rejected")
    hours = hours_text(now - since) if waiting and since else None
    who = worker_name or "The worker"
    if stage == NONE:
        note = f"{who} replied late, after the supervisor was brought in."
    elif hours:
        note = f"{who} has not replied for {hours}."
    else:
        note = f"{who} did not reply."
    return {
        "stage": stage,
        "stage_key": STAGE_KEYS.get(stage),
        "label": STAGE_LABELS.get(stage, "Replied late"),
        "note": note,
        "hours_without_reply": hours,
        "wait_since": since if stage > NONE else None,
        "reminded_at": row.no_reply_reminded_at,
        "supervisor_at": row.no_reply_supervisor_at,
        "admin_at": row.no_reply_admin_at,
        "late_reply_at": late,
        "can_decide_without_worker": stage >= WITH_SUPERVISOR
        and row.status in ("awaiting_supervisor", "escalated"),
    }
