from datetime import date

import pytest
from sqlalchemy import select

from attendflow.cases import worker_message
from attendflow.cases.worker_message import WorkerFacts, validate_worker_message
from attendflow.db.models import WorkerMessageRow
from attendflow.llm.client import ChatMessage, LLMError
from tests.api_helpers import (
    AMIT,
    AMIT_P1,
    MEENA,
    MEENA_P5,
    RAVI,
    assert_error,
    get,
    post,
    session_for,
    store_test_investigation,
)


@pytest.fixture
def facts():
    return WorkerFacts(
        first_name="Amit",
        date="2026-04-14",
        display_date="April 14, 2026",
        issue="Your clock-out is missing.",
        proposed_fix="Record your clock-out at 18:00.",
        question="Did you leave at 18:00?",
        reply_prompt="What time did you actually leave, and why?",
    )


def test_message_accepts_equivalent_date_and_time(facts):
    text = "Hi Amit, we missed your clock-out on April 14, 2026. Did you leave at 6:00 PM?"
    assert validate_worker_message(text, facts) == text


def test_message_normalizes_quoted_reply_with_line_breaks(facts):
    reply = (
        "  “Hi Amit, your clock-out is missing on April 14, 2026.\r\n\r\n"
        "Did you leave at 6:00 PM?”\n"
    )
    expected = "Hi Amit, your clock-out is missing on April 14, 2026. Did you leave at 6:00 PM?"
    assert validate_worker_message(reply, facts) == expected


@pytest.mark.parametrize(
    "invented", ["We saw you leave at 7:15 PM.", "Your shift lasted 11 hours."]
)
def test_normalized_reply_still_rejects_invented_times_and_numbers(facts, invented):
    reply = f'"Hi Amit, about April 14, 2026. {invented}\nDid you leave at 6:00 PM?"\n'
    with pytest.raises(ValueError, match="unverified number or time"):
        validate_worker_message(reply, facts)


@pytest.mark.parametrize(
    "text",
    [
        "Hi Amit, on April 14, 2026 your shift was 32 hours. Did you leave at 18:00?",
        "Hi Amit, on April 14, 2026 we saw a punch at 7 PM. Did you leave at 18:00?",
        "Hi Amit, on April 15, 2026 your clock-out is missing. Did you leave at 18:00?",
        "Hi Amit, your clock-out is missing. Did you leave at 18:00?",
        "<b>April 14, 2026</b>. Did you leave at 18:00?",
        "Hi Amit, on April 14, 2026. Did you arrive at 18:00?",
    ],
)
def test_message_rejects_unverified_or_missing_facts(facts, text):
    with pytest.raises(ValueError):
        validate_worker_message(text, facts)


def test_template_delivery_and_private_reply_receipt(demo, monkeypatch):
    def unavailable(*args, **kwargs):
        raise LLMError("chat request failed (HTTP 401)")

    monkeypatch.setattr(worker_message, "chat", unavailable)
    store_test_investigation(demo, AMIT_P1)
    delivered = post(demo, AMIT_P1, "ask-worker", {}, RAVI)
    assert delivered.status_code == 200
    detail = delivered.json()
    assert (detail["status"], detail["assigned_to"]) == ("awaiting_worker", "E001")
    assert detail["waiting_since"] == demo.app.state.clock.now().isoformat()
    audit = detail["audit_trail"][-1]
    assert audit["action"] == "worker_message_sent"
    assert audit["actor"] == "system" and audit["after"]["source"] == "template"
    assert audit["reason"] == "chat request failed (HTTP 401)"
    assert audit["after"]["duration_ms"] >= 0

    messages = demo.get("/api/worker/messages", headers=AMIT).json()["items"]
    assert len(messages) == 1
    message = messages[0]
    assert set(message) == {"exception_id", "date", "message", "reply_prompt", "needs_actual_time"}
    assert message["date"] == detail["date"] and message["exception_id"] == AMIT_P1
    assert "Did you leave" in message["message"]
    assert demo.get("/api/worker/messages", headers=MEENA).json() == {"items": [], "notices": []}
    assert_error(demo.get("/api/worker/messages", headers=RAVI), 403, "worker_inbox_only")
    assert_error(
        post(demo, AMIT_P1, "worker-reply", {"confirmed": True}, MEENA), 403, "not_the_worker"
    )

    response = post(demo, AMIT_P1, "worker-reply", {"confirmed": True}, AMIT)
    assert response.status_code == 200
    receipt = response.json()
    review = receipt.pop("time_review")
    assert review["stage"] == "confirmed"
    assert receipt == {
        "exception_id": AMIT_P1,
        "confirmed": True,
        "needs_actual_time": False,
    }
    assert demo.get("/api/worker/messages", headers=AMIT).json() == {"items": [], "notices": []}
    row = get(demo, AMIT_P1)
    assert (row["status"], row["assigned_to"]) == ("awaiting_supervisor", "E101")


def test_no_stays_in_worker_inbox_and_out_of_supervisor_queue(demo, monkeypatch):
    def message(settings, messages, tools, **kwargs):
        import json

        facts = json.loads(messages[1]["content"])
        assert set(facts) == {
            "first_name",
            "date",
            "display_date",
            "issue",
            "proposed_fix",
            "question",
        }
        assert not tools and kwargs["retry_transient"] is False
        return ChatMessage(
            text=f"Hi {facts['first_name']}, on {facts['display_date']}. {facts['question']}"
        )

    monkeypatch.setattr(worker_message, "chat", message)
    store_test_investigation(demo, AMIT_P1)
    delivered = post(demo, AMIT_P1, "ask-worker", {}, RAVI)
    assert delivered.status_code == 200
    assert delivered.json()["audit_trail"][-1]["after"]["source"] == "llm"
    assert_error(
        post(demo, AMIT_P1, "worker-reply", {"confirmed": False}, AMIT), 422, "validation_error"
    )
    text = "I left later after finishing the handover."
    reply = post(demo, AMIT_P1, "worker-reply", {"confirmed": False, "text": text}, AMIT)
    assert reply.status_code == 200 and reply.json()["needs_actual_time"]
    assert get(demo, AMIT_P1)["status"] == "awaiting_worker"
    inbox = demo.get("/api/worker/messages", headers=AMIT).json()["items"]
    assert [item["exception_id"] for item in inbox] == [AMIT_P1]
    assert inbox[0]["needs_actual_time"] is True
    assert "reply_text" not in inbox[0]
    queue = demo.get("/api/exceptions?assigned_to=E101", headers=RAVI).json()["items"]
    assert AMIT_P1 not in {item["id"] for item in queue}
    supervisor = demo.get("/api/exceptions?status=awaiting_supervisor", headers=RAVI).json()[
        "items"
    ]
    assert AMIT_P1 not in {item["id"] for item in supervisor}
    with session_for(demo) as session:
        message = session.scalar(
            select(WorkerMessageRow).where(WorkerMessageRow.exception_id == AMIT_P1)
        )
        assert message.reply_text == text and message.confirmed is False
        assert message.date == date.fromisoformat(inbox[0]["date"])
        assert message.needs_actual_time
    assert_error(
        post(demo, AMIT_P1, "worker-reply", {"confirmed": True}, AMIT),
        409,
        "no_open_worker_question",
    )


def test_ask_worker_requires_an_investigation_routed_to_worker(demo):
    assert_error(post(demo, AMIT_P1, "ask-worker", {}, RAVI), 409, "investigation_required")
    store_test_investigation(demo, MEENA_P5)
    assert_error(post(demo, MEENA_P5, "ask-worker", {}, RAVI), 409, "worker_not_next_contact")


def test_cors_for_vite_exposes_polling_location(client):
    allowed = {"Origin": "http://localhost:5173"}
    preflight = client.options(
        "/api/worker/messages",
        headers={
            **allowed,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Actor-Id",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == allowed["Origin"]
    request = client.get("/api/health", headers=allowed)
    assert request.headers["access-control-expose-headers"] == "Location"
    unknown = client.get("/api/health", headers={"Origin": "https://other.example"})
    assert "access-control-allow-origin" not in unknown.headers
