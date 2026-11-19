"""Full rule engine (P1-P17) on the real demo data: output must equal docs/PLANTED_CASES.md."""

import json
from datetime import date

import pytest

from attendflow.config import DEFAULT_AS_OF, parse_local_timestamp
from attendflow.data.schemas import LeaveRecord
from attendflow.engine import EngineResult, run_engine
from attendflow.policy import load_policy
from attendflow.scripts import detect
from tests.conftest import DATA_DIR
from tests.engine_helpers import policy_with

AS_OF = parse_local_timestamp(DEFAULT_AS_OF)
MON, TUE, WED = date(2026, 4, 13), date(2026, 4, 14), date(2026, 4, 15)

# The whole answer key: every planted case plus the documented side effects.
EXPECTED = {
    ("P1", "E001", TUE),  # 1  Amit: no clock-out on the holiday
    ("P14", "E001", TUE),  #    ... while on holiday duty
    ("P3", "E002", MON),  # 2  Meena: 12 h days
    ("P3", "E002", TUE),
    ("P3", "E002", WED),
    ("P5", "E002", MON),  #    36 + 12 = 48 h (risk)
    ("P14", "E002", TUE),  #    holiday duty
    ("P4", "E004", MON),  # 4  Neha: 6 h, no break
    ("P10", "E004", WED),  # 5  Neha: absent, no leave
    ("P2", "E005", MON),  # 6  Sana: double tap (auto-resolved)
    ("P8", "E005", TUE),  # 7  Sana: unscheduled ...
    ("P14", "E005", TUE),  #    ... holiday work
    ("P7", "E006", MON),  # 8  Karan: 90 min late
    ("P9", "E006", WED),  # 9  Karan: punched on approved leave
    ("P11", "E007", MON),  # 10 Dev: 3 sick days, balance 1
    ("P12", "E007", MON),  #    no certificate
    ("P13", "E008", WED),  # 11 Farah: half-day leave, full day worked
}


@pytest.fixture(scope="module")
def result(dataset) -> EngineResult:
    return run_engine(dataset, load_policy(DATA_DIR / "policy.json"), AS_OF)


def by(result, policy_id, emp):
    found = [e for e in result.exceptions if e.policy_id == policy_id and e.employee_id == emp]
    assert len(found) == 1, (policy_id, emp, found)
    return found[0]


def test_full_answer_key(result):
    assert {(e.policy_id, e.employee_id, e.date) for e in result.exceptions} == EXPECTED
    assert len(result.exceptions) == len(EXPECTED)


def test_dev_applied_3_balance_1_and_certificate(result):
    p11 = by(result, "P11", "E007")
    assert "applied 3, balance 1" in p11.summary
    assert p11.details["requested_dates"] == ["2026-04-13", "2026-04-15", "2026-04-16"]
    assert [f.option_id for f in p11.fix_options][:2] == ["split_paid_unpaid", "move_to_casual"]
    p12 = by(result, "P12", "E007")
    assert p12.details["sick_days"] == 3  # the Tuesday holiday does not break the run
    assert all(isinstance(r, LeaveRecord) for r in p12.evidence)
    assert not [e for e in result.exceptions if e.employee_id == "E007" and e.policy_id == "P10"]


def test_karan_sana_farah_amit_meena(result):
    p9 = by(result, "P9", "E006")
    assert p9.details["leave_type"] == "casual" and p9.details["leave_status"] == "approved"
    sana = by(result, "P14", "E005")
    assert sana.severity == "medium" and sana.details["depends_on"] == ["P8"]
    assert sana.details["comp_off_days"] == 0.5
    assert by(result, "P14", "E001").severity == "low"
    assert by(result, "P14", "E001").details["depends_on"] == ["P1"]
    assert by(result, "P14", "E002").severity == "low"
    farah = by(result, "P13", "E008")
    assert farah.details["type"] == "worked_full_day" and farah.details["worked_hours"] > 7.5


def test_phase1_numbers_unchanged_after_the_seconds_offset(result):
    p5 = by(result, "P5", "E002")
    assert "36 h worked + 12 h scheduled = 48 h > 40 h (over by 8 h)" in p5.summary
    assert by(result, "P7", "E006").details["late_minutes"] == 90
    assert by(result, "P4", "E004").details["worked_hours"] == 6
    assert "kept P0003 08:57, voided P0005 08:59" in by(result, "P2", "E005").summary


def test_controls_ramesh_and_review_checks_are_clean(result):
    flagged = {e.employee_id for e in result.exceptions}
    assert not flagged & {"E003", "E009", "E010", "E101", "E102", "E201"}
    assert not [e for e in result.exceptions if e.policy_id in {"P6", "P16", "P17"}]
    assert all(e.date <= WED for e in result.exceptions)  # Thu/Fri are the future


def test_every_exception_is_grounded(result):
    for e in result.exceptions:
        assert e.severity in {"low", "medium", "high"}
        assert e.summary and e.details and e.evidence, e.exception_id
        if e.policy_id not in {"P2", "P3", "P4", "P7"}:  # P3/P4/P7 fixes: a later phase
            assert e.fix_options, e.exception_id
        assert "fraud" not in e.summary.lower()
    assert len({e.exception_id for e in result.exceptions}) == len(result.exceptions)


def test_dev_forecast_leaves_out_his_sick_thursday(dataset):
    """Leave-aware P5: with a tiny limit, Dev's week shows Thu as leave (0 h), Fri as 8 h."""
    tiny = policy_with({("P5", "weekly_overtime_after_hours"): 1})
    out = run_engine(dataset, tiny, AS_OF, ["P5"])
    (dev,) = [e for e in out.exceptions if e.employee_id == "E007"]
    assert dev.details["scheduled_remaining_hours"] == 8
    days = {d["date"]: d for d in dev.details["days"]}
    assert days["2026-04-16"]["hours"] == 0
    assert days["2026-04-16"]["source"] == "full-day sick leave (pending)"


def test_json_output_round_trips_with_mixed_evidence(result):
    data = json.loads(result.model_dump_json())
    assert EngineResult.model_validate(data) == result


def test_cli_prints_all_exception_types_together(capsys):
    detect.main(["--data-dir", str(DATA_DIR), "--as-of", DEFAULT_AS_OF])
    out = capsys.readouterr().out
    assert "E007 Dev Malhotra" in out and "applied 3, balance 1" in out
    assert "3 sick days in a row" in out  # Dev: certificate
    assert "on a full-day casual leave day (approved)" in out  # Karan
    assert "Worked 10:00-14:00 (4 h) on Ambedkar Jayanti, not scheduled" in out  # Sana
    assert "Half-day casual leave (approved), but 8.03 h worked" in out  # Farah
    assert "17 exception(s): 16 open, 1 auto-resolved." in out
    assert "By policy: P1 1, P2 1, P3 3, P4 1, P5 1, P7 1, P8 1, P9 1, P10 1" in out


def test_cli_policy_filter_rejects_unknown_ids(capsys):
    with pytest.raises(SystemExit) as exc:
        detect.main(["--data-dir", str(DATA_DIR), "--policy", "P99"])
    assert exc.value.code == 2
    assert "P99" in capsys.readouterr().err
