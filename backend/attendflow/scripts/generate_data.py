"""Generate the demo dataset into data/*.csv.

Deterministic: planted cases are written by hand below, and the small random jitter on
"clean" days uses a fixed seed, so running this twice gives byte-identical files.
A test checks that the committed CSVs match this script's output.

Demo week: Mon 13 Apr to Sun 19 Apr 2026. Holiday: Tue 14 Apr (Ambedkar Jayanti).
Demo "now" (as-of): Thu 16 Apr 2026 08:00, so no punches exist after that moment;
schedule rows after it are the forecast. See docs/PLANTED_CASES.md.
"""

from __future__ import annotations

import argparse
import csv
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path

from attendflow.config import get_settings
from attendflow.data.schemas import CSV_MODELS, columns_for

SEED = 42
MON = date(2026, 4, 13)
TUE, WED, THU, FRI = (MON + timedelta(days=i) for i in range(1, 5))

DAY_SHIFT = ("09:00", "18:00")  # 9 h on site, 1 h lunch = 8 h worked

APP = ("MOBILE-APP", "Warehouse 1 - Mobile app (geofenced)")
TEAM_GATE = {
    "Inbound": ("GATE-01", "Warehouse 1 - Inbound Gate"),
    "Outbound": ("GATE-02", "Warehouse 1 - Outbound Gate"),
}

# employee_id, name, role, team, supervisor_id
EMPLOYEES = [
    ("E101", "Ravi Kumar", "supervisor", "Inbound", ""),
    ("E102", "Sunita Rao", "supervisor", "Outbound", ""),
    ("E201", "Priya Sharma", "payroll_admin", "Payroll", ""),
    ("E001", "Amit Verma", "worker", "Inbound", "E101"),
    ("E002", "Meena Iyer", "worker", "Inbound", "E101"),
    ("E003", "Ramesh Patil", "worker", "Outbound", "E102"),
    ("E004", "Neha Gupta", "worker", "Inbound", "E101"),
    ("E005", "Sana Khan", "worker", "Inbound", "E101"),
    ("E006", "Karan Mehta", "worker", "Outbound", "E102"),
    ("E007", "Dev Malhotra", "worker", "Outbound", "E102"),
    ("E008", "Farah Ali", "worker", "Outbound", "E102"),
    ("E009", "Arjun Nair", "worker", "Inbound", "E101"),  # clean control
    ("E010", "Pooja Singh", "worker", "Outbound", "E102"),  # clean control
]
TEAM_OF = {e[0]: e[3] for e in EMPLOYEES}
WORKERS = [e[0] for e in EMPLOYEES if e[2] == "worker"]

HOLIDAYS = [
    ("2026-01-26", "Republic Day", "national"),
    ("2026-04-14", "Ambedkar Jayanti", "national"),
    ("2026-05-01", "Labour Day", "company"),
    ("2026-08-15", "Independence Day", "national"),
    ("2026-10-02", "Gandhi Jayanti", "national"),
    ("2026-12-25", "Christmas", "national"),
]

LEAVE_TOTALS = {"sick": 12, "casual": 12, "earned": 15}
DEFAULT_USED = {"sick": 1, "casual": 2, "earned": 3}
USED_OVERRIDES = {
    ("E007", "sick"): 11,  # Dev: only 1 sick day left
    ("E006", "casual"): 3,
    ("E008", "casual"): 2,
    ("E010", "earned"): 4,
}

PUNCH_ORDER = {"in": 0, "break_start": 1, "break_end": 2, "out": 3}

# Real terminals record seconds. Each worker gets one fixed seconds offset for ALL their
# punches, so durations (hours, breaks, lateness) stay exactly the same, but two workers
# never share a second on the same device (that would be a P17 "same second" conflict).
# Offsets are negative (a few seconds earlier) so no one becomes late by seconds, and
# under 30 s so times shown rounded to the minute still read as planted (08:57, not 08:56).
# Amit and Karan keep :00 (they use different gates), so their planted times stay exact.
SECONDS_OFFSET = {
    "E001": 0,
    "E002": -13,
    "E003": -17,
    "E004": -23,
    "E005": -29,
    "E006": 0,
    "E007": -7,
    "E008": -19,
    "E009": -11,
    "E010": -3,
}


def at(d: date, hhmm: str, next_day: bool = False) -> datetime:
    return datetime.combine(d + timedelta(days=1 if next_day else 0), time.fromisoformat(hhmm))


class PunchLog:
    def __init__(self) -> None:
        self.rows: list[tuple[datetime, str, str, str, str, str]] = []

    def add(self, emp: str, ts: datetime, kind: str, app: bool = False) -> None:
        device, location = APP if app else TEAM_GATE[TEAM_OF[emp]]
        self.rows.append((ts, emp, kind, "app" if app else "device", device, location))

    def shift(self, emp: str, d: date, times: list[tuple[str, str]], app: bool = False) -> None:
        """times: list of (kind, "HH:MM" or "+HH:MM" for next day)."""
        for kind, hhmm in times:
            nxt = hhmm.startswith("+")
            self.add(emp, at(d, hhmm.lstrip("+"), nxt), kind, app)

    def clean_day(self, emp: str, d: date, rng: random.Random, app: bool = False) -> None:
        """A normal 09:00-18:00 day: on time, 1 h lunch, never over 8 h 10 m worked."""
        start = at(d, "09:00") - timedelta(minutes=rng.randint(0, 6))
        brk = at(d, "13:00") + timedelta(minutes=rng.randint(0, 3))
        brk_end = brk + timedelta(minutes=60 + rng.randint(0, 2))
        end = at(d, "18:00") + timedelta(minutes=rng.randint(0, 4))
        for ts, kind in ((start, "in"), (brk, "break_start"), (brk_end, "break_end"), (end, "out")):
            self.add(emp, ts, kind, app)


def build_schedule() -> list[tuple[str, date, str, str]]:
    rows: list[tuple[str, date, str, str]] = []
    standard = [MON, WED, THU, FRI]  # most staff are off on the Tuesday holiday
    for emp in ("E005", "E006", "E007", "E008", "E009", "E010"):
        rows += [(emp, d, *DAY_SHIFT) for d in standard]
    # Amit is on the holiday-duty roster, so he is scheduled Mon-Fri.
    rows += [("E001", d, *DAY_SHIFT) for d in (MON, TUE, WED, THU, FRI)]
    # Meena: three 12 h days (incl. holiday duty) then two 6 h days = 48 h for the week.
    rows += [("E002", d, "07:00", "19:30") for d in (MON, TUE, WED)]
    rows += [("E002", d, "09:00", "15:00") for d in (THU, FRI)]
    # Ramesh: night shifts crossing midnight; off on the holiday night.
    rows += [("E003", d, "22:00", "06:00") for d in standard]
    # Neha: a short 6 h Monday, normal days after.
    rows += [("E004", MON, "09:00", "15:00")]
    rows += [("E004", d, *DAY_SHIFT) for d in (WED, THU, FRI)]
    return rows


def build_punches() -> PunchLog:
    rng = random.Random(SEED)
    log = PunchLog()

    # Amit: normal Mon and Wed; Tue (holiday duty) clocks in at 09:00, never clocks out. -> P1
    log.shift(
        "E001",
        MON,
        [("in", "08:58"), ("break_start", "13:00"), ("break_end", "14:00"), ("out", "17:58")],
    )
    log.shift("E001", TUE, [("in", "09:00"), ("break_start", "13:00"), ("break_end", "14:00")])
    log.shift(
        "E001",
        WED,
        [("in", "08:55"), ("break_start", "13:02"), ("break_end", "14:02"), ("out", "17:55")],
    )

    # Meena: 12 h worked each day Mon-Wed = 36 h; 12 h more scheduled Thu-Fri. -> P5 risk
    for d in (MON, TUE, WED):
        log.shift(
            "E002",
            d,
            [("in", "07:00"), ("break_start", "12:30"), ("break_end", "13:00"), ("out", "19:30")],
        )

    # Ramesh: correct night shifts crossing midnight. -> must NOT be flagged
    for d in (MON, WED):
        log.shift(
            "E003",
            d,
            [
                ("in", "21:58"),
                ("break_start", "+02:00"),
                ("break_end", "+02:30"),
                ("out", "+06:00"),
            ],
        )

    # Neha: Monday 6 h with no break (P4); Wednesday nothing at all (P10).
    log.shift("E004", MON, [("in", "09:00"), ("out", "15:00")])

    # Sana: double tap 2 min apart on Monday (P2); unscheduled holiday work Tue (P14, P8).
    log.shift(
        "E005",
        MON,
        [
            ("in", "08:57"),
            ("in", "08:59"),
            ("break_start", "13:00"),
            ("break_end", "14:00"),
            ("out", "18:00"),
        ],
    )
    log.shift("E005", TUE, [("in", "10:00"), ("out", "14:00")])
    log.clean_day("E005", WED, rng)

    # Karan: 10:30 arrival for a 09:00 shift (P7); works on his approved leave day (P9).
    log.shift(
        "E006",
        MON,
        [("in", "10:30"), ("break_start", "13:30"), ("break_end", "14:00"), ("out", "18:00")],
    )
    log.shift(
        "E006",
        WED,
        [("in", "08:58"), ("break_start", "13:00"), ("break_end", "14:00"), ("out", "18:00")],
    )

    # Dev: on (pending) sick leave Mon, Wed, Thu; no punches.

    # Farah: clean Monday; Wednesday is a half-day leave but she works 09:00-18:00. -> P13
    log.clean_day("E008", MON, rng)
    log.shift(
        "E008",
        WED,
        [("in", "08:59"), ("break_start", "13:00"), ("break_end", "14:00"), ("out", "18:01")],
    )

    # Controls: Arjun (clean, Wed via mobile app); Pooja (clean Mon, approved leave Wed).
    log.clean_day("E009", MON, rng)
    log.clean_day("E009", WED, rng, app=True)
    log.clean_day("E010", MON, rng)
    return log


def build_leave_records() -> list[tuple[str, date, str, str, str, str]]:
    return [
        ("E006", WED, "casual", "full", "approved", "no"),
        ("E007", MON, "sick", "full", "pending", "no"),
        ("E007", WED, "sick", "full", "pending", "no"),
        ("E007", THU, "sick", "full", "pending", "no"),
        ("E008", WED, "casual", "half", "approved", "no"),
        ("E010", WED, "earned", "full", "approved", "no"),
    ]


def _fmt(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _write(path: Path, file_name: str, rows: list[tuple]) -> None:
    columns = columns_for(CSV_MODELS[file_name])
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(columns)
        for row in rows:
            assert len(row) == len(columns), (file_name, row)
            writer.writerow([_fmt(v) for v in row])


def generate(out_dir: Path) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)

    punches = sorted(build_punches().rows, key=lambda r: (r[0], r[1], PUNCH_ORDER[r[2]]))
    # IDs follow the whole-minute order; the seconds offset is applied afterwards, so the
    # punch IDs (cited in docs and tests) do not depend on it.
    punch_rows = [
        (
            f"P{i:04d}",
            emp,
            ts + timedelta(seconds=SECONDS_OFFSET[emp]),
            kind,
            src,
            dev,
            loc,
        )
        for i, (ts, emp, kind, src, dev, loc) in enumerate(punches, start=1)
    ]

    schedule = sorted(build_schedule(), key=lambda r: (r[1], r[0]))
    leave = sorted(build_leave_records(), key=lambda r: (r[1], r[0]))
    balances = [
        (emp, lt, total, USED_OVERRIDES.get((emp, lt), DEFAULT_USED[lt]))
        for emp in sorted(WORKERS)
        for lt, total in LEAVE_TOTALS.items()
    ]

    files = {
        "employees.csv": EMPLOYEES,
        "timecards.csv": punch_rows,
        "schedule.csv": schedule,
        "leave_records.csv": leave,
        "leave_balances.csv": balances,
        "holidays.csv": HOLIDAYS,
    }
    for name, rows in files.items():
        _write(out_dir / name, name, rows)
    return {name: len(rows) for name, rows in files.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=None, help="output folder (default: data/)")
    args = parser.parse_args()
    out = args.out or get_settings().data_dir
    counts = generate(out)
    for name, n in counts.items():
        print(f"wrote {n:3d} rows -> {out / name}")


if __name__ == "__main__":
    main()
