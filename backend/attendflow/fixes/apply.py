"""Apply an approved fix to the source data.

This is the ONLY module (besides the demo seed) that writes to timecards, schedule,
leave_records and leave_balances; a test enforces it. It never commits: the caller wraps
the fix, the exception update and the audit row in one transaction, so either all of
them are saved or none.

Rules:
- Punches are never deleted or overwritten. A correction voids the old punch and adds a
  new one (source='correction'); both rows point at the exception.
- Decision-only actions (approve overtime, holiday pay, ...) change no data; the decision
  is stored on the exception (applied_fix) and in the audit log.
- Every change is returned as a small dict, so the audit row shows exactly what changed.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from attendflow.data.schemas import ScheduleRow
from attendflow.db.models import (
    ExceptionRow,
    LeaveBalanceRow,
    LeaveRecordRow,
    PunchRow,
    ScheduleEntryRow,
)
from attendflow.engine.shifts import scheduled_hours, shift_end_for_hours
from attendflow.errors import ConflictError, InvalidFixError
from attendflow.fixes.params import (
    AddBreakParams,
    AddPunchesParams,
    ConvertFullDayParams,
    CorrectPunchParams,
    DateParams,
    EditPunchesParams,
    LeaveDayParams,
    MoveLeaveTypeParams,
    MoveShiftParams,
    Params,
    PunchIdsParams,
    ReduceScheduleParams,
    RejectLeaveDaysParams,
    RejectUnscheduledParams,
    SetClockParams,
    SplitPaidUnpaidParams,
)
from attendflow.policy.models import PolicyConfig

Change = dict[str, Any]
CORRECTION_DEVICE = "CORRECTION"
_PUNCH_ID_LOCK = 42_001  # advisory lock key: one writer at a time picks new punch IDs


class FixContext:
    def __init__(self, session: Session, exc: ExceptionRow, policy: PolicyConfig, as_of: datetime):
        self.session = session
        self.exc = exc
        self.policy = policy
        self.as_of = as_of

    @property
    def employee_id(self) -> str:
        return self.exc.employee_id

    # ---- punches

    def punch(self, punch_id: str) -> PunchRow:
        row = self.session.get(PunchRow, punch_id, with_for_update=True)
        if row is None or row.employee_id != self.employee_id:
            raise InvalidFixError(
                f"punch {punch_id} does not belong to {self.employee_id}", code="unknown_punch"
            )
        if row.voided:
            raise ConflictError(
                f"punch {punch_id} is already voided; run detection again", code="stale_fix"
            )
        return row

    def evidence_punches(self) -> list[dict[str, Any]]:
        return [r for r in self.exc.evidence if "punch_id" in r]

    def check_punch_time(self, ts: datetime) -> None:
        """A corrected punch must be on the exception's day (or the next morning for a
        night shift) and cannot be in the future."""
        if ts > self.as_of:
            raise InvalidFixError(
                f"{ts:%a %d %b %H:%M} is after now ({self.as_of:%a %d %b %H:%M})",
                code="punch_in_future",
            )
        first = datetime.combine(self.exc.date, datetime.min.time())
        if not first <= ts < first + timedelta(days=2):
            raise InvalidFixError(
                f"{ts:%a %d %b %H:%M} is not on the shift day ({self.exc.date:%a %d %b})",
                code="punch_outside_shift",
            )

    def new_punch(self, ts: datetime, type_: str, location: str | None = None) -> Change:
        self.check_punch_time(ts)
        self.session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _PUNCH_ID_LOCK})
        ids = self.session.scalars(select(PunchRow.punch_id)).all()
        next_no = max((int(i.removeprefix("P")) for i in ids), default=0) + 1
        if location is None:
            known = self.evidence_punches()
            location = known[0]["location"] if known else "Supervisor correction"
        row = PunchRow(
            punch_id=f"P{next_no:04d}",
            employee_id=self.employee_id,
            timestamp=ts,
            type=type_,
            source="correction",
            device_id=CORRECTION_DEVICE,
            location=location,
            voided=False,
            created_by_exception=self.exc.id,
        )
        self.session.add(row)
        self.session.flush()
        return {
            "table": "timecards",
            "op": "insert",
            "punch_id": row.punch_id,
            "type": type_,
            "timestamp": ts.isoformat(timespec="seconds"),
        }

    def void(self, punch_id: str) -> Change:
        row = self.punch(punch_id)
        row.voided = True
        row.voided_by_exception = self.exc.id
        return {
            "table": "timecards",
            "op": "void",
            "punch_id": punch_id,
            "type": row.type,
            "timestamp": row.timestamp.isoformat(timespec="seconds"),
        }

    # ---- schedule

    def schedule_row(self, on: date) -> ScheduleEntryRow:
        row = self.session.scalars(
            select(ScheduleEntryRow)
            .where(ScheduleEntryRow.employee_id == self.employee_id, ScheduleEntryRow.date == on)
            .with_for_update()
        ).one_or_none()
        if row is None:
            raise ConflictError(
                f"{self.employee_id} has no scheduled shift on {on}; run detection again",
                code="stale_fix",
            )
        start = datetime.combine(row.date, row.shift_start)
        if start < self.as_of:
            raise InvalidFixError(
                f"the shift on {on:%a %d %b} has already started; only upcoming shifts can change",
                code="shift_not_upcoming",
            )
        return row

    # ---- leave

    def leave_row(self, on: date, leave_type: str) -> LeaveRecordRow:
        row = self.session.scalars(
            select(LeaveRecordRow)
            .where(LeaveRecordRow.employee_id == self.employee_id, LeaveRecordRow.date == on)
            .with_for_update()
        ).one_or_none()
        if row is None or row.leave_type != leave_type:
            raise ConflictError(
                f"{self.employee_id} has no {leave_type} leave on {on}; run detection again",
                code="stale_fix",
            )
        return row

    def balance(self, leave_type: str) -> LeaveBalanceRow:
        row = self.session.get(
            LeaveBalanceRow, (self.employee_id, leave_type), with_for_update=True
        )
        if row is None:
            raise ConflictError(
                f"{self.employee_id} has no {leave_type} leave balance", code="no_balance"
            )
        return row

    def change_used(self, leave_type: str, delta: float) -> Change:
        bal = self.balance(leave_type)
        before = bal.used
        bal.used = round(bal.used + delta, 2)
        if bal.used < 0:
            raise ConflictError(f"{leave_type} leave used would go below 0", code="stale_fix")
        return {
            "table": "leave_balances",
            "op": "update",
            "leave_type": leave_type,
            "used": {"before": before, "after": bal.used},
        }


def _leave_days(row: LeaveRecordRow) -> float:
    return 1.0 if row.duration == "full" else 0.5


def _leave_change(row: LeaveRecordRow, op: str, **fields: Any) -> Change:
    return {
        "table": "leave_records",
        "op": op,
        "date": row.date.isoformat(),
        "leave_type": row.leave_type,
        **fields,
    }


# ------------------------------------------------------------------ appliers


def _set_clock_out(ctx: FixContext, p: SetClockParams) -> list[Change]:
    ctx.check_punch_time(p.timestamp)
    ins = [r for r in ctx.evidence_punches() if r["type"] == "in"]
    if ins:
        clock_in = datetime.fromisoformat(ins[-1]["timestamp"])
        max_hours = ctx.policy.number("P15", "max_shift_hours")
        if not clock_in < p.timestamp <= clock_in + timedelta(hours=max_hours):
            raise InvalidFixError(
                f"clock-out must be after the clock-in ({clock_in:%H:%M}) and within "
                f"{max_hours:g} h of it",
                code="punch_outside_shift",
            )
    return [ctx.new_punch(p.timestamp, "out")]


def _set_clock_in(ctx: FixContext, p: SetClockParams) -> list[Change]:
    ctx.check_punch_time(p.timestamp)
    outs = [r for r in ctx.evidence_punches() if r["type"] == "out"]
    if outs:
        clock_out = datetime.fromisoformat(outs[0]["timestamp"])
        max_hours = ctx.policy.number("P15", "max_shift_hours")
        if not clock_out - timedelta(hours=max_hours) <= p.timestamp < clock_out:
            raise InvalidFixError(
                f"clock-in must be before the clock-out ({clock_out:%H:%M}) and within "
                f"{max_hours:g} h of it",
                code="punch_outside_shift",
            )
    return [ctx.new_punch(p.timestamp, "in")]


def _evidence_times(ctx: FixContext, type_: str) -> list[datetime]:
    return sorted(
        datetime.fromisoformat(r["timestamp"]) for r in ctx.evidence_punches() if r["type"] == type_
    )


def _correct_clock_out(ctx: FixContext, p: CorrectPunchParams) -> list[Change]:
    """P3: the clock-out was wrong. Void it and add the confirmed one (never overwrite)."""
    old = ctx.punch(p.punch_id)
    if old.type != "out":
        raise InvalidFixError(
            f"punch {p.punch_id} is a '{old.type}' punch, not a clock-out", code="wrong_punch_type"
        )
    ctx.check_punch_time(p.timestamp)
    ins = _evidence_times(ctx, "in")
    if ins:
        max_hours = ctx.policy.number("P15", "max_shift_hours")
        if not ins[-1] < p.timestamp <= ins[-1] + timedelta(hours=max_hours):
            raise InvalidFixError(
                f"clock-out must be after the clock-in ({ins[-1]:%H:%M}) and within "
                f"{max_hours:g} h of it",
                code="punch_outside_shift",
            )
    return [ctx.void(p.punch_id), ctx.new_punch(p.timestamp, "out", old.location)]


def _add_break(ctx: FixContext, p: AddBreakParams) -> list[Change]:
    """P4: add the break the worker confirms, inside the shift and clear of other breaks."""
    ins, outs = _evidence_times(ctx, "in"), _evidence_times(ctx, "out")
    if (ins and p.break_start <= ins[0]) or (outs and p.break_end >= outs[-1]):
        raise InvalidFixError(
            "the break must be between the clock-in and the clock-out", code="break_outside_shift"
        )
    others = _evidence_times(ctx, "break_start") + _evidence_times(ctx, "break_end")
    if any(p.break_start <= t <= p.break_end for t in others):
        raise InvalidFixError(
            "the break overlaps a break that is already punched", code="break_overlaps"
        )
    return [ctx.new_punch(p.break_start, "break_start"), ctx.new_punch(p.break_end, "break_end")]


def _move_shift(ctx: FixContext, p: MoveShiftParams) -> list[Change]:
    """P6: move an upcoming shift later so the rest before it is long enough."""
    row = ctx.schedule_row(p.date)
    if (row.shift_start, row.shift_end) != (p.current_start, p.current_end):
        raise ConflictError(
            f"the {p.date} shift is now {row.shift_start:%H:%M}-{row.shift_end:%H:%M}, not "
            f"{p.current_start:%H:%M}-{p.current_end:%H:%M}; run detection again",
            code="stale_fix",
        )
    if datetime.combine(p.date, p.new_start) <= ctx.as_of:
        raise InvalidFixError(
            f"the new start {p.new_start:%H:%M} on {p.date:%a %d %b} is not in the future",
            code="shift_not_upcoming",
        )
    before = f"{row.shift_start:%H:%M}-{row.shift_end:%H:%M}"
    row.shift_start, row.shift_end = p.new_start, p.new_end
    return [
        {
            "table": "schedule",
            "op": "update",
            "date": p.date.isoformat(),
            "shift": {"before": before, "after": f"{p.new_start:%H:%M}-{p.new_end:%H:%M}"},
        }
    ]


def _add_punches(ctx: FixContext, p: AddPunchesParams) -> list[Change]:
    max_hours = ctx.policy.number("P15", "max_shift_hours")
    if p.clock_out - p.clock_in > timedelta(hours=max_hours):
        raise InvalidFixError(f"a shift cannot be longer than {max_hours:g} h", code="too_long")
    return [ctx.new_punch(p.clock_in, "in"), ctx.new_punch(p.clock_out, "out")]


def _void_punches(ctx: FixContext, p: PunchIdsParams) -> list[Change]:
    return [ctx.void(pid) for pid in p.punch_ids]


def _edit_punches(ctx: FixContext, p: EditPunchesParams) -> list[Change]:
    changes: list[Change] = []
    for c in p.changes:
        old = ctx.punch(c.punch_id)
        changes.append(ctx.void(c.punch_id))
        changes.append(ctx.new_punch(c.timestamp, old.type, old.location))
    return changes


def _reject_unscheduled(ctx: FixContext, p: RejectUnscheduledParams) -> list[Change]:
    return [ctx.void(pid) for pid in p.punch_ids]


def _reduce_schedule(ctx: FixContext, p: ReduceScheduleParams) -> list[Change]:
    changes: list[Change] = []
    for cut in p.cuts:
        row = ctx.schedule_row(cut.date)
        planned = scheduled_hours(ScheduleRow.model_validate(row, from_attributes=True), ctx.policy)
        if abs(planned - cut.scheduled_hours) > 0.01:
            raise ConflictError(
                f"the {cut.date} shift is now {planned:g} h, not {cut.scheduled_hours:g} h; "
                "run detection again",
                code="stale_fix",
            )
        before = f"{row.shift_start:%H:%M}-{row.shift_end:%H:%M}"
        if cut.new_hours == 0:
            ctx.session.delete(row)
            changes.append(
                {"table": "schedule", "op": "delete", "date": cut.date.isoformat(), "shift": before}
            )
            continue
        sched = ScheduleRow.model_validate(row, from_attributes=True)
        row.shift_end = shift_end_for_hours(sched, cut.new_hours, ctx.policy).time()
        changes.append(
            {
                "table": "schedule",
                "op": "update",
                "date": cut.date.isoformat(),
                "shift": {
                    "before": before,
                    "after": f"{row.shift_start:%H:%M}-{row.shift_end:%H:%M}",
                },
                "hours": {"before": cut.scheduled_hours, "after": cut.new_hours},
            }
        )
    return changes


def _give_rest_day(ctx: FixContext, p: DateParams) -> list[Change]:
    row = ctx.schedule_row(p.date)
    shift = f"{row.shift_start:%H:%M}-{row.shift_end:%H:%M}"
    ctx.session.delete(row)
    return [{"table": "schedule", "op": "delete", "date": p.date.isoformat(), "shift": shift}]


def _record_leave(ctx: FixContext, p: LeaveDayParams) -> list[Change]:
    existing = ctx.session.scalars(
        select(LeaveRecordRow).where(
            LeaveRecordRow.employee_id == ctx.employee_id, LeaveRecordRow.date == p.date
        )
    ).one_or_none()
    if existing is not None:
        raise ConflictError(
            f"{ctx.employee_id} already has {existing.leave_type} leave on {p.date}",
            code="stale_fix",
        )
    bal = ctx.balance(p.leave_type)
    if bal.total_per_year - bal.used < p.days:
        raise ConflictError(
            f"only {bal.total_per_year - bal.used:g} {p.leave_type} day(s) left",
            code="not_enough_balance",
        )
    row = LeaveRecordRow(
        employee_id=ctx.employee_id,
        date=p.date,
        leave_type=p.leave_type,
        duration="full" if p.days >= 1 else "half",
        status="approved",
        certificate_uploaded=False,
        unpaid=False,
    )
    ctx.session.add(row)
    return [
        _leave_change(row, "insert", duration=row.duration, status="approved"),
        ctx.change_used(p.leave_type, p.days),
    ]


def _cancel_leave(ctx: FixContext, p: LeaveDayParams) -> list[Change]:
    row = ctx.leave_row(p.date, p.leave_type)
    changes = [_leave_change(row, "delete", duration=row.duration, status=row.status)]
    if row.status == "approved":
        changes.append(ctx.change_used(row.leave_type, -_leave_days(row)))
    ctx.session.delete(row)
    return changes


def _convert_to_full_day(ctx: FixContext, p: ConvertFullDayParams) -> list[Change]:
    row = ctx.leave_row(p.date, p.leave_type)
    if row.duration != "half":
        raise ConflictError(f"the leave on {p.date} is already a full day", code="stale_fix")
    row.duration = "full"
    changes = [_leave_change(row, "update", duration={"before": "half", "after": "full"})]
    if row.status == "approved":
        changes.append(ctx.change_used(row.leave_type, 0.5))
    return changes


def _reject_days(ctx: FixContext, leave_type: str, dates: list[date], unpaid: bool) -> list[Change]:
    changes: list[Change] = []
    for on in dates:
        row = ctx.leave_row(on, leave_type)
        before = row.status
        row.status = "rejected"
        row.unpaid = unpaid
        changes.append(
            _leave_change(
                row, "update", status={"before": before, "after": "rejected"}, unpaid=unpaid
            )
        )
        if before == "approved":
            changes.append(ctx.change_used(leave_type, -_leave_days(row)))
    return changes


def _split_paid_unpaid(ctx: FixContext, p: SplitPaidUnpaidParams) -> list[Change]:
    for d in p.paid:  # paid days stay as they are; just check they still exist
        ctx.leave_row(d.date, p.leave_type)
    return _reject_days(ctx, p.leave_type, [d.date for d in p.unpaid], unpaid=True)


def _move_leave_type(ctx: FixContext, p: MoveLeaveTypeParams) -> list[Change]:
    bal = ctx.balance(p.to_type)
    needed = sum(d.days for d in p.days)
    if bal.total_per_year - bal.used < needed:
        raise ConflictError(
            f"only {bal.total_per_year - bal.used:g} {p.to_type} day(s) left, {needed:g} needed",
            code="not_enough_balance",
        )
    changes: list[Change] = []
    for d in p.days:
        row = ctx.leave_row(d.date, p.from_type)
        row.leave_type = p.to_type
        changes.append(
            {
                "table": "leave_records",
                "op": "update",
                "date": d.date.isoformat(),
                "leave_type": {"before": p.from_type, "after": p.to_type},
            }
        )
        if row.status == "approved":
            changes.append(ctx.change_used(p.from_type, -_leave_days(row)))
            changes.append(ctx.change_used(p.to_type, _leave_days(row)))
    return changes


def _reject_leave_days(ctx: FixContext, p: RejectLeaveDaysParams) -> list[Change]:
    return _reject_days(ctx, p.leave_type, p.all_dates(), unpaid=p.as_ == "unpaid")


APPLIERS: dict[str, Callable[[FixContext, Any], list[Change]]] = {
    "set_clock_in": _set_clock_in,
    "set_clock_out": _set_clock_out,
    "add_punches": _add_punches,
    "void_punches": _void_punches,
    "edit_punches": _edit_punches,
    "reject_unscheduled_work": _reject_unscheduled,
    "reduce_scheduled_hours": _reduce_schedule,
    "give_rest_day": _give_rest_day,
    "record_leave": _record_leave,
    "cancel_leave": _cancel_leave,
    "convert_to_full_day_leave": _convert_to_full_day,
    "split_paid_unpaid_leave": _split_paid_unpaid,
    "move_leave_type": _move_leave_type,
    "reject_leave_days": _reject_leave_days,
    "correct_clock_out": _correct_clock_out,
    "add_break": _add_break,
    "move_shift": _move_shift,
}


def apply_fix(
    session: Session,
    exc: ExceptionRow,
    action: str,
    params: Params | dict[str, Any],
    policy: PolicyConfig,
    as_of: datetime,
) -> list[Change]:
    """Write the data changes for one approved fix. Decision-only actions return []."""
    applier = APPLIERS.get(action)
    if applier is None:
        return []
    changes = applier(FixContext(session, exc, policy, as_of), params)
    session.flush()  # surface constraint errors inside the caller's transaction
    return changes


def apply_auto_resolve(
    session: Session, exc: ExceptionRow, policy: PolicyConfig, as_of: datetime
) -> list[Change]:
    """Data changes for an exception the engine auto-resolved (policy.json auto_resolve).

    P2: void the duplicate taps the engine already ignored, so the stored timecard matches
    what the engine counted. P7 (late within grace) changes no data.
    """
    ctx = FixContext(session, exc, policy, as_of)
    if exc.policy_id == "P2":
        changes = [ctx.void(pid) for pid in exc.details.get("voided_punch_ids", [])]
        session.flush()
        return changes
    return []
