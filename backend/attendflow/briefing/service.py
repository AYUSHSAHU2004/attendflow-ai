"""Read, refresh and schedule briefings: caching by facts hash, rate limits, audit rows.

- `get_briefing` never calls the LLM and writes nothing. It returns the stored briefing
  when the facts are unchanged, else a fresh template from the current facts with
  `stale=true` (the card then asks for a refresh once).
- `refresh` is a person's Refresh: at most two LLM calls (one correction), refused with
  429 within BRIEFING_MIN_INTERVAL_SECONDS of the scope's last briefing or when the daily
  call budget is used up. Audit: `briefing_refresh_requested` (the person), then
  `briefing_generated` (agent, the draft passed every check) or `briefing_fallback`
  (system, template with a reason code).
- `scheduled` is step 5 of a scheduler cycle: Priya's briefing at most once per workflow
  date, only after new activity since the scheduler watermark (so not right after a demo
  reset), and only when the facts changed.

No function here touches timecards, schedule or leave.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, time
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from attendflow.briefing.facts import SECTIONS, build_packet, packet_hash, scope_key
from attendflow.briefing.generate import Generation, generate
from attendflow.briefing.validate import BriefingDraft, template_draft
from attendflow.cases.service import ROLE_TO_ACTOR
from attendflow.cases.supervisor import require_reviewer
from attendflow.clock import Clock
from attendflow.config import Settings
from attendflow.db.models import AuditLogRow, BriefingRow, EmployeeRow, ExceptionRow
from attendflow.errors import ConflictError, RateLimitedError
from attendflow.policy.models import PolicyConfig

LABELS = {
    "llm": "Written by the LLM from verified facts",
    "validation_failed": "Template (the LLM draft failed the checks)",
    "facts_changed": "Template (facts changed since the last briefing)",
    "not_generated": "Template (no briefing generated yet)",
}
UNAVAILABLE = "Template (LLM unavailable)"
# Audit actions that do not count as "new activity" for the scheduled briefing.
QUIET_ACTIONS = (
    "scheduler_cycle",
    "briefing_refresh_requested",
    "briefing_generated",
    "briefing_fallback",
)

_guard = threading.Lock()
_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)


def _scope_lock(scope: str) -> threading.Lock:
    with _guard:
        return _locks[scope]


def label(source: str, reason: str) -> str:
    if source == "llm":
        return LABELS["llm"]
    return LABELS.get(reason, UNAVAILABLE)


# ------------------------------------------------------------------ reads


def _latest(session: Session, scope: str) -> BriefingRow | None:
    return session.scalars(
        select(BriefingRow).where(BriefingRow.scope == scope).order_by(BriefingRow.id.desc())
    ).first()


def _calls_today(session: Session, now_utc: datetime) -> int:
    midnight = datetime.combine(now_utc.date(), time.min, tzinfo=UTC)
    return int(
        session.scalar(
            select(func.coalesce(func.sum(BriefingRow.llm_calls), 0)).where(
                BriefingRow.created_utc >= midnight
            )
        )
        or 0
    )


def _refresh_state(
    session: Session, settings: Settings, latest: BriefingRow | None, now_utc: datetime
) -> dict[str, Any]:
    llm_ready = bool(settings.briefing_enabled and settings.llm_api_key)
    left = max(0, settings.briefing_max_llm_calls_per_day - _calls_today(session, now_utc))
    state: dict[str, Any] = {
        "allowed": True,
        "reason": None,
        "retry_after_seconds": None,
        "calls_left_today": left,
        "llm_configured": llm_ready,
    }
    if latest is not None:
        waited = (now_utc - latest.created_utc).total_seconds()
        if waited < settings.briefing_min_interval_seconds:
            state.update(
                allowed=False,
                reason="too_soon",
                retry_after_seconds=int(settings.briefing_min_interval_seconds - waited) + 1,
            )
            return state
    if llm_ready and left < 1:
        tomorrow = datetime.combine(now_utc.date(), time.min, tzinfo=UTC).timestamp() + 86400
        state.update(
            allowed=False,
            reason="daily_cap",
            retry_after_seconds=int(tomorrow - now_utc.timestamp()) + 1,
        )
    return state


def _view(
    *,
    scope: str,
    packet: dict[str, Any],
    draft: BriefingDraft,
    source: str,
    reason: str,
    stale: bool,
    row: BriefingRow | None,
    generated_at: datetime,
    refresh: dict[str, Any],
) -> dict[str, Any]:
    by_section: dict[str, list[dict[str, Any]]] = {key: [] for key in SECTIONS}
    for bullet in draft.bullets:
        by_section[bullet.section].append({"text": bullet.text, "case_ids": bullet.case_ids})
    return {
        "scope": "all" if scope == "all" else "team",
        "team": packet["team"],
        "source": source,
        "reason": reason,
        "label": label(source, reason),
        "stale": stale,
        "stored": row is not None,
        "briefing_id": row.id if row is not None else None,
        "headline": draft.headline,
        "sections": [
            {"key": key, "title": title, "bullets": by_section[key]}
            for key, title in SECTIONS.items()
            if by_section[key]
        ],
        "team_lines": [line.model_dump() for line in draft.team_lines],
        "generated_at": generated_at,
        "facts_hash": (row.facts_hash if row is not None else packet_hash(packet))[:12],
        "llm_calls": row.llm_calls if row is not None else 0,
        "latency_ms": row.latency_ms if row is not None else None,
        "failed_checks": sorted(
            {c for a in (row.attempts if row is not None else []) for c in a.get("checks", [])}
        ),
        "refresh": refresh,
    }


def _row_view(row: BriefingRow, packet: dict[str, Any], refresh: dict[str, Any]) -> dict:
    return _view(
        scope=row.scope,
        packet=packet,
        draft=BriefingDraft.model_validate(row.content),
        source=row.source,
        reason=row.reason,
        stale=False,
        row=row,
        generated_at=row.workflow_at,
        refresh=refresh,
    )


def get_briefing(
    session: Session, actor_id: str, clock: Clock, policy: PolicyConfig, settings: Settings
) -> dict[str, Any]:
    actor = require_reviewer(session, actor_id)
    scope = scope_key(actor)
    packet = build_packet(session, actor_id, clock, policy, settings)
    latest = _latest(session, scope)
    refresh = _refresh_state(session, settings, latest, datetime.now(UTC))
    if latest is not None and latest.facts_hash == packet_hash(packet):
        return _row_view(latest, packet, refresh)
    return _view(
        scope=scope,
        packet=packet,
        draft=template_draft(packet),
        source="template",
        reason="facts_changed" if latest is not None else "not_generated",
        stale=True,
        row=None,
        generated_at=clock.now(),
        refresh=refresh,
    )


# ------------------------------------------------------------------ writes


def _context(session: Session) -> tuple[set[str], dict[str, str]]:
    known = set(session.scalars(select(ExceptionRow.id)))
    people = {e.employee_id: e.name for e in session.scalars(select(EmployeeRow))}
    return known, people


def _store(
    session: Session,
    *,
    scope: str,
    packet: dict[str, Any],
    gen: Generation,
    settings: Settings,
    clock: Clock,
    trigger: str,
    requested_by: str | None,
) -> BriefingRow:
    row = BriefingRow(
        scope=scope,
        facts_hash=packet_hash(packet),
        facts=packet,
        content=gen.draft.model_dump(),
        source=gen.source,
        reason=gen.reason,
        attempts=gen.attempts,
        llm_calls=gen.llm_calls,
        model=settings.llm_model if gen.llm_calls else None,
        latency_ms=gen.latency_ms,
        trigger=trigger,
        requested_by=requested_by,
        workflow_at=clock.now(),
        created_utc=datetime.now(UTC),
    )
    session.add(row)
    session.flush()
    after = {
        "scope": scope,
        "briefing_id": row.id,
        "trigger": trigger,
        "reason": gen.reason,
        "llm_calls": gen.llm_calls,
        "failed_checks": gen.failed_checks,
        "latency_ms": gen.latency_ms,
    }
    session.add(
        AuditLogRow(
            exception_id=None,
            actor="agent" if gen.source == "llm" else "system",
            actor_id=None,
            action="briefing_generated" if gen.source == "llm" else "briefing_fallback",
            after=after,
            created_at=clock.now(),
        )
    )
    return row


def refresh(
    sessions: sessionmaker[Session],
    actor_id: str,
    clock: Clock,
    policy: PolicyConfig,
    settings: Settings,
    *,
    chat_model: Callable | None = None,
) -> dict[str, Any]:
    with sessions() as session:
        actor = require_reviewer(session, actor_id)
        scope = scope_key(actor)
        role = actor.role
    lock = _scope_lock(scope)
    if not lock.acquire(blocking=False):
        raise ConflictError("a briefing is already being written", code="briefing_busy")
    try:
        with sessions.begin() as session:
            packet = build_packet(session, actor_id, clock, policy, settings)
            state = _refresh_state(session, settings, _latest(session, scope), datetime.now(UTC))
            if not state["allowed"]:
                raise RateLimitedError(
                    "Refresh is not available yet"
                    if state["reason"] == "too_soon"
                    else "Today's briefing budget is used up",
                    code=f"briefing_{state['reason']}",
                    details={"retry_after_seconds": state["retry_after_seconds"]},
                )
            known, people = _context(session)
            session.add(
                AuditLogRow(
                    exception_id=None,
                    actor=ROLE_TO_ACTOR[role],
                    actor_id=actor_id,
                    action="briefing_refresh_requested",
                    after={"scope": scope},
                    created_at=clock.now(),
                )
            )
        # The model call runs outside any transaction.
        gen = generate(
            settings,
            packet,
            known_case_ids=known,
            all_people=people,
            max_calls=state["calls_left_today"],
            chat_model=chat_model,
        )
        with sessions.begin() as session:
            row = _store(
                session,
                scope=scope,
                packet=packet,
                gen=gen,
                settings=settings,
                clock=clock,
                trigger="refresh",
                requested_by=actor_id,
            )
            state = _refresh_state(session, settings, row, datetime.now(UTC))
            return _row_view(row, packet, state)
    finally:
        lock.release()


def scheduled(
    sessions: sessionmaker[Session],
    settings: Settings,
    clock: Clock,
    policy: PolicyConfig,
    *,
    watermark: int,
    chat_model: Callable | None = None,
) -> dict[str, Any]:
    """Scheduler step 5: Priya's briefing, at most once per workflow date."""
    if not settings.briefing_scheduled:
        return {"status": "skipped", "reason": "disabled"}
    lock = _scope_lock("all")
    if not lock.acquire(blocking=False):
        return {"status": "skipped", "reason": "busy"}
    try:
        with sessions() as session:
            admin_id = session.scalar(
                select(EmployeeRow.employee_id)
                .where(EmployeeRow.role == "payroll_admin")
                .order_by(EmployeeRow.employee_id)
            )
            if admin_id is None:
                return {"status": "skipped", "reason": "no_payroll_admin"}
            today = clock.now().date()
            done_today = session.scalar(
                select(func.count(BriefingRow.id)).where(
                    BriefingRow.scope == "all",
                    BriefingRow.trigger == "scheduler",
                    BriefingRow.workflow_at >= datetime.combine(today, time.min),
                )
            )
            if done_today:
                return {"status": "skipped", "reason": "already_today"}
            new_activity = session.scalar(
                select(func.count(AuditLogRow.id)).where(
                    AuditLogRow.id > watermark, AuditLogRow.action.notin_(QUIET_ACTIONS)
                )
            )
            if not new_activity:
                return {"status": "skipped", "reason": "no_new_activity"}
            packet = build_packet(session, admin_id, clock, policy, settings)
            latest = _latest(session, "all")
            if latest is not None and latest.facts_hash == packet_hash(packet):
                return {"status": "skipped", "reason": "facts_unchanged"}
            state = _refresh_state(session, settings, latest, datetime.now(UTC))
            if not state["allowed"]:
                return {"status": "skipped", "reason": state["reason"]}
            known, people = _context(session)
        gen = generate(
            settings,
            packet,
            known_case_ids=known,
            all_people=people,
            max_calls=state["calls_left_today"],
            chat_model=chat_model,
        )
        with sessions.begin() as session:
            row = _store(
                session,
                scope="all",
                packet=packet,
                gen=gen,
                settings=settings,
                clock=clock,
                trigger="scheduler",
                requested_by=None,
            )
            return {
                "status": "generated" if gen.source == "llm" else "fallback",
                "reason": gen.reason,
                "briefing_id": row.id,
                "llm_calls": gen.llm_calls,
            }
    finally:
        lock.release()
