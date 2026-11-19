"""P17: punches that need a person to review them. Plain code, limits from policy.json.

Wording rule: these are data checks, never accusations. Every summary starts with
"Possible punch conflict, needs review" and no text says "fraud" (a test enforces this).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from attendflow.data.schemas import Punch
from attendflow.engine.models import FixOption, TimecardException
from attendflow.engine.rules import RuleContext, fmt, h, hhmm, make_exception

LEAD = "Possible punch conflict, needs review"


def _fixes(own: list[Punch]) -> list[FixOption]:
    ids = [p.punch_id for p in own]
    return [
        FixOption(
            option_id="confirm_punches_valid",
            action="confirm_punches_valid",
            label="Confirm the punches are valid (nothing changes)",
            params={"punch_ids": ids},
        ),
        FixOption(
            option_id="void_punches",
            action="void_punches",
            label=f"After asking the worker, void punch(es) {', '.join(ids)}",
            params={"punch_ids": ids},
        ),
    ]


def check_p17_punch_review(ctx: RuleContext) -> list[TimecardException]:
    shift_date = {p.punch_id: s.date for s in ctx.shifts for p in s.punches}

    def day_of(p: Punch) -> date:
        return shift_date.get(p.punch_id, p.timestamp.date())

    return [*_same_second(ctx, day_of), *_two_sites(ctx, day_of), *_app_location(ctx, day_of)]


def _same_second(ctx: RuleContext, day_of) -> list[TimecardException]:
    """Several workers on the same terminal at exactly the same second."""
    min_workers = ctx.policy.number("P17", "same_second_min_employees")
    groups: dict[tuple[str, datetime], list[Punch]] = defaultdict(list)
    for p in ctx.punches:
        if p.source == "device":  # app punches come from separate phones
            groups[(p.device_id, p.timestamp)].append(p)
    found = []
    for (device, ts), punches in sorted(groups.items()):
        workers = sorted({p.employee_id for p in punches})
        if len(workers) < min_workers:
            continue
        for emp in workers:
            own = [p for p in punches if p.employee_id == emp]
            others = [w for w in workers if w != emp]
            found.append(
                make_exception(
                    ctx,
                    "P17",
                    emp,
                    day_of(own[0]),
                    f"{LEAD}: punched on {device} at the same second ({ts:%H:%M:%S}) as "
                    f"{', '.join(others)}",
                    {
                        "check": "same_second",
                        "device_id": device,
                        "timestamp": ts.isoformat(timespec="seconds"),
                        "employees": workers,
                        "punch_ids": [p.punch_id for p in punches],
                        "same_second_min_employees": min_workers,
                    },
                    punches,
                    suffix=f"same-second-{own[0].punch_id}",
                    fix_options=_fixes(own),
                )
            )
    return found


def _two_sites(ctx: RuleContext, day_of) -> list[TimecardException]:
    """One worker at two different sites within a few minutes."""
    window = ctx.policy.number("P17", "location_switch_minutes")
    sites = ctx.policy.mapping("P17", "sites")
    by_emp: dict[str, list[Punch]] = defaultdict(list)
    for p in ctx.punches:
        if p.source != "correction":  # typed in by a supervisor, not punched at a place
            by_emp[p.employee_id].append(p)
    found = []
    for emp, punches in sorted(by_emp.items()):
        punches.sort(key=lambda p: (p.timestamp, p.punch_id))
        for a, b in zip(punches, punches[1:], strict=False):
            site_a = sites.get(a.location, a.location)  # unknown place = its own site
            site_b = sites.get(b.location, b.location)
            gap = (b.timestamp - a.timestamp).total_seconds() / 60
            if site_a == site_b or gap > window:
                continue
            found.append(
                make_exception(
                    ctx,
                    "P17",
                    emp,
                    day_of(b),
                    f"{LEAD}: punched at {site_a} ({hhmm(a.timestamp)}) and at {site_b} "
                    f"({hhmm(b.timestamp)}), {fmt(gap)} min apart",
                    {
                        "check": "two_sites",
                        "first": {"punch_id": a.punch_id, "location": a.location, "site": site_a},
                        "second": {"punch_id": b.punch_id, "location": b.location, "site": site_b},
                        "gap_minutes": h(gap),
                        "location_switch_minutes": window,
                    },
                    [a, b],
                    suffix=f"two-sites-{b.punch_id}",
                    fix_options=_fixes([a, b]),
                )
            )
    return found


def _app_location(ctx: RuleContext, day_of) -> list[TimecardException]:
    """A mobile app punch from a place that is not an approved app location."""
    approved = ctx.policy.strings("P17", "approved_app_locations")
    found = []
    for p in sorted(ctx.punches, key=lambda p: (p.employee_id, p.timestamp)):
        if p.source != "app" or p.location in approved:
            continue
        found.append(
            make_exception(
                ctx,
                "P17",
                p.employee_id,
                day_of(p),
                f"{LEAD}: app punch at {hhmm(p.timestamp)} from '{p.location}', which is not "
                f"an approved app location",
                {
                    "check": "app_location",
                    "punch_id": p.punch_id,
                    "location": p.location,
                    "approved_app_locations": approved,
                },
                [p],
                suffix=f"app-location-{p.punch_id}",
                fix_options=_fixes([p]),
            )
        )
    return found
