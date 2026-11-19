"""Load all CSV files, validate every row, then run cross-file checks.

All problems are collected and raised together in one DataValidationError, so a bad
file shows every issue at once instead of one per run.
"""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from attendflow.data.schemas import (
    CSV_MODELS,
    CsvRow,
    Employee,
    Holiday,
    LeaveBalance,
    LeaveRecord,
    Punch,
    ScheduleRow,
    columns_for,
)


class DataValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"{len(errors)} data error(s):\n" + "\n".join(f"  - {e}" for e in errors))


@dataclass
class Dataset:
    employees: list[Employee]
    punches: list[Punch]
    schedule: list[ScheduleRow]
    leave_records: list[LeaveRecord]
    leave_balances: list[LeaveBalance]
    holidays: list[Holiday]
    warnings: list[str] = field(default_factory=list)

    @property
    def employees_by_id(self) -> dict[str, Employee]:
        return {e.employee_id: e for e in self.employees}


def _read_csv(path: Path, model: type[CsvRow], errors: list[str]) -> list[CsvRow]:
    name = path.name
    if not path.exists():
        errors.append(f"{name}: file is missing")
        return []

    # utf-8-sig strips the byte-order mark Excel adds when saving CSVs.
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = [h.strip() for h in (reader.fieldnames or [])]
        expected = columns_for(model)
        missing = [c for c in expected if c not in header]
        extra = [c for c in header if c not in expected]
        if missing:
            errors.append(f"{name}: missing column(s) {missing}")
        if extra:
            errors.append(f"{name}: unexpected column(s) {extra}")
        if missing or extra:
            return []

        rows: list[CsvRow] = []
        for line_no, raw in enumerate(reader, start=2):  # line 1 is the header
            values = {k.strip(): (v or "").strip() for k, v in raw.items() if k is not None}
            if None in raw:
                errors.append(f"{name} line {line_no}: more values than columns")
                continue
            try:
                rows.append(model.model_validate(values))
            except ValidationError as exc:
                for err in exc.errors():
                    col = ".".join(str(p) for p in err["loc"]) or "row"
                    errors.append(f"{name} line {line_no}: {col}: {err['msg']}")
        return rows


def _duplicates(keys: list) -> list:
    return [k for k, n in Counter(keys).items() if n > 1]


def _cross_checks(ds: Dataset, errors: list[str]) -> None:
    emp = ds.employees_by_id

    for dup in _duplicates([e.employee_id for e in ds.employees]):
        errors.append(f"employees.csv: duplicate employee_id {dup}")

    for e in ds.employees:
        if e.role == "worker" and e.supervisor_id is None:
            errors.append(f"employees.csv: worker {e.employee_id} has no supervisor_id")
        if e.supervisor_id is not None:
            sup = emp.get(e.supervisor_id)
            if sup is None:
                errors.append(
                    f"employees.csv: {e.employee_id} has unknown supervisor_id {e.supervisor_id}"
                )
            elif sup.role != "supervisor":
                errors.append(
                    f"employees.csv: {e.employee_id}'s supervisor {sup.employee_id} "
                    f"has role {sup.role!r}, expected 'supervisor'"
                )

    referencing = {
        "timecards.csv": ds.punches,
        "schedule.csv": ds.schedule,
        "leave_records.csv": ds.leave_records,
        "leave_balances.csv": ds.leave_balances,
    }
    for file_name, rows in referencing.items():
        unknown = sorted({r.employee_id for r in rows} - emp.keys())
        for eid in unknown:
            errors.append(f"{file_name}: unknown employee_id {eid}")

    for dup in _duplicates([p.punch_id for p in ds.punches]):
        errors.append(f"timecards.csv: duplicate punch_id {dup}")
    for dup in _duplicates([(s.employee_id, s.date) for s in ds.schedule]):
        errors.append(f"schedule.csv: more than one shift for {dup[0]} on {dup[1]}")
    for dup in _duplicates([(r.employee_id, r.date) for r in ds.leave_records]):
        errors.append(f"leave_records.csv: more than one leave row for {dup[0]} on {dup[1]}")
    for dup in _duplicates([(b.employee_id, b.leave_type) for b in ds.leave_balances]):
        errors.append(f"leave_balances.csv: duplicate balance row for {dup[0]} / {dup[1]}")
    for dup in _duplicates([h.date for h in ds.holidays]):
        errors.append(f"holidays.csv: duplicate holiday date {dup}")

    balance_keys = {(b.employee_id, b.leave_type) for b in ds.leave_balances}
    for r in ds.leave_records:
        if (r.employee_id, r.leave_type) not in balance_keys:
            errors.append(
                f"leave_records.csv: {r.employee_id} has {r.leave_type} leave on {r.date} "
                f"but no matching row in leave_balances.csv"
            )

    # Not an error: an over-used balance is real-world data the agent should surface.
    for b in ds.leave_balances:
        if b.used > b.total_per_year:
            ds.warnings.append(
                f"leave_balances.csv: {b.employee_id} {b.leave_type} used {b.used} "
                f"> total {b.total_per_year}"
            )


def load_dataset(data_dir: Path) -> Dataset:
    """Load and validate every CSV in data_dir. Raises DataValidationError on any problem."""
    errors: list[str] = []
    rows = {name: _read_csv(data_dir / name, model, errors) for name, model in CSV_MODELS.items()}
    ds = Dataset(
        employees=rows["employees.csv"],  # type: ignore[arg-type]
        punches=rows["timecards.csv"],  # type: ignore[arg-type]
        schedule=rows["schedule.csv"],  # type: ignore[arg-type]
        leave_records=rows["leave_records.csv"],  # type: ignore[arg-type]
        leave_balances=rows["leave_balances.csv"],  # type: ignore[arg-type]
        holidays=rows["holidays.csv"],  # type: ignore[arg-type]
    )
    _cross_checks(ds, errors)
    if errors:
        raise DataValidationError(errors)
    return ds
