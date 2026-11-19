"""Deterministic attendance readiness and payroll-admin sign-offs."""

from collections import defaultdict
from datetime import date, timedelta
from hashlib import sha256
from json import dumps
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from attendflow.agent.case import routing
from attendflow.cases import admin, no_reply
from attendflow.cases.selection import ACTIVE_STATUSES, scope_cases
from attendflow.cases.supervisor import require_reviewer
from attendflow.clock import Clock, data_as_of
from attendflow.db.dataset import load_dataset_from_db, unpaid_leave_days
from attendflow.db.models import (
    AuditLogRow,
    EmployeeRow,
    ExceptionRow,
    PayrollSignoffRow,
)
from attendflow.engine.checks import CHECKS
from attendflow.engine.engine import build_context
from attendflow.engine.models import TimecardException
from attendflow.engine.rules import h, week_hours, week_start
from attendflow.errors import ConflictError, InvalidInputError
from attendflow.fixes.apply import AUTO_FIX_VERSION
from attendflow.policy.models import PolicyConfig

BLOCKING_POLICIES = frozenset(
    {"P1", "P2", "P3", "P4", "P5", "P8", "P9", "P10", "P11", "P12", "P13", "P14", "P17"}
)
# These cases use the first affected day as their ID date.
MULTI_DAY_LEAVE = {"P11": "requested_dates", "P12": "dates"}


def _case_dates(row: ExceptionRow | TimecardException) -> set[str]:
    key = MULTI_DAY_LEAVE.get(row.policy_id)
    return {row.date.isoformat(), *(row.details.get(key, []) if key else [])}


def _status(reasons: list[dict[str, Any]]) -> str:
    if any(reason["blocking"] for reason in reasons):
        return "blocked"
    return "ready_with_notes" if reasons else "ready"


def _reason(
    employee_id: str,
    code: str,
    message: str,
    *,
    blocking: bool = True,
    cases: tuple[str, ...] = (),
    owner: EmployeeRow | None = None,
    contact: str | None = None,
) -> dict[str, Any]:
    return {
        "employee_id": employee_id,
        "code": code,
        "message": message,
        "blocking": blocking,
        "exception_ids": list(cases),
        "owner_id": owner.employee_id if owner else None,
        "owner_name": owner.name if owner else None,
        "contact": contact,
    }


def _case_reason(row: ExceptionRow, people: dict[str, EmployeeRow]) -> dict | None:
    eid = row.employee_id
    if row.status in ACTIVE_STATUSES:
        waiting = row.status == "awaiting_worker" or row.no_reply_stage > 0
        label = no_reply.STAGE_LABELS.get(row.no_reply_stage)
        message = f"{row.summary or row.title} · {label or row.status.replace('_', ' ')}"
        contact = None
        if row.status == "open" and row.auto_resolve_undone_at is None:
            option_id = (row.proposed_fix or {}).get("option_id")
            option = next((opt for opt in row.fix_options if opt["option_id"] == option_id), None)
            contact, _ = routing(row, option)
        return _reason(
            eid,
            "awaiting_reply" if waiting else "active_case",
            message,
            blocking=waiting or row.policy_id in BLOCKING_POLICIES,
            cases=(row.id,),
            owner=people.get(row.assigned_to),
            contact=contact,
        )

    if row.auto_resolved:
        hint = (
            " (review or undo from the case)"
            if (row.applied_fix or {}).get("snapshot_version") == AUTO_FIX_VERSION
            else ""
        )
        return _reason(
            eid,
            "auto_resolved",
            f"{row.title} · auto-resolved{hint}",
            blocking=False,
            cases=(row.id,),
        )
    if (row.applied_fix or {}).get("without_worker"):
        return _reason(
            eid,
            "without_worker",
            "Decided without the worker's reply",
            blocking=False,
            cases=(row.id,),
        )
    return None


def snapshot(
    session: Session, actor: EmployeeRow, clock: Clock, policy: PolicyConfig, start: date | None
) -> tuple[dict[str, Any], str]:
    cutoff = data_as_of(clock)
    current = week_start(cutoff.date())
    start = start or current
    if start != week_start(start) or start > current:
        raise InvalidInputError(
            "Choose a Monday on or before the attendance cutoff week", code="invalid_payroll_week"
        )
    end = start + timedelta(days=6)
    through = min(end, cutoff.date())
    days = {(start + timedelta(days=i)).isoformat() for i in range((through - start).days + 1)}
    supervisor = actor.employee_id if actor.role == "supervisor" else None
    people = {row.employee_id: row for row in session.scalars(select(EmployeeRow))}
    workers = sorted(
        (
            row
            for row in people.values()
            if row.role == "worker" and (supervisor is None or row.supervisor_id == supervisor)
        ),
        key=lambda row: (row.team, row.name, row.employee_id),
    )
    payroll_admin = next((row for row in people.values() if row.role == "payroll_admin"), None)
    reasons = defaultdict(list)
    cases_by_worker = defaultdict(list)
    case_query = scope_cases(
        select(ExceptionRow)
        .where(or_(ExceptionRow.date >= start, ExceptionRow.policy_id.in_(MULTI_DAY_LEAVE)))
        .order_by(ExceptionRow.id),
        date_to=through,
        supervisor_id=supervisor,
    )
    for row in session.scalars(case_query):
        if days.isdisjoint(_case_dates(row)):
            continue
        cases_by_worker[row.employee_id].append(row)
        reason = _case_reason(row, people)
        if reason:
            reasons[row.employee_id].append(reason)

    dataset = load_dataset_from_db(session)
    ctx, _ = build_context(dataset, policy, cutoff)
    shifts, schedules = ctx.shifts_by_employee(), ctx.schedule_by_employee()
    # A missed detection run must not make attendance with an actionable finding signable.
    # P5 is evaluated with the same week_hours result already used for the row below.
    findings = defaultdict(list)
    for policy_id in sorted(BLOCKING_POLICIES - {"P5"}):
        for case in CHECKS[policy_id](ctx):
            if not days.isdisjoint(_case_dates(case)):
                findings[case.employee_id].append(case)
    leave_by_worker = defaultdict(list)
    for leave in ctx.leave_records:
        if leave.date.isoformat() in days:
            leave_by_worker[leave.employee_id].append(leave)
    unpaid_leave = unpaid_leave_days(session, start, through)

    limit = policy.number("P5", "weekly_overtime_after_hours")
    rows, fingerprint_inputs = [], []
    has_data = False
    for worker in workers:
        eid = worker.employee_id
        owner = people.get(worker.supervisor_id) or payroll_admin
        cases = cases_by_worker[eid]
        by_id = {row.id: row for row in cases}
        week_shifts = [shift for shift in shifts.get(eid, []) if shift.date.isoformat() in days]
        week_schedule = [row for row in schedules.get(eid, []) if row.date.isoformat() in days]
        leaves = leave_by_worker[eid]
        has_data |= bool(week_shifts or week_schedule or leaves or cases)
        for case in findings[eid]:
            stored = by_id.get(case.exception_id)
            if stored and stored.status in ACTIVE_STATUSES:
                continue
            # A missing punch remains a data defect even if someone closed the case.
            # P17 requires a positive human review of the conflicting punches.
            code = {"P1": "missing_punch", "P17": "punch_conflict"}.get(case.policy_id)
            if (
                stored
                and case.policy_id != "P1"
                and (case.policy_id != "P17" or stored.applied_fix)
            ):
                continue
            reasons[eid].append(
                _reason(
                    eid,
                    code or "undecided_finding",
                    case.summary,
                    cases=(stored.id,) if stored else (),
                    owner=owner,
                    contact="worker" if case.policy_id == "P1" else None,
                )
            )
        for shift in week_shifts:
            if start < current and shift.status == "in_progress":
                reasons[eid].append(
                    _reason(
                        eid,
                        "unfinished_shift",
                        f"Shift on {shift.date} is still in progress",
                        owner=owner,
                    )
                )
        for leave in leaves:
            if leave.status != "pending":
                continue
            related = tuple(
                row.id
                for row in cases
                if row.policy_id in {"P9", "P11", "P12", "P13"}
                and leave.date.isoformat() in _case_dates(row)
            )
            reasons[eid].append(
                _reason(
                    eid,
                    "pending_leave",
                    f"{leave.duration.title()}-day leave on {leave.date} needs approval",
                    cases=related,
                    owner=owner,
                )
            )

        hours = week_hours(ctx, eid, start, shifts.get(eid, []), schedules.get(eid, []))
        overtime_cases = tuple(row.id for row in cases if row.policy_id == "P5")
        if hours.projected > limit and not overtime_cases:
            reasons[eid].append(
                _reason(
                    eid,
                    "undecided_overtime",
                    f"{h(hours.projected):g} h projected "
                    f"· weekly limit {limit:g} h · overtime decision required",
                    owner=owner,
                )
            )
        if hours.worked >= limit:
            reasons[eid].append(
                _reason(
                    eid,
                    "overtime_hours",
                    f"{h(hours.worked):g} h worked · weekly limit {limit:g} h",
                    blocking=False,
                    cases=overtime_cases,
                )
            )
        rows.append(
            {
                "employee_id": eid,
                "employee_name": worker.name,
                "team": worker.team,
                "status": _status(reasons[eid]),
                "reasons": reasons[eid],
                "worked_hours": h(hours.worked),
                "scheduled_remaining_hours": h(hours.remaining),
                "projected_hours": h(hours.projected),
            }
        )
        fingerprint_inputs.append(
            (
                eid,
                worker.team,
                worker.supervisor_id,
                [shift.model_dump(mode="json") for shift in week_shifts],
                [row.model_dump(mode="json") for row in week_schedule],
                [
                    (leave.model_dump(mode="json"), (eid, leave.date) in unpaid_leave)
                    for leave in leaves
                ],
                [
                    (
                        row.id,
                        row.status,
                        row.auto_resolved,
                        row.applied_fix,
                        row.details,
                        row.assigned_to,
                        row.no_reply_stage,
                    )
                    for row in cases
                ],
            )
        )

    teams = defaultdict(list)
    for row in rows:
        teams[row["team"]].extend(row["reasons"])
    all_reasons = [reason for row in rows for reason in row["reasons"]]
    fingerprint = _fingerprint([policy.model_dump(mode="json"), fingerprint_inputs])
    signoff = session.get(PayrollSignoffRow, start) if supervisor is None else None
    signed = signoff is not None and signoff.reopened_at is None
    status = _status(all_reasons)
    closed = start < current
    return {
        "week_start": start,
        "week_end": end,
        "evaluated_through": through,
        "data_cutoff": cutoff,
        "closed": closed,
        "has_data": has_data,
        "status": status,
        "scope": "team" if supervisor else "all",
        "can_sign": supervisor is None
        and closed
        and has_data
        and status != "blocked"
        and not signed,
        "can_reopen": signed,
        "signoff": {
            "signer_name": signoff.signer_name,
            "signed_at": signoff.signed_at,
            "note": signoff.note,
            "reopened_at": signoff.reopened_at,
            "stale": signed and signoff.fingerprint != fingerprint,
        }
        if signoff
        else None,
        "exception_counts": admin.counters(
            session, date_from=start, date_to=through, supervisor_id=supervisor
        ),
        "overtime_limit_hours": limit,
        "reasons": all_reasons,
        "teams": [
            {"team": team, "status": _status(items), "reasons": items}
            for team, items in teams.items()
        ],
        "workers": rows,
    }, fingerprint


def _fingerprint(inputs: list) -> str:
    return sha256(dumps(inputs, sort_keys=True, default=str).encode()).hexdigest()


def overview(
    session: Session, actor_id: str, clock: Clock, policy: PolicyConfig, start: date | None
) -> dict:
    actor = require_reviewer(session, actor_id)
    result, _ = snapshot(session, actor, clock, policy, start)
    return result


def sign(
    session: Session,
    actor_id: str,
    clock: Clock,
    policy: PolicyConfig,
    start: date,
    note: str | None,
) -> dict:
    actor = admin.require_admin(session, actor_id)
    report, fingerprint = snapshot(session, actor, clock, policy, start)
    if not report["can_sign"]:
        raise ConflictError(
            "Sign-off requires a closed week with attendance data, "
            "no blockers, and no active sign-off",
            code="payroll_not_signable",
        )
    row = session.get(PayrollSignoffRow, start)
    if row is None:
        row = PayrollSignoffRow(week_start=start)
        session.add(row)
    row.signed_by = actor.employee_id
    row.signer_name = actor.name
    row.signed_at = clock.now()
    row.note = note
    row.fingerprint = fingerprint
    row.reopened_at = None
    session.add(
        AuditLogRow(
            actor="admin",
            actor_id=actor.employee_id,
            action="payroll_signed_off",
            after={"week_start": start.isoformat(), "fingerprint": fingerprint},
            reason=note,
            created_at=row.signed_at,
        )
    )
    return {
        **report,
        "can_sign": False,
        "can_reopen": True,
        "signoff": {
            "signer_name": actor.name,
            "signed_at": row.signed_at,
            "note": note,
            "reopened_at": None,
            "stale": False,
        },
    }


def reopen(
    session: Session,
    actor_id: str,
    clock: Clock,
    policy: PolicyConfig,
    start: date,
    reason: str,
) -> dict:
    actor = admin.require_admin(session, actor_id)
    row = session.get(PayrollSignoffRow, start)
    if not row or row.reopened_at is not None:
        raise ConflictError("This week has no active sign-off", code="payroll_not_signed")
    row.reopened_at = clock.now()
    session.add(
        AuditLogRow(
            actor="admin",
            actor_id=actor.employee_id,
            action="payroll_reopened",
            before={"week_start": start.isoformat(), "signed_at": row.signed_at.isoformat()},
            after={"week_start": start.isoformat()},
            reason=reason,
            created_at=row.reopened_at,
        )
    )
    report, _ = snapshot(session, actor, clock, policy, start)
    return report
