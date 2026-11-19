"""Phase 11: the mock attendance device (POST /api/punches) and detection after a punch.

Numbers and IDs are read from the database or the engine, never hard-coded, except the
agreed demo scenario: Neha (E004) clocks in on Wed 15 Apr and has no clock-out, which
the engine turns into a fresh P1 once her shift plus the P1 grace has passed.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from attendflow.api.app import create_app
from attendflow.cases import service
from attendflow.cases.service import punch_scope
from attendflow.db.models import AuditLogRow, ExceptionRow, PunchRow
from tests.api_helpers import (
    AMIT,
    NEHA_P10,
    PRIYA,
    RAVI,
    assert_error,
    audit_count,
    get,
    session_for,
    snapshot,
)

DEVICE = {"X-Device-Key": "test-device-key"}
NEHA = "E004"
NEHA_IN = {"employee_id": NEHA, "timestamp": "2026-04-15T08:58", "type": "in"}
NEHA_P1 = "P1-E004-2026-04-15"


def send(client, body: dict, headers: dict = DEVICE):
    return client.post("/api/punches", json=body, headers=headers)


def latest_device_punch(client, employee_id: str) -> PunchRow:
    with session_for(client) as s:
        return s.scalars(
            select(PunchRow)
            .where(PunchRow.employee_id == employee_id, PunchRow.source == "device")
            .order_by(PunchRow.timestamp.desc())
        ).first()


def next_punch_id(client) -> str:
    with session_for(client) as s:
        ids = s.scalars(select(PunchRow.punch_id)).all()
    return f"P{max(int(i[1:]) for i in ids) + 1:04d}"


# ---------------------------------------------------------------- accepted punch


def test_valid_punch_is_stored_audited_and_detected(demo):
    expected_id = next_punch_id(demo)
    usual = latest_device_punch(demo, NEHA)
    r = send(demo, NEHA_IN)
    assert r.status_code == 201, r.text
    body = r.json()
    punch = body["punch"]
    assert punch == {
        "punch_id": expected_id,
        "employee_id": NEHA,
        "timestamp": "2026-04-15T08:58:00",
        "type": "in",
        "source": "device",
        "device_id": usual.device_id,  # the worker's usual device, read from the data
        "location": usual.location,
    }
    with session_for(demo) as s:
        row = s.get(PunchRow, expected_id)
        assert (row.voided, row.created_by_exception, row.voided_by_exception) == (
            False,
            None,
            None,
        )
        [audit] = s.scalars(select(AuditLogRow).where(AuditLogRow.action == "punch_ingested"))
    assert (audit.actor, audit.actor_id, audit.exception_id) == ("device", None, None)
    assert audit.after == {**punch, "via": "device_api", "requested_by": None}

    # Detection ran for Neha's week: a fresh P1, and the "no punches" P10 is closed.
    detection = body["detection"]
    assert detection["ran"] is True and detection["error"] is None
    assert detection["new_exception_ids"] == [NEHA_P1]
    assert detection["closed_exception_ids"] == [NEHA_P10]
    assert detection["scope"] == {"employee_id": NEHA, "start": "2026-04-13", "end": "2026-04-19"}
    p1 = get(demo, NEHA_P1)
    assert (p1["status"], p1["assigned_to"]) == ("open", "E101")
    assert [a["action"] for a in p1["audit_trail"]] == ["detected"]
    assert get(demo, NEHA_P10)["status"] == "resolved"
    with session_for(demo) as s:
        [post] = s.scalars(select(AuditLogRow).where(AuditLogRow.action == "post_punch_detection"))
    assert post.actor == "system" and post.after["punch_id"] == expected_id

    # Idempotent: a full detection run afterwards creates nothing new.
    assert demo.post("/api/detection/run").json()["created"] == 0


def test_explicit_device_and_known_location_are_kept(demo):
    with session_for(demo) as s:
        other = s.scalars(
            select(PunchRow).where(PunchRow.employee_id != NEHA, PunchRow.source == "device")
        ).first()
    body = {**NEHA_IN, "device_id": "GATE-TEST", "location": other.location}
    r = send(demo, body)
    assert r.status_code == 201, r.text
    assert (r.json()["punch"]["device_id"], r.json()["punch"]["location"]) == (
        "GATE-TEST",
        other.location,
    )


# ---------------------------------------------------------------- refused punches


def _unchanged(client, call):
    before, audits = snapshot(client), audit_count(client)
    response = call()
    assert snapshot(client) == before
    assert audit_count(client) == audits
    return response


@pytest.mark.parametrize(
    ("headers", "status", "code"),
    [
        ({}, 401, "invalid_device_key"),
        ({"X-Device-Key": "wrong"}, 401, "invalid_device_key"),
        ({"X-Device-Key": ""}, 401, "invalid_device_key"),
        (PRIYA, 401, "invalid_device_key"),  # an actor is not a device
    ],
)
def test_device_key_is_required(demo, headers, status, code):
    assert_error(_unchanged(demo, lambda: send(demo, NEHA_IN, headers)), status, code)


def test_device_api_off_without_a_key(db_engine, api_settings):
    app = create_app(replace(api_settings, device_api_key=None), engine=db_engine)
    with TestClient(app, raise_server_exceptions=False) as c:
        assert_error(send(c, NEHA_IN), 503, "device_api_not_configured")


@pytest.mark.parametrize(
    ("change", "status", "code"),
    [
        ({"employee_id": "E999"}, 422, "unknown_employee"),
        ({"employee_id": "E101"}, 422, "not_a_worker"),
        ({"type": "lunch"}, 422, "validation_error"),
        ({"source": "app"}, 422, "validation_error"),
        ({"timestamp": "2026-04-15T08:58+05:30"}, 422, "validation_error"),
        ({"timestamp": "2026-04-15 08:58"}, 422, "validation_error"),
        ({"timestamp": "2026-02-30T09:00"}, 422, "validation_error"),
        ({"timestamp": "yesterday"}, 422, "validation_error"),
        ({"location": "Somewhere else"}, 422, "unknown_location"),
        ({"device_id": "gate 1; drop"}, 422, "validation_error"),
        ({"extra": 1}, 422, "validation_error"),
    ],
)
def test_bad_input_is_refused_and_nothing_is_written(demo, change, status, code):
    body = {**NEHA_IN, **change}
    assert_error(_unchanged(demo, lambda: send(demo, body)), status, code)


def test_future_and_too_old_punches_are_refused(demo):
    settings = demo.app.state.settings
    now = demo.app.state.clock.now()
    later = (now + timedelta(minutes=1)).isoformat(timespec="minutes")
    oldest = now - timedelta(days=settings.device_max_backdate_days)
    old = (oldest - timedelta(minutes=1)).isoformat(timespec="minutes")
    for stamp, code in ((later, "punch_in_future"), (old, "punch_too_old")):
        body = {**NEHA_IN, "timestamp": stamp}
        assert_error(_unchanged(demo, lambda body=body: send(demo, body)), 422, code)
    # Exactly "now" is allowed (not after the as-of time).
    exact = {**NEHA_IN, "timestamp": now.isoformat(timespec="seconds"), "type": "break_start"}
    assert send(demo, exact).status_code == 201


def test_exact_duplicates_are_refused(demo):
    with session_for(demo) as s:
        seeded = s.scalars(select(PunchRow).where(PunchRow.employee_id == "E001")).first()
    copy = {
        "employee_id": seeded.employee_id,
        "timestamp": seeded.timestamp.isoformat(timespec="seconds"),
        "type": seeded.type,
    }
    err = assert_error(_unchanged(demo, lambda: send(demo, copy)), 409, "duplicate_punch")
    assert err["details"] == {"punch_id": seeded.punch_id}

    assert send(demo, NEHA_IN).status_code == 201
    assert_error(_unchanged(demo, lambda: send(demo, NEHA_IN)), 409, "duplicate_punch")
    # Same minute but another type is a different punch.
    assert send(demo, {**NEHA_IN, "type": "break_start"}).status_code == 201


def test_punch_before_seed_is_refused(client):
    assert_error(send(client, NEHA_IN), 422, "unknown_employee")


# ---------------------------------------------------------------- detection after a punch


def test_detection_after_a_punch_is_scoped_to_that_worker(demo):
    """A change elsewhere (here: a row written straight into the test DB) is not picked up
    by the punch's detection; the next full run finds it."""
    with session_for(demo) as s, s.begin():
        s.add(
            PunchRow(
                punch_id="P9001",
                employee_id="E009",
                timestamp=datetime(2026, 4, 14, 9, 0),
                type="in",
                source="device",
                device_id="GATE-01",
                location=latest_device_punch(demo, NEHA).location,
                voided=False,
            )
        )
    before = {
        r["id"]: (r["status"], r["updated_at"])
        for r in demo.get("/api/exceptions").json()["items"]
        if r["employee_id"] != NEHA
    }
    r = send(demo, NEHA_IN)
    assert r.status_code == 201
    assert all(
        i.startswith(("P1-E004", "P10-E004")) for i in r.json()["detection"]["new_exception_ids"]
    )
    after = {
        r["id"]: (r["status"], r["updated_at"])
        for r in demo.get("/api/exceptions").json()["items"]
        if r["employee_id"] != NEHA
    }
    assert after == before
    full = demo.post("/api/detection/run").json()
    assert any("E009" in i for i in full["created_ids"])


def test_punch_scope_covers_a_night_shift_across_the_week_start():
    scope = punch_scope("E003", datetime(2026, 4, 20, 2, 0))  # Monday 02:00
    assert (scope.start.isoformat(), scope.end.isoformat()) == ("2026-04-13", "2026-04-26")
    scope = punch_scope("E003", datetime(2026, 4, 15, 9, 0))  # Wednesday
    assert (scope.start.isoformat(), scope.end.isoformat()) == ("2026-04-13", "2026-04-19")


def test_failed_detection_keeps_the_punch_and_is_audited(demo, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("database hiccup")

    monkeypatch.setattr(service, "run_detection", boom)
    r = send(demo, NEHA_IN)
    assert r.status_code == 201, r.text
    detection = r.json()["detection"]
    assert detection["ran"] is False and "next run" in detection["error"]
    punch_id = r.json()["punch"]["punch_id"]
    with session_for(demo) as s:
        assert s.get(PunchRow, punch_id) is not None
        [failed] = s.scalars(
            select(AuditLogRow).where(AuditLogRow.action == "post_punch_detection_failed")
        )
        assert s.get(ExceptionRow, NEHA_P1) is None
    assert failed.actor == "system" and "RuntimeError" in failed.reason
    assert "database hiccup" not in failed.reason  # only the type is stored

    monkeypatch.undo()
    assert NEHA_P1 in demo.post("/api/detection/run").json()["created_ids"]


def test_concurrent_writers_never_share_a_punch_id(demo):
    """The ingest module and fixes/apply.py number punches under the same lock."""
    from attendflow.db.models import PUNCH_ID_LOCK
    from attendflow.fixes import apply

    assert apply._PUNCH_ID_LOCK == PUNCH_ID_LOCK
    first = send(demo, NEHA_IN).json()["punch"]["punch_id"]
    second = send(demo, {**NEHA_IN, "type": "break_start"}).json()["punch"]["punch_id"]
    assert int(second[1:]) == int(first[1:]) + 1
    with session_for(demo) as s:
        assert s.scalar(select(func.count()).select_from(PunchRow)) == int(second[1:])


def test_workers_and_supervisors_cannot_use_the_device_route_as_actors(demo):
    for actor in (AMIT, RAVI):
        assert_error(send(demo, NEHA_IN, actor), 401, "invalid_device_key")
