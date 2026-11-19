"""Rule engine on the real demo data: output must equal docs/PLANTED_CASES.md for P1-P7."""

from datetime import date, datetime

import pytest

from attendflow.config import DEFAULT_AS_OF, parse_local_timestamp
from attendflow.data import load_dataset
from attendflow.engine import run_engine
from attendflow.policy import load_policy
from attendflow.scripts import detect
from tests.conftest import DATA_DIR, replace_in_file

AS_OF = parse_local_timestamp(DEFAULT_AS_OF)
MON, TUE, WED = date(2026, 4, 13), date(2026, 4, 14), date(2026, 4, 15)

# PLANTED_CASES.md filtered to P1-P7. P8-P14 and P16 come in Phase 2.
EXPECTED = {
    ("P1", "E001", TUE),  # Amit: no clock-out on the holiday
    ("P3", "E002", MON),  # Meena: 12 h days
    ("P3", "E002", TUE),
    ("P3", "E002", WED),
    ("P5", "E002", MON),  # Meena: week starting Mon 13 Apr, 36 + 12 = 48 h
    ("P4", "E004", MON),  # Neha: 6 h, no break
    ("P2", "E005", MON),  # Sana: double tap at 08:57 / 08:59
    ("P7", "E006", MON),  # Karan: 90 min late
}


@pytest.fixture(scope="module")
def result(dataset):
    return run_engine(dataset, load_policy(DATA_DIR / "policy.json"), AS_OF)


def keys(result):
    return {(e.policy_id, e.employee_id, e.date) for e in result.exceptions}


def test_demo_data_gives_exactly_the_planted_cases(result):
    assert keys(result) == EXPECTED
    assert len(result.exceptions) == len(EXPECTED)  # no doubles hiding behind the set


def test_meena_overtime_risk_numbers(result):
    (p5,) = [e for e in result.exceptions if e.policy_id == "P5"]
    assert p5.kind == "risk" and p5.status == "open" and p5.severity == "high"
    d = p5.details
    assert (d["worked_hours"], d["scheduled_remaining_hours"]) == (36, 12)
    assert (d["projected_hours"], d["weekly_overtime_after_hours"], d["over_by_hours"]) == (
        48,
        40,
        8,
    )
    assert "36 h worked + 12 h scheduled = 48 h > 40 h (over by 8 h)" in p5.summary
    assert [f.action for f in p5.fix_options] == ["approve_overtime", "reduce_scheduled_hours"]
    assert p5.fix_options[1].params["total_cut_hours"] == 8
    assert len(p5.evidence) == 12  # in, break start, break end, out on Mon, Tue and Wed


def test_amit_p1_suggests_scheduled_end(result):
    (p1,) = [e for e in result.exceptions if e.policy_id == "P1"]
    assert [p.punch_id for p in p1.evidence] == ["P0037", "P0040", "P0042"]
    (fix,) = p1.fix_options
    assert fix.params == {"timestamp": "2026-04-14T18:00", "worked_hours_after_fix": 8.0}


def test_sana_duplicate_is_auto_resolved(result):
    (p2,) = [e for e in result.exceptions if e.policy_id == "P2"]
    assert p2.status == "auto_resolved"
    assert p2.details["kept_punch_id"] == "P0003"
    assert result.voided_punch_ids == ["P0005"]


def test_neha_and_karan_numbers(result):
    by_policy = {e.policy_id: e for e in result.exceptions}
    assert by_policy["P4"].details["worked_hours"] == 6
    assert by_policy["P4"].details["break_minutes"] == 0
    assert by_policy["P7"].details["late_minutes"] == 90
    assert by_policy["P7"].fix_options == []  # filled in a later phase


def test_ramesh_night_shifts_are_single_shifts_and_not_flagged(result):
    shifts = [s for s in result.shifts if s.employee_id == "E003"]
    assert [s.date for s in shifts] == [MON, WED]
    for s in shifts:
        assert s.status == "complete"
        span = (s.clock_out.timestamp - s.clock_in.timestamp).total_seconds() / 3600
        assert round(span) == 8  # 21:58 -> 06:00, one 8-hour shift
        assert round(s.worked_hours, 2) == 7.53  # minus the 30 min break
    assert not [e for e in result.exceptions if e.employee_id == "E003"]


def test_controls_and_future_days_are_clean(result):
    flagged = {e.employee_id for e in result.exceptions}
    assert not flagged & {"E009", "E010", "E101", "E102", "E201"}
    assert not [e for e in result.exceptions if e.employee_id == "E001" and e.date != TUE]
    assert all(e.date <= WED for e in result.exceptions)


def test_every_exception_has_severity_details_and_evidence(result):
    for e in result.exceptions:
        assert e.severity in {"low", "medium", "high"}
        assert e.details and e.summary
        assert e.evidence, e.exception_id
    assert len({e.exception_id for e in result.exceptions}) == len(result.exceptions)


def test_punches_after_as_of_are_ignored(dataset):
    early = run_engine(dataset, load_policy(DATA_DIR / "policy.json"), datetime(2026, 4, 14, 8, 0))
    assert early.ignored_future_punches > 0
    # Amit's Tuesday shift has not started yet, so there is no missed punch.
    assert ("P1", "E001", TUE) not in keys(early)


def test_changing_a_limit_in_policy_json_changes_the_result(data_copy):
    """No code edit: only the JSON file changes."""
    replace_in_file(data_copy / "policy.json", '"max_hours_per_day": 9', '"max_hours_per_day": 12')
    replace_in_file(data_copy / "policy.json", '"grace_minutes": 10', '"grace_minutes": 120')
    replace_in_file(
        data_copy / "policy.json",
        '"weekly_overtime_after_hours": 40',
        '"weekly_overtime_after_hours": 50',
    )
    replace_in_file(
        data_copy / "policy.json",
        '"break_required_after_hours": 5',
        '"break_required_after_hours": 4',
    )
    out = run_engine(load_dataset(data_copy), load_policy(data_copy / "policy.json"), AS_OF)
    got = keys(out)
    assert not {k for k in got if k[0] in {"P3", "P5"}}  # limits raised: gone
    (p7,) = [e for e in out.exceptions if e.policy_id == "P7"]
    assert p7.status == "auto_resolved"  # Karan's 90 min is now within the 120 min grace
    assert ("P4", "E009", MON) not in got  # Arjun took a 62 min break: still fine
    assert ("P4", "E004", MON) in got


def test_cli_prints_table_with_meena_numbers(capsys):
    detect.main(["--data-dir", str(DATA_DIR), "--as-of", DEFAULT_AS_OF])
    out = capsys.readouterr().out
    assert "36 h worked + 12 h scheduled = 48 h > 40 h (over by 8 h)" in out
    assert "E002 Meena Iyer" in out
    assert "E003" not in out  # Ramesh
    assert "8 exception(s): 7 open, 1 auto-resolved." in out


def test_cli_json_output(capsys):
    import json

    detect.main(
        ["--data-dir", str(DATA_DIR), "--as-of", DEFAULT_AS_OF, "--json", "--employee", "E002"]
    )
    data = json.loads(capsys.readouterr().out)
    assert {e["policy_id"] for e in data["exceptions"]} == {"P3", "P5"}
