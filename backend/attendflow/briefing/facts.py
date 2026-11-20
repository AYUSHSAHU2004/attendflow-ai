"""The briefing's facts packet: built entirely by code, scoped before anything else.

Priya (payroll admin) gets every team; a supervisor gets only their own team. Every number
is reused from an existing view, so the briefing can never disagree with the screens:

- counts: `admin.counters` (team-scoped); team workload: `dashboard.overview`;
- the decision queue: `supervisor.queue` (the same list the reviewer works from);
- what blocks payroll: `payroll.snapshot` for the current Monday-Sunday week;
- overtime risk: the dashboard's P5 panel (engine weekly hours at the data cutoff);
- what the system did today: `activity.summary` for the workflow date;
- auto-resolved without a person: `auto_fix.metric`.

The packet holds case IDs, employee IDs, names of people in scope, policy titles, dates
and numbers. It never holds free text typed by people, LLM narratives, prompts,
diagnostics or secrets. A test checks the scope and the numbers against the views.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from attendflow.activity import feed
from attendflow.cases import admin, dashboard, payroll, supervisor
from attendflow.cases.selection import active_cases, scope_cases
from attendflow.clock import Clock, data_as_of
from attendflow.config import Settings
from attendflow.db.models import EmployeeRow, ExceptionRow
from attendflow.policy.models import PolicyConfig

LIST_LIMIT = 10  # each case list is capped; the matching *_total says how many there are
SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}

# Fixed sections of a briefing, in display order: key -> title.
SECTIONS: dict[str, str] = {
    "needs_decision": "Needs a decision today",
    "handled_on_its_own": "Handled on its own",
    "blocking_payroll": "Blocking payroll",
    "watch": "Watch",
}


def scope_key(actor: EmployeeRow) -> str:
    """'all' for the payroll admin, else the supervisor's own employee ID."""
    return "all" if actor.role == "payroll_admin" else actor.employee_id


def _case(row: ExceptionRow) -> dict[str, Any]:
    return {
        "case_id": row.id,
        "policy_id": row.policy_id,
        "employee_id": row.employee_id,
        "date": row.date.isoformat(),
        "status": row.status,
        "severity": row.severity,
        "no_reply_stage": row.no_reply_stage or 0,
    }


def _ordered(rows: list[ExceptionRow]) -> list[ExceptionRow]:
    return sorted(rows, key=lambda r: (SEVERITY_RANK.get(r.severity, 9), r.date, r.id))


def build_packet(
    session: Session,
    actor_id: str,
    clock: Clock,
    policy: PolicyConfig,
    settings: Settings,
) -> dict[str, Any]:
    actor = supervisor.require_reviewer(session, actor_id)
    team_of = None if actor.role == "payroll_admin" else actor.employee_id
    employees = {e.employee_id: e for e in session.scalars(select(EmployeeRow))}
    today = clock.now().date()

    board = dashboard.overview(session, actor_id, clock, policy, settings)
    readiness, _ = payroll.snapshot(session, actor, clock, policy, None)
    activity = feed.summary(session, actor_id, date_from=today, date_to=today)["counts"]
    queue = supervisor.queue(session, actor_id, clock.now())
    counts = admin.counters(session, supervisor_id=team_of)  # the same tiles as /admin

    def scoped(stmt):
        return session.scalars(scope_cases(stmt, supervisor_id=team_of)).all()

    by_id = {
        row.id: row
        for row in scoped(select(ExceptionRow))  # every case in scope (also the closed ones)
    }

    # 1. Needs a decision: the reviewer's own queue, in its order.
    needs = [by_id[item["exception_id"]] for item in queue if item["exception_id"] in by_id]

    # 2. Handled on its own: auto-resolved and not undone (Phase 12 X).
    auto = _ordered([r for r in by_id.values() if r.auto_resolved])

    # 3. Blocking payroll: the current week's blocking reasons (their stored case IDs).
    blocking_reasons = [r for r in readiness["reasons"] if r["blocking"]]
    blocking_ids = sorted({cid for r in blocking_reasons for cid in r["exception_ids"]})
    blocking = _ordered([by_id[cid] for cid in blocking_ids if cid in by_id])

    # 4. Watch: overtime risk (the dashboard's P5 panel) and unanswered questions.
    overtime = board["overtime"]
    risk_ids = {w["employee_id"] for w in overtime["workers"]}
    overtime_cases = _ordered(
        [
            r
            for r in scoped(select(ExceptionRow).where(active_cases()))
            if r.policy_id == "P5" and r.employee_id in risk_ids
        ]
    )
    no_reply = _ordered(
        [r for r in scoped(select(ExceptionRow).where(active_cases())) if r.no_reply_stage]
    )

    metric = board["auto_resolve"]
    team_names = {e.employee_id: e.team for e in employees.values()}
    teams = [
        {
            "team": team_names.get(item["supervisor_id"]) or "Unassigned",
            "supervisor_id": item["supervisor_id"],
            "active": item["active"],
            "awaiting_worker": item["awaiting_worker"],
            "awaiting_supervisor": item["awaiting_supervisor"],
        }
        for item in board["workload"]
        if item["supervisor_id"] and (team_of is None or item["supervisor_id"] == team_of)
    ]

    packet: dict[str, Any] = {
        "scope": "all" if team_of is None else "team",
        "team": None if team_of is None else actor.team,
        "workflow_date": today.isoformat(),
        "data_cutoff": data_as_of(clock).isoformat(timespec="minutes"),
        "counts": {"active": board["active_total"], **counts},
        "needs_decision": {
            "total": len(needs),
            "cases": [_case(r) for r in needs[:LIST_LIMIT]],
        },
        "handled_on_its_own": {
            "auto_resolved_total": len(auto),
            "auto_resolved_cases": [_case(r) for r in auto[:LIST_LIMIT]],
            "resolved_without_human": metric["resolved_without_human"],
            "needed_handling": metric["needed_handling"],
            "percent": metric["percent"],
            "undone": metric["undone"],
            "today": dict(activity),
        },
        "blocking_payroll": {
            "week_start": readiness["week_start"].isoformat(),
            "week_end": readiness["week_end"].isoformat(),
            "week_closed": readiness["closed"],
            "status": readiness["status"],
            "signed_off": bool(readiness["signoff"] and readiness["signoff"]["signed_at"])
            and not (readiness["signoff"] or {}).get("reopened_at"),
            "blocking_total": len(blocking),
            "blocking_cases": [_case(r) for r in blocking[:LIST_LIMIT]],
            "blocking_without_case": sum(1 for r in blocking_reasons if not r["exception_ids"]),
            "notes": sum(1 for r in readiness["reasons"] if not r["blocking"]),
        },
        "watch": {
            "overtime_limit_hours": overtime["limit_hours"],
            "overtime_workers": [
                {
                    "employee_id": w["employee_id"],
                    "worked_hours": w["worked_hours"],
                    "projected_hours": w["projected_hours"],
                    "level": w["level"],
                }
                for w in overtime["workers"][:LIST_LIMIT]
            ],
            "overtime_cases": [_case(r) for r in overtime_cases[:LIST_LIMIT]],
            "no_reply_total": len(no_reply),
            "no_reply_cases": [_case(r) for r in no_reply[:LIST_LIMIT]],
        },
        "teams": teams,
    }

    referenced = {
        c["employee_id"]
        for key in ("needs_decision", "handled_on_its_own", "blocking_payroll", "watch")
        for value in packet[key].values()
        if isinstance(value, list)
        for c in value
        if isinstance(c, dict) and "employee_id" in c
    } | {t["supervisor_id"] for t in teams}
    allowed = {
        eid
        for eid, e in employees.items()
        if team_of is None or e.supervisor_id == team_of or eid == team_of
    }
    packet["people"] = {
        eid: employees[eid].name for eid in sorted(referenced & allowed) if eid in employees
    }
    policies = {
        c["policy_id"]
        for key in ("needs_decision", "handled_on_its_own", "blocking_payroll", "watch")
        for value in packet[key].values()
        if isinstance(value, list)
        for c in value
        if isinstance(c, dict) and "policy_id" in c
    }
    packet["policies"] = {
        pid: policy.policies[pid].title
        for pid in sorted(policies, key=lambda p: int(p[1:]))
        if pid in policy.policies
    }
    return packet


def section_case_ids(packet: dict[str, Any]) -> dict[str, set[str]]:
    """Which case IDs each section may cite."""
    h, b, w = packet["handled_on_its_own"], packet["blocking_payroll"], packet["watch"]
    return {
        "needs_decision": {c["case_id"] for c in packet["needs_decision"]["cases"]},
        "handled_on_its_own": {c["case_id"] for c in h["auto_resolved_cases"]},
        "blocking_payroll": {c["case_id"] for c in b["blocking_cases"]},
        "watch": {c["case_id"] for c in w["overtime_cases"] + w["no_reply_cases"]},
    }


def packet_hash(packet: dict[str, Any]) -> str:
    """Changes only when the facts change (the workflow time of day is not in the packet)."""
    text = json.dumps(packet, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
