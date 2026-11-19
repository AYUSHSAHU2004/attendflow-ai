"""API: health, docs, seed, detection, listing, logs and the error format."""

from __future__ import annotations

import json
import logging
from dataclasses import replace

from attendflow.config import REPO_ROOT, get_settings
from attendflow.data import load_dataset
from attendflow.db.models import PunchRow, ToolCallRow
from attendflow.engine.engine import run_engine
from attendflow.policy.models import load_policy
from tests.api_helpers import (
    AMIT_P1,
    RAVI,
    SANA_P2,
    assert_error,
    audit_count,
    confirm_amit_clock_out,
    get,
    session_for,
    snapshot,
)

EXPECTED_PATHS = {
    ("get", "/api/health"),
    ("post", "/api/seed"),
    ("post", "/api/detection/run"),
    ("get", "/api/exceptions"),
    ("get", "/api/exceptions/{exception_id}"),
    ("post", "/api/exceptions/{exception_id}/investigate"),
    ("get", "/api/exceptions/{exception_id}/investigate/{job_id}"),
    ("post", "/api/exceptions/{exception_id}/approve"),
    ("post", "/api/exceptions/{exception_id}/edit"),
    ("post", "/api/exceptions/{exception_id}/reject"),
    ("post", "/api/exceptions/{exception_id}/ask-worker"),
    ("post", "/api/exceptions/{exception_id}/worker-reply"),
    ("post", "/api/exceptions/{exception_id}/worker-confirm-time"),
    ("post", "/api/exceptions/{exception_id}/worker-manual-time"),
    ("get", "/api/audit-log"),
    ("get", "/api/tool-calls"),
    ("get", "/api/worker/messages"),
    ("get", "/api/supervisor/queue"),
    ("get", "/api/supervisor/auto-resolved"),
    ("post", "/api/exceptions/{exception_id}/undo"),
    ("get", "/api/admin/metrics/auto-resolve"),
    ("get", "/api/supervisor/cases/{exception_id}"),
    ("get", "/api/admin/exceptions"),
    ("get", "/api/admin/exceptions/{exception_id}"),
    # Phase 11. The /api/admin/demo/* helpers are absent: demo mode is off by default.
    ("post", "/api/punches"),
    ("get", "/api/admin/scheduler"),
    ("post", "/api/admin/scheduler/run-now"),
    ("post", "/api/admin/scheduler/start"),
    ("post", "/api/admin/scheduler/stop"),
    # Phase 13. /api/admin/demo/clock is demo-only too.
    ("post", "/api/exceptions/{exception_id}/escalate"),
}


# ---------------------------------------------------------------- system


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {
        "status": "ok",
        "database": "ok",
        "as_of": "2026-04-16T08:00:00",
        "policy_version": "2026.1",
        "version": "0.1.0",
    }
    assert r.headers["X-Request-ID"]


def test_health_reports_database_down(api_settings):
    from fastapi.testclient import TestClient

    from attendflow.api.app import create_app
    from attendflow.db.session import make_engine

    bad = make_engine("postgresql+psycopg://nobody:x@127.0.0.1:1/none?connect_timeout=1")
    with TestClient(create_app(api_settings, engine=bad), raise_server_exceptions=False) as c:
        r = c.get("/api/health")
        assert r.status_code == 503
        assert r.json()["database"] == "unreachable"
        assert_error(c.get("/api/exceptions"), 503, "database_unavailable")


def test_openapi_lists_every_endpoint_with_models(client):
    spec = client.get("/openapi.json").json()
    found = {(m, p) for p, ops in spec["paths"].items() for m in ops}
    assert found == EXPECTED_PATHS
    approve = spec["paths"]["/api/exceptions/{exception_id}/approve"]["post"]
    assert "requestBody" in approve
    assert {"200", "403", "404", "409", "422"} <= set(approve["responses"])
    assert "ErrorResponse" in spec["components"]["schemas"]
    assert client.get("/docs").status_code == 200


def test_request_id_is_echoed(client):
    r = client.get("/api/health", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"


def test_errors_have_one_shape(client):
    assert_error(client.get("/api/nope"), 404, "not_found")
    assert_error(client.get("/api/exceptions?status=done"), 422, "validation_error")
    assert_error(client.get("/api/exceptions?employee_id=amit"), 422, "validation_error")
    assert_error(client.get("/api/exceptions/P1-E999-2026-01-01"), 404, "exception_not_found")


# ---------------------------------------------------------------- seed


def test_seed_loads_every_csv(client):
    r = client.post("/api/seed")
    assert r.status_code == 200
    assert r.json()["counts"] == {
        "employees": 13,
        "timecards": 72,
        "schedule": 42,
        "leave_records": 6,
        "leave_balances": 30,
        "holidays": 6,
    }


def test_seed_is_a_full_reset(demo):
    assert demo.get("/api/exceptions").json()["count"] == 17
    assert demo.post("/api/seed").status_code == 200
    assert demo.get("/api/exceptions").json()["count"] == 0
    assert audit_count(demo) == 0


def test_seed_can_be_disabled(db_engine, api_settings):
    from fastapi.testclient import TestClient

    from attendflow.api.app import create_app

    app = create_app(replace(api_settings, enable_seed=False), engine=db_engine)
    with TestClient(app) as c:
        assert_error(c.post("/api/seed"), 403, "seed_disabled")


def test_seed_with_bad_csv_changes_nothing(demo, db_engine, api_settings, data_copy):
    from fastapi.testclient import TestClient

    from attendflow.api.app import create_app
    from tests.conftest import replace_in_file

    before = snapshot(demo)
    replace_in_file(data_copy / "timecards.csv", "P0001,E002", "P0001,E999")
    app = create_app(replace(api_settings, data_dir=data_copy), engine=db_engine)
    with TestClient(app) as c:
        err = assert_error(c.post("/api/seed"), 400, "invalid_data")
        assert any("E999" in e for e in err["details"])
    assert snapshot(demo) == before


# ---------------------------------------------------------------- detection


def test_detection_needs_data(client):
    assert_error(client.post("/api/detection/run"), 409, "not_seeded")


def test_detection_saves_the_17_expected_exceptions(client):
    client.post("/api/seed")
    r = client.post("/api/detection/run")
    assert r.status_code == 200
    run = r.json()
    assert (run["found"], run["created"], run["auto_resolved"]) == (17, 17, 1)
    assert run["by_policy"] == {
        "P1": 1, "P2": 1, "P3": 3, "P4": 1, "P5": 1, "P7": 1, "P8": 1,
        "P9": 1, "P10": 1, "P11": 1, "P12": 1, "P13": 1, "P14": 3,
    }  # fmt: skip

    # Same IDs as the engine on the CSVs (the stable natural key).
    settings = get_settings(env_file=None)
    engine_ids = [
        e.exception_id
        for e in run_engine(
            load_dataset(REPO_ROOT / "data"),
            load_policy(REPO_ROOT / "data" / "policy.json"),
            settings.as_of,
        ).exceptions
    ]
    items = client.get("/api/exceptions").json()["items"]
    assert sorted(i["id"] for i in items) == sorted(engine_ids)

    by_status = {}
    for i in items:
        by_status.setdefault(i["status"], []).append(i["id"])
    assert by_status["resolved"] == [SANA_P2]
    assert len(by_status["open"]) == 16
    for i in items:
        assert i["assigned_to"] == ("E101" if i["employee_id"] <= "E005" else "E102")
        assert i["created_at"] == "2026-04-16T08:00:00"  # the demo clock, not the server's
        assert i["waiting_since"] is None


def test_auto_resolved_p2_is_stored_resolved_with_the_tap_voided(demo):
    exc = get(demo, SANA_P2)
    assert exc["status"] == "resolved" and exc["auto_resolved"] is True
    assert exc["applied_fix"]["action"] == "auto_resolve"
    assert [a["action"] for a in exc["audit_trail"]] == ["detected", "auto_resolve"]
    assert all(a["actor"] == "system" for a in exc["audit_trail"])
    assert "policy.json" in exc["audit_trail"][1]["reason"]
    with session_for(demo) as s:
        assert s.get(PunchRow, "P0005").voided is True
        assert s.get(PunchRow, "P0005").voided_by_exception == SANA_P2
        assert s.get(PunchRow, "P0003").voided is False


def test_detection_twice_never_duplicates(demo):
    rows_before, audit_before = demo.get("/api/exceptions").json()["count"], audit_count(demo)
    run = demo.post("/api/detection/run").json()
    assert run["created"] == 0 and run["updated"] == 0
    assert run["unchanged"] == 16  # P2 is gone: its duplicate tap is now voided in the DB
    assert demo.get("/api/exceptions").json()["count"] == rows_before == 17
    assert audit_count(demo) == audit_before


def test_detection_closes_open_exceptions_that_disappear(demo):
    # Rejecting Sana's unscheduled holiday work voids those punches, so her P14 vanishes.
    r = demo.post(
        "/api/exceptions/P8-E005-2026-04-14-P0038/approve",
        json={"option_id": "reject_unscheduled_work"},
        headers=RAVI,
    )
    assert r.status_code == 200, r.text
    # Detection re-runs after a fix that changed data (Phase 9); a second run finds nothing.
    assert r.json()["detection"]["closed_exception_ids"] == ["P14-E005-2026-04-14-P0038"]
    assert demo.post("/api/detection/run").json()["closed_no_longer_detected"] == []
    p14 = get(demo, "P14-E005-2026-04-14-P0038")
    assert p14["status"] == "resolved"
    assert p14["audit_trail"][-1]["action"] == "no_longer_detected"
    assert p14["audit_trail"][-1]["actor"] == "system"


def test_detection_refreshes_open_exceptions(demo):
    # Fixing Amit's P1 makes his holiday hours known, so his open P14 gets new numbers.
    confirm_amit_clock_out(demo)
    demo.post(
        f"/api/exceptions/{AMIT_P1}/approve",
        json={"option_id": "set_clock_out_to_scheduled_end"},
        headers=RAVI,
    )
    # The approve already re-ran detection (Phase 9), so a second run changes nothing.
    assert demo.post("/api/detection/run").json()["updated"] == 0
    p14 = get(demo, "P14-E001-2026-04-14-P0037")
    assert p14["status"] == "open"
    assert "missing punch" not in p14["summary"]
    assert p14["audit_trail"][-1]["action"] == "updated_by_detection"
    assert get(demo, AMIT_P1)["status"] == "resolved"  # resolved is never reopened


# ---------------------------------------------------------------- list, audit, tool calls


def test_list_filters(demo):
    def ids(query: str) -> list[str]:
        r = demo.get(f"/api/exceptions?{query}")
        assert r.status_code == 200, r.text
        return [i["id"] for i in r.json()["items"]]

    assert ids("status=resolved") == [SANA_P2]
    assert ids("employee_id=E001") == [AMIT_P1, "P14-E001-2026-04-14-P0037"]
    assert ids("policy_id=P3") == [f"P3-E002-2026-04-1{d}" for d in (3, 4, 5)]
    assert ids("employee_id=E002&policy_id=P14") == ["P14-E002-2026-04-14-P0036"]
    assert len(ids("assigned_to=E102")) == 5  # Karan P7+P9, Dev P11+P12, Farah P13
    assert ids("status=escalated") == []


def test_list_is_sorted_by_employee_date_policy(demo):
    items = demo.get("/api/exceptions").json()["items"]
    keys = [(i["employee_id"], i["date"], int(i["policy_id"][1:])) for i in items]
    assert keys == sorted(keys)


def test_get_one_includes_audit_trail_and_evidence(demo):
    exc = get(demo, AMIT_P1)
    assert exc["policy_id"] == "P1" and exc["severity"] == "high"
    assert exc["fix_options"][0]["option_id"] == "set_clock_out_to_scheduled_end"
    assert exc["evidence"][0]["punch_id"] == "P0037"
    assert [a["action"] for a in exc["audit_trail"]] == ["detected"]


def test_audit_log_list_and_filters(demo):
    all_rows = demo.get("/api/audit-log").json()
    assert all_rows["count"] == 18  # 17 detected + 1 auto_resolve
    assert [a["id"] for a in all_rows["items"]] == sorted(a["id"] for a in all_rows["items"])
    one = demo.get(f"/api/audit-log?exception_id={SANA_P2}").json()
    assert [a["action"] for a in one["items"]] == ["detected", "auto_resolve"]
    assert demo.get("/api/audit-log?actor=supervisor").json()["count"] == 0
    assert demo.get("/api/audit-log?limit=5").json()["count"] == 5
    assert_error(demo.get("/api/audit-log?actor=robot"), 422, "validation_error")


def test_tool_calls_list(demo):
    assert demo.get("/api/tool-calls").json() == {"count": 0, "items": []}
    with session_for(demo) as s, s.begin():
        s.add(
            ToolCallRow(
                exception_id=AMIT_P1,
                step_no=1,
                tool_name="get_punches",
                input={"employee_id": "E001"},
                output={"rows": 3},
                created_at=demo.app.state.clock.now(),
            )
        )
    r = demo.get(f"/api/tool-calls?exception_id={AMIT_P1}").json()
    assert r["count"] == 1 and r["items"][0]["tool_name"] == "get_punches"
    assert demo.get("/api/tool-calls?exception_id=other").json()["count"] == 0


# ---------------------------------------------------------------- logging


def test_json_log_lines_have_timestamp_and_fields(capsys):
    from attendflow.api.logging_setup import configure_logging, request_id_var

    configure_logging("json", "INFO")
    token = request_id_var.set("req-1")
    logging.getLogger("attendflow.test").info("hello", extra={"event": "x", "n": 2})
    request_id_var.reset(token)
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["msg"] == "hello" and line["level"] == "INFO"
    assert line["request_id"] == "req-1" and line["event"] == "x" and line["n"] == 2
    assert line["ts"].endswith("+00:00")


def test_migrations_match_the_models(db_engine):
    """The Alembic migration and the SQLAlchemy models describe the same schema."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from attendflow.db.models import Base

    with db_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], f"run: alembic revision --autogenerate  ({diff})"
