"""API (real Postgres): the Phase 4 fix options for P3, P4, P6, P7, their appliers, the
worker-confirmation guard, and options added to cases already in progress."""

from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import select

from attendflow.db.models import AuditLogRow, ExceptionRow, PunchRow, ScheduleEntryRow
from tests.api_helpers import (
    MEENA_P3_MON,
    RAVI,
    SUNITA,
    assert_error,
    audit_count,
    get,
    post,
    session_for,
    snapshot,
    store_test_investigation,
)

MEENA = {"X-Actor-Id": "E002"}
NEHA = {"X-Actor-Id": "E004"}
NEHA_P4 = "P4-E004-2026-04-13"
KARAN_P7 = "P7-E006-2026-04-13-late"
AMIT_P6_FRI = "P6-E001-2026-04-17"


def punches_of(client, employee_id: str, day: date) -> list[PunchRow]:
    start = datetime.combine(day, time())
    with session_for(client) as s:
        return list(
            s.scalars(
                select(PunchRow)
                .where(
                    PunchRow.employee_id == employee_id,
                    PunchRow.timestamp >= start,
                    PunchRow.timestamp
                    < datetime.combine(date.fromordinal(day.toordinal() + 1), time()),
                )
                .order_by(PunchRow.timestamp)
            )
        )


def confirm_with_worker(client, exception_id: str, worker: dict, confirmed: bool = True) -> None:
    case = get(client, exception_id)
    option = next(
        option for option in case["fix_options"] if option["requires_worker_confirmation"]
    )
    store_test_investigation(client, exception_id, option["option_id"])
    assert (
        post(client, exception_id, "ask-worker", {"note": "Please confirm"}, RAVI).status_code
        == 200
    )
    r = post(client, exception_id, "worker-reply", {"confirmed": confirmed, "text": "ok"}, worker)
    assert r.status_code == 200, r.text


def detect(client) -> dict:
    r = client.post("/api/detection/run")
    assert r.status_code == 200, r.text
    return r.json()


def open_ids(client) -> set[str]:
    return {e["id"] for e in client.get("/api/exceptions?status=open").json()["items"]}


# ---------------------------------------------------------------- listed by the API


def test_p3_p4_p7_options_are_listed_with_their_fields(demo):
    items = {e["id"]: e for e in demo.get("/api/exceptions").json()["items"]}
    for exc_id, expected in [
        (MEENA_P3_MON, ["approve_overtime", "correct_clock_out"]),
        (NEHA_P4, ["record_break", "record_missed_break"]),
        (KARAN_P7, ["accept_reason", "record_as_late"]),
    ]:
        opts = items[exc_id]["fix_options"]
        assert [o["option_id"] for o in opts] == expected
        for o in opts:
            assert o["description"] and o["policy_id"] == items[exc_id]["policy_id"]
            assert isinstance(o["decision_only"], bool)
    p3 = {o["option_id"]: o for o in items[MEENA_P3_MON]["fix_options"]}
    assert p3["correct_clock_out"]["requires_worker_confirmation"] is True
    assert p3["approve_overtime"]["decision_only"] is True


def test_detection_again_never_duplicates(demo):
    before = demo.get("/api/exceptions").json()["count"]
    assert detect(demo)["created"] == 0
    assert demo.get("/api/exceptions").json()["count"] == before


# ---------------------------------------------------------------- P3


def test_p3_approve_overtime_changes_no_data(demo):
    before = snapshot(demo)
    r = post(demo, MEENA_P3_MON, "approve", {"option_id": "approve_overtime"}, RAVI)
    assert r.status_code == 200, r.text
    assert r.json()["applied_fix"]["changes"] == []
    assert snapshot(demo) == before


def test_p3_correction_needs_the_worker_to_confirm_first(demo):
    body = {"option_id": "correct_clock_out"}
    before, audits = snapshot(demo), audit_count(demo)
    err = assert_error(post(demo, MEENA_P3_MON, "approve", body, RAVI), 409, "worker_not_confirmed")
    assert err["details"] == {"worker_replied": False}
    # The worker says No: still refused.
    confirm_with_worker(demo, MEENA_P3_MON, MEENA, confirmed=False)
    assert_error(post(demo, MEENA_P3_MON, "approve", body, RAVI), 409, "invalid_transition")
    assert snapshot(demo) == before
    assert audit_count(demo) == audits + 4  # handoff, message, reply, and extraction outcome


def test_p3_correction_voids_the_old_clock_out_and_adds_the_confirmed_one(demo):
    confirm_with_worker(demo, MEENA_P3_MON, MEENA)
    r = post(
        demo,
        MEENA_P3_MON,
        "edit",
        {
            "option_id": "correct_clock_out",
            "params": {"timestamp": "2026-04-13T17:00:00"},
            "reason": "Meena confirmed she left at 17:00",
        },
        RAVI,
    )
    assert r.status_code == 200, r.text
    changes = r.json()["applied_fix"]["changes"]
    assert [(c["op"], c["type"]) for c in changes] == [("void", "out"), ("insert", "out")]
    rows = {p.punch_id: p for p in punches_of(demo, "E002", date(2026, 4, 13))}
    assert rows["P0031"].voided and rows["P0031"].voided_by_exception == MEENA_P3_MON
    [new] = [p for p in rows.values() if p.source == "correction"]
    assert new.timestamp == datetime(2026, 4, 13, 17, 0) and new.type == "out"
    # 06:59:47-17:00 minus 30 min = 9.5 h: still over 9 h, so a new P3 would not appear for
    # this date (the case is resolved), but Meena's P5 numbers refresh.
    detect(demo)
    p5 = get(demo, "P5-E002-2026-04-13")
    assert p5["details"]["worked_hours"] == 33.5


def test_p3_correction_in_the_future_changes_nothing(demo):
    confirm_with_worker(demo, MEENA_P3_MON, MEENA)
    before, audits = snapshot(demo), audit_count(demo)
    body = {
        "option_id": "correct_clock_out",
        "params": {"timestamp": "2026-04-17T09:00:00"},
        "reason": "typo",
    }
    assert_error(post(demo, MEENA_P3_MON, "edit", body, RAVI), 422, "punch_in_future")
    assert snapshot(demo) == before and audit_count(demo) == audits
    assert get(demo, MEENA_P3_MON)["status"] == "awaiting_supervisor"


# ---------------------------------------------------------------- P4


def test_p4_record_break_adds_two_correction_punches(demo):
    confirm_with_worker(demo, NEHA_P4, NEHA)
    r = post(demo, NEHA_P4, "approve", {"option_id": "record_break"}, RAVI)
    assert r.status_code == 200, r.text
    added = [p for p in punches_of(demo, "E004", date(2026, 4, 13)) if p.source == "correction"]
    assert [(p.type, p.timestamp.time()) for p in added] == [
        ("break_start", time(12, 0)),
        ("break_end", time(12, 30)),
    ]
    detect(demo)
    assert NEHA_P4 not in open_ids(demo)
    assert not any(e.startswith("P4-E004") for e in detect(demo)["exception_ids"])


def test_p4_break_outside_the_shift_changes_nothing(demo):
    confirm_with_worker(demo, NEHA_P4, NEHA)
    before, audits = snapshot(demo), audit_count(demo)
    body = {
        "option_id": "record_break",
        "params": {"break_start": "2026-04-13T08:00:00", "break_end": "2026-04-13T08:30:00"},
        "reason": "Neha said 8:00",
    }
    assert_error(post(demo, NEHA_P4, "edit", body, RAVI), 422, "break_outside_shift")
    assert snapshot(demo) == before and audit_count(demo) == audits


def test_p4_missed_break_needs_a_follow_up_note(demo):
    body = {"option_id": "record_missed_break"}
    err = assert_error(post(demo, NEHA_P4, "approve", body, RAVI), 422, "invalid_params")
    assert "follow-up" in err["message"]
    before = snapshot(demo)
    r = post(demo, NEHA_P4, "approve", {**body, "reason": "Talked to Neha; breaks from now"}, RAVI)
    assert r.status_code == 200, r.text
    fix = r.json()["applied_fix"]
    assert fix["params"]["follow_up"] == "Talked to Neha; breaks from now"
    assert fix["changes"] == [] and snapshot(demo) == before


# ---------------------------------------------------------------- P7


def test_p7_accept_reason_stores_the_reason(demo):
    err = assert_error(
        post(demo, KARAN_P7, "approve", {"option_id": "accept_reason"}, SUNITA),
        422,
        "invalid_params",
    )
    assert "reason" in err["message"]
    before = snapshot(demo)
    r = post(
        demo, KARAN_P7, "approve", {"option_id": "accept_reason", "reason": "Bus strike"}, SUNITA
    )
    assert r.status_code == 200, r.text
    assert r.json()["applied_fix"]["params"]["reason"] == "Bus strike"
    assert snapshot(demo) == before


def test_p7_record_as_late_needs_no_reason(demo):
    r = post(demo, KARAN_P7, "approve", {"option_id": "record_as_late"}, SUNITA)
    assert r.status_code == 200, r.text
    assert r.json()["applied_fix"]["action"] == "record_lateness"


# ---------------------------------------------------------------- P6 (synthetic in the DB)


def make_amit_p6(client) -> None:
    """Amit works Thu 09:00-18:00; move his Fri shift to 03:00-12:00 -> 9 h rest (risk)."""
    with session_for(client) as s, s.begin():
        row = s.scalars(
            select(ScheduleEntryRow).where(
                ScheduleEntryRow.employee_id == "E001", ScheduleEntryRow.date == date(2026, 4, 17)
            )
        ).one()
        row.shift_start, row.shift_end = time(3, 0), time(12, 0)
    detect(client)


def amit_fri_shift(client) -> tuple[time, time]:
    with session_for(client) as s:
        row = s.scalars(
            select(ScheduleEntryRow).where(
                ScheduleEntryRow.employee_id == "E001", ScheduleEntryRow.date == date(2026, 4, 17)
            )
        ).one()
        return row.shift_start, row.shift_end


def test_p6_move_next_shift_later(demo):
    make_amit_p6(demo)
    exc = get(demo, AMIT_P6_FRI)
    assert exc["kind"] == "risk"
    move = {o["option_id"]: o for o in exc["fix_options"]}["move_next_shift_later"]
    assert move["params"]["new_start"] == "05:00" and move["params"]["new_end"] == "14:00"
    r = post(demo, AMIT_P6_FRI, "approve", {"option_id": "move_next_shift_later"}, RAVI)
    assert r.status_code == 200, r.text
    assert r.json()["applied_fix"]["changes"][0]["shift"] == {
        "before": "03:00-12:00",
        "after": "05:00-14:00",
    }
    assert amit_fri_shift(demo) == (time(5, 0), time(14, 0))
    assert not any(e.startswith("P6-E001") for e in detect(demo)["exception_ids"])


def test_p6_stale_move_changes_nothing(demo):
    make_amit_p6(demo)
    with session_for(demo) as s, s.begin():  # someone changes the shift after detection
        row = s.scalars(
            select(ScheduleEntryRow).where(
                ScheduleEntryRow.employee_id == "E001", ScheduleEntryRow.date == date(2026, 4, 17)
            )
        ).one()
        row.shift_start = time(2, 0)
    before, audits = snapshot(demo), audit_count(demo)
    body = {"option_id": "move_next_shift_later"}
    assert_error(post(demo, AMIT_P6_FRI, "approve", body, RAVI), 409, "stale_fix")
    assert snapshot(demo) == before and audit_count(demo) == audits
    assert get(demo, AMIT_P6_FRI)["status"] == "open"


def test_p6_record_short_rest(demo):
    make_amit_p6(demo)
    r = post(
        demo,
        AMIT_P6_FRI,
        "approve",
        {"option_id": "record_short_rest", "reason": "Stock count"},
        RAVI,
    )
    assert r.status_code == 200, r.text
    assert amit_fri_shift(demo) == (time(3, 0), time(12, 0))


# ---------------------------------------------------------------- options for cases in progress


def test_detection_adds_options_to_a_case_in_progress_that_had_none(demo):
    # A P3 case escalated before Phase 4, stored without options.
    assert (
        post(demo, MEENA_P3_MON, "reject", {"reason": "check with payroll"}, RAVI).status_code
        == 200
    )
    with session_for(demo) as s, s.begin():
        s.get(ExceptionRow, MEENA_P3_MON).fix_options = []
    summary = detect(demo)
    assert summary["options_added"] == 1
    exc = get(demo, MEENA_P3_MON)
    assert exc["status"] == "escalated" and exc["assigned_to"] == "E201"
    assert [o["option_id"] for o in exc["fix_options"]] == ["approve_overtime", "correct_clock_out"]
    assert exc["audit_trail"][-1]["action"] == "options_added"
    assert detect(demo)["options_added"] == 0  # only once


def test_old_stored_options_are_shown_with_derived_fields(demo):
    with session_for(demo) as s, s.begin():
        row = s.get(ExceptionRow, MEENA_P3_MON)
        row.status = "awaiting_supervisor"
        row.fix_options = [
            {
                "option_id": "approve_overtime",
                "action": "approve_overtime",
                "label": "x",
                "params": {},
            }
        ]
    [opt] = get(demo, MEENA_P3_MON)["fix_options"]
    assert opt["decision_only"] is True and opt["description"] and opt["policy_id"] == "P3"
    assert opt["requires_worker_confirmation"] is False


def test_audit_rows_for_options_are_system_rows(demo):
    with session_for(demo) as s:
        rows = s.scalars(select(AuditLogRow).where(AuditLogRow.action == "options_added")).all()
    assert rows == []  # a fresh demo never needs it
