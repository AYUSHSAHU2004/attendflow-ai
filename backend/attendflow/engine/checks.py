"""The ordered registry of every policy check (P15 is applied while building shifts).

Order of work in run_engine():
1. Punches -> shifts (P2 de-dup, P15 attribution).
2. Leave and holiday calendar are applied when the RuleContext is built: leave days are
   taken out of the planned schedule BEFORE any check runs, so the forecast checks
   (P5 overtime, P6 rest, P16 consecutive days) never count a leave day as hours to work.
3. The checks below. Each one only reads the context, so their results do not depend on
   the order in this list; the order is just the policy order.
"""

from __future__ import annotations

from collections.abc import Callable

from attendflow.engine.models import TimecardException
from attendflow.engine.rules import (
    RuleContext,
    check_p1_missing_punch,
    check_p2_duplicate_punch,
    check_p3_daily_hours,
    check_p4_break,
    check_p5_weekly_overtime,
    check_p6_rest,
    check_p7_late_early,
)
from attendflow.engine.rules_leave import (
    check_p9_punches_on_leave,
    check_p11_leave_balance,
    check_p12_sick_certificate,
    check_p13_half_day,
)
from attendflow.engine.rules_review import check_p17_punch_review
from attendflow.engine.rules_schedule import (
    check_p8_unscheduled_work,
    check_p10_absence,
    check_p14_holiday_work,
    check_p16_consecutive_days,
)

Check = Callable[[RuleContext], list[TimecardException]]

CHECKS: dict[str, Check] = {
    "P1": check_p1_missing_punch,
    "P2": check_p2_duplicate_punch,
    "P3": check_p3_daily_hours,
    "P4": check_p4_break,
    "P5": check_p5_weekly_overtime,
    "P6": check_p6_rest,
    "P7": check_p7_late_early,
    "P8": check_p8_unscheduled_work,
    "P9": check_p9_punches_on_leave,
    "P10": check_p10_absence,
    "P11": check_p11_leave_balance,
    "P12": check_p12_sick_certificate,
    "P13": check_p13_half_day,
    "P14": check_p14_holiday_work,
    "P16": check_p16_consecutive_days,
    "P17": check_p17_punch_review,
}

PHASE1_POLICIES = ["P1", "P2", "P3", "P4", "P5", "P6", "P7"]
