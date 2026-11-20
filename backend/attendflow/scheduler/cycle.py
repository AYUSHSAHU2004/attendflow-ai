"""One scheduler cycle. Code decides what to do; the LLM only runs inside the existing
investigate and ask-worker steps, which keep their template fallbacks.

A cycle:
1. runs detection for everyone (idempotent: upsert by stable ID, never duplicates);
2. investigates open cases that have no stored investigation yet (or whose engine facts
   changed since), newest first, at most `scheduler_investigations_per_cycle`, one at a
   time, so a rate-limited provider is never flooded;
3. sends the worker message for open cases whose stored investigation routes to the
   worker, at most `scheduler_messages_per_cycle`, acting as "system";
4. runs the no-reply ladder (Phase 13, cases/ladder.py): reminder, then the supervisor,
   then payroll, for cases still waiting for a reply. It covers EVERY case waiting for a
   worker, also hand-asked and backlog ones (the watermark below does not apply to it),
   and skips undone cases. No LLM, no data changes;
5. writes Priya's daily briefing (Phase 17, briefing/service.py): at most once per
   workflow date, only after new activity since the watermark and when the facts changed;
   at most two LLM calls, else the template. No data changes;
6. stores a summary (scheduler_runs + one `scheduler_cycle` audit row).

Backlog rule: by default only cases first detected AFTER the watermark are touched. The
watermark is the audit-log ID at the moment the scheduler started (or a demo reset, or
the first cycle if neither happened). Older cases are counted as `skipped_backlog` and
left for the manual walkthrough. SCHEDULER_BACKLOG=true processes them too.

Auto-resolved cases are resolved, so the scheduler never sees them. A case a person
undid (Phase 12) is never investigated or messaged automatically, even with
SCHEDULER_BACKLOG=true: it is counted as `skipped_undone` and left to people.

An error on one case is recorded and the cycle moves on to the next.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from attendflow.agent.jobs import InvestigationJobs
from attendflow.briefing import service as briefing_service
from attendflow.cases import ladder, service
from attendflow.cases.facts import facts_hash
from attendflow.clock import Clock
from attendflow.config import Settings
from attendflow.db.models import (
    AuditLogRow,
    ExceptionRow,
    InvestigationJobRow,
    SchedulerRunRow,
    SettingRow,
    WorkerMessageRow,
)
from attendflow.errors import AppError
from attendflow.policy.models import PolicyConfig
from attendflow.runtime_settings import SettingsReader

log = logging.getLogger("attendflow.scheduler")

Trigger = Literal["schedule", "run_now"]
WATERMARK_KEY = "scheduler_watermark"
SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
AUTO_NOTE = "Sent automatically by the scheduler."


@dataclass
class CycleDeps:
    sessions: sessionmaker[Session]
    settings: Settings  # the server's values; runtime overrides are applied per cycle
    policy: PolicyConfig
    clock: Clock
    jobs: InvestigationJobs
    reader: SettingsReader | None = None  # Phase 18 runtime settings

    def for_cycle(self) -> CycleDeps:
        """A copy with the effective settings read once, at the start of a cycle. The
        whole cycle uses this one frozen copy, so a change made while it runs applies from
        the next cycle (never half-way through one)."""
        if self.reader is None:
            return self
        return replace(self, settings=self.reader.apply(self.settings))


# ------------------------------------------------------------------ watermark


def set_watermark(sessions: sessionmaker[Session], clock: Clock, set_by: str) -> int:
    """From now on, only cases detected after this point are 'new' for the scheduler."""
    with sessions.begin() as session:
        audit_id = int(session.scalar(select(func.coalesce(func.max(AuditLogRow.id), 0))))
        value = {
            "audit_id": audit_id,
            "set_by": set_by,
            "set_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        row = session.get(SettingRow, WATERMARK_KEY, with_for_update=True)
        if row is None:
            session.add(SettingRow(key=WATERMARK_KEY, value=value, updated_at=clock.now()))
        else:
            row.value = value
            row.updated_at = clock.now()
    return audit_id


def get_watermark(session: Session) -> dict[str, Any] | None:
    row = session.get(SettingRow, WATERMARK_KEY)
    return dict(row.value) if row is not None else None


# ------------------------------------------------------------------ selection


@dataclass
class Candidate:
    exception_id: str
    detected_audit_id: int
    severity: str
    eligible: bool  # detected after the watermark (or backlog processing is on), not undone
    needs_investigation: bool
    needs_message: bool
    undone: bool = False  # a person undid its auto-resolve: people own it, never automatic


def candidates(session: Session, watermark: int, backlog: bool) -> list[Candidate]:
    """Open cases with what the scheduler would do for each, newest first."""
    detected = dict(
        session.execute(
            select(AuditLogRow.exception_id, func.min(AuditLogRow.id))
            .where(AuditLogRow.action == "detected")
            .group_by(AuditLogRow.exception_id)
        ).all()
    )
    asked = set(session.scalars(select(WorkerMessageRow.exception_id).distinct()))
    running = set(
        session.scalars(
            select(InvestigationJobRow.exception_id).where(InvestigationJobRow.status == "running")
        )
    )
    rows = session.scalars(select(ExceptionRow).where(ExceptionRow.status == "open")).all()
    out = []
    for row in rows:
        detected_id = detected.get(row.id, 0)
        case = row.investigation_case
        # A stored hash that no longer matches = the engine facts changed since. A case
        # stored before Phase 11 has no hash and counts as investigated.
        stale = (
            case is not None
            and row.investigated_facts_hash is not None
            and row.investigated_facts_hash != facts_hash(row)
        )
        undone = row.auto_resolve_undone_at is not None
        out.append(
            Candidate(
                exception_id=row.id,
                detected_audit_id=detected_id,
                severity=row.severity,
                eligible=not undone and (backlog or detected_id > watermark),
                undone=undone,
                needs_investigation=(case is None or stale) and row.id not in running,
                needs_message=(
                    case is not None
                    and not stale
                    and case.get("who_to_ask") == "worker"
                    and row.id not in asked
                ),
            )
        )
    # Newest first (a case from a fresh punch goes next), then the most severe.
    out.sort(key=lambda c: (-c.detected_audit_id, SEVERITY_RANK.get(c.severity, 9), c.exception_id))
    return out


# ------------------------------------------------------------------ the cycle


def _error(exception_id: str | None, step: str, exc: Exception) -> dict[str, Any]:
    # Stored error text is code-built: an AppError's code and message, else the type only.
    text = f"{exc.code}: {exc.message}" if isinstance(exc, AppError) else type(exc).__name__
    return {"exception_id": exception_id, "step": step, "error": text[:300]}


def _audit(
    deps: CycleDeps,
    exception_id: str | None,
    action: str,
    after: dict[str, Any],
    reason: str | None = None,
) -> None:
    with deps.sessions.begin() as session:
        session.add(
            AuditLogRow(
                exception_id=exception_id,
                actor="system",
                actor_id=None,
                action=action,
                after=after,
                reason=reason,
                created_at=deps.clock.now(),
            )
        )


def _investigate(deps: CycleDeps, exception_id: str, cycle_id: int) -> dict[str, Any] | None:
    job, created = deps.jobs.start(exception_id, None)
    if not created:  # someone started one by hand; leave it to them
        return None
    _audit(
        deps,
        exception_id,
        "auto_investigation_started",
        {"job_id": job.id, "cycle_id": cycle_id},
        reason="Started automatically by the scheduler.",
    )
    deps.jobs.run(job.id)
    with deps.sessions() as session:
        done = session.get(InvestigationJobRow, job.id)
        case = session.get(ExceptionRow, exception_id).investigation_case or {}
        result = {
            "exception_id": exception_id,
            "job_id": job.id,
            "job_status": done.status,
            "reason": done.reason,
            "fallback": bool(case.get("fallback")),
            "who_to_ask": case.get("who_to_ask"),
            "duration_ms": done.duration_ms,
        }
    _audit(deps, exception_id, "auto_investigation_finished", {**result, "cycle_id": cycle_id})
    return result


def _new_summary(cycle_id: int, trigger: Trigger, deps: CycleDeps, started, watermark: int):
    return {
        "cycle_id": cycle_id,
        "trigger": trigger,
        "as_of": deps.clock.now().isoformat(timespec="seconds"),
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": None,
        "duration_ms": None,
        "backlog": deps.settings.scheduler_backlog,
        "watermark_audit_id": watermark,
        "detection": None,
        "detected": 0,
        "new": 0,
        "new_exception_ids": [],
        "closed_exception_ids": [],
        "investigated": [],
        "messages_sent": [],
        "skipped_budget": [],
        "skipped_message_budget": [],
        "skipped_backlog": 0,
        "skipped_undone": 0,
        "no_reply": {
            "enabled": deps.settings.no_reply_escalation_enabled,
            "reminded": [],
            "to_supervisor": [],
            "to_admin": [],
        },
        "briefing": None,
        "errors": [],
    }


def counts(summary: dict[str, Any]) -> dict[str, int]:
    return {
        "detected": summary["detected"],
        "new": summary["new"],
        "investigated": len(summary["investigated"]),
        "messages_sent": len(summary["messages_sent"]),
        "skipped_budget": len(summary["skipped_budget"]),
        "skipped_message_budget": len(summary["skipped_message_budget"]),
        "skipped_backlog": summary["skipped_backlog"],
        "skipped_undone": summary["skipped_undone"],
        "reminded": len(summary["no_reply"]["reminded"]),
        "to_supervisor": len(summary["no_reply"]["to_supervisor"]),
        "to_admin": len(summary["no_reply"]["to_admin"]),
        "errors": len(summary["errors"]),
    }


def run_cycle(deps: CycleDeps, trigger: Trigger) -> dict[str, Any]:
    """Run one cycle and return its summary. The caller makes sure cycles never overlap."""
    settings = deps.settings
    started = datetime.now(UTC)
    t0 = time.monotonic()
    with deps.sessions.begin() as session:
        run = SchedulerRunRow(trigger=trigger, status="running", started_at=started)
        session.add(run)
        session.flush()
        cycle_id = run.id
        mark = get_watermark(session)
    watermark = (
        int(mark["audit_id"])
        if mark is not None
        else set_watermark(deps.sessions, deps.clock, "first_cycle")
    )
    summary = _new_summary(cycle_id, trigger, deps, started, watermark)

    # 1. Detection for everyone.
    try:
        with deps.sessions() as session:
            det = service.run_detection(
                session, deps.policy, deps.clock, auto_resolve=settings.auto_resolve_enabled
            )
        summary.update(
            detection="ok",
            detected=det.found,
            new=det.created,
            new_exception_ids=det.created_ids,
            closed_exception_ids=det.closed_no_longer_detected,
        )
    except Exception as exc:  # noqa: BLE001 - the cycle goes on with what is stored
        log.exception("scheduler detection failed", extra={"event": "scheduler_detection_failed"})
        summary["detection"] = "failed"
        summary["errors"].append(_error(None, "detection", exc))

    # 2. Investigations: new cases only, newest first, within the budget, one at a time.
    with deps.sessions() as session:
        found = candidates(session, watermark, settings.scheduler_backlog)
    summary["skipped_backlog"] = sum(
        1
        for c in found
        if not c.eligible and not c.undone and (c.needs_investigation or c.needs_message)
    )
    summary["skipped_undone"] = sum(
        1 for c in found if c.undone and (c.needs_investigation or c.needs_message)
    )
    for c in (c for c in found if c.eligible and c.needs_investigation):
        if len(summary["investigated"]) >= settings.scheduler_investigations_per_cycle:
            summary["skipped_budget"].append(c.exception_id)
            continue
        try:
            result = _investigate(deps, c.exception_id, cycle_id)
            if result is not None:
                summary["investigated"].append(result)
        except Exception as exc:  # noqa: BLE001 - one bad case never stops the cycle
            log.exception(
                "scheduler investigation failed",
                extra={"event": "scheduler_investigation_failed", "exception_id": c.exception_id},
            )
            summary["errors"].append(_error(c.exception_id, "investigate", exc))

    # 3. Worker messages for cases routed to the worker (including the ones just done).
    with deps.sessions() as session:
        found = candidates(session, watermark, settings.scheduler_backlog)
    for c in (c for c in found if c.eligible and c.needs_message):
        if len(summary["messages_sent"]) >= settings.scheduler_messages_per_cycle:
            summary["skipped_message_budget"].append(c.exception_id)
            continue
        try:
            with deps.sessions() as session:
                service.ask_worker(
                    session,
                    deps.clock,
                    settings,
                    exception_id=c.exception_id,
                    actor_id=None,
                    note=AUTO_NOTE,
                )
            summary["messages_sent"].append(c.exception_id)
        except Exception as exc:  # noqa: BLE001
            log.exception(
                "scheduler message failed",
                extra={"event": "scheduler_message_failed", "exception_id": c.exception_id},
            )
            summary["errors"].append(_error(c.exception_id, "ask_worker", exc))

    # 4. The no-reply ladder (every case waiting for a worker; no LLM, no data changes).
    try:
        steps = ladder.run_ladder(deps.sessions, settings, deps.clock)
        summary["errors"].extend(steps.pop("errors"))
        summary["no_reply"] = steps
    except Exception as exc:  # noqa: BLE001 - e.g. the database is down; next cycle retries
        log.exception("no-reply ladder failed", extra={"event": "no_reply_ladder_failed"})
        summary["errors"].append(_error(None, "no_reply", exc))

    # 5. Priya's daily briefing (Phase 17): once per workflow date, only after new activity
    #    since the watermark and when the facts changed; never changes data.
    try:
        summary["briefing"] = briefing_service.scheduled(
            deps.sessions, settings, deps.clock, deps.policy, watermark=watermark
        )
    except Exception as exc:  # noqa: BLE001 - the briefing is optional; next cycle retries
        log.exception("scheduled briefing failed", extra={"event": "briefing_failed"})
        summary["errors"].append(_error(None, "briefing", exc))

    # 6. Summary: scheduler_runs row + one audit row Priya can read.
    finished = datetime.now(UTC)
    summary["finished_at"] = finished.isoformat(timespec="seconds")
    summary["duration_ms"] = round((time.monotonic() - t0) * 1000, 1)
    status = "failed" if summary["detection"] == "failed" else "completed"
    totals = counts(summary)
    with deps.sessions.begin() as session:
        run = session.get(SchedulerRunRow, cycle_id)
        run.status = status
        run.finished_at = finished
        run.summary = summary
        session.add(
            AuditLogRow(
                exception_id=None,
                actor="system",
                actor_id=None,
                action="scheduler_cycle",
                after={
                    "cycle_id": cycle_id,
                    "trigger": trigger,
                    "status": status,
                    **totals,
                    "new_exception_ids": summary["new_exception_ids"],
                    "investigated_ids": [i["exception_id"] for i in summary["investigated"]],
                    "messages_sent": summary["messages_sent"],
                    "no_reply": summary["no_reply"],
                    "briefing": summary["briefing"],
                    "duration_ms": summary["duration_ms"],
                },
                created_at=deps.clock.now(),
            )
        )
    log.info("scheduler cycle", extra={"event": "scheduler_cycle", "cycle_id": cycle_id, **totals})
    return {**summary, "status": status}
