"""The five lookup tools: schedule, leave, leave balance, punches and policy text."""

from __future__ import annotations

import re

from attendflow.engine.rules import h, hhmm
from attendflow.engine.shifts import schedule_bounds, scheduled_hours
from attendflow.tools.context import ToolContext, fmt_time
from attendflow.tools.models import (
    EmployeeDayIn,
    LeaveBalanceIn,
    LeaveBalanceOut,
    LeaveOut,
    PolicyIn,
    PolicyOut,
    PunchesOut,
    PunchOut,
    ScheduleOut,
    ShiftOut,
    ToolInputError,
)


def get_schedule(ctx: ToolContext, args: EmployeeDayIn) -> ScheduleOut:
    ctx.employee(args.employee_id)
    row = next(
        (
            r
            for r in ctx.dataset.schedule
            if r.employee_id == args.employee_id and r.date == args.date
        ),
        None,
    )
    hol = next((x for x in ctx.dataset.holidays if x.date == args.date), None)
    out = ScheduleOut(
        employee_id=args.employee_id,
        date=args.date.isoformat(),
        scheduled=row is not None,
        holiday=f"{hol.name} ({hol.type})" if hol else None,
    )
    if row is None:
        out.note = "not scheduled"
        return out
    start, end = schedule_bounds(row)
    out.start, out.end = hhmm(start), hhmm(end)
    out.ends_next_day = row.crosses_midnight
    out.planned_hours = h(scheduled_hours(row, ctx.policy))
    return out


def get_leave(ctx: ToolContext, args: EmployeeDayIn) -> LeaveOut:
    ctx.employee(args.employee_id)
    rec = next(
        (
            r
            for r in ctx.dataset.leave_records
            if r.employee_id == args.employee_id and r.date == args.date
        ),
        None,
    )
    out = LeaveOut(employee_id=args.employee_id, date=args.date.isoformat(), on_leave=False)
    if rec is None:
        out.note = "no leave"
    elif rec.status == "rejected":
        out.note = f"no leave (a {rec.leave_type} leave request for this day was rejected)"
    else:
        out.on_leave = True
        out.leave_type, out.duration, out.status = rec.leave_type, rec.duration, rec.status
        out.certificate = rec.certificate_uploaded
    return out


def get_leave_balance(ctx: ToolContext, args: LeaveBalanceIn) -> LeaveBalanceOut:
    ctx.employee(args.employee_id)
    bal = next(
        (
            b
            for b in ctx.dataset.leave_balances
            if b.employee_id == args.employee_id and b.leave_type == args.leave_type
        ),
        None,
    )
    if bal is None:
        raise ToolInputError(
            "no_balance", f"{args.employee_id} has no {args.leave_type} leave balance"
        )
    year = ctx.as_of.year
    pending = sum(
        1.0 if r.duration == "full" else 0.5
        for r in ctx.dataset.leave_records
        if r.employee_id == args.employee_id
        and r.leave_type == args.leave_type
        and r.status == "pending"
        and r.date.year == year
    )
    balance = bal.total_per_year - bal.used  # never stored, always computed
    return LeaveBalanceOut(
        employee_id=args.employee_id,
        leave_type=args.leave_type,
        year=year,
        total_per_year=bal.total_per_year,
        used=bal.used,
        pending_days=pending,
        balance=h(balance),
        balance_after_pending=h(balance - pending),
    )


def get_punches(ctx: ToolContext, args: EmployeeDayIn) -> PunchesOut:
    emp = ctx.employee(args.employee_id)
    out = PunchesOut(employee_id=args.employee_id, date=args.date.isoformat(), shifts=[])
    if emp.role != "worker":
        out.note = f"{emp.employee_id} is a {emp.role.replace('_', ' ')}; only workers punch"
        return out
    if args.date > ctx.as_of.date():
        out.note = f"this date is after now ({ctx.as_of:%a %d %b %Y %H:%M}): no punches yet"
        return out
    dupes = {r.kept.punch_id: r.voided for r in ctx.processed.duplicate_runs}
    for s in ctx.processed.shifts:
        if s.employee_id != args.employee_id or s.date != args.date:
            continue
        punches = []
        for p in s.punches:
            punches.append(
                PunchOut(
                    id=p.punch_id, time=fmt_time(p.timestamp, s.date), type=p.type, source=p.source
                )
            )
            punches += [
                PunchOut(
                    id=d.punch_id,
                    time=fmt_time(d.timestamp, s.date),
                    type=d.type,
                    source=d.source,
                    duplicate=True,
                )
                for d in dupes.get(p.punch_id, ())
            ]
        sched = None
        if s.scheduled_start and s.scheduled_end:
            sched = f"{hhmm(s.scheduled_start)}-{hhmm(s.scheduled_end)}"
        out.shifts.append(
            ShiftOut(
                scheduled=sched,
                status=s.status,
                clock_in=fmt_time(s.clock_in.timestamp, s.date) if s.clock_in else None,
                clock_out=fmt_time(s.clock_out.timestamp, s.date) if s.clock_out else None,
                break_minutes=h(s.break_minutes),
                worked_hours=h(s.worked_hours) if s.worked_hours is not None else None,
                punches=punches,
            )
        )
    if not out.shifts:
        out.note = "no punches for this shift date"
    return out


_POLICY_ID = re.compile(r"^[Pp]0*(\d{1,2})$")


def get_policy(ctx: ToolContext, args: PolicyIn) -> PolicyOut:
    m = _POLICY_ID.match(args.policy_id.strip())
    pid = f"P{int(m.group(1))}" if m else args.policy_id
    rule = ctx.policy.policies.get(pid)
    section = ctx.policy_text.get(pid)
    if rule is None or section is None:
        known = sorted(ctx.policy.policies, key=lambda p: int(p[1:]))
        raise ToolInputError(
            "unknown_policy", f"no policy {args.policy_id!r}", hint=f"use one of {', '.join(known)}"
        )
    return PolicyOut(policy_id=pid, title=rule.title, text=section, limits=dict(rule.params))
