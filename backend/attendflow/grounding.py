"""Shared grounding checks for LLM text built from a code-made facts packet.

Used by the daily briefing (Phase 17, briefing/validate.py) and the employee Q&A
(Phase 20, qa/validate.py). Everything here is plain code: patterns, the numbers a packet
allows, capitalised words that may be invented names, status phrases tied to case IDs and
"nothing pending" claims. Failure messages built from these never quote model text.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from pydantic import BaseModel

from attendflow.agent.case import _BYPASS, numeric_tokens

BYPASS = _BYPASS
__all__ = ["BYPASS", "numeric_tokens"]


class Failure(BaseModel):
    code: str
    message: str


# ------------------------------------------------------------------ patterns

CASE_ID = re.compile(r"\bP\d{1,2}-E\d{3}-\d{4}-\d{2}-\d{2}(?:-[A-Za-z0-9]+)*")
EMPLOYEE_ID = re.compile(r"\bE\d{3}\b")
POLICY_ID = re.compile(r"\bP\d{1,2}\b")
NUMBER_WORDS = {
    word: str(value)
    for value, word in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen "
        "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split()
    )
    if value >= 2  # "one" is too often a pronoun ("no one"); "zero" is "0" below
} | {"zero": "0", "none": "0"}
NUMBER_WORD = re.compile(r"\b(" + "|".join(NUMBER_WORDS) + r")\b", re.IGNORECASE)
FUTURE = re.compile(
    r"\b(?:will|won't|shall|going to|gonna|about to|plans? to|planned to|intends? to|"
    r"soon|tomorrow|(?:i|we|it|they|you|he|she)'ll)\b",
    re.IGNORECASE,
)
MONTHS = (
    "january february march april may june july august september october november december"
).split()
WEEKDAYS = "monday tuesday wednesday thursday friday saturday sunday".split()
ALWAYS_ALLOWED = {
    *MONTHS,
    *(m[:3] for m in MONTHS),
    *WEEKDAYS,
    *(d[:3] for d in WEEKDAYS),
    "attendflow",
    "llm",
}
WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")
SENTENCE_BREAK = re.compile(r"(?:^|[.!?:;(—–]|\s-)\s*[\"'“‘]?$")
NOT_PLAIN = re.compile(r"[<>`\[\]{}\r\n\x00-\x1f\x7f]")


# ------------------------------------------------------------------ normalising


def json_text(text: str) -> str:
    text = text.strip()
    for _ in range(2):
        if match := re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.I | re.S):
            text = match[1].strip()
    return text


def load_json_object(text: str) -> dict[str, Any]:
    data = json.loads(json_text(text))
    if not isinstance(data, dict):
        raise ValueError("the reply is not a JSON object")
    return data


def clean(value: Any) -> Any:
    """Harmless formatting only: markdown emphasis, a leading list marker, spacing."""
    if not isinstance(value, str):
        return value
    value = re.sub(r"\*\*|__", "", value)
    value = re.sub(r"^\s*(?:[-*•]\s+)", "", value)
    return re.sub(r"\s+", " ", value).strip()


# ------------------------------------------------------------------ allowed facts


def walk(value: Any):
    if isinstance(value, dict):
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        yield value
        for item in value:
            yield from walk(item)
    else:
        yield value


def strip_ids(text: str) -> str:
    text = CASE_ID.sub(" ", text)
    text = EMPLOYEE_ID.sub(" ", text)
    return POLICY_ID.sub(" ", text)


def strip_ids_keep_policy(text: str) -> str:
    return EMPLOYEE_ID.sub(" ", CASE_ID.sub(" ", text))


def allowed_numbers(packet: dict[str, Any]) -> set[str]:
    """Every number in the packet, every list length, and the day, month and year of
    every ISO date in it."""
    allowed: set[str] = set()
    for value in walk(packet):
        if isinstance(value, list):
            allowed.add(str(len(value)))
        elif isinstance(value, bool) or value is None:
            continue
        elif isinstance(value, int | float):
            allowed |= numeric_tokens(str(value))
        elif isinstance(value, str):
            allowed |= numeric_tokens(strip_ids(value))
            for found in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", value):
                day = date.fromisoformat(found)
                allowed |= {str(day.day), str(day.month), str(day.year)}
    return allowed


def numbers_in(text: str) -> set[str]:
    text = NUMBER_WORD.sub(lambda m: NUMBER_WORDS[m[1].lower()], strip_ids(text))
    return numeric_tokens(text)


def capitalised_mid_sentence(text: str) -> list[str]:
    out = []
    plain = strip_ids(text)
    for match in WORD.finditer(plain):
        word = match[0]
        if not word[0].isupper() or word.isupper():
            continue  # lower case, or an acronym such as "ID"
        if SENTENCE_BREAK.search(plain[: match.start()]):
            continue
        out.append(word)
    return out


def vocabulary_of(values: Any) -> set[str]:
    """Case-folded words of every string in a packet (possessive endings dropped)."""
    return {
        w.casefold().rstrip("'’s")
        for value in walk(values)
        if isinstance(value, str)
        for w in WORD.findall(value)
    }


# ------------------------------------------------------------------ status and emptiness

ACTIVE = ("open", "awaiting_worker", "awaiting_supervisor", "escalated")
STATUS_WORDS = {
    "open": "open",
    "awaiting_worker": "awaiting the worker",
    "awaiting_supervisor": "awaiting supervisor",
    "escalated": "escalated to payroll",
    "resolved": "resolved",
    "rejected": "rejected",
}
# Phrase key -> (code-built label, statuses that make it true, pattern). "open" in plain
# words means "not closed", so it fits every active status.
STATUS_PHRASES: dict[str, tuple[str, tuple[str, ...], re.Pattern[str]]] = {
    "awaiting_supervisor": (
        "awaiting supervisor",
        ("awaiting_supervisor",),
        re.compile(r"\b(?:awaiting|waiting (?:for|on))\s+(?:the |a |your )?supervisors?\b", re.I),
    ),
    "awaiting_worker": (
        "awaiting the worker",
        ("awaiting_worker",),
        re.compile(
            r"\b(?:awaiting|waiting (?:for|on))\s+(?:the |a |your )?(?:worker|employee)'?s?\b",
            re.I,
        ),
    ),
    "open": ("open", ACTIVE, re.compile(r"\bopen\b", re.I)),
    "escalated": (
        "escalated",
        ("escalated",),
        re.compile(r"\bescalated\b|\bwith payroll\b", re.I),
    ),
    "resolved": ("resolved", ("resolved",), re.compile(r"\bresolved\b", re.I)),
    "closed": ("closed", ("resolved", "rejected"), re.compile(r"\bclosed\b", re.I)),
    "rejected": ("rejected", ("rejected",), re.compile(r"\brejected\b", re.I)),
    "approved": ("approved", ("resolved",), re.compile(r"\bapproved\b", re.I)),
}
_NEGATED = re.compile(r"\b(?:not|no longer|never)\s+(?:yet\s+)?$", re.I)
_LIST_GAP = re.compile(r"^\s*(?:,|and|or|&)?\s*(?:,|and|or|&)?\s*$", re.I)
_SENTENCE = re.compile(r"(?<=[.!?;])\s+")
EMPTY_CLAIM = re.compile(
    r"\bno pending\b|\bnothing (?:is )?(?:pending|waiting|open|outstanding)\b|"
    r"\bno (?:open|active|outstanding) (?:cases?|items?|issues?)\b|\ball clear\b",
    re.I,
)


def case_statuses(packet: dict[str, Any]) -> dict[str, str]:
    """case ID -> status, from every case list in the packet."""
    out: dict[str, str] = {}
    for value in walk(packet):
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and "case_id" in item and "status" in item:
                    out[item["case_id"]] = item["status"]
    return out


def _groups(sentence: str) -> list[tuple[int, int, list[str]]]:
    """Runs of case IDs joined only by commas, "and" or "or": (start, end, ids)."""
    groups: list[tuple[int, int, list[str]]] = []
    for match in CASE_ID.finditer(sentence):
        if groups and _LIST_GAP.match(sentence[groups[-1][1] : match.start()]):
            start, _, ids = groups[-1]
            groups[-1] = (start, match.end(), [*ids, match[0]])
        else:
            groups.append((match.start(), match.end(), [match[0]]))
    return groups


def status_claims(text: str) -> list[tuple[str, str]]:
    """(case ID, phrase key) for each status phrase, tied to the nearest group of case IDs
    in the same sentence (the one before it on a tie). Negated phrases are left alone."""
    claims = []
    for sentence in _SENTENCE.split(text):
        groups = _groups(sentence)
        if not groups:
            continue
        taken: list[tuple[int, int]] = []
        for key, (_, _, pattern) in STATUS_PHRASES.items():
            for match in pattern.finditer(sentence):
                span = (match.start(), match.end())
                if any(s <= span[0] < e for s, e in taken):
                    continue  # "awaiting supervisor" already covered this text
                if _NEGATED.search(sentence[: match.start()]):
                    continue
                taken.append(span)
                nearest = min(groups, key=lambda group, span=span: _distance(group, span))
                for cid in nearest[2]:
                    claims.append((cid, key))
    return claims


def _distance(group: tuple[int, int, list[str]], span: tuple[int, int]) -> tuple[int, int]:
    """Characters between a group of case IDs and a phrase; the group before wins a tie."""
    start, end, _ = group
    before = span[0] - end if end <= span[0] else None
    after = start - span[1] if start >= span[1] else None
    if before is None and after is None:
        return (0, 0)
    if after is None or (before is not None and before <= after):
        return (before or 0, 0)
    return (after, 1)


def status_mismatches(text: str, statuses: dict[str, str]) -> list[Failure]:
    """A status phrase tied to a case ID that contradicts the case's status."""
    out = []
    for cid, claimed in status_claims(text):
        actual = statuses.get(cid)
        if actual is not None and actual not in STATUS_PHRASES[claimed][1]:
            out.append(
                Failure(
                    code="status_mismatch",
                    message=f"{cid} is {STATUS_WORDS[actual]}, not {STATUS_PHRASES[claimed][0]}",
                )
            )
    return out
