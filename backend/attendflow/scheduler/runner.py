"""Runs scheduler cycles on a plain background thread inside the API process.

- Off unless SCHEDULER_ENABLED=true (or POST /api/admin/scheduler/start).
- Cycles never overlap: a non-blocking lock. A cycle that would start while another is
  still running is skipped (counted), never doubled or queued.
- Start/stop is a runtime switch only; a restart goes back to the setting.
- Single API process, like the investigation jobs (the demo setup).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from attendflow.db.models import SchedulerRunRow
from attendflow.scheduler.cycle import CycleDeps, Trigger, get_watermark, run_cycle, set_watermark

log = logging.getLogger("attendflow.scheduler")


class Scheduler:
    def __init__(self, deps: CycleDeps):
        self.deps = deps
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.next_run_at: datetime | None = None
        self.overlaps_skipped = 0

    @property
    def interval(self) -> float:
        return self.deps.settings.scheduler_interval_seconds

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    def recover_interrupted(self) -> int:
        """Cycles left 'running' by a stopped process are marked failed at startup."""
        with self.deps.sessions.begin() as session:
            rows = session.scalars(
                select(SchedulerRunRow).where(SchedulerRunRow.status == "running")
            ).all()
            for row in rows:
                row.status = "failed"
                row.finished_at = datetime.now(UTC)
        return len(rows)

    def start(self) -> bool:
        """Start the timer thread. Cases detected from now on are 'new'. False if it was
        already running."""
        if self.running:
            return False
        set_watermark(self.deps.sessions, self.deps.clock, "scheduler_start")
        self._stop.clear()
        self.next_run_at = datetime.now(UTC) + timedelta(seconds=self.interval)
        self._thread = threading.Thread(target=self._loop, name="attendflow-scheduler", daemon=True)
        self._thread.start()
        log.info("scheduler started", extra={"event": "scheduler_started"})
        return True

    def stop(self, timeout: float = 5) -> bool:
        thread = self._thread
        if thread is None or not thread.is_alive():
            return False
        self._stop.set()
        thread.join(timeout)
        self._thread = None
        self.next_run_at = None
        log.info("scheduler stopped", extra={"event": "scheduler_stopped"})
        return True

    def run_once(self, trigger: Trigger, *, model_free: bool = False) -> dict[str, Any] | None:
        """Run one cycle now. None if another cycle is still running (skipped)."""
        if not self._lock.acquire(blocking=False):
            self.overlaps_skipped += 1
            log.warning(
                "scheduler cycle skipped: the previous one is still running",
                extra={"event": "scheduler_cycle_skipped", "trigger": trigger},
            )
            return None
        try:
            deps = self.deps.for_cycle()  # Phase 18: effective settings, read once per cycle
            if model_free:
                settings = replace(
                    deps.settings,
                    scheduler_investigations_per_cycle=0,
                    scheduler_messages_per_cycle=0,
                )
                deps = replace(deps, settings=settings)
            return run_cycle(deps, trigger)
        finally:
            self._lock.release()

    def _loop(self) -> None:
        while not self._stop.wait(max(0.0, self._seconds_to_next())):
            try:
                self.run_once("schedule")
            except Exception:  # noqa: BLE001 - e.g. the database is down; try next time
                log.exception("scheduler cycle crashed", extra={"event": "scheduler_cycle_error"})
            self.next_run_at = datetime.now(UTC) + timedelta(seconds=self.interval)

    def _seconds_to_next(self) -> float:
        if self.next_run_at is None:
            return self.interval
        return (self.next_run_at - datetime.now(UTC)).total_seconds()

    def status(self) -> dict[str, Any]:
        settings = self.deps.for_cycle().settings  # what the next cycle will use
        with self.deps.sessions() as session:
            last = session.scalars(
                select(SchedulerRunRow)
                .where(SchedulerRunRow.status != "running")
                .order_by(SchedulerRunRow.id.desc())
                .limit(1)
            ).first()
            watermark = get_watermark(session)
            last_out = {**(last.summary or {}), "status": last.status} if last else None
        return {
            "enabled_setting": settings.scheduler_enabled,
            "running": self.running,
            "cycle_in_progress": self.busy,
            "interval_seconds": settings.scheduler_interval_seconds,
            "investigations_per_cycle": settings.scheduler_investigations_per_cycle,
            "messages_per_cycle": settings.scheduler_messages_per_cycle,
            "backlog": settings.scheduler_backlog,
            "next_run_at": self.next_run_at if self.running else None,
            "overlaps_skipped": self.overlaps_skipped,
            "watermark": watermark,
            "last_cycle": last_out,
        }
