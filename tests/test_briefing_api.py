"""Phase 17: the daily briefing over the API (real PostgreSQL).

Facts packet scope and numbers, permissions, caching by facts hash, the rate limits, the
scheduled briefing, the leak check with LLM diagnostics on, and data safety. The model is
always a scripted fake (`attendflow.briefing.generate.chat` is replaced); no test
contacts a provider.
"""

from __future__ import annotations

import contextlib
import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from attendflow.api.app import create_app
from attendflow.briefing import generate as gen_module
from attendflow.briefing import service as briefing_service
from attendflow.briefing.facts import build_packet
from attendflow.briefing.generate import SYSTEM_PROMPT
from attendflow.briefing.validate import template_draft
from attendflow.db.models import AuditLogRow, BriefingRow
from attendflow.db.seed import truncate_all
from attendflow.llm.client import ChatMessage, LLMError
from tests.api_helpers import AMIT, PRIYA, RAVI, SANA_P2, SUNITA, assert_error, snapshot
from tests.conftest import make_api_settings
from tests.test_ingest import NEHA_IN

KEY = "test-key-not-real-0123456789"
INBOUND = {"E001", "E002", "E004", "E005", "E009", "E101"}
OUTBOUND = {"E003", "E006", "E007", "E008", "E010", "E102"}
OUTBOUND_NAMES = ("Ramesh", "Karan", "Dev Malhotra", "Farah", "Pooja", "Sunita")
INBOUND_NAMES = ("Amit", "Meena", "Neha", "Sana", "Arjun", "Ravi")
TODAY = "2026-04-16"


@contextlib.contextmanager
def app_client(db_engine, *, seed: bool = True, **changes):
    with Session(db_engine) as s, s.begin():
        truncate_all(s)
    settings = make_api_settings(db_engine, **changes)
    app = create_app(settings, engine=db_engine)
    with TestClient(app, raise_server_exceptions=False) as c:
        if seed:
            assert c.post("/api/seed").status_code == 200
            assert c.post("/api/detection/run").status_code == 200
        yield c


@pytest.fixture
def keyed(db_engine):
    """Seeded demo with an LLM key configured (the model itself is always scripted)."""
    with app_client(db_engine, llm_api_key=KEY) as c:
        yield c


class Script:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls: list[list[dict]] = []

    def __call__(self, settings, messages, tools, required=None, **kwargs):
        assert tools == [] and kwargs.get("json_output") is True
        self.calls.append(json.loads(json.dumps(messages)))
        if not self.replies:
            raise LLMError("no scripted reply left")
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return ChatMessage(text=reply if isinstance(reply, str) else json.dumps(reply))


def use_model(monkeypatch, *replies) -> Script:
    script = Script(*replies)
    monkeypatch.setattr(gen_module, "chat", script)
    return script


def packet_for(client, actor: dict) -> dict:
    state = client.app.state
    with Session(state.engine) as s:
        return build_packet(s, actor["X-Actor-Id"], state.clock, state.policy, state.settings)


def faithful(client, actor: dict) -> dict:
    """A grounded draft for the current facts, worded differently from the template."""
    draft = template_draft(packet_for(client, actor)).model_dump()
    draft["headline"] = "Daily view: " + draft["headline"]
    return draft


def briefing(client, actor=PRIYA) -> dict:
    r = client.get("/api/briefing", headers=actor)
    assert r.status_code == 200, r.text
    return r.json()


def refresh(client, actor=PRIYA) -> dict:
    r = client.post("/api/briefing/refresh", headers=actor)
    assert r.status_code == 200, r.text
    return r.json()


def rows(client, model=BriefingRow):
    with Session(client.app.state.engine) as s:
        return s.scalars(select(model).order_by(model.id)).all()


def briefing_audit(client) -> list[AuditLogRow]:
    return [a for a in rows(client, AuditLogRow) if a.action.startswith("briefing_")]


def all_ids(packet: dict) -> set[str]:
    text = json.dumps(packet)
    return {eid for eid in INBOUND | OUTBOUND if eid in text}


# ---------------------------------------------------------------- facts packet


@pytest.mark.parametrize("actor", [PRIYA, RAVI, SUNITA], ids=["priya", "ravi", "sunita"])
def test_the_packet_matches_the_dashboard_payroll_and_activity_numbers(demo, actor):
    packet = packet_for(demo, actor)
    board = demo.get("/api/dashboard", headers=actor).json()
    pay = demo.get("/api/payroll", headers=actor).json()
    act = demo.get(f"/api/activity/summary?date_from={TODAY}&date_to={TODAY}", headers=actor).json()
    assert packet["counts"]["active"] == board["active_total"]
    assert {k: packet["counts"][k] for k in board["by_status"]} == board["by_status"]
    assert packet["counts"]["stuck"] == board["stuck"]
    handled, metric = packet["handled_on_its_own"], board["auto_resolve"]
    assert (handled["resolved_without_human"], handled["needed_handling"]) == (
        metric["resolved_without_human"],
        metric["needed_handling"],
    )
    assert (handled["percent"], handled["undone"]) == (metric["percent"], metric["undone"])
    assert handled["today"] == act["counts"]
    blocking = sorted({c for r in pay["reasons"] if r["blocking"] for c in r["exception_ids"]})
    pb = packet["blocking_payroll"]
    assert (pb["blocking_total"], pb["status"], pb["week_start"]) == (
        len(blocking),
        pay["status"],
        pay["week_start"],
    )
    assert {c["case_id"] for c in pb["blocking_cases"]} <= set(blocking)
    assert [w["employee_id"] for w in packet["watch"]["overtime_workers"]] == [
        w["employee_id"] for w in board["overtime"]["workers"]
    ]
    assert packet["watch"]["overtime_limit_hours"] == board["overtime"]["limit_hours"]
    workload = {w["supervisor_id"]: w for w in board["workload"] if w["supervisor_id"]}
    for team in packet["teams"]:
        w = workload[team["supervisor_id"]]
        assert (team["active"], team["awaiting_worker"], team["awaiting_supervisor"]) == (
            w["active"],
            w["awaiting_worker"],
            w["awaiting_supervisor"],
        )
    if actor is PRIYA:  # the seeded demo, as documented in docs/PLANTED_CASES.md
        assert packet["counts"]["total"] == 17 and packet["counts"]["auto_resolved"] == 1
        assert [c["case_id"] for c in handled["auto_resolved_cases"]] == [SANA_P2]


def test_a_supervisor_packet_holds_only_their_own_team(demo):
    for actor, own, other, other_names, team in (
        (RAVI, INBOUND, OUTBOUND, OUTBOUND_NAMES, "Inbound"),
        (SUNITA, OUTBOUND, INBOUND, INBOUND_NAMES, "Outbound"),
    ):
        packet = packet_for(demo, actor)
        text = json.dumps(packet)
        assert (packet["scope"], packet["team"]) == ("team", team)
        assert [t["team"] for t in packet["teams"]] == [team]
        assert all_ids(packet) <= own and not all_ids(packet) & other
        assert set(packet["people"]) <= own
        for name in other_names:
            assert name not in text, name
        shown = json.dumps(briefing(demo, actor))
        assert not any(eid in shown for eid in other)
        assert not any(name in shown for name in other_names)
    everyone = packet_for(demo, PRIYA)
    assert everyone["scope"] == "all" and {t["team"] for t in everyone["teams"]} == {
        "Inbound",
        "Outbound",
    }


def test_the_packet_never_holds_typed_text_or_llm_narratives(demo):
    # A worker's free-text reply exists in the database ...
    from tests.api_helpers import AMIT_P1, post, store_test_investigation

    store_test_investigation(demo, AMIT_P1)
    assert post(demo, AMIT_P1, "ask-worker", {}, RAVI).status_code == 200
    typed = "PRIVATE-NOTE left at the gate around 7:30ish"
    reply = post(demo, AMIT_P1, "worker-reply", {"confirmed": False, "text": typed}, AMIT)
    assert reply.status_code == 200
    for actor in (PRIYA, RAVI):
        text = json.dumps(packet_for(demo, actor))
        assert "PRIVATE-NOTE" not in text and "Hi Amit" not in text
        assert '"what_happened"' not in text and '"message"' not in text


# ---------------------------------------------------------------- permissions


def test_workers_get_403_and_unknown_actors_are_refused(demo):
    for path, method in (("/api/briefing", "get"), ("/api/briefing/refresh", "post")):
        r = getattr(demo, method)(path, headers=AMIT)
        assert r.status_code == 403
        assert_error(r, 403, "supervisor_only")
        assert_error(
            getattr(demo, method)(path, headers={"X-Actor-Id": "E999"}), 403, "unknown_actor"
        )
    assert rows(demo) == [] and briefing_audit(demo) == []


# ---------------------------------------------------------------- reading never calls the LLM


def test_reading_calls_no_llm_and_writes_nothing(keyed, monkeypatch):
    script = use_model(monkeypatch)
    before, audit = snapshot(keyed), len(rows(keyed, AuditLogRow))
    for actor in (PRIYA, RAVI, SUNITA):
        body = briefing(keyed, actor)
        assert (body["source"], body["reason"], body["stale"], body["stored"]) == (
            "template",
            "not_generated",
            True,
            False,
        )
        assert body["label"] == "Template (no briefing generated yet)"
        assert [s["key"] for s in body["sections"]] == [
            "needs_decision",
            "handled_on_its_own",
            "blocking_payroll",
            "watch",
        ]
    assert script.calls == []
    assert snapshot(keyed) == before and len(rows(keyed, AuditLogRow)) == audit
    assert rows(keyed) == []


def test_without_a_key_refresh_stores_the_template_and_says_why(demo):
    before = snapshot(demo)
    body = refresh(demo, RAVI)
    assert (body["source"], body["reason"], body["label"]) == (
        "template",
        "llm_unavailable",
        "Template (LLM unavailable)",
    )
    assert body["llm_calls"] == 0 and body["refresh"]["llm_configured"] is False
    audit = briefing_audit(demo)
    assert [(a.action, a.actor, a.actor_id) for a in audit] == [
        ("briefing_refresh_requested", "supervisor", "E101"),
        ("briefing_fallback", "system", None),
    ]
    assert audit[1].after["reason"] == "llm_unavailable"
    assert snapshot(demo) == before
    again = briefing(demo, RAVI)
    assert (again["stored"], again["stale"], again["briefing_id"]) == (
        True,
        False,
        body["briefing_id"],
    )


# ---------------------------------------------------------------- refresh with the LLM


def test_refresh_stores_an_llm_briefing_and_audits_it(keyed, monkeypatch):
    script = use_model(monkeypatch, faithful(keyed, PRIYA))
    before = snapshot(keyed)
    body = refresh(keyed, PRIYA)
    assert (body["source"], body["reason"], body["llm_calls"]) == ("llm", "validated", 1)
    assert body["label"] == "Written by the LLM from verified facts"
    assert body["headline"].startswith("Daily view: ")
    assert body["failed_checks"] == []
    assert len(script.calls) == 1
    sent = json.dumps(script.calls[0])
    for marker in ("$ref", "$defs", "date-time"):
        assert marker not in sent
    audit = briefing_audit(keyed)
    assert [(a.action, a.actor) for a in audit] == [
        ("briefing_refresh_requested", "admin"),
        ("briefing_generated", "agent"),
    ]
    assert audit[1].after["llm_calls"] == 1 and audit[1].after["scope"] == "all"
    [row] = rows(keyed)
    assert (row.trigger, row.requested_by, row.model) == ("refresh", "E201", "openai/gpt-oss-120b")
    assert snapshot(keyed) == before  # the briefing never changes any data


def test_a_draft_that_fails_twice_falls_back_and_records_only_codes(keyed, monkeypatch):
    bad = faithful(keyed, RAVI)
    bad["bullets"][0]["text"] = "P9-E006-2026-04-15 for Karan Mehta waits; 99 more are late."
    script = use_model(monkeypatch, bad, bad)
    body = refresh(keyed, RAVI)
    assert (body["source"], body["reason"], body["llm_calls"]) == (
        "template",
        "validation_failed",
        2,
    )
    assert body["label"] == "Template (the LLM draft failed the checks)"
    assert {"case_id_not_in_facts", "name_outside_scope", "ungrounded_number"} <= set(
        body["failed_checks"]
    )
    assert "Karan" not in json.dumps(body) and "E006" not in json.dumps(body)
    correction = script.calls[1][-1]["content"]
    assert "the number 99" in correction and "Karan" not in correction
    [_, fallback] = briefing_audit(keyed)
    assert (fallback.action, fallback.actor, fallback.after["reason"]) == (
        "briefing_fallback",
        "system",
        "validation_failed",
    )


def test_a_correction_that_passes_is_used(keyed, monkeypatch):
    bad = faithful(keyed, PRIYA)
    bad["headline"] = "The team will finish 3 fixes tomorrow."
    use_model(monkeypatch, bad, faithful(keyed, PRIYA))
    body = refresh(keyed, PRIYA)
    assert (body["source"], body["reason"], body["llm_calls"]) == (
        "llm",
        "validated_after_retry",
        2,
    )
    assert "future_claim" in body["failed_checks"]


@pytest.mark.parametrize(
    ("error", "reason"),
    [(LLMError("chat request failed (HTTP 500)"), "llm_error"), (TimeoutError(), "llm_error")],
)
def test_model_failure_uses_the_template_without_a_retry(keyed, monkeypatch, error, reason):
    script = use_model(monkeypatch, error, faithful(keyed, PRIYA))
    body = refresh(keyed, PRIYA)
    assert (body["source"], body["reason"], body["llm_calls"]) == ("template", reason, 1)
    assert len(script.calls) == 1


# ---------------------------------------------------------------- caching and limits


def test_same_facts_need_no_call_and_changed_facts_make_it_stale(keyed, monkeypatch):
    script = use_model(monkeypatch, faithful(keyed, PRIYA))
    first = refresh(keyed, PRIYA)
    for _ in range(3):
        cached = briefing(keyed, PRIYA)
        assert (cached["stale"], cached["source"], cached["briefing_id"]) == (
            False,
            "llm",
            first["briefing_id"],
        )
    assert len(script.calls) == 1
    # The facts change: Priya undoes Sana's auto-resolve.
    r = keyed.post(
        f"/api/exceptions/{SANA_P2}/undo", json={"reason": "Two taps were real."}, headers=PRIYA
    )
    assert r.status_code == 200, r.text
    stale = briefing(keyed, PRIYA)
    assert (stale["stale"], stale["source"], stale["reason"]) == (True, "template", "facts_changed")
    assert stale["label"] == "Template (facts changed since the last briefing)"
    assert len(script.calls) == 1  # reading still calls nothing
    script.replies.append(faithful(keyed, PRIYA))
    fresh = refresh(keyed, PRIYA)
    assert (fresh["source"], fresh["stale"]) == ("llm", False) and len(script.calls) == 2
    # Refresh asked again with unchanged facts: a person asked, so one call.
    script.replies.append(faithful(keyed, PRIYA))
    refresh(keyed, PRIYA)
    assert len(script.calls) == 3


def test_refresh_is_rate_limited_and_capped(db_engine, monkeypatch):
    with app_client(db_engine, llm_api_key=KEY, briefing_min_interval_seconds=300) as c:
        use_model(monkeypatch, faithful(c, PRIYA))
        refresh(c, PRIYA)
        err = assert_error(c.post("/api/briefing/refresh", headers=PRIYA), 429, "briefing_too_soon")
        assert 0 < err["details"]["retry_after_seconds"] <= 301
        assert briefing(c, PRIYA)["refresh"]["reason"] == "too_soon"
        refresh(c, RAVI)  # another scope has its own interval (the scripted model is empty:
        # the call fails and the template is stored)
    with app_client(db_engine, llm_api_key=KEY, briefing_max_llm_calls_per_day=1) as c:
        bad = faithful(c, PRIYA)
        bad["headline"] = "42 cases."
        script = use_model(monkeypatch, bad, faithful(c, PRIYA))
        body = refresh(c, PRIYA)
        assert (body["reason"], body["llm_calls"]) == ("validation_failed", 1)  # no retry left
        assert len(script.calls) == 1
        assert_error(c.post("/api/briefing/refresh", headers=PRIYA), 429, "briefing_daily_cap")
        assert briefing(c, PRIYA)["refresh"]["calls_left_today"] == 0
        assert len(script.calls) == 1


# ---------------------------------------------------------------- the scheduled briefing


def test_scheduled_briefing_once_per_workflow_day_after_new_activity(db_engine, monkeypatch):
    with app_client(db_engine, seed=False, demo_mode=True, briefing_scheduled=True) as c:
        assert c.post("/api/seed").status_code == 200
        assert c.post("/api/admin/demo/reset", headers=PRIYA).status_code == 200
        before = snapshot(c)

        def cycle() -> dict:
            r = c.post("/api/admin/scheduler/run-now", headers=PRIYA)
            assert r.status_code == 200, r.text
            assert r.json()["errors"] == []
            return r.json()["briefing"]

        # Right after a reset nothing new happened: the seeded backlog is no surprise.
        assert cycle() == {
            "status": "skipped",
            "reason": "no_new_activity",
            "briefing_id": None,
            "llm_calls": 0,
        }
        r = c.post("/api/admin/demo/punch", json=NEHA_IN, headers=PRIYA)
        assert r.status_code == 201, r.text
        made = cycle()
        assert (made["status"], made["reason"], made["llm_calls"]) == (
            "fallback",
            "llm_unavailable",
            0,
        )
        assert cycle()["reason"] == "already_today"
        assert c.post("/api/admin/demo/clock", json={"hours": 24}, headers=PRIYA).status_code == 200
        assert cycle()["status"] == "fallback"  # a new workflow day
        assert cycle()["reason"] == "already_today"
        scheduled = [r for r in rows(c) if r.trigger == "scheduler"]
        assert [r.scope for r in scheduled] == ["all", "all"]
        audit = briefing_audit(c)
        assert [(a.action, a.actor) for a in audit] == [("briefing_fallback", "system")] * 2
        assert all(a.after["trigger"] == "scheduler" for a in audit)
        punches = [p for p in snapshot(c)["timecards"] if p not in before["timecards"]]
        assert len(punches) == 1  # only the simulated punch; the briefing wrote nothing


def test_scheduled_briefing_skips_unchanged_facts_and_uses_the_model(keyed, monkeypatch):
    from dataclasses import replace

    state = keyed.app.state
    on = replace(state.settings, briefing_scheduled=True)
    with Session(state.engine) as s:
        watermark = max(a.id for a in s.scalars(select(AuditLogRow)))
    use_model(monkeypatch, faithful(keyed, PRIYA))
    refresh(keyed, PRIYA)  # a person's briefing for exactly these facts
    run = briefing_service.scheduled(
        state.session_factory, on, state.clock, state.policy, watermark=watermark - 1
    )
    assert run == {"status": "skipped", "reason": "facts_unchanged"}
    state.clock.set_offset(timedelta(days=1))  # a new workflow date changes the facts
    script = use_model(monkeypatch, faithful(keyed, PRIYA))
    run = briefing_service.scheduled(
        state.session_factory, on, state.clock, state.policy, watermark=watermark - 1
    )
    assert (run["status"], run["reason"], run["llm_calls"]) == ("generated", "validated", 1)
    assert len(script.calls) == 1
    assert briefing_audit(keyed)[-1].action == "briefing_generated"


# ---------------------------------------------------------------- leaks and the feed


LEAK = "LEAKCHECK-briefing-marker"


def test_no_diagnostics_prompts_or_keys_leak_with_diagnostics_on(db_engine, monkeypatch):
    with app_client(db_engine, llm_api_key=KEY, llm_diagnostics=True) as c:
        use_model(monkeypatch, LLMError(f"{LEAK}-provider: upstream said no ({KEY})"))
        shown = [refresh(c, PRIYA)]
        bad = {"headline": LEAK, "bullets": [], LEAK: 1}
        use_model(monkeypatch, bad, f"{LEAK} not json")
        shown.append(refresh(c, RAVI))
        shown += [briefing(c, PRIYA), briefing(c, RAVI)]
        for actor in (PRIYA, RAVI):
            shown.append(c.get("/api/activity?limit=200", headers=actor).json())
            shown.append(c.get("/api/activity/summary", headers=actor).json())
        stored = [
            {"attempts": r.attempts, "content": r.content, "facts": r.facts} for r in rows(c)
        ] + [{"after": a.after, "reason": a.reason} for a in briefing_audit(c)]
        text = json.dumps(shown, default=str) + json.dumps(stored, default=str)
        assert LEAK not in text
        assert KEY not in text
        assert SYSTEM_PROMPT[:60] not in text
        reasons = [r.reason for r in rows(c)]
        assert reasons == ["llm_error", "validation_failed"]


def test_priya_sees_briefing_rows_in_the_feed_and_supervisors_do_not(demo):
    refresh(demo, RAVI)
    refresh(demo, PRIYA)
    items = demo.get("/api/activity", headers=PRIYA).json()["items"]
    sentences = [i["sentence"] for i in items if i["action"].startswith("briefing_")]
    assert sentences == [
        "Showed the template briefing (all teams): no LLM is configured.",
        "Asked for a fresh daily briefing (all teams).",
        "Showed the template briefing (Inbound team): no LLM is configured.",
        "Asked for a fresh daily briefing (Inbound team).",
    ]
    ravi = demo.get("/api/activity", headers=RAVI).json()["items"]
    assert not [i for i in ravi if i["action"].startswith("briefing_")]
