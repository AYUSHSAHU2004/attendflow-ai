"""Validate every CSV plus policy.json and policy.md. Exits with code 1 on any error."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from attendflow.config import get_settings
from attendflow.data import DataValidationError, load_dataset
from attendflow.policy import load_policy, load_policy_text
from attendflow.policy.models import POLICY_IDS


def validate_policy_files(data_dir: Path) -> list[str]:
    errors: list[str] = []
    try:
        policy = load_policy(data_dir / "policy.json")
    except FileNotFoundError:
        return ["policy.json: file is missing"]
    except ValidationError as exc:
        return [f"policy.json: {e['loc']}: {e['msg']}" for e in exc.errors()]

    try:
        sections = load_policy_text(data_dir / "policy.md")
    except FileNotFoundError:
        return ["policy.md: file is missing"]

    for pid in POLICY_IDS:
        if pid not in sections:
            errors.append(f"policy.md: no section '## {pid}: ...'")
            continue
        # Every numeric limit in policy.json must also appear in the plain-language text,
        # so the text the agent cites never disagrees with the limit the code enforces.
        for name, value in policy.policies[pid].params.items():
            if isinstance(value, int | float) and not isinstance(value, bool):
                if str(value) not in sections[pid]:
                    errors.append(f"policy.md {pid}: does not mention {name}={value}")
    return errors


def run(data_dir: Path) -> int:
    print(f"Validating data in {data_dir}")
    errors: list[str] = []
    dataset = None
    try:
        dataset = load_dataset(data_dir)
    except DataValidationError as exc:
        errors += exc.errors
    errors += validate_policy_files(data_dir)

    if errors:
        print(f"\nFAILED with {len(errors)} error(s):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    assert dataset is not None
    print(f"  employees      {len(dataset.employees):4d}")
    print(f"  punches        {len(dataset.punches):4d}")
    print(f"  schedule rows  {len(dataset.schedule):4d}")
    print(f"  leave records  {len(dataset.leave_records):4d}")
    print(f"  leave balances {len(dataset.leave_balances):4d}")
    print(f"  holidays       {len(dataset.holidays):4d}")
    print(f"  policies       {len(POLICY_IDS):4d} (policy.json + policy.md in sync)")
    for w in dataset.warnings:
        print(f"  warning: {w}")
    print("\nOK: all data files are valid.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=None)
    args = parser.parse_args()
    sys.exit(run(args.data_dir or get_settings().data_dir))


if __name__ == "__main__":
    main()
