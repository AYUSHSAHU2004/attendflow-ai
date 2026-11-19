"""Phase 11: the scheduler cycle, its controls and the demo-mode helpers.

No real LLM key and no sleeping: cycles are run directly (`run_once` or run-now) with a
scripted model, a down model, or a model that returns invalid output.
"""

from __future__ import annotations

import json
import threading
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from attendflow.api.app import create_app
from attendflow.cases import service
from attendflow.db.models import (
    AuditLogRow,
    ExceptionRow,
    InvestigationJobRow,
    SchedulerRunRow,
    WorkerMessageRow,
)
from attendflow.llm.client import ChatMessage, LLMError
from attendflow.scheduler import cycle
from tests.api_helpers import (
    AMIT,
    AMIT_P1,
    NEHA_P10,
    PRIYA,
    RAVI,
    SUNITA,
    assert_error,
    session_for,
)
from tests.test_e2e_prototype import good_message, scripted_investigation, scripted_message
from tests.test_ingest import DEVICE, NEHA_IN, NEHA_P1
from tests.test_investigation import final, simulate

NEHA = {"X-Actor-Id": "E004"}


class AnyCaseModel:
    """A scripted model for any number of investigations: simulate the first stored
    option, then return a valid draft."""

    def __init__(self):
        self.calls = 0

    def __call__(self, settings, messages, tools, required, *, deadline, json_output):
        self.calls += 1
        request = json.loads(messages[1]["content"])
        return final(request) if json_output else simulate(request)


class DownModel:
    def __init__(self, failure):
        self.failure = failure
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if isinstance(self.failure, Exception):
            raise self.failure
        return ChatMessage(text=self.failure)


def scheduler(client):
    return client.app.state.scheduler


def configure(client, **changes) -> None:
    sched = scheduler(client)
    sched.deps.settings = replace(sched.deps.settings, **changes)


def run(client) -> dict:
    summary = scheduler(client).run_once("run_now")
    assert summary is not None
    return summary


def open_cases(client) -> list[ExceptionRow]:
    with session_for(client) as s:
        return s.scalars(select(ExceptionRow).where(ExceptionRow.status == "open")).all()


def trail(client, exception_id: str) -> list[tuple]:
    with session_for(client) as s:
        rows = s.scalars(
            select(AuditLogRow)
            .where(AuditLogRow.exception_id == exception_id)
            .order_by(AuditLogRow.id)
        ).all()
    return [(a.action, a.actor) for a in rows]


def punch_neha(client) -> None:
    r = client.post("/api/punches", json=NEHA_IN, headers=DEVICE)
    assert r.status_code == 201, r.text
    assert NEHA_P1 in r.json()["detection"]["new_exception_ids"]


# The system's steps for a new worker-routed case, oldest first.
AUTO_STORY = [
    ("detected", "system"),
    ("auto_investigation_started", "system"),
    ("structured_investigation_started", "agent"),
    ("structured_investigation_finished", "agent"),
    ("investigation_case_stored", "agent"),
    ("auto_investigation_finished", "system"),
    ("ask_worker", "system"),
    ("worker_message_sent", "agent"),
]


# ---------------------------------------------------------------- backlog rule


def test_seeded_backlog_is_left_alone_by_default(demo):
    waiting = len(open_cases(demo))
    summary = run(demo)
    assert summary["status"] == "completed" and summary["detection"] == "ok"
    assert summary["backlog"] is False
    assert summary["new"] == 0 and summary["investigated"] == []
    assert summary["messages_sent"] == [] and summary["errors"] == []
    assert summary["skipped_backlog"] == waiting  # every open case, none investigated yet
    with session_for(demo) as s:
        assert s.get(ExceptionRow, AMIT_P1).investigation_case is None
        assert s.scalar(select(func.count()).select_from(InvestigationJobRow)) == 0
        assert s.scalar(select(func.count()).select_from(WorkerMessageRow)) == 0
        [audit] = s.scalars(select(AuditLogRow).where(AuditLogRow.action == "scheduler_cycle"))
        run_row = s.get(SchedulerRunRow, summary["cycle_id"])
    assert (audit.actor, audit.exception_id) == ("system", None)
    assert audit.after["skipped_backlog"] == waiting
    assert run_row.status == "completed" and run_row.summary["cycle_id"] == summary["cycle_id"]
    # The first cycle set the mark itself because nothing else had.
    assert summary["watermark_audit_id"] > 0


def test_case_from_a_punch_is_handled_in_the_very_next_cycle(demo, monkeypatch):
    run(demo)  # sets the watermark; the seeded cases are backlog
    model = AnyCaseModel()
    scripted_investigation(monkeypatch, model)
    messages = scripted_message(monkeypatch, good_message)

    punch_neha(demo)
    summary = run(demo)
    [done] = summary["investigated"]
    assert done["exception_id"] == NEHA_P1
    assert (done["job_status"], done["fallback"], done["who_to_ask"]) == (
        "completed",
        False,
        "worker",
    )
    assert summary["messages_sent"] == [NEHA_P1]
    assert summary["skipped_budget"] == [] and summary["errors"] == []
    assert summary["skipped_backlog"] == len(open_cases(demo))  # NEHA_P1 left "open"
    assert len(messages) == 1 and model.calls == 2

    inbox = demo.get("/api/worker/messages", headers=NEHA).json()["items"]
    assert [m["exception_id"] for m in inbox] == [NEHA_P1]
    assert inbox[0]["message"].startswith("Hi Neha")
    case = demo.get(f"/api/exceptions/{NEHA_P1}").json()
    assert (case["status"], case["assigned_to"]) == ("awaiting_worker", "E004")
    assert trail(demo, NEHA_P1) == AUTO_STORY
    with session_for(demo) as s:
        ask = s.scalars(
            select(AuditLogRow).where(
                AuditLogRow.exception_id == NEHA_P1, AuditLogRow.action == "ask_worker"
            )
        ).one()
    assert ask.actor_id is None and ask.reason == cycle.AUTO_NOTE

    # A second cycle duplicates nothing.
    again = run(demo)
    assert again["new"] == 0 and again["investigated"] == [] and again["messages_sent"] == []
    assert trail(demo, NEHA_P1) == AUTO_STORY
    with session_for(demo) as s:
        assert s.scalar(select(func.count()).select_from(InvestigationJobRow)) == 1
        assert s.scalar(select(func.count()).select_from(WorkerMessageRow)) == 1
    # Amit's planted case is still untouched for the manual walkthrough.
    assert trail(demo, AMIT_P1) == [("detected", "system")]


def test_backlog_setting_processes_seeded_cases_within_the_budget(demo, monkeypatch):
    configure(
        demo,
        scheduler_backlog=True,
        scheduler_investigations_per_cycle=2,
        scheduler_messages_per_cycle=1,
    )
    scripted_investigation(monkeypatch, DownModel(LLMError("provider down")))
    scripted_message(monkeypatch, LLMError("provider down"))
    waiting = [r.id for r in open_cases(demo)]

    first = run(demo)
    done = [i["exception_id"] for i in first["investigated"]]
    assert len(done) == 2 and first["skipped_backlog"] == 0
    assert set(done) | set(first["skipped_budget"]) == set(waiting)
    assert not set(done) & set(first["skipped_budget"])
    worker_routed = [
        i["exception_id"] for i in first["investigated"] if i["who_to_ask"] == "worker"
    ]
    assert first["messages_sent"] == worker_routed[:1]

    second = run(demo)
    later = [i["exception_id"] for i in second["investigated"]]
    assert len(later) == 2 and not set(later) & set(done)
    assert later == first["skipped_budget"][:2]  # newest first, in the same order


def test_newest_cases_go_first(demo, monkeypatch):
    configure(demo, scheduler_backlog=True, scheduler_investigations_per_cycle=1)
    scripted_investigation(monkeypatch, DownModel(LLMError("provider down")))
    scripted_message(monkeypatch, LLMError("provider down"))
    punch_neha(demo)
    summary = run(demo)
    assert [i["exception_id"] for i in summary["investigated"]] == [NEHA_P1]


def test_a_new_start_moves_the_mark(demo):
    first = run(demo)
    sched = scheduler(demo)
    assert sched.start() is True
    try:
        status = sched.status()
        assert status["running"] is True and status["next_run_at"] is not None
        assert status["watermark"]["set_by"] == "scheduler_start"
        assert status["watermark"]["audit_id"] > first["watermark_audit_id"]
        assert sched.start() is False  # already running
    finally:
        assert sched.stop() is True
    assert sched.status()["running"] is False


# ---------------------------------------------------------------- facts changed / fallback


def test_only_changed_facts_are_investigated_again(demo, monkeypatch):
    run(demo)
    configure(demo, scheduler_messages_per_cycle=0)  # keep the case open
    model = DownModel(LLMError("provider down"))
    scripted_investigation(monkeypatch, model)
    punch_neha(demo)
    first = run(demo)
    assert [i["exception_id"] for i in first["investigated"]] == [NEHA_P1]
    assert first["investigated"][0]["fallback"] is True
    assert first["skipped_message_budget"] == [NEHA_P1]

    # Same facts, template case: not retried (keeps a rate-limited provider quiet).
    assert run(demo)["investigated"] == []

    # New evidence for the same case (a break punch) -> its facts changed -> investigated again.
    r = demo.post(
        "/api/punches",
        json={**NEHA_IN, "timestamp": "2026-04-15T13:00", "type": "break_start"},
        headers=DEVICE,
    )
    assert r.status_code == 201, r.text
    assert ("updated_by_detection", "system") in trail(demo, NEHA_P1)
    again = run(demo)
    assert [i["exception_id"] for i in again["investigated"]] == [NEHA_P1]
    assert run(demo)["investigated"] == []


# ---------------------------------------------------------------- failures


def test_one_failing_case_does_not_stop_the_cycle(demo, monkeypatch):
    configure(demo, scheduler_backlog=True, scheduler_investigations_per_cycle=3)
    scripted_investigation(monkeypatch, DownModel(LLMError("provider down")))
    scripted_message(monkeypatch, LLMError("provider down"))
    jobs = scheduler(demo).deps.jobs
    real_start = jobs.start
    failing = []

    def start(exception_id, actor):
        if not failing:
            failing.append(exception_id)
            raise RuntimeError("secret detail that must not be stored")
        return real_start(exception_id, actor)

    monkeypatch.setattr(jobs, "start", start)
    summary = run(demo)
    assert summary["status"] == "completed"
    assert summary["errors"] == [
        {"exception_id": failing[0], "step": "investigate", "error": "RuntimeError"}
    ]
    assert len(summary["investigated"]) == 3
    assert failing[0] not in [i["exception_id"] for i in summary["investigated"]]


def test_detection_failure_is_recorded_and_the_cycle_finishes(demo, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("down")

    monkeypatch.setattr(service, "run_detection", boom)
    summary = run(demo)
    assert summary["status"] == "failed" and summary["detection"] == "failed"
    assert summary["errors"] == [
        {"exception_id": None, "step": "detection", "error": "RuntimeError"}
    ]
    with session_for(demo) as s:
        assert s.get(SchedulerRunRow, summary["cycle_id"]).status == "failed"


def test_cycle_before_any_data_does_not_crash(client):
    summary = run(client)
    assert summary["status"] == "failed"
    assert summary["errors"][0]["error"].startswith("not_seeded")


@pytest.mark.parametrize(
    "failure",
    [LLMError("HTTP 401 from provider"), "not json at all"],
    ids=["llm_down", "invalid_output"],
)
def test_llm_failure_uses_templates_and_the_cycle_completes(demo, monkeypatch, failure):
    run(demo)
    model = DownModel(failure)
    scripted_investigation(monkeypatch, model)
    scripted_message(monkeypatch, failure if isinstance(failure, Exception) else lambda f: failure)
    punch_neha(demo)
    summary = run(demo)
    assert summary["status"] == "completed" and summary["errors"] == []
    [done] = summary["investigated"]
    assert done["fallback"] is True and done["who_to_ask"] == "worker"
    assert summary["messages_sent"] == [NEHA_P1]
    with session_for(demo) as s:
        [message] = s.scalars(select(WorkerMessageRow))
    assert message.source == "template"
    actions = [a for a, _ in trail(demo, NEHA_P1)]
    assert actions[0] == "detected" and actions[-2:] == ["ask_worker", "worker_message_sent"]
    assert "auto_investigation_finished" in actions


# ---------------------------------------------------------------- overlap


def test_an_overlapping_cycle_is_skipped_not_doubled(demo, monkeypatch):
    sched = scheduler(demo)
    entered, release = threading.Event(), threading.Event()
    real = service.run_detection

    def slow(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return real(*args, **kwargs)

    monkeypatch.setattr(service, "run_detection", slow)
    results = []
    worker = threading.Thread(target=lambda: results.append(sched.run_once("schedule")))
    worker.start()
    assert entered.wait(10)
    assert sched.run_once("schedule") is None  # skipped while the first is running
    assert_error(demo.post("/api/admin/scheduler/run-now", headers=PRIYA), 409, "scheduler_busy")
    assert demo.get("/api/admin/scheduler", headers=PRIYA).json()["cycle_in_progress"] is True
    release.set()
    worker.join(10)
    assert results and results[0]["status"] == "completed"
    assert sched.overlaps_skipped == 2
    with session_for(demo) as s:
        assert s.scalar(select(func.count()).select_from(SchedulerRunRow)) == 1


def test_interrupted_cycles_are_marked_failed(demo):
    from datetime import UTC, datetime

    with session_for(demo) as s, s.begin():
        s.add(SchedulerRunRow(trigger="schedule", status="running", started_at=datetime.now(UTC)))
    assert scheduler(demo).recover_interrupted() == 1
    with session_for(demo) as s:
        assert s.scalars(select(SchedulerRunRow.status)).all() == ["failed"]


# ---------------------------------------------------------------- endpoints


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/admin/scheduler"),
        ("post", "/api/admin/scheduler/run-now"),
        ("post", "/api/admin/scheduler/start"),
        ("post", "/api/admin/scheduler/stop"),
    ],
)
def test_only_the_payroll_admin_controls_the_scheduler(demo, method, path):
    for actor in (RAVI, SUNITA, AMIT, NEHA):
        assert_error(getattr(demo, method)(path, headers=actor), 403, "admin_only")
    assert_error(getattr(demo, method)(path, headers={"X-Actor-Id": "E999"}), 403, "unknown_actor")
    assert_error(getattr(demo, method)(path), 422, "validation_error")
    ok = getattr(demo, method)(path, headers=PRIYA)
    assert ok.status_code == 200, ok.text
    scheduler(demo).stop()


def test_status_and_run_now_for_priya(demo):
    status = demo.get("/api/admin/scheduler", headers=PRIYA).json()
    settings = demo.app.state.settings
    assert status["enabled_setting"] is False and status["running"] is False
    assert status["last_cycle"] is None and status["watermark"] is None
    assert status["interval_seconds"] == settings.scheduler_interval_seconds
    assert status["investigations_per_cycle"] == settings.scheduler_investigations_per_cycle
    assert status["demo_mode"] is False and status["workers"] == []

    summary = demo.post("/api/admin/scheduler/run-now", headers=PRIYA).json()
    assert summary["trigger"] == "run_now" and summary["status"] == "completed"
    status = demo.get("/api/admin/scheduler", headers=PRIYA).json()
    assert status["last_cycle"]["cycle_id"] == summary["cycle_id"]
    assert status["watermark"]["set_by"] == "first_cycle"

    started = demo.post("/api/admin/scheduler/start", headers=PRIYA).json()
    assert started["running"] is True and started["next_run_at"]
    stopped = demo.post("/api/admin/scheduler/stop", headers=PRIYA).json()
    assert stopped["running"] is False and stopped["next_run_at"] is None


def test_scheduler_enabled_starts_with_the_app(db_engine, api_settings):
    app = create_app(replace(api_settings, scheduler_enabled=True), engine=db_engine)
    with TestClient(app, raise_server_exceptions=False) as c:
        assert c.app.state.scheduler.running is True
    assert app.state.scheduler.running is False  # stopped on shutdown


# ---------------------------------------------------------------- demo mode


def test_demo_helpers_do_not_exist_when_demo_mode_is_off(demo):
    for path in ("/api/admin/demo/reset", "/api/admin/demo/punch"):
        assert_error(demo.post(path, json=NEHA_IN, headers=PRIYA), 404, "not_found")
    paths = demo.get("/openapi.json").json()["paths"]
    assert not [p for p in paths if p.startswith("/api/admin/demo")]


def test_demo_reset_and_punch_with_demo_mode_on(demo_client):
    c = demo_client
    # The reset checks the caller against the stored employees, so an empty database is
    # loaded once with POST /api/seed.
    assert_error(c.post("/api/admin/demo/reset", headers=PRIYA), 403, "unknown_actor")
    assert c.post("/api/seed").status_code == 200
    assert_error(c.post("/api/admin/demo/reset", headers=RAVI), 403, "admin_only")
    reset = c.post("/api/admin/demo/reset", headers=PRIYA)
    assert reset.status_code == 200, reset.text
    body = reset.json()
    assert body["detection"]["created"] == body["detection"]["found"] > 0
    status = c.get("/api/admin/scheduler", headers=PRIYA).json()
    assert status["demo_mode"] is True
    assert status["watermark"] == {**status["watermark"], "set_by": "demo_reset"}
    assert status["watermark"]["audit_id"] == body["watermark_audit_id"]
    assert {w["employee_id"] for w in status["workers"]} >= {"E001", "E004"}
    assert all(w["employee_id"] not in {"E101", "E102", "E201"} for w in status["workers"])

    assert_error(c.post("/api/admin/demo/punch", json=NEHA_IN, headers=RAVI), 403, "admin_only")
    r = c.post("/api/admin/demo/punch", json=NEHA_IN, headers=PRIYA)
    assert r.status_code == 201, r.text
    assert NEHA_P1 in r.json()["detection"]["new_exception_ids"]
    assert NEHA_P10 in r.json()["detection"]["closed_exception_ids"]
    with session_for(c) as s:
        [audit] = s.scalars(select(AuditLogRow).where(AuditLogRow.action == "punch_ingested"))
    assert audit.actor == "device"
    assert (audit.after["via"], audit.after["requested_by"]) == ("demo_simulator", "E201")
    assert_error(
        c.post("/api/admin/demo/punch", json=NEHA_IN, headers=PRIYA), 409, "duplicate_punch"
    )

    # A second reset wipes the punch and its case.
    assert c.post("/api/admin/demo/reset", headers=PRIYA).status_code == 200
    assert c.get(f"/api/exceptions/{NEHA_P1}").status_code == 404
