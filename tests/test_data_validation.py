from pathlib import Path

import pytest

from attendflow.data import DataValidationError, load_dataset
from attendflow.data.schemas import CSV_MODELS
from attendflow.scripts.generate_data import generate
from attendflow.scripts.validate_data import run
from tests.conftest import DATA_DIR, replace_in_file


def errors_for(data_dir: Path) -> list[str]:
    with pytest.raises(DataValidationError) as exc:
        load_dataset(data_dir)
    return exc.value.errors


def test_committed_data_is_valid(dataset):
    assert len(dataset.employees) == 13
    assert len([e for e in dataset.employees if e.role == "worker"]) == 10
    assert dataset.warnings == []


def test_committed_csvs_match_generator(tmp_path):
    """If this fails, someone edited a CSV by hand: change generate_data.py instead."""
    generate(tmp_path)
    for name in CSV_MODELS:
        assert (tmp_path / name).read_bytes() == (DATA_DIR / name).read_bytes(), name


def test_missing_column(data_copy):
    replace_in_file(
        data_copy / "employees.csv",
        "employee_id,name,role,team,supervisor_id",
        "employee_id,name,role,supervisor_id",
    )
    assert "employees.csv: missing column(s) ['team']" in errors_for(data_copy)


def test_stored_balance_column_is_rejected(data_copy):
    replace_in_file(
        data_copy / "leave_balances.csv",
        "employee_id,leave_type,total_per_year,used",
        "employee_id,leave_type,total_per_year,used,balance",
    )
    assert "leave_balances.csv: unexpected column(s) ['balance']" in errors_for(data_copy)


def test_missing_file(data_copy):
    (data_copy / "holidays.csv").unlink()
    assert "holidays.csv: file is missing" in errors_for(data_copy)


def test_unknown_employee_id(data_copy):
    replace_in_file(data_copy / "timecards.csv", "P0001,E002", "P0001,E999")
    assert "timecards.csv: unknown employee_id E999" in errors_for(data_copy)


def test_unknown_supervisor(data_copy):
    replace_in_file(data_copy / "employees.csv", "worker,Inbound,E101", "worker,Inbound,E555")
    assert any("unknown supervisor_id E555" in e for e in errors_for(data_copy))


@pytest.mark.parametrize("bad", ["2026-02-30", "13/04/2026", "2026-4-13", ""])
def test_bad_dates(data_copy, bad):
    replace_in_file(data_copy / "schedule.csv", "E001,2026-04-13,", f"E001,{bad},")
    errors = errors_for(data_copy)
    assert any(e.startswith("schedule.csv line") and ": date:" in e for e in errors), errors


@pytest.mark.parametrize("bad", ["2026-04-13T07:00:00+05:30", "2026-04-13 07:00", "07:00"])
def test_bad_or_timezone_timestamps(data_copy, bad):
    replace_in_file(data_copy / "timecards.csv", "2026-04-13T07:00:00", bad)
    assert any(": timestamp:" in e for e in errors_for(data_copy))


def test_bad_enum_value(data_copy):
    replace_in_file(data_copy / "timecards.csv", ",in,device,", ",clock_in,device,")
    assert any(": type:" in e for e in errors_for(data_copy))


def test_duplicate_punch_id(data_copy):
    replace_in_file(data_copy / "timecards.csv", "P0002,", "P0001,")
    assert "timecards.csv: duplicate punch_id P0001" in errors_for(data_copy)


def test_zero_length_shift(data_copy):
    replace_in_file(
        data_copy / "schedule.csv", "E001,2026-04-13,09:00,18:00", "E001,2026-04-13,09:00,09:00"
    )
    assert any("must differ" in e for e in errors_for(data_copy))


def test_all_errors_reported_together(data_copy):
    replace_in_file(data_copy / "timecards.csv", "P0001,E002", "P0001,E999")
    replace_in_file(data_copy / "schedule.csv", "E001,2026-04-13,", "E001,2026-02-30,")
    assert len(errors_for(data_copy)) >= 2


def test_overused_balance_is_a_warning_not_an_error(data_copy):
    replace_in_file(data_copy / "leave_balances.csv", "E007,sick,12,11", "E007,sick,12,14")
    ds = load_dataset(data_copy)
    assert ds.warnings == ["leave_balances.csv: E007 sick used 14.0 > total 12.0"]


def test_validate_cli_exit_codes(data_copy):
    assert run(data_copy) == 0
    replace_in_file(data_copy / "timecards.csv", "P0001,E002", "P0001,E999")
    assert run(data_copy) == 1
