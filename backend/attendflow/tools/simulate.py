"""Apply a proposed change to an in-memory copy of the data (for run_checks).

This mirrors fixes/apply.py, including its guards (no future punches, only upcoming shifts
can change, leave needs balance), but it only ever builds a new Dataset: nothing here can
reach the database. A parity test applies the same changes with the real writer and
checks that detection then finds exactly what run_checks predicted.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta

from attendflow.data.loader import Dataset
from attendflow.data.schemas import LeaveBalance, LeaveRecord, Punch, ScheduleRow
from attendflow.engine.models import Shift
from attendflow.engine.shifts import scheduled_hours, shift_end_for_hours
from attendflow.policy.models import PolicyConfig
from attendflow.tools.models import ToolInputError

CORRECTION_DEVICE = "CORRECTION"


class Simulation:
    def __init__(
        self,
        dataset: Dataset,
        policy: PolicyConfig,
        as_of: datetime,
        employee_id: str,
        shift_date: date,
        shifts: list[Shift],
    ):
        self.policy = policy
        self.as_of = as_of
        self.emp = employee_id
        self.on = shift_date
        # This worker's shifts on that date, as the engine built them (P15 attribution).
        self.shifts = [s for s in shifts if s.employee_id == employee_id and s.date == shift_date]
        self.punches = list(dataset.punches)
        self.schedule = list(dataset.schedule)
        self.leave = list(dataset.leave_records)
        self.balances = list(dataset.leave_balances)
        self._base = dataset
        self._next_no = max((int(p.punch_id[1:]) for p in dataset.punches), default=0) + 1

    def result(self) -> Dataset:
        return replace(
            self._base,
            punches=self.punches,
            schedule=self.schedule,
            leave_records=self.leave,
            leave_balances=self.balances,
        )

    # ---- punches

    def _shift_punch_times(self, type_: str) -> list[datetime]:
        return sorted(p.timestamp for s in self.shifts for p in s.punches if p.type == type_)

    def check_time(self, ts: datetime) -> None:
        if ts > self.as_of:
            raise ToolInputError(
                "punch_in_future", f"{ts:%a %d %b %H:%M} is after now ({self.as_of:%a %d %b %H:%M})"
            )
        first = datetime.combine(self.on, datetime.min.time())
        if not first <= ts < first + timedelta(days=2):
            raise ToolInputError(
                "punch_outside_shift", f"{ts:%a %d %b %H:%M} is not on the shift day ({self.on})"
            )

    def find_punch(self, punch_id: str) -> Punch:
        p = next((x for x in self.punches if x.punch_id == punch_id), None)
        if p is None or p.employee_id != self.emp:
            raise ToolInputError(
                "unknown_punch",
                f"punch {punch_id} does not belong to {self.emp} (or is voided)",
                hint="get_punches lists the punch IDs",
            )
        return p

    def add_punch(self, ts: datetime, type_: str, location: str | None = None) -> None:
        self.check_time(ts)
        if location is None:
            known = [p.location for s in self.shifts for p in s.punches]
            location = known[0] if known else "Supervisor correction"
        self.punches.append(
            Punch(
                punch_id=f"P{self._next_no:04d}",
                employee_id=self.emp,
                timestamp=ts,
                type=type_,
                source="correction",
                device_id=CORRECTION_DEVICE,
                location=location,
            )
        )
        self._next_no += 1

    def void(self, punch_id: str) -> Punch:
        p = self.find_punch(punch_id)
        self.punches.remove(p)
        return p

    def _within_max_shift(self, start: datetime, end: datetime, what: str) -> None:
        max_hours = self.policy.number("P15", "max_shift_hours")
        if not start < end <= start + timedelta(hours=max_hours):
            raise ToolInputError(
                "punch_outside_shift",
                f"{what} must be after {start:%H:%M} and within {max_hours:g} h of it",
            )

    # ---- schedule and leave

    def upcoming_row(self, on: date) -> ScheduleRow:
        row = next((r for r in self.schedule if r.employee_id == self.emp and r.date == on), None)
        if row is None:
            raise ToolInputError("not_scheduled", f"{self.emp} has no scheduled shift on {on}")
        if datetime.combine(row.date, row.shift_start) < self.as_of:
            raise ToolInputError(
                "shift_not_upcoming",
                f"the shift on {on:%a %d %b} has already started; only upcoming shifts can change",
            )
        return row

    def leave_row(self, on: date, leave_type: str) -> LeaveRecord:
        row = next((r for r in self.leave if r.employee_id == self.emp and r.date == on), None)
        if row is None or row.leave_type != leave_type:
            raise ToolInputError("no_leave", f"{self.emp} has no {leave_type} leave on {on}")
        return row

    def change_used(self, leave_type: str, delta: float) -> None:
        bal = next(
            (b for b in self.balances if b.employee_id == self.emp and b.leave_type == leave_type),
            None,
        )
        if bal is None:
            raise ToolInputError("no_balance", f"{self.emp} has no {leave_type} leave balance")
        used = round(bal.used + delta, 2)
        if used < 0:
            raise ToolInputError("invalid_change", f"{leave_type} leave used would go below 0")
        if used > bal.total_per_year:
            left = bal.total_per_year - bal.used
            raise ToolInputError("not_enough_balance", f"only {left:g} {leave_type} day(s) left")
        self.balances[self.balances.index(bal)] = LeaveBalance(
            employee_id=bal.employee_id,
            leave_type=bal.leave_type,
            total_per_year=bal.total_per_year,
            used=used,
        )

    # ---- one method per action (same names as fixes/apply.py)

    def set_clock_out(self, p) -> None:
        self.check_time(p.timestamp)
        ins = self._shift_punch_times("in")
        if ins:
            self._within_max_shift(ins[-1], p.timestamp, "clock-out")
        self.add_punch(p.timestamp, "out")

    def set_clock_in(self, p) -> None:
        self.check_time(p.timestamp)
        outs = self._shift_punch_times("out")
        if outs:
            self._within_max_shift(p.timestamp, outs[0], "the clock-out")
        self.add_punch(p.timestamp, "in")

    def correct_clock_out(self, p) -> None:
        old = self.find_punch(p.punch_id)
        if old.type != "out":
            raise ToolInputError(
                "wrong_punch_type", f"punch {p.punch_id} is a '{old.type}' punch, not a clock-out"
            )
        self.check_time(p.timestamp)
        ins = self._shift_punch_times("in")
        if ins:
            self._within_max_shift(ins[-1], p.timestamp, "clock-out")
        self.void(p.punch_id)
        self.add_punch(p.timestamp, "out", old.location)

    def add_break(self, p) -> None:
        ins, outs = self._shift_punch_times("in"), self._shift_punch_times("out")
        if (ins and p.break_start <= ins[0]) or (outs and p.break_end >= outs[-1]):
            raise ToolInputError(
                "break_outside_shift", "the break must be between the clock-in and the clock-out"
            )
        others = self._shift_punch_times("break_start") + self._shift_punch_times("break_end")
        if any(p.break_start <= t <= p.break_end for t in others):
            raise ToolInputError("break_overlaps", "the break overlaps a break already punched")
        self.add_punch(p.break_start, "break_start")
        self.add_punch(p.break_end, "break_end")

    def add_punches(self, p) -> None:
        max_hours = self.policy.number("P15", "max_shift_hours")
        if p.clock_out - p.clock_in > timedelta(hours=max_hours):
            raise ToolInputError("too_long", f"a shift cannot be longer than {max_hours:g} h")
        self.add_punch(p.clock_in, "in")
        self.add_punch(p.clock_out, "out")

    def void_punches(self, p) -> None:
        for pid in p.punch_ids:
            self.void(pid)

    def edit_punches(self, p) -> None:
        for c in p.changes:
            old = self.void(c.punch_id)
            self.add_punch(c.timestamp, old.type, old.location)

    def move_shift(self, p) -> None:
        row = self.upcoming_row(p.date)
        if (row.shift_start, row.shift_end) != (p.current_start, p.current_end):
            raise ToolInputError(
                "stale_change",
                f"the {p.date} shift is {row.shift_start:%H:%M}-{row.shift_end:%H:%M}, not "
                f"{p.current_start:%H:%M}-{p.current_end:%H:%M}",
                hint="get_schedule shows the current times",
            )
        if datetime.combine(p.date, p.new_start) <= self.as_of:
            raise ToolInputError("shift_not_upcoming", "the new start is not in the future")
        self.schedule[self.schedule.index(row)] = ScheduleRow(
            employee_id=row.employee_id, date=row.date, shift_start=p.new_start, shift_end=p.new_end
        )

    def reduce_scheduled_hours(self, p) -> None:
        for cut in p.cuts:
            row = self.upcoming_row(cut.date)
            planned = scheduled_hours(row, self.policy)
            if abs(planned - cut.scheduled_hours) > 0.01:
                raise ToolInputError(
                    "stale_change",
                    f"the {cut.date} shift is {planned:g} h, not {cut.scheduled_hours:g} h",
                    hint="get_schedule shows planned_hours",
                )
            i = self.schedule.index(row)
            if cut.new_hours == 0:
                del self.schedule[i]
                continue
            end = shift_end_for_hours(row, cut.new_hours, self.policy)
            self.schedule[i] = ScheduleRow(
                employee_id=row.employee_id,
                date=row.date,
                shift_start=row.shift_start,
                shift_end=end.time(),
            )

    def record_leave(self, p) -> None:
        if any(r.employee_id == self.emp and r.date == p.date for r in self.leave):
            raise ToolInputError("leave_exists", f"{self.emp} already has leave on {p.date}")
        self.change_used(p.leave_type, p.days)
        self.leave.append(
            LeaveRecord(
                employee_id=self.emp,
                date=p.date,
                leave_type=p.leave_type,
                duration="full" if p.days >= 1 else "half",
                status="approved",
                certificate_uploaded=False,
            )
        )

    def cancel_leave(self, p) -> None:
        row = self.leave_row(p.date, p.leave_type)
        if row.status == "approved":
            self.change_used(row.leave_type, -(1.0 if row.duration == "full" else 0.5))
        self.leave.remove(row)


def simulate(
    dataset: Dataset,
    policy: PolicyConfig,
    as_of: datetime,
    employee_id: str,
    shift_date: date,
    shifts: list[Shift],
    action: str,
    params,
) -> Dataset:
    sim = Simulation(dataset, policy, as_of, employee_id, shift_date, shifts)
    getattr(sim, action)(params)
    return sim.result()
