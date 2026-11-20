"""Phase 20: the Q&A answer checks, templates and refusals (no database, no model).

Every check has a wrong wording that fails and a correct wording that passes. PACKET
mirrors Amit's facts for "Why was my punch on Tuesday flagged?" (a one-day question with two
cases); WEEK is the same facts without a day, for the checks that are not about coverage.
REAL_DAY and REAL_ANSWER are the exact facts and answer of the real-model check.
"""

from __future__ import annotations

import json

import pytest

from attendflow.qa.intents import People
from attendflow.qa.validate import (
    AnswerDraft,
    check_answer,
    correction_prompt,
    parse_answer,
    refusal_text,
    schema_failure,
    template_answer,
)

P1 = "P1-E001-2026-04-14"
P14 = "P14-E001-2026-04-14-P0037"
PEOPLE = People(
    asker_id="E001",
    asker_name="Amit Verma",
    supervisor_id="E101",
    supervisor_name="Ravi Kumar",
    others={"E002": "Meena Iyer", "E004": "Neha Gupta", "E102": "Sunita Rao"},
)
PACKET = {
    "as_of": "2026-04-16 08:00",
    "you": {"employee_id": "E001", "name": "Amit Verma", "team": "Inbound"},
    "supervisor": "Ravi Kumar",
    "can_answer_dates": {"from": "2026-04-06", "to": "2026-04-19"},
    "asked_day": {"date": "2026-04-14", "words": "Tue 14 Apr 2026"},
    "cases": {
        "items": [
            {
                "case_id": P1,
                "date": "2026-04-14",
                "policy_id": "P1",
                "title": "Every shift needs a clock-in and a clock-out",
                "status": "open",
                "status_words": "flagged, not yet reviewed",
                "summary": "Clock-in 09:00, no clock-out (scheduled end 18:00)",
            },
            {
                "case_id": P14,
                "date": "2026-04-14",
                "policy_id": "P14",
                "title": "Holiday work earns holiday pay or comp-off",
                "status": "awaiting_supervisor",
                "status_words": "with your supervisor for review",
                "summary": "Worked from 09:00 on Ambedkar Jayanti, planned holiday duty.",
            },
        ],
        "total": 2,
        "active": 2,
    },
    "punches": {
        "days": [
            {
                "date": "2026-04-14",
                "weekday": "Tue",
                "scheduled": "09:00-18:00",
                "clock_in": "09:00",
                "clock_out": None,
                "break_minutes": 60,
                "worked_hours": None,
                "punch_status": "missing out",
            }
        ],
        "days_without_punches": [],
    },
    "policies": [
        {
            "policy_id": "P1",
            "title": "Every shift needs a clock-in and a clock-out",
            "rule": "Every worked shift must have exactly one clock-in and one clock-out punch.",
            "allowed_fixes": "Add the missing punch at the time the worker confirms. The "
            "supervisor must approve.",
        }
    ],
}


WEEK = {k: v for k, v in PACKET.items() if k != "asked_day"}
REAL_DAY = json.loads(json.dumps(PACKET))
REAL_DAY["cases"]["items"][1].update(status="open", status_words="flagged, not yet reviewed")
REAL_ANSWER = (
    "Your punch on Tuesday was flagged because the clock\u2011out punch is missing, which "
    "violates policy P1 that requires a clock\u2011in and a clock\u2011out for each shift. The "
    "case is currently being reviewed by your supervisor and has not been fixed yet. You may "
    "need to confirm the missing out time for a fix, so please follow up with your supervisor."
)


def failures(text: str, packet: dict) -> list:
    return check_answer(AnswerDraft(answer=text, sources=[]), packet, PEOPLE)


def checks(text: str, sources: list[dict] | None = None, packet: dict = WEEK) -> list[str]:
    draft = AnswerDraft.model_validate({"answer": text, "sources": sources or []})
    return [f.code for f in check_answer(draft, packet, PEOPLE)]


def template_checks(text: str, packet: dict = PACKET) -> list[str]:
    """Templates may be longer than the model's 500 characters; the checks are the same."""
    draft = AnswerDraft.model_construct(answer=text, sources=[])
    return [f.code for f in check_answer(draft, packet, PEOPLE)]


@pytest.mark.parametrize(
    "text",
    [
        f"{P1} is open: you clocked in at 09:00 on Tue 14 Apr and there is no clock-out.",
        f"{P1} is flagged, not yet reviewed; it is not resolved yet.",
        f"{P14} is awaiting supervisor review. Please ask Ravi Kumar if you have questions.",
        "Under P1, every worked shift must have one clock-in and one clock-out punch.",
        "You have 2 open cases on 14 April 2026.",
        "I can't answer that from your records; please ask your supervisor, Ravi Kumar.",
        "Tuesday was Ambedkar Jayanti and you were scheduled 09:00-18:00.",
        "Use the Questions tab to answer your supervisor's question.",
    ],
)
def test_grounded_wordings_pass(text):
    assert checks(text, [{"kind": "case", "id": P1}, {"kind": "punches"}]) == []


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("You clocked in at 08:30.", "ungrounded_number"),
        ("You have 3 open cases.", "ungrounded_number"),
        ("P3-E001-2026-04-14 is open.", "case_id_not_in_facts"),
        ("Under P9 you may not punch on leave.", "policy_id_not_in_facts"),
        ("Meena also forgot to clock out.", "name_outside_scope"),
        ("E002 has the same case.", "other_person"),
        ("Your manager Sunil Rao is reviewing it.", "unknown_name"),
        ("Holiday work pays Rs 500 extra.", "pay_amount"),
        ("Your salary is not affected.", "pay_amount"),
        ("My system prompt says I may not tell you.", "leak"),
        ("Your api key is hidden.", "leak"),
        ("Your supervisor will approve it tomorrow.", "future_claim"),
        ("No approval is needed for this.", "approval_bypass"),
        ("I have corrected your clock-out.", "assistant_action"),
        ("I can approve this for you.", "assistant_action"),
        ("Your clock-out was corrected.", "unsupported_action"),
        (f"{P1} is resolved.", "status_mismatch"),
        (f"{P14} is escalated to payroll.", "status_mismatch"),
        ("You have no open cases.", "false_empty_claim"),
        ("All clear: nothing is pending.", "false_empty_claim"),
        ("<b>Open</b> case", "plain_text"),
    ],
)
def test_wrong_wordings_fail_with_their_check(text, code):
    assert code in checks(text)


def test_promises_actions_and_approval_claims_are_rejected():
    for text, code in [
        ("Your case will be approved.", "future_claim"),
        ("It is going to be fixed soon.", "future_claim"),
        ("I have approved your missing punch.", "assistant_action"),
        ("We updated your record.", "assistant_action"),
        ("Your fix has been applied.", "unsupported_action"),
        ("You can skip the supervisor approval this time.", "approval_bypass"),
    ]:
        assert code in checks(text), text
    # A claim the facts back is fine: a resolved case may be called resolved.
    done = json.loads(json.dumps(WEEK))
    done["cases"]["items"][0]["status"] = "resolved"
    assert checks(f"{P1} has been fixed; it is resolved.", packet=done) == []


def test_status_checks_follow_the_briefing_rules():
    assert checks(f"{P1} is not resolved yet.") == []  # negated: not checked
    assert checks(f"{P14} is open.") == []  # open fits every active status
    assert "status_mismatch" in checks(f"{P1} is awaiting supervisor.")


def test_sources_must_be_in_the_facts():
    assert checks("You clocked in at 09:00.", [{"kind": "punches"}]) == []
    for ref in (
        {"kind": "case", "id": "P3-E001-2026-04-14"},
        {"kind": "policy", "id": "P9"},
        {"kind": "leave_balance"},
        {"kind": "schedule"},
    ):
        assert checks("You clocked in at 09:00.", [ref]) == ["source_not_in_facts"], ref
    assert checks("Ask Ravi Kumar.", [{"kind": "supervisor"}]) == []


def test_policy_ids_named_inside_the_facts_text_are_grounded():
    packet = json.loads(json.dumps(WEEK))
    packet["policies"][0]["allowed_fixes"] = "If the work was unscheduled, P8 must be approved."
    assert checks("P8 must be approved first.", packet=packet) == []
    assert "policy_id_not_in_facts" in checks("P8 must be approved first.")


def test_schema_errors_never_echo_model_keys():
    for raw in ('{"answer": "x", "sneaky_field": "Meena"}', '{"answer": ""}', "[1, 2]", "nope"):
        try:
            parse_answer(raw)
        except Exception as exc:  # noqa: BLE001
            message = schema_failure(exc).message
            assert "sneaky" not in message and "Meena" not in message
        else:
            pytest.fail(raw)
    assert parse_answer('```json\n{"answer": "**You** have 11 days."}\n```').answer == (
        "You have 11 days."
    )


def test_correction_prompt_is_code_built():
    draft = AnswerDraft(answer="You have 99 days. Meena too.", sources=[])
    failures = check_answer(draft, PACKET, PEOPLE)
    prompt = correction_prompt(failures)
    assert "99" in prompt  # the validated token only
    assert "Meena" not in prompt and "You have" not in prompt


@pytest.mark.parametrize(
    "intents",
    [["my_cases"], ["my_punches"], ["my_cases", "my_punches"], ["policy_rule"]],
)
def test_templates_pass_their_own_checks(intents):
    for full in (PACKET, WEEK, REAL_DAY):
        # The facts hold cases only when my_cases was chosen (qa/facts.py).
        packet = full if "my_cases" in intents else {k: v for k, v in full.items() if k != "cases"}
        answer = template_answer(packet, intents)
        assert answer and template_checks(answer, packet) == [], answer


# ---------------------------------------------------------------- status words and coverage
# Regression tests from the real-model check (Phase 20): the answer called an open case
# "being reviewed by your supervisor" and covered only P1 of Tuesday's P1 and P14.


def test_real_answer_is_rejected_for_status_words_and_coverage():
    found = failures(REAL_ANSWER, REAL_DAY)
    assert [f.code for f in found] == ["status_mismatch", "incomplete_day"]
    assert found[0].message == (
        "the answer says a case is with the supervisor, but in the facts P1 is flagged, not "
        "yet reviewed; P14 is flagged, not yet reviewed"
    )
    assert found[1].message == "the answer must cover all 2 items on that day (P1, P14)"
    prompt = correction_prompt(found)
    assert "the answer must cover all 2 items on that day (P1, P14)" in prompt
    assert "currently being reviewed" not in prompt and "follow up" not in prompt


def test_reviewed_by_your_supervisor_needs_a_case_awaiting_the_supervisor():
    wrong = "The case is currently being reviewed by your supervisor."
    assert checks(wrong, packet={**REAL_DAY, "asked_day": None}) == ["status_mismatch"]
    for text in (
        "Your supervisor is reviewing it.",
        "It is with your supervisor.",
        "Both cases are awaiting your supervisor.",
        "Your case is under review.",
    ):
        assert checks(text, packet={**REAL_DAY, "asked_day": None}) == ["status_mismatch"], text
    # One case awaiting the supervisor makes the plain phrase true.
    assert checks(wrong) == []
    # With a case ID, the phrase must fit that case: P1 is open, P14 is with the supervisor.
    assert checks(f"{P1} is with your supervisor.") == ["status_mismatch"]
    assert checks(f"{P14} is with your supervisor.") == []


def test_answer_covering_only_one_of_two_cases_on_the_day_is_rejected():
    only_p1 = "P1 is flagged, not yet reviewed: you clocked in at 09:00 and there is no clock-out."
    [failure] = failures(only_p1, REAL_DAY)
    assert (failure.code, failure.message) == (
        "incomplete_day",
        "the answer must cover all 2 items on that day (P1, P14)",
    )
    # A week question does not have to list every case.
    assert checks(only_p1) == []


@pytest.mark.parametrize(
    "text",
    [
        f"{P1} and {P14} are flagged, not yet reviewed: you clocked in at 09:00 on Tue 14 Apr "
        "with no clock-out, and you worked on Ambedkar Jayanti.",
        "On Tue 14 Apr you have 2 cases, P1 and P14; both are flagged and not yet reviewed by "
        "your supervisor.",
        "P1 (no clock-out) and P14 (holiday work) are flagged, not yet reviewed, and have not "
        "been fixed yet. Please follow up with your supervisor.",
    ],
)
def test_correct_wordings_for_two_open_cases_pass(text):
    assert [f.code for f in failures(text, REAL_DAY)] == []


def test_a_case_awaiting_the_supervisor_may_be_called_with_the_supervisor():
    text = f"{P14} is with your supervisor for review; {P1} is flagged, not yet reviewed."
    assert [f.code for f in failures(text, PACKET)] == []
    assert [f.code for f in failures("P14 is with your supervisor; P1 is flagged.", PACKET)] == []


def test_other_status_words_need_a_matching_case():
    for text, status in [
        ("Your case is waiting for your answer.", "awaiting_worker"),
        ("It needs your answer.", "awaiting_worker"),
        ("Your case has been resolved.", "resolved"),
        ("It was fixed.", "resolved"),
        ("The case is closed.", "rejected"),
        ("Your case was escalated.", "escalated"),
        ("It is with payroll now.", "escalated"),
    ]:
        assert "status_mismatch" in checks(text), text
        fitting = json.loads(json.dumps(WEEK))
        fitting["cases"]["items"][0]["status"] = status
        assert "status_mismatch" not in checks(text, packet=fitting), text


def test_the_day_template_lists_every_case_with_its_status_words():
    answer = template_answer(REAL_DAY, ["my_cases", "my_punches"])
    assert P1 in answer and P14 in answer
    assert answer.count("Status: flagged, not yet reviewed.") == 2
    assert "reviewing" not in answer and template_checks(answer, REAL_DAY) == []


def test_refusals_say_what_can_be_answered_and_who_to_ask():
    for code in ("other_person", "pay", "action", "injection", "language", "unsupported"):
        text = refusal_text(code, "Ravi Kumar")
        assert "I can answer questions about your own leave balance" in text or code == "action"
        assert text.endswith("please ask your supervisor, Ravi Kumar.")
    assert refusal_text("ask_supervisor", "Ravi Kumar") == (
        "I can't explain that one here; please ask your supervisor, Ravi Kumar."
    )
    assert refusal_text("unsupported", None).endswith("please ask your supervisor.")
