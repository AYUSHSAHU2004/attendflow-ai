"""Rule engine unit tests on small synthetic fixtures: a passing and a failing case per
policy (P1-P7, P15), plus boundaries. Real demo data is tested in test_engine_demo.py."""

from datetime import date, datetime

from tests.engine_helpers import day_shift, only, policy_with, run

MON, TUE, WED, THU, FRI = "2026-04-13", "2026-04-14", "2026-04-15", "2026-04-16", "2026-04-17"
LATE_LUNCH = ("18:00", "19:00")


def sched(*days: str, start: str = "09:00", end: str = "18:00"):
    return [(d, start, end) for d in days]


# ------------------------------------------------------------------ P1 missing punch


def test_p1_missing_clock_out_is_flagged_with_scheduled_end_fix():
    punches = day_shift(MON)[:-1]  # drop the clock-out
    result = run(punches, sched(MON), as_of=datetime(2026, 4, 13, 23, 0))
    (exc,) = only(result, "P1")
    assert exc.details["missing"] == "clock_out"
    assert exc.severity == "high"
    assert [p.punch_id for p in exc.evidence] == ["P0001", "P0002", "P0003"]
    (fix,) = exc.fix_options
    assert fix.action == "set_clock_out"
    assert fix.params == {"timestamp": "2026-04-13T18:00", "worked_hours_after_fix": 8.0}


def test_p1_open_shift_still_in_progress_is_not_flagged():
    punches = day_shift(MON)[:-1]
    # 18:00 end + 4 h grace = 22:00, so at 21:00 the shift is still in progress.
    result = run(punches, sched(MON), as_of=datetime(2026, 4, 13, 21, 0))
    assert only(result, "P1") == []
    assert result.shifts[0].status == "in_progress"


def test_p1_complete_shift_passes():
    assert only(run(day_shift(MON), sched(MON)), "P1") == []


def test_p1_missing_clock_in_suggests_scheduled_start():
    punches = day_shift(MON)[1:]  # drop the clock-in
    (exc,) = only(run(punches, sched(MON)), "P1")
    assert exc.details["missing"] == "clock_in"
    assert exc.fix_options[0].params == {"timestamp": "2026-04-13T09:00"}


def test_p1_unscheduled_open_shift_uses_max_shift_length_and_has_no_fix():
    punches = [(f"{MON}T10:00:00", "in")]
    assert only(run(punches, as_of=datetime(2026, 4, 14, 1, 0)), "P1") == []  # 15 h < 16 h
    (exc,) = only(run(punches, as_of=datetime(2026, 4, 14, 3, 0)), "P1")  # 17 h
    assert exc.fix_options == []


# ------------------------------------------------------------------ P2 duplicates


def test_p2_duplicate_within_window_is_auto_resolved_and_voided():
    punches = [(f"{MON}T08:57:00", "in"), (f"{MON}T08:59:00", "in"), *day_shift(MON)[1:]]
    result = run(punches, sched(MON))
    (exc,) = only(result, "P2")
    assert exc.status == "auto_resolved"
    assert exc.severity == "low"
    assert exc.details["kept_punch_id"] == "P0001"
    assert exc.details["voided_punch_ids"] == ["P0002"]
    assert exc.details["gap_minutes"] == 2
    assert result.voided_punch_ids == ["P0002"]
    # Hours use the kept 08:57 punch: 08:57-18:00 minus 1 h lunch.
    assert round(result.shifts[0].worked_hours, 2) == 8.05


def test_p2_punches_outside_window_are_not_duplicates():
    punches = [(f"{MON}T08:50:00", "in"), (f"{MON}T08:56:00", "in"), *day_shift(MON)[1:]]
    result = run(punches, sched(MON))
    assert only(result, "P2") == []
    assert "2 clock-ins" in result.shifts[0].notes[0]


def test_p2_exactly_at_window_counts_and_taps_chain():
    punches = [
        (f"{MON}T08:55:00", "in"),
        (f"{MON}T09:00:00", "in"),  # exactly 5 min after the first
        (f"{MON}T09:04:00", "in"),  # 4 min after the second: same run
        (f"{MON}T18:00:00", "out"),
    ]
    (exc,) = only(run(punches, sched(MON)), "P2")
    assert exc.details["voided_punch_ids"] == ["P0002", "P0003"]


def test_p2_goes_to_supervisor_when_auto_resolve_is_off():
    punches = [(f"{MON}T08:57:00", "in"), (f"{MON}T08:59:00", "in"), *day_shift(MON)[1:]]
    policy = policy_with({("P2", "auto_resolve"): False})
    (exc,) = only(run(punches, sched(MON), policy=policy), "P2")
    assert exc.status == "open"


# ------------------------------------------------------------------ P3 daily hours


def test_p3_long_day_is_flagged_with_numbers():
    punches = day_shift(MON, "07:00", "19:30", ("12:30", "13:00"))
    (exc,) = only(run(punches, sched(MON, start="07:00", end="19:30")), "P3")
    assert exc.details == {
        "worked_hours": 12.0,
        "max_hours_per_day": 9.0,
        "over_by_hours": 3.0,
        "shifts": 1,
    }


def test_p3_exactly_the_limit_passes():
    punches = day_shift(MON, "08:00", "18:00")  # 10 h minus 1 h lunch = 9 h
    assert only(run(punches, sched(MON, start="08:00")), "P3") == []


def test_p3_adds_up_two_shifts_on_the_same_day():
    punches = day_shift(MON, "06:00", "11:00", None) + day_shift(MON, "13:00", "18:00", None)
    (exc,) = only(run(punches), "P3")  # unscheduled: 5 h + 5 h = 10 h
    assert exc.details["worked_hours"] == 10 and exc.details["shifts"] == 2


# ------------------------------------------------------------------ P4 break


def test_p4_six_hours_without_break_is_flagged():
    punches = day_shift(MON, "09:00", "15:00", None)
    (exc,) = only(run(punches, sched(MON, end="15:00")), "P4")
    assert exc.details["worked_hours"] == 6.0
    assert exc.details["break_minutes"] == 0
    assert exc.severity == "medium"


def test_p4_exactly_five_hours_without_break_passes():
    punches = day_shift(MON, "09:00", "14:00", None)
    assert only(run(punches, sched(MON, end="14:00")), "P4") == []


def test_p4_thirty_minute_break_passes():
    punches = day_shift(MON, "09:00", "15:30", ("12:00", "12:30"))
    assert only(run(punches, sched(MON, end="15:30")), "P4") == []


def test_p4_unpaired_break_counts_as_no_break():
    punches = [
        (f"{MON}T09:00:00", "in"),
        (f"{MON}T12:00:00", "break_start"),
        (f"{MON}T15:00:00", "out"),
    ]
    result = run(punches, sched(MON, end="15:00"))
    assert len(only(result, "P4")) == 1
    assert "no break end" in result.shifts[0].notes[0]


# ------------------------------------------------------------------ P5 weekly overtime


def test_p5_risk_uses_worked_plus_scheduled_and_cuts_exact_hours():
    worked = [
        p for d in (MON, TUE, WED) for p in day_shift(d, "07:00", "19:30", ("12:30", "13:00"))
    ]
    schedule = sched(MON, TUE, WED, start="07:00", end="19:30") + sched(THU, FRI, end="15:00")
    result = run(worked, schedule, as_of=datetime(2026, 4, 16, 8, 0), policies=["P5"])
    (exc,) = result.exceptions
    assert exc.kind == "risk"
    assert exc.date == date(2026, 4, 13)
    assert (exc.details["worked_hours"], exc.details["scheduled_remaining_hours"]) == (36, 12)
    assert (exc.details["projected_hours"], exc.details["over_by_hours"]) == (48, 8)
    approve, cut = exc.fix_options
    assert approve.params == {"hours": 8.0}
    assert cut.params["total_cut_hours"] == 8
    assert [(c["date"], c["new_hours"]) for c in cut.params["cuts"]] == [
        ("2026-04-17", 0.0),
        ("2026-04-16", 4.0),
    ]


def test_p5_exactly_forty_hours_passes():
    days = (MON, TUE, WED, THU, FRI)
    result = run([p for d in days for p in day_shift(d)], sched(*days), policies=["P5"])
    assert result.exceptions == []  # 5 x 8 h = 40 h, not more


def test_p5_breach_when_already_worked_over_limit_has_no_cut_option():
    days = (MON, TUE, WED, THU, FRI)
    punches = [p for d in days for p in day_shift(d, "08:00", "18:00")]  # 5 x 9 h = 45 h
    (exc,) = run(punches, sched(*days, start="08:00"), policies=["P5"]).exceptions
    assert exc.kind == "breach"
    assert exc.details["over_by_hours"] == 5
    assert [f.action for f in exc.fix_options] == ["approve_overtime"]


def test_p5_missing_punch_shift_counts_at_scheduled_hours():
    days = (MON, TUE, WED, THU, FRI)
    punches = [p for d in days for p in day_shift(d)]
    punches = [p for p in punches if p != (f"{TUE}T18:00:00", "out")]
    # Tue counts as its scheduled 8 h, so the week stays at 40 h: no P5.
    assert run(punches, sched(*days), policies=["P5"]).exceptions == []
    tighter = policy_with({("P5", "weekly_overtime_after_hours"): 39})
    (exc,) = run(punches, sched(*days), policy=tighter, policies=["P5"]).exceptions
    tue = next(d for d in exc.details["days"] if d["date"] == TUE)
    assert tue == {"date": TUE, "hours": 8.0, "source": "estimated"}


# ------------------------------------------------------------------ P6 rest


def test_p6_short_rest_between_actual_shifts_is_a_breach():
    punches = day_shift(MON, "14:00", "23:00", LATE_LUNCH) + day_shift(TUE, "07:00", "16:00")
    schedule = [(MON, "14:00", "23:00"), (TUE, "07:00", "16:00")]
    (exc,) = only(run(punches, schedule), "P6")
    assert exc.kind == "breach"
    assert exc.date == date(2026, 4, 14)
    assert exc.details["rest_hours"] == 8 and exc.details["short_by_hours"] == 3
    assert [p.type for p in exc.evidence] == ["out", "in"]


def test_p6_exactly_eleven_hours_rest_passes():
    punches = day_shift(MON, "11:00", "20:00") + day_shift(TUE, "07:00", "16:00")
    schedule = [(MON, "11:00", "20:00"), (TUE, "07:00", "16:00")]
    assert only(run(punches, schedule), "P6") == []


def test_p6_short_rest_before_an_upcoming_shift_is_a_risk():
    punches = day_shift(WED, "14:00", "23:00", LATE_LUNCH)
    schedule = [(WED, "14:00", "23:00"), (THU, "07:00", "16:00")]
    (exc,) = only(run(punches, schedule, as_of=datetime(2026, 4, 16, 1, 0)), "P6")
    assert exc.kind == "risk"
    assert exc.details["next_start_source"] == "schedule"


# ------------------------------------------------------------------ P7 late / early


def test_p7_late_beyond_grace_is_open():
    punches = [(f"{MON}T09:11:00", "in"), *day_shift(MON)[1:]]
    (exc,) = only(run(punches, sched(MON)), "P7")
    assert exc.status == "open"
    assert exc.details["late_minutes"] == 11 and exc.details["grace_minutes"] == 10


def test_p7_late_within_grace_is_auto_resolved():
    punches = [(f"{MON}T09:10:00", "in"), *day_shift(MON)[1:]]
    (exc,) = only(run(punches, sched(MON)), "P7")
    assert exc.status == "auto_resolved"


def test_p7_on_time_and_small_early_leave_pass():
    punches = [*day_shift(MON)[:-1], (f"{MON}T17:52:00", "out")]  # 8 min early: in grace
    assert only(run(punches, sched(MON)), "P7") == []


def test_p7_early_leave_beyond_grace_is_open():
    punches = [*day_shift(MON)[:-1], (f"{MON}T17:45:00", "out")]
    (exc,) = only(run(punches, sched(MON)), "P7")
    assert exc.details["type"] == "early_leave" and exc.details["early_minutes"] == 15


def test_p7_skips_unscheduled_shifts():
    punches = [(f"{MON}T11:00:00", "in"), (f"{MON}T15:00:00", "out")]
    assert only(run(punches), "P7") == []


# ------------------------------------------------------------------ P15 night shifts


def test_p15_night_shift_is_one_shift_on_its_start_date_and_not_flagged():
    punches = [
        (f"{MON}T21:58:00", "in"),
        (f"{TUE}T02:00:00", "break_start"),
        (f"{TUE}T02:30:00", "break_end"),
        (f"{TUE}T06:00:00", "out"),
    ]
    result = run(punches, [(MON, "22:00", "06:00")])
    (shift,) = result.shifts
    assert shift.date == date(2026, 4, 13)
    assert shift.status == "complete"
    assert round(shift.worked_hours, 2) == 7.53
    assert result.exceptions == []


def test_p15_unscheduled_night_shift_is_also_dated_by_start():
    punches = [(f"{MON}T22:00:00", "in"), (f"{TUE}T06:00:00", "out")]
    (shift,) = run(punches).shifts
    assert shift.date == date(2026, 4, 13)


def test_p15_night_shift_problems_are_dated_by_start_date():
    # Missing clock-out on a night shift: P1 belongs to Monday, not Tuesday.
    p1 = run([(f"{MON}T22:00:00", "in")], [(MON, "22:00", "06:00")])
    assert [(e.policy_id, e.date) for e in p1.exceptions] == [("P1", date(2026, 4, 13))]
    # A 12 h night shift breaks P3 on Monday.
    punches = [
        (f"{MON}T20:00:00", "in"),
        (f"{TUE}T01:00:00", "break_start"),
        (f"{TUE}T01:30:00", "break_end"),
        (f"{TUE}T08:30:00", "out"),
    ]
    (exc,) = only(run(punches, [(MON, "20:00", "08:30")]), "P3")
    assert exc.date == date(2026, 4, 13) and exc.details["worked_hours"] == 12


# ------------------------------------------------------------------ engine-wide


def test_supervisors_and_payroll_are_never_checked():
    punches = [(f"{MON}T09:00:00", "in", "E101")]
    assert run(punches).exceptions == []


def test_engine_is_deterministic():
    punches = day_shift(MON, "09:00", "15:00", None)
    a = run(punches, sched(MON, end="15:00")).model_dump_json()
    b = run(punches, sched(MON, end="15:00")).model_dump_json()
    assert a == b
