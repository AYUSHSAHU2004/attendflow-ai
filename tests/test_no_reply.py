"""Phase 13: the no-reply ladder (reminder -> supervisor -> payroll), deciding without the
worker, escalate, the demo clock, and the data-safety guarantees.

The ladder only reads `clock.now()`. Tests move the app's DemoClock directly (the demo
endpoint does the same, tested at the end) and run one scheduler cycle with the timer
off, exactly like "Run scheduler now".
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from attendflow.cases import no_reply
from attendflow.clock import DemoClock, data_as_of
from attendflow.config import Settings, get_settings
from attendflow.db.models import AuditLogRow, ExceptionRow, WorkerMessageRow
from tests.api_helpers import (
    AMIT,
    AMIT_P1,
    MEENA_P3_MON,
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
from tests.test_e2e_prototype import write_log  # noqa: F401 - a fixture

AS_OF = datetime(2026, 4, 16, 8, 0)
LIMITS = no_reply.Limits(
    reminder=timedelta(hours=8), supervisor=timedelta(hours=24), admin=timedelta(hours=24)
)
REMINDER_TEXT = (
    "Reminder: we still need your answer about Tue 14 Apr. If we don't hear from you by "
    "Fri 17 Apr 08:00, your supervisor will review it using the records."
)
REASON = "Worker unreachable; the gate log shows 18:00."


# ---------------------------------------------------------------- helpers


def move(client, hours: float, minutes: float = 0) -> None:
    """Set the demo clock to as-of + this offset (the endpoint is tested separately)."""
    client.app.state.clock.set_offset(timedelta(hours=hours, minutes=minutes))


def run(client) -> dict:
    """One cycle through the admin endpoint, with the timer off."""
    r = client.post("/api/admin/scheduler/run-now", headers=PRIYA)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "completed", body
    return body["no_reply"]


def case(client, exception_id: str) -> ExceptionRow:
    with session_for(client) as s:
        return s.get(ExceptionRow, exception_id)


def actions(client, exception_id: str, prefix: str = "no_reply") -> list[AuditLogRow]:
    with session_for(client) as s:
        return s.scalars(
            select(AuditLogRow)
            .where(AuditLogRow.exception_id == exception_id, AuditLogRow.action.startswith(prefix))
            .order_by(AuditLogRow.id)
        ).all()


def ask_amit(client) -> None:
    """A supervisor asks by hand about a SEEDED case (before any watermark)."""
    store_test_investigation(client, AMIT_P1)
    r = post(client, AMIT_P1, "ask-worker", {}, RAVI)
    assert r.status_code == 200, r.text


def to_stage(client, stage: int) -> None:
    """Amit asked at 08:00 Thu, then silent until the ladder reaches this stage."""
    ask_amit(client)
    for hours in (8, 24, 48)[:stage]:
        move(client, hours)
        run(client)
    assert case(client, AMIT_P1).no_reply_stage == stage


def clock_out_option(client) -> dict:
    return next(o for o in get(client, AMIT_P1)["fix_options"] if o["action"] == "set_clock_out")


def inbox(client, headers=AMIT) -> dict:
    r = client.get("/api/worker/messages", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def queue(client, headers=RAVI) -> list[dict]:
    r = client.get("/api/supervisor/queue", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["items"]


# ---------------------------------------------------------------- pure rules


def row_at(status: str, stage: int = 0, **stamps) -> ExceptionRow:
    return ExceptionRow(
        status=status,
        no_reply_stage=stage,
        no_reply_wait_since=stamps.get("since", AS_OF),
        no_reply_supervisor_at=stamps.get("supervisor_at"),
        auto_resolve_undone_at=stamps.get("undone"),
        waiting_since=AS_OF,
    )


@pytest.mark.parametrize(
    ("row", "offset", "expected"),
    [
        (row_at("awaiting_worker"), timedelta(hours=8) - timedelta(seconds=1), None),
        (row_at("awaiting_worker"), timedelta(hours=8), "remind"),
        (row_at("awaiting_worker", 1), timedelta(hours=24) - timedelta(seconds=1), None),
        (row_at("awaiting_worker", 1), timedelta(hours=24), "supervisor"),
        (
            row_at("awaiting_supervisor", 2, supervisor_at=AS_OF + timedelta(hours=24)),
            timedelta(hours=48) - timedelta(seconds=1),
            None,
        ),
        (
            row_at("awaiting_supervisor", 2, supervisor_at=AS_OF + timedelta(hours=24)),
            timedelta(hours=48),
            "admin",
        ),
        # One step at a time: a long silence still gets the reminder first.
        (row_at("awaiting_worker"), timedelta(days=5), "remind"),
        # Each step once: a higher stage never repeats a lower one.
        (row_at("awaiting_worker", 2), timedelta(days=5), None),
        (row_at("awaiting_supervisor", 3), timedelta(days=5), None),
    ],
)
def test_due_step_boundaries(row, offset, expected):
    due = no_reply.due_step(row, AS_OF + offset, LIMITS)
    assert (due[0] if due else None) == expected


@pytest.mark.parametrize(
    "status", ["open", "awaiting_supervisor", "escalated", "resolved", "rejected"]
)
def test_nothing_is_due_unless_waiting_for_the_worker(status):
    # awaiting_supervisor only steps on once the ladder itself brought the supervisor in.
    assert no_reply.due_step(row_at(status), AS_OF + timedelta(days=9), LIMITS) is None


def test_undone_cases_never_step():
    row = row_at("awaiting_worker", undone=AS_OF)
    assert no_reply.due_step(row, AS_OF + timedelta(days=9), LIMITS) is None


def test_ladder_settings_are_validated():
    base = get_settings(env_file=None)
    assert (base.no_reply_reminder_hours, base.no_reply_supervisor_hours) == (8, 24)
    assert base.no_reply_admin_hours == 24 and base.no_reply_escalation_enabled
    with pytest.raises(ValueError, match="REMINDER_HOURS must be less"):
        replace(base, no_reply_reminder_hours=24)
    with pytest.raises(ValueError, match="positive"):
        replace(base, no_reply_admin_hours=0)
    assert isinstance(base, Settings)


def test_demo_clock_moves_now_but_never_the_data_cut_off():
    clock = DemoClock(AS_OF)
    clock.set_offset(timedelta(hours=30))
    assert clock.now() == AS_OF + timedelta(hours=30)
    assert data_as_of(clock) == AS_OF
    with pytest.raises(ValueError):
        clock.set_offset(timedelta(hours=-1))
    with pytest.raises(ValueError):
        clock.set_offset(timedelta(days=15))


# ---------------------------------------------------------------- the silent path


def test_each_stage_fires_once_at_its_limit_never_before(demo, write_log):  # noqa: F811
    before = snapshot(demo)
    ask_amit(demo)  # a seeded case asked by hand: the backlog watermark does not apply

    move(demo, 7, 59)
    assert run(demo)["reminded"] == []
    move(demo, 8)
    assert run(demo)["reminded"] == [AMIT_P1]
    assert run(demo)["reminded"] == []  # exactly once
    row = case(demo, AMIT_P1)
    assert (row.status, row.no_reply_stage) == ("awaiting_worker", 1)
    assert row.no_reply_reminded_at == AS_OF + timedelta(hours=8)
    [message] = inbox(demo)["items"]
    assert message["reminder"]["text"] == REMINDER_TEXT
    assert message["reminder"]["sent_at"] == "2026-04-16T16:00:00"

    move(demo, 23, 59)
    assert run(demo)["to_supervisor"] == []
    move(demo, 24)
    assert run(demo)["to_supervisor"] == [AMIT_P1]
    assert run(demo)["to_supervisor"] == []
    row = case(demo, AMIT_P1)
    assert (row.status, row.assigned_to, row.no_reply_stage) == ("awaiting_supervisor", "E101", 2)
    [item] = [i for i in queue(demo) if i["exception_id"] == AMIT_P1]
    assert item["no_reply"]["note"] == "Amit Verma has not replied for 24 h."
    assert item["no_reply"]["stage_key"] == "supervisor"
    assert item["no_reply"]["can_decide_without_worker"] is True
    [message] = inbox(demo)["items"]  # still answerable
    assert message["status_note"] == no_reply.WITH_SUPERVISOR_NOTE

    move(demo, 47, 59)
    assert run(demo)["to_admin"] == []
    move(demo, 48)
    assert run(demo)["to_admin"] == [AMIT_P1]
    assert run(demo)["to_admin"] == []
    row = case(demo, AMIT_P1)
    assert (row.status, row.assigned_to, row.no_reply_stage) == ("escalated", "E201", 3)
    assert AMIT_P1 not in [i["exception_id"] for i in queue(demo)]
    assert AMIT_P1 in [i["exception_id"] for i in queue(demo, PRIYA)]

    move(demo, 24 * 14)  # nothing more, ever
    assert run(demo) == {"enabled": True, "reminded": [], "to_supervisor": [], "to_admin": []}

    # Each step audited once, as the system, with the exact times.
    steps = actions(demo, AMIT_P1)
    assert [(a.action, a.actor) for a in steps] == [
        ("no_reply_reminder", "system"),
        ("no_reply_to_supervisor", "system"),
        ("no_reply_to_admin", "system"),
    ]
    assert [a.after["fired_at"] for a in steps] == [
        "2026-04-16T16:00:00",
        "2026-04-17T08:00:00",
        "2026-04-18T08:00:00",
    ]
    assert [a.after["due_at"] for a in steps] == [a.after["fired_at"] for a in steps]
    assert steps[1].after["hours_without_reply"] == "24 h"
    assert "Nothing was changed" in steps[2].reason

    # Silence never changed data and never applied a fix.
    assert snapshot(demo) == before
    assert [e for e in write_log if e["writer"] != "seed"] == []
    assert case(demo, AMIT_P1).applied_fix is None

    # The worker can no longer answer; the inbox says payroll has it.
    assert inbox(demo)["items"] == []
    [notice] = inbox(demo)["notices"]
    assert (notice["kind"], notice["text"]) == ("with_payroll", no_reply.WITH_PAYROLL_NOTE)
    late = post(demo, AMIT_P1, "worker-reply", {"confirmed": True}, AMIT)
    assert_error(late, 409, "handled_by_payroll")


def test_a_clock_jump_still_takes_one_step_at_a_time(demo):
    ask_amit(demo)
    move(demo, 72)
    assert run(demo)["reminded"] == [AMIT_P1]
    assert run(demo)["to_supervisor"] == [AMIT_P1]
    # K counts from when the supervisor was brought in (now), not from the question.
    assert run(demo)["to_admin"] == []
    move(demo, 96)
    assert run(demo)["to_admin"] == [AMIT_P1]


def test_seeded_cases_do_not_fire_by_themselves(demo):
    move(demo, 24 * 14)
    assert run(demo) == {"enabled": True, "reminded": [], "to_supervisor": [], "to_admin": []}
    with session_for(demo) as s:
        assert {r.no_reply_stage for r in s.scalars(select(ExceptionRow))} == {0}
    assert actions(demo, AMIT_P1) == []


def test_resolved_rejected_escalated_and_undone_cases_never_step(demo):
    # Escalated by a reject; resolved (Sana's auto-resolved P2); and a case waiting for the
    # worker that is marked undone (Phase 12 cases are never handled automatically).
    rejected = post(demo, MEENA_P3_MON, "reject", {"reason": "Not authorised overtime"}, RAVI)
    assert rejected.status_code == 200, rejected.text
    assert get(demo, MEENA_P3_MON)["status"] == "escalated"
    assert get(demo, SANA_P2)["status"] == "resolved"
    ask_amit(demo)
    with session_for(demo) as s, s.begin():
        s.get(ExceptionRow, AMIT_P1).auto_resolve_undone_at = AS_OF
    move(demo, 24 * 14)
    for _ in range(3):
        assert run(demo) == {
            "enabled": True,
            "reminded": [],
            "to_supervisor": [],
            "to_admin": [],
        }
    for exception_id in (SANA_P2, MEENA_P3_MON, AMIT_P1):
        assert actions(demo, exception_id) == []


def test_the_kill_switch_stops_every_step(demo):
    ask_amit(demo)
    sched = demo.app.state.scheduler
    sched.deps.settings = replace(sched.deps.settings, no_reply_escalation_enabled=False)
    move(demo, 24 * 14)
    summary = run(demo)
    assert summary["enabled"] is False and summary["reminded"] == []
    assert case(demo, AMIT_P1).no_reply_stage == 0


def test_cycle_summary_and_audit_count_the_steps(demo):
    ask_amit(demo)
    move(demo, 8)
    run(demo)
    with session_for(demo) as s:
        cycle = s.scalars(
            select(AuditLogRow)
            .where(AuditLogRow.action == "scheduler_cycle")
            .order_by(AuditLogRow.id.desc())
        ).first()
    assert cycle.after["reminded"] == 1 and cycle.after["to_supervisor"] == 0
    assert cycle.after["no_reply"]["reminded"] == [AMIT_P1]
    assert cycle.created_at == AS_OF + timedelta(hours=8)


# ---------------------------------------------------------------- replies stop the ladder


def test_a_reply_after_the_reminder_stops_the_ladder(demo):
    to_stage(demo, 1)
    r = post(demo, AMIT_P1, "worker-reply", {"confirmed": True}, AMIT)
    assert r.status_code == 200, r.text
    row = case(demo, AMIT_P1)
    assert (row.status, row.no_reply_stage, row.no_reply_late_reply_at) == (
        "awaiting_supervisor",
        0,
        None,
    )
    [stopped] = actions(demo, AMIT_P1, "no_reply_ladder_stopped")
    assert stopped.after == {"stage_before": 1, "late": False, "reply": "yes"}
    move(demo, 24 * 14)
    run(demo)
    assert case(demo, AMIT_P1).status == "awaiting_supervisor"  # no K timer: a normal case


def test_a_late_yes_resumes_the_normal_flow(demo):
    to_stage(demo, 2)
    r = post(demo, AMIT_P1, "worker-reply", {"confirmed": True}, AMIT)
    assert r.status_code == 200, r.text
    row = case(demo, AMIT_P1)
    assert (row.status, row.assigned_to, row.no_reply_stage) == ("awaiting_supervisor", "E101", 0)
    assert row.no_reply_late_reply_at == AS_OF + timedelta(hours=24)
    assert row.worker_recheck["source"] == "yes"  # the Phase 8 re-check ran
    [item] = [i for i in queue(demo) if i["exception_id"] == AMIT_P1]
    assert item["no_reply"]["label"] == "Replied late"
    assert item["no_reply"]["can_decide_without_worker"] is False
    [stopped] = actions(demo, AMIT_P1, "no_reply_ladder_stopped")
    assert stopped.after["late"] is True

    move(demo, 24 * 14)
    assert run(demo)["to_admin"] == []  # the ladder stopped
    option = clock_out_option(demo)
    approved = post(demo, AMIT_P1, "approve", {"option_id": option["option_id"]}, RAVI)
    assert approved.status_code == 200, approved.text
    assert "without_worker" not in approved.json()["applied_fix"]


def test_a_late_no_goes_back_to_the_worker_and_starts_a_new_wait(demo):
    to_stage(demo, 2)
    r = post(demo, AMIT_P1, "worker-reply", {"confirmed": False, "text": "I left at 17:30"}, AMIT)
    assert r.status_code == 200, r.text
    row = case(demo, AMIT_P1)
    assert (row.status, row.assigned_to, row.no_reply_stage) == ("awaiting_worker", "E001", 0)
    assert row.no_reply_wait_since == AS_OF + timedelta(hours=24)
    assert AMIT_P1 not in [i["exception_id"] for i in queue(demo)]
    [message] = inbox(demo)["items"]
    assert message["needs_actual_time"] is True

    # The new wait has its own ladder (8 h from the No).
    move(demo, 31, 59)
    assert run(demo)["reminded"] == []
    move(demo, 32)
    assert run(demo)["reminded"] == [AMIT_P1]

    # The worker gives the time (Phase 8 manual form): normal flow, ladder stopped.
    timed = post(demo, AMIT_P1, "worker-manual-time", {"time": "17:30"}, AMIT)
    assert timed.status_code == 200, timed.text
    row = case(demo, AMIT_P1)
    assert (row.status, row.no_reply_stage) == ("awaiting_supervisor", 0)
    assert row.worker_recheck["timestamp"].startswith("2026-04-14T17:30")


def test_a_late_time_after_an_earlier_no_is_accepted(demo):
    ask_amit(demo)
    r = post(demo, AMIT_P1, "worker-reply", {"confirmed": False, "text": "Left late"}, AMIT)
    assert r.status_code == 200
    for hours in (8, 24):  # silent about the time: reminder, then the supervisor
        move(demo, hours)
        run(demo)
    row = case(demo, AMIT_P1)
    assert (row.status, row.no_reply_stage) == ("awaiting_supervisor", 2)
    # The No-without-time case is no longer hidden from the supervisor.
    [item] = [i for i in queue(demo) if i["exception_id"] == AMIT_P1]
    assert item["no_reply"]["stage"] == 2
    [message] = inbox(demo)["items"]
    assert message["needs_actual_time"] is True
    timed = post(demo, AMIT_P1, "worker-manual-time", {"time": "18:10"}, AMIT)
    assert timed.status_code == 200, timed.text
    assert (case(demo, AMIT_P1).status, case(demo, AMIT_P1).no_reply_stage) == (
        "awaiting_supervisor",
        0,
    )


def test_asking_again_starts_a_new_wait(demo):
    to_stage(demo, 2)
    again = post(demo, AMIT_P1, "ask-worker", {"note": "Please answer"}, RAVI)
    assert again.status_code == 200, again.text
    row = case(demo, AMIT_P1)
    assert (row.status, row.no_reply_stage) == ("awaiting_worker", 0)
    assert row.no_reply_wait_since == AS_OF + timedelta(hours=24)
    [message] = inbox(demo)["items"]
    assert message.get("reminder") is None  # the new question has no reminder yet
    move(demo, 32)
    assert run(demo)["reminded"] == [AMIT_P1]


# ---------------------------------------------------------------- deciding without the worker


def test_decide_without_the_worker_needs_a_reason_and_the_tick(demo, write_log):  # noqa: F811
    to_stage(demo, 2)
    option = clock_out_option(demo)["option_id"]
    body = {"option_id": option, "reason": REASON, "without_worker": True}

    plain = post(demo, AMIT_P1, "approve", {"option_id": option}, RAVI)
    assert_error(plain, 409, "worker_not_confirmed")  # silence is never a Yes
    short = post(demo, AMIT_P1, "approve", {**body, "reason": "no reply"}, RAVI)
    assert_error(short, 422, "reason_required")
    untick = post(demo, AMIT_P1, "approve", body, RAVI)
    assert_error(untick, 422, "time_confirmation_required")

    ok = post(demo, AMIT_P1, "approve", {**body, "confirm_time_without_worker": True}, RAVI)
    assert ok.status_code == 200, ok.text
    fix = ok.json()["applied_fix"]
    assert fix["without_worker"]["time_source"] == "prefilled"
    assert fix["without_worker"]["reason"] == REASON
    assert fix["without_worker"]["no_reply_stage"] == 2
    assert fix["without_worker"]["hours_without_reply"] == "24 h"
    [decided] = actions(demo, AMIT_P1, "decided_without_worker")
    assert (decided.actor, decided.actor_id, decided.after["time_source"]) == (
        "supervisor",
        "E101",
        "prefilled",
    )
    # The punch was written by fixes/apply.py only, for this case.
    written = [e for e in write_log if e["writer"] != "seed"]
    assert written and {e["writer"] for e in written} == {"apply"}
    assert {e["exception_id"] for e in written} == {AMIT_P1}

    [notice] = inbox(demo)["notices"]
    assert (notice["kind"], notice["title"]) == (
        "decided_without_reply",
        "Decided without your reply",
    )
    assert notice["reason"] == REASON and notice["text"].startswith("Set clock-out to 18:00")


def test_not_allowed_before_the_ladder_brings_the_case_in(demo):
    ask_amit(demo)
    move(demo, 8)
    run(demo)
    option = clock_out_option(demo)["option_id"]
    body = {
        "option_id": option,
        "reason": REASON,
        "without_worker": True,
        "confirm_time_without_worker": True,
    }
    # Stage 1: still the worker's turn, so nobody else can decide.
    assert_error(post(demo, AMIT_P1, "approve", body, RAVI), 409, "invalid_transition")
    # A normal case with the supervisor (the worker answered): no "without the worker".
    assert post(demo, AMIT_P1, "worker-reply", {"confirmed": True}, AMIT).status_code == 200
    assert_error(post(demo, AMIT_P1, "approve", body, RAVI), 409, "no_reply_not_escalated")


def test_an_edited_time_is_recorded_and_still_validated(demo):
    to_stage(demo, 2)
    option = clock_out_option(demo)["option_id"]
    body = {
        "option_id": option,
        "reason": REASON,
        "without_worker": True,
        "confirm_time_without_worker": True,
    }
    outside = post(
        demo, AMIT_P1, "edit", {**body, "params": {"timestamp": "2026-04-14T03:00"}}, RAVI
    )
    assert_error(outside, 422, "punch_outside_shift")  # Phase 8 checks still apply
    ok = post(demo, AMIT_P1, "edit", {**body, "params": {"timestamp": "2026-04-14T17:30"}}, RAVI)
    assert ok.status_code == 200, ok.text
    assert ok.json()["applied_fix"]["without_worker"]["time_source"] == "edited"
    assert ok.json()["applied_fix"]["label"] == "Set clock-out to 17:30"


def test_priya_decides_without_the_worker_at_stage_three(demo):
    to_stage(demo, 3)
    option = clock_out_option(demo)["option_id"]
    body = {
        "option_id": option,
        "reason": REASON,
        "without_worker": True,
        "confirm_time_without_worker": True,
    }
    assert_error(post(demo, AMIT_P1, "approve", body, RAVI), 403, "not_assigned")
    card = demo.get(f"/api/supervisor/cases/{AMIT_P1}", headers=PRIYA)
    assert card.status_code == 200 and card.json()["no_reply"]["stage"] == 3
    ok = post(demo, AMIT_P1, "approve", body, PRIYA)
    assert ok.status_code == 200, ok.text
    assert ok.json()["applied_fix"]["without_worker"]["no_reply_stage"] == 3


# ---------------------------------------------------------------- permissions and escalate


def test_permissions_at_stage_two(demo):
    to_stage(demo, 2)
    option = clock_out_option(demo)["option_id"]
    body = {
        "option_id": option,
        "reason": REASON,
        "without_worker": True,
        "confirm_time_without_worker": True,
    }
    assert_error(post(demo, AMIT_P1, "approve", body, AMIT), 403, "supervisor_only")
    assert_error(post(demo, AMIT_P1, "approve", body, SUNITA), 403, "not_assigned")
    assert_error(post(demo, AMIT_P1, "approve", body, PRIYA), 403, "not_assigned")
    card = demo.get(f"/api/supervisor/cases/{AMIT_P1}", headers=SUNITA)
    assert_error(card, 403, "not_assigned")
    card = demo.get(f"/api/supervisor/cases/{AMIT_P1}", headers=RAVI)
    assert card.status_code == 200
    assert card.json()["no_reply"]["note"] == "Amit Verma has not replied for 24 h."
    admin = demo.get(f"/api/admin/exceptions/{AMIT_P1}", headers=PRIYA).json()
    assert admin["no_reply"]["stage_key"] == "supervisor"
    assert [m["reminder_text"] for m in admin["worker_messages"]] == [REMINDER_TEXT]


def test_the_supervisor_can_escalate_to_payroll(demo):
    to_stage(demo, 2)
    reason = {"reason": "Cannot verify; payroll please decide"}
    assert_error(post(demo, AMIT_P1, "escalate", reason, AMIT), 403, "supervisor_only")
    assert_error(post(demo, AMIT_P1, "escalate", reason, SUNITA), 403, "not_assigned")
    assert_error(
        post(demo, AMIT_P1, "escalate", {"reason": "short"}, RAVI), 422, "validation_error"
    )
    ok = post(demo, AMIT_P1, "escalate", reason, RAVI)
    assert ok.status_code == 200, ok.text
    assert (ok.json()["status"], ok.json()["assigned_to"]) == ("escalated", "E201")
    [row] = actions(demo, AMIT_P1, "escalate_to_admin")
    assert (row.actor_id, row.reason) == ("E101", reason["reason"])
    assert_error(post(demo, AMIT_P1, "escalate", reason, PRIYA), 409, "invalid_transition")
    move(demo, 24 * 14)
    assert run(demo)["to_admin"] == []  # already with payroll: the ladder does nothing


def test_admin_list_has_the_stage_the_stuck_counter_and_filter(demo):
    to_stage(demo, 2)
    body = demo.get("/api/admin/exceptions", headers=PRIYA).json()
    assert body["counters"]["stuck"] == 1
    assert body["filter_options"]["no_reply"] == [
        "any", "reminded", "supervisor", "payroll_admin", "waiting",
    ]
    for value, expected in (("any", [AMIT_P1]), ("supervisor", [AMIT_P1]), ("reminded", [])):
        r = demo.get(f"/api/admin/exceptions?no_reply={value}", headers=PRIYA).json()
        assert [i["exception_id"] for i in r["items"]] == expected
    [item] = [i for i in body["items"] if i["exception_id"] == AMIT_P1]
    assert item["no_reply"]["hours_without_reply"] == "24 h"
    detail = demo.get(f"/api/admin/exceptions/{AMIT_P1}", headers=PRIYA).json()
    summaries = [a["summary"] for a in detail["audit_trail"]]
    assert "No reply yet: the system sent one reminder (template)." in summaries
    assert "No reply for 24 h: brought in Ravi Kumar. Nothing was changed." in summaries


# ---------------------------------------------------------------- demo clock


def test_demo_clock_endpoints_do_not_exist_without_demo_mode(demo):
    assert demo.get("/api/admin/demo/clock", headers=PRIYA).status_code == 404
    assert demo.post("/api/admin/demo/clock", json={"hours": 8}, headers=PRIYA).status_code == 404
    status = demo.get("/api/admin/scheduler", headers=PRIYA).json()
    assert status["clock"]["movable"] is False
    assert status["clock"]["now"] == status["clock"]["data_as_of"] == "2026-04-16T08:00:00"


def test_demo_clock_moves_forward_persists_and_reset_restores_it(
    demo_client, db_engine, api_settings
):
    c = demo_client
    assert c.post("/api/seed").status_code == 200
    assert c.post("/api/admin/demo/reset", headers=PRIYA).status_code == 200
    found_before = c.post("/api/detection/run").json()
    assert_error(
        c.post("/api/admin/demo/clock", json={"hours": 8}, headers=RAVI), 403, "admin_only"
    )
    r = c.post("/api/admin/demo/clock", json={"hours": 8}, headers=PRIYA)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["now"] == "2026-04-16T16:00:00" and body["data_as_of"] == "2026-04-16T08:00:00"
    assert body["hint"] == "Run the scheduler (or wait for the next cycle) to apply."
    assert c.get("/api/admin/demo/clock", headers=PRIYA).json()["offset_hours"] == 8
    assert_error(
        c.post("/api/admin/demo/clock", json={"hours": 24 * 14}, headers=PRIYA), 422, "clock_limit"
    )
    assert_error(
        c.post("/api/admin/demo/clock", json={"hours": -1}, headers=PRIYA), 422, "validation_error"
    )
    # Moving the clock never changes detection (the data cut-off is fixed).
    found_after = c.post("/api/detection/run").json()
    assert found_after["found"] == found_before["found"] and found_after["created"] == 0
    with session_for(c) as s:
        moved = s.scalars(select(AuditLogRow).where(AuditLogRow.action == "demo_clock_moved")).all()
    assert [(a.actor, a.actor_id, a.after["hours"]) for a in moved] == [("admin", "E201", 8.0)]

    # A restart restores the stored offset.
    from fastapi.testclient import TestClient

    from attendflow.api.app import create_app

    again = create_app(replace(api_settings, demo_mode=True), engine=db_engine)
    with TestClient(again) as c2:
        assert c2.get("/api/admin/demo/clock", headers=PRIYA).json()["offset_hours"] == 8

    reset = c.post("/api/admin/demo/reset", headers=PRIYA)
    assert reset.status_code == 200
    assert reset.json()["clock"]["now"] == "2026-04-16T08:00:00"
    assert c.app.state.clock.now() == AS_OF
    with TestClient(create_app(replace(api_settings, demo_mode=True), engine=db_engine)) as c3:
        assert c3.get("/api/admin/demo/clock", headers=PRIYA).json()["offset_hours"] == 0


def test_a_question_starts_the_wait(demo):
    ask_amit(demo)
    with session_for(demo) as s:
        message = s.scalars(select(WorkerMessageRow)).one()
    assert case(demo, AMIT_P1).no_reply_wait_since == message.sent_at
    assert message.sent_at.date() == date(2026, 4, 16)
