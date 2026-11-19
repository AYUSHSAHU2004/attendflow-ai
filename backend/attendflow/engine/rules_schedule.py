"""Phase 2 checks against the schedule and the holiday calendar: P8, P10, P14 and P16.

Plain code, limits from policy.json. Shared helpers live in rules.py.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Literal

from attendflow.data.schemas import ScheduleRow
from attendflow.engine.models import EvidenceRow, FixOption, Shift, TimecardException
from attendflow.engine.rules import (
    RuleContext,
    day_label,
    fmt,
    h,
    hhmm,
    hours_text,
    iso,
    make_exception,
    span_text,
)
from attendflow.engine.shifts import schedule_bounds, scheduled_hours

# ---------------------------------------------------------------- P8 unscheduled work


def check_p8_unscheduled_work(ctx: RuleContext) -> list[TimecardException]:
    scheduled_days = {(r.employee_id, r.date) for r in ctx.schedule}
    found = []
    for s in ctx.shifts:
        if s.schedule is not None:
            continue
        worked = s.worked_hours
        holiday = ctx.holiday_on(s.date)
        on_holiday = f" on {holiday.name}" if holiday else ""
        fixes = [
            FixOption(
                option_id="approve_unscheduled_work",
                action="approve_unscheduled_work",
                label=f"Approve the unscheduled work ({hours_text(worked)}) as an extra shift",
                params={
                    "date": s.date.isoformat(),
                    "worked_hours": h(worked) if worked is not None else None,
                },
            ),
            FixOption(
                option_id="reject_unscheduled_work",
                action="reject_unscheduled_work",
                label="Reject the unscheduled work: the hours are not paid (worker is asked first)",
                params={"date": s.date.isoformat(), "punch_ids": [p.punch_id for p in s.punches]},
            ),
        ]
        found.append(
            make_exception(
                ctx,
                "P8",
                s.employee_id,
                s.date,
                f"Punched {span_text(s)} ({hours_text(worked)}) with no scheduled shift"
                f"{on_holiday}",
                {
                    "clock_in": iso(s.clock_in.timestamp) if s.clock_in else None,
                    "clock_out": iso(s.clock_out.timestamp) if s.clock_out else None,
                    "worked_hours": h(worked) if worked is not None else None,
                    "other_shift_scheduled_that_day": (s.employee_id, s.date) in scheduled_days,
                    "holiday": holiday.name if holiday else None,
                },
                s.punches,
                suffix=s.punches[0].punch_id,
                fix_options=fixes,
            )
        )
    return found


# ---------------------------------------------------------------- P10 unexplained absence


def check_p10_absence(ctx: RuleContext) -> list[TimecardException]:
    grace = timedelta(hours=ctx.policy.number("P1", "open_shift_grace_hours"))
    worked_days = {(s.employee_id, s.date) for s in ctx.shifts}
    found = []
    for r in sorted(ctx.schedule, key=lambda r: (r.employee_id, r.date)):
        if (r.employee_id, r.date) in worked_days:
            continue
        start, end = schedule_bounds(r)
        if end + grace > ctx.as_of:
            continue  # not over yet (or still inside the P1 grace)
        if ctx.leave_on(r.employee_id, r.date) is not None:
            continue  # a leave request of any status explains the day (P11/P12 judge it)
        hours = scheduled_hours(r, ctx.policy)
        holiday = ctx.holiday_on(r.date)
        fixes = _p10_fix_options(ctx, r, start, end, hours)
        duty = f" (holiday duty on {holiday.name})" if holiday else ""
        found.append(
            make_exception(
                ctx,
                "P10",
                r.employee_id,
                r.date,
                f"Scheduled {hhmm(start)}-{hhmm(end)}{duty}: no punches and no leave request",
                {
                    "scheduled_start": iso(start),
                    "scheduled_end": iso(end),
                    "scheduled_hours": h(hours),
                    "holiday": holiday.name if holiday else None,
                    "open_shift_grace_hours": ctx.policy.number("P1", "open_shift_grace_hours"),
                },
                [r],
                fix_options=fixes,
            )
        )
    return found


def _p10_fix_options(
    ctx: RuleContext, r: ScheduleRow, start: datetime, end: datetime, hours: float
) -> list[FixOption]:
    fixes = []
    for b in sorted(ctx.leave_balances, key=lambda b: b.leave_type):
        if b.employee_id != r.employee_id:
            continue
        available = b.total_per_year - b.used - ctx.pending_days(r.employee_id, b.leave_type)
        if available >= 1:
            fixes.append(
                FixOption(
                    option_id=f"record_{b.leave_type}_leave",
                    action="record_leave",
                    label=f"Record a day of {b.leave_type} leave ({fmt(available)} available)",
                    params={"date": r.date.isoformat(), "leave_type": b.leave_type, "days": 1},
                )
            )
    fixes += [
        FixOption(
            option_id="mark_unpaid_absence",
            action="mark_unpaid_absence",
            label=f"Mark as unpaid absence ({fmt(hours)} h)",
            params={"date": r.date.isoformat(), "hours": h(hours)},
        ),
        FixOption(
            option_id="add_scheduled_punches",
            action="add_punches",
            label=f"Worker was present (device failure): add punches {hhmm(start)}-{hhmm(end)}",
            params={"clock_in": iso(start), "clock_out": iso(end)},
        ),
    ]
    return fixes


# ---------------------------------------------------------------- P14 holiday work


def check_p14_holiday_work(ctx: RuleContext) -> list[TimecardException]:
    options = ctx.policy.strings("P14", "compensation_options")
    half_max = ctx.policy.number("P14", "comp_off_half_day_max_hours")
    duty_severity: Any = ctx.policy.param("P14", "scheduled_duty_severity")
    found = []
    for s in ctx.shifts:
        holiday = ctx.holiday_on(s.date)
        if holiday is None:
            continue
        scheduled = s.schedule is not None
        worked = s.worked_hours
        depends_on = []
        if s.status in ("missing_in", "missing_out"):
            depends_on.append("P1")
        if not scheduled:
            depends_on.append("P8")
        # Hours to compensate: the punches, or the scheduled hours while a punch is missing.
        if worked is not None:
            basis, basis_source = worked, "worked"
        elif s.schedule is not None:
            basis, basis_source = scheduled_hours(s.schedule, ctx.policy), "scheduled"
        else:
            basis, basis_source = None, "unknown"
        comp_days = None if basis is None else (0.5 if basis <= half_max else 1.0)

        fixes = []
        hours_note = "" if basis_source == "worked" else " (scheduled hours until P1 is fixed)"
        if "holiday_pay" in options:
            fixes.append(
                FixOption(
                    option_id="holiday_pay",
                    action="holiday_pay",
                    label=f"Holiday pay for {fmt(basis)} h{hours_note}"
                    if basis is not None
                    else "Holiday pay for the hours worked (after P1 is fixed)",
                    params={
                        "date": s.date.isoformat(),
                        "hours": h(basis) if basis is not None else None,
                    },
                )
            )
        if "comp_off" in options:
            days_txt = "a full day" if comp_days == 1.0 else "half a day"
            fixes.append(
                FixOption(
                    option_id="comp_off",
                    action="comp_off",
                    label=f"Comp-off: {days_txt} off later{hours_note}"
                    if comp_days is not None
                    else "Comp-off (size decided after P1 is fixed)",
                    params={"date": s.date.isoformat(), "days": comp_days},
                )
            )
        who = "planned holiday duty" if scheduled else "not scheduled"
        first = " First: " + ", ".join(depends_on) + "." if depends_on else ""
        found.append(
            make_exception(
                ctx,
                "P14",
                s.employee_id,
                s.date,
                f"Worked {span_text(s)} ({hours_text(worked)}) on {holiday.name}, {who}: "
                f"choose holiday pay or comp-off.{first}",
                {
                    "holiday": holiday.name,
                    "holiday_type": holiday.type,
                    "scheduled": scheduled,
                    "worked_hours": h(worked) if worked is not None else None,
                    "compensation_hours": h(basis) if basis is not None else None,
                    "compensation_hours_source": basis_source,
                    "comp_off_days": comp_days,
                    "comp_off_half_day_max_hours": half_max,
                    "depends_on": depends_on,
                },
                [*s.punches, holiday],
                suffix=s.punches[0].punch_id,
                fix_options=fixes,
                severity=duty_severity if scheduled else None,
            )
        )
    return found


# ---------------------------------------------------------------- P16 consecutive days


def check_p16_consecutive_days(ctx: RuleContext) -> list[TimecardException]:
    limit = int(ctx.policy.number("P16", "max_consecutive_days"))
    shifts_by_emp = ctx.shifts_by_employee()
    rows_by_emp = ctx.schedule_by_employee()
    found = []
    for emp in sorted(shifts_by_emp.keys() | rows_by_emp.keys()):
        worked: dict[date, list[Shift]] = {}
        for s in shifts_by_emp.get(emp, []):
            worked.setdefault(s.date, []).append(s)
        # Upcoming scheduled days that will be worked (not on full-day leave).
        planned: dict[date, ScheduleRow] = {
            r.date: r
            for r in rows_by_emp.get(emp, [])
            if r.date not in worked
            and schedule_bounds(r)[0] > ctx.as_of
            and ctx.planned_hours(r) > 0
        }
        for run in _runs(sorted(worked.keys() | planned.keys())):
            if len(run) <= limit:
                continue
            found.append(_p16_exception(ctx, emp, run, limit, worked, planned))
    return found


def _runs(days: list[date]) -> list[list[date]]:
    runs: list[list[date]] = []
    for d in days:
        if runs and d - runs[-1][-1] == timedelta(days=1):
            runs[-1].append(d)
        else:
            runs.append([d])
    return runs


def _p16_exception(
    ctx: RuleContext,
    emp: str,
    run: list[date],
    limit: int,
    worked: dict[date, list[Shift]],
    planned: dict[date, ScheduleRow],
) -> TimecardException:
    breach_day = run[limit]  # the first day over the limit (the 7th)
    kind: Literal["breach", "risk"] = (
        "breach" if all(d in worked for d in run[: limit + 1]) else "risk"
    )
    upcoming = [d for d in run[limit:] if d in planned]
    fixes = []
    if upcoming:
        fixes.append(
            FixOption(
                option_id="give_rest_day",
                action="give_rest_day",
                label=f"Give a rest day on {day_label(upcoming[0])} (remove that shift)",
                params={"date": upcoming[0].isoformat()},
            )
        )
    fixes.append(
        FixOption(
            option_id="approve_exception",
            action="approve_exception",
            label=f"Record an approved exception for {len(run)} days in a row",
            params={"run_start": run[0].isoformat(), "run_end": run[-1].isoformat()},
        )
    )
    evidence: list[EvidenceRow] = [
        p for d in run if d in worked for s in worked[d] for p in s.punches
    ]
    evidence += [planned[d] for d in run if d in planned]
    return make_exception(
        ctx,
        "P16",
        emp,
        breach_day,
        f"{len(run)} working days in a row ({day_label(run[0])} to {day_label(run[-1])}) "
        f"> {limit} allowed",
        {
            "run_start": run[0].isoformat(),
            "run_end": run[-1].isoformat(),
            "consecutive_days": len(run),
            "max_consecutive_days": limit,
            "first_day_over_limit": breach_day.isoformat(),
            "days": [
                {"date": d.isoformat(), "source": "worked" if d in worked else "scheduled"}
                for d in run
            ],
        },
        evidence,
        kind=kind,
        fix_options=fixes,
    )
