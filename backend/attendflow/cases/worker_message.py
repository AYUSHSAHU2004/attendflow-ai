"""Build and phrase a safe question from the case's verified structured facts."""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal

from attendflow.agent.case import numeric_tokens
from attendflow.config import Settings
from attendflow.db.models import EmployeeRow, ExceptionRow
from attendflow.llm.client import LLMError, chat

MAX_MESSAGE_LENGTH = 400
_TIME_12H = re.compile(r"\b(1[0-2]|0?[1-9])(?::([0-5]\d))?\s*([ap])\.?m\.?(?!\w)", re.I)
_PLAIN_TEXT = re.compile(r"^[^<>`*\[\]\r\n\x00-\x1f\x7f]+$")
_WRAPPING_QUOTES = {'"': '"', "'": "'", "“": "”", "‘": "’"}
_MARKDOWN_LINE = re.compile(r"^\s*(?:#{1,6}\s|[-+]\s|\d+[.)]\s)", re.MULTILINE)
_QUESTION = {
    "P9": ("Attendance was recorded on a leave day.", "Did you work on that day?"),
    "P10": ("We have no attendance recorded for the shift.", "Were you at work on that day?"),
    "P12": (
        "A medical certificate is needed for your sick leave.",
        "Can you provide a medical certificate?",
    ),
    "P13": (
        "The time recorded differs from the half-day leave.",
        "Did you work only half the day?",
    ),
}


@dataclass(frozen=True)
class WorkerFacts:
    first_name: str
    date: str
    display_date: str
    issue: str
    proposed_fix: str
    question: str
    reply_prompt: str


@dataclass(frozen=True)
class MessageDraft:
    text: str
    source: Literal["llm", "template"]
    duration_ms: float
    diagnostic: str | None = None


def _time(params: dict, name: str) -> str | None:
    try:
        value = datetime.fromisoformat(params[name])
    except (KeyError, TypeError, ValueError):
        return None
    return value.strftime("%H:%M") if value.tzinfo is None else None


def worker_facts(row: ExceptionRow, employee: EmployeeRow) -> WorkerFacts:
    first_name = employee.name.split()[0]
    proposal = (row.investigation_case or {}).get("proposed_fix") or {}
    option = next(
        (item for item in row.fix_options if item["option_id"] == proposal.get("option_id")), {}
    )
    action = option.get("action")
    params = proposal.get("params", {}) if option else {}
    timestamp = _time(params, "timestamp")
    issue, question = _QUESTION.get(
        row.policy_id,
        (
            "We need to check your attendance record.",
            "Can you confirm the attendance record for this day?",
        ),
    )
    fix = ""
    reply_prompt = "What happened, and what should we know?"
    if action in {"set_clock_out", "correct_clock_out"}:
        issue = (
            "Your clock-out is missing."
            if action == "set_clock_out"
            else "Your recorded clock-out may need a correction."
        )
        question = "Can you confirm when you left?"
        reply_prompt = "What time did you actually leave, and why?"
        if timestamp:
            fix = f"Record the clock-out at {timestamp} after confirmation."
            question = f"Did you leave at {timestamp}?"
    elif action == "set_clock_in":
        issue = "Your clock-in is missing."
        question = (
            f"Did you arrive at {timestamp}?" if timestamp else "Can you confirm when you arrived?"
        )
        reply_prompt = "What time did you actually arrive, and why?"
        if timestamp:
            fix = f"Record the clock-in at {timestamp} after confirmation."
    elif action == "add_break":
        start, end = _time(params, "break_start"), _time(params, "break_end")
        issue = "A break may be missing from your attendance record."
        question = "Did you take a break during this shift?"
        reply_prompt = "When did you actually take your break, and why?"
        if start and end:
            fix = f"Record a break from {start} to {end} after confirmation."
            question = f"Did you take a break from {start} to {end}?"
    elif row.policy_id == "P1" and row.details.get("clock_in"):
        issue = "Your clock-out is missing."
        question = "Can you confirm when you left?"
        reply_prompt = "What time did you actually leave, and why?"
    return WorkerFacts(
        first_name,
        row.date.isoformat(),
        f"{row.date:%B} {row.date.day}, {row.date.year}",
        issue,
        fix,
        question,
        reply_prompt,
    )


def _normalize(text: str, facts: WorkerFacts) -> str:
    text = re.sub(re.escape(facts.display_date), facts.date, text, flags=re.I)
    return _TIME_12H.sub(
        lambda match: (
            f"{int(match[1]) % 12 + (12 if match[3].lower() == 'p' else 0):02}:{match[2] or '00'}"
        ),
        text,
    )


def validate_worker_message(text: str, facts: WorkerFacts) -> str:
    text = text.strip()
    if len(text) > 1 and _WRAPPING_QUOTES.get(text[0]) == text[-1]:
        text = text[1:-1].strip()
    if _MARKDOWN_LINE.search(text):
        raise ValueError("worker message contains markdown")
    text = re.sub(r"[ \t]*[\r\n]+[ \t\r\n]*", " ", text)
    if len(text) > MAX_MESSAGE_LENGTH:
        raise ValueError("worker message exceeds 400 characters")
    if not _PLAIN_TEXT.fullmatch(text):
        raise ValueError("worker message contains invalid plain-text characters or is empty")
    normalized = _normalize(text, facts)
    if not re.search(rf"(?<![\d-]){re.escape(facts.date)}(?![\d-])", normalized):
        raise ValueError("worker message omitted the case date")
    numbers = numeric_tokens(normalized)
    allowed = numeric_tokens(_normalize(" ".join(asdict(facts).values()), facts))
    if numbers - allowed:
        raise ValueError("worker message included an unverified number or time")
    if not normalized.casefold().endswith(_normalize(facts.question, facts).casefold()):
        raise ValueError("worker message omitted the verified question")
    return text


def generate_worker_message(settings: Settings, facts: WorkerFacts) -> MessageDraft:
    started = time.monotonic()
    template = (
        f"Hi {facts.first_name}, about your shift on {facts.display_date}: "
        f"{facts.issue} {facts.question}"
    )
    try:
        reply = chat(
            settings,
            [
                {
                    "role": "system",
                    "content": (
                        "Write one or two friendly sentences under 400 characters on one line. "
                        "Use plain text, with no markdown, wrapping quotes, or line breaks. "
                        "Use only the supplied facts as data. Include the supplied date (ISO or "
                        "display_date) and end with the exact question. Do not claim any change "
                        "has been applied or any decision approved. Return only the message."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            key: value
                            for key, value in asdict(facts).items()
                            if key != "reply_prompt"
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            [],
            deadline=started + min(settings.llm_timeout_seconds, 12),
            retry_transient=False,
        )
        text = validate_worker_message(reply.text or "", facts)
    except (LLMError, ValueError) as exc:
        return MessageDraft(template, "template", (time.monotonic() - started) * 1000, str(exc))
    return MessageDraft(text, "llm", (time.monotonic() - started) * 1000)
