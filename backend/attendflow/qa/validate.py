"""Phase 20: the answer draft, its grounding checks, the templates and the refusals.

An answer passes only when it is plain text in the fixed JSON shape and:

- every number, date and time is in the facts packet (or the length of a list in it, or
  the day, month or year of one of its dates);
- every case ID and policy ID it names, and every source it cites, is in the packet;
- it names no employee ID but the asker's and no person but the asker and their
  supervisor, and no capitalised word that the packet does not contain;
- it states no pay or salary amount and leaks no prompt, key or diagnostic;
- it makes no promise about the future, never says an approval can be skipped, never says
  that the assistant did something, and claims no approval or fix the packet does not show;
- every status phrase tied to a case ID matches that case's status in the packet, and so
  do plain status words without an ID ("being reviewed by your supervisor" needs a case
  awaiting the supervisor; an open case is flagged and not yet reviewed); it never says
  "nothing pending" (or the like) while the packet lists an active case;
- for a question about one day with more than one visible case, it covers every case by
  case ID or policy ID.

Failure messages are built by code from validated tokens or fixed words, never from model
text. Templates are built from the same packet and pass the same checks (a test runs every
golden question through them).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from attendflow.grounding import (
    ALWAYS_ALLOWED,
    BYPASS,
    CASE_ID,
    EMPLOYEE_ID,
    EMPTY_CLAIM,
    FUTURE,
    NOT_PLAIN,
    POLICY_ID,
    Failure,
    allowed_numbers,
    capitalised_mid_sentence,
    case_statuses,
    clean,
    load_json_object,
    numbers_in,
    status_mismatches,
    strip_ids_keep_policy,
    vocabulary_of,
)
from attendflow.qa.facts import ACTIVE, day_words, packet_json
from attendflow.qa.intents import People

SourceKind = Literal["policy", "case", "leave_balance", "schedule", "punches", "supervisor"]
KIND_KEYS = {
    "leave_balance": "leave_balance",
    "schedule": "schedule",
    "punches": "punches",
    "supervisor": "supervisor",
}
MAX_ANSWER = 500


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class SourceRef(_Model):
    kind: SourceKind
    id: str | None = Field(default=None, max_length=40)


class AnswerDraft(_Model):
    answer: str = Field(min_length=1, max_length=MAX_ANSWER)
    sources: list[SourceRef] = Field(default_factory=list, max_length=6)


FIELDS = {"answer", "sources", "kind", "id"}


def parse_answer(text: str) -> AnswerDraft:
    """JSON -> AnswerDraft after harmless normalising (the schema is never loosened)."""
    data = load_json_object(text)
    if isinstance(data.get("answer"), str):
        data["answer"] = clean(data["answer"])
    return AnswerDraft.model_validate(data)


def schema_failure(exc: Exception) -> Failure:
    """Names only the draft's own fields: an unknown key the model invented is never echoed."""
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


# ------------------------------------------------------------------ checks

PAY_TEXT = re.compile(
    r"[₹$€£]|\b(?:rs\.?|inr|rupees?|salary|salaries|wages?|payslips?|bonus(?:es)?|ctc|"
    r"earnings?|income)\b|\bper\s+hour\s+rate\b|\bhourly\s+rate\b",
    re.IGNORECASE,
)
LEAK = re.compile(
    r"\bsystem\s+prompt\b|\bprompts?\b|\binstructions\b|\bapi[ _-]?keys?\b|\bLLM_\w+|"
    r"\bdiagnostics?\b|\bfacts\s+packet\b|\bJSON\b|\bsecrets?\b",
    re.IGNORECASE,
)
ASSISTANT_ACTION = re.compile(
    r"\b(?:I|we)(?:\s+have|'ve)?\s+(?:approved|changed|fixed|corrected|updated|deleted|added|"
    r"submitted|sent|resolved|closed|edited|removed|cancelled|canceled|applied|granted|"
    r"marked|moved|recorded)\b|\b(?:I|we)\s+(?:can|could)\s+(?:approve|change|fix|correct|"
    r"update|delete|add|submit|resolve|close|edit|remove|cancel|apply|grant|mark|move)\b",
    re.IGNORECASE,
)
DONE_CLAIM = re.compile(
    r"\b(?:has|have)\s+been\s+(?:approved|corrected|fixed|changed|updated|resolved|applied|"
    r"closed|granted)\b|\b(?:was|were)\s+(?:approved|corrected|fixed|changed|updated|applied|"
    r"granted)\b",
    re.IGNORECASE,
)
NO_CASES = re.compile(r"\byou\s+have\s+no\s+(?:attendance\s+)?(?:cases?|issues?|problems?)\b", re.I)
# Inbox words the answer may capitalise ("use the Questions tab").
EXTRA_WORDS = {"questions", "history", "ask", "inbox", "tab", "my"}


def _name_tokens(name: str | None) -> set[str]:
    return {t.casefold() for t in re.findall(r"[A-Za-z]+", name or "") if len(t) > 1}


def check_answer(
    draft: AnswerDraft,
    packet: dict[str, Any],
    people: People,
) -> list[Failure]:
    """All failures, in a stable order (empty = the answer is grounded)."""
    failures: list[Failure] = []
    seen: set[tuple[str, str]] = set()

    def fail(code: str, message: str) -> None:
        if (code, message) not in seen:
            seen.add((code, message))
            failures.append(Failure(code=code, message=message))

    text = draft.answer
    cases = {c["case_id"]: c for c in packet.get("cases", {}).get("items", [])}
    # Policy IDs the facts name anywhere (a policy entry, a case, or a policy's own text).
    policies = set(POLICY_ID.findall(strip_ids_keep_policy(packet_json(packet))))
    own = _name_tokens(people.asker_name)
    boss = _name_tokens(people.supervisor_name)
    vocabulary = vocabulary_of(packet) | ALWAYS_ALLOWED | own | boss | EXTRA_WORDS

    if NOT_PLAIN.search(text):
        fail("plain_text", "the answer must be plain text on one line without markup")
    for cid in CASE_ID.findall(text):
        if cid not in cases:
            fail("case_id_not_in_facts", "the answer names a case ID that is not in the facts")
    for eid in EMPLOYEE_ID.findall(text):
        if eid != people.asker_id:
            fail("other_person", "the answer names another employee ID")
    for pid in POLICY_ID.findall(strip_ids_keep_policy(text)):
        if pid not in policies:
            fail("policy_id_not_in_facts", f"policy {pid} is not in the facts")
    for token in sorted(numbers_in(text) - allowed_numbers(packet)):
        fail("ungrounded_number", f"the number {token} in the answer is not in the facts")
    others = set().union(*(_name_tokens(n) for n in people.others.values())) - own - boss
    for token in sorted(others):
        if re.search(rf"\b{re.escape(token)}\b", text, re.IGNORECASE):
            fail("name_outside_scope", "the answer names a person other than you or the supervisor")
            break
    for word in capitalised_mid_sentence(text):
        folded = word.casefold()
        if folded.rstrip("'’s") not in vocabulary and folded not in vocabulary:
            fail("unknown_name", "the answer uses a name or proper noun not in the facts")
    if PAY_TEXT.search(text):
        fail("pay_amount", "the answer mentions pay or salary; attendance only")
    if LEAK.search(text):
        fail("leak", "the answer mentions the prompt, keys or internal data")
    if FUTURE.search(text):
        fail("future_claim", "the answer uses future tense or a promise; use present or past")
    if BYPASS.search(text):
        fail("approval_bypass", "the answer says an approval or confirmation can be skipped")
    if ASSISTANT_ACTION.search(text):
        fail("assistant_action", "the answer says the assistant changed or can change something")
    if DONE_CLAIM.search(text) and not any(
        c["status"] in {"resolved", "rejected"} for c in cases.values()
    ):
        fail("unsupported_action", "the answer claims an approval or fix the facts do not show")
    for failure in status_mismatches(text, case_statuses(packet)):
        fail(failure.code, failure.message)
    for failure in status_word_failures(text, cases):
        fail(failure.code, failure.message)
    if (failure := completeness_failure(text, packet)) is not None:
        fail(failure.code, failure.message)
    active = sum(1 for c in cases.values() if c["status"] in ACTIVE)
    if active and (EMPTY_CLAIM.search(text) or NO_CASES.search(text)):
        fail(
            "false_empty_claim",
            f"the answer says nothing is pending, but the facts list {active} active cases",
        )
    for ref in draft.sources:
        if ref.kind == "policy":
            ok = ref.id in {p["policy_id"] for p in packet.get("policies", [])} | {
                c["policy_id"] for c in cases.values()
            }
        elif ref.kind == "case":
            ok = ref.id in cases
        else:
            ok = KIND_KEYS[ref.kind] in packet and (
                ref.kind != "supervisor" or bool(packet.get("supervisor"))
            )
        if not ok:
            fail("source_not_in_facts", f"a cited {ref.kind} source is not in the facts")
    return failures


# ------------------------------------------------------------------ status words, coverage

_AUX = r"(?:has\s+been|have\s+been|had\s+been|was|were|is|are|been)"
# Plain-words status phrases, checked even when the sentence names no case ID. Each one is
# true only if a case it may refer to (the sentence's own case IDs, else any case in the
# facts) has one of the listed statuses.
STATUS_TEXT: list[tuple[str, re.Pattern[str], tuple[str, ...]]] = [
    (
        "with the supervisor",
        re.compile(
            r"\b(?:being\s+)?reviewed\s+by\s+(?:your|the|a)\s+supervisor"
            r"|\b(?:awaiting|waiting\s+(?:for|on))\s+(?:your\s+|the\s+|a\s+)?supervisor"
            r"|\b(?:is|are|now|currently|sits?|still)\s+with\s+(?:your|the)\s+supervisor"
            r"|\b(?:your|the)\s+supervisor\s+(?:is|has\s+been)\s+(?:reviewing|checking|"
            r"looking\s+(?:at|into))",
            re.I,
        ),
        ("awaiting_supervisor",),
    ),
    (
        "under review",
        re.compile(r"\bunder\s+review\b|\bbeing\s+(?:reviewed|looked\s+at|checked)\b", re.I),
        ("awaiting_supervisor", "escalated"),
    ),
    (
        "waiting for your answer",
        re.compile(
            r"\b(?:waiting|wait)\s+for\s+your\s+(?:reply|answer|response|confirmation)"
            r"|\bawaiting\s+your\s+(?:reply|answer|response|confirmation)"
            r"|\bneeds?\s+your\s+(?:answer|reply|response|confirmation)",
            re.I,
        ),
        ("awaiting_worker",),
    ),
    (
        "resolved",
        re.compile(
            rf"\b{_AUX}\s+(?:resolved|fixed|corrected|sorted)\b"
            r"|\balready\s+(?:resolved|fixed|corrected)\b",
            re.I,
        ),
        ("resolved",),
    ),
    ("closed", re.compile(rf"\b{_AUX}\s+closed\b", re.I), ("resolved", "rejected")),
    (
        "with payroll",
        re.compile(
            r"\bescalated\b|\b(?:is|are|now|currently|still)\s+with\s+payroll\b"
            r"|\bpayroll\s+is\s+(?:reviewing|checking)",
            re.I,
        ),
        ("escalated",),
    ),
]
_NOT_BEFORE = re.compile(r"\b(?:not|never|no\s+longer)\s+(?:yet\s+)?(?:been\s+|being\s+)?$", re.I)
_SENTENCES = re.compile(r"(?<=[.!?;])\s+")
STATUS_LABELS = {
    "open": "flagged, not yet reviewed",
    "awaiting_worker": "waiting for the worker's answer",
    "awaiting_supervisor": "with the supervisor",
    "escalated": "with payroll",
    "resolved": "resolved",
    "rejected": "closed by payroll",
}


def status_word_failures(text: str, cases: dict[str, dict[str, Any]]) -> list[Failure]:
    """Status words with or without a case ID must match a case's status in the facts.
    The message is code-built: the phrase's label and each case's real status."""
    out: list[Failure] = []
    if not cases:
        return out
    for sentence in _SENTENCES.split(text):
        named = [cases[c] for c in CASE_ID.findall(sentence) if c in cases]
        pool = named or list(cases.values())
        taken: list[tuple[int, int]] = []
        for label, pattern, allowed in STATUS_TEXT:
            for match in pattern.finditer(sentence):
                if any(s < match.end() and match.start() < e for s, e in taken):
                    continue  # the same words already matched a more specific phrase
                taken.append(match.span())
                if _NOT_BEFORE.search(sentence[: match.start()]):
                    continue  # "not yet reviewed by your supervisor", "has not been fixed"
                if not any(c["status"] in allowed for c in pool):
                    actual = "; ".join(
                        f"{c['policy_id']} is {STATUS_LABELS.get(c['status'], c['status'])}"
                        for c in pool[:4]
                    )
                    out.append(
                        Failure(
                            code="status_mismatch",
                            message=f"the answer says a case is {label}, but in the facts {actual}",
                        )
                    )
                break
    return out


def completeness_failure(text: str, packet: dict[str, Any]) -> Failure | None:
    """A question about one day with more than one visible case must cover every case,
    by case ID or policy ID."""
    items = packet.get("cases", {}).get("items", [])
    if not packet.get("asked_day") or len(items) < 2:
        return None
    ids = set(CASE_ID.findall(text))
    policies = set(POLICY_ID.findall(strip_ids_keep_policy(text)))
    if all(c["case_id"] in ids or c["policy_id"] in policies for c in items):
        return None
    listed = ", ".join(c["policy_id"] for c in items)
    return Failure(
        code="incomplete_day",
        message=f"the answer must cover all {len(items)} items on that day ({listed})",
    )


def correction_prompt(failures: list[Failure]) -> str:
    lines = "; ".join(f.message for f in failures[:4])
    return (
        f"The answer failed these checks: {lines}. Return the corrected JSON object only, "
        "using only facts from the packet."
    )


# ------------------------------------------------------------------ templates


def _num(value: float | None) -> str:
    return f"{value or 0:g}"


def _day(iso: str) -> str:
    return day_words(date.fromisoformat(iso))


def _days(n: float) -> str:
    return f"{_num(n)} day" if n == 1 else f"{_num(n)} days"


def _case_line(c: dict[str, Any]) -> str:
    summary = c["summary"].rstrip(".")
    line = f"{c['case_id']} ({c['title']}): {summary}. Status: {c['status_words']}."
    if c.get("outcome"):
        line += f" {c['outcome']}"
    return line


def template_parts(packet: dict[str, Any], intents: list[str]) -> list[str]:
    parts: list[str] = []
    for intent in intents:
        if intent == "leave_balance" and "leave_balance" in packet:
            lines = []
            for b in packet["leave_balance"]["types"]:
                line = (
                    f"{_days(b['days_left'])} of {b['leave_type']} leave left "
                    f"({_num(b['used'])} used of {_num(b['total_per_year'])} this year"
                )
                if b["pending_days"]:
                    line += (
                        f"; {_num(b['pending_days'])} pending, "
                        f"{_num(b['days_left_after_pending'])} after they are decided"
                    )
                lines.append(line + ")")
            none = "I have no leave balance for you."
            parts.append("You have " + "; ".join(lines) + "." if lines else none)
        elif intent == "my_schedule" and "schedule" in packet:
            sched = packet["schedule"]
            shown = []
            for d in sched["days"]:
                text = f"{_day(d['date'])}: " + (f"{d['shift']}" if d["shift"] else "no shift")
                if d.get("holiday"):
                    text += f" ({d['holiday']})"
                if d.get("leave"):
                    text += f" ({d['leave']})"
                shown.append(text)
            if shown:
                parts.append(
                    "Your schedule: "
                    + "; ".join(shown)
                    + f". Planned hours in total: {_num(sched['planned_hours_total'])}."
                )
            else:
                parts.append("You have no scheduled shifts on the days you asked about.")
        elif intent == "my_punches" and "punches" in packet:
            lines = []
            for d in packet["punches"]["days"]:
                text = f"{_day(d['date'])}: clock-in {d['clock_in'] or 'missing'}, " + (
                    f"clock-out {d['clock_out']}" if d["clock_out"] else "no clock-out"
                )
                if d["worked_hours"] is not None:
                    text += f", {_num(d['worked_hours'])} h worked"
                lines.append(text)
            for iso in packet["punches"]["days_without_punches"][:3]:
                lines.append(f"{_day(iso)}: no punches")
            parts.append(
                ("Your punches: " + "; ".join(lines) + ".")
                if lines
                else "I have no punches for you on the days you asked about."
            )
        elif intent == "my_cases" and "cases" in packet:
            items = packet["cases"]["items"]
            asked = packet.get("asked_day")
            where = f" on {asked['words']}" if asked else " in these weeks"
            if not items:
                parts.append(f"I have no attendance case for you{where}.")
            else:
                # A day question lists every visible case of that day (P17 never is one).
                shown = items if asked else items[:3]
                lines = [_case_line(c) for c in shown]
                head = f"You have {packet['cases']['total']} attendance "
                head += "case" if packet["cases"]["total"] == 1 else "cases"
                parts.append(f"{head}{where}. " + " ".join(lines))
        elif intent == "policy_rule" and packet.get("policies"):
            for p in packet["policies"]:
                text = f"{p['policy_id']} ({p['title']}): {p['rule']}"
                if p.get("allowed_fixes"):
                    text += f" What happens next: {p['allowed_fixes']}"
                parts.append(text)
        elif intent == "my_supervisor" and packet.get("supervisor"):
            team = packet["you"].get("team")
            parts.append(
                f"Your supervisor is {packet['supervisor']}"
                + (f" ({team} team)" if team else "")
                + f". You can ask {packet['supervisor']} about your attendance records and cases."
            )
    if packet.get("ask_supervisor_about"):
        days = ", ".join(_day(d) for d in packet["ask_supervisor_about"])
        parts.append(f"For {days}, please ask your supervisor.")
    if "policies" in packet and "policy_rule" not in intents:
        for p in packet["policies"][:1]:
            parts.append(f"The rule ({p['policy_id']}): {p['rule']}")
    return parts


def template_answer(packet: dict[str, Any], intents: list[str]) -> str:
    parts = template_parts(packet, intents)
    return " ".join(parts) if parts else refusal_text("unsupported", packet.get("supervisor"))


def packet_sources(packet: dict[str, Any], intents: list[str]) -> list[SourceRef]:
    refs: list[SourceRef] = []
    for c in packet.get("cases", {}).get("items", [])[:3]:
        refs.append(SourceRef(kind="case", id=c["case_id"]))
    for p in packet.get("policies", []):
        refs.append(SourceRef(kind="policy", id=p["policy_id"]))
    for kind in ("leave_balance", "schedule", "punches"):
        if kind in packet:
            refs.append(SourceRef(kind=kind))
    if "my_supervisor" in intents and packet.get("supervisor"):
        refs.append(SourceRef(kind="supervisor"))
    return refs[:6]


# ------------------------------------------------------------------ refusals

CAN = (
    "I can answer questions about your own leave balance, schedule, punches and attendance "
    "cases, and about the attendance policy (P1 to P17)."
)


def _ask(supervisor: str | None) -> str:
    who = f"your supervisor, {supervisor}" if supervisor else "your supervisor"
    return f"For anything else, please ask {who}."


def refusal_text(
    code: str,
    supervisor: str | None,
    *,
    dates: tuple[date, date] | None = None,
) -> str:
    if code == "ask_supervisor":
        who = f"your supervisor, {supervisor}" if supervisor else "your supervisor"
        return f"I can't explain that one here; please ask {who}."
    if code == "other_person":
        lead = (
            "I can't answer that: I only answer questions about your own attendance, never "
            "about other people."
        )
    elif code == "pay":
        lead = "I can't answer questions about pay or salary; I only cover attendance."
    elif code == "action":
        lead = (
            "I can't change, approve or delete anything; I only answer questions. To answer a "
            "question about your record, use the Questions tab."
        )
    elif code == "out_of_range" and dates is not None:
        lo, hi = dates
        lead = (
            f"I can't answer that: I can only answer about {lo.day} {lo:%b} to {hi.day} {hi:%b %Y}."
        )
    else:
        lead = "I can't answer that."
    return f"{lead} {CAN} {_ask(supervisor)}"
