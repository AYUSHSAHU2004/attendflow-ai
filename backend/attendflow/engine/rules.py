"""Shared rule context and helpers, plus one check function per policy for P1-P7.

Every limit is read from policy.json. Each check takes the same RuleContext and returns a
list of TimecardException. P15 is not a check: it is applied when punches are grouped into
shifts (see shifts.py). Phase 2 checks live in rules_schedule.py, rules_leave.py and
rules_review.py; the full ordered registry is in checks.py.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Literal

from attendflow.data.schemas import Holiday, LeaveBalance, LeaveRecord, Punch, ScheduleRow
from attendflow.engine.models import EvidenceRow, FixOption, Shift, TimecardException
from attendflow.engine.shifts import DuplicateRun, schedule_bounds, scheduled_hours
from attendflow.policy.models import PolicyConfig

ACTIVE_LEAVE = ("approved", "pending")  # rejected leave is ignored everywhere except P10


@dataclass
class RuleContext:
    policy: PolicyConfig
    as_of: datetime
    shifts: list[Shift]
    schedule: list[ScheduleRow]
    duplicate_runs: list[DuplicateRun] = field(default_factory=list)
    leave_records: list[LeaveRecord] = field(default_factory=list)
    leave_balances: list[LeaveBalance] = field(default_factory=list)
    holidays: list[Holiday] = field(default_factory=list)
    punches: list[Punch] = field(default_factory=list)  # past punches, before P2 de-dup
    # Stage 1, built before any check runs: leave is applied to the schedule, so the
    # forecast checks (P5, P6, P16) never count a leave day as hours still to work.
    planned: dict[tuple[str, date], float] = field(init=False)

    def __post_init__(self) -> None:
        self._leave = {(r.employee_id, r.date): r for r in self.leave_records}
        counted = set(self.policy.strings("P14", "counted_holiday_types"))
        self._holidays = {h.date: h for h in self.holidays if h.type in counted}
        self.planned = {(r.employee_id, r.date): self._leave_adjusted(r) for r in self.schedule}

    def _leave_adjusted(self, row: ScheduleRow) -> float:
        hours = scheduled_hours(row, self.policy)
        leave = self.active_leave_on(row.employee_id, row.date)
        if leave is None:
            return hours
        if leave.duration == "full":
            return 0.0
        return max(0.0, hours - self.policy.number("P13", "half_day_hours"))

    # ------------------------------------------------------------ lookups

    def shifts_by_employee(self) -> dict[str, list[Shift]]:
        out: dict[str, list[Shift]] = defaultdict(list)
        for s in self.shifts:
            out[s.employee_id].append(s)
        return out

    def schedule_by_employee(self) -> dict[str, list[ScheduleRow]]:
        out: dict[str, list[ScheduleRow]] = defaultdict(list)
        for r in self.schedule:
            out[r.employee_id].append(r)
        return out

    def planned_hours(self, row: ScheduleRow) -> float:
        """Scheduled hours after leave: 0 on a full-day leave, minus 4 h on a half day."""
        return self.planned[(row.employee_id, row.date)]

    def leave_on(self, employee_id: str, on: date) -> LeaveRecord | None:
        """The leave record for that day, any status (only one per day is allowed)."""
        return self._leave.get((employee_id, on))

    def active_leave_on(self, employee_id: str, on: date) -> LeaveRecord | None:
        """Approved or pending leave for that day. Rejected leave does not count."""
        leave = self._leave.get((employee_id, on))
        return leave if leave is not None and leave.status in ACTIVE_LEAVE else None

    def holiday_on(self, on: date) -> Holiday | None:
        """A holiday that counts for P14 (national or company by default)."""
        return self._holidays.get(on)

    def balance_row(self, employee_id: str, leave_type: str) -> LeaveBalance | None:
        for b in self.leave_balances:
            if b.employee_id == employee_id and b.leave_type == leave_type:
                return b
        return None

    def pending_days(self, employee_id: str, leave_type: str) -> float:
        return sum(
            leave_days(r)
            for r in self.leave_records
            if r.employee_id == employee_id and r.leave_type == leave_type and r.status == "pending"
        )


def leave_days(record: LeaveRecord) -> float:
    return 1.0 if record.duration == "full" else 0.5


# ---------------------------------------------------------------- formatting helpers


def h(value: float) -> float:
    """Round hours or minutes for display and storage (2 decimals)."""
    return round(value, 2)


def fmt(value: float) -> str:
    """36.0 -> '36', 7.5333 -> '7.53'."""
    return f"{round(value, 2):g}"


def to_minute(ts: datetime) -> datetime:
    """Round to the nearest minute for display (punches carry seconds)."""
    return (ts + timedelta(seconds=30)).replace(second=0, microsecond=0)


def iso(ts: datetime | None) -> str | None:
    return to_minute(ts).isoformat(timespec="minutes") if ts else None


def hhmm(ts: datetime) -> str:
    return to_minute(ts).strftime("%H:%M")


def day_label(d: date) -> str:
    return d.strftime("%a %d %b")


def _make(
    ctx: RuleContext,
    policy_id: str,
    employee_id: str,
    on: date,
    summary: str,
    details: dict[str, Any],
    evidence: list[EvidenceRow],
    *,
    suffix: str = "",
    kind: Literal["breach", "risk"] = "breach",
    status: Literal["open", "auto_resolved"] = "open",
    fix_options: list[FixOption] | None = None,
    severity: Literal["low", "medium", "high"] | None = None,
) -> TimecardException:
    rule = ctx.policy.policies[policy_id]
    if rule.severity == "info":  # P15 never produces exceptions
        raise ValueError(f"{policy_id} is informational and cannot raise an exception")
    exception_id = f"{policy_id}-{employee_id}-{on.isoformat()}" + (f"-{suffix}" if suffix else "")
    # Punches first, in time order; then the other rows in the order given. No duplicates.
    punches = {p.punch_id: p for p in evidence if isinstance(p, Punch)}
    others = list(dict.fromkeys(r for r in evidence if not isinstance(r, Punch)))
    return TimecardException(
        exception_id=exception_id,
        policy_id=policy_id,
        title=rule.title,
        employee_id=employee_id,
        date=on,
        severity=severity or rule.severity,  # type: ignore[arg-type]
        kind=kind,
        status=status,
        summary=summary,
        details=details,
        evidence=[*sorted(punches.values(), key=lambda p: (p.timestamp, p.punch_id)), *others],
        fix_options=fix_options or [],
    )


make_exception = _make  # public name for the Phase 2 rule modules


def span_text(s: Shift) -> str:
    """'09:00-18:00' for a complete shift, 'from 09:00' when the clock-out is missing."""
    start = s.clock_in.timestamp if s.clock_in else s.punches[0].timestamp
    if s.clock_out is None:
        return f"from {hhmm(start)}"
    return f"{hhmm(start)}-{hhmm(s.clock_out.timestamp)}"


def hours_text(worked: float | None) -> str:
    return f"{fmt(worked)} h" if worked is not None else "hours unknown, missing punch"


# ---------------------------------------------------------------- P1 missing punch


def check_p1_missing_punch(ctx: RuleContext) -> list[TimecardException]:
    found = []
    for s in ctx.shifts:
        if s.status == "missing_out":
            assert s.clock_in is not None
            fixes = []
            if s.scheduled_end is not None:
                span = (s.scheduled_end - s.clock_in.timestamp).total_seconds() / 3600
                fixes.append(
                    FixOption(
                        option_id="set_clock_out_to_scheduled_end",
                        action="set_clock_out",
                        label=f"Set clock-out to the scheduled shift end ({hhmm(s.scheduled_end)})",
                        params={
                            "timestamp": iso(s.scheduled_end),
                            "worked_hours_after_fix": h(span - s.break_minutes / 60),
                        },
                    )
                )
            end_txt = f"scheduled end {hhmm(s.scheduled_end)}" if s.scheduled_end else "unscheduled"
            found.append(
                _make(
                    ctx,
                    "P1",
                    s.employee_id,
                    s.date,
                    f"Clock-in {hhmm(s.clock_in.timestamp)}, no clock-out ({end_txt})",
                    {
                        "missing": "clock_out",
                        "clock_in": iso(s.clock_in.timestamp),
                        "scheduled_start": iso(s.scheduled_start),
                        "scheduled_end": iso(s.scheduled_end),
                        "break_minutes": h(s.break_minutes),
                        "open_shift_grace_hours": ctx.policy.number("P1", "open_shift_grace_hours"),
                    },
                    s.punches,
                    fix_options=fixes,
                )
            )
        elif s.status == "missing_in":
            fixes = []
            if s.scheduled_start is not None:
                fixes.append(
                    FixOption(
                        option_id="set_clock_in_to_scheduled_start",
                        action="set_clock_in",
                        label=f"Set clock-in to the scheduled shift start "
                        f"({hhmm(s.scheduled_start)})",
                        params={"timestamp": iso(s.scheduled_start)},
                    )
                )
            out_txt = f"clock-out {hhmm(s.clock_out.timestamp)}" if s.clock_out else "no clock-out"
            found.append(
                _make(
                    ctx,
                    "P1",
                    s.employee_id,
                    s.date,
                    f"No clock-in ({out_txt})",
                    {
                        "missing": "clock_in" if s.clock_out else "clock_in_and_clock_out",
                        "clock_out": iso(s.clock_out.timestamp) if s.clock_out else None,
                        "scheduled_start": iso(s.scheduled_start),
                        "scheduled_end": iso(s.scheduled_end),
                    },
                    s.punches,
                    fix_options=fixes,
                )
            )
    return found


# ---------------------------------------------------------------- P2 duplicate punch


def check_p2_duplicate_punch(ctx: RuleContext) -> list[TimecardException]:
    shift_date = {p.punch_id: s.date for s in ctx.shifts for p in s.punches}
    window = ctx.policy.number("P2", "duplicate_window_minutes")
    status: Literal["open", "auto_resolved"] = (
        "auto_resolved" if ctx.policy.policies["P2"].auto_resolve else "open"
    )
    found = []
    for run in ctx.duplicate_runs:
        kept, voided = run.kept, run.voided
        gap = (voided[-1].timestamp - kept.timestamp).total_seconds() / 60
        on = shift_date.get(kept.punch_id, kept.timestamp.date())
        voided_txt = ", ".join(f"{p.punch_id} {hhmm(p.timestamp)}" for p in voided)
        found.append(
            _make(
                ctx,
                "P2",
                kept.employee_id,
                on,
                f"{len(voided) + 1} '{kept.type}' taps within {fmt(gap)} min: kept "
                f"{kept.punch_id} {hhmm(kept.timestamp)}, voided {voided_txt}",
                {
                    "punch_type": kept.type,
                    "kept_punch_id": kept.punch_id,
                    "voided_punch_ids": [p.punch_id for p in voided],
                    "gap_minutes": h(gap),
                    "duplicate_window_minutes": window,
                },
                [kept, *voided],
                suffix=kept.punch_id,
                status=status,
            )
        )
    return found


# ---------------------------------------------------------------- P3 daily hours


def check_p3_daily_hours(ctx: RuleContext) -> list[TimecardException]:
    limit = ctx.policy.number("P3", "max_hours_per_day")
    per_day: dict[tuple[str, date], list[Shift]] = defaultdict(list)
    for s in ctx.shifts:
        if s.worked_hours is not None:
            per_day[(s.employee_id, s.date)].append(s)
    found = []
    for (emp, on), shifts in sorted(per_day.items()):
        worked = sum(s.worked_hours or 0 for s in shifts)
        if worked > limit:
            found.append(
                _make(
                    ctx,
                    "P3",
                    emp,
                    on,
                    f"{fmt(worked)} h worked > {fmt(limit)} h daily limit "
                    f"(over by {fmt(worked - limit)} h)",
                    {
                        "worked_hours": h(worked),
                        "max_hours_per_day": limit,
                        "over_by_hours": h(worked - limit),
                        "shifts": len(shifts),
                    },
                    [p for s in shifts for p in s.punches],
                )
            )
    return found


# ---------------------------------------------------------------- P4 break


def check_p4_break(ctx: RuleContext) -> list[TimecardException]:
    after = ctx.policy.number("P4", "break_required_after_hours")
    min_break = ctx.policy.number("P4", "min_break_minutes")
    found = []
    for s in ctx.shifts:
        worked = s.worked_hours
        if worked is None or worked <= after or s.break_minutes >= min_break:
            continue
        found.append(
            _make(
                ctx,
                "P4",
                s.employee_id,
                s.date,
                f"{fmt(worked)} h worked with {fmt(s.break_minutes)} min break "
                f"(needs {fmt(min_break)} min after {fmt(after)} h)",
                {
                    "worked_hours": h(worked),
                    "break_minutes": h(s.break_minutes),
                    "break_required_after_hours": after,
                    "min_break_minutes": min_break,
                },
                s.punches,
            )
        )
    return found


# ---------------------------------------------------------------- P5 weekly overtime


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())  # policy.json: week_starts_on = monday


def _p5_fix_options(
    over_by: float, future: list[tuple[date, float]], limit: float
) -> list[FixOption]:
    fixes = [
        FixOption(
            option_id="approve_overtime",
            action="approve_overtime",
            label=f"Approve {fmt(over_by)} h of overtime this week",
            params={"hours": h(over_by)},
        )
    ]
    # Cut the exact hours needed, starting with the last upcoming shift of the week.
    remaining, cuts = over_by, []
    for on, hours in sorted(future, reverse=True):
        if remaining <= 0:
            break
        cut = min(hours, remaining)
        cuts.append(
            {
                "date": on.isoformat(),
                "scheduled_hours": h(hours),
                "new_hours": h(hours - cut),
                "cut_hours": h(cut),
            }
        )
        remaining -= cut
    if cuts and remaining <= 1e-9:
        parts = ", ".join(
            f"{day_label(date.fromisoformat(c['date']))} {fmt(c['scheduled_hours'])} h -> "
            f"{fmt(c['new_hours'])} h"
            for c in cuts
        )
        fixes.append(
            FixOption(
                option_id="reduce_upcoming_shifts",
                action="reduce_scheduled_hours",
                label=f"Cut {fmt(over_by)} h from upcoming shifts to reach {fmt(limit)} h: {parts}",
                params={"total_cut_hours": h(over_by), "cuts": cuts},
            )
        )
    return fixes


def check_p5_weekly_overtime(ctx: RuleContext) -> list[TimecardException]:
    limit = ctx.policy.number("P5", "weekly_overtime_after_hours")
    shifts_by_emp = ctx.shifts_by_employee()
    rows_by_emp = ctx.schedule_by_employee()
    found = []
    for emp in sorted(shifts_by_emp.keys() | rows_by_emp.keys()):
        shifts, rows = shifts_by_emp.get(emp, []), rows_by_emp.get(emp, [])
        weeks = sorted({week_start(r.date) for r in rows} | {week_start(s.date) for s in shifts})
        for wk in weeks:
            in_week = lambda d, wk=wk: wk <= d < wk + timedelta(days=7)  # noqa: E731
            days: list[dict[str, Any]] = []
            worked = 0.0
            future: list[tuple[date, float]] = []  # (date, hours) that can still be changed
            covered: set[date] = set()
            for s in shifts:
                if not in_week(s.date):
                    continue
                if s.schedule is not None:
                    covered.add(s.schedule.date)
                if s.worked_hours is not None:
                    hours, source = s.worked_hours, "worked"
                    worked += hours
                elif s.schedule is None:
                    hours, source = 0.0, "unknown (missing punch, unscheduled)"
                elif s.status == "in_progress":
                    hours, source = scheduled_hours(s.schedule, ctx.policy), "in progress"
                else:
                    # Past shift with a missing punch: estimate at its scheduled hours.
                    hours, source = scheduled_hours(s.schedule, ctx.policy), "estimated"
                    worked += hours
                days.append({"date": s.date.isoformat(), "hours": h(hours), "source": source})

            remaining = 0.0
            for r in rows:
                if not in_week(r.date) or r.date in covered:
                    continue
                start, end = schedule_bounds(r)
                if end <= ctx.as_of:
                    continue  # past scheduled day without punches: an absence, not hours
                hours = ctx.planned_hours(r)  # leave already taken out of the schedule
                leave = ctx.active_leave_on(emp, r.date)
                source = "scheduled"
                if leave is not None:
                    source = f"{leave.duration}-day {leave.leave_type} leave ({leave.status})"
                    if leave.duration == "half":
                        source = f"scheduled minus {source}"
                days.append({"date": r.date.isoformat(), "hours": h(hours), "source": source})
                if hours <= 0:
                    continue
                remaining += hours
                if start > ctx.as_of:
                    future.append((r.date, hours))
            # In-progress shifts still count as scheduled hours.
            remaining += sum(d["hours"] for d in days if d["source"] == "in progress")

            projected = worked + remaining
            if projected <= limit:
                continue
            over_by = projected - limit
            kind: Literal["breach", "risk"] = "breach" if worked > limit else "risk"
            found.append(
                _make(
                    ctx,
                    "P5",
                    emp,
                    wk,
                    f"{fmt(worked)} h worked + {fmt(remaining)} h scheduled = "
                    f"{fmt(projected)} h > {fmt(limit)} h (over by {fmt(over_by)} h)",
                    {
                        "week_start": wk.isoformat(),
                        "week_end": (wk + timedelta(days=6)).isoformat(),
                        "worked_hours": h(worked),
                        "scheduled_remaining_hours": h(remaining),
                        "projected_hours": h(projected),
                        "weekly_overtime_after_hours": limit,
                        "over_by_hours": h(over_by),
                        "days": sorted(days, key=lambda d: d["date"]),
                    },
                    [p for s in shifts if in_week(s.date) for p in s.punches],
                    kind=kind,
                    fix_options=_p5_fix_options(over_by, future, limit),
                )
            )
    return found


# ---------------------------------------------------------------- P6 rest between shifts


@dataclass(frozen=True)
class _Period:
    date: date
    start: datetime | None
    end: datetime | None
    start_actual: bool
    end_actual: bool
    start_punch: Punch | None = None
    end_punch: Punch | None = None


def _periods(shifts: list[Shift], rows: list[ScheduleRow], as_of: datetime) -> list[_Period]:
    periods = []
    covered = {s.schedule.date for s in shifts if s.schedule is not None}
    for s in shifts:
        start = s.clock_in.timestamp if s.clock_in else s.scheduled_start
        if s.clock_out:
            end, end_actual = s.clock_out.timestamp, True
        else:
            end, end_actual = s.scheduled_end, False  # estimate until corrected
        periods.append(
            _Period(s.date, start, end, s.clock_in is not None, end_actual, s.clock_in, s.clock_out)
        )
    for r in rows:
        start, end = schedule_bounds(r)
        if r.date not in covered and start > as_of:  # upcoming shift: forecast
            periods.append(_Period(r.date, start, end, False, False))
    return sorted(periods, key=lambda p: p.start or datetime.max)


def check_p6_rest(ctx: RuleContext) -> list[TimecardException]:
    min_rest = ctx.policy.number("P6", "min_rest_hours")
    rows_by_emp = ctx.schedule_by_employee()
    found = []
    for emp, shifts in sorted(ctx.shifts_by_employee().items()):
        # Upcoming shifts on full-day leave will not be worked, so they are not forecast.
        rows = [r for r in rows_by_emp.get(emp, []) if ctx.planned_hours(r) > 0]
        periods = _periods(shifts, rows, ctx.as_of)
        for prev, nxt in zip(periods, periods[1:], strict=False):
            if prev.end is None or nxt.start is None:
                continue
            rest = (nxt.start - prev.end).total_seconds() / 3600
            if rest >= min_rest:
                continue
            actual = prev.end_actual and nxt.start_actual
            found.append(
                _make(
                    ctx,
                    "P6",
                    emp,
                    nxt.date,
                    f"{fmt(rest)} h rest before this shift < {fmt(min_rest)} h "
                    f"(short by {fmt(min_rest - rest)} h)",
                    {
                        "previous_shift_date": prev.date.isoformat(),
                        "previous_end": iso(prev.end),
                        "previous_end_source": "punch" if prev.end_actual else "schedule",
                        "next_start": iso(nxt.start),
                        "next_start_source": "punch" if nxt.start_actual else "schedule",
                        "rest_hours": h(rest),
                        "min_rest_hours": min_rest,
                        "short_by_hours": h(min_rest - rest),
                    },
                    [p for p in (prev.end_punch, nxt.start_punch) if p is not None],
                    kind="breach" if actual else "risk",
                )
            )
    return found


# ---------------------------------------------------------------- P7 late / early


def check_p7_late_early(ctx: RuleContext) -> list[TimecardException]:
    grace = ctx.policy.number("P7", "grace_minutes")
    auto = ctx.policy.policies["P7"].auto_resolve
    found = []
    for s in ctx.shifts:
        if s.scheduled_start is None or s.scheduled_end is None:
            continue  # unscheduled work has no start to be late for (P8)
        if ctx.active_leave_on(s.employee_id, s.date) is not None:
            continue  # leave day: the times are judged by P9 (full day) or P13 (half day)
        if s.clock_in is not None:
            late = (s.clock_in.timestamp - s.scheduled_start).total_seconds() / 60
            details = {
                "type": "late_arrival",
                "scheduled_start": iso(s.scheduled_start),
                "clock_in": iso(s.clock_in.timestamp),
                "late_minutes": h(late),
                "grace_minutes": grace,
            }
            if late > grace:
                found.append(
                    _make(
                        ctx,
                        "P7",
                        s.employee_id,
                        s.date,
                        f"Clock-in {hhmm(s.clock_in.timestamp)} for a "
                        f"{hhmm(s.scheduled_start)} start: {fmt(late)} min late "
                        f"(grace {fmt(grace)} min)",
                        details,
                        [s.clock_in],
                        suffix="late",
                    )
                )
            elif late > 0 and auto:
                found.append(
                    _make(
                        ctx,
                        "P7",
                        s.employee_id,
                        s.date,
                        f"Clock-in {fmt(late)} min after the start, within the "
                        f"{fmt(grace)} min grace: not late",
                        details,
                        [s.clock_in],
                        suffix="late",
                        status="auto_resolved",
                    )
                )
        if s.clock_out is not None:
            early = (s.scheduled_end - s.clock_out.timestamp).total_seconds() / 60
            if early > grace:
                found.append(
                    _make(
                        ctx,
                        "P7",
                        s.employee_id,
                        s.date,
                        f"Clock-out {hhmm(s.clock_out.timestamp)} for a "
                        f"{hhmm(s.scheduled_end)} end: {fmt(early)} min early "
                        f"(grace {fmt(grace)} min)",
                        {
                            "type": "early_leave",
                            "scheduled_end": iso(s.scheduled_end),
                            "clock_out": iso(s.clock_out.timestamp),
                            "early_minutes": h(early),
                            "grace_minutes": grace,
                        },
                        [s.clock_out],
                        suffix="early",
                    )
                )
    return found
