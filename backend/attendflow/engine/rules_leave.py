"""Phase 2 leave checks: P9 (punches on leave), P11 (balance), P12 (certificate), P13 (half day).

Plain code, limits from policy.json. Leave balance is always total_per_year - used,
computed here and never stored. `used` already includes approved leave, so the requests
still to decide are the pending ones.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from attendflow.data.schemas import LeaveRecord
from attendflow.engine.models import EvidenceRow, FixOption, Shift, TimecardException
from attendflow.engine.rules import (
    ACTIVE_LEAVE,
    RuleContext,
    day_label,
    fmt,
    h,
    hours_text,
    leave_days,
    make_exception,
    span_text,
)
from attendflow.engine.shifts import schedule_bounds


def _dates_text(entries: list[dict]) -> str:
    return ", ".join(
        day_label(date.fromisoformat(e["date"])) + (" (half)" if e["days"] == 0.5 else "")
        for e in entries
    )


def _shifts_by_day(ctx: RuleContext) -> dict[tuple[str, date], list[Shift]]:
    out: dict[tuple[str, date], list[Shift]] = defaultdict(list)
    for s in ctx.shifts:
        out[(s.employee_id, s.date)].append(s)
    return out


# ---------------------------------------------------------------- P9 punches on a leave day


def check_p9_punches_on_leave(ctx: RuleContext) -> list[TimecardException]:
    found = []
    for (emp, on), shifts in sorted(_shifts_by_day(ctx).items()):
        leave = ctx.active_leave_on(emp, on)
        if leave is None or leave.duration != "full":
            continue  # half-day leave is P13
        hours = [s.worked_hours for s in shifts]
        worked = None if None in hours else sum(x or 0 for x in hours)
        spans = ", ".join(span_text(s) for s in shifts)
        punch_ids = [p.punch_id for s in shifts for p in s.punches]
        cancel = (
            "Cancel the leave: the day counts as worked and 1 day goes back to the "
            f"{leave.leave_type} balance"
            if leave.status == "approved"
            else "Withdraw the pending leave request: the day counts as worked"
        )
        found.append(
            make_exception(
                ctx,
                "P9",
                emp,
                on,
                f"Punched {spans} ({hours_text(worked)}) on a full-day {leave.leave_type} "
                f"leave day ({leave.status})",
                {
                    "leave_type": leave.leave_type,
                    "leave_status": leave.status,
                    "worked_hours": h(worked) if worked is not None else None,
                    "punch_ids": punch_ids,
                },
                [*(p for s in shifts for p in s.punches), leave],
                fix_options=[
                    FixOption(
                        option_id="cancel_leave",
                        action="cancel_leave",
                        label=cancel,
                        params={"date": on.isoformat(), "leave_type": leave.leave_type, "days": 1},
                        requires_worker_confirmation=True,
                    ),
                    FixOption(
                        option_id="void_punches",
                        action="void_punches",
                        label="Keep the leave and void the punches made by mistake "
                        "(worker is asked first)",
                        params={"punch_ids": punch_ids},
                        requires_worker_confirmation=True,
                    ),
                ],
            )
        )
    return found


# ---------------------------------------------------------------- P11 leave balance


def check_p11_leave_balance(ctx: RuleContext) -> list[TimecardException]:
    found = []
    for b in sorted(ctx.leave_balances, key=lambda b: (b.employee_id, b.leave_type)):
        pending = sorted(
            (
                r
                for r in ctx.leave_records
                if r.employee_id == b.employee_id
                and r.leave_type == b.leave_type
                and r.status == "pending"
            ),
            key=lambda r: r.date,
        )
        applied = sum(leave_days(r) for r in pending)
        balance = b.total_per_year - b.used  # computed, never stored
        if applied <= balance:
            continue
        over = applied - balance
        # The balance pays for the earliest days first; the rest is over the balance.
        paid: list[dict] = []
        extra: list[dict] = []
        left = max(balance, 0.0)
        for r in pending:
            days = leave_days(r)
            take = min(days, left)
            left -= take
            if take > 0:
                paid.append({"date": r.date.isoformat(), "days": take})
            if days - take > 0:
                extra.append({"date": r.date.isoformat(), "days": days - take})

        lt = b.leave_type
        fixes = [
            FixOption(
                option_id="split_paid_unpaid",
                action="split_paid_unpaid_leave",
                label=f"Approve {fmt(sum(e['days'] for e in paid))} paid {lt} day(s)"
                + (f" ({_dates_text(paid)})" if paid else "")
                + f" and {fmt(over)} unpaid day(s) ({_dates_text(extra)})",
                params={"leave_type": lt, "paid": paid, "unpaid": extra},
            )
        ]
        # Move the extra days to another leave type that can cover all of them.
        others = sorted(
            (
                o
                for o in ctx.leave_balances
                if o.employee_id == b.employee_id and o.leave_type != lt
            ),
            key=lambda o: (o.leave_type != "casual", o.leave_type),  # casual first
        )
        for o in others:
            available = o.total_per_year - o.used - ctx.pending_days(o.employee_id, o.leave_type)
            if available >= over:
                fixes.append(
                    FixOption(
                        option_id=f"move_to_{o.leave_type}",
                        action="move_leave_type",
                        label=f"Take the {fmt(over)} extra day(s) ({_dates_text(extra)}) from "
                        f"{o.leave_type} leave ({fmt(available)} available)",
                        params={"from_type": lt, "to_type": o.leave_type, "days": extra},
                    )
                )
        fixes.append(
            FixOption(
                option_id="reject_extra_days",
                action="reject_leave_days",
                label=f"Reject the {fmt(over)} extra day(s) ({_dates_text(extra)})",
                params={"leave_type": lt, "days": extra},
            )
        )
        found.append(
            make_exception(
                ctx,
                "P11",
                b.employee_id,
                pending[0].date,
                f"{lt.capitalize()} leave applied {fmt(applied)}, balance {fmt(balance)} "
                f"({fmt(b.total_per_year)} total - {fmt(b.used)} used): "
                f"{fmt(over)} day(s) over the balance",
                {
                    "leave_type": lt,
                    "applied_days": applied,
                    "total_per_year": b.total_per_year,
                    "used": b.used,
                    "balance": balance,
                    "over_by_days": over,
                    "requested_dates": [r.date.isoformat() for r in pending],
                },
                [*pending, b],
                suffix=lt,
                fix_options=fixes,
            )
        )
    return found


# ---------------------------------------------------------------- P12 sick-leave certificate


def check_p12_sick_certificate(ctx: RuleContext) -> list[TimecardException]:
    limit = ctx.policy.number("P12", "max_sick_days_without_certificate")
    scheduled = {(r.employee_id, r.date) for r in ctx.schedule}
    worked = {(s.employee_id, s.date) for s in ctx.shifts}
    by_emp: dict[str, list[LeaveRecord]] = defaultdict(list)
    for r in ctx.leave_records:
        if r.leave_type == "sick" and r.status in ACTIVE_LEAVE:
            by_emp[r.employee_id].append(r)

    found = []
    for emp, records in sorted(by_emp.items()):
        records.sort(key=lambda r: r.date)  # sort BEFORE counting streaks

        def breaks_run(d: date, emp: str = emp) -> bool:
            # A scheduled (non-holiday) day or a worked day ends the run. Days off and
            # holidays in between do not.
            if (emp, d) in worked:
                return True
            return (emp, d) in scheduled and ctx.holiday_on(d) is None

        runs: list[list[LeaveRecord]] = []
        for r in records:
            if runs:
                prev = runs[-1][-1].date
                gap = [prev + timedelta(days=i) for i in range(1, (r.date - prev).days)]
                if not any(breaks_run(d) for d in gap):
                    runs[-1].append(r)
                    continue
            runs.append([r])

        for run in runs:
            days = sum(leave_days(r) for r in run)
            if days <= limit or any(r.certificate_uploaded for r in run):
                continue
            # Days beyond the limit, in date order (the ones a certificate is needed for).
            count, beyond = 0.0, []
            for r in run:
                count += leave_days(r)
                if count > limit:
                    beyond.append(r.date.isoformat())
            start, end = run[0].date, run[-1].date
            dates = [r.date.isoformat() for r in run]
            beyond_txt = ", ".join(day_label(date.fromisoformat(d)) for d in beyond)
            found.append(
                make_exception(
                    ctx,
                    "P12",
                    emp,
                    start,
                    f"{fmt(days)} sick days in a row ({day_label(start)} to {day_label(end)}) "
                    f"with no medical certificate (needed after {fmt(limit)} days)",
                    {
                        "sick_days": days,
                        "max_sick_days_without_certificate": limit,
                        "run_start": start.isoformat(),
                        "run_end": end.isoformat(),
                        "dates": dates,
                        "statuses": sorted({r.status for r in run}),
                        "certificate_uploaded": False,
                    },
                    list(run),
                    fix_options=[
                        FixOption(
                            option_id="request_certificate",
                            action="request_certificate",
                            label="Ask the worker to upload a medical certificate "
                            "(the days stay pending until it arrives)",
                            params={"dates": dates},
                        ),
                        FixOption(
                            option_id="approve_without_certificate",
                            action="approve_without_certificate",
                            label="Supervisor approves the sick days without a certificate",
                            params={"dates": dates},
                        ),
                        FixOption(
                            option_id="unpaid_beyond_limit",
                            action="reject_leave_days",
                            label=f"No certificate: mark the days after day {fmt(limit)} as "
                            f"unpaid ({beyond_txt})",
                            params={"leave_type": "sick", "dates": beyond, "as": "unpaid"},
                        ),
                    ],
                )
            )
    return found


# ---------------------------------------------------------------- P13 half-day leave


def check_p13_half_day(ctx: RuleContext) -> list[TimecardException]:
    half = ctx.policy.number("P13", "half_day_hours")
    tol = ctx.policy.number("P13", "tolerance_hours")
    grace = timedelta(hours=ctx.policy.number("P1", "open_shift_grace_hours"))
    rows = {(r.employee_id, r.date): r for r in ctx.schedule}
    shifts_by_day = _shifts_by_day(ctx)
    found = []
    for leave in sorted(ctx.leave_records, key=lambda r: (r.employee_id, r.date)):
        if leave.duration != "half" or leave.status not in ACTIVE_LEAVE:
            continue
        emp, on = leave.employee_id, leave.date
        shifts = shifts_by_day.get((emp, on), [])
        if any(s.worked_hours is None for s in shifts):
            continue  # missing punch or still running: P1 first
        worked = sum(s.worked_hours or 0 for s in shifts)
        row = rows.get((emp, on))
        day_end = (
            schedule_bounds(row)[1] + grace
            if row
            else datetime.combine(on, time()) + timedelta(days=1)
        )
        evidence: list[EvidenceRow] = [*(p for s in shifts for p in s.punches), leave]
        if row:
            evidence.append(row)
        details = {
            "leave_type": leave.leave_type,
            "leave_status": leave.status,
            "worked_hours": h(worked),
            "half_day_hours": half,
            "tolerance_hours": tol,
            "expected_min_hours": h(half - tol),
            "expected_max_hours": h(half + tol),
        }
        expect = f"expected about {fmt(half)} h ({fmt(half - tol)}-{fmt(half + tol)} h)"
        what = f"Half-day {leave.leave_type} leave ({leave.status})"
        punch_ids = [p.punch_id for s in shifts for p in s.punches]
        if worked > half + tol:
            fixes = [
                FixOption(
                    option_id="cancel_leave",
                    action="cancel_leave",
                    label="Cancel the half-day leave: the full day counts as worked and 0.5 day "
                    f"goes back to the {leave.leave_type} balance",
                    params={"date": on.isoformat(), "leave_type": leave.leave_type, "days": 0.5},
                    requires_worker_confirmation=True,
                ),
                FixOption(
                    option_id="edit_punches",
                    action="edit_punches",
                    label="Keep the leave and correct the punches to the times the worker confirms",
                    params={"punch_ids": punch_ids},
                    requires_worker_confirmation=True,
                ),
            ]
            found.append(
                make_exception(
                    ctx,
                    "P13",
                    emp,
                    on,
                    f"{what}, but {fmt(worked)} h worked: {expect}",
                    {**details, "type": "worked_full_day"},
                    evidence,
                    fix_options=fixes,
                )
            )
        elif worked < half - tol and day_end <= ctx.as_of:
            missing = half - worked
            fixes = [
                FixOption(
                    option_id="convert_to_full_day_leave",
                    action="convert_to_full_day_leave",
                    label=f"Change it to a full day of {leave.leave_type} leave",
                    params={"date": on.isoformat(), "leave_type": leave.leave_type},
                    requires_worker_confirmation=True,
                ),
                FixOption(
                    option_id="mark_unpaid_hours",
                    action="mark_unpaid_hours",
                    label=f"Keep the half-day leave and mark {fmt(missing)} h as unpaid",
                    params={"date": on.isoformat(), "hours": h(missing)},
                    requires_worker_confirmation=True,
                ),
                FixOption(
                    option_id="edit_punches",
                    action="edit_punches",
                    label="Correct or add punches to the times the worker confirms",
                    params={"punch_ids": punch_ids},
                    requires_worker_confirmation=True,
                ),
            ]
            found.append(
                make_exception(
                    ctx,
                    "P13",
                    emp,
                    on,
                    f"{what}, but only {fmt(worked)} h worked: {expect}",
                    {**details, "type": "working_half_missing"},
                    evidence,
                    fix_options=fixes,
                )
            )
    return found
