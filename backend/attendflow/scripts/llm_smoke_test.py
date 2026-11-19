"""Send one prompt to the configured LLM and print the reply (Phase 0 connectivity check)."""

from __future__ import annotations

import argparse
import sys

from attendflow.config import get_settings
from attendflow.llm import LLMError, chat_once, list_models

DEFAULT_PROMPT = (
    "A warehouse worker clocked in at 09:00 for a 09:00-18:00 shift but has no clock-out. "
    "In two short sentences, explain to their supervisor why this matters before payroll."
)
SYSTEM = "You are a concise assistant for a time and attendance team. Plain language only."


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument(
        "--list-models", action="store_true", help="also check the model is offered"
    )
    args = parser.parse_args()
    # Windows consoles default to cp1252; model replies often contain Unicode punctuation.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    s = get_settings()
    print(f"endpoint : {s.llm_base_url}")
    print(f"model    : {s.llm_model}")
    print(f"api key  : {'set' if s.llm_api_key else 'MISSING'}")  # never print the key itself

    try:
        if args.list_models:
            models = list_models(s)
            found = s.llm_model in models
            print(f"model listed by provider: {'yes' if found else 'NO'} ({len(models)} models)")
            if not found:
                print("available: " + ", ".join(models))
                sys.exit(1)
        print(f"\nprompt   : {args.prompt}\n")
        reply = chat_once(s, args.prompt, system=SYSTEM)
    except LLMError as exc:
        print(f"\nLLM call FAILED: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"reply    : {reply.text}\n")
    print(
        f"served by {reply.model} in {reply.latency_ms} ms "
        f"(tokens in={reply.prompt_tokens}, out={reply.completion_tokens})"
    )


if __name__ == "__main__":
    main()
