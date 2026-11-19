"""Punch processing: drop duplicates (P2), then group punches into shifts (P15).

Steps for each worker:
1. Ignore punches after the as-of time (they have not happened yet).
2. Remove duplicate taps: same type within the P2 window. The earliest tap is kept.
3. Attach each punch to the scheduled shift whose window contains it. The window runs from
   a few hours before the scheduled start to a few hours after the scheduled end, so a
   night shift's punches after midnight still join the shift that started the day before.
4. Punches that fit no scheduled shift are grouped in order, from clock-in to clock-out.
Every shift is dated by the day it started (P15).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from attendflow.data.loader import Dataset
from attendflow.data.schemas import Punch, ScheduleRow
from attendflow.engine.models import BreakPeriod, Shift, ShiftStatus
from attendflow.policy.models import PolicyConfig


@dataclass(frozen=True)
class DuplicateRun:
    """One kept punch and the later taps (same type, inside the P2 window) voided for it."""

    kept: Punch
    voided: tuple[Punch, ...]


def schedule_bounds(row: ScheduleRow) -> tuple[datetime, datetime]:
    """Scheduled start and end as local datetimes. A night shift ends on the next day."""
    start = datetime.combine(row.date, row.shift_start)
    end = datetime.combine(row.date, row.shift_end)
    if row.crosses_midnight:
        end += timedelta(days=1)
    return start, end


def scheduled_hours(row: ScheduleRow, policy: PolicyConfig) -> float:
    """Planned paid hours of a scheduled shift: its length minus the planned unpaid lunch
    on long shifts (P5 params). 09:00-18:00 -> 8 h, 09:00-15:00 -> 6 h."""
    start, end = schedule_bounds(row)
    hours = (end - start).total_seconds() / 3600
    if hours > policy.number("P5", "planned_break_after_hours"):
        hours -= policy.number("P5", "planned_break_minutes") / 60
    return hours


def _sort_key(p: Punch) -> tuple[datetime, str]:
    return (p.timestamp, p.punch_id)


def remove_duplicates(
    punches: list[Punch], window_minutes: float
) -> tuple[list[Punch], list[DuplicateRun]]:
    """Split one worker's punches into kept punches and duplicate runs (P2).

    A tap is a duplicate when the previous punch of the same type came at most
    `window_minutes` earlier. Taps chain: 08:57, 09:00, 09:03 all collapse into 08:57.
    """
    window = timedelta(minutes=window_minutes)
    kept: list[Punch] = []
    runs: dict[str, list[Punch]] = {}  # kept punch_id -> voided taps
    last_seen: dict[str, tuple[Punch, Punch]] = {}  # type -> (last tap, kept punch of run)
    for p in sorted(punches, key=_sort_key):
        prev = last_seen.get(p.type)
        if prev is not None and p.timestamp - prev[0].timestamp <= window:
            runs.setdefault(prev[1].punch_id, []).append(p)
            last_seen[p.type] = (p, prev[1])
        else:
            kept.append(p)
            last_seen[p.type] = (p, p)
    by_id = {p.punch_id: p for p in kept}
    return kept, [DuplicateRun(by_id[k], tuple(v)) for k, v in runs.items()]


def _distance(p: Punch, start: datetime, end: datetime) -> timedelta:
    """How far a punch is from where it is expected in a scheduled shift."""
    ts = p.timestamp
    if p.type == "in":
        return abs(ts - start)
    if p.type == "out":
        return abs(ts - end)
    if start <= ts <= end:
        return timedelta(0)
    return min(abs(ts - start), abs(ts - end))


def _build_shift(
    employee_id: str,
    punches: list[Punch],
    row: ScheduleRow | None,
    policy: PolicyConfig,
    as_of: datetime,
) -> Shift:
    punches = sorted(punches, key=_sort_key)
    notes: list[str] = []
    ins = [p for p in punches if p.type == "in"]
    outs = [p for p in punches if p.type == "out"]
    clock_in = ins[0] if ins else None
    clock_out = outs[-1] if outs else None
    if len(ins) > 1:
        notes.append(f"{len(ins)} clock-ins after removing duplicates; using the first")
    if len(outs) > 1:
        notes.append(f"{len(outs)} clock-outs after removing duplicates; using the last")
    if clock_in and clock_out and clock_out.timestamp < clock_in.timestamp:
        notes.append("clock-out is before clock-in; treated as a missing clock-out")
        clock_out = None

    breaks: list[BreakPeriod] = []
    open_break: Punch | None = None
    for p in punches:
        if p.type == "break_start":
            if open_break is not None:
                notes.append(f"break start {open_break.punch_id} has no break end; ignored")
            open_break = p
        elif p.type == "break_end":
            if open_break is None:
                notes.append(f"break end {p.punch_id} has no break start; ignored")
            else:
                breaks.append(BreakPeriod(start=open_break.timestamp, end=p.timestamp))
                open_break = None
    if open_break is not None:
        notes.append(f"break start {open_break.punch_id} has no break end; ignored")

    sched_start, sched_end = schedule_bounds(row) if row else (None, None)

    status: ShiftStatus
    if clock_in and clock_out:
        status = "complete"
    elif clock_in:
        # Still open. It only counts as a missed clock-out once enough time has passed.
        if sched_end is not None:
            deadline = sched_end + timedelta(hours=policy.number("P1", "open_shift_grace_hours"))
        else:
            deadline = clock_in.timestamp + timedelta(hours=policy.number("P15", "max_shift_hours"))
        status = "in_progress" if as_of < deadline else "missing_out"
    else:
        status = "missing_in"

    first = clock_in or punches[0]
    shift_date = row.date if row else first.timestamp.date()
    return Shift(
        employee_id=employee_id,
        date=shift_date,
        schedule=row,
        scheduled_start=sched_start,
        scheduled_end=sched_end,
        punches=punches,
        clock_in=clock_in,
        clock_out=clock_out,
        breaks=breaks,
        status=status,
        notes=notes,
    )


def group_shifts(
    employee_id: str,
    punches: list[Punch],
    schedule: list[ScheduleRow],
    policy: PolicyConfig,
    as_of: datetime,
) -> list[Shift]:
    """Group one worker's (already de-duplicated, past) punches into shifts."""
    before = timedelta(hours=policy.number("P15", "match_before_start_hours"))
    after = timedelta(hours=policy.number("P15", "match_after_end_hours"))
    max_len = timedelta(hours=policy.number("P15", "max_shift_hours"))
    bounds = {row.date: (row, *schedule_bounds(row)) for row in schedule}

    assigned: dict[date, list[Punch]] = {}
    loose: list[Punch] = []
    for p in sorted(punches, key=_sort_key):
        candidates = [
            (_distance(p, start, end), start, day)
            for day, (_, start, end) in bounds.items()
            if start - before <= p.timestamp <= end + after
        ]
        if candidates:
            assigned.setdefault(min(candidates)[2], []).append(p)
        else:
            loose.append(p)

    shifts = [
        _build_shift(employee_id, ps, bounds[day][0], policy, as_of) for day, ps in assigned.items()
    ]

    # Unscheduled punches: a clock-in starts a shift, a clock-out ends it.
    group: list[Punch] = []
    groups: list[list[Punch]] = []
    for p in loose:
        if group and (p.type == "in" or p.timestamp - group[0].timestamp > max_len):
            groups.append(group)
            group = []
        group.append(p)
        if p.type == "out":
            groups.append(group)
            group = []
    if group:
        groups.append(group)
    shifts += [_build_shift(employee_id, g, None, policy, as_of) for g in groups]

    return sorted(shifts, key=lambda s: (s.date, s.punches[0].timestamp))


@dataclass(frozen=True)
class ProcessedPunches:
    shifts: list[Shift]
    duplicate_runs: list[DuplicateRun]
    ignored_future_punches: int


def process_punches(dataset: Dataset, policy: PolicyConfig, as_of: datetime) -> ProcessedPunches:
    """Turn raw punches into shifts for every worker (not supervisors or payroll admins)."""
    window = policy.number("P2", "duplicate_window_minutes")
    workers = [e.employee_id for e in dataset.employees if e.role == "worker"]
    shifts: list[Shift] = []
    runs: list[DuplicateRun] = []
    ignored = 0
    for emp in workers:
        mine = [p for p in dataset.punches if p.employee_id == emp]
        past = [p for p in mine if p.timestamp <= as_of]
        ignored += len(mine) - len(past)
        kept, emp_runs = remove_duplicates(past, window)
        runs += emp_runs
        rows = [r for r in dataset.schedule if r.employee_id == emp]
        shifts += group_shifts(emp, kept, rows, policy, as_of)
    return ProcessedPunches(shifts, runs, ignored)
