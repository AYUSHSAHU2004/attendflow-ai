"""run_checks: "what would the rules say if we made this change?" Never writes anything."""

from __future__ import annotations

from datetime import date, timedelta

from attendflow.engine.engine import build_context, run_engine
from attendflow.engine.models import TimecardException
from attendflow.engine.rules import h, week_hours, week_start
from attendflow.tools.context import ToolContext
from attendflow.tools.models import Finding, RunChecksIn, RunChecksOut, ToolInputError
from attendflow.tools.simulate import simulate


def _in_scope(exc: TimecardException, emp: str, wk: date) -> bool:
    # auto-resolved records (P2 taps, P7 within grace) are not violations
    return (
        exc.employee_id == emp and wk <= exc.date < wk + timedelta(days=7) and exc.status == "open"
    )


def _numbers(exc: TimecardException) -> dict[str, float]:
    return {
        k: v
        for k, v in exc.details.items()
        if isinstance(v, int | float) and not isinstance(v, bool)
    }


def _finding(exc: TimecardException, with_numbers: bool) -> Finding:
    return Finding(
        policy_id=exc.policy_id,
        date=exc.date.isoformat(),
        reason=exc.summary,
        numbers=_numbers(exc) if with_numbers else None,
    )


def run_checks(ctx: ToolContext, args: RunChecksIn) -> RunChecksOut:
    emp = ctx.employee(args.employee_id)
    if emp.role != "worker":
        raise ToolInputError("not_a_worker", f"{emp.employee_id} is not a worker")
    change = args.proposed_change
    after_data = simulate(
        ctx.dataset,
        ctx.policy,
        ctx.as_of,
        args.employee_id,
        args.date,
        ctx.processed.shifts,
        change.action,
        change.params,
    )
    wk = week_start(args.date)
    before = {
        e.exception_id: e
        for e in run_engine(ctx.dataset, ctx.policy, ctx.as_of).exceptions
        if _in_scope(e, args.employee_id, wk)
    }
    after = {
        e.exception_id: e
        for e in run_engine(after_data, ctx.policy, ctx.as_of).exceptions
        if _in_scope(e, args.employee_id, wk)
    }

    new = [_finding(e, True) for i, e in after.items() if i not in before]
    resolved = [_finding(before[i], False) for i in before if i not in after]
    still = [_finding(e, False) for i, e in after.items() if i in before]  # reason has numbers

    rules, _ = build_context(after_data, ctx.policy, ctx.as_of)
    mine = [s for s in rules.shifts if s.employee_id == args.employee_id]
    rows = [r for r in rules.schedule if r.employee_id == args.employee_id]
    week = week_hours(rules, args.employee_id, wk, mine, rows)
    day = [s for s in mine if s.date == args.date]
    day_hours = None
    if day and all(s.worked_hours is not None for s in day):
        day_hours = h(sum(s.worked_hours or 0 for s in day))

    if new:
        verdict = f"{len(new)} new violation(s): " + ", ".join(
            f"{f.policy_id} {f.date}" for f in new
        )
    else:
        verdict = "no new violations"
    if resolved:
        verdict += "; resolves " + ", ".join(f"{f.policy_id} {f.date}" for f in resolved)
    limit = ctx.policy.number("P5", "weekly_overtime_after_hours")
    return RunChecksOut(
        employee_id=args.employee_id,
        week=f"{wk.isoformat()} to {(wk + timedelta(days=6)).isoformat()}",
        verdict=verdict,
        new_violations=new,
        resolved=resolved,
        still_open=still,
        day_worked_hours=day_hours,
        week_projected_hours=h(week.projected),
        weekly_limit_hours=limit,
    )
