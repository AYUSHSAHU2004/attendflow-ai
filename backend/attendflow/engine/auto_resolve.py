"""Phase 12: the last engine step. Decides, by code only, which candidates may close
without a person.

Only P2 (duplicate taps) and P7 (late arrival within grace) are candidates; the checks
mark them with `details["auto_resolve"]["basis"]`, a sentence built from the engine's own
numbers. This step adds `eligible` and `held_because` and sets the status:

- `auto_resolved` only when policy.json allows it for that policy and nothing is unclear;
- otherwise `open`, so a person decides (the fix options are already on the exception).

Unclear (held for a person):
- P2: the taps span more than the duplicate window (taps chain), they come from more than
  one device or location, or a tap is also under punch review (P17).
- P7: the shift has more than one clock-in, or the clock-in is under punch review (P17).

The global kill switch (AUTO_RESOLVE_ENABLED) is applied later by detection, so the CLI
and the API agree on what the engine itself allows.
"""

from __future__ import annotations

from typing import Any

from attendflow.data.schemas import Punch
from attendflow.engine.models import TimecardException
from attendflow.policy.models import AUTO_RESOLVABLE, PolicyConfig


def is_candidate(exc: TimecardException) -> bool:
    return exc.policy_id in AUTO_RESOLVABLE and "auto_resolve" in exc.details


def _punches(exc: TimecardException) -> list[Punch]:
    return [p for p in exc.evidence if isinstance(p, Punch)]


def _fmt(value: float) -> str:
    return f"{round(value, 2):g}"


def held_reasons(exc: TimecardException, policy: PolicyConfig, under_review: set[str]) -> list[str]:
    """Why this candidate must go to a person ([] = it may auto-resolve)."""
    reasons: list[str] = []
    if not policy.policies[exc.policy_id].auto_resolve:
        reasons.append(f"auto_resolve is off for {exc.policy_id} in policy.json")
    punches = _punches(exc)
    if exc.policy_id == "P2":
        span = float(exc.details["gap_minutes"])
        window = policy.number("P2", "duplicate_window_minutes")
        if span > window:
            reasons.append(
                f"the taps span {_fmt(span)} min, more than the {_fmt(window)} min window "
                "(chained taps)"
            )
        if len({p.device_id for p in punches}) > 1:
            reasons.append("the taps came from different devices")
        if len({p.location for p in punches}) > 1:
            reasons.append("the taps came from different locations")
        if any(p.punch_id in under_review for p in punches):
            reasons.append("a tap is also under punch review (P17)")
    elif exc.policy_id == "P7":
        clock_ins = int(exc.details.get("clock_ins_on_shift", 1))
        if clock_ins > 1:
            reasons.append(f"the shift has {clock_ins} clock-ins")
        if any(p.punch_id in under_review for p in punches):
            reasons.append("the clock-in is under punch review (P17)")
    return reasons


def apply_guard(
    exceptions: list[TimecardException], policy: PolicyConfig
) -> list[TimecardException]:
    """Set eligible / held_because / status on every auto-resolve candidate."""
    under_review = {p.punch_id for e in exceptions if e.policy_id == "P17" for p in _punches(e)}
    out = []
    for exc in exceptions:
        if not is_candidate(exc):
            out.append(exc)
            continue
        reasons = held_reasons(exc, policy, under_review)
        info: dict[str, Any] = {
            **exc.details["auto_resolve"],
            "eligible": not reasons,
            "held_because": reasons,
        }
        out.append(
            exc.model_copy(
                update={
                    "details": {**exc.details, "auto_resolve": info},
                    "status": "open" if reasons else "auto_resolved",
                }
            )
        )
    return out
