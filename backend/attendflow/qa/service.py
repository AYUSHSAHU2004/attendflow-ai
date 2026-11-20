"""Phase 20: ask a question, read your own question history, and Priya's read-only list.

`ask` is the only writer here, and it writes only its own `worker_questions` row and one
audit row (no free text) in one transaction. It never touches timecards, schedule or
leave, and imports no writer. The order of a question:

1. who asks (a worker; the employee ID is the request's actor), the length cap, the
   per-worker hourly limit (429 qa_rate_limited) and the per-worker lock (409 qa_busy);
2. code refusals before any LLM call (other people, pay, changes, rule-changing text,
   other languages), then the keyword plan and its dates (out of range = refusal);
3. the model's intent pick only when the keywords found nothing or too much;
4. the facts packet (read-only), the fixed "ask your supervisor" line for a day whose only
   case is a P17 case, else the answer call (one correction at most) or the template;
5. the stored row and its audit row: `qa_answered` (agent), `qa_fallback` (system, reason
   code) or `qa_refused` (system, refusal code).
"""

from __future__ import annotations

import threading
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from time import monotonic
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from attendflow.cases.admin import require_admin
from attendflow.clock import Clock, data_as_of
from attendflow.config import Settings
from attendflow.db.models import AuditLogRow, EmployeeRow, WorkerQuestionRow
from attendflow.errors import AppError, ConflictError, RateLimitedError
from attendflow.grounding import CASE_ID, POLICY_ID
from attendflow.policy.models import PolicyConfig, load_policy_text
from attendflow.qa.facts import Facts, build_facts, facts_hash, load_people, require_worker
from attendflow.qa.generate import Budget, choose_intents, write_answer
from attendflow.qa.intents import INTENT_WORDS, People, date_range, keyword_plan, precheck
from attendflow.qa.validate import (
    SourceRef,
    packet_sources,
    refusal_text,
    template_answer,
)

HISTORY_LIMIT = 20
MAX_HISTORY_LIMIT = 50
LABELS = {"llm": "AI answer", "template": "Template answer", "refusal": "Can't answer"}
SOURCE_LABELS = {
    "leave_balance": "Your leave balance",
    "schedule": "Your schedule",
    "punches": "Your punches",
    "supervisor": "Your supervisor",
}

_guard = threading.Lock()
_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)


def _worker_lock(employee_id: str) -> threading.Lock:
    with _guard:
        return _locks[employee_id]


class QuestionTooLongError(AppError):
    status_code = 422
    code = "question_too_long"


# ------------------------------------------------------------------ limits


def _midnight(now_utc: datetime) -> datetime:
    return datetime.combine(now_utc.date(), time.min, tzinfo=UTC)


def calls_today(session: Session, now_utc: datetime) -> int:
    return int(
        session.scalar(
            select(func.coalesce(func.sum(WorkerQuestionRow.llm_calls), 0)).where(
                WorkerQuestionRow.created_utc >= _midnight(now_utc)
            )
        )
        or 0
    )


def limits(
    session: Session, settings: Settings, employee_id: str, now_utc: datetime
) -> dict[str, Any]:
    window = now_utc - timedelta(hours=1)
    recent = list(
        session.scalars(
            select(WorkerQuestionRow.created_utc)
            .where(
                WorkerQuestionRow.employee_id == employee_id,
                WorkerQuestionRow.created_utc > window,
            )
            .order_by(WorkerQuestionRow.created_utc)
        )
    )
    left = max(0, settings.qa_questions_per_hour - len(recent))
    retry = None
    if left == 0 and recent:
        oldest = recent[-settings.qa_questions_per_hour]  # the one that must expire first
        retry = max(1, int((oldest + timedelta(hours=1) - now_utc).total_seconds()) + 1)
    return {
        "max_chars": settings.qa_max_question_chars,
        "questions_per_hour": settings.qa_questions_per_hour,
        "questions_left_this_hour": left,
        "retry_after_seconds": retry,
        "llm_configured": bool(settings.qa_enabled and settings.llm_api_key),
        "llm_calls_left_today": max(
            0, settings.qa_max_llm_calls_per_day - calls_today(session, now_utc)
        ),
    }


# ------------------------------------------------------------------ views


def _source_view(ref: dict[str, Any], details: dict[str, Any]) -> dict[str, Any]:
    kind, ident = ref["kind"], ref.get("id")
    view: dict[str, Any] = {"kind": kind, "id": ident, "label": SOURCE_LABELS.get(kind, ident)}
    if kind == "policy":
        policy = details.get("policies", {}).get(ident) or {}
        view["label"] = f"{ident}: {policy.get('title')}" if policy.get("title") else ident
        view["text"] = policy.get("text")
    elif kind == "case":
        case = details.get("cases", {}).get(ident) or {}
        view["label"] = f"{case.get('policy_id', 'Case')} · {case.get('date', '')}".strip(" ·")
        view["text"] = (
            f"{case.get('summary', '').rstrip('.')}. Status: "
            f"{case.get('status_words') or case.get('where_it_is', '')}".rstrip(". ")
            if case
            else None
        )
        view["in_history"] = bool(case.get("in_history"))
    return view


def row_view(row: WorkerQuestionRow) -> dict[str, Any]:
    details: dict[str, dict[str, Any]] = {"policies": {}, "cases": {}}
    refs = [s for s in row.sources or [] if isinstance(s, dict) and "kind" in s]
    for s in refs:
        if s["kind"] == "policy":
            details["policies"][s.get("id")] = {"title": s.get("title"), "text": s.get("text")}
        elif s["kind"] == "case":
            details["cases"][s.get("id")] = s
    return {
        "question_id": row.id,
        "question": row.question,
        "kind": row.kind,
        "source": row.source,
        "label": LABELS[row.source],
        "reason": row.reason,
        "refusal_code": row.refusal_code,
        "answer": row.answer,
        "sources": [_source_view(s, details) for s in refs],
        "intents": list(row.intents or []),
        "asked_at": row.workflow_at,
        "llm_calls": row.llm_calls,
        "latency_ms": row.latency_ms,
    }


def _stored_sources(refs: list[SourceRef], facts: Facts | None) -> list[dict[str, Any]]:
    """The cited sources with the code-held detail the chips show (policy text, case
    summary). Kept with the row so the history shows the same chips later."""
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()
    for ref in refs:
        key = (ref.kind, ref.id)
        if key in seen:
            continue
        seen.add(key)
        item: dict[str, Any] = {"kind": ref.kind, "id": ref.id}
        if facts is not None and ref.kind == "policy" and ref.id:
            brief = next(
                (p for p in facts.packet.get("policies", []) if p["policy_id"] == ref.id), None
            )
            case_policy = next(
                (c for c in facts.case_details.values() if c["policy_id"] == ref.id), None
            )
            item["title"] = (brief or {}).get("title") or (case_policy or {}).get("title")
            item["text"] = facts.policy_sections.get(ref.id)
        elif facts is not None and ref.kind == "case" and ref.id in facts.case_details:
            c = facts.case_details[ref.id]
            item.update(
                policy_id=c["policy_id"],
                date=c["date"],
                summary=c["summary"],
                status_words=c["status_words"],
                in_history=c["in_history"],
            )
        out.append(item)
    return out


def _answer_refs(answer: str, cited: list[SourceRef], facts: Facts) -> list[SourceRef]:
    """The model's validated citations plus any case or policy ID the answer names. No
    fallback: an answer that cites nothing (say, "I can't answer that") shows no sources."""
    refs = list(cited)
    known_cases = set(facts.case_details)
    for cid in CASE_ID.findall(answer):
        if cid in known_cases:
            refs.append(SourceRef(kind="case", id=cid))
    for pid in POLICY_ID.findall(CASE_ID.sub(" ", answer)):
        if pid in facts.policy_sections:
            refs.append(SourceRef(kind="policy", id=pid))
    return refs


# ------------------------------------------------------------------ ask


def ask(
    sessions: sessionmaker[Session],
    actor_id: str,
    question: str,
    clock: Clock,
    policy: PolicyConfig,
    settings: Settings,
    *,
    chat_model: Callable | None = None,
) -> dict[str, Any]:
    question = " ".join(question.split())
    with sessions() as session:
        asker = require_worker(session, actor_id)
        people = load_people(session, asker)
    if len(question) > settings.qa_max_question_chars:
        raise QuestionTooLongError(
            f"Please keep your question under {settings.qa_max_question_chars} characters.",
            details={"max_chars": settings.qa_max_question_chars},
        )
    lock = _worker_lock(actor_id)
    if not lock.acquire(blocking=False):
        raise ConflictError("your previous question is still being answered", code="qa_busy")
    try:
        now_utc = datetime.now(UTC)
        with sessions() as session:
            state = limits(session, settings, actor_id, now_utc)
        if state["questions_left_this_hour"] < 1:
            raise RateLimitedError(
                "You have asked a lot of questions this hour. Please try again later.",
                code="qa_rate_limited",
                details={"retry_after_seconds": state["retry_after_seconds"]},
            )
        outcome = _answer(sessions, people, question, clock, policy, settings, state, chat_model)
        with sessions.begin() as session:
            row = _store(session, people, question, outcome, settings, clock)
            view = row_view(row)
            view["limits"] = limits(session, settings, actor_id, datetime.now(UTC))
            return view
    finally:
        lock.release()


class _Outcome:
    def __init__(self) -> None:
        self.kind = "answer"
        self.source = "template"
        self.reason = "llm_unavailable"
        self.refusal_code: str | None = None
        self.answer = ""
        self.sources: list[dict[str, Any]] = []
        self.intents: list[str] = []
        self.plan_source = "none"
        self.facts_hash: str | None = None
        self.budget: Budget | None = None

    def refuse(self, code: str, text: str) -> _Outcome:
        self.kind, self.source, self.reason = "refusal", "refusal", "refused"
        self.refusal_code, self.answer = code, text
        return self


def _answer(
    sessions: sessionmaker[Session],
    people: People,
    question: str,
    clock: Clock,
    policy: PolicyConfig,
    settings: Settings,
    state: dict[str, Any],
    chat_model: Callable | None,
) -> _Outcome:
    out = _Outcome()
    boss = people.supervisor_name
    today = data_as_of(clock).date()
    code = precheck(question, people)
    if code is not None:
        return out.refuse(code, refusal_text(code, boss))
    plan = keyword_plan(question, today, boss)
    out.plan_source = plan.source
    if plan.out_of_range:
        out.intents = plan.intents
        text = refusal_text("out_of_range", boss, dates=date_range(today))
        return out.refuse("out_of_range", text)
    budget = Budget(
        settings=settings,
        calls_left=state["llm_calls_left_today"],
        deadline=_monotonic_deadline(settings),
        chat_model=chat_model,
    )
    out.budget = budget
    if settings.qa_enabled and settings.llm_api_key:
        titles = {pid: rule.title for pid, rule in policy.policies.items()}
        plan = choose_intents(budget, question, plan, titles)
        out.plan_source = plan.source
    out.intents = list(plan.intents)
    if not plan.intents:
        return out.refuse("unsupported", refusal_text("unsupported", boss))
    policy_text = load_policy_text(settings.data_dir / "policy.md")
    facts = build_facts(sessions, people, plan, clock, policy, policy_text)
    out.facts_hash = facts_hash(facts.packet)
    if facts.held:
        return out.refuse("ask_supervisor", refusal_text("ask_supervisor", boss))
    result = write_answer(budget, question, facts.packet, people)
    out.source, out.reason = result.source, result.reason
    if result.draft is not None:
        out.answer = result.draft.answer
        refs = _answer_refs(out.answer, result.draft.sources, facts)
    else:
        out.answer = template_answer(facts.packet, out.intents)
        refs = packet_sources(facts.packet, out.intents)
    out.sources = _stored_sources(refs, facts)
    return out


def _monotonic_deadline(settings: Settings) -> float:
    return monotonic() + settings.qa_llm_deadline_seconds


def _store(
    session: Session,
    people: People,
    question: str,
    out: _Outcome,
    settings: Settings,
    clock: Clock,
) -> WorkerQuestionRow:
    budget = out.budget
    calls = budget.llm_calls if budget else 0
    attempts = budget.attempts if budget else []
    row = WorkerQuestionRow(
        employee_id=people.asker_id,
        question=question,
        intents=out.intents,
        plan_source=out.plan_source,
        kind=out.kind,
        source=out.source,
        reason=out.reason,
        refusal_code=out.refusal_code,
        answer=out.answer,
        sources=out.sources,
        facts_hash=out.facts_hash,
        attempts=attempts,
        llm_calls=calls,
        model=settings.llm_model if calls else None,
        latency_ms=budget.latency_ms if budget and calls else None,
        workflow_at=clock.now(),
        created_utc=datetime.now(UTC),
    )
    session.add(row)
    session.flush()
    failed = sorted({c for a in attempts for c in a.get("checks", [])})
    after = {
        "question_id": row.id,
        "employee_id": people.asker_id,
        "intents": out.intents,
        "plan_source": out.plan_source,
        "reason": out.reason,
        "refusal_code": out.refusal_code,
        "llm_calls": calls,
        "failed_checks": failed,
        "latency_ms": row.latency_ms,
    }
    actor = "agent" if out.kind == "answer" and out.source == "llm" else "system"
    if out.kind == "refusal":
        action = "qa_refused"
    elif out.source == "llm":
        action = "qa_answered"
    else:
        action = "qa_fallback"
    session.add(
        AuditLogRow(
            exception_id=None,
            actor=actor,
            actor_id=None,
            action=action,
            after=after,
            created_at=clock.now(),
        )
    )
    return row


# ------------------------------------------------------------------ reads


def history(
    session: Session, actor_id: str, settings: Settings, *, limit: int = HISTORY_LIMIT
) -> dict[str, Any]:
    require_worker(session, actor_id)
    rows = session.scalars(
        select(WorkerQuestionRow)
        .where(WorkerQuestionRow.employee_id == actor_id)
        .order_by(WorkerQuestionRow.id.desc())
        .limit(max(1, min(limit, MAX_HISTORY_LIMIT)))
    ).all()
    return {
        "items": [row_view(r) for r in rows],
        "limits": limits(session, settings, actor_id, datetime.now(UTC)),
    }


def admin_list(
    session: Session,
    actor_id: str,
    *,
    employee_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    require_admin(session, actor_id)
    stmt = select(WorkerQuestionRow, EmployeeRow.name).join(
        EmployeeRow, EmployeeRow.employee_id == WorkerQuestionRow.employee_id
    )
    count = select(func.count(WorkerQuestionRow.id))
    if employee_id:
        stmt = stmt.where(WorkerQuestionRow.employee_id == employee_id)
        count = count.where(WorkerQuestionRow.employee_id == employee_id)
    rows = session.execute(
        stmt.order_by(WorkerQuestionRow.id.desc()).limit(max(1, min(limit, 200))).offset(offset)
    ).all()
    items = []
    for row, name in rows:
        view = row_view(row)
        view.update(
            employee_id=row.employee_id,
            employee_name=name,
            failed_checks=sorted({c for a in row.attempts or [] for c in a.get("checks", [])}),
        )
        items.append(view)
    return {"items": items, "total": int(session.scalar(count) or 0)}


def intent_words(intents: list[str]) -> str:
    return ", ".join(INTENT_WORDS.get(i, i) for i in intents) or "no topic"
