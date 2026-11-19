"""Structured investigation data and policy-owned contact routing."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from attendflow.db.models import ExceptionRow
from attendflow.fixes.params import (
    DECISION_ACTIONS,
    FixParamsError,
    params_json,
    parse_params,
    validate_decision_params,
)
from attendflow.tools.models import RunChecksOut

Contact = Literal["worker", "supervisor", "hr"]
Confidence = Literal["low", "medium", "high"]


class CaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class EvidenceFact(CaseModel):
    fact: str = Field(min_length=1, max_length=300)
    source: str = Field(min_length=1, max_length=80)


class ProposedFix(CaseModel):
    option_id: str = Field(min_length=1, max_length=100)
    params: dict[str, Any]


class CaseDraft(CaseModel):
    what_happened: str = Field(min_length=1, max_length=600)
    policy_id: str
    policy_text_cited: str = Field(min_length=1, max_length=350)
    evidence: list[EvidenceFact] = Field(min_length=1, max_length=12)
    proposed_fix: ProposedFix | None
    validation_result: RunChecksOut | None = None
    who_to_ask: Contact | None = None
    confidence: Confidence
    fallback: bool = False
    tool_steps: int = Field(default=0, ge=0)
    duration_ms: float = Field(default=0, ge=0)


class InvestigationCase(CaseDraft):
    who_to_ask: Contact
    next_action: str


CONTACTS: dict[str, Contact] = {
    "P1": "worker",
    "P2": "supervisor",
    "P3": "supervisor",
    "P4": "supervisor",
    "P5": "supervisor",
    "P6": "supervisor",
    "P7": "supervisor",
    "P8": "supervisor",
    "P9": "worker",
    "P10": "supervisor",
    "P11": "supervisor",
    "P12": "worker",
    "P13": "worker",
    "P14": "supervisor",
    "P15": "supervisor",
    "P16": "supervisor",
    "P17": "supervisor",
}


def routing(row: ExceptionRow, option: dict | None) -> tuple[Contact, str]:
    if row.status == "escalated" and row.assigned_to:
        return "hr", "Payroll reviews the escalated case before any fix is applied."
    policy = row.policy_id
    if row.auto_resolved or policy == "P15":
        return "supervisor", "No action is required. A supervisor can review the record if needed."
    if policy == "P12":
        return "worker", "Ask the worker for the certificate. The supervisor reviews the response."
    if policy == "P1":
        return (
            "worker",
            "Ask the worker to confirm the punch time, then obtain supervisor approval.",
        )
    if policy == "P14":
        return "supervisor", (
            "Resolve prerequisite P1 or P8 cases first. The supervisor chooses compensation "
            "with the worker."
        )
    if policy in {"P8", "P17"}:
        return (
            "supervisor",
            "The supervisor reviews the case and consults the worker before rejection or voiding.",
        )
    if option and (
        option.get("requires_worker_confirmation")
        or (policy == "P10" and option["action"] in {"record_leave", "add_punches"})
    ):
        return "worker", "Ask the worker to confirm the facts, then obtain supervisor approval."
    contact = CONTACTS[policy]
    if contact == "worker":
        return contact, "Ask the worker to confirm what happened, then obtain supervisor approval."
    return contact, "Send the case to the supervisor for review and approval before applying a fix."


def normalized_params(option: dict, params: dict) -> dict:
    action = option["action"]
    original = option["params"]
    if action in DECISION_ACTIONS:
        # Required human notes are collected at approval, not invented during investigation.
        return validate_decision_params(original, params)
    return params_json(parse_params(action, original, params))


_TOKEN = re.compile(
    r"\d{4}-\d{2}-\d{2}(?:T\d{1,2}:\d{2}(?::\d{2})?)?"
    r"|\d{1,2}:\d{2}(?::\d{2})?|[+-]?\d+(?:\.\d+)?"
)
_BYPASS = re.compile(
    r"\b(?:no\s+(?:(?:further|additional|prior|explicit)\s+)*"
    r"(?:human(?: intervention)?|worker (?:input|confirmation)|supervisor(?: approval)?|"
    r"approval|confirmation)\b"
    r"|(?:approval|confirmation|human intervention)\s+(?:is\s+)?"
    r"(?:not (?:needed|required|necessary)|unnecessary|optional)"
    r"|(?:skip|bypass|waive)\b.{0,35}\b(?:approval|confirmation|review)"
    r"|(?:apply|approve)\b.{0,45}\b(?:automatically|without|immediately)"
    r"|already\s+(?:approved|applied|confirmed))\b",
    re.IGNORECASE,
)


def numeric_tokens(text: str) -> set[str]:
    values = set()
    # Normalize dash variants and common prose time formatting.
    text = text.replace("‑", "-").replace("–", " ").replace("—", " ")
    for found in _TOKEN.findall(text):
        if ":" in found:
            prefix, sep, clock = found.rpartition("T")
            hour, minute, *seconds = clock.split(":")
            value = f"{prefix}{sep}{int(hour):02}:{minute}"
            values.add(value if not seconds or seconds[0] == "00" else f"{value}:{seconds[0]}")
        elif "-" in found.lstrip("+-"):
            values.add(found)
        else:
            values.add(str(Decimal(found).normalize()))
    return values


def validate_facts(draft: CaseDraft, sources: dict[str, Any], row: ExceptionRow) -> None:
    all_numbers = set()
    for source in sources.values():
        all_numbers.update(numeric_tokens(json.dumps(source, ensure_ascii=False)))
    if numeric_tokens(draft.what_happened) - all_numbers:
        raise ValueError("what_happened contains a number or time absent from the case sources")
    for item in draft.evidence:
        if item.source not in sources:
            raise ValueError(f"unknown evidence source {item.source!r}")
        if numeric_tokens(item.fact) - numeric_tokens(
            json.dumps(sources[item.source], ensure_ascii=False)
        ):
            raise ValueError(f"evidence contains an unsupported number or time in {item.source}")
    if not row.auto_resolved and row.policy_id != "P15":
        if any(
            _BYPASS.search(text)
            for text in [draft.what_happened, *(e.fact for e in draft.evidence)]
        ):
            raise ValueError("narrative contradicts required human confirmation or approval")


def fallback_case(
    row: ExceptionRow, policy_text: str, duration_ms: float, tool_steps: int = 0
) -> InvestigationCase:
    proposal = None
    option = None
    if not row.auto_resolved and row.policy_id != "P15":
        for candidate in row.fix_options:
            try:
                params = normalized_params(candidate, candidate["params"])
            except FixParamsError:
                continue
            option = candidate
            proposal = ProposedFix(option_id=option["option_id"], params=params)
            break
    who, next_action = routing(row, option)
    quote = next((line for line in policy_text.splitlines() if line.startswith("**Rule:**")), "")
    return InvestigationCase(
        what_happened=(row.summary or row.title)[:600],
        policy_id=row.policy_id,
        policy_text_cited=(quote.removeprefix("**Rule:**").strip() or policy_text.strip())[:350],
        evidence=[EvidenceFact(fact=(row.summary or row.title)[:300], source="stored:details")],
        proposed_fix=proposal,
        validation_result=None,
        who_to_ask=who,
        next_action=next_action,
        confidence="low",
        fallback=True,
        tool_steps=tool_steps,
        duration_ms=duration_ms,
    )
