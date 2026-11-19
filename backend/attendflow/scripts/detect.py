"""Run the deterministic rule engine on the CSVs and print every timecard exception."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from attendflow.config import get_settings, parse_local_timestamp
from attendflow.data import DataValidationError, load_dataset
from attendflow.engine import EngineResult, run_engine
from attendflow.policy import load_policy


def _status(kind: str, status: str) -> str:
    if status == "auto_resolved":
        return "auto-resolved"
    return "open (risk)" if kind == "risk" else "open"


def format_table(result: EngineResult, names: dict[str, str], show_fixes: bool = False) -> str:
    header = ("Employee", "Date", "Policy", "Severity", "Status", "Numbers")
    rows = [
        (
            f"{e.employee_id} {names.get(e.employee_id, '')}".strip(),
            e.date.strftime("%a %d %b") + (" (week)" if e.policy_id == "P5" else ""),
            e.policy_id,
            e.severity,
            _status(e.kind, e.status),
            e.summary,
        )
        for e in result.exceptions
    ]
    widths = [max(len(str(r[i])) for r in [header, *rows]) for i in range(len(header) - 1)]
    lines = []

    def line(cells: tuple[str, ...]) -> str:
        return "  ".join(c.ljust(w) for c, w in zip(cells[:-1], widths, strict=True)) + (
            "  " + cells[-1]
        )

    lines.append(line(header))
    lines.append(line(tuple("-" * w for w in widths) + ("-" * 7,)))
    for exc, row in zip(result.exceptions, rows, strict=True):
        lines.append(line(row))
        if show_fixes:
            for fix in exc.fix_options:
                lines.append(" " * (sum(widths) + 2 * len(widths)) + f"fix: {fix.label}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--as-of", default=None, help="local time like 2026-04-16T08:00")
    parser.add_argument("--employee", default=None, help="only this employee id, e.g. E002")
    parser.add_argument(
        "--policy", default=None, help="only these policies, comma separated, e.g. P1,P5,P14"
    )
    parser.add_argument("--fixes", action="store_true", help="also print the fix options")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args(argv)

    settings = get_settings()
    data_dir = args.data_dir or settings.data_dir
    as_of = parse_local_timestamp(args.as_of) if args.as_of else settings.as_of
    try:
        dataset = load_dataset(data_dir)
    except DataValidationError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
    policy = load_policy(data_dir / "policy.json")
    selected = [p.strip().upper() for p in args.policy.split(",")] if args.policy else None
    try:
        result = run_engine(dataset, policy, as_of, selected)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        sys.exit(2)
    if args.employee:
        result = result.model_copy(
            update={"exceptions": [e for e in result.exceptions if e.employee_id == args.employee]}
        )

    if args.json:
        print(json.dumps(result.model_dump(mode="json"), indent=2))
        return

    names = {e.employee_id: e.name for e in dataset.employees}
    open_count = sum(1 for e in result.exceptions if e.status == "open")
    print(f"AttendFlow rule engine | as of {as_of:%a %d %b %Y %H:%M} | policy {policy.version}")
    print()
    print(format_table(result, names, show_fixes=args.fixes))
    print()
    print(
        f"{len(result.exceptions)} exception(s): {open_count} open, "
        f"{len(result.exceptions) - open_count} auto-resolved. "
        f"{len(result.shifts)} shifts built, {len(result.voided_punch_ids)} duplicate punch(es) "
        f"voided, {result.ignored_future_punches} punch(es) after as-of ignored."
    )
    counts = Counter(e.policy_id for e in result.exceptions)
    if counts:
        by_policy = ", ".join(
            f"{pid} {n}" for pid, n in sorted(counts.items(), key=lambda kv: int(kv[0][1:]))
        )
        print(f"By policy: {by_policy}")


if __name__ == "__main__":
    main()
