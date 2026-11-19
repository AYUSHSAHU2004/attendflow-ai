"""API: approve, edit, reject, ask-worker and worker-reply, with permissions, the status
flow, the data each fix writes, and the one-transaction guarantee."""

from __future__ import annotations

from datetime import date, datetime, time

import pytest
from sqlalchemy import select

from attendflow.cases import service
from attendflow.db.models import (
    ExceptionRow,
    LeaveBalanceRow,
    LeaveRecordRow,
    PunchRow,
    ScheduleEntryRow,
)
from tests.api_helpers import (
    AMIT,
    AMIT_P1,
    DEV_P11,
    FARAH_P13,
    KARAN_P9,
    MEENA,
    MEENA_P3_MON,
    MEENA_P5,
    NEHA_P10,
    PRIYA,
    RAVI,
    SANA_P2,
    SUNITA,
    assert_error,
    audit_count,
    get,
    post,
    session_for,
    snapshot,
)

CLOCK_OUT = {"option_id": "set_clock_out_to_scheduled_end"}


def corrections(client, employee_id: str) -> list[PunchRow]:
    with session_for(client) as s:
        return list(
            s.scalars(
                select(PunchRow).where(
                    PunchRow.employee_id == employee_id, PunchRow.source == "correction"
                )
            )
        )


# ---------------------------------------------------------------- approve


def test_approve_applies_fix_and_writes_audit(demo):
    r = post(demo, AMIT_P1, "approve", {**CLOCK_OUT, "reason": "Shift ended normally"}, RAVI)
    assert r.status_code == 200, r.text
    exc = r.json()
    assert exc["status"] == "resolved"
    assert exc["applied_fix"]["action"] == "set_clock_out"
    assert exc["applied_fix"]["approved_by"] == "E101"
    assert exc["applied_fix"]["edited"] is False

    [punch] = corrections(demo, "E001")
    assert (punch.timestamp, punch.type, punch.device_id) == (
        datetime(2026, 4, 14, 18, 0),
        "out",
        "CORRECTION",
    )
    assert punch.created_by_exception == AMIT_P1
    assert punch.location == "Warehouse 1 - Inbound Gate"

    audit = exc["audit_trail"][-1]
    assert (audit["actor"], audit["actor_id"], audit["action"]) == ("supervisor", "E101", "approve")
    assert audit["before"]["status"] == "open" and audit["after"]["status"] == "resolved"
    assert audit["after"]["applied_fix"]["changes"] == [
        {
            "table": "timecards",
            "op": "insert",
            "punch_id": punch.punch_id,
            "type": "out",
            "timestamp": "2026-04-14T18:00:00",
        }
    ]
    assert audit["reason"] == "Shift ended normally"


def test_approve_twice_is_an_invalid_transition(demo):
    assert post(demo, AMIT_P1, "approve", CLOCK_OUT, RAVI).status_code == 200
    before = snapshot(demo)
    err = assert_error(post(demo, AMIT_P1, "approve", CLOCK_OUT, RAVI), 409, "invalid_transition")
    assert "final" in err["message"]
    assert snapshot(demo) == before
    assert len(corrections(demo, "E001")) == 1


def test_approve_unknown_option(demo):
    err = assert_error(
        post(demo, AMIT_P1, "approve", {"option_id": "pay_double"}, RAVI), 422, "unknown_option"
    )
    assert err["details"]["available"] == ["set_clock_out_to_scheduled_end"]


def test_approve_without_fix_options(demo):
    # P3 gets its fix options in Phase 4; until then it can only be rejected.
    assert_error(
        post(demo, MEENA_P3_MON, "approve", {"option_id": "x"}, RAVI), 409, "no_fix_options"
    )


def test_auto_resolved_exception_cannot_be_approved(demo):
    assert_error(
        post(demo, SANA_P2, "approve", {"option_id": "x"}, RAVI), 409, "invalid_transition"
    )


# ---------------------------------------------------------------- permissions


@pytest.mark.parametrize(
    "headers,code",
    [
        (SUNITA, "not_assigned"),  # supervises the other team
        (PRIYA, "not_assigned"),  # admin acts only after an escalation
        (AMIT, "not_assigned"),  # the worker cannot approve his own fix
        ({"X-Actor-Id": "E999"}, "unknown_actor"),
    ],
)
def test_only_the_assignee_can_decide(demo, headers, code):
    before = snapshot(demo)
    assert_error(post(demo, AMIT_P1, "approve", CLOCK_OUT, headers), 403, code)
    assert_error(post(demo, AMIT_P1, "reject", {"reason": "not ok"}, headers), 403, code)
    assert snapshot(demo) == before
    assert get(demo, AMIT_P1)["status"] == "open"


def test_actor_header_is_required_and_checked(demo):
    assert_error(
        demo.post(f"/api/exceptions/{AMIT_P1}/approve", json=CLOCK_OUT), 422, "validation_error"
    )
    assert_error(
        post(demo, AMIT_P1, "approve", CLOCK_OUT, {"X-Actor-Id": "ravi"}), 422, "validation_error"
    )


def test_unknown_exception(demo):
    assert_error(
        post(demo, "P1-E001-2030-01-01", "approve", CLOCK_OUT, RAVI), 404, "exception_not_found"
    )


def test_request_bodies_are_validated(demo):
    assert_error(post(demo, AMIT_P1, "approve", {}, RAVI), 422, "validation_error")
    assert_error(
        post(demo, AMIT_P1, "approve", {**CLOCK_OUT, "extra": 1}, RAVI), 422, "validation_error"
    )
    assert_error(post(demo, AMIT_P1, "reject", {"reason": ""}, RAVI), 422, "validation_error")
    assert_error(
        post(demo, AMIT_P1, "edit", {**CLOCK_OUT, "params": {}, "reason": "x y"}, RAVI),
        422,
        "validation_error",
    )
    assert_error(post(demo, AMIT_P1, "worker-reply", {"text": "hi"}, AMIT), 422, "validation_error")


# ---------------------------------------------------------------- edit


def test_edit_applies_changed_params(demo):
    body = {**CLOCK_OUT, "params": {"timestamp": "2026-04-14T17:30"}, "reason": "Left at 17:30"}
    r = post(demo, AMIT_P1, "edit", body, RAVI)
    assert r.status_code == 200, r.text
    exc = r.json()
    assert exc["applied_fix"]["edited"] is True
    assert exc["applied_fix"]["params"]["timestamp"] == "2026-04-14T17:30:00"
    assert exc["audit_trail"][-1]["action"] == "edit_and_approve"
    assert [p.timestamp.time() for p in corrections(demo, "E001")] == [time(17, 30)]


@pytest.mark.parametrize(
    "params,code",
    [
        ({"timestamp": "2026-04-14T08:00"}, "punch_outside_shift"),  # before the clock-in
        ({"timestamp": "2026-04-17T09:00"}, "punch_in_future"),  # after "now"
        ({"timestamp": "2026-04-14 18:00"}, "invalid_params"),  # wrong format
        ({"hours": 3}, "invalid_params"),  # not a param of this action
    ],
)
def test_bad_edit_changes_nothing(demo, params, code):
    before, audits = snapshot(demo), audit_count(demo)
    body = {**CLOCK_OUT, "params": params, "reason": "try it"}
    assert_error(post(demo, AMIT_P1, "edit", body, RAVI), 422, code)
    assert snapshot(demo) == before
    assert audit_count(demo) == audits
    assert get(demo, AMIT_P1)["status"] == "open"


def test_edit_of_a_decision_only_option(demo):
    before = snapshot(demo)
    bad = {"option_id": "approve_overtime", "params": {"hours": "all"}, "reason": "x y z"}
    assert_error(post(demo, MEENA_P5, "edit", bad, RAVI), 422, "invalid_params")
    body = {"option_id": "approve_overtime", "params": {"hours": 6}, "reason": "6 h agreed"}
    r = post(demo, MEENA_P5, "edit", body, RAVI)
    assert r.status_code == 200, r.text
    assert r.json()["applied_fix"]["params"] == {"hours": 6}
    assert r.json()["applied_fix"]["changes"] == []
    assert snapshot(demo) == before  # a decision only: no data changes


# ---------------------------------------------------------------- reject flow


def test_supervisor_reject_escalates_to_payroll_admin(demo):
    before = snapshot(demo)
    r = post(demo, AMIT_P1, "reject", {"reason": "Amit was on a site visit"}, RAVI)
    assert r.status_code == 200, r.text
    exc = r.json()
    assert exc["status"] == "escalated"
    assert exc["assigned_to"] == "E201"
    assert exc["waiting_since"] == "2026-04-16T08:00:00"
    audit = exc["audit_trail"][-1]
    assert (audit["action"], audit["actor"], audit["actor_id"]) == (
        "reject_and_escalate",
        "supervisor",
        "E101",
    )
    assert audit["reason"] == "Amit was on a site visit"
    assert audit["after"]["assigned_to"] == "E201"
    assert snapshot(demo) == before  # a rejected fix leaves the timecard unchanged


def test_admin_reject_of_escalated_case_is_final(demo):
    post(demo, AMIT_P1, "reject", {"reason": "not convinced"}, RAVI)
    # The supervisor no longer owns it.
    assert_error(post(demo, AMIT_P1, "reject", {"reason": "again"}, RAVI), 403, "not_assigned")
    before = snapshot(demo)
    r = post(demo, AMIT_P1, "reject", {"reason": "Agree, no change"}, PRIYA)
    assert r.status_code == 200, r.text
    exc = r.json()
    assert exc["status"] == "rejected" and exc["waiting_since"] is None
    assert exc["audit_trail"][-1]["actor"] == "admin"
    assert exc["audit_trail"][-1]["action"] == "reject"
    assert snapshot(demo) == before
    assert_error(post(demo, AMIT_P1, "approve", CLOCK_OUT, PRIYA), 409, "invalid_transition")


def test_admin_can_approve_an_escalated_case(demo):
    post(demo, AMIT_P1, "reject", {"reason": "not sure"}, RAVI)
    assert_error(post(demo, AMIT_P1, "approve", CLOCK_OUT, RAVI), 403, "not_assigned")
    r = post(demo, AMIT_P1, "approve", CLOCK_OUT, PRIYA)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "resolved"
    assert r.json()["applied_fix"]["approved_by"] == "E201"
    assert len(corrections(demo, "E001")) == 1


def test_exceptions_without_options_can_still_be_rejected(demo):
    r = post(demo, MEENA_P3_MON, "reject", {"reason": "Overtime was agreed"}, RAVI)
    assert r.status_code == 200 and r.json()["status"] == "escalated"


# ---------------------------------------------------------------- worker loop


def test_ask_worker_then_reply(demo):
    r = post(demo, AMIT_P1, "ask-worker", {"note": "Please confirm your clock-out"}, RAVI)
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["assigned_to"]) == ("awaiting_worker", "E001")
    assert r.json()["waiting_since"] == "2026-04-16T08:00:00"

    # While waiting for Amit, nobody can approve.
    assert_error(post(demo, AMIT_P1, "approve", CLOCK_OUT, RAVI), 409, "invalid_transition")
    # Only Amit may answer.
    assert_error(
        post(demo, AMIT_P1, "worker-reply", {"confirmed": True}, MEENA), 403, "not_the_worker"
    )
    assert_error(
        post(demo, AMIT_P1, "worker-reply", {"confirmed": True}, RAVI), 403, "not_the_worker"
    )

    r = post(
        demo, AMIT_P1, "worker-reply", {"confirmed": False, "text": "left around 7:30ish"}, AMIT
    )
    assert r.status_code == 200, r.text
    exc = r.json()
    assert (exc["status"], exc["assigned_to"]) == ("awaiting_supervisor", "E101")
    audit = exc["audit_trail"][-1]
    assert (audit["actor"], audit["action"]) == ("worker", "worker_reply")
    assert audit["after"]["text"] == "left around 7:30ish" and audit["after"]["confirmed"] is False

    # Back with Ravi, who can now decide.
    body = {**CLOCK_OUT, "params": {"timestamp": "2026-04-14T19:30"}, "reason": "Per Amit's reply"}
    assert post(demo, AMIT_P1, "edit", body, RAVI).json()["status"] == "resolved"


def test_worker_reply_only_when_asked(demo):
    assert_error(
        post(demo, AMIT_P1, "worker-reply", {"confirmed": True}, AMIT), 409, "invalid_transition"
    )


def test_ask_worker_needs_the_assignee(demo):
    assert_error(post(demo, AMIT_P1, "ask-worker", {}, SUNITA), 403, "not_assigned")
    post(demo, AMIT_P1, "reject", {"reason": "escalate it"}, RAVI)
    assert_error(post(demo, AMIT_P1, "ask-worker", {}, PRIYA), 409, "invalid_transition")


# ---------------------------------------------------------------- one transaction


def test_failure_after_the_fix_rolls_everything_back(demo, monkeypatch):
    before, audits = snapshot(demo), audit_count(demo)

    def broken_audit(*args, **kwargs):
        raise RuntimeError("audit store down")

    monkeypatch.setattr(service, "_audit", broken_audit)
    assert_error(post(demo, AMIT_P1, "approve", CLOCK_OUT, RAVI), 500, "internal_error")
    assert snapshot(demo) == before  # the clock-out punch was rolled back
    assert audit_count(demo) == audits
    assert get(demo, AMIT_P1)["status"] == "open"


# ---------------------------------------------------------------- what each fix writes


def _approve(client, exception_id, option_id, headers=RAVI, **extra):
    r = post(client, exception_id, "approve", {"option_id": option_id, **extra}, headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_reduce_upcoming_shifts(demo):
    _approve(demo, MEENA_P5, "reduce_upcoming_shifts")
    with session_for(demo) as s:
        rows = {
            r.date: (r.shift_start, r.shift_end)
            for r in s.scalars(
                select(ScheduleEntryRow).where(ScheduleEntryRow.employee_id == "E002")
            )
        }
    assert rows[date(2026, 4, 16)] == (time(9, 0), time(13, 0))  # 6 h -> 4 h
    assert date(2026, 4, 17) not in rows  # 6 h -> 0 h: shift removed
    run = demo.post("/api/detection/run").json()
    assert "P5" not in run["by_policy"]  # 36 + 4 = 40 h: within the limit now


def test_cancel_leave_gives_the_day_back(demo):
    _approve(demo, KARAN_P9, "cancel_leave", SUNITA)
    with session_for(demo) as s:
        assert (
            s.scalars(select(LeaveRecordRow).where(LeaveRecordRow.employee_id == "E006")).all()
            == []
        )
        assert s.get(LeaveBalanceRow, ("E006", "casual")).used == 2  # was 3
    assert "P9" not in demo.post("/api/detection/run").json()["by_policy"]


def test_record_leave_for_an_absence(demo):
    _approve(demo, NEHA_P10, "record_casual_leave")
    with session_for(demo) as s:
        leave = s.scalars(select(LeaveRecordRow).where(LeaveRecordRow.employee_id == "E004")).one()
        assert (leave.date, leave.leave_type, leave.status) == (
            date(2026, 4, 15),
            "casual",
            "approved",
        )
        assert s.get(LeaveBalanceRow, ("E004", "casual")).used == 3
    assert "P10" not in demo.post("/api/detection/run").json()["by_policy"]


def test_split_paid_unpaid_leave(demo):
    _approve(demo, DEV_P11, "split_paid_unpaid", SUNITA)
    with session_for(demo) as s:
        rows = {
            r.date: (r.status, r.unpaid)
            for r in s.scalars(select(LeaveRecordRow).where(LeaveRecordRow.employee_id == "E007"))
        }
    assert rows[date(2026, 4, 13)] == ("pending", False)
    assert rows[date(2026, 4, 15)] == ("rejected", True)
    assert rows[date(2026, 4, 16)] == ("rejected", True)
    assert "P11" not in demo.post("/api/detection/run").json()["by_policy"]


def test_move_leave_type(demo):
    _approve(demo, DEV_P11, "move_to_casual", SUNITA)
    with session_for(demo) as s:
        types = sorted(
            (r.date, r.leave_type)
            for r in s.scalars(select(LeaveRecordRow).where(LeaveRecordRow.employee_id == "E007"))
        )
    assert types == [
        (date(2026, 4, 13), "sick"),
        (date(2026, 4, 15), "casual"),
        (date(2026, 4, 16), "casual"),
    ]


def test_edit_punches_needs_the_new_times(demo):
    assert_error(
        post(demo, FARAH_P13, "approve", {"option_id": "edit_punches"}, SUNITA),
        422,
        "invalid_params",
    )
    exc = get(demo, FARAH_P13)
    out = next(e for e in exc["evidence"] if e.get("type") == "out")
    body = {
        "option_id": "edit_punches",
        "params": {"changes": [{"punch_id": out["punch_id"], "timestamp": "2026-04-15T13:00"}]},
        "reason": "Farah confirmed she left at 13:00",
    }
    r = post(demo, FARAH_P13, "edit", body, SUNITA)
    assert r.status_code == 200, r.text
    with session_for(demo) as s:
        assert s.get(PunchRow, out["punch_id"]).voided is True
        [new] = s.scalars(select(PunchRow).where(PunchRow.created_by_exception == FARAH_P13)).all()
        assert (new.type, new.timestamp) == ("out", datetime(2026, 4, 15, 13, 0))


def test_stale_fix_is_refused(demo):
    # Cancel Karan's leave through P9, then a hand-made stale exception that still points at
    # it must fail cleanly instead of writing anything.
    _approve(demo, KARAN_P9, "cancel_leave", SUNITA)
    with session_for(demo) as s, s.begin():
        row = s.get(ExceptionRow, KARAN_P9)
        stale = ExceptionRow(
            **{c.name: getattr(row, c.name) for c in ExceptionRow.__table__.columns}
            | {"id": "P9-E006-stale", "status": "open", "applied_fix": None}
        )
        s.add(stale)
    before = snapshot(demo)
    assert_error(
        post(demo, "P9-E006-stale", "approve", {"option_id": "cancel_leave"}, SUNITA),
        409,
        "stale_fix",
    )
    assert snapshot(demo) == before
