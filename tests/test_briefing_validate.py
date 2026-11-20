"""Phase 17: the briefing's grounding and claim checks, the template and the generator.

No database: the packet below is the real Priya packet of the seeded demo (trimmed).
"""

from __future__ import annotations

import copy
import json

import pytest

from attendflow.briefing import generate as gen_module
from attendflow.briefing.generate import SYSTEM_PROMPT, generate
from attendflow.briefing.validate import (
    BriefingDraft,
    check_draft,
    correction_prompt,
    parse_draft,
    template_draft,
)
from attendflow.config import get_settings
from attendflow.llm.client import ChatMessage, LLMError

P2 = "P2-E005-2026-04-13-P0003"
P3 = "P3-E002-2026-04-13"
P5 = "P5-E002-2026-04-13"
P1 = "P1-E001-2026-04-14"
P11 = "P11-E007-2026-04-13-sick"
KARAN_P9 = "P9-E006-2026-04-15"  # exists, but is not in this packet

PEOPLE = {
    "E001": "Amit Verma",
    "E002": "Meena Iyer",
    "E003": "Ramesh Patil",
    "E005": "Sana Khan",
    "E006": "Karan Mehta",
    "E007": "Dev Malhotra",
    "E101": "Ravi Kumar",
    "E102": "Sunita Rao",
    "E201": "Priya Sharma",
}
KNOWN = {P2, P3, P5, P1, P11, KARAN_P9}


def _c(cid: str, pid: str, eid: str, day: str, status: str = "open", sev: str = "high"):
    return {
        "case_id": cid,
        "policy_id": pid,
        "employee_id": eid,
        "date": day,
        "status": status,
        "severity": sev,
        "no_reply_stage": 0,
    }


PACKET = {
    "scope": "all",
    "team": None,
    "workflow_date": "2026-04-16",
    "data_cutoff": "2026-04-16T08:00",
    "counts": {
        "active": 16,
        "total": 17,
        "open": 16,
        "awaiting_worker": 0,
        "awaiting_supervisor": 0,
        "escalated": 0,
        "resolved": 1,
        "rejected": 0,
        "auto_resolved": 1,
        "stuck": 0,
    },
    "needs_decision": {"total": 1, "cases": [_c(P11, "P11", "E007", "2026-04-13")]},
    "handled_on_its_own": {
        "auto_resolved_total": 1,
        "auto_resolved_cases": [_c(P2, "P2", "E005", "2026-04-13", "resolved", "low")],
        "resolved_without_human": 1,
        "needed_handling": 17,
        "percent": 5.9,
        "undone": 0,
        "today": {
            "investigated": 0,
            "messages_sent": 0,
            "reminders_sent": 0,
            "auto_resolved": 1,
            "auto_resolves_undone": 0,
            "escalated_by_silence": 0,
            "human_approvals": 0,
            "decided_without_worker": 0,
            "human_rejections": 0,
            "device_punches": 0,
        },
    },
    "blocking_payroll": {
        "week_start": "2026-04-13",
        "week_end": "2026-04-19",
        "week_closed": False,
        "status": "blocked",
        "signed_off": False,
        "blocking_total": 15,
        "blocking_cases": [
            _c(P3, "P3", "E002", "2026-04-13"),
            _c(P5, "P5", "E002", "2026-04-13"),
            _c(P1, "P1", "E001", "2026-04-14"),
        ],
        "blocking_without_case": 0,
        "notes": 2,
    },
    "watch": {
        "overtime_limit_hours": 40.0,
        "overtime_workers": [
            {
                "employee_id": "E002",
                "worked_hours": 36.0,
                "projected_hours": 48.0,
                "level": "projected_over",
            }
        ],
        "overtime_cases": [_c(P5, "P5", "E002", "2026-04-13")],
        "no_reply_total": 0,
        "no_reply_cases": [],
    },
    "teams": [
        {
            "team": "Inbound",
            "supervisor_id": "E101",
            "active": 11,
            "awaiting_worker": 0,
            "awaiting_supervisor": 0,
        },
        {
            "team": "Outbound",
            "supervisor_id": "E102",
            "active": 5,
            "awaiting_worker": 0,
            "awaiting_supervisor": 0,
        },
    ],
    "people": {
        "E001": "Amit Verma",
        "E002": "Meena Iyer",
        "E005": "Sana Khan",
        "E007": "Dev Malhotra",
        "E101": "Ravi Kumar",
        "E102": "Sunita Rao",
    },
    "policies": {
        "P1": "Every shift needs a clock-in and a clock-out",
        "P2": "Duplicate punches are merged",
        "P3": "Maximum hours per day",
        "P5": "Weekly overtime threshold",
        "P11": "Leave must be within balance",
    },
}

GOOD = {
    "headline": "16 cases are active and 1 needs your decision.",
    "bullets": [
        {
            "section": "needs_decision",
            "text": f"{P11} for Dev Malhotra waits for your decision.",
            "case_ids": [P11],
        },
        {
            "section": "handled_on_its_own",
            "text": f"Code auto-resolved {P2} for Sana Khan: 1 of 17 cases (5.9%).",
            "case_ids": [P2],
        },
        {
            "section": "blocking_payroll",
            "text": f"15 cases block payroll for the week of 2026-04-13, including {P3} and {P1}.",
            "case_ids": [P3, P1],
        },
        {
            "section": "watch",
            "text": f"Meena Iyer (E002) has 48 projected hours against the 40 h limit ({P5}).",
            "case_ids": [P5],
        },
    ],
    "team_lines": [
        {"team": "Inbound", "text": "Inbound has 11 active cases."},
        {"team": "Outbound", "text": "Outbound has 5 active cases."},
    ],
}


def codes(draft: dict, packet: dict = PACKET) -> list[str]:
    parsed = parse_draft(json.dumps(draft))
    return [f.code for f in check_draft(parsed, packet, known_case_ids=KNOWN, all_people=PEOPLE)]


def with_bullet(text: str, section: str = "needs_decision", case_ids=None) -> dict:
    draft = copy.deepcopy(GOOD)
    index = next(i for i, b in enumerate(draft["bullets"]) if b["section"] == section)
    draft["bullets"][index] = {
        "section": section,
        "text": text,
        "case_ids": [P11] if case_ids is None else case_ids,
    }
    return draft


# ---------------------------------------------------------------- accepted


def test_a_faithful_briefing_passes():
    assert codes(GOOD) == []


def test_list_lengths_and_the_parts_of_packet_dates_are_allowed():
    draft = with_bullet(f"{P11} is the only case waiting on Thursday 16 April 2026.")
    assert codes(draft) == []  # 16 / April / 2026 come from the workflow date


def test_harmless_formatting_is_normalised_but_the_shape_is_not_loosened():
    fenced = (
        "```json\n"
        + json.dumps({**GOOD, "headline": "**16 cases are active** and 1 needs your decision."})
        + "\n```"
    )
    assert parse_draft(fenced).headline == "16 cases are active and 1 needs your decision."
    with pytest.raises(ValueError):
        parse_draft(json.dumps({**GOOD, "extra": "x"}))
    with pytest.raises(ValueError):
        parse_draft(json.dumps({**GOOD, "bullets": GOOD["bullets"][:2]}))


@pytest.mark.parametrize("scope", ["all", "team", "empty"])
def test_the_template_always_passes_its_own_checks(scope):
    packet = copy.deepcopy(PACKET)
    if scope == "team":
        packet.update(scope="team", team="Inbound", teams=packet["teams"][:1])
    if scope == "empty":
        packet["needs_decision"] = {"total": 0, "cases": []}
        packet["blocking_payroll"].update(blocking_total=0, blocking_cases=[])
        packet["watch"].update(overtime_workers=[], overtime_cases=[])
        packet["handled_on_its_own"].update(
            resolved_without_human=0, auto_resolved_total=0, auto_resolved_cases=[]
        )
    draft = template_draft(packet)
    assert [b.section for b in draft.bullets] == [
        "needs_decision",
        "handled_on_its_own",
        "blocking_payroll",
        "watch",
    ]
    failures = check_draft(draft, packet, known_case_ids=KNOWN, all_people=PEOPLE)
    assert failures == [], failures


# ---------------------------------------------------------------- rejected


@pytest.mark.parametrize(
    ("text", "code"),
    [
        (f"{P11} waits; 42 hours are missing.", "ungrounded_number"),
        (f"{P11} waits; twelve workers are late.", "ungrounded_number"),
        (f"{P11} waits since 09:15.", "ungrounded_number"),
        (f"{P11} and P9-E006-2026-04-15 wait.", "case_id_not_in_facts"),
        (f"{P11} and P4-E009-2026-04-13 wait.", "unknown_case_id"),
        (f"{P11} waits for Karan Mehta.", "name_outside_scope"),
        (f"{P11} waits; ask Karan about it.", "name_outside_scope"),
        (f"{P11} waits; John Smith raised it.", "unknown_name"),
        (f"{P11} waits, and E006 is involved.", "employee_id_not_in_facts"),
        (f"{P11} waits under P9.", "policy_id_not_in_facts"),
        (f"{P11} will be approved by Ravi Kumar.", "future_claim"),
        (f"{P11} is going to close.", "future_claim"),
        (f"Ravi Kumar approved {P11}.", "unsupported_action"),
        (f"The agent investigated {P11}.", "unsupported_action"),
        (f"{P11} needs no supervisor approval.", "approval_bypass"),
        (f"{P11} waits <b>now</b>.", "plain_text"),
    ],
)
def test_ungrounded_or_unsupported_text_is_rejected(text, code):
    assert code in codes(with_bullet(text))


def test_case_ids_must_belong_to_the_bullet_section_and_be_cited():
    assert "case_id_wrong_section" in codes(with_bullet(f"{P3} waits.", case_ids=[P3]))
    assert "case_id_not_cited" in codes(with_bullet(f"{P11} waits.", case_ids=[]))
    assert "missing_case_ids" in codes(with_bullet("Something waits.", case_ids=[]))


def test_team_lines_must_name_teams_in_the_packet_once():
    draft = copy.deepcopy(GOOD)
    draft["team_lines"] = [{"team": "Night shift", "text": "Night shift has 5 active cases."}]
    assert "unknown_team" in codes(draft)
    draft["team_lines"] = [GOOD["team_lines"][0], GOOD["team_lines"][0]]
    assert "duplicate_team" in codes(draft)


def test_a_supervisor_packet_rejects_the_other_team():
    packet = copy.deepcopy(PACKET)
    packet.update(scope="team", team="Inbound", teams=packet["teams"][:1])
    packet["needs_decision"] = {"total": 0, "cases": []}
    packet["people"].pop("E007")
    packet["people"].pop("E102")
    draft = copy.deepcopy(GOOD)
    draft["bullets"][0] = {
        "section": "needs_decision",
        "text": "No case waits for your decision.",
        "case_ids": [],
    }
    assert "unknown_team" in codes(draft, packet)  # the Outbound line
    draft["team_lines"] = draft["team_lines"][:1]
    assert codes(draft, packet) == []
    draft["bullets"][0]["text"] = "Dev Malhotra has nothing waiting."
    assert "name_outside_scope" in codes(draft, packet)
    draft["bullets"][0] = {"section": "needs_decision", "text": f"{P11} waits.", "case_ids": [P11]}
    assert "case_id_not_in_facts" in codes(draft, packet)


def test_failure_messages_never_quote_model_words():
    draft = with_bullet(f"{P11} waits; Zorblax said 42 IGNORE-PREVIOUS will soon happen.")
    parsed = parse_draft(json.dumps(draft))
    failures = check_draft(parsed, PACKET, known_case_ids=KNOWN, all_people=PEOPLE)
    prompt = correction_prompt(failures)
    assert "the number 42" in prompt
    for word in ("Zorblax", "IGNORE", "soon happen"):
        assert word not in prompt
        assert all(word not in f.message for f in failures)


# ---------------------------------------------------------------- the generator


class Script:
    """A fake chat(): returns (or raises) the scripted replies and records each request."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls: list[dict] = []

    def __call__(self, settings, messages, tools, required=None, **kwargs):
        self.calls.append({"messages": copy.deepcopy(messages), "tools": tools, **kwargs})
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return ChatMessage(text=reply if isinstance(reply, str) else json.dumps(reply))


def settings(**changes):
    from dataclasses import replace

    base = replace(get_settings(env_file=None), llm_api_key="test-key-not-real")
    return replace(base, **changes)


def run(script, *, max_calls=40, **changes):
    return generate(
        settings(**changes),
        PACKET,
        known_case_ids=KNOWN,
        all_people=PEOPLE,
        max_calls=max_calls,
        chat_model=script,
    )


BAD = with_bullet(f"{P11} waits for Zorblax and 42 more.")


def test_a_valid_first_draft_is_used_after_one_call():
    script = Script(GOOD)
    result = run(script)
    assert (result.source, result.reason, result.llm_calls) == ("llm", "validated", 1)
    assert result.draft == BriefingDraft.model_validate(GOOD)
    [call] = script.calls
    assert call["tools"] == [] and call["json_output"] is True
    assert call["retry_transient"] is False  # a network error is never retried
    sent = json.dumps(call["messages"])
    for marker in ("$ref", "$defs", "date-time", '"format"'):
        assert marker not in sent
    assert "present tense and past tense" in SYSTEM_PROMPT
    assert "Refer to cases by their case IDs" in SYSTEM_PROMPT


def test_one_correction_after_a_failed_check_names_the_check_in_code_words_only():
    script = Script(BAD, GOOD)
    result = run(script)
    assert (result.source, result.reason, result.llm_calls) == ("llm", "validated_after_retry", 2)
    assert result.attempts[0]["outcome"] == "rejected"
    assert "ungrounded_number" in result.attempts[0]["checks"]
    correction = script.calls[1]["messages"][-1]["content"]
    assert "the number 42" in correction and "Zorblax" not in correction


def test_two_failed_drafts_fall_back_to_the_template():
    result = run(Script(BAD, BAD))
    assert (result.source, result.reason, result.llm_calls) == ("template", "validation_failed", 2)
    assert result.draft == template_draft(PACKET)
    assert result.failed_checks == ["ungrounded_number", "unknown_name"]


def test_invalid_json_also_gets_one_correction():
    result = run(Script("not json at all", GOOD))
    assert (result.reason, result.llm_calls) == ("validated_after_retry", 2)
    assert result.attempts[0]["checks"] == ["invalid_json"]


@pytest.mark.parametrize(
    ("error", "reason"), [(LLMError("HTTP 500"), "llm_error"), (TimeoutError(), "llm_error")]
)
def test_provider_errors_and_timeouts_are_never_retried(error, reason):
    script = Script(error, GOOD)
    result = run(script)
    assert (result.source, result.reason, result.llm_calls) == ("template", reason, 1)
    assert len(script.calls) == 1


def test_a_spent_deadline_is_a_timeout(monkeypatch):
    clock = iter([0.0, 0.0, 100.0, 100.0, 100.0])
    monkeypatch.setattr(gen_module.time, "monotonic", lambda: next(clock, 100.0))
    script = Script(LLMError("investigation deadline exceeded"))
    result = run(script, briefing_llm_deadline_seconds=20)
    assert (result.reason, result.llm_calls) == ("timeout", 1)


def test_no_key_disabled_or_no_budget_means_no_call():
    script = Script(GOOD)
    assert run(script, llm_api_key=None).reason == "llm_unavailable"
    assert run(script, briefing_enabled=False).reason == "llm_disabled"
    assert run(script, max_calls=0).reason == "no_budget"
    assert script.calls == []


def test_the_last_call_of_the_budget_gets_no_correction():
    script = Script(BAD, GOOD)
    result = run(script, max_calls=1)
    assert (result.reason, result.llm_calls) == ("validation_failed", 1)


# ---------------------------------------------------------------- status and emptiness claims
# Added after the first real-model run (docs/PROGRESS.md Phase 17): both drafts below came
# back from openai/gpt-oss-120b and passed the earlier checks.


def status_packet() -> dict:
    """The packet at the time of the real run: Amit had answered, so P1 awaits Ravi."""
    packet = copy.deepcopy(PACKET)
    for case in packet["blocking_payroll"]["blocking_cases"]:
        if case["case_id"] == P1:
            case["status"] = "awaiting_supervisor"
    return packet


REAL_BLOCKING = (
    f"Payroll remains blocked with open high‑severity cases {P3} and {P1} awaiting "
    "supervisor review."
)
REAL_OUTBOUND = "Outbound team has 5 active cases and no pending items."


def failures_for(draft: dict, packet: dict) -> list:
    parsed = parse_draft(json.dumps(draft))
    return check_draft(parsed, packet, known_case_ids=KNOWN, all_people=PEOPLE)


def test_real_example_p3_awaiting_supervisor_is_rejected_with_a_code_built_message():
    draft = with_bullet(REAL_BLOCKING, "blocking_payroll", [P3, P1])
    failures = failures_for(draft, status_packet())
    assert [f.code for f in failures] == ["status_mismatch"]
    assert failures[0].message == f"{P3} is open, not awaiting supervisor"
    prompt = correction_prompt(failures)
    assert f"{P3} is open, not awaiting supervisor" in prompt
    assert "remains blocked" not in prompt and "high" not in prompt  # no model words


def test_real_example_outbound_no_pending_items_is_rejected():
    draft = copy.deepcopy(GOOD)
    draft["team_lines"][1] = {"team": "Outbound", "text": REAL_OUTBOUND}
    failures = failures_for(draft, status_packet())
    assert [f.code for f in failures] == ["false_empty_claim"]
    assert failures[0].message == (
        "the Outbound team line says nothing is pending, but Outbound has 5 active cases"
    )


@pytest.mark.parametrize(
    "text",
    [
        f"{P3} is open and {P1} is awaiting supervisor review.",
        f"{P1} is awaiting supervisor review; {P3} is open.",
        f"Open cases {P3} and {P1} block payroll.",  # "open" = not closed
        f"{P3} is not awaiting supervisor review yet.",  # negated: not a claim
        f"{P1} is waiting for the supervisor, and {P3} is still open.",
    ],
)
def test_correct_status_wording_passes(text):
    draft = with_bullet(text, "blocking_payroll", [P3, P1])
    assert failures_for(draft, status_packet()) == []


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (f"{P3} is escalated to payroll.", f"{P3} is open, not escalated"),
        (f"{P1} is resolved.", f"{P1} is awaiting supervisor, not resolved"),
        (f"{P3} was approved.", f"{P3} is open, not approved"),
        (f"{P3} is awaiting the worker.", f"{P3} is open, not awaiting the worker"),
        (
            f"{P1} and {P3} are waiting for the supervisor.",
            f"{P3} is open, not awaiting supervisor",
        ),
    ],
)
def test_wrong_status_wording_is_rejected(text, message):
    draft = with_bullet(text, "blocking_payroll", [P3, P1])
    failures = [f for f in failures_for(draft, status_packet()) if f.code == "status_mismatch"]
    assert [f.message for f in failures] == [message]


def test_closed_and_auto_resolved_fit_a_resolved_case():
    draft = with_bullet(f"Code closed {P2} without a person.", "handled_on_its_own", [P2])
    assert failures_for(draft, status_packet()) == []
    open_case = with_bullet(f"{P2} is still open.", "handled_on_its_own", [P2])
    assert [f.message for f in failures_for(open_case, status_packet())] == [
        f"{P2} is resolved, not open"
    ]


@pytest.mark.parametrize(
    ("place", "text"),
    [
        ("headline", "All clear today."),
        ("blocking_payroll", "Nothing is pending for payroll."),
        ("needs_decision", f"No open cases need you; {P11} is listed."),
    ],
)
def test_empty_claims_are_rejected_where_the_facts_have_items(place, text):
    if place == "headline":
        draft = {**copy.deepcopy(GOOD), "headline": text}
    else:
        ids = [P3] if place == "blocking_payroll" else [P11]
        draft = with_bullet(text, place, ids)
    assert "false_empty_claim" in [f.code for f in failures_for(draft, status_packet())]


def test_empty_claims_pass_where_the_facts_are_empty():
    packet = status_packet()
    packet["needs_decision"] = {"total": 0, "cases": []}
    packet["teams"][1]["active"] = 0
    draft = copy.deepcopy(GOOD)
    draft["bullets"][0] = {
        "section": "needs_decision",
        "text": "Nothing is waiting for your decision.",
        "case_ids": [],
    }
    draft["team_lines"][1] = {"team": "Outbound", "text": "Outbound has no pending items."}
    assert failures_for(draft, packet) == []


def test_a_status_mismatch_gets_the_one_correction():
    bad = with_bullet(REAL_BLOCKING, "blocking_payroll", [P3, P1])
    script = Script(bad, GOOD)
    result = generate(
        settings(),
        status_packet(),
        known_case_ids=KNOWN,
        all_people=PEOPLE,
        max_calls=40,
        chat_model=script,
    )
    assert (result.reason, result.llm_calls) == ("validated_after_retry", 2)
    assert result.attempts[0]["checks"] == ["status_mismatch"]
    correction = script.calls[1]["messages"][-1]["content"]
    assert f"{P3} is open, not awaiting supervisor" in correction
    assert "remains blocked" not in correction
