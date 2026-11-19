"""Phase 13: the demo clock's stored offset (demo mode only).

The offset lives in memory on the DemoClock and in the `settings` table (key
`demo_clock`), so it survives an API restart. Only POST /api/admin/demo/clock moves it
(forward only, audited) and a demo reset sets it back to zero. With demo mode off it is
never loaded: the clock stays at the as-of time and no timeout ever fires.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from attendflow.clock import MAX_DEMO_OFFSET, Clock, DemoClock, data_as_of
from attendflow.db.models import AuditLogRow, SettingRow
from attendflow.errors import ConflictError, InvalidInputError

log = logging.getLogger("attendflow.demo_clock")

CLOCK_KEY = "demo_clock"
HINT = "Run the scheduler (or wait for the next cycle) to apply."


def describe(clock: Clock, demo_mode: bool, hint: str | None = None) -> dict[str, Any]:
    offset = clock.offset if isinstance(clock, DemoClock) else timedelta(0)
    return {
        "now": clock.now(),
        "data_as_of": data_as_of(clock),
        "offset_hours": round(offset.total_seconds() / 3600, 2),
        "max_offset_hours": MAX_DEMO_OFFSET.total_seconds() / 3600,
        "movable": demo_mode and isinstance(clock, DemoClock),
        "hint": hint,
    }


def load(sessions: sessionmaker[Session], clock: Clock) -> None:
    """At startup in demo mode: restore the stored offset (if any)."""
    if not isinstance(clock, DemoClock):
        return
    try:
        with sessions() as session:
            row = session.get(SettingRow, CLOCK_KEY)
            minutes = float((row.value or {}).get("offset_minutes", 0)) if row else 0.0
        clock.set_offset(timedelta(minutes=minutes))
    except (SQLAlchemyError, ValueError):
        log.warning("demo clock offset not restored; starting at the as-of time")


def _store(session: Session, offset: timedelta, now: datetime, set_by: str) -> None:
    value = {"offset_minutes": offset.total_seconds() / 60, "set_by": set_by}
    row = session.get(SettingRow, CLOCK_KEY, with_for_update=True)
    if row is None:
        session.add(SettingRow(key=CLOCK_KEY, value=value, updated_at=now))
    else:
        row.value = value
        row.updated_at = now


def _require_demo_clock(clock: Clock) -> DemoClock:
    if not isinstance(clock, DemoClock):
        raise ConflictError("this server's clock is fixed", code="clock_fixed")
    return clock


def move(session: Session, clock: Clock, hours: float, actor_id: str) -> None:
    """Move the demo clock forward and audit it. Runs nothing by itself."""
    demo = _require_demo_clock(clock)
    before = demo.now()
    new_offset = demo.offset + timedelta(hours=hours)
    if new_offset > MAX_DEMO_OFFSET:
        raise InvalidInputError(
            f"the demo clock can move at most {MAX_DEMO_OFFSET.days} days past the as-of time",
            code="clock_limit",
            details={"offset_hours": demo.offset.total_seconds() / 3600},
        )
    new_now = demo.data_as_of() + new_offset
    with session.begin():  # saved first; the in-memory clock moves only after the commit
        _store(session, new_offset, new_now, actor_id)
        session.add(
            AuditLogRow(
                exception_id=None,
                actor="admin",
                actor_id=actor_id,
                action="demo_clock_moved",
                before={"now": before.isoformat()},
                after={"now": new_now.isoformat(), "hours": hours},
                reason="Demo only: the clock moved forward to show timeouts.",
                created_at=new_now,
            )
        )
    demo.set_offset(new_offset)


def reset(session: Session, clock: Clock) -> None:
    """Demo reset: back to the as-of time (inside the caller's transaction)."""
    if not isinstance(clock, DemoClock):
        return
    _store(session, timedelta(0), clock.data_as_of(), "demo_reset")
    clock.set_offset(timedelta(0))
