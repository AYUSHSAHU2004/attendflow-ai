"""The briefing draft, its grounding and claim checks, and the deterministic template.

Every check is plain code over the facts packet. A draft passes only when:

- it is plain text in the fixed JSON shape (headline, 3-5 bullets in fixed sections, team
  lines for teams in the packet);
- every case ID exists, is in the reader's scope and belongs to the bullet's section;
- every employee ID and policy ID is in the packet; no name outside the scope appears, and
  no capitalised word that the packet does not contain (an invented name) mid-sentence;
- every number is in the packet, is the length of a list in it, or is the day, month or
  year of one of its dates (number words two to twenty count as numbers);
- it makes no promise about the future and claims no action the packet does not show,
  and (outside "handled on its own") never says that approval can be skipped;
- every status phrase (awaiting supervisor, awaiting the worker, open, escalated / with
  payroll, resolved, closed, rejected, approved) tied to a case ID matches that case's
  status in the packet. A phrase belongs to the nearest group of case IDs in its sentence
  ("A and B awaiting supervisor" covers both); "open" means any active status; a negated
  phrase ("not escalated") is not checked;
- it never says "no pending", "nothing waiting", "no open cases", "all clear" (or the
  like) for the headline, a section or a team whose count in the packet is above 0.

Failure messages are built by code from validated tokens (a number, a case ID) or fixed
words. They never quote model text, so they are safe to store and to send back to the
model in the one correction request.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from attendflow.agent.case import _BYPASS, numeric_tokens
from attendflow.briefing.facts import SECTIONS, section_case_ids

Section = Literal["needs_decision", "handled_on_its_own", "blocking_payroll", "watch"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class Bullet(_Model):
    section: Section
    text: str = Field(min_length=1, max_length=220)
    case_ids: list[str] = Field(default_factory=list, max_length=6)


class TeamLine(_Model):
    team: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=1, max_length=220)


class BriefingDraft(_Model):
    headline: str = Field(min_length=1, max_length=120)
    bullets: list[Bullet] = Field(min_length=3, max_length=5)
    team_lines: list[TeamLine] = Field(default_factory=list, max_length=3)


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
_NUMBER_WORD = re.compile(r"\b(" + "|".join(NUMBER_WORDS) + r")\b", re.IGNORECASE)
FUTURE = re.compile(
    r"\b(?:will|won't|shall|going to|gonna|about to|plans? to|planned to|intends? to|"
    r"soon|tomorrow|(?:i|we|it|they|you|he|she)'ll)\b",
    re.IGNORECASE,
)
# Past-tense action claims -> the packet facts that must back them (any one is enough).
ACTION_CLAIMS: list[tuple[re.Pattern[str], tuple[str, ...]]] = [
    (re.compile(r"\bapprov(?:ed|al was|als were)\b", re.I), ("approvals",)),
    (re.compile(r"\brejected\b", re.I), ("rejections",)),
    (
        re.compile(r"\bauto-?resolved\b|\b(?:resolved|closed|fixed) automatically\b", re.I),
        ("auto",),
    ),
    (re.compile(r"\bresolved\b", re.I), ("resolved", "auto")),
    (re.compile(r"\b(?:undone|undid)\b", re.I), ("undone",)),
    (re.compile(r"\binvestigated\b", re.I), ("investigated",)),
    (re.compile(r"\b(?:messaged|asked)\b|\bsent (?:a )?(?:message|question)", re.I), ("messages",)),
    (re.compile(r"\breminded\b|\breminders? (?:was|were) sent\b", re.I), ("reminders",)),
    (re.compile(r"\bescalated\b", re.I), ("escalated",)),
    (re.compile(r"\bsigned off\b|\bsign-off was\b", re.I), ("signed_off",)),
    (re.compile(r"\b(?:applied|corrected)\b", re.I), ("approvals", "auto")),
]
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
_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")
_SENTENCE_BREAK = re.compile(r"(?:^|[.!?:;(—–]|\s-)\s*[\"'“‘]?$")
_NOT_PLAIN = re.compile(r"[<>`\[\]{}\r\n\x00-\x1f\x7f]")


# ------------------------------------------------------------------ normalising


def _json_text(text: str) -> str:
    text = text.strip()
    for _ in range(2):
        if match := re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.I | re.S):
            text = match[1].strip()
    return text


def _clean(value: Any) -> Any:
    """Harmless formatting only: markdown emphasis, a leading list marker, spacing."""
    if not isinstance(value, str):
        return value
    value = re.sub(r"\*\*|__", "", value)
    value = re.sub(r"^\s*(?:[-*•]\s+)", "", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_draft(text: str) -> BriefingDraft:
    """JSON -> BriefingDraft after harmless normalising. Raises ValueError or
    ValidationError (the schema itself is never loosened)."""
    data = json.loads(_json_text(text))
    if not isinstance(data, dict):
        raise ValueError("the reply is not a JSON object")
    if isinstance(data.get("headline"), str):
        data["headline"] = _clean(data["headline"])
    for key in ("bullets", "team_lines"):
        for item in data.get(key) or []:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                item["text"] = _clean(item["text"])
            if isinstance(item, dict) and isinstance(item.get("case_ids"), list):
                item["case_ids"] = [_clean(c) for c in item["case_ids"]]
    return BriefingDraft.model_validate(data)


FIELDS = {"headline", "bullets", "team_lines", "section", "text", "case_ids", "team"}


def schema_failure(exc: Exception) -> Failure:
    """Names only the draft's known fields: an unknown key the model invented is never
    echoed (it is model text)."""
    if isinstance(exc, ValidationError):
        fields = sorted(
            {
                ".".join(
                    str(part) if part in FIELDS else "unexpected field"
                    for part in err["loc"]
                    if not isinstance(part, int)
                )
                or "reply"
                for err in exc.errors(include_input=False, include_context=False, include_url=False)
            }
        )
        return Failure(
            code="schema",
            message="the JSON does not match the required shape (fields: "
            + ", ".join(fields[:5])
            + ")",
        )
    return Failure(code="invalid_json", message="the reply is not one valid JSON object")


# ------------------------------------------------------------------ allowed facts


def _walk(value: Any):
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        yield value
        for item in value:
            yield from _walk(item)
    else:
        yield value


def _strip_ids(text: str) -> str:
    text = CASE_ID.sub(" ", text)
    text = EMPLOYEE_ID.sub(" ", text)
    return POLICY_ID.sub(" ", text)


def allowed_numbers(packet: dict[str, Any]) -> set[str]:
    allowed: set[str] = set()
    for value in _walk(packet):
        if isinstance(value, list):
            allowed.add(str(len(value)))
        elif isinstance(value, bool) or value is None:
            continue
        elif isinstance(value, int | float):
            allowed |= numeric_tokens(str(value))
        elif isinstance(value, str):
            allowed |= numeric_tokens(_strip_ids(value))
            for found in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", value):
                day = date.fromisoformat(found)
                allowed |= {str(day.day), str(day.month), str(day.year)}
    return allowed


def _vocabulary(packet: dict[str, Any]) -> set[str]:
    words = {
        w.casefold().rstrip("'’s")
        for value in _walk(packet)
        if isinstance(value, str)
        for w in _WORD.findall(value)
    }
    words |= {w.casefold() for title in SECTIONS.values() for w in _WORD.findall(title)}
    return words | ALWAYS_ALLOWED


def _claims(packet: dict[str, Any]) -> dict[str, bool]:
    h, today = packet["handled_on_its_own"], packet["handled_on_its_own"]["today"]
    counts = packet["counts"]
    return {
        "approvals": bool(today.get("human_approvals") or today.get("decided_without_worker")),
        "rejections": bool(today.get("human_rejections") or counts.get("rejected")),
        "auto": bool(h["resolved_without_human"] or today.get("auto_resolved")),
        "resolved": bool(counts.get("resolved")),
        "undone": bool(h["undone"] or today.get("auto_resolves_undone")),
        "investigated": bool(today.get("investigated")),
        "messages": bool(today.get("messages_sent") or today.get("reminders_sent")),
        "reminders": bool(today.get("reminders_sent")),
        "escalated": bool(counts.get("escalated") or today.get("escalated_by_silence")),
        "signed_off": bool(packet["blocking_payroll"]["signed_off"]),
    }


# ------------------------------------------------------------------ checks


def _numbers_in(text: str) -> set[str]:
    text = _NUMBER_WORD.sub(lambda m: NUMBER_WORDS[m[1].lower()], _strip_ids(text))
    return numeric_tokens(text)


def _capitalised_mid_sentence(text: str) -> list[str]:
    out = []
    plain = _strip_ids(text)
    for match in _WORD.finditer(plain):
        word = match[0]
        if not word[0].isupper() or word.isupper():
            continue  # lower case, or an acronym such as "ID"
        if _SENTENCE_BREAK.search(plain[: match.start()]):
            continue
        out.append(word)
    return out


def check_draft(
    draft: BriefingDraft,
    packet: dict[str, Any],
    *,
    known_case_ids: set[str],
    all_people: dict[str, str],
) -> list[Failure]:
    """All failures, in a stable order (empty = the draft is grounded)."""
    failures: list[Failure] = []
    seen: set[tuple[str, str]] = set()

    def fail(code: str, message: str) -> None:
        if (code, message) not in seen:
            seen.add((code, message))
            failures.append(Failure(code=code, message=message))

    sections = section_case_ids(packet)
    in_scope = set().union(*sections.values())
    people = packet["people"]
    numbers = allowed_numbers(packet)
    vocabulary = _vocabulary(packet) | {
        w.casefold() for name in people.values() for w in _WORD.findall(name)
    }
    outside = {eid: name for eid, name in all_people.items() if eid not in people}
    claims = _claims(packet)
    teams = {t["team"] for t in packet["teams"]}

    def check_ids(ids: list[str], allowed: set[str], where: str) -> None:
        for cid in ids:
            if not CASE_ID.fullmatch(cid) or cid not in known_case_ids:
                fail("unknown_case_id", f"{where} cites a case ID that does not exist")
            elif cid not in in_scope:
                fail("case_id_not_in_facts", f"case ID {cid} is not in the facts for this reader")
            elif cid not in allowed:
                fail("case_id_wrong_section", f"case ID {cid} does not belong to {where}")

    def check_text(text: str, where: str, *, section: str | None) -> None:
        if _NOT_PLAIN.search(text):
            fail("plain_text", f"{where} must be plain text on one line without markup")
        for eid in EMPLOYEE_ID.findall(text):
            if eid not in people:
                fail("employee_id_not_in_facts", f"employee ID {eid} is not in the facts")
        for pid in POLICY_ID.findall(_strip_ids_keep_policy(text)):
            if pid not in packet["policies"]:
                fail("policy_id_not_in_facts", f"policy {pid} is not in the facts")
        for token in sorted(_numbers_in(text) - numbers):
            fail("ungrounded_number", f"the number {token} in {where} is not in the facts")
        for name in outside.values():
            first = name.split()[0]
            if re.search(rf"\b(?:{re.escape(name)}|{re.escape(first)})\b", text):
                fail("name_outside_scope", f"{where} names a person outside this briefing")
        for word in _capitalised_mid_sentence(text):
            folded = word.casefold()
            if folded.rstrip("'’s") not in vocabulary and folded not in vocabulary:
                fail("unknown_name", f"{where} uses a name or proper noun not in the facts")
        if FUTURE.search(text):
            fail("future_claim", f"{where} uses future tense or a promise; use present or past")
        for pattern, keys in ACTION_CLAIMS:
            if pattern.search(text) and not any(claims[k] for k in keys):
                fail("unsupported_action", f"{where} claims an action the facts do not show")
        if section != "handled_on_its_own" and _BYPASS.search(text):
            fail("approval_bypass", f"{where} says an approval or confirmation can be skipped")

    check_text(draft.headline, "the headline", section=None)
    check_ids(CASE_ID.findall(draft.headline), in_scope, "the headline")
    for n, bullet in enumerate(draft.bullets, start=1):
        where = f"bullet {n} ({bullet.section})"
        allowed = sections[bullet.section]
        check_ids(bullet.case_ids, allowed, where)
        text_ids = CASE_ID.findall(bullet.text)
        check_ids(text_ids, allowed, where)
        for cid in text_ids:
            if cid in allowed and cid not in bullet.case_ids:
                fail("case_id_not_cited", f"{where} mentions {cid} without listing it in case_ids")
        if allowed and not bullet.case_ids:
            fail("missing_case_ids", f"{where} must cite at least one case ID from its section")
        check_text(bullet.text, where, section=bullet.section)
    named = [line.team for line in draft.team_lines]
    for n, line in enumerate(draft.team_lines, start=1):
        where = f"team line {n}"
        if line.team not in teams:
            fail("unknown_team", f"{where} names a team that is not in the facts")
        check_ids(CASE_ID.findall(line.text), in_scope, where)
        check_text(line.text, where, section=None)
    if len(named) != len(set(named)):
        fail("duplicate_team", "each team may have one team line only")

    # Status claims about named cases, and "nothing pending" claims (added after the first
    # real-model run, see docs/PROGRESS.md Phase 17).
    statuses = case_statuses(packet)
    texts = [draft.headline, *(b.text for b in draft.bullets), *(t.text for t in draft.team_lines)]
    for text in texts:
        for cid, claimed in status_claims(text):
            actual = statuses.get(cid)
            if actual is not None and actual not in STATUS_PHRASES[claimed][1]:
                fail(
                    "status_mismatch",
                    f"{cid} is {STATUS_WORDS[actual]}, not {STATUS_PHRASES[claimed][0]}",
                )
    counts = packet["counts"]
    if EMPTY_CLAIM.search(draft.headline) and counts["active"] > 0:
        fail(
            "false_empty_claim",
            f"the headline says nothing is pending, but {counts['active']} cases are active",
        )
    section_counts = _section_counts(packet)
    for n, bullet in enumerate(draft.bullets, 1):
        size = section_counts[bullet.section]
        if EMPTY_CLAIM.search(bullet.text) and size > 0:
            fail(
                "false_empty_claim",
                f"bullet {n} says nothing is pending, but the facts list {size} for "
                f"{SECTIONS[bullet.section]}",
            )
    team_active = {t["team"]: t["active"] for t in packet["teams"]}
    for line in draft.team_lines:
        active = team_active.get(line.team, 0)
        if EMPTY_CLAIM.search(line.text) and active > 0:
            fail(
                "false_empty_claim",
                f"the {line.team} team line says nothing is pending, but {line.team} has "
                f"{active} active cases",
            )
    return failures


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
    for value in _walk(packet):
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


def _section_counts(packet: dict[str, Any]) -> dict[str, int]:
    h, b, w = packet["handled_on_its_own"], packet["blocking_payroll"], packet["watch"]
    return {
        "needs_decision": packet["needs_decision"]["total"],
        "handled_on_its_own": h["auto_resolved_total"],
        "blocking_payroll": b["blocking_total"] + b["blocking_without_case"],
        "watch": len(w["overtime_workers"]) + w["no_reply_total"],
    }


def _strip_ids_keep_policy(text: str) -> str:
    return EMPLOYEE_ID.sub(" ", CASE_ID.sub(" ", text))


def correction_prompt(failures: list[Failure]) -> str:
    lines = "; ".join(f.message for f in failures[:4])
    return (
        f"The briefing failed these checks: {lines}. Return the corrected JSON object only, "
        "using only facts from the packet."
    )


# ------------------------------------------------------------------ template


def _num(value: float) -> str:
    return f"{value:g}"


def _cases(n: int) -> str:
    return f"{n} case" if n == 1 else f"{n} cases"


def template_draft(packet: dict[str, Any]) -> BriefingDraft:
    """The deterministic briefing from the same packet (always passes check_draft)."""
    counts, people = packet["counts"], packet["people"]
    needs = packet["needs_decision"]
    handled = packet["handled_on_its_own"]
    pay = packet["blocking_payroll"]
    watch = packet["watch"]
    you = "your"

    need_ids = [c["case_id"] for c in needs["cases"][:3]]
    if needs["total"]:
        verb = "waits" if needs["total"] == 1 else "wait"
        text = (
            f"{_cases(needs['total'])} {verb} for {you} decision, including {', '.join(need_ids)}."
        )
    else:
        text = f"No case is waiting for {you} decision."
    bullets = [Bullet(section="needs_decision", text=text, case_ids=need_ids)]

    auto_ids = [c["case_id"] for c in handled["auto_resolved_cases"][:3]]
    if handled["resolved_without_human"]:
        text = (
            f"Code closed {handled['resolved_without_human']} of {handled['needed_handling']} "
            f"cases without a person ({handled['percent']}%)"
        )
        if handled["undone"]:
            text += f"; a person reversed {handled['undone']}"
        text += f", including {', '.join(auto_ids)}." if auto_ids else "."
    else:
        text = "No case was closed without a person."
    if handled["today"].get("investigated"):
        text += f" The agent investigated {_cases(handled['today']['investigated'])} today."
    bullets.append(Bullet(section="handled_on_its_own", text=text, case_ids=auto_ids))

    block_ids = [c["case_id"] for c in pay["blocking_cases"][:3]]
    week = pay["week_start"]
    if pay["blocking_total"]:
        verb = "blocks" if pay["blocking_total"] == 1 else "block"
        text = (
            f"{_cases(pay['blocking_total'])} {verb} payroll for the week of {week}, "
            f"including {', '.join(block_ids)}."
        )
    elif pay["blocking_without_case"]:
        text = f"Payroll for the week of {week} is blocked by records without a stored case."
    else:
        text = f"Nothing blocks payroll for the week of {week}."
    bullets.append(Bullet(section="blocking_payroll", text=text, case_ids=block_ids))

    parts = []
    for worker in watch["overtime_workers"][:2]:
        name = people.get(worker["employee_id"], worker["employee_id"])
        parts.append(
            f"{name} has {_num(worker['projected_hours'])} projected hours against the "
            f"{_num(watch['overtime_limit_hours'])} h weekly limit"
        )
    if watch["no_reply_total"]:
        verb = "has" if watch["no_reply_total"] == 1 else "have"
        parts.append(f"{_cases(watch['no_reply_total'])} {verb} no reply from the worker yet")
    watch_ids = [c["case_id"] for c in (watch["overtime_cases"] + watch["no_reply_cases"])[:3]]
    text = ("; ".join(parts) + ".") if parts else "No overtime risk or unanswered question."
    if parts:
        text = text[0].upper() + text[1:]
    bullets.append(Bullet(section="watch", text=text, case_ids=watch_ids))

    active = counts["active"]
    headline = (
        f"{_cases(active)} active, {needs['total']} waiting for {you} decision."
        if active
        else "No active cases."
    )
    team_lines = [
        TeamLine(
            team=t["team"],
            text=f"{t['active']} active, {t['awaiting_worker']} waiting for workers, "
            f"{t['awaiting_supervisor']} waiting for the supervisor.",
        )
        for t in packet["teams"]
    ]
    return BriefingDraft(headline=headline[:120], bullets=bullets, team_lines=team_lines)
