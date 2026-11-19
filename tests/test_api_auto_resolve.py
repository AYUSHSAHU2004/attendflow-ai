"""Phase 12 through the API: auto-resolve snapshot, undo, refusals, permissions, the kill
switch, the scheduler, and the "resolved without a human" metric.

Sana's P2 (two clock-ins 2 min apart, P0003 kept, P0005 voided) is the planted case; Neha's
09:02 clock-in (demo punch) gives a live P7 within grace.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from attendflow.db.models import AuditLogRow, ExceptionRow, PunchRow
from attendflow.fixes.apply import punch_snapshot
from tests.api_helpers import (
    AMIT_P1,
    PRIYA,
    RAVI,
    SANA_P2,
    SANA_P8,
    SUNITA,
    assert_error,
    audit_count,
    get,
    post,
    session_for,
    snapshot,
)
from tests.test_admin import detail, overview
from tests.test_e2e_prototype import (  # noqa: F401 - write_log is a fixture
    assert_writes_audited,
    write_log,
)

SANA = {"X-Actor-Id": "E005"}
NEHA_0902 = {"employee_id": "E004", "timestamp": "2026-04-15T09:02", "type": "in"}
NEHA_P7 = "P7-E004-2026-04-15-late"
NEHA_P1 = "P1-E004-2026-04-15"
NEHA_P10 = "P10-E004-2026-04-15"
REASON = "Checking the second tap with the worker first"


def undo(client, exception_id: str, headers: dict, reason: str = REASON):
    return post(client, exception_id, "undo", {"reason": reason}, headers)


def metric(client, **params) -> dict:
    r = client.get("/api/admin/metrics/auto-resolve", headers=PRIYA, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def punch_row(client, punch_id: str) -> dict:
    with session_for(client) as s:
        return punch_snapshot(s.get(PunchRow, punch_id))


def audits(client, exception_id: str, action: str) -> list[AuditLogRow]:
    with session_for(client) as s:
        return list(
            s.scalars(
                select(AuditLogRow)
                .where(AuditLogRow.exception_id == exception_id, AuditLogRow.action == action)
                .order_by(AuditLogRow.id)
            )
        )


def by_policy(m: dict) -> dict:
    return {p["policy_id"]: p for p in m["by_policy"]}


# ---------------------------------------------------------------- snapshot


def test_auto_resolve_stores_an_exact_before_and_after_snapshot(demo):
    case = get(demo, SANA_P2)
    fix = case["applied_fix"]
    assert (case["status"], case["auto_resolved"]) == ("resolved", True)
    assert fix["action"] == "auto_resolve" and fix["snapshot_version"] == 1
    assert fix["basis"] == "2 'in' taps 2 min apart, within the 5 min duplicate window"
    [change] = fix["changes"]
    assert change["punch_id"] == "P0005"
    assert change["before"]["voided"] is False and change["before"]["voided_by_exception"] is None
    assert change["after"] == punch_row(demo, "P0005")  # what is stored now
    assert {
        k: v for k, v in change["before"].items() if k not in ("voided", "voided_by_exception")
    } == {k: v for k, v in change["after"].items() if k not in ("voided", "voided_by_exception")}
    [guard] = fix["guarded_rows"]
    assert guard["row"] == punch_row(demo, "P0003")  # the kept tap, unchanged
    [audit] = audits(demo, SANA_P2, "auto_resolve")
    assert (audit.actor, audit.actor_id) == ("system", None)
    assert audit.after["changes"] == fix["changes"] and audit.after["policy_id"] == "P2"
    assert "within policy" in audit.reason


# ---------------------------------------------------------------- undo


def test_undo_restores_the_exact_old_values_and_reopens_the_case(demo):
    before_fix = get(demo, SANA_P2)["applied_fix"]["changes"][0]["before"]
    r = undo(demo, SANA_P2, RAVI)
    assert r.status_code == 200, r.text
    body = r.json()
    assert punch_row(demo, "P0005") == before_fix  # every column back exactly
    assert body["status"] == "open" and body["assigned_to"] == "E101"
    assert body["auto_resolved"] is False and body["applied_fix"] is None
    assert body["auto_resolve_undone_by"] == "E101" and body["auto_resolve_undone_at"]
    assert [c["op"] for c in body["restored"]] == ["restore"]
    assert body["detection"]["ran"] is True
    [audit] = audits(demo, SANA_P2, "auto_resolve_undone")
    assert (audit.actor, audit.actor_id, audit.reason) == ("supervisor", "E101", REASON)
    assert audit.before["applied_fix"]["changes"][0]["punch_id"] == "P0005"
    assert audit.after["changes"][0]["after"] == before_fix
    assert audit.after["policy_id"] == "P2"
    assert audits(demo, SANA_P2, "post_undo_detection")


def test_an_undone_case_is_never_auto_resolved_again(demo):
    assert undo(demo, SANA_P2, RAVI).status_code == 200
    for _ in range(2):
        run = demo.post("/api/detection/run")
        assert run.status_code == 200 and run.json()["auto_resolved"] == 0
    case = get(demo, SANA_P2)
    assert (case["status"], case["auto_resolved"]) == ("open", False)
    assert len(audits(demo, SANA_P2, "auto_resolve")) == 1
    assert punch_row(demo, "P0005")["voided"] is False


def test_after_undo_a_person_decides_with_the_normal_flow(demo):
    assert undo(demo, SANA_P2, RAVI).status_code == 200
    queue = demo.get("/api/supervisor/queue", headers=RAVI).json()["items"]
    [item] = [i for i in queue if i["exception_id"] == SANA_P2]
    assert item["auto_resolve_undone"] is True
    approved = post(demo, SANA_P2, "approve", {"option_id": "void_duplicate"}, RAVI)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "resolved"
    assert approved.json()["auto_resolved"] is False  # a human decided it
    row = punch_row(demo, "P0005")
    assert (row["voided"], row["voided_by_exception"]) == (True, SANA_P2)


def test_undo_is_refused_when_the_changed_row_was_edited_since(demo):
    with session_for(demo) as s, s.begin():
        s.get(PunchRow, "P0005").location = "Edited by hand"
    before, case_before, n = snapshot(demo), get(demo, SANA_P2), audit_count(demo)
    err = assert_error(undo(demo, SANA_P2, PRIYA), 409, "undo_conflict")
    assert err["details"]["conflicts"] == [{"punch_id": "P0005", "changed_fields": ["location"]}]
    assert snapshot(demo) == before
    after = get(demo, SANA_P2)
    assert {k: after[k] for k in ("status", "auto_resolved", "applied_fix")} == {
        k: case_before[k] for k in ("status", "auto_resolved", "applied_fix")
    }
    assert audit_count(demo) == n + 1  # only the refusal is recorded
    [refused] = audits(demo, SANA_P2, "undo_refused")
    assert (refused.actor_id, refused.after["code"]) == ("E201", "undo_conflict")


def test_undo_is_refused_when_the_kept_punch_changed_since(demo):
    with session_for(demo) as s, s.begin():
        row = s.get(PunchRow, "P0003")
        row.voided, row.voided_by_exception = True, "P1-E005-2026-04-13"
    before = snapshot(demo)
    err = assert_error(undo(demo, SANA_P2, RAVI), 409, "undo_conflict")
    assert err["details"]["conflicts"][0]["punch_id"] == "P0003"
    assert snapshot(demo) == before


def test_undo_is_refused_when_another_fix_touched_that_day_later(demo):
    # A later audited fix of another case added a correction punch on Sana's Monday.
    with session_for(demo) as s, s.begin():
        s.add(
            PunchRow(
                punch_id="P0999",
                employee_id="E005",
                timestamp=datetime(2026, 4, 13, 18, 0),
                type="out",
                source="correction",
                device_id="CORRECTION",
                location="Supervisor correction",
                voided=False,
                created_by_exception=SANA_P8,
            )
        )
        s.add(
            AuditLogRow(
                exception_id=SANA_P8,
                actor="supervisor",
                actor_id="E101",
                action="approve",
                after={"applied_fix": {"changes": [{"punch_id": "P0999"}]}},
                created_at=datetime(2026, 4, 16, 8, 0),
            )
        )
    before = snapshot(demo)
    err = assert_error(undo(demo, SANA_P2, RAVI), 409, "undo_conflict")
    assert err["details"]["later_fixes"] == [{"exception_id": SANA_P8, "punch_ids": ["P0999"]}]
    assert snapshot(demo) == before


def test_undo_without_a_snapshot_is_refused(demo):
    with session_for(demo) as s, s.begin():
        row = s.get(ExceptionRow, SANA_P2)
        row.applied_fix = {"action": "auto_resolve", "policy_id": "P2", "changes": []}
    before = snapshot(demo)
    assert_error(undo(demo, SANA_P2, PRIYA), 409, "undo_unavailable")
    assert snapshot(demo) == before
    assert audits(demo, SANA_P2, "undo_refused")


def test_only_auto_resolved_cases_can_be_undone_and_only_once(demo):
    assert_error(undo(demo, AMIT_P1, RAVI), 409, "not_auto_resolved")
    assert undo(demo, SANA_P2, RAVI).status_code == 200
    assert_error(undo(demo, SANA_P2, PRIYA), 409, "already_undone")


# ---------------------------------------------------------------- permissions


def test_a_worker_cannot_undo(demo):
    before = snapshot(demo)
    assert_error(undo(demo, SANA_P2, SANA), 403, "supervisor_only")
    assert snapshot(demo) == before and get(demo, SANA_P2)["auto_resolved"] is True


def test_a_supervisor_can_undo_only_their_own_team(demo):
    assert_error(undo(demo, SANA_P2, SUNITA), 403, "not_assigned")
    assert get(demo, SANA_P2)["auto_resolved"] is True
    assert undo(demo, SANA_P2, RAVI).status_code == 200


def test_the_payroll_admin_can_undo_any_case(demo):
    r = undo(demo, SANA_P2, PRIYA)
    assert r.status_code == 200, r.text
    assert r.json()["assigned_to"] == "E101"  # back to the worker's supervisor
    [audit] = audits(demo, SANA_P2, "auto_resolve_undone")
    assert (audit.actor, audit.actor_id) == ("admin", "E201")


def test_undo_needs_a_reason(demo):
    assert_error(undo(demo, SANA_P2, RAVI, reason="too short"), 422, "validation_error")
    assert get(demo, SANA_P2)["auto_resolved"] is True


def test_unknown_actor_cannot_undo(demo):
    assert_error(undo(demo, SANA_P2, {"X-Actor-Id": "E999"}), 403, "unknown_actor")


# ---------------------------------------------------------------- visibility


def test_admin_detail_explains_the_auto_resolve_and_offers_undo(demo):
    info = detail(demo, SANA_P2)["auto_fix"]
    assert info["state"] == "auto_resolved" and info["resolved_by"] == "system"
    assert info["basis"] == "2 'in' taps 2 min apart, within the 5 min duplicate window"
    assert info["policy_quote"].startswith("Keep the earliest punch and void the later one.")
    assert info["changes"] == ["P0005 clock-in 08:59: voided (kept in the database)"]
    assert info["can_undo"] is True and info["undone_by"] is None
    summaries = [a["summary"] for a in detail(demo, SANA_P2)["audit_trail"]]
    assert summaries[-1].startswith("Auto-resolved by the system: 2 'in' taps 2 min apart")

    assert undo(demo, SANA_P2, PRIYA).status_code == 200
    info = detail(demo, SANA_P2)["auto_fix"]
    assert info["state"] == "undone" and info["can_undo"] is False
    assert (info["undone_by"], info["undone_by_name"], info["undo_reason"]) == (
        "E201",
        "Priya Sharma",
        REASON,
    )
    summaries = [a["summary"] for a in detail(demo, SANA_P2)["audit_trail"]]
    assert "Priya Sharma undid the auto-resolve, 1 punch(es) restored; the case is open again." in (
        summaries
    )
    item = overview(demo, employee_id="E005", policy_id="P2")["items"][0]
    assert (item["auto_resolved"], item["auto_resolve_undone"]) == (False, True)


def test_refused_undo_shows_in_plain_words(demo):
    with session_for(demo) as s, s.begin():
        s.get(PunchRow, "P0005").location = "Edited by hand"
    undo(demo, SANA_P2, PRIYA)
    trail = detail(demo, SANA_P2)["audit_trail"]
    assert trail[-1]["summary"].startswith("Undo refused, nothing changed: punch P0005 changed")
    assert detail(demo, SANA_P2)["auto_fix"]["last_refusal"]["by"] == "E201"


def test_supervisor_team_list_shows_only_their_team(demo):
    ravi = demo.get("/api/supervisor/auto-resolved", headers=RAVI).json()
    assert [i["exception_id"] for i in ravi["items"]] == [SANA_P2]
    assert ravi["items"][0]["auto_fix"]["can_undo"] is True
    sunita = demo.get("/api/supervisor/auto-resolved", headers=SUNITA).json()
    assert sunita == {"count": 0, "items": []}
    assert_error(demo.get("/api/supervisor/auto-resolved", headers=SANA), 403, "supervisor_only")


# ---------------------------------------------------------------- the metric


def test_metric_after_the_demo_reset(demo):
    m = metric(demo)
    counters = overview(demo)["counters"]
    assert (m["resolved_without_human"], m["needed_handling"]) == (1, 17)
    assert m["percent"] == round(100 / 17, 1) == 5.9
    assert (m["undone"], m["closed_by_data_change"]) == (0, 0)
    assert m["auto_resolve_enabled"] is True and m["allowed_policies"] == ["P2", "P7"]
    assert by_policy(m)["P2"] == {
        "policy_id": "P2",
        "needed_handling": 1,
        "auto_resolved": 1,
        "undone": 0,
        "closed_by_data_change": 0,
    }
    assert sum(p["needed_handling"] for p in m["by_policy"]) == m["needed_handling"]
    assert m["resolved_without_human"] == counters["auto_resolved"]  # the tile agrees
    assert m["needed_handling"] == counters["total"]


def test_metric_after_an_undo_counts_it_as_human_work(demo):
    assert undo(demo, SANA_P2, RAVI).status_code == 200
    m = metric(demo)
    assert (m["resolved_without_human"], m["needed_handling"], m["percent"]) == (0, 17, 0.0)
    assert m["undone"] == 1
    assert by_policy(m)["P2"]["auto_resolved"] == 0 and by_policy(m)["P2"]["undone"] == 1
    assert overview(demo)["counters"]["auto_resolved"] == 0


def test_metric_date_filter_and_permissions(demo):
    m = metric(demo, date_from="2026-04-14", date_to="2026-04-14")
    assert m["resolved_without_human"] == 0 and m["date_from"] == "2026-04-14"
    assert "P2" not in by_policy(m)
    for who in (RAVI, SANA):
        r = demo.get("/api/admin/metrics/auto-resolve", headers=who)
        assert_error(r, 403, "admin_only")


# ---------------------------------------------------------------- live P7 (demo punch)


@pytest.fixture
def demo_reset(demo_client):
    c = demo_client
    assert c.post("/api/seed").status_code == 200
    assert c.post("/api/admin/demo/reset", headers=PRIYA).status_code == 200
    return c


def test_neha_0902_gives_an_auto_resolved_p7_and_the_p1_flow_is_unchanged(demo_reset):
    c = demo_reset
    amit_before = get(c, AMIT_P1)
    r = c.post("/api/admin/demo/punch", json=NEHA_0902, headers=PRIYA)
    assert r.status_code == 201, r.text
    det = r.json()["detection"]
    assert sorted(det["new_exception_ids"]) == [NEHA_P1, NEHA_P7]
    assert det["closed_exception_ids"] == [NEHA_P10]
    p7, p1 = get(c, NEHA_P7), get(c, NEHA_P1)
    assert (p7["status"], p7["auto_resolved"]) == ("resolved", True)
    assert p7["applied_fix"]["changes"] == []  # P7 changes no data
    assert (p1["status"], p1["auto_resolved"]) == ("open", False)

    m = metric(c)
    # 17 + P1 + P7 = 19 stored; Neha's P10, closed by the data change, is not in Y.
    assert (m["resolved_without_human"], m["needed_handling"], m["closed_by_data_change"]) == (
        2,
        18,
        1,
    )
    assert by_policy(m)["P10"] == {
        "policy_id": "P10",
        "needed_handling": 0,
        "auto_resolved": 0,
        "undone": 0,
        "closed_by_data_change": 1,
    }
    assert m["resolved_without_human"] == overview(c)["counters"]["auto_resolved"]

    before = snapshot(c)
    u = undo(c, NEHA_P7, PRIYA)
    assert u.status_code == 200, u.text
    assert u.json()["restored"] == [] and u.json()["detection"]["ran"] is False
    assert snapshot(c) == before  # nothing to restore for P7
    assert get(c, NEHA_P7)["fix_options"][0]["option_id"] == "confirm_within_grace"
    m = metric(c)
    assert (m["resolved_without_human"], m["needed_handling"], m["undone"]) == (1, 18, 1)
    assert m["needed_handling"] + m["closed_by_data_change"] == overview(c)["counters"]["total"]
    after = get(c, AMIT_P1)
    assert {k: after[k] for k in ("status", "assigned_to", "audit_trail")} == {
        k: amit_before[k] for k in ("status", "assigned_to", "audit_trail")
    }


def test_p7_undo_is_refused_if_the_clock_in_was_corrected(demo_reset):
    c = demo_reset
    assert c.post("/api/admin/demo/punch", json=NEHA_0902, headers=PRIYA).status_code == 201
    with session_for(c) as s, s.begin():
        clock_in = s.scalars(select(PunchRow).where(PunchRow.employee_id == "E004")).all()[-1]
        clock_in.voided, clock_in.voided_by_exception = True, NEHA_P1
    assert_error(undo(c, NEHA_P7, RAVI), 409, "undo_conflict")


def test_scheduler_never_touches_an_undone_case_even_with_backlog(db_engine, api_settings):
    from attendflow.api.app import create_app
    from attendflow.db.seed import truncate_all

    with Session(db_engine) as s, s.begin():
        truncate_all(s)
    settings = replace(api_settings, demo_mode=True, scheduler_backlog=True)
    with TestClient(create_app(settings, engine=db_engine), raise_server_exceptions=False) as c:
        assert c.post("/api/seed").status_code == 200
        assert c.post("/api/admin/demo/reset", headers=PRIYA).status_code == 200
        assert c.post("/api/admin/demo/punch", json=NEHA_0902, headers=PRIYA).status_code == 201
        assert undo(c, NEHA_P7, PRIYA).status_code == 200
        assert undo(c, SANA_P2, PRIYA).status_code == 200
        c.app.state.settings = replace(
            settings, scheduler_investigations_per_cycle=50, scheduler_messages_per_cycle=50
        )
        cycle = c.post("/api/admin/scheduler/run-now", headers=PRIYA)
        assert cycle.status_code == 200, cycle.text
        summary = cycle.json()
        touched = {i["exception_id"] for i in summary["investigated"]} | set(
            summary["messages_sent"]
        )
        assert NEHA_P7 not in touched and SANA_P2 not in touched
        assert NEHA_P1 in touched  # the normal flow still runs
        assert summary["skipped_undone"] == 2
        for eid in (NEHA_P7, SANA_P2):
            case = get(c, eid)
            assert case["status"] == "open" and case["investigation_case"] is None
            assert not audits(c, eid, "auto_investigation_started")


# ---------------------------------------------------------------- kill switch


@pytest.fixture
def switched_off(db_engine, api_settings):
    from attendflow.api.app import create_app
    from attendflow.db.seed import truncate_all

    with Session(db_engine) as s, s.begin():
        truncate_all(s)
    settings = replace(api_settings, auto_resolve_enabled=False, demo_mode=True)
    with TestClient(create_app(settings, engine=db_engine), raise_server_exceptions=False) as c:
        assert c.post("/api/seed").status_code == 200
        run = c.post("/api/detection/run")
        assert run.status_code == 200
        assert (run.json()["auto_resolved"], run.json()["auto_resolve_held"]) == (0, 1)
        yield c


def test_kill_switch_off_nothing_auto_resolves(switched_off):
    c = switched_off
    case = get(c, SANA_P2)
    assert (case["status"], case["auto_resolved"], case["applied_fix"]) == ("open", False, None)
    assert punch_row(c, "P0005")["voided"] is False
    [held] = audits(c, SANA_P2, "auto_resolve_held")
    assert held.after["held_because"] == [
        "auto-resolve is switched off (AUTO_RESOLVE_ENABLED=false)"
    ]
    assert detail(c, SANA_P2)["auto_fix"]["state"] == "held"
    r = c.post("/api/admin/demo/punch", json=NEHA_0902, headers=PRIYA)
    assert r.status_code == 201
    assert get(c, NEHA_P7)["status"] == "open"
    m = metric(c)
    assert (m["resolved_without_human"], m["auto_resolve_enabled"]) == (0, False)
    with session_for(c) as s:
        assert not s.scalars(select(ExceptionRow).where(ExceptionRow.auto_resolved)).all()


# ---------------------------------------------------------------- data safety


def test_auto_fix_and_undo_write_only_through_apply_and_are_audited(
    client,
    write_log,  # noqa: F811 - the imported fixture
):
    assert client.post("/api/seed").status_code == 200
    assert client.post("/api/detection/run").status_code == 200  # auto-resolve voids P0005
    assert undo(client, SANA_P2, RAVI).status_code == 200  # undo restores it
    approved = post(client, SANA_P2, "approve", {"option_id": "void_duplicate"}, RAVI)
    assert approved.status_code == 200  # a person voids it again
    fixes = [e for e in write_log if e["writer"] == "apply"]
    assert [(e["table"], e["sql"], e["exception_id"]) for e in fixes] == [
        ("timecards", "UPDATE", SANA_P2)
    ] * 3
    assert {e["writer"] for e in write_log} == {"seed", "apply"}
    assert_writes_audited(client, write_log)
