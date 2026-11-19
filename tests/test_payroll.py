"""Readiness shares engine decisions and requires an explicit payroll-admin sign-off."""

from dataclasses import replace
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from attendflow.api.app import create_app
from attendflow.cases.payroll import _case_dates, _case_reason, _status
from attendflow.config import get_settings
from attendflow.data.loader import load_dataset
from attendflow.db.models import ExceptionRow, LeaveRecordRow, PunchRow
from attendflow.db.seed import add_demo_week
from attendflow.engine.engine import run_engine
from attendflow.policy.models import load_policy
from tests.api_helpers import (
    AMIT,
    AMIT_P1,
    PRIYA,
    RAVI,
    SANA_P2,
    assert_error,
    get,
    post,
    session_for,
    snapshot,
    store_test_investigation,
)
from tests.test_e2e_prototype import write_log  # noqa: F401 - a fixture
from tests.test_e2e_scheduler import _clock, _cycle
from tests.test_ingest import NEHA_IN, NEHA_P1

CLOSED_WEEK = "2026-04-06"
CURRENT_WEEK = "2026-04-13"


def test_optional_demo_week_preserves_every_default_finding(monkeypatch):
    monkeypatch.delenv("ATTENDFLOW_DEMO_EXTRA_WEEK", raising=False)
    settings = get_settings(env_file=None)
    assert settings.demo_extra_week is False
    data = load_dataset(settings.data_dir)
    policy = load_policy(settings.data_dir / "policy.json")
    baseline = run_engine(data, policy, settings.as_of).exceptions
    original_schedule = list(data.schedule)
    original_punches = list(data.punches)
    add_demo_week(data)
    assert run_engine(data, policy, settings.as_of).exceptions == baseline
    assert len(baseline) == 17
    assert data.schedule[: len(original_schedule)] == original_schedule
    assert data.punches[: len(original_punches)] == original_punches
    earlier = data.schedule[len(original_schedule) :]
    assert {row.date for row in earlier} == {date(2026, 4, day) for day in range(6, 11)}
    assert {row.employee_id for row in earlier} == {
        row.employee_id for row in data.employees if row.role == "worker"
    }
    assert len(set(p.punch_id for p in data.punches)) == len(data.punches)


@pytest.mark.parametrize(
    "number,blocking",
    [(n, n not in (6, 7, 16)) for n in range(1, 18) if n != 15],
)
def test_each_policy_leaves_a_reason_and_human_decision_clears_it(number, blocking):
    row = ExceptionRow(
        id="case",
        employee_id="E001",
        policy_id=f"P{number}",
        title="Review time",
        status="open",
        no_reply_stage=0,
        auto_resolved=False,
        proposed_fix=None,
        fix_options=[],
    )
    result = _case_reason(row, {})
    assert result["blocking"] == blocking
    assert result["exception_ids"] == ["case"]
    assert _status([result]) == ("blocked" if blocking else "ready_with_notes")
    row.status = "resolved"
    assert _case_reason(row, {}) is None


def test_multi_day_leave_reason_crosses_week_boundary():
    for policy, key in (("P11", "requested_dates"), ("P12", "dates")):
        row = ExceptionRow(
            policy_id=policy,
            date=date(2026, 4, 12),
            details={key: ["2026-04-13"]},
        )
        assert _case_dates(row) == {"2026-04-12", "2026-04-13"}


def report(client, week=None, headers=PRIYA):
    params = {"week_start": week} if week else {}
    result = client.get("/api/payroll", headers=headers, params=params)
    assert result.status_code == 200, result.text
    return result.json()


def decision(client, action, week=CLOSED_WEEK, actor=PRIYA, **body):
    return client.post(f"/api/payroll/{week}/{action}", headers=actor, json=body)


@pytest.fixture
def extra_client(db_engine, api_settings):
    settings = replace(
        api_settings,
        demo_mode=True,
        demo_extra_week=True,
        llm_base_url="http://127.0.0.1:1",
    )
    app = create_app(settings, engine=db_engine)
    with TestClient(app, raise_server_exceptions=False) as client:
        seeded = client.post("/api/seed")
        assert seeded.status_code == 200, seeded.text
        yield client


def test_payroll_signoff_and_reopen(write_log, extra_client):  # noqa: F811
    c = extra_client
    assert report(c, CLOSED_WEEK)["status"] == "ready"
    reset = c.post("/api/admin/demo/reset", headers=PRIYA)
    assert reset.status_code == 200, reset.text
    assert reset.json()["detection"]["found"] == 17
    assert report(c)["status"] == "blocked"
    assert report(c)["closed"] is False
    assert get(c, AMIT_P1)["status"] == "open"
    assert_error(decision(c, "sign-off", CURRENT_WEEK), 409, "payroll_not_signable")
    _clock(c, 120)
    assert_error(decision(c, "sign-off", CURRENT_WEEK), 409, "payroll_not_signable")
    assert_error(decision(c, "sign-off", "2026-03-30"), 409, "payroll_not_signable")
    assert_error(decision(c, "sign-off", actor=RAVI), 403, "admin_only")
    assert_error(
        decision(c, "reopen", actor=AMIT, reason="Recheck the attendance"), 403, "admin_only"
    )

    before = snapshot(c)
    write_log.clear()
    ready = report(c, CLOSED_WEEK)
    assert ready["can_sign"] and ready["signoff"] is None
    assert ready["closed"] and ready["has_data"]
    assert all(worker["worked_hours"] == 20 for worker in ready["workers"])
    assert report(c, CLOSED_WEEK, RAVI)["signoff"] is None
    signed = decision(c, "sign-off", note="Attendance checked")
    assert signed.status_code == 200, signed.text
    signoff = signed.json()["signoff"]
    assert signoff["signer_name"] == "Priya Sharma" and not signoff["stale"]
    assert signoff["signed_at"] == "2026-04-21T08:00:00"
    assert report(c, CLOSED_WEEK)["signoff"] == signoff
    assert_error(decision(c, "sign-off"), 409, "payroll_not_signable")
    assert decision(c, "reopen", reason="  ").status_code == 422
    reason = "Review the period again"
    reopened = decision(c, "reopen", reason=reason)
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["can_sign"] and reopened.json()["signoff"]["reopened_at"]
    assert decision(c, "sign-off").status_code == 200
    assert snapshot(c) == before
    assert not [event for event in write_log if event["writer"] != "seed"]
    assert get(c, AMIT_P1)["status"] == "open"

    feed = c.get("/api/activity", headers=PRIYA).json()["items"]
    events = [item for item in feed if item["action"].startswith("payroll_")]
    assert [item["action"] for item in events] == [
        "payroll_signed_off",
        "payroll_reopened",
        "payroll_signed_off",
    ]
    assert all(item["actor_name"] == "Priya Sharma" and not item["autonomous"] for item in events)
    assert events[1]["reason"] == reason
    assert not any(
        item["action"].startswith("payroll_")
        for item in c.get("/api/activity", headers=RAVI).json()["items"]
    )
    assert not any(
        item["action"].startswith("payroll_") for item in c.get("/api/audit-log").json()["items"]
    )


def test_pending_leave_blocks_a_closed_week_and_makes_a_signoff_stale(extra_client):
    c = extra_client
    assert decision(c, "sign-off").status_code == 200
    with session_for(c) as session, session.begin():
        session.add(
            LeaveRecordRow(
                employee_id="E007",
                date=date(2026, 4, 11),
                leave_type="casual",
                duration="full",
                status="pending",
                certificate_uploaded=False,
            )
        )
    blocked = report(c, CLOSED_WEEK)
    assert blocked["status"] == "blocked" and blocked["signoff"]["stale"]
    assert [(r["code"], r["owner_id"]) for r in blocked["reasons"]] == [("pending_leave", "E102")]
    assert decision(c, "reopen", reason="Review the newly entered leave").status_code == 200
    assert_error(decision(c, "sign-off"), 409, "payroll_not_signable")
    with session_for(c) as session, session.begin():
        leave = session.scalars(
            select(LeaveRecordRow).filter_by(
                employee_id="E007",
                date=date(2026, 4, 11),
            )
        ).one()
        leave.status = "rejected"
    assert report(c, CLOSED_WEEK)["status"] == "ready"
    assert decision(c, "sign-off").status_code == 200


def test_readiness_counts_match_dashboard_and_admin_and_scope_is_enforced(demo):
    chart = demo.get("/api/dashboard", headers=PRIYA).json()
    counts = demo.get("/api/admin/exceptions", headers=PRIYA).json()["counters"]
    readiness = report(demo)
    assert readiness["exception_counts"] == counts
    assert chart["active_total"] == sum(counts[status] for status in chart["by_status"])
    meena = next(worker for worker in readiness["workers"] if worker["employee_id"] == "E002")
    forecast = next(row for row in chart["overtime"]["workers"] if row["employee_id"] == "E002")
    for field in ("worked_hours", "scheduled_remaining_hours", "projected_hours"):
        assert meena[field] == forecast[field]
    team = report(demo, headers=RAVI)
    assert team["scope"] == "team"
    assert {worker["team"] for worker in team["workers"]} == {"Inbound"}
    assert set(reason["employee_id"] for reason in team["reasons"]) <= {
        worker["employee_id"] for worker in team["workers"]
    }
    assert demo.get("/api/payroll", headers=AMIT).status_code == 403
    assert demo.get("/api/payroll?week_start=2026-04-14", headers=PRIYA).status_code == 422
    assert report(demo, CLOSED_WEEK)["has_data"] is False
    assert any(r["code"] == "auto_resolved" and not r["blocking"] for r in readiness["reasons"])


def test_undo_and_ladder_change_reasons_until_human_decision(extra_client):
    c = extra_client
    assert c.post("/api/admin/demo/reset", headers=PRIYA).status_code == 200
    assert c.post("/api/admin/demo/punch", headers=PRIYA, json=NEHA_IN).status_code == 201
    first = c.post("/api/admin/scheduler/run-now", headers=PRIYA)
    assert first.status_code == 200, first.text
    assert first.json()["errors"] == []
    assert NEHA_P1 in first.json()["messages_sent"]

    def for_case(case_id):
        return [r for r in report(c)["reasons"] if case_id in r["exception_ids"]]

    assert all(r["blocking"] for r in for_case(NEHA_P1))
    assert for_case(NEHA_P1)[0]["owner_id"] == "E004"
    _clock(c, 8)
    assert _cycle(c)["reminded"] == [NEHA_P1]
    assert for_case(NEHA_P1)[0]["code"] == "awaiting_reply"
    _clock(c, 16)
    assert _cycle(c)["to_supervisor"] == [NEHA_P1]
    assert for_case(NEHA_P1)[0]["owner_id"] == "E101"
    ok = post(
        c,
        NEHA_P1,
        "approve",
        {
            "option_id": "set_clock_out_to_scheduled_end",
            "reason": "Reviewed the shift schedule and site records",
            "without_worker": True,
            "confirm_time_without_worker": True,
        },
        RAVI,
    )
    assert ok.status_code == 200, ok.text
    assert [(r["code"], r["blocking"]) for r in for_case(NEHA_P1)] == [("without_worker", False)]

    assert not for_case(SANA_P2)[0]["blocking"]
    undo = post(c, SANA_P2, "undo", {"reason": "Review duplicate punches manually"}, RAVI)
    assert undo.status_code == 200, undo.text
    assert for_case(SANA_P2)[0]["blocking"]
    resolved = post(c, SANA_P2, "approve", {"option_id": "void_duplicate"}, RAVI)
    assert resolved.status_code == 200, resolved.text
    assert not for_case(SANA_P2)
    assert get(c, AMIT_P1)["status"] == "open"


def test_closed_week_becomes_ready_with_notes_after_a_human_decision(extra_client):
    c = extra_client
    assert c.post("/api/admin/demo/reset", headers=PRIYA).status_code == 200
    case_id = "P1-E001-2026-04-10"
    with session_for(c) as session, session.begin():
        punch = session.scalars(
            select(PunchRow).filter_by(
                employee_id="E001",
                timestamp=datetime(2026, 4, 10, 13),
                type="out",
            )
        ).one()
        punch.voided = True
    assert report(c, CLOSED_WEEK)["status"] == "blocked"
    assert_error(decision(c, "sign-off"), 409, "payroll_not_signable")
    detection = c.post("/api/detection/run")
    assert detection.status_code == 200, detection.text
    assert case_id in detection.json()["exception_ids"]
    store_test_investigation(c, case_id)
    asked = post(c, case_id, "ask-worker", {}, RAVI)
    assert asked.status_code == 200, asked.text
    _clock(c, 8)
    assert case_id in _cycle(c)["reminded"]
    _clock(c, 16)
    assert case_id in _cycle(c)["to_supervisor"]
    approved = post(
        c,
        case_id,
        "approve",
        {
            "option_id": "set_clock_out_to_scheduled_end",
            "reason": "Reviewed the shift schedule and gate records",
            "without_worker": True,
            "confirm_time_without_worker": True,
        },
        RAVI,
    )
    assert approved.status_code == 200, approved.text
    result = report(c, CLOSED_WEEK)
    assert result["status"] == "ready_with_notes" and result["can_sign"]
    assert [(row["code"], row["exception_ids"]) for row in result["reasons"]] == [
        ("without_worker", [case_id])
    ]
    assert decision(c, "sign-off").status_code == 200
    assert get(c, AMIT_P1)["status"] == "open"
