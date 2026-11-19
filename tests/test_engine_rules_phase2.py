"""Phase 2 rule tests on small synthetic fixtures: P8-P14, P16, P17, and the check order
(leave is taken out of the schedule before the overtime forecast)."""

from datetime import date, datetime, timedelta

import pytest

from attendflow.data.schemas import Holiday, LeaveBalance, LeaveRecord, ScheduleRow
from tests.engine_helpers import day_shift, only, policy_with, run

MON, TUE, WED, THU, FRI, SAT, SUN = (
    (date(2026, 4, 13) + timedelta(days=i)).isoformat() for i in range(7)
)
NEXT_MON = "2026-04-20"
THU_8AM = datetime(2026, 4, 16, 8, 0)
HOLIDAY = [(TUE, "Ambedkar Jayanti", "national")]
BALANCES = [("sick", 12, 11), ("casual", 12, 2), ("earned", 15, 3)]


def sched(*days: str, start: str = "09:00", end: str = "18:00"):
    return [(d, start, end) for d in days]


def all_text(exc) -> str:
    return " ".join([exc.title, exc.summary, *(f.label for f in exc.fix_options)]).lower()


# ------------------------------------------------------------------ P8 unscheduled work


def test_p8_work_on_a_day_without_schedule_needs_approval():
    (exc,) = only(run(day_shift(TUE, "10:00", "14:00", None), sched(MON)), "P8")
    assert exc.date == date(2026, 4, 14) and exc.severity == "medium"
    assert exc.details["worked_hours"] == 4
    assert "Punched 10:00-14:00 (4 h) with no scheduled shift" in exc.summary
    assert [f.action for f in exc.fix_options] == [
        "approve_unscheduled_work",
        "reject_unscheduled_work",
    ]


def test_p8_scheduled_work_passes():
    assert only(run(day_shift(MON), sched(MON)), "P8") == []


# ------------------------------------------------------------------ P9 punches on leave


def test_p9_punches_on_approved_full_day_leave():
    result = run(day_shift(WED), sched(WED), leave=[(WED, "casual", "full", "approved")])
    (exc,) = only(result, "P9")
    assert exc.details["leave_status"] == "approved" and exc.details["worked_hours"] == 8
    assert isinstance(exc.evidence[-1], LeaveRecord)  # punches first, then the leave row
    assert [f.action for f in exc.fix_options] == ["cancel_leave", "void_punches"]
    assert exc.fix_options[1].params["punch_ids"] == ["P0001", "P0002", "P0003", "P0004"]
    assert only(result, "P7") == []  # times on a leave day are not judged by P7


def test_p9_also_flags_pending_full_day_leave():
    result = run(day_shift(WED), sched(WED), leave=[(WED, "sick", "full", "pending")])
    (exc,) = only(result, "P9")
    assert "Withdraw the pending leave request" in exc.fix_options[0].label


@pytest.mark.parametrize(
    "leave",
    [(WED, "casual", "full", "rejected"), (WED, "casual", "half", "approved")],
    ids=["rejected", "half-day"],
)
def test_p9_ignores_rejected_and_half_day_leave(leave):
    assert only(run(day_shift(WED), sched(WED), leave=[leave]), "P9") == []


def test_p9_and_p10_leave_without_punches_is_clean():
    result = run([], sched(WED), leave=[(WED, "earned", "full", "approved")])
    assert result.exceptions == []


# ------------------------------------------------------------------ P10 absence


def test_p10_scheduled_day_with_no_punches_and_no_leave():
    (exc,) = run([], sched(WED), balances=BALANCES).exceptions
    assert exc.policy_id == "P10" and exc.severity == "high"
    assert exc.summary == "Scheduled 09:00-18:00: no punches and no leave request"
    assert isinstance(exc.evidence[0], ScheduleRow)
    # Sick has only 1 day left, which is still enough for one day of leave.
    assert [f.option_id for f in exc.fix_options] == [
        "record_casual_leave",
        "record_earned_leave",
        "record_sick_leave",
        "mark_unpaid_absence",
        "add_scheduled_punches",
    ]
    assert exc.fix_options[-1].params == {
        "clock_in": "2026-04-15T09:00",
        "clock_out": "2026-04-15T18:00",
    }


def test_p10_waits_for_shift_end_plus_grace_and_ignores_the_future():
    # 18:00 end + 4 h grace = 22:00
    assert run([], sched(WED), as_of=datetime(2026, 4, 15, 21, 59)).exceptions == []
    assert len(run([], sched(WED), as_of=datetime(2026, 4, 15, 22, 0)).exceptions) == 1
    assert run([], sched(THU, FRI), as_of=THU_8AM).exceptions == []


def test_p10_any_leave_status_explains_the_day():
    leave = [(WED, "casual", "full", "rejected")]
    assert only(run([], sched(WED), leave=leave), "P10") == []


def test_p10_holiday_duty_no_show_is_an_absence():
    (exc,) = only(run([], sched(TUE), holidays=HOLIDAY), "P10")
    assert "holiday duty on Ambedkar Jayanti" in exc.summary


def test_p10_pending_leave_reduces_what_can_still_be_recorded():
    # Sick: 12 - 11 used - 1 pending = 0 left, so no "record sick leave" option.
    result = run(
        [],
        sched(MON, WED),
        balances=BALANCES,
        leave=[(MON, "sick", "full", "pending")],
    )
    (exc,) = only(result, "P10")
    assert "record_sick_leave" not in [f.option_id for f in exc.fix_options]


# ------------------------------------------------------------------ P11 leave balance

DEV_LEAVE = [(d, "sick", "full", "pending") for d in (MON, WED, THU)]


def test_p11_applied_over_balance_with_three_fix_options():
    result = run([], sched(MON, WED, THU), leave=DEV_LEAVE, balances=BALANCES, as_of=THU_8AM)
    (exc,) = only(result, "P11")
    assert "Sick leave applied 3, balance 1 (12 total - 11 used): 2 day(s) over" in exc.summary
    assert exc.date == date(2026, 4, 13)
    assert (exc.details["applied_days"], exc.details["balance"]) == (3, 1)
    split, casual, earned, reject = exc.fix_options
    # The balance pays for the earliest day; the later days are over the balance.
    assert split.params["paid"] == [{"date": MON, "days": 1.0}]
    assert [e["date"] for e in split.params["unpaid"]] == [WED, THU]
    assert (casual.action, casual.params["to_type"]) == ("move_leave_type", "casual")
    assert earned.params["to_type"] == "earned"
    assert reject.action == "reject_leave_days"
    assert isinstance(exc.evidence[-1], LeaveBalance)


def test_p11_within_balance_passes_and_balance_is_computed_not_stored():
    roomy = [("sick", 12, 9), ("casual", 12, 2), ("earned", 15, 3)]  # 3 left
    assert only(run([], leave=DEV_LEAVE, balances=roomy), "P11") == []


def test_p11_half_days_count_as_half():
    halves = [(d, "sick", "half", "pending") for d in (MON, TUE)]
    assert only(run([], leave=halves, balances=BALANCES), "P11") == []  # 1.0 <= 1
    three = [*halves, (WED, "sick", "half", "pending")]
    (exc,) = only(run([], leave=three, balances=BALANCES), "P11")
    assert exc.details["over_by_days"] == 0.5


def test_p11_move_option_only_when_the_other_type_has_room():
    tight = [("sick", 12, 11), ("casual", 12, 11), ("earned", 15, 14)]  # 1 left each
    (exc,) = only(run([], leave=DEV_LEAVE, balances=tight), "P11")
    assert [f.action for f in exc.fix_options] == ["split_paid_unpaid_leave", "reject_leave_days"]


def test_p11_approved_leave_is_already_in_used():
    approved = [(d, "sick", "full", "approved") for d in (MON, WED, THU)]
    assert only(run([], leave=approved, balances=BALANCES), "P11") == []


# ------------------------------------------------------------------ P12 sick certificate


def test_p12_unsorted_sick_days_across_a_holiday_form_one_run():
    shuffled = [DEV_LEAVE[2], DEV_LEAVE[0], DEV_LEAVE[1]]  # Thu, Mon, Wed
    result = run([], sched(MON, WED, THU), leave=shuffled, holidays=HOLIDAY)
    (exc,) = only(result, "P12")
    assert exc.date == date(2026, 4, 13)
    assert exc.details["dates"] == [MON, WED, THU]
    assert "3 sick days in a row (Mon 13 Apr to Thu 16 Apr)" in exc.summary
    unpaid = exc.fix_options[-1]
    assert unpaid.params["dates"] == [THU]  # only the day after the 2-day limit


def test_p12_weekend_does_not_break_the_run():
    leave = [(d, "sick", "full", "pending") for d in (FRI, NEXT_MON, "2026-04-21")]
    assert len(only(run([], sched(FRI), leave=leave), "P12")) == 1


def test_p12_a_scheduled_working_day_breaks_the_run():
    leave = [(d, "sick", "full", "pending") for d in (MON, WED, THU)]
    result = run(day_shift(TUE), sched(MON, TUE, WED, THU), leave=leave)  # worked Tuesday
    assert only(result, "P12") == []  # runs of 1 and 2 days


def test_p12_two_days_or_a_certificate_pass():
    two = [(d, "sick", "full", "pending") for d in (MON, TUE)]
    assert only(run([], leave=two), "P12") == []
    with_cert = [(MON, "sick", "full", "pending", "yes"), *DEV_LEAVE[1:]]
    assert only(run([], leave=with_cert, holidays=HOLIDAY), "P12") == []


def test_p12_rejected_days_do_not_count():
    leave = [*DEV_LEAVE[:2], (THU, "sick", "full", "rejected")]
    assert only(run([], leave=leave, holidays=HOLIDAY), "P12") == []


# ------------------------------------------------------------------ P13 half-day leave

HALF = [(WED, "casual", "half", "approved")]


def test_p13_full_day_worked_on_a_half_day_leave():
    (exc,) = only(run(day_shift(WED), sched(WED), leave=HALF), "P13")
    assert exc.details["type"] == "worked_full_day"
    assert "8 h worked: expected about 4 h (3-5 h)" in exc.summary
    assert exc.fix_options[0].params == {"date": WED, "leave_type": "casual", "days": 0.5}
    assert only(run(day_shift(WED), sched(WED), leave=HALF), "P9") == []  # not P9


@pytest.mark.parametrize("end", ["13:00", "14:00"])  # 4 h and exactly 5 h
def test_p13_about_half_a_day_passes_and_skips_p7(end):
    result = run(day_shift(WED, "09:00", end, None), sched(WED), leave=HALF)
    assert only(result, "P13") == []
    assert only(result, "P7") == []  # leaving at 13:00 is the half day, not an early leave


def test_p13_missing_working_half_once_the_day_is_over():
    (exc,) = only(run([], sched(WED), leave=HALF), "P13")
    assert exc.details["type"] == "working_half_missing"
    assert [f.action for f in exc.fix_options][:2] == [
        "convert_to_full_day_leave",
        "mark_unpaid_hours",
    ]
    assert only(run([], sched(WED), leave=HALF, as_of=datetime(2026, 4, 15, 12)), "P13") == []


def test_p13_short_day_without_leave_is_p7_not_p13():
    result = run(day_shift(WED, "09:00", "13:00", None), sched(WED))
    assert only(result, "P13") == []
    assert only(result, "P7")[0].details["type"] == "early_leave"


# ------------------------------------------------------------------ P14 holiday work


def test_p14_planned_holiday_duty_is_low_severity():
    (exc,) = only(run(day_shift(TUE), sched(TUE), holidays=HOLIDAY), "P14")
    assert exc.severity == "low"
    assert exc.details["scheduled"] is True and exc.details["comp_off_days"] == 1.0
    assert [f.action for f in exc.fix_options] == ["holiday_pay", "comp_off"]
    assert isinstance(exc.evidence[-1], Holiday)


def test_p14_unscheduled_holiday_work_is_medium_and_needs_p8_first():
    result = run(day_shift(TUE, "10:00", "14:00", None), holidays=HOLIDAY)
    (exc,) = only(result, "P14")
    assert exc.severity == "medium"
    assert exc.details["depends_on"] == ["P8"]
    assert exc.details["comp_off_days"] == 0.5  # 4 h or less = half a day
    assert len(only(result, "P8")) == 1


def test_p14_missing_punch_uses_scheduled_hours_and_needs_p1_first():
    punches = day_shift(TUE)[:-1]  # no clock-out
    (exc,) = only(run(punches, sched(TUE), holidays=HOLIDAY), "P14")
    assert exc.details["depends_on"] == ["P1"]
    assert exc.details["compensation_hours"] == 8
    assert exc.details["compensation_hours_source"] == "scheduled"


@pytest.mark.parametrize(("kind", "flagged"), [("company", True), ("optional", False)])
def test_p14_holiday_types(kind, flagged):
    result = run(day_shift(TUE), sched(TUE), holidays=[(TUE, "Some day", kind)])
    assert bool(only(result, "P14")) is flagged


def test_p14_night_shift_ending_on_the_holiday_is_not_holiday_work():
    punches = [(f"{MON}T22:00:00", "in"), (f"{TUE}T06:00:00", "out")]
    result = run(punches, [(MON, "22:00", "06:00")], holidays=HOLIDAY)
    assert only(result, "P14") == []


def test_p14_offers_only_the_configured_options():
    comp_only = policy_with({("P14", "compensation_options"): ["comp_off"]})
    result = run(day_shift(TUE), sched(TUE), holidays=HOLIDAY, policy=comp_only)
    assert [f.action for f in only(result, "P14")[0].fix_options] == ["comp_off"]


# ------------------------------------------------------------------ P16 consecutive days

WEEK = [MON, TUE, WED, THU, FRI, SAT, SUN]


def test_p16_seventh_worked_day_in_a_row_is_a_breach():
    punches = [p for d in WEEK for p in day_shift(d)]
    (exc,) = only(run(punches, sched(*WEEK)), "P16")
    assert exc.kind == "breach" and exc.severity == "high"
    assert exc.date == date(2026, 4, 19)  # the 7th day
    assert exc.details["consecutive_days"] == 7 and exc.details["max_consecutive_days"] == 6
    assert [f.action for f in exc.fix_options] == ["approve_exception"]


def test_p16_six_days_pass():
    punches = [p for d in WEEK[:6] for p in day_shift(d)]
    assert only(run(punches, sched(*WEEK[:6])), "P16") == []


def test_p16_forecast_from_schedule_is_a_risk_with_a_rest_day_fix():
    punches = [p for d in WEEK[:3] for p in day_shift(d)]  # Mon-Wed worked
    result = run(punches, sched(*WEEK), as_of=THU_8AM)  # Thu-Sun still scheduled
    (exc,) = only(result, "P16")
    assert exc.kind == "risk"
    assert [d["source"] for d in exc.details["days"]] == ["worked"] * 3 + ["scheduled"] * 4
    rest = exc.fix_options[0]
    assert rest.action == "give_rest_day" and rest.params == {"date": SUN}


def test_p16_leave_day_or_absence_breaks_the_run():
    punches = [p for d in WEEK[:3] for p in day_shift(d)]
    on_leave = run(
        punches, sched(*WEEK), as_of=THU_8AM, leave=[(FRI, "casual", "full", "approved")]
    )
    assert only(on_leave, "P16") == []
    absent = [p for d in WEEK if d != WED for p in day_shift(d)]  # Wed scheduled, not worked
    assert only(run(absent, sched(*WEEK)), "P16") == []


def test_p16_limit_comes_from_policy_json():
    punches = [p for d in WEEK[:6] for p in day_shift(d)]
    strict = policy_with({("P16", "max_consecutive_days"): 5})
    assert len(only(run(punches, sched(*WEEK[:6]), policy=strict), "P16")) == 1


# ------------------------------------------------------------------ P17 punch review

GATE_2 = {"device_id": "GATE-02"}
INBOUND = {"location": "Warehouse 1 - Inbound Gate"}
OUTBOUND = {"location": "Warehouse 1 - Outbound Gate"}
APP_OK = {
    "source": "app",
    "device_id": "MOBILE-APP",
    "location": "Warehouse 1 - Mobile app (geofenced)",
}
APP_HOME = {"source": "app", "device_id": "MOBILE-APP", "location": "Home - Andheri"}


def test_p17_two_workers_same_second_same_device():
    punches = [(f"{MON}T08:59:41", "in", "E001"), (f"{MON}T08:59:41", "in", "E002")]
    found = only(run(punches), "P17")
    assert {e.employee_id for e in found} == {"E001", "E002"}
    for e in found:
        assert e.summary.startswith("Possible punch conflict, needs review: punched on GATE-01")
        assert e.details["check"] == "same_second" and len(e.evidence) == 2
        assert [f.action for f in e.fix_options] == ["confirm_punches_valid", "void_punches"]


@pytest.mark.parametrize(
    ("first_meta", "second"),
    [
        ({}, (f"{MON}T08:59:42", "in", "E002")),  # one second later
        ({}, (f"{MON}T08:59:41", "in", "E002", GATE_2)),  # other device
        (APP_OK, (f"{MON}T08:59:41", "in", "E002", APP_OK)),  # app: separate phones
    ],
    ids=["one-second-apart", "other-device", "both-app"],
)
def test_p17_same_second_needs_same_device_and_exact_second(first_meta, second):
    punches = [(f"{MON}T08:59:41", "in", "E001", first_meta), second]
    assert [e for e in only(run(punches), "P17") if e.details["check"] == "same_second"] == []


def test_p17_two_sites_within_the_window():
    far = {"location": "Warehouse 9 - North Gate"}
    punches = [(f"{MON}T09:00:00", "in", "E001", INBOUND), (f"{MON}T09:20:00", "out", "E001", far)]
    (exc,) = only(run(punches), "P17")
    assert exc.details["check"] == "two_sites" and exc.details["gap_minutes"] == 20
    assert "punched at Warehouse 1 (09:00) and at Warehouse 9 - North Gate (09:20)" in exc.summary


def test_p17_two_gates_of_the_same_site_or_a_long_gap_pass():
    same_site = [
        (f"{MON}T09:00:00", "in", "E001", INBOUND),
        (f"{MON}T09:05:00", "break_start", "E001", OUTBOUND),
    ]
    assert only(run(same_site), "P17") == []
    far = {"location": "Warehouse 9 - North Gate"}
    late = [(f"{MON}T09:00:00", "in", "E001", INBOUND), (f"{MON}T10:01:00", "out", "E001", far)]
    assert only(run(late), "P17") == []  # 61 min > 60 min window


def test_p17_app_punch_outside_approved_locations():
    punches = [
        (f"{MON}T09:00:00", "in", "E001", APP_HOME),
        (f"{MON}T18:00:00", "out", "E001", APP_OK),
    ]
    found = only(run(punches), "P17")
    app = [e for e in found if e.details["check"] == "app_location"]
    assert len(app) == 1 and app[0].details["punch_id"] == "P0001"
    assert "app punch at 09:00 from 'Home - Andheri'" in app[0].summary


def test_p17_wording_never_accuses():
    far = {"location": "Warehouse 9 - North Gate"}
    punches = [
        (f"{MON}T08:59:41", "in", "E001", INBOUND),
        (f"{MON}T08:59:41", "in", "E002", INBOUND),
        (f"{MON}T09:10:00", "break_start", "E001", far),
        (f"{MON}T12:00:00", "in", "E002", APP_HOME),
    ]
    found = only(run(punches), "P17")
    assert {e.details["check"] for e in found} == {"same_second", "two_sites", "app_location"}
    for e in found:
        assert "fraud" not in all_text(e)
        assert e.title == "Possible punch conflict, needs review"


# ------------------------------------------------------------------ check order: leave first

MEENA_WEEK = [
    p for d in (MON, TUE, WED) for p in day_shift(d, "07:00", "19:30", ("12:30", "13:00"))
]
MEENA_SCHEDULE = sched(MON, TUE, WED, start="07:00", end="19:30") + sched(THU, FRI, end="15:00")


def test_check_order_leave_is_removed_before_the_overtime_forecast():
    # Without leave: 36 h + 12 h = 48 h.
    (plain,) = run(MEENA_WEEK, MEENA_SCHEDULE, as_of=THU_8AM, policies=["P5"]).exceptions
    assert plain.details["projected_hours"] == 48
    # Friday is a pending sick day: 36 h + 6 h = 42 h, not a wrong 36 + 12.
    leave = [(FRI, "sick", "full", "pending")]
    (exc,) = run(MEENA_WEEK, MEENA_SCHEDULE, as_of=THU_8AM, policies=["P5"], leave=leave).exceptions
    assert exc.details["scheduled_remaining_hours"] == 6
    assert "36 h worked + 6 h scheduled = 42 h" in exc.summary
    fri = next(d for d in exc.details["days"] if d["date"] == FRI)
    assert fri == {"date": FRI, "hours": 0.0, "source": "full-day sick leave (pending)"}
    # The cut option only touches Thursday now; Friday is already off.
    assert [c["date"] for c in exc.fix_options[1].params["cuts"]] == [THU]


def test_leave_brings_a_week_back_under_the_limit():
    # Dev-like: 32 h worked + Fri 8 h = 40 h is fine; Thu is a sick day and must not count.
    days = (MON, TUE, WED)
    punches = [p for d in days for p in day_shift(d, "08:00", "18:00")]  # 3 x 9 h = 27 h
    schedule = sched(*days, start="08:00") + sched(THU, FRI)
    assert len(run(punches, schedule, as_of=THU_8AM, policies=["P5"]).exceptions) == 1  # 43 h
    leave = [(THU, "sick", "full", "pending")]
    assert run(punches, schedule, as_of=THU_8AM, policies=["P5"], leave=leave).exceptions == []


def test_half_day_and_rejected_leave_in_the_forecast():
    half = [(FRI, "casual", "half", "approved")]
    (exc,) = run(MEENA_WEEK, MEENA_SCHEDULE, as_of=THU_8AM, policies=["P5"], leave=half).exceptions
    assert exc.details["scheduled_remaining_hours"] == 8  # Thu 6 + Fri (6 - 4)
    rejected = [(FRI, "casual", "full", "rejected")]
    (exc,) = run(
        MEENA_WEEK, MEENA_SCHEDULE, as_of=THU_8AM, policies=["P5"], leave=rejected
    ).exceptions
    assert exc.details["scheduled_remaining_hours"] == 12  # rejected leave changes nothing


def test_p6_does_not_forecast_rest_before_a_leave_day():
    punches = day_shift(WED, "14:00", "23:00", ("18:00", "19:00"))
    schedule = [(WED, "14:00", "23:00"), (THU, "07:00", "16:00")]
    as_of = datetime(2026, 4, 16, 1, 0)
    assert len(only(run(punches, schedule, as_of=as_of), "P6")) == 1
    leave = [(THU, "casual", "full", "approved")]
    assert only(run(punches, schedule, as_of=as_of, leave=leave), "P6") == []
