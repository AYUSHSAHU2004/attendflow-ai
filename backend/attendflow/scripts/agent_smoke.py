"""Investigate one stored exception using the configured model and dev database."""

import argparse
import json
import sys

from sqlalchemy import select

from attendflow.agent.structured import investigate
from attendflow.clock import FixedClock
from attendflow.config import get_settings
from attendflow.db.models import ToolCallRow
from attendflow.db.session import make_engine, make_session_factory
from attendflow.errors import NotFoundError


def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exception_id")
    parser.add_argument(
        "--fallback-only", action="store_true", help="build a template without an LLM"
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    engine = make_engine(settings.database_url)
    sessions = make_session_factory(engine)
    try:
        result = investigate(
            args.exception_id,
            settings,
            sessions,
            FixedClock(settings.as_of),
            fallback_only=args.fallback_only,
        )
        with sessions() as session:
            calls = list(
                session.scalars(
                    select(ToolCallRow)
                    .where(ToolCallRow.run_id == result.run_id)
                    .order_by(ToolCallRow.id)
                )
            )
    except NotFoundError as exc:
        parser.exit(1, f"{exc}\n")
    finally:
        engine.dispose()

    print(f"Investigation {result.run_id} for {args.exception_id}")
    for call in calls:
        outcome = "ok" if call.ok else "error"
        print(f"Step {call.step_no} · {call.tool_name} [{outcome}, {call.duration_ms:g} ms]")
        print(f"  Input:  {json.dumps(call.input, ensure_ascii=False)}")
        print(f"  Output: {json.dumps(call.output, ensure_ascii=False)}")
    print(result.case.model_dump_json(indent=2))
    print(f"Result: {result.reason} ({result.case.duration_ms:.0f} ms)")
    if result.case.fallback and not args.fallback_only:
        raise SystemExit(1)
