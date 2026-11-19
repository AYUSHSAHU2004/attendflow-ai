"""Phase 11 end to end, through the HTTP API only, with DEMO_MODE on and a scripted LLM.

Priya resets the demo, sends the agreed simulated punch (Neha clocks in on Wed 15 Apr and
never clocks out), and runs one scheduler cycle. Nobody clicks Investigate or Ask: the new
P1 is detected, investigated and sent to Neha by the system, Priya's counters move, and
the audit trail shows every automatic step in order. The data-safety hook proves that
only the seed, fixes/apply.py and the ingest module wrote source data.
"""

from __future__ import annotations

from sqlalchemy import select

from attendflow.db.models import AuditLogRow
from tests.api_helpers import AMIT_P1, NEHA_P10, PRIYA, session_for
from tests.test_admin import detail, overview
from tests.test_e2e_prototype import (  # noqa: F401 - write_log is a fixture
    assert_writes_audited,
    good_message,
    run_main_story,
    scripted_investigation,
    scripted_message,
    write_log,
)
from tests.test_ingest import NEHA_IN, NEHA_P1
from tests.test_scheduler import AUTO_STORY, AnyCaseModel

NEHA = {"X-Actor-Id": "E004"}


def counters(client) -> dict:
    return overview(client)["counters"]


def test_a_simulated_punch_is_detected_investigated_and_sent_without_clicks(
    demo_client,
    write_log,  # noqa: F811 - the imported fixture
    monkeypatch,
):
    c = demo_client
    assert c.post("/api/seed").status_code == 200  # empty test DB: load the employees once
    reset = c.post("/api/admin/demo/reset", headers=PRIYA)
    assert reset.status_code == 200, reset.text
    before = counters(c)
    assert before["total"] == reset.json()["detection"]["found"]

    model = AnyCaseModel()
    scripted_investigation(monkeypatch, model)
    messages = scripted_message(monkeypatch, good_message)

    # 1. The simulated punch: stored, audited, and detection opens a fresh P1.
    punch = c.post("/api/admin/demo/punch", json=NEHA_IN, headers=PRIYA)
    assert punch.status_code == 201, punch.text
    detection = punch.json()["detection"]
    assert detection["new_exception_ids"] == [NEHA_P1]
    assert detection["closed_exception_ids"] == [NEHA_P10]
    [item] = overview(c, employee_id="E004", policy_id="P1")["items"]
    assert (item["status"], item["investigated"]) == ("open", False)

    # 2. One scheduler cycle does the rest.
    cycle = c.post("/api/admin/scheduler/run-now", headers=PRIYA)
    assert cycle.status_code == 200, cycle.text
    summary = cycle.json()
    assert summary["status"] == "completed" and summary["errors"] == []
    assert [i["exception_id"] for i in summary["investigated"]] == [NEHA_P1]
    assert summary["messages_sent"] == [NEHA_P1]
    assert summary["skipped_backlog"] > 0  # the seeded cases were left alone
    assert len(messages) == 1

    [item] = overview(c, employee_id="E004", policy_id="P1")["items"]
    assert item["investigated"] is True and item["who_to_ask"] == "worker"
    assert item["investigation_fallback"] is False
    assert (item["status"], item["assigned_to"]) == ("awaiting_worker", "E004")

    inbox = c.get("/api/worker/messages", headers=NEHA).json()["items"]
    assert [m["exception_id"] for m in inbox] == [NEHA_P1]

    # 3. Priya's counters: one new case (now with the worker), Neha's P10 closed.
    after = counters(c)
    assert after["total"] == before["total"] + 1
    assert after["open"] == before["open"] - 1
    assert after["awaiting_worker"] == before["awaiting_worker"] + 1
    assert after["resolved"] == before["resolved"] + 1

    # 4. The system's steps, in order: on the case, and around it.
    case = detail(c, NEHA_P1)
    assert [(a["action"], a["actor"]) for a in case["audit_trail"]] == AUTO_STORY
    summaries = {a["action"]: a["summary"] for a in case["audit_trail"]}
    assert "(automatic)" in summaries["ask_worker"]
    assert "validated model draft" in summaries["auto_investigation_finished"]
    assert case["investigation"]["who_to_ask"] == "worker"
    with session_for(c) as s:
        rows = s.scalars(select(AuditLogRow).order_by(AuditLogRow.id)).all()
    ids = {
        key: next(a.id for a in rows if (a.action, a.exception_id) == key)
        for key in [
            ("punch_ingested", None),
            ("detected", NEHA_P1),
            ("no_longer_detected", NEHA_P10),
            ("post_punch_detection", None),
            ("auto_investigation_started", NEHA_P1),
            ("ask_worker", NEHA_P1),
            ("scheduler_cycle", None),
        ]
    }
    order = list(ids.values())
    assert order == sorted(order), ids
    ingested = next(a for a in rows if a.action == "punch_ingested")
    assert (ingested.actor, ingested.after["via"]) == ("device", "demo_simulator")

    # 5. Nothing else was touched, and a second cycle duplicates nothing.
    assert [a["action"] for a in detail(c, AMIT_P1)["audit_trail"]] == ["detected"]
    again = c.post("/api/admin/scheduler/run-now", headers=PRIYA).json()
    assert again["new"] == 0 and again["investigated"] == [] and again["messages_sent"] == []
    assert counters(c) == after

    # 6. Data safety: the seed, the ingest module, and fixes/apply.py only for the P2
    # auto-resolve that detection does on every reset. Nothing the scheduler did wrote data.
    assert {e["writer"] for e in write_log} == {"seed", "apply", "ingest"}
    auto = {
        i["exception_id"] for i in overview(c, status="resolved")["items"] if i["auto_resolved"]
    }
    assert {e["exception_id"] for e in write_log if e["writer"] == "apply"} <= auto
    assert_writes_audited(c, write_log)


def test_data_safety_with_all_three_writers(demo_client, write_log, monkeypatch):  # noqa: F811
    """Amit's full approval story (fixes/apply.py) plus a device punch (ingest): every
    source write came from one of the three allowed writers and is audited."""
    run_main_story(demo_client, monkeypatch)
    punch = demo_client.post("/api/admin/demo/punch", json=NEHA_IN, headers=PRIYA)
    assert punch.status_code == 201, punch.text
    assert {e["writer"] for e in write_log} == {"seed", "apply", "ingest"}
    assert_writes_audited(demo_client, write_log)


# ---------------------------------------------------------------- Phase 13: no reply


def _clock(client, hours: float) -> dict:
    r = client.post("/api/admin/demo/clock", json={"hours": hours}, headers=PRIYA)
    assert r.status_code == 200, r.text
    return r.json()


def _cycle(client) -> dict:
    r = client.post("/api/admin/scheduler/run-now", headers=PRIYA)
    assert r.status_code == 200, r.text
    assert r.json()["errors"] == []
    return r.json()["no_reply"]


def test_silence_climbs_the_ladder_without_changing_data(demo_client, write_log):  # noqa: F811
    """Neha clocks in and never answers: reminder, then Ravi, then Priya. Templates only
    (no LLM key), the scheduler timer off, only HTTP. Silence writes no source data."""
    c = demo_client
    assert c.post("/api/seed").status_code == 200
    assert c.post("/api/admin/demo/reset", headers=PRIYA).status_code == 200
    assert c.post("/api/admin/demo/punch", json=NEHA_IN, headers=PRIYA).status_code == 201
    first = c.post("/api/admin/scheduler/run-now", headers=PRIYA).json()
    assert first["messages_sent"] == [NEHA_P1]
    writes_before = len(write_log)

    hint = _clock(c, 8)["hint"]
    assert hint == "Run the scheduler (or wait for the next cycle) to apply."
    assert _cycle(c)["reminded"] == [NEHA_P1]
    [message] = c.get("/api/worker/messages", headers=NEHA).json()["items"]
    assert message["reminder"]["text"].startswith(
        "Reminder: we still need your answer about Wed 15 Apr."
    )

    _clock(c, 16)
    assert _cycle(c)["to_supervisor"] == [NEHA_P1]
    queue = c.get("/api/supervisor/queue", headers={"X-Actor-Id": "E101"}).json()["items"]
    [item] = [i for i in queue if i["exception_id"] == NEHA_P1]
    assert item["no_reply"]["note"] == "Neha Gupta has not replied for 24 h."

    _clock(c, 24)
    assert _cycle(c)["to_admin"] == [NEHA_P1]
    [item] = overview(c, no_reply="payroll_admin")["items"]
    assert (item["exception_id"], item["status"], item["assigned_to"]) == (
        NEHA_P1,
        "escalated",
        "E201",
    )
    assert counters(c)["stuck"] == 1
    trail = [a["action"] for a in detail(c, NEHA_P1)["audit_trail"]]
    assert trail[-3:] == ["no_reply_reminder", "no_reply_to_supervisor", "no_reply_to_admin"]

    # Amit's planted P1 was never touched; the ladder wrote no source data at all.
    assert [a["action"] for a in detail(c, AMIT_P1)["audit_trail"]] == ["detected"]
    assert write_log[writes_before:] == []
    assert_writes_audited(c, write_log)
