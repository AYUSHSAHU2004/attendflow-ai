"""Call one read-only agent tool from the terminal, exactly as the agent will.

Examples:
  attendflow-tools list
  attendflow-tools get_punches employee_id=E001 date=2026-04-14
  attendflow-tools get_policy policy_id=P3
  attendflow-tools run_checks "{\"employee_id\": \"E001\", \"date\": \"2026-04-14\",
      \"proposed_change\": {\"action\": \"set_clock_out\",
      \"params\": {\"timestamp\": \"2026-04-14T19:30\"}}}"

Reads the database (DATABASE_URL, read-only) by default; --csv reads data/*.csv instead.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from attendflow.config import get_settings
from attendflow.data import load_dataset
from attendflow.policy import load_policy
from attendflow.policy.models import load_policy_text
from attendflow.tools import TOOLS, ToolRunner, openai_tools


def parse_arguments(parts: list[str]) -> dict[str, Any] | str:
    """One JSON object, or key=value pairs (values stay strings)."""
    if len(parts) == 1 and parts[0].lstrip().startswith("{"):
        return parts[0]
    out: dict[str, Any] = {}
    for part in parts:
        key, sep, value = part.partition("=")
        if not sep:
            raise SystemExit(f"expected key=value or one JSON object, got {part!r}")
        out[key] = value
    return out


def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("tool", help="a tool name, 'list', or 'schema'")
    parser.add_argument("arguments", nargs="*", help="key=value pairs or one JSON object")
    parser.add_argument("--csv", action="store_true", help="read data/*.csv, not the database")
    args = parser.parse_args(argv)

    if args.tool == "list":
        for t in TOOLS.values():
            print(f"{t.name:18} {t.description}")
        return
    if args.tool == "schema":
        print(json.dumps(openai_tools(), indent=2))
        return

    settings = get_settings()
    policy = load_policy(settings.data_dir / "policy.json")
    text = load_policy_text(settings.data_dir / "policy.md")
    if args.csv:
        data = load_dataset(Path(settings.data_dir))
        runner = ToolRunner(lambda: data, policy, text, settings.as_of)
    else:
        from attendflow.db.session import make_engine, make_session_factory

        factory = make_session_factory(make_engine(settings.database_url))
        runner = ToolRunner.for_database(factory, policy, text, settings.as_of)
    result = runner.run(args.tool, parse_arguments(args.arguments))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"({len(json.dumps(result))} characters)", file=sys.stderr)
    if not result.get("ok"):
        raise SystemExit(1)
