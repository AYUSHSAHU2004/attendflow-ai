"""Phase 14: one end-to-end story through HTTP only, shared by the Activity Center tests and
the autonomy anti-drift tests. No real LLM: every model call is scripted.

Demo mode on, demo reset (Sana's P2 auto-resolves), Neha's 08:58 device punch, a scheduler
cycle (investigates and asks Neha), Ravi investigates and asks Amit by hand, two more
investigations whose model fails or drafts badly (diagnostics on), the demo clock moves
past every ladder step (reminder, Ravi, Priya for Neha), Amit answers No in free text
after the reminder (one rejected model output, then 19:30) and confirms, Ravi approves
Amit's fix, and Ravi undoes Sana's auto-resolve.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from attendflow.llm.client import ChatMessage, LLMError
from tests.api_helpers import (
    AMIT,
    AMIT_P1,
    MEENA_P3_MON,
    MEENA_P5,
    PRIYA,
    RAVI,
    SANA_P2,
    post,
)
from tests.test_e2e_prototype import (
    CLOCK_OUT,
    TEXT,
    good_message,
    run_investigation,
    scripted_investigation,
    scripted_message,
)
from tests.test_ingest import NEHA_IN, NEHA_P1
from tests.test_investigation import draft, final, simulate
from tests.test_worker_time import fake_model, output

# Planted in model failures and outputs; must never reach the feed, summary or trace.
LEAK_PROVIDER = "LEAKCHECK-provider-diagnostic"
LEAK_OUTPUT = "LEAKCHECK-raw-model-output"
LEAK_QUOTE = "LEAKCHECK-invented-policy-quote"
LEAKS = (LEAK_PROVIDER, LEAK_OUTPUT, LEAK_QUOTE)
UNDO_REASON = "Sana says the second tap was a real re-entry"


class StoryModel:
    """Investigations: Meena P5's model call always fails, Meena P3's drafts always fail
    validation, every other case simulates its first option and drafts correctly."""

    def __call__(self, settings, messages, tools, required, *, deadline, json_output):
        request = json.loads(messages[1]["content"])
        case = request["case"]  # employee_id, date, policy_id
        meena = case["employee_id"] == "E002"
        if meena and case["policy_id"] == "P5":
            raise LLMError(f"{LEAK_PROVIDER}: upstream said no")
        if not json_output:
            simulatable = request["simulatable_option_ids"]
            # Simulate the first option the tool can run (P3's first is decision-only).
            options = [o for o in request["fix_options"] if o["option_id"] in simulatable]
            return simulate({**request, "fix_options": options or request["fix_options"]})
        if meena and case["policy_id"] == "P3":
            body = draft(request)
            body["policy_text_cited"] = LEAK_QUOTE
            return ChatMessage(text=json.dumps(body))
        return final(request)


@dataclass
class Story:
    cycles: list[dict] = field(default_factory=list)


def _clock(client, hours: float) -> None:
    r = client.post("/api/admin/demo/clock", json={"hours": hours}, headers=PRIYA)
    assert r.status_code == 200, r.text


def _cycle(client) -> dict:
    r = client.post("/api/admin/scheduler/run-now", headers=PRIYA)
    assert r.status_code == 200, r.text
    assert r.json()["errors"] == [], r.json()
    return r.json()


def run_story(client, monkeypatch) -> Story:
    c = client
    story = Story()
    assert c.post("/api/seed").status_code == 200  # empty test DB: load the employees once
    assert c.post("/api/admin/demo/reset", headers=PRIYA).status_code == 200
    scripted_investigation(monkeypatch, StoryModel())
    scripted_message(monkeypatch, good_message)

    # Device punch, then one cycle: Neha's new P1 is investigated and she is asked.
    punch = c.post("/api/admin/demo/punch", json=NEHA_IN, headers=PRIYA)
    assert punch.status_code == 201, punch.text
    story.cycles.append(_cycle(c))
    assert story.cycles[-1]["messages_sent"] == [NEHA_P1]

    # Ravi investigates by hand: Amit (validated), Meena P5 (model down), Meena P3 (bad
    # drafts, then the engine template), and asks Amit.
    assert run_investigation(c, AMIT_P1, RAVI)["reason"] == "validated"
    assert run_investigation(c, MEENA_P5, RAVI)["reason"] == "llm_error"
    p3 = run_investigation(c, MEENA_P3_MON, RAVI)
    assert p3["reason"] == "validation_failed", p3
    assert post(c, AMIT_P1, "ask-worker", {}, RAVI).status_code == 200

    # +8 h: one reminder each.
    _clock(c, 8)
    story.cycles.append(_cycle(c))
    assert sorted(story.cycles[-1]["no_reply"]["reminded"]) == sorted([AMIT_P1, NEHA_P1])

    # Amit answers No in free text: the first model output is rejected, the second reads
    # an approximate 19:30, and he confirms it.
    fake_model(monkeypatch, f"{LEAK_OUTPUT} not json", output("19:30", approximate=True))
    reply = post(c, AMIT_P1, "worker-reply", {"confirmed": False, "text": TEXT}, AMIT)
    assert reply.status_code == 200, reply.text
    assert reply.json()["time_review"]["stage"] == "candidate"
    assert post(c, AMIT_P1, "worker-confirm-time", {}, AMIT).status_code == 200

    # Neha stays silent: Ravi at 24 h, Priya 24 h later.
    _clock(c, 16)
    story.cycles.append(_cycle(c))
    assert story.cycles[-1]["no_reply"]["to_supervisor"] == [NEHA_P1]
    _clock(c, 24)
    story.cycles.append(_cycle(c))
    assert story.cycles[-1]["no_reply"]["to_admin"] == [NEHA_P1]

    # People decide: Ravi approves Amit's confirmed time and undoes Sana's auto-resolve.
    approved = post(c, AMIT_P1, "approve", {"option_id": CLOCK_OUT}, RAVI)
    assert approved.status_code == 200, approved.text
    undone = post(c, SANA_P2, "undo", {"reason": UNDO_REASON}, RAVI)
    assert undone.status_code == 200, undone.text
    return story
