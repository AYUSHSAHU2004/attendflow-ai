"""Phase 18: runtime settings (payroll admin only, whitelisted, audited, never retroactive).

No real LLM: the app runs without a key, and scheduler tests use a down model.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from attendflow import runtime_settings
from attendflow.api.app import create_app
from attendflow.config import REPO_ROOT, Settings
from attendflow.db.models import AuditLogRow, ExceptionRow, SettingRow
from attendflow.llm.client import LLMError
from attendflow.scheduler import cycle
from tests.api_helpers import (
    AMIT,
    AMIT_P1,
    PRIYA,
    RAVI,
    SANA_P2,
    SUNITA,
    assert_error,
    get,
    post,
    session_for,
    snapshot,
    store_test_investigation,
)
from tests.test_e2e_prototype import (
    scripted_investigation,
    scripted_message,
    write_log,  # noqa: F401 - a fixture
)
from tests.test_scheduler import DownModel

REASON = "Night shift workers need more time to answer"
PASSWORD = "F15c2aa44a925eb5297280555b5c3e1bbe498b6a"
EDITABLE = [
    "auto_resolve_enabled",
    "no_reply_reminder_hours",
    "no_reply_supervisor_hours",
    "no_reply_admin_hours",
    "scheduler_investigations_per_cycle",
    "scheduler_messages_per_cycle",
    "briefing_min_interval_seconds",
    "briefing_max_llm_calls_per_day",
    "briefing_scheduled",
    "qa_questions_per_hour",  # Phase 20
    "qa_max_llm_calls_per_day",  # Phase 20
    "overtime_warning_margin_hours",
]


# ---------------------------------------------------------------- helpers


def put(client, key: str, value, headers=PRIYA, reason: str | None = REASON, **extra):
    body = {"value": value, **extra}
    if reason is not None:
        body["reason"] = reason
    return client.put(f"/api/settings/{key}", json=body, headers=headers)


def reset(client, key: str, headers=PRIYA, reason: str | None = REASON):
    body = {} if reason is None else {"reason": reason}
    return client.post(f"/api/settings/{key}/reset", json=body, headers=headers)


def settings_view(client, headers=PRIYA) -> dict:
    r = client.get("/api/settings", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def item(client, key: str) -> dict:
    return next(i for i in settings_view(client)["items"] if i["key"] == key)


def settings_audit(client) -> list[AuditLogRow]:
    with session_for(client) as s:
        return s.scalars(
            select(AuditLogRow)
            .where(AuditLogRow.action.in_(runtime_settings.HISTORY_ACTIONS))
            .order_by(AuditLogRow.id)
        ).all()


def stored_overrides(client) -> dict | None:
    with session_for(client) as s:
        row = s.get(SettingRow, runtime_settings.OVERRIDES_KEY)
        return None if row is None else dict(row.value)


def assert_nothing_written(client) -> None:
    assert not stored_overrides(client)
    assert settings_audit(client) == []


def effective(client) -> Settings:
    state = client.app.state
    return state.settings_reader.apply(state.settings)


# ---------------------------------------------------------------- reading


def test_get_lists_every_setting_with_value_source_and_range(demo):
    view = settings_view(demo)
    assert (view["profile"], view["changes_allowed"], view["min_reason_length"]) == (
        "local",
        True,
        10,
    )
    editable = [i for i in view["items"] if i["editable"]]
    assert [i["key"] for i in editable] == EDITABLE
    ranges = {i["key"]: (i["minimum"], i["maximum"]) for i in editable}
    assert ranges["scheduler_investigations_per_cycle"] == (0, 5)
    assert ranges["scheduler_messages_per_cycle"] == (0, 10)
    assert ranges["briefing_max_llm_calls_per_day"] == (0, 100)
    assert ranges["no_reply_reminder_hours"] == (1, 72)
    assert ranges["no_reply_supervisor_hours"] == (2, 168)
    assert ranges["overtime_warning_margin_hours"] == (0.5, 20)
    assert ranges["qa_questions_per_hour"] == (1, 30)
    assert ranges["qa_max_llm_calls_per_day"] == (0, 100)
    reminder = next(i for i in editable if i["key"] == "no_reply_reminder_hours")
    assert (reminder["value"], reminder["source"], reminder["value_text"]) == (8, "default", "8 h")
    assert reminder["range_text"] == "a whole number from 1 to 72 h"
    assert reminder["last_change"] is None and reminder["within_range"] is True
    read_only = [i for i in view["items"] if not i["editable"]]
    assert {i["key"] for i in read_only} == runtime_settings.READ_ONLY_KEYS
    assert all(i["minimum"] is None and i["locked_note"] for i in read_only)


def test_get_never_shows_secrets_or_locked_configuration(demo, monkeypatch):
    state = demo.app.state
    monkeypatch.setattr(
        state, "settings", replace(state.settings, llm_api_key="sk-private-test-key-value")
    )
    text = demo.get("/api/settings", headers=PRIYA).text
    for secret in ("sk-private-test-key-value", "test-device-key", "postgresql", "llm_model"):
        assert secret not in text


def test_source_is_env_when_the_server_value_differs_from_the_default(demo, monkeypatch):
    state = demo.app.state
    monkeypatch.setattr(
        state, "settings", replace(state.settings, scheduler_investigations_per_cycle=8)
    )
    investigations = item(demo, "scheduler_investigations_per_cycle")
    # An env value outside the runtime range is shown as it is, and flagged.
    assert (investigations["value"], investigations["source"]) == (8, "env")
    assert investigations["within_range"] is False


# ---------------------------------------------------------------- permissions


@pytest.mark.parametrize("headers", [RAVI, SUNITA, AMIT])
def test_supervisors_and_workers_cannot_change_settings(demo, headers):
    for response in (
        demo.get("/api/settings", headers=headers),
        demo.get("/api/settings/history", headers=headers),
        put(demo, "no_reply_reminder_hours", 12, headers=headers),
        reset(demo, "no_reply_reminder_hours", headers=headers),
    ):
        assert_error(response, 403, "admin_only")
    assert_error(
        put(demo, "no_reply_reminder_hours", 12, {"X-Actor-Id": "E999"}), 403, "unknown_actor"
    )
    assert_nothing_written(demo)
    assert effective(demo).no_reply_reminder_hours == 8


@pytest.mark.parametrize(
    "key",
    [
        "llm_api_key",
        "llm_base_url",
        "llm_model",
        "database_url",
        "demo_mode",
        "demo_password",
        "as_of",
        "llm_diagnostics",
        "device_api_key",
        "scheduler_enabled",
        "no_reply_escalation_enabled",
        "P5",
        "p5.weekly_overtime_after_hours",
        "policy",
    ],
)
def test_locked_keys_and_policy_rules_are_refused(demo, key):
    error = assert_error(put(demo, key, True), 403, "setting_locked")
    assert "cannot be changed" in error["message"]
    assert_error(reset(demo, key), 403, "setting_locked")
    assert_error(put(demo, "no_such_setting", 1), 404, "unknown_setting")
    assert_nothing_written(demo)


# ---------------------------------------------------------------- changing


def test_a_change_takes_effect_without_a_restart_and_is_audited(demo):
    r = put(demo, "no_reply_reminder_hours", 12)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["before"] == {"key": "no_reply_reminder_hours", "value": 8, "source": "default"}
    assert body["after"] == {"key": "no_reply_reminder_hours", "value": 12, "source": "override"}
    assert (body["setting"]["value"], body["setting"]["source"]) == (12, "override")
    assert body["setting"]["last_change"]["reason"] == REASON
    assert effective(demo).no_reply_reminder_hours == 12
    status = demo.get("/api/admin/scheduler", headers=PRIYA).json()
    assert status["no_reply"]["reminder_hours"] == 12  # read live, no restart
    [row] = settings_audit(demo)
    assert (row.action, row.actor, row.actor_id, row.exception_id) == (
        "settings_changed",
        "admin",
        "E201",
        None,
    )
    assert row.before == {"key": "no_reply_reminder_hours", "value": 8, "source": "default"}
    assert row.after == {"key": "no_reply_reminder_hours", "value": 12, "source": "override"}
    assert row.reason == REASON
    assert stored_overrides(demo) == {"no_reply_reminder_hours": 12}


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("no_reply_reminder_hours", 0),
        ("no_reply_reminder_hours", 73),
        ("no_reply_reminder_hours", 8.5),
        ("no_reply_reminder_hours", "8"),
        ("no_reply_reminder_hours", True),
        ("no_reply_reminder_hours", None),
        ("no_reply_supervisor_hours", 169),
        ("no_reply_admin_hours", 0),
        ("scheduler_investigations_per_cycle", 6),
        ("scheduler_investigations_per_cycle", -1),
        ("scheduler_messages_per_cycle", 11),
        ("briefing_max_llm_calls_per_day", 101),
        ("briefing_min_interval_seconds", 59),
        ("briefing_min_interval_seconds", 3601),
        ("overtime_warning_margin_hours", 0.25),
        ("overtime_warning_margin_hours", 0.75),
        ("overtime_warning_margin_hours", 20.5),
        ("auto_resolve_enabled", "false"),
        ("auto_resolve_enabled", 0),
        ("briefing_scheduled", None),
    ],
)
def test_wrong_types_and_out_of_range_values_are_refused_in_plain_words(demo, key, value):
    error = assert_error(put(demo, key, value), 422, "invalid_setting_value")
    label = runtime_settings.SPECS[key].label
    assert error["message"].startswith(label + " must be")
    assert_nothing_written(demo)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("scheduler_investigations_per_cycle", 5),
        ("scheduler_investigations_per_cycle", 0),
        ("scheduler_messages_per_cycle", 10),
        ("briefing_max_llm_calls_per_day", 100),
        ("briefing_max_llm_calls_per_day", 0),
        ("briefing_min_interval_seconds", 3600),
        ("no_reply_admin_hours", 168),
        ("overtime_warning_margin_hours", 19.5),
        ("overtime_warning_margin_hours", 0.5),
        ("briefing_scheduled", True),  # the test settings start with it off
    ],
)
def test_values_at_the_bounds_are_accepted(demo, key, value):
    r = put(demo, key, value)
    assert r.status_code == 200, r.text
    assert getattr(effective(demo), key) == value


def test_rules_across_settings_are_checked_in_plain_words(demo):
    error = assert_error(
        put(demo, "no_reply_reminder_hours", 24), 422, "invalid_setting_combination"
    )
    assert "must come before the supervisor" in error["message"]
    assert "NO_REPLY" not in error["message"]  # plain words, not env variable names
    assert_error(put(demo, "no_reply_supervisor_hours", 8), 422, "invalid_setting_combination")
    assert put(demo, "no_reply_supervisor_hours", 30).status_code == 200
    assert put(demo, "no_reply_reminder_hours", 28).status_code == 200
    # Resetting the supervisor hours would put them (24) before the reminder (28).
    error = assert_error(
        reset(demo, "no_reply_supervisor_hours"), 422, "invalid_setting_combination"
    )
    assert "Change the reminder first" in error["message"]
    assert effective(demo).no_reply_supervisor_hours == 30


def test_every_change_needs_a_reason(demo):
    for reason in (None, "", "  too short  "):
        assert_error(put(demo, "no_reply_admin_hours", 30, reason=reason), 422, "reason_required")
    assert_nothing_written(demo)
    assert put(demo, "no_reply_admin_hours", 30).status_code == 200
    assert_error(reset(demo, "no_reply_admin_hours", reason="short"), 422, "reason_required")
    assert effective(demo).no_reply_admin_hours == 30


def test_turning_auto_resolve_on_needs_confirm(demo):
    off = put(demo, "auto_resolve_enabled", False)  # turning it off needs no confirm
    assert off.status_code == 200, off.text
    error = assert_error(put(demo, "auto_resolve_enabled", True), 422, "confirmation_required")
    assert "confirm" in error["message"]
    assert_error(
        put(demo, "auto_resolve_enabled", True, confirm=False), 422, "confirmation_required"
    )
    assert effective(demo).auto_resolve_enabled is False
    on = put(demo, "auto_resolve_enabled", True, confirm=True)
    assert on.status_code == 200, on.text
    assert effective(demo).auto_resolve_enabled is True
    assert settings_audit(demo)[-1].after == {
        "key": "auto_resolve_enabled",
        "value": True,
        "source": "override",
        "confirmed": True,
    }


def test_no_change_and_nothing_to_reset_are_refused(demo):
    assert_error(put(demo, "no_reply_reminder_hours", 8), 409, "no_change")
    assert_error(put(demo, "no_reply_reminder_hours", 8.0), 409, "no_change")
    assert_error(reset(demo, "no_reply_reminder_hours"), 409, "no_override")
    assert_nothing_written(demo)


def test_reset_goes_back_to_the_server_value(demo):
    assert put(demo, "scheduler_messages_per_cycle", 7).status_code == 200
    r = reset(demo, "scheduler_messages_per_cycle", reason="Back to the server value")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["before"] == {
        "key": "scheduler_messages_per_cycle",
        "value": 7,
        "source": "override",
    }
    assert body["after"] == {"key": "scheduler_messages_per_cycle", "value": 3, "source": "default"}
    assert (body["setting"]["value"], body["setting"]["source"]) == (3, "default")
    assert body["setting"]["last_change"]["action"] == "settings_reset"
    assert stored_overrides(demo) == {}
    assert effective(demo).scheduler_messages_per_cycle == 3
    assert [r.action for r in settings_audit(demo)] == ["settings_changed", "settings_reset"]


def test_history_is_newest_first_paged_and_filterable(demo):
    for value in (10, 11, 12):
        assert put(demo, "no_reply_reminder_hours", value).status_code == 200
    assert put(demo, "briefing_scheduled", True).status_code == 200
    first = demo.get("/api/settings/history?limit=2", headers=PRIYA).json()
    assert [i["new_value"] for i in first["items"]] == [True, 12]
    assert first["items"][1]["old_text"] == "11 h" and first["items"][1]["new_text"] == "12 h"
    assert first["items"][0]["actor_name"] == "Priya Sharma"
    rest = demo.get(
        f"/api/settings/history?before_id={first['next_before_id']}", headers=PRIYA
    ).json()
    assert [i["new_value"] for i in rest["items"]] == [11, 10]
    assert rest["next_before_id"] is None
    only = demo.get("/api/settings/history?key=briefing_scheduled", headers=PRIYA).json()
    assert [i["key"] for i in only["items"]] == ["briefing_scheduled"]


def test_the_feed_shows_changes_to_priya_only(demo):
    assert put(demo, "no_reply_reminder_hours", 12).status_code == 200
    priya = demo.get("/api/activity", headers=PRIYA).json()["items"]
    [row] = [i for i in priya if i["action"] == "settings_changed"]
    assert row["sentence"] == "Changed No-reply reminder after from 8 h to 12 h."
    assert (row["reason"], row["actor_name"], row["capability"]) == (
        REASON,
        "Priya Sharma",
        "runtime_settings",
    )
    ravi = demo.get("/api/activity", headers=RAVI).json()["items"]
    assert not [i for i in ravi if i["action"].startswith("settings_")]


def test_audit_rows_hold_only_the_key_values_and_reason(demo, monkeypatch):
    state = demo.app.state
    monkeypatch.setattr(
        state, "settings", replace(state.settings, llm_api_key="sk-private-test-key-value")
    )
    assert put(demo, "briefing_max_llm_calls_per_day", 20).status_code == 200
    assert reset(demo, "briefing_max_llm_calls_per_day").status_code == 200
    for row in settings_audit(demo):
        assert set(row.before) == {"key", "value", "source"}
        assert set(row.after) == {"key", "value", "source"}
        assert row.after["key"] in runtime_settings.SPECS
        dumped = json.dumps([row.before, row.after, row.reason])
        assert "sk-private" not in dumped and "postgresql" not in dumped


# ---------------------------------------------------------------- profiles


def deployed_settings(base: Settings, *, guided: bool) -> Settings:
    return replace(
        base,
        deployed=True,
        session_secret="profile-fixture-" + "x" * 32,
        demo_mode=guided,
        demo_reset_enabled=False,
        enable_seed=False,
        demo_password=PASSWORD,
        database_url="postgres://demo:private-db-value@db.example/demo",  # the engine is given
        llm_diagnostics=False,
        device_api_key=None,
        cors_origins=("https://demo.example",),
    )


@pytest.fixture
def frontend(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    return tmp_path


def deployed_client(settings: Settings, db_engine, frontend) -> TestClient:
    app = create_app(settings, engine=db_engine, frontend_dir=frontend)
    return TestClient(app, raise_server_exceptions=False)


def test_locked_profile_refuses_changes_but_still_reads(demo, db_engine, frontend):
    locked = deployed_settings(demo.app.state.settings, guided=False)
    with deployed_client(locked, db_engine, frontend) as c:
        c.auth = ("demo", PASSWORD)
        view = settings_view(c)
        assert (view["profile"], view["changes_allowed"]) == ("locked", False)
        assert "Locked" in view["locked_reason"]
        assert c.get("/api/settings/history", headers=PRIYA).status_code == 200
        for response in (
            put(c, "no_reply_reminder_hours", 12),
            put(c, "auto_resolve_enabled", False),
            reset(c, "no_reply_reminder_hours"),
            put(c, "no_reply_reminder_hours", 12, headers=RAVI),
        ):
            assert_error(response, 403, "settings_locked_in_profile")
    assert_nothing_written(demo)


def test_guided_profile_allows_changes_within_the_bounds(demo, db_engine, frontend):
    guided = deployed_settings(demo.app.state.settings, guided=True)
    with deployed_client(guided, db_engine, frontend) as c:
        c.auth = ("demo", PASSWORD)
        assert settings_view(c)["profile"] == "guided"
        assert put(c, "scheduler_investigations_per_cycle", 1).status_code == 200
        assert_error(put(c, "scheduler_investigations_per_cycle", 6), 422, "invalid_setting_value")
        assert_error(put(c, "llm_model", "x"), 403, "setting_locked")
        assert_error(put(c, "no_reply_reminder_hours", 12, headers=RAVI), 403, "admin_only")


def test_a_stored_value_that_no_longer_fits_is_skipped_not_fatal():
    base = Settings(
        data_dir=REPO_ROOT,
        as_of=datetime(2026, 4, 16, 8, 0),
        llm_base_url="",
        llm_model="",
        llm_api_key=None,
        llm_timeout_seconds=1,
    )
    out = runtime_settings.apply_overrides(
        base, {"no_reply_reminder_hours": 30, "scheduler_messages_per_cycle": 2}
    )
    assert out.no_reply_reminder_hours == 8  # 30 is not before the supervisor (24): skipped
    assert out.scheduler_messages_per_cycle == 2  # the other override still applies


# ---------------------------------------------------------------- taking effect


def test_the_scheduler_picks_up_a_changed_cap_on_the_next_cycle(demo, monkeypatch):
    sched = demo.app.state.scheduler
    sched.deps.settings = replace(sched.deps.settings, scheduler_backlog=True)
    scripted_investigation(monkeypatch, DownModel(LLMError("provider down")))
    scripted_message(monkeypatch, LLMError("provider down"))
    assert put(demo, "scheduler_investigations_per_cycle", 1).status_code == 200
    assert put(demo, "scheduler_messages_per_cycle", 0).status_code == 200
    assert sched.status()["investigations_per_cycle"] == 1

    summary = sched.run_once("run_now")
    assert len(summary["investigated"]) == 1
    assert len(summary["skipped_budget"]) >= 2
    assert summary["messages_sent"] == []
    assert summary["skipped_message_budget"]  # a worker-routed case waits for the next cycle


def test_a_change_during_a_cycle_applies_from_the_next_cycle(demo, monkeypatch):
    sched = demo.app.state.scheduler
    sched.deps.settings = replace(
        sched.deps.settings, scheduler_backlog=True, scheduler_investigations_per_cycle=2
    )
    scripted_investigation(monkeypatch, DownModel(LLMError("provider down")))
    scripted_message(monkeypatch, LLMError("provider down"))
    real = cycle.service.run_detection
    changed = []

    def detection_then_change(*args, **kwargs):
        if not changed:  # Priya pauses investigations while the cycle is running
            changed.append(put(demo, "scheduler_investigations_per_cycle", 0).status_code)
        return real(*args, **kwargs)

    monkeypatch.setattr(cycle.service, "run_detection", detection_then_change)
    first = sched.run_once("run_now")
    assert changed == [200]
    assert len(first["investigated"]) == 2  # this cycle keeps the value it started with
    second = sched.run_once("run_now")
    assert second["investigated"] == [] and second["skipped_budget"]


def test_auto_resolve_off_really_stops_auto_resolution(demo_client):
    c = demo_client
    assert c.post("/api/seed").status_code == 200
    assert put(c, "auto_resolve_enabled", False).status_code == 200
    run = c.post("/api/detection/run").json()
    assert (run["auto_resolved"], run["auto_resolve_held"]) == (0, 1)
    assert get(c, SANA_P2)["status"] == "open"
    punch = {"employee_id": "E004", "timestamp": "2026-04-15T09:02", "type": "in"}
    assert c.post("/api/admin/demo/punch", json=punch, headers=PRIYA).status_code == 201
    assert get(c, "P7-E004-2026-04-15-late")["status"] == "open"
    with session_for(c) as s:
        assert not s.scalars(select(ExceptionRow).where(ExceptionRow.auto_resolved)).all()

    # Turning it back on is never retroactive: the held cases stay with a person.
    assert put(c, "auto_resolve_enabled", True, confirm=True).status_code == 200
    assert c.post("/api/detection/run").json()["auto_resolved"] == 0
    assert get(c, SANA_P2)["status"] == "open"
    assert get(c, "P7-E004-2026-04-15-late")["status"] == "open"


def test_ladder_changes_never_retime_a_running_wait(demo_client):
    c = demo_client
    assert c.post("/api/seed").status_code == 200
    assert c.post("/api/detection/run").status_code == 200
    store_test_investigation(c, AMIT_P1)
    assert post(c, AMIT_P1, "ask-worker", {}, RAVI).status_code == 200
    with session_for(c) as s:
        assert s.get(ExceptionRow, AMIT_P1).no_reply_limits == {
            "reminder_hours": 8,
            "supervisor_hours": 24,
            "admin_hours": 24,
        }
    assert put(c, "no_reply_reminder_hours", 2).status_code == 200
    assert put(c, "no_reply_supervisor_hours", 4).status_code == 200

    c.app.state.clock.set_offset(timedelta(hours=5))
    ran = c.post("/api/admin/scheduler/run-now", headers=PRIYA).json()["no_reply"]
    assert ran["reminded"] == [] and ran["to_supervisor"] == []  # still the 8 h it started with
    c.app.state.clock.set_offset(timedelta(hours=8))
    ran = c.post("/api/admin/scheduler/run-now", headers=PRIYA).json()["no_reply"]
    assert ran["reminded"] == [AMIT_P1]
    reminder = c.get("/api/worker/messages", headers=AMIT).json()["items"][0]["reminder"]
    assert "Fri 17 Apr 08:00" in reminder["text"]  # the 24 h deadline it was promised

    # A new wait (a No that still needs the time) takes the limits in force now.
    reply = post(c, AMIT_P1, "worker-reply", {"confirmed": False, "text": "I left late."}, AMIT)
    assert reply.status_code == 200, reply.text
    with session_for(c) as s:
        assert s.get(ExceptionRow, AMIT_P1).no_reply_limits == {
            "reminder_hours": 2,
            "supervisor_hours": 4,
            "admin_hours": 24,
        }


def test_a_demo_reset_clears_every_override(demo_client):
    c = demo_client
    assert c.post("/api/seed").status_code == 200
    assert put(c, "scheduler_messages_per_cycle", 1).status_code == 200
    assert c.post("/api/admin/demo/reset", headers=PRIYA).status_code == 200
    assert item(c, "scheduler_messages_per_cycle")["source"] == "default"
    assert effective(c).scheduler_messages_per_cycle == 3


# ---------------------------------------------------------------- data safety


def test_settings_changes_write_no_source_data(
    demo,
    write_log,  # noqa: F811 - the imported fixture
):
    before = snapshot(demo)
    assert put(demo, "no_reply_reminder_hours", 12).status_code == 200
    assert put(demo, "auto_resolve_enabled", False).status_code == 200
    assert reset(demo, "no_reply_reminder_hours").status_code == 200
    assert_error(put(demo, "scheduler_messages_per_cycle", 99), 422, "invalid_setting_value")
    assert write_log == []  # no INSERT, UPDATE or DELETE on timecards, schedule or leave
    assert snapshot(demo) == before


def test_the_settings_module_writes_only_settings_and_audit_rows():
    path = REPO_ROOT / "backend" / "attendflow" / "runtime_settings.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    models = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "attendflow.db.models"
        for alias in node.names
    }
    assert models == {"AuditLogRow", "EmployeeRow", "SettingRow"}
    imported = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not {m for m in imported if m.startswith(("attendflow.fixes", "attendflow.ingest"))}
    src = path.read_text(encoding="utf-8")
    assert src.count("session.add(") == 1  # the audit row; the settings row is an upsert
    for call in (".delete(", "TRUNCATE", "delete(", "merge("):
        assert call not in src
    assert re.findall(r"(?<!with_for_)update\(", src) == []  # row locks only, no UPDATE
