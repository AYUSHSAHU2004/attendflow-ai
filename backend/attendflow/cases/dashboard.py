"""Read-only operations dashboard built from case state and the engine's P5 forecast."""

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from attendflow.cases import admin, auto_fix
from attendflow.cases.selection import (
    ACTIVE_STATUSES,
    NO_REPLY_STAGES,
    active_cases,
    scope_cases,
    validate_date_range,
)
from attendflow.cases.supervisor import require_reviewer
from attendflow.clock import Clock, data_as_of
from attendflow.config import Settings
from attendflow.db.dataset import load_dataset_from_db
from attendflow.db.models import EmployeeRow, ExceptionRow
from attendflow.engine.engine import build_context
from attendflow.engine.rules import h, week_hours, week_start
from attendflow.policy.models import PolicyConfig

AGE_LIMITS = (8, 24, 48)


def _age_buckets(stamps: list[datetime], now: datetime) -> list[int]:
    counts = [0] * (len(AGE_LIMITS) + 1)
    for stamp in stamps:
        hours = (now - stamp).total_seconds() / 3600
        counts[sum(hours >= limit for limit in AGE_LIMITS)] += 1
    return counts


def _overtime(
    session: Session,
    policy: PolicyConfig,
    cutoff: datetime,
    margin: float,
    workers: list[EmployeeRow],
) -> dict[str, Any]:
    week = week_start(cutoff.date())
    limit = policy.number("P5", "weekly_overtime_after_hours")
    ctx, _ = build_context(load_dataset_from_db(session), policy, cutoff)
    shifts, schedule = ctx.shifts_by_employee(), ctx.schedule_by_employee()
    rows = []
    for worker in workers:
        eid = worker.employee_id
        if eid not in shifts and eid not in schedule:
            continue
        hours = week_hours(ctx, eid, week, shifts.get(eid, []), schedule.get(eid, []))
        projected = hours.projected
        if not hours.days or projected < limit - margin:
            continue
        if hours.worked > limit:
            level = "already_over"
        elif projected > limit:
            level = "projected_over"
        elif projected == limit:
            level = "at_limit"
        else:
            level = "approaching"
        rows.append(
            {
                "employee_id": eid,
                "employee_name": worker.name,
                "worked_hours": h(hours.worked),
                "scheduled_remaining_hours": h(hours.remaining),
                "projected_hours": h(projected),
                "level": level,
            }
        )
    return {
        "week_start": week,
        "week_end": week + timedelta(days=6),
        "limit_hours": limit,
        "warning_margin_hours": margin,
        "workers": sorted(rows, key=lambda row: (-row["projected_hours"], row["employee_id"])),
    }


def overview(
    session: Session,
    actor_id: str,
    clock: Clock,
    policy: PolicyConfig,
    settings: Settings,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    actor = require_reviewer(session, actor_id)
    validate_date_range(date_from, date_to)
    supervisor_id = actor.employee_id if actor.role == "supervisor" else None
    scope = dict(date_from=date_from, date_to=date_to, supervisor_id=supervisor_id)
    now = clock.now()
    counts = admin.counters(session, **scope)
    employees = {row.employee_id: row for row in session.scalars(select(EmployeeRow))}
    workers = [
        row for row in employees.values()
        if row.role == "worker" and (not supervisor_id or row.supervisor_id == supervisor_id)
    ]
    rows = session.execute(
        scope_cases(
            select(
                ExceptionRow.employee_id, ExceptionRow.status, ExceptionRow.severity,
                ExceptionRow.policy_id, ExceptionRow.no_reply_stage, ExceptionRow.created_at,
                ExceptionRow.waiting_since,
            ).where(active_cases()),
            **scope,
        )
    ).all()
    stages = Counter(row.no_reply_stage for row in rows if row.no_reply_stage > 0)
    workload: dict[str | None, Counter[str]] = {
        worker.supervisor_id: Counter() for worker in workers
    }
    for row in rows:
        owner = employees[row.employee_id].supervisor_id
        group = workload.setdefault(owner, Counter())
        group["active"] += 1
        group[row.status] += 1

    policies = Counter(row.policy_id for row in rows)
    return {
        "scope": "team" if supervisor_id else "all",
        "workflow_now": now,
        "active_total": sum(counts[status] for status in ACTIVE_STATUSES),
        "by_status": {status: counts[status] for status in ACTIVE_STATUSES},
        "stuck": counts["stuck"],
        "by_severity": dict(Counter(row.severity for row in rows)),
        "by_policy": dict(sorted(policies.items(), key=lambda pair: (-pair[1], int(pair[0][1:])))),
        "ladder": {
            "waiting": sum(
                row.status == "awaiting_worker" and row.no_reply_stage == 0 for row in rows
            ),
            **{key: stages[stage] for key, stage in NO_REPLY_STAGES.items()},
        },
        "aging": {
            "limits_hours": list(AGE_LIMITS),
            "case_age": _age_buckets([row.created_at for row in rows], now),
            "waiting_age": _age_buckets(
                [row.waiting_since for row in rows if row.waiting_since is not None], now
            ),
        },
        "workload": [
            {
                "supervisor_id": owner,
                "supervisor_name": employees[owner].name if owner else "Unassigned",
                "active": workload[owner]["active"],
                "awaiting_worker": workload[owner]["awaiting_worker"],
                "awaiting_supervisor": workload[owner]["awaiting_supervisor"],
            }
            for owner in sorted(workload, key=lambda eid: (-workload[eid]["active"], eid or ""))
        ],
        "overtime": _overtime(
            session, policy, data_as_of(clock), settings.overtime_warning_margin_hours, workers
        ),
        "auto_resolve": auto_fix.metric(
            session, policy, auto_resolve_enabled=settings.auto_resolve_enabled, **scope
        ),
    }
