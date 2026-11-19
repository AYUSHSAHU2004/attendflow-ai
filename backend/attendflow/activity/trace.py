"""A one-line result for each agent tool call, built by code from the stored output.

Used by the compact investigation trace on the case cards. It never returns the raw
output, the arguments' free text, prompts or keys: only counts, times and policy IDs.
"""

from __future__ import annotations

from typing import Any


def _hours(value: Any) -> str:
    return f"{round(float(value), 2):g} h"


def result_summary(tool_name: str, ok: bool | None, output: dict[str, Any] | None) -> str:
    out = output or {}
    if ok is False or out.get("ok") is False:
        error = out.get("error") if isinstance(out.get("error"), dict) else {}
        return f"Refused: {error.get('code') or 'error'}."
    if ok is None and not out:
        return "No result recorded."
    if tool_name == "get_schedule":
        if not out.get("scheduled"):
            return "Not scheduled that day." + (" Holiday." if out.get("holiday") else "")
        holiday = " (holiday)" if out.get("holiday") else ""
        return f"Scheduled {out.get('start')} to {out.get('end')}{holiday}."
    if tool_name == "get_punches":
        shifts = out.get("shifts") or []
        punches = sum(len(s.get("punches") or []) for s in shifts)
        return f"{len(shifts)} shift(s), {punches} punch(es)."
    if tool_name == "get_leave":
        if not out.get("on_leave"):
            return "No leave that day."
        return f"On {out.get('leave_type')} leave ({out.get('duration')}, {out.get('status')})."
    if tool_name == "get_leave_balance":
        return f"{out.get('leave_type')} balance {out.get('balance')} day(s)."
    if tool_name == "get_policy":
        return f"Read policy {out.get('policy_id')}."
    if tool_name == "run_checks":
        new = [v.get("policy_id") for v in out.get("new_violations") or [] if isinstance(v, dict)]
        resolved = [v.get("policy_id") for v in out.get("resolved") or [] if isinstance(v, dict)]
        text = f"New violations: {', '.join(new)}." if new else "No new violations."
        if resolved:
            text += f" Resolves {', '.join(resolved)}."
        week = out.get("week_projected_hours")
        if isinstance(week, (int, float)):
            text += f" Week {_hours(week)}."
        return text
    return "Done."
