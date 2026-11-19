"""Print the Autonomy Table, or write it into README.md ("Autonomy and guardrails").

attendflow-autonomy                  # print the Markdown table
attendflow-autonomy --write-readme   # replace the generated block in README.md
attendflow-autonomy --check          # exit 1 if README.md is out of date (CI)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from attendflow.activity.autonomy import as_markdown, render_readme

README = Path(__file__).resolve().parents[3] / "README.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write-readme", action="store_true", help="update README.md")
    group.add_argument("--check", action="store_true", help="fail if README.md is stale")
    parser.add_argument("--readme", type=Path, default=README, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    if not (args.write_readme or args.check):
        print(as_markdown(), end="")
        return 0
    current = args.readme.read_text(encoding="utf-8")
    try:
        wanted = render_readme(current)
    except ValueError:
        print(f"{args.readme}: the autonomy-table markers are missing", file=sys.stderr)
        return 1
    if args.check:
        if wanted != current:
            print(
                "README.md is out of date: run `python -m uv run attendflow-autonomy "
                "--write-readme`",
                file=sys.stderr,
            )
            return 1
        print("README.md autonomy table is up to date.")
        return 0
    if wanted != current:
        args.readme.write_text(wanted, encoding="utf-8", newline="\n")
        print(f"Updated {args.readme.name}.")
    else:
        print(f"{args.readme.name} already up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
