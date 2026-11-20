"""Phase 17: GET /api/worker/history, "what happened to my case" (worker-scoped, read-only)."""

from __future__ import annotations

from tests.api_helpers import (
    AMIT,
    AMIT_P1,
    PRIYA,
    RAVI,
    assert_error,
    audit_count,
    confirm_amit_clock_out,
    post,
    snapshot,
    store_test_investigation,
)
from tests.test_no_reply import REASON, clock_out_option, to_stage

NEHA = {"X-Actor-Id": "E004"}


def history(client, actor=AMIT) -> list[dict]:
    r = client.get("/api/worker/history", headers=actor)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_only_workers_and_only_their_own_cases(demo):
    for actor in (RAVI, PRIYA):
        r = demo.get("/api/worker/history", headers=actor)
        assert r.status_code == 403
        assert_error(r, 403, "worker_inbox_only")
    assert_error(
        demo.get("/api/worker/history", headers={"X-Actor-Id": "E999"}), 403, "unknown_actor"
    )
    assert history(demo) == []  # nothing asked yet
    store_test_investigation(demo, AMIT_P1)
    assert post(demo, AMIT_P1, "ask-worker", {}, RAVI).status_code == 200
    [item] = history(demo)
    assert item["exception_id"] == AMIT_P1
    assert item["outcome"] == {
        "state": "waiting_for_you",
        "text": "Waiting for your answer.",
        "reason": None,
    }
    assert item["questions"][0]["answer"] is None
    assert history(demo, NEHA) == []  # Neha never sees Amit's case


def test_yes_then_approve_reads_as_fixed_with_the_confirmed_time(demo):
    before_audit = audit_count(demo)
    confirm_amit_clock_out(demo)
    [item] = history(demo)
    assert item["outcome"]["state"] == "with_supervisor"
    [question] = item["questions"]
    assert question["answer"]["confirmed"] is True
    option = clock_out_option(demo)["option_id"]
    ok = post(demo, AMIT_P1, "approve", {"option_id": option}, RAVI)
    assert ok.status_code == 200, ok.text
    [item] = history(demo)
    assert item["outcome"] == {
        "state": "fixed",
        "text": "Fixed: Set clock-out to 18:00.",
        "reason": None,
    }
    # Reading the history writes nothing.
    data, audit = snapshot(demo), audit_count(demo)
    history(demo)
    assert snapshot(demo) == data and audit_count(demo) == audit > before_audit


def test_a_no_with_a_time_keeps_the_worker_words_and_time(demo):
    confirm_amit_clock_out(demo, time="17:45")
    [item] = history(demo)
    [question] = item["questions"]
    assert question["answer"]["confirmed"] is False
    assert question["answer"]["text"] == "I left late."
    assert question["answer"]["time"] == "17:45"


def test_decided_without_reply_shows_the_reason_and_a_reject_does_not(demo):
    to_stage(demo, 2)
    option = clock_out_option(demo)["option_id"]
    body = {
        "option_id": option,
        "reason": REASON,
        "without_worker": True,
        "confirm_time_without_worker": True,
    }
    assert post(demo, AMIT_P1, "approve", body, RAVI).status_code == 200
    [item] = history(demo)
    assert item["outcome"]["state"] == "decided_without_reply"
    assert item["outcome"]["text"] == "Decided without your reply: Set clock-out to 18:00."
    assert item["outcome"]["reason"] == REASON
    assert item["questions"][0]["reminded_at"] is not None


def test_a_reject_reads_as_with_payroll_without_the_reason(demo):
    store_test_investigation(demo, AMIT_P1)
    assert post(demo, AMIT_P1, "ask-worker", {}, RAVI).status_code == 200
    assert post(demo, AMIT_P1, "worker-reply", {"confirmed": True}, AMIT).status_code == 200
    secret = "Supervisor-only note about the gate camera."
    assert post(demo, AMIT_P1, "reject", {"reason": secret}, RAVI).status_code == 200
    [item] = history(demo)
    assert item["outcome"] == {
        "state": "with_payroll",
        "text": "Payroll is reviewing it.",
        "reason": None,
    }
    assert secret not in str(item)
