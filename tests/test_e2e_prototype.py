"""Phase 10: the prototype end to end, through the HTTP API only.

1. Amit's main story with scripted LLM clients at every LLM step (investigation, worker
   message, time extraction). No real key is needed.
2. The reject path: Ravi rejects Meena's P5, Priya's reject is final.
3. The failure paths: the LLM is down, or returns invalid output, at every step. The
   flow still completes with the template and the manual time field.
4. Data safety: every write to timecards, schedule or leave came from fixes/apply.py,
   the punch ingest module (Phase 11, INSERT only, each with a punch_ingested audit row) (or
   the seed), and every fix write has a matching audit row.

Numbers (hours, counts) are read from the engine's stored results and the database,
never hard-coded.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import event, select, text

from attendflow.agent import jobs
from attendflow.agent.structured import investigate
from attendflow.cases import worker_message
from attendflow.db.models import AuditLogRow, PunchRow
from attendflow.llm.client import ChatMessage, LLMError
from tests.api_helpers import (
    AMIT,
    AMIT_P1,
    MEENA_P5,
    PRIYA,
    RAVI,
    SUNITA,
    assert_error,
    post,
    session_for,
    snapshot,
)
from tests.test_admin import db_counts, detail, overview
from tests.test_investigation import Model, final, simulate
from tests.test_worker_time import fake_model, output

CLOCK_OUT = "set_clock_out_to_scheduled_end"
TEXT = "stayed late to unload the truck, left around 7:30ish"
SOURCE_TABLES = ("timecards", "schedule", "leave_records", "leave_balances")
WRITE = re.compile(
    r'^\s*(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE(?:\s+TABLE)?)\s+"?(\w+)"?', re.I
)
APPLY_FILE = str(Path("attendflow", "fixes", "apply.py"))
SEED_FILE = str(Path("attendflow", "db", "seed.py"))
INGEST_FILE = str(Path("attendflow", "ingest", "punches.py"))
FIX_ACTIONS = ("approve", "edit_and_approve", "auto_resolve", "auto_resolve_undone")

# An investigation job journals its start and end, then stores the case.
INVESTIGATION = [
    ("structured_investigation_started", "agent", None),
    ("structured_investigation_finished", "agent", None),
    ("investigation_case_stored", "agent", None),
]
# The exact audit story of Amit's P1, oldest first: (action, actor, actor_id).
AMIT_STORY = [
    ("detected", "system", None),
    *INVESTIGATION,
    ("ask_worker", "supervisor", "E101"),
    ("worker_message_sent", "agent", None),
    ("worker_reply", "worker", "E001"),
    ("worker_time_extracted", "agent", None),
    ("worker_time_confirmed", "worker", "E001"),
    ("approve", "supervisor", "E101"),
    ("post_fix_detection", "system", None),
]


# ---------------------------------------------------------------- scripted LLM clients


def scripted_investigation(monkeypatch, model) -> None:
    monkeypatch.setattr(
        jobs, "investigate", lambda *a, **kw: investigate(*a, **kw, chat_model=model)
    )


def scripted_message(monkeypatch, reply) -> list:
    """Worker-message model. `reply` is a function of the facts, or an exception."""
    calls = []

    def chat(settings, messages, tools, **kwargs):
        assert tools == [] and kwargs["retry_transient"] is False
        facts = json.loads(messages[1]["content"])
        calls.append(facts)
        if isinstance(reply, Exception):
            raise reply
        return ChatMessage(text=reply(facts))

    monkeypatch.setattr(worker_message, "chat", chat)
    return calls


def good_message(facts: dict) -> str:
    return f"Hi {facts['first_name']}, about {facts['display_date']}. {facts['question']}"


class Broken:
    """A model that always fails the same way: an exception, or the same invalid text."""

    def __init__(self, failure):
        self.failure = failure
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if isinstance(self.failure, Exception):
            raise self.failure
        return ChatMessage(text=self.failure)


# ---------------------------------------------------------------- write log (data safety)


def _fix_owner(frame) -> str | None:
    """The exception a frame of fixes/apply.py is writing for."""
    loc = frame.f_locals
    for name in ("exc", "self", "ctx"):
        value = loc.get(name)
        exc = value if name == "exc" else getattr(value, "exc", None)
        if exc is not None and hasattr(exc, "policy_id"):
            return exc.id
    return None


@pytest.fixture
def write_log(client):
    """Every SQL write to a source table, with the code that caused it."""
    log: list[dict] = []

    def hook(conn, cursor, statement, parameters, context, executemany):
        match = WRITE.match(statement)
        if not match or match.group(1).lower() not in SOURCE_TABLES:
            return
        entry = {"table": match.group(1).lower(), "sql": statement.split()[0].upper()}
        frame = sys._getframe()
        while frame is not None:
            filename = frame.f_code.co_filename
            if filename.endswith(APPLY_FILE):
                owner = _fix_owner(frame)
                if owner:
                    entry["writer"], entry["exception_id"] = "apply", owner
                    break
            if filename.endswith(SEED_FILE):
                entry["writer"] = "seed"
                break
            if filename.endswith(INGEST_FILE):
                entry["writer"] = "ingest"
                break
            frame = frame.f_back
        else:
            entry["writer"] = None
        log.append(entry)

    engine = client.app.state.engine
    event.listen(engine, "before_cursor_execute", hook)
    yield log
    event.remove(engine, "before_cursor_execute", hook)


def assert_writes_audited(client, log: list[dict]) -> None:
    """Only fixes/apply.py, the seed and the ingest module wrote source data; every fix
    write and every ingested punch is audited."""
    unknown = [entry for entry in log if entry["writer"] is None]
    assert not unknown, unknown
    ingest = [e for e in log if e["writer"] == "ingest"]
    # The ingest module only ever INSERTs into timecards, once per stored punch, and each
    # stored device punch that is not in the seed has its own punch_ingested audit row.
    assert {(e["table"], e["sql"]) for e in ingest} <= {("timecards", "INSERT")}, ingest
    seeded = {
        row["punch_id"]
        for row in csv.DictReader(
            (client.app.state.settings.data_dir / "timecards.csv").open(encoding="utf-8")
        )
    }
    with session_for(client) as s:
        ingested = s.scalars(
            select(AuditLogRow)
            .where(AuditLogRow.action == "punch_ingested")
            .order_by(AuditLogRow.id)
        ).all()
        devices = {
            p.punch_id: p
            for p in s.scalars(select(PunchRow).where(PunchRow.source != "correction"))
            if p.punch_id not in seeded
        }
    assert len(ingest) == len(ingested), (ingest, ingested)
    assert {a.after["punch_id"] for a in ingested} == set(devices)
    for audit in ingested:
        punch = devices[audit.after["punch_id"]]
        assert (audit.actor, audit.actor_id, audit.exception_id) == ("device", None, None)
        assert audit.after["timestamp"] == punch.timestamp.isoformat(timespec="seconds")
        assert (audit.after["employee_id"], audit.after["type"]) == (punch.employee_id, punch.type)
    written = {e["exception_id"] for e in log if e["writer"] == "apply"}
    with session_for(client) as s:
        audits = s.scalars(
            select(AuditLogRow).where(AuditLogRow.action.in_(FIX_ACTIONS)).order_by(AuditLogRow.id)
        ).all()
        changed = {}
        for a in audits:
            after = a.after or {}
            changes = (after.get("applied_fix") or {}).get("changes") or after.get("changes") or []
            if changes:
                changed.setdefault(a.exception_id, []).extend(changes)
        touched = s.scalars(
            select(PunchRow).where(
                (PunchRow.created_by_exception.is_not(None))
                | (PunchRow.voided_by_exception.is_not(None))
            )
        ).all()
    # Each exception whose fix wrote data has an audit row listing those changes, and
    # each audited change was really written.
    assert written == set(changed), (written, set(changed))
    for punch in touched:
        owner = punch.created_by_exception or punch.voided_by_exception
        assert owner in changed, punch.punch_id
        assert punch.punch_id in json.dumps(changed[owner]), (punch.punch_id, owner)


# ---------------------------------------------------------------- shared steps


def seed_and_detect(client) -> dict:
    assert client.post("/api/seed").status_code == 200
    run = client.post("/api/detection/run")
    assert run.status_code == 200, run.text
    return run.json()


def assert_counters_match_db(client) -> dict:
    counters = overview(client)["counters"]
    assert counters == db_counts(client)
    return counters


def run_investigation(client, exception_id: str, headers) -> dict:
    started = post(client, exception_id, "investigate", {}, headers)
    assert started.status_code == 202, started.text
    job = client.get(started.headers["Location"], headers=headers).json()
    assert job["status"] == "completed", job
    return job


def audit_story(client, exception_id: str) -> list[tuple]:
    trail = detail(client, exception_id)["audit_trail"]
    ids = [a["id"] for a in trail]
    assert ids == sorted(ids)
    return [(a["action"], a["actor"], a["actor_id"]) for a in trail]


def approve_amit(client) -> dict:
    """Ravi sees the case with the stored re-check and approves it; returns the result."""
    queue = client.get("/api/supervisor/queue", headers=RAVI).json()["items"]
    assert AMIT_P1 in [i["exception_id"] for i in queue]
    card = client.get(f"/api/supervisor/cases/{AMIT_P1}", headers=RAVI).json()
    [option] = card["options"]
    assert option["consequence"]["source"] == "worker_recheck"
    assert option["consequence"]["creates_violations"] is True
    approved = post(client, AMIT_P1, "approve", {"option_id": CLOCK_OUT}, RAVI)
    assert approved.status_code == 200, approved.text
    return approved.json()


def assert_amit_fixed(client, result: dict, before: dict) -> None:
    """Correction punch at the confirmed time, new P3 and P5, Priya's list updated."""
    stored = detail(client, AMIT_P1)
    recheck = stored["recheck"]
    stamp = recheck["timestamp"]
    assert result["status"] == "resolved"
    assert result["applied_fix"]["params"]["timestamp"] == stamp
    with session_for(client) as s:
        [punch] = s.scalars(select(PunchRow).where(PunchRow.created_by_exception == AMIT_P1)).all()
    assert (punch.type, punch.source) == ("out", "correction")
    assert punch.timestamp == datetime.fromisoformat(stamp)

    new_ids = result["detection"]["new_exception_ids"]
    expected = {(v["policy_id"], v["kind"]) for v in recheck["result"]["new_violations"]}
    assert {p for p, _ in expected} == {"P3", "P5"}
    after = overview(client)
    items = {i["exception_id"]: i for i in after["items"]}
    assert {(items[i]["policy_id"], items[i]["kind"]) for i in new_ids} == expected
    assert all(items[i]["status"] == "open" and items[i]["employee_id"] == "E001" for i in new_ids)
    assert items[AMIT_P1]["status"] == "resolved"
    p3 = detail(client, next(i for i in new_ids if items[i]["policy_id"] == "P3"))
    assert p3["details"]["worked_hours"] == recheck["result"]["day_worked_hours"]

    counters = assert_counters_match_db(client)
    assert counters["total"] == before["total"] + len(new_ids)
    assert counters["resolved"] == before["resolved"] + 1
    assert counters["open"] == before["open"] - 1 + len(new_ids)
    assert counters["auto_resolved"] == before["auto_resolved"]


# ---------------------------------------------------------------- 1. the main story


def run_main_story(client, monkeypatch) -> None:
    run = seed_and_detect(client)

    # Priya's list and counters before anything happens.
    before = assert_counters_match_db(client)
    assert before["total"] == run["found"]
    assert before["auto_resolved"] == run["auto_resolved"] == before["resolved"]
    assert before["open"] == before["total"] - before["resolved"]
    [amit] = overview(client, employee_id="E001", policy_id="P1")["items"]
    assert (amit["exception_id"], amit["status"], amit["investigated"]) == (AMIT_P1, "open", False)

    # Investigate with a scripted model that simulates the fix, then drafts the case.
    model = Model(simulate, final)
    scripted_investigation(monkeypatch, model)
    job = run_investigation(client, AMIT_P1, RAVI)
    assert job["reason"] == "validated"
    case = detail(client, AMIT_P1)
    assert case["investigation"]["fallback"] is False
    assert case["investigation"]["who_to_ask"] == "worker"
    assert [c["tool_name"] for c in case["tool_calls"]][-1] == "run_checks"

    # Ask Amit; the scripted model phrases the question from verified facts.
    messages = scripted_message(monkeypatch, good_message)
    assert post(client, AMIT_P1, "ask-worker", {}, RAVI).status_code == 200
    assert len(messages) == 1
    inbox = client.get("/api/worker/messages", headers=AMIT).json()["items"]
    assert [m["exception_id"] for m in inbox] == [AMIT_P1]
    assert inbox[0]["message"].startswith("Hi Amit")

    # Amit says No with free text; the scripted extraction reads an approximate 19:30.
    extraction = fake_model(monkeypatch, output("19:30", approximate=True))
    reply = post(client, AMIT_P1, "worker-reply", {"confirmed": False, "text": TEXT}, AMIT)
    assert reply.status_code == 200, reply.text
    review = reply.json()["time_review"]
    assert review["stage"] == "candidate" and review["timestamp"][11:16] == "19:30"
    assert len(extraction) == 1
    assert AMIT_P1 not in [
        i["exception_id"] for i in client.get("/api/supervisor/queue", headers=RAVI).json()["items"]
    ]
    confirmed = post(client, AMIT_P1, "worker-confirm-time", {}, AMIT)
    assert confirmed.status_code == 200, confirmed.text
    recheck = detail(client, AMIT_P1)["recheck"]
    assert recheck["source"] == "llm" and recheck["approximate"] is True

    # Ravi approves; the timecard, the new exceptions and Priya's list all follow.
    result = approve_amit(client)
    assert_amit_fixed(client, result, before)

    # A second detection run creates nothing new (no duplicates).
    assert client.post("/api/detection/run").json()["created"] == 0
    assert_counters_match_db(client)

    # The full audit trail, exactly and in order.
    assert audit_story(client, AMIT_P1) == AMIT_STORY
    trail = detail(client, AMIT_P1)["audit_trail"]
    approve = next(a for a in trail if a["action"] == "approve")
    assert approve["before_summary"] == "awaiting supervisor, with Ravi Kumar"
    assert approve["after_summary"] == "resolved, with Ravi Kumar"
    assert recheck["timestamp"][11:16] in approve["summary"]


def test_main_story_end_to_end(client, monkeypatch):
    run_main_story(client, monkeypatch)


# ---------------------------------------------------------------- 2. the reject path


def run_reject_path(client, monkeypatch) -> None:
    monkeypatch.setattr(
        jobs, "investigate", lambda *a, **kw: investigate(*a, **kw, fallback_only=True)
    )
    sources = snapshot(client)
    before = assert_counters_match_db(client)
    run_investigation(client, MEENA_P5, RAVI)
    assert MEENA_P5 in [
        i["exception_id"] for i in client.get("/api/supervisor/queue", headers=RAVI).json()["items"]
    ]

    reason = "Overtime was never agreed for this week"
    rejected = post(client, MEENA_P5, "reject", {"reason": reason}, RAVI)
    assert rejected.status_code == 200, rejected.text
    assert (rejected.json()["status"], rejected.json()["assigned_to"]) == ("escalated", "E201")

    # Ravi can no longer touch it; Sunita never could.
    for who in (RAVI, SUNITA):
        assert_error(
            client.get(f"/api/supervisor/cases/{MEENA_P5}", headers=who), 403, "not_assigned"
        )
        assert_error(post(client, MEENA_P5, "reject", {"reason": reason}, who), 403, "not_assigned")
    assert_error(
        post(client, MEENA_P5, "approve", {"option_id": "approve_overtime"}, RAVI),
        403,
        "not_assigned",
    )

    # Priya sees it, marked for her decision, with Ravi's reason.
    [item] = overview(client, status="escalated")["items"]
    assert item["exception_id"] == MEENA_P5 and item["needs_your_decision"]
    case = detail(client, MEENA_P5)
    assert case["audit_trail"][-1]["reason"] == reason
    counters = assert_counters_match_db(client)
    assert counters["escalated"] == before["escalated"] + 1
    assert counters["open"] == before["open"] - 1

    # Priya opens the same supervisor card and rejects: final.
    card = client.get(f"/api/supervisor/cases/{MEENA_P5}", headers=PRIYA)
    assert card.status_code == 200
    final_reason = "Agree with Ravi: no overtime this week"
    closed = post(client, MEENA_P5, "reject", {"reason": final_reason}, PRIYA)
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "rejected"
    assert_error(
        post(client, MEENA_P5, "reject", {"reason": final_reason}, PRIYA), 409, "invalid_transition"
    )
    counters = assert_counters_match_db(client)
    assert counters["rejected"] == before["rejected"] + 1
    assert counters["escalated"] == before["escalated"]
    assert audit_story(client, MEENA_P5) == [
        ("detected", "system", None),
        *INVESTIGATION,
        ("reject_and_escalate", "supervisor", "E101"),
        ("reject", "admin", "E201"),
    ]
    assert detail(client, MEENA_P5)["audit_trail"][-1]["reason"] == final_reason
    assert snapshot(client) == sources  # a reject never changes data


def test_reject_path_ends_with_priyas_final_decision(client, monkeypatch):
    seed_and_detect(client)
    run_reject_path(client, monkeypatch)


# ---------------------------------------------------------------- 3. failure paths


@pytest.mark.parametrize("mode", ["down", "invalid"])
def test_flow_completes_when_the_llm_fails_at_every_step(client, monkeypatch, mode):
    down = LLMError("chat request failed (HTTP 503)")
    seed_and_detect(client)
    before = assert_counters_match_db(client)

    # Investigation: the model is down, or keeps returning a draft that is not JSON.
    model = Broken(down if mode == "down" else "{this is not json")
    scripted_investigation(monkeypatch, model)
    job = run_investigation(client, AMIT_P1, RAVI)
    assert model.calls >= 1
    case = detail(client, AMIT_P1)["investigation"]
    assert case["fallback"] is True and case["confidence"] == "low"
    stored = detail(client, AMIT_P1)["audit_trail"][-1]
    assert stored["action"] == "investigation_case_stored"
    assert job["reason"] == ("llm_error" if mode == "down" else "validation_failed")
    assert "engine template" in stored["summary"] and job["reason"] in stored["summary"]

    # Worker message: down, or a message that invents numbers. The template is sent.
    scripted_message(
        monkeypatch, down if mode == "down" else (lambda facts: "Hi, you worked 23 hours on 1 Jan.")
    )
    assert post(client, AMIT_P1, "ask-worker", {}, RAVI).status_code == 200
    sent = detail(client, AMIT_P1)["audit_trail"][-1]
    assert (sent["action"], sent["actor"]) == ("worker_message_sent", "system")
    assert sent["reason"] and "template" in sent["summary"]
    [message] = detail(client, AMIT_P1)["worker_messages"]
    assert message["source"] == "template"

    # Extraction: down (manual form at once) or invalid twice (one correction, then manual).
    if mode == "down":
        fake_model(monkeypatch, down)
    else:
        fake_model(monkeypatch, "not json at all", "still not json")
    reply = post(client, AMIT_P1, "worker-reply", {"confirmed": False, "text": TEXT}, AMIT)
    assert reply.status_code == 200, reply.text
    assert reply.json()["time_review"]["stage"] == "manual"
    actions = [a["action"] for a in detail(client, AMIT_P1)["audit_trail"]]
    if mode == "invalid":
        assert actions.count("worker_time_extraction_rejected") == 2
    extracted = next(
        a
        for a in reversed(detail(client, AMIT_P1)["audit_trail"])
        if a["action"] == "worker_time_extracted"
    )
    assert extracted["reason"] and "manual time field" in extracted["summary"]
    assert_error(post(client, AMIT_P1, "worker-confirm-time", {}, AMIT), 409, "no_time_candidate")

    # Amit types the time; the flow completes exactly as with a working model.
    typed = post(client, AMIT_P1, "worker-manual-time", {"time": "19:30"}, AMIT)
    assert typed.status_code == 200, typed.text
    recheck = detail(client, AMIT_P1)["recheck"]
    assert recheck["source"] == "manual" and recheck["approximate"] is False
    result = approve_amit(client)
    assert_amit_fixed(client, result, before)
    story = [a for a, _, _ in audit_story(client, AMIT_P1)]
    # The audit says which model step failed and that the fallback was used.
    failure = "structured_model_failed" if mode == "down" else "structured_draft_rejected"
    assert failure in story
    assert story.index("structured_investigation_started") < story.index(failure)
    assert story.index(failure) < story.index("investigation_case_stored")
    assert story[0] == "detected"
    assert story[-4:] == [
        "worker_time_extracted",
        "worker_time_confirmed",
        "approve",
        "post_fix_detection",
    ]


# ---------------------------------------------------------------- 4. data safety


def test_only_apply_wrote_source_data_and_every_write_is_audited(client, monkeypatch, write_log):
    run_main_story(client, monkeypatch)
    run_reject_path(client, monkeypatch)
    writers = {e["writer"] for e in write_log}
    assert writers == {"seed", "apply"}, writers
    fixed = {e["exception_id"] for e in write_log if e["writer"] == "apply"}
    # Amit's approval and the P2 auto-resolve wrote data; the rejects wrote nothing.
    assert AMIT_P1 in fixed and MEENA_P5 not in fixed
    with session_for(client) as s:
        auto = set(
            s.execute(
                text("SELECT id FROM exceptions WHERE auto_resolved AND policy_id = 'P2'")
            ).scalars()
        )
    assert auto and auto <= fixed
    assert_writes_audited(client, write_log)


def test_the_write_log_catches_a_write_outside_apply(client, write_log):
    """The guard itself works: a direct write from test code is flagged."""
    seed_and_detect(client)
    with session_for(client) as s, s.begin():
        s.get(PunchRow, "P0001").location = "Somewhere else"
    rogue = [e for e in write_log if e["writer"] is None]
    assert rogue == [{"table": "timecards", "sql": "UPDATE", "writer": None}]
