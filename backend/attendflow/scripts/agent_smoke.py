"""Investigate one stored exception using the configured model and dev database."""

import argparse
import json
import sys

from attendflow.agent.loop import run_investigation
from attendflow.errors import NotFoundError


def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exception_id")
    args = parser.parse_args(argv)

    try:
        run = run_investigation(args.exception_id)
    except NotFoundError as exc:
        parser.exit(1, f"{exc}\n")

    print(f"Investigation {run.run_id} for {args.exception_id}")
    for step in run.steps:
        print(f"Step {step.number}")
        for call in step.tool_calls:
            outcome = "ok" if call.ok else "error"
            print(f"  {call.name} [{outcome}, {call.duration_ms:g} ms]")
            print(f"  Input:  {json.dumps(call.arguments, ensure_ascii=False)}")
            print(f"  Output: {json.dumps(call.output, ensure_ascii=False)}")
        if step.text:
            print(f"  {step.text}")
        if step.error:
            print(f"  {step.error}")
    print(f"Stopped: {run.stop_reason} ({run.tool_calls_made} calls, {run.duration_ms:.0f} ms)")
    missing = ", ".join(run.missing_required_tools) or "none"
    print(f"Missing required tools: {missing}")
    if run.stop_reason != "final" or run.missing_required_tools:
        raise SystemExit(1)
