"""Phase 20: the facts packet for one worker's question, built by code.

The asker's employee ID comes from the request's actor, never from the question or the
model. Everything is read in one READ ONLY transaction (tools/context.read_only_session)
and goes through the existing read-only tool functions with that ID set by code, so a
worker can never see another employee's data.

The packet the model sees is small (PACKET_LIMIT characters): only the sections the
chosen intents need, policy text cut to its Rule and Allowed fixes paragraphs, at most a
week of days. P17 ("possible punch conflict") cases are never put in it: a day whose only
case is a P17 case is "held", and the answer is a fixed line that sends the worker to
their supervisor, with no other detail (no policy name, no punch times).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from attendflow.cases.worker_history import outcome
from attendflow.clock import Clock, data_as_of
from attendflow.db.dataset import load_dataset_from_db
from attendflow.db.models import EmployeeRow, ExceptionRow, WorkerMessageRow
from attendflow.errors import ForbiddenError
from attendflow.policy.models import PolicyConfig
from attendflow.qa.intents import People, Plan, date_range, week_start
from attendflow.tools.context import ToolContext, read_only_session
from attendflow.tools.models import EmployeeDayIn, LeaveBalanceIn, PolicyIn, ToolInputError
from attendflow.tools.read_tools import (
    get_leave,
    get_leave_balance,
    get_policy,
    get_punches,
    get_schedule,
)

PACKET_LIMIT = 3000
HELD_POLICY = "P17"
MAX_CASES = 6
ACTIVE = ("open", "awaiting_worker", "awaiting_supervisor", "escalated")
# Where a case stands, in the words the model is told to reuse (Phase 20 follow-up). An open
# case was detected but nobody has acted on it yet, so it is not "being reviewed".
CASE_STATUS_WORDS = {
    "open": "flagged, not yet reviewed",
    "awaiting_worker": "waiting for your answer",
    "awaiting_supervisor": "with your supervisor for review",
    "escalated": "with payroll for review",
    "resolved": "resolved",
    "rejected": "closed by payroll with no change to your record",
}


@dataclass
class Facts:
    packet: dict[str, Any]
    policy_sections: dict[str, str] = field(default_factory=dict)  # for the source chips
    case_details: dict[str, dict[str, Any]] = field(default_factory=dict)
    held: bool = False  # the asked day's only case is a P17 case

    @property
    def size(self) -> int:
        return len(packet_json(self.packet))


def packet_json(packet: dict[str, Any]) -> str:
    return json.dumps(packet, ensure_ascii=False, separators=(",", ":"))


def facts_hash(packet: dict[str, Any]) -> str:
    return hashlib.sha256(packet_json(packet).encode()).hexdigest()


def day_words(day: date) -> str:
    """'Tue 14 Apr 2026' (no platform-specific strftime flags)."""
    return f"{day:%a} {day.day} {day:%b %Y}"


# ------------------------------------------------------------------ who is asking


def require_worker(session: Session, actor_id: str) -> EmployeeRow:
    actor = session.get(EmployeeRow, actor_id)
    if actor is None:
        raise ForbiddenError(f"unknown actor {actor_id}", code="unknown_actor")
    if actor.role != "worker":
        raise ForbiddenError("only a worker can ask about their attendance", code="worker_only")
    return actor


def load_people(session: Session, asker: EmployeeRow) -> People:
    everyone = {e.employee_id: e.name for e in session.scalars(select(EmployeeRow))}
    boss_id = asker.supervisor_id
    return People(
        asker_id=asker.employee_id,
        asker_name=asker.name,
        supervisor_id=boss_id,
        supervisor_name=everyone.get(boss_id) if boss_id else None,
        others={k: v for k, v in everyone.items() if k not in {asker.employee_id, boss_id}},
    )


# ------------------------------------------------------------------ policy text


_PARA = re.compile(r"\*\*(Rule|Allowed fixes):\*\*\s*(.+?)(?=\n\s*\n|\Z)", re.S)


def _short(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = cut.rfind(". ")
    return cut[: end + 1] if end > limit // 2 else cut.rsplit(" ", 1)[0] + "."


def policy_brief(ctx: ToolContext, pid: str, *, fixes: bool = True) -> dict[str, Any] | None:
    try:
        out = get_policy(ctx, PolicyIn(policy_id=pid))
    except ToolInputError:
        return None
    parts = {m[1]: m[2] for m in _PARA.finditer(out.text)}
    brief: dict[str, Any] = {
        "policy_id": out.policy_id,
        "title": out.title,
        "rule": _short(parts.get("Rule", ""), 360),
    }
    if fixes and parts.get("Allowed fixes"):
        brief["allowed_fixes"] = _short(parts["Allowed fixes"], 300)
    return brief


# ------------------------------------------------------------------ the packet


def _case_item(row: ExceptionRow) -> dict[str, Any]:
    item = {
        "case_id": row.id,
        "date": row.date.isoformat(),
        "policy_id": row.policy_id,
        "title": row.title,
        "status": row.status,
        "status_words": CASE_STATUS_WORDS.get(row.status, row.status),
        "summary": _short(row.summary, 200),
    }
    if row.status in {"resolved", "rejected"}:
        item["outcome"] = outcome(row)["text"]  # what was decided, built by code
    return item


def _schedule_day(ctx: ToolContext, employee_id: str, day: date) -> dict[str, Any]:
    out = get_schedule(ctx, EmployeeDayIn(employee_id=employee_id, date=day))
    item: dict[str, Any] = {"date": day.isoformat(), "weekday": f"{day:%a}"}
    item["shift"] = f"{out.start}-{out.end}" if out.scheduled else None
    if out.scheduled:
        item["planned_hours"] = out.planned_hours
    if out.holiday:
        item["holiday"] = out.holiday
    leave = get_leave(ctx, EmployeeDayIn(employee_id=employee_id, date=day))
    if leave.on_leave:
        item["leave"] = f"{leave.leave_type} leave, {leave.duration} day ({leave.status})"
    return item


def _punch_day(ctx: ToolContext, employee_id: str, day: date) -> dict[str, Any] | None:
    out = get_punches(ctx, EmployeeDayIn(employee_id=employee_id, date=day))
    if not out.shifts:
        return None
    shift = out.shifts[0]
    return {
        "date": day.isoformat(),
        "weekday": f"{day:%a}",
        "scheduled": shift.scheduled,
        "clock_in": shift.clock_in,
        "clock_out": shift.clock_out,
        "break_minutes": shift.break_minutes,
        "worked_hours": shift.worked_hours,
        "punch_status": shift.status.replace("_", " "),
    }


def _days(plan: Plan, today: date) -> list[date]:
    if plan.day is not None:
        return [plan.day]
    start = week_start(today) - (timedelta(days=7) if plan.week == "previous" else timedelta())
    return [start + timedelta(days=n) for n in range(7)]


def build_facts(
    sessions: sessionmaker[Session],
    people: People,
    plan: Plan,
    clock: Clock,
    policy: PolicyConfig,
    policy_text: dict[str, str],
) -> Facts:
    as_of: datetime = data_as_of(clock)
    today = as_of.date()
    lo, hi = date_range(today)
    me = people.asker_id
    with read_only_session(sessions) as session:
        dataset = load_dataset_from_db(session)
        asker = session.get(EmployeeRow, me)
        team = asker.team if asker is not None else None
        rows = session.scalars(
            select(ExceptionRow)
            .where(ExceptionRow.employee_id == me, ExceptionRow.date.between(lo, hi))
            .order_by(ExceptionRow.date, ExceptionRow.id)
        ).all()
        asked_ids = set(
            session.scalars(
                select(WorkerMessageRow.exception_id).where(WorkerMessageRow.recipient_id == me)
            )
        )
        ordered = sorted(rows, key=lambda r: (r.date, int(r.policy_id[1:]), r.id))
        visible = [_case_item(r) for r in ordered if r.policy_id != HELD_POLICY]
        held_days = sorted(
            {
                r.date
                for r in rows
                if r.policy_id == HELD_POLICY
                and not any(o.date == r.date and o.policy_id != HELD_POLICY for o in rows)
            }
        )
    ctx = ToolContext(dataset=dataset, policy=policy, policy_text=policy_text, as_of=as_of)

    packet: dict[str, Any] = {
        "as_of": f"{as_of:%Y-%m-%d %H:%M}",
        "you": {"employee_id": me, "name": people.asker_name, "team": team},
        "supervisor": people.supervisor_name,
        "can_answer_dates": {"from": lo.isoformat(), "to": hi.isoformat()},
    }
    facts = Facts(packet=packet)
    if plan.day is not None:
        packet["asked_day"] = {"date": plan.day.isoformat(), "words": day_words(plan.day)}
        if (
            plan.day in held_days
            and plan.intents
            and set(plan.intents)
            & {
                "my_cases",
                "my_punches",
            }
        ):
            facts.held = True
            return facts
    elif plan.week:
        packet["asked_week"] = plan.week

    days = [d for d in _days(plan, today) if d not in held_days]
    policies: list[str] = []
    for intent in plan.intents:
        if intent == "leave_balance":
            kinds = [plan.leave_type] if plan.leave_type else ["sick", "casual", "earned"]
            balances = []
            for kind in kinds:
                try:
                    b = get_leave_balance(ctx, LeaveBalanceIn(employee_id=me, leave_type=kind))
                except ToolInputError:
                    continue
                balances.append(
                    {
                        "leave_type": kind,
                        "total_per_year": b.total_per_year,
                        "used": b.used,
                        "days_left": b.balance,
                        "pending_days": b.pending_days,
                        "days_left_after_pending": b.balance_after_pending,
                    }
                )
            packet["leave_balance"] = {"year": today.year, "types": balances}
        elif intent == "my_schedule":
            items = [_schedule_day(ctx, me, d) for d in days]
            shown = [i for i in items if i["shift"] or i.get("holiday") or i.get("leave")]
            packet["schedule"] = {
                "days": shown if plan.day is None else items,
                "scheduled_days": sum(1 for i in items if i["shift"]),
                "planned_hours_total": round(sum(i.get("planned_hours") or 0 for i in items), 2),
            }
        elif intent == "my_punches":
            past = [d for d in days if d <= today]
            found = [p for d in past if (p := _punch_day(ctx, me, d)) is not None]
            got = {p["date"] for p in found}
            # Today's shift may still be ahead: only past days count as "no punches".
            past_only = [d for d in past if d < today]
            packet["punches"] = {
                "days": found,
                "days_without_punches": [d for d in map(date.isoformat, past_only) if d not in got],
            }
        elif intent == "my_cases":
            chosen = [c for c in visible if plan.day is None or c["date"] == plan.day.isoformat()]
            packet["cases"] = {
                "items": chosen[:MAX_CASES],
                "total": len(chosen),
                "active": sum(1 for c in chosen if c["status"] in ACTIVE),
            }
            if plan.day is not None:
                policies += [c["policy_id"] for c in chosen]
        elif intent == "policy_rule":
            policies += plan.policy_ids
        elif intent == "my_supervisor":
            packet["who_to_ask"] = {"supervisor": people.supervisor_name, "team": team}
    if held_days and set(plan.intents) & {"my_cases", "my_punches", "my_schedule"}:
        packet["ask_supervisor_about"] = [d.isoformat() for d in held_days]

    briefs = []
    for pid in dict.fromkeys(policies):
        brief = policy_brief(ctx, pid)
        if brief is not None:
            briefs.append(brief)
            facts.policy_sections[pid] = policy_text.get(pid, "")
        if len(briefs) == 2:
            break
    if briefs:
        packet["policies"] = briefs
    for item in packet.get("cases", {}).get("items", []):
        facts.case_details[item["case_id"]] = {
            **item,
            "in_history": item["case_id"] in asked_ids,
        }
        if item["policy_id"] not in facts.policy_sections:
            facts.policy_sections[item["policy_id"]] = policy_text.get(item["policy_id"], "")
    _fit(packet)
    return facts


def _fit(packet: dict[str, Any]) -> None:
    """Keep the packet under PACKET_LIMIT characters: drop the allowed-fixes text first,
    then shorten case summaries, then drop days from the end."""
    if len(packet_json(packet)) <= PACKET_LIMIT:
        return
    for brief in packet.get("policies", []):
        brief.pop("allowed_fixes", None)
    for item in packet.get("cases", {}).get("items", []):
        if len(packet_json(packet)) <= PACKET_LIMIT:
            return
        item["summary"] = _short(item["summary"], 90)
    for key in ("punches", "schedule"):
        days = packet.get(key, {}).get("days", [])
        while days and len(packet_json(packet)) > PACKET_LIMIT:
            days.pop()
    items = packet.get("cases", {}).get("items", [])
    while items and len(packet_json(packet)) > PACKET_LIMIT:
        items.pop()
