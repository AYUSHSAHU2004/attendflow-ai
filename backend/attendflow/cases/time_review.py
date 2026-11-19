"""Build a worker-confirmed fix and simulate it against the current dataset."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from attendflow.cases.time_extraction import TimeContext
from attendflow.db.dataset import load_dataset_from_db, load_schedule_day
from attendflow.db.models import ExceptionRow
from attendflow.engine.shifts import schedule_bounds
from attendflow.errors import ConflictError, InvalidFixError
from attendflow.fixes.params import FixParamsError, params_json, parse_params
from attendflow.policy.models import PolicyConfig
from attendflow.tools.context import ToolContext
from attendflow.tools.models import RunChecksIn, RunChecksOut, ToolInputError
from attendflow.tools.run_checks import run_checks

TIME_ACTIONS = {"set_clock_out", "set_clock_in", "correct_clock_out"}


def asked_fix(row: ExceptionRow) -> dict | None:
    if row.policy_id not in {"P1", "P3"}:
        return None
    proposal = (row.investigation_case or {}).get("proposed_fix")
    if not proposal:
        return None
    option = next(
        (item for item in row.fix_options if item["option_id"] == proposal["option_id"]), None
    )
    if not option or option["action"] not in TIME_ACTIONS:
        return None
    params = params_json(parse_params(option["action"], option["params"], proposal["params"]))
    return {"option_id": option["option_id"], "action": option["action"], "params": params}


def clock_out_option(row: ExceptionRow, asked: dict | None) -> dict | None:
    action = {"P1": "set_clock_out", "P3": "correct_clock_out"}.get(row.policy_id)
    if action is None or (asked and asked["action"] != action):
        return None
    # The engine supplies at most one clock-out option per supported case.
    options = [item for item in row.fix_options if item["action"] == action]
    return options[0] if len(options) == 1 else None


def context(
    session: Session,
    row: ExceptionRow,
    policy: PolicyConfig,
    now: datetime,
) -> TimeContext | None:
    # P1 includes the matched shift's clock-in. P3 offers a correction on a single-shift day.
    starts = [item["timestamp"] for item in row.evidence if item.get("type") == "in"]
    clock_in = row.details.get("clock_in") or (max(starts) if starts else None)
    if not clock_in:
        return None
    schedule = load_schedule_day(session, row.employee_id, row.date)
    start, end = schedule_bounds(schedule) if schedule else (None, None)
    return TimeContext(
        row.date,
        datetime.fromisoformat(clock_in),
        start,
        end,
        now,
        policy.number("P15", "max_shift_hours"),
    )


def _impact(result: RunChecksOut, policy: PolicyConfig) -> str:
    notes = []
    if result.day_worked_hours is not None:
        hours = result.day_worked_hours
        notes.append(f"This makes the day {hours:g} h")
        if any(item.policy_id == "P3" for item in result.new_violations):
            notes[-1] += f", over the {policy.number('P3', 'max_hours_per_day'):g} h daily limit"
    if result.week_projected_hours > result.weekly_limit_hours and any(
        item.policy_id == "P5" for item in result.new_violations
    ):
        notes.append(
            f"The week is projected at {result.week_projected_hours:g} h, "
            f"over the {result.weekly_limit_hours:g} h weekly limit"
        )
    if not result.new_violations:
        notes.append("The change adds no new violations")
    elif not notes:
        notes.append("The supervisor will review the additional attendance exceptions")
    return ". ".join(notes) + "."


def recheck(
    session: Session,
    row: ExceptionRow,
    option: dict[str, Any],
    stamp: datetime,
    policy: PolicyConfig,
    now: datetime,
) -> dict:
    action = option["action"]
    original = option["params"]
    try:
        params = params_json(
            parse_params(
                action,
                original,
                {
                    **{k: v for k, v in original.items() if k != "worked_hours_after_fix"},
                    "timestamp": stamp.isoformat(timespec="seconds"),
                },
            )
        )
    except FixParamsError as exc:
        raise InvalidFixError(
            "the time does not form a valid correction", code="invalid_time"
        ) from exc
    args = RunChecksIn.model_validate(
        {
            "employee_id": row.employee_id,
            "date": row.date.isoformat(),
            "proposed_change": {"action": action, "params": params},
        }
    )
    try:
        result = run_checks(ToolContext(load_dataset_from_db(session), policy, {}, now), args)
    except ToolInputError as exc:
        raise InvalidFixError(exc.error.message, code=exc.error.code) from None
    if row.policy_id == "P1" and not any(
        item.policy_id == row.policy_id and item.date == row.date.isoformat()
        for item in result.resolved
    ):
        raise ConflictError(
            "the time does not resolve this missing punch", code="punch_not_resolved"
        )
    return {
        "timestamp": stamp.isoformat(timespec="seconds"),
        "proposed_fix": {"option_id": option["option_id"], "params": params},
        "result": result.model_dump(mode="json"),
        "impact_note": _impact(result, policy),
    }
