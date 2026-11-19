"""Check the demo data really contains every case listed in docs/PLANTED_CASES.md.

These are fixture checks (is the planted data right?), not rule-engine tests.
"""

from datetime import date, datetime, timedelta

import pytest

from attendflow.config import DEFAULT_AS_OF, parse_local_timestamp

MON, TUE, WED, THU, FRI = (date(2026, 4, 13) + timedelta(days=i) for i in range(5))


def punches(ds, emp, day=None):
    rows = [p for p in ds.punches if p.employee_id == emp]
    if day is not None:
        rows = [p for p in rows if p.timestamp.date() == day]
    return sorted(rows, key=lambda p: p.timestamp)


def of_type(rows, kind):
    return [p.timestamp for p in rows if p.type == kind]


def worked_hours(rows) -> float:
    """Simple in->out minus breaks for one shift's punches (fixture helper only)."""
    (start,), (end,) = of_type(rows, "in"), of_type(rows, "out")
    breaks = sum(
        (e - s).total_seconds()
        for s, e in zip(of_type(rows, "break_start"), of_type(rows, "break_end"), strict=True)
    )
    return ((end - start).total_seconds() - breaks) / 3600


def leave(ds, emp):
    return [r for r in ds.leave_records if r.employee_id == emp]


def scheduled(ds, emp):
    return {s.date: s for s in ds.schedule if s.employee_id == emp}


def test_holiday_is_tuesday(dataset):
    assert {h.date: h.name for h in dataset.holidays}[TUE] == "Ambedkar Jayanti"


def test_no_punch_after_as_of(dataset):
    as_of = parse_local_timestamp(DEFAULT_AS_OF)
    assert max(p.timestamp for p in dataset.punches) <= as_of


def test_amit_missing_clock_out_tuesday(dataset):
    tue = punches(dataset, "E001", TUE)
    assert of_type(tue, "in") == [datetime(2026, 4, 14, 9, 0)]
    assert of_type(tue, "out") == []
    assert scheduled(dataset, "E001")[TUE].shift_end.hour == 18
    assert worked_hours(punches(dataset, "E001", MON)) == 8
    assert worked_hours(punches(dataset, "E001", WED)) == 8


def test_meena_36_worked_plus_12_scheduled(dataset):
    worked = sum(worked_hours(punches(dataset, "E002", d)) for d in (MON, TUE, WED))
    assert worked == 36
    sched = scheduled(dataset, "E002")
    future = sum(
        (
            datetime.combine(d, sched[d].shift_end) - datetime.combine(d, sched[d].shift_start)
        ).total_seconds()
        / 3600
        for d in (THU, FRI)
    )
    assert future == 12


def test_ramesh_night_shift_crosses_midnight(dataset):
    sched = scheduled(dataset, "E003")
    assert sched[MON].crosses_midnight
    rows = punches(dataset, "E003")
    ins, outs = of_type(rows, "in"), of_type(rows, "out")
    assert len(ins) == len(outs) == 2
    for start, end in zip(ins, outs, strict=True):
        assert end.date() == start.date() + timedelta(days=1)
        assert 7 < (end - start).total_seconds() / 3600 < 9


def test_neha_no_break_and_absence(dataset):
    mon = punches(dataset, "E004", MON)
    assert [p.type for p in mon] == ["in", "out"]
    assert worked_hours(mon) == 6
    assert WED in scheduled(dataset, "E004")
    assert punches(dataset, "E004", WED) == []
    assert all(r.date != WED for r in leave(dataset, "E004"))


def test_sana_duplicate_and_holiday(dataset):
    ins = of_type(punches(dataset, "E005", MON), "in")
    assert len(ins) == 2 and ins[1] - ins[0] == timedelta(minutes=2)
    assert punches(dataset, "E005", TUE)
    assert TUE not in scheduled(dataset, "E005")


def test_karan_late_and_works_on_leave(dataset):
    assert of_type(punches(dataset, "E006", MON), "in") == [datetime(2026, 4, 13, 10, 30)]
    (wed_leave,) = [r for r in leave(dataset, "E006") if r.date == WED]
    assert (wed_leave.status, wed_leave.duration) == ("approved", "full")
    assert punches(dataset, "E006", WED)


def test_dev_sick_leave_over_balance_without_certificate(dataset):
    sick = [r for r in leave(dataset, "E007") if r.leave_type == "sick"]
    assert len(sick) == 3
    assert all(r.status == "pending" and not r.certificate_uploaded for r in sick)
    (bal,) = [
        b for b in dataset.leave_balances if b.employee_id == "E007" and b.leave_type == "sick"
    ]
    assert bal.total_per_year - bal.used == 1
    assert punches(dataset, "E007") == []


def test_farah_half_day_but_full_punches(dataset):
    (wed_leave,) = leave(dataset, "E008")
    assert (wed_leave.date, wed_leave.duration, wed_leave.status) == (WED, "half", "approved")
    assert worked_hours(punches(dataset, "E008", WED)) > 7.5


@pytest.mark.parametrize("emp", ["E009", "E010"])
def test_controls_have_normal_days(dataset, emp):
    for day in (MON, WED):
        rows = punches(dataset, emp, day)
        if not rows:
            # Pooja's Wednesday: approved full-day leave instead of punches.
            assert any(r.date == day and r.status == "approved" for r in leave(dataset, emp))
            continue
        assert 7.5 <= worked_hours(rows) <= 9
        assert of_type(rows, "in")[0].time() <= scheduled(dataset, emp)[day].shift_start
