"""Phase 9: the supervisor's queue, case card, decisions and permissions.

No test needs a real LLM key: investigations use the engine template and the worker's
free text goes through a scripted extraction model (tests.test_worker_time.fake_model).
Numbers are read from the engine's stored re-check, never hard-coded.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from sqlalchemy import select

from attendflow.agent import jobs
from attendflow.db.models import EmployeeRow, ExceptionRow, PunchRow, WorkerMessageRow
from attendflow.llm.client import LLMError
from attendflow.policy.models import load_policy
from tests.api_helpers import (
    AMIT,
    AMIT_P1,
    DEV_P11,
    FARAH_P13,
    KARAN_P9,
    MEENA_P5,
    NEHA_P10,
    PRIYA,
    RAVI,
    SUNITA,
    assert_error,
    confirm_amit_clock_out,
    get,
    post,
    session_for,
    snapshot,
    store_test_investigation,
    worker_says_yes,
)
from tests.test_worker_time import fake_model, output

FARAH = {"X-Actor-Id": "E008"}
KARAN_P7 = "P7-E006-2026-04-13-late"
NEHA_P4 = "P4-E004-2026-04-13"
CLOCK_OUT = "set_clock_out_to_scheduled_end"
TEXT = "stayed late to unload the truck, left around 7:30ish"
SEVERITY = {"high": 0, "medium": 1, "low": 2}


def queue(client, headers) -> list[dict]:
    r = client.get("/api/supervisor/queue", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == len(body["items"])
    return body["items"]


def queue_ids(client, headers) -> list[str]:
    return [item["exception_id"] for item in queue(client, headers)]


def card(client, exception_id: str, headers) -> dict:
    r = client.get(f"/api/supervisor/cases/{exception_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def all_exception_ids(client) -> list[str]:
    return [e["id"] for e in client.get("/api/exceptions").json()["items"]]


def amit_says_about_1930(client, monkeypatch) -> None:
    """Template investigation, worker No with free text, scripted approximate 19:30,
    worker confirms the candidate. The case is then with Ravi."""
    store_test_investigation(client, AMIT_P1)
    assert post(client, AMIT_P1, "ask-worker", {}, RAVI).status_code == 200
    fake_model(monkeypatch, output("19:30", approximate=True))
    reply = post(client, AMIT_P1, "worker-reply", {"confirmed": False, "text": TEXT}, AMIT)
    assert reply.status_code == 200, reply.text
    assert reply.json()["time_review"]["stage"] == "candidate"
    confirmed = post(client, AMIT_P1, "worker-confirm-time", {}, AMIT)
    assert confirmed.status_code == 200, confirmed.text


@pytest.fixture
def policy(demo):
    return load_policy(demo.app.state.settings.data_dir / "policy.json")


# ---------------------------------------------------------------- queue


def test_queue_is_empty_until_a_case_is_ready(demo):
    for headers in (RAVI, SUNITA, PRIYA):
        assert queue(demo, headers) == []  # detection alone puts nothing up for a decision


def test_queue_scopes_by_team_route_and_sort(demo):
    for exception_id in all_exception_ids(demo):
        with session_for(demo) as s:
            final = s.get(ExceptionRow, exception_id).status in {"resolved", "rejected"}
        if not final:
            store_test_investigation(demo, exception_id)
    with session_for(demo) as s:
        team = {e.employee_id: e.supervisor_id for e in s.scalars(select(EmployeeRow))}
        rows = {r.id: r for r in s.scalars(select(ExceptionRow))}

    for headers in (RAVI, SUNITA):
        actor = headers["X-Actor-Id"]
        items = queue(demo, headers)
        assert items, actor
        expected = {
            r.id
            for r in rows.values()
            if r.status == "open"
            and team[r.employee_id] == actor
            and r.investigation_case["who_to_ask"] == "supervisor"
        }
        assert {i["exception_id"] for i in items} == expected
        assert all(team[i["employee_id"]] == actor for i in items)
        keys = [(SEVERITY[i["severity"]], i["date"], i["exception_id"]) for i in items]
        assert keys == sorted(keys)
    # Worker-routed cases stay off the queue until the worker replies.
    assert AMIT_P1 not in queue_ids(demo, RAVI)
    assert KARAN_P9 not in queue_ids(demo, SUNITA)
    assert FARAH_P13 not in queue_ids(demo, SUNITA)
    # Supervisor-routed examples from both teams.
    assert MEENA_P5 in queue_ids(demo, RAVI)
    assert {DEV_P11, KARAN_P7} <= set(queue_ids(demo, SUNITA))
    assert queue(demo, PRIYA) == []  # only escalated cases assigned to her


def test_worker_confirmed_case_moves_into_the_queue(demo):
    store_test_investigation(demo, KARAN_P9, "cancel_leave")
    assert KARAN_P9 not in queue_ids(demo, SUNITA)
    worker_says_yes(demo, KARAN_P9, "cancel_leave", SUNITA, {"X-Actor-Id": "E006"})
    [item] = [i for i in queue(demo, SUNITA) if i["exception_id"] == KARAN_P9]
    assert item["status"] == "awaiting_supervisor" and item["employee_name"] == "Karan Mehta"
    assert KARAN_P9 not in queue_ids(demo, RAVI)


def test_needs_actual_time_never_appears(demo, monkeypatch):
    store_test_investigation(demo, AMIT_P1)
    assert post(demo, AMIT_P1, "ask-worker", {}, RAVI).status_code == 200
    fake_model(monkeypatch, LLMError("chat request failed (HTTP 401)"))
    reply = post(demo, AMIT_P1, "worker-reply", {"confirmed": False, "text": TEXT}, AMIT)
    assert reply.json()["needs_actual_time"] is True
    assert AMIT_P1 not in queue_ids(demo, RAVI)
    # Even if the row were handed back by mistake, the pending time keeps it off.
    with session_for(demo) as s, s.begin():
        row = s.get(ExceptionRow, AMIT_P1)
        row.status, row.assigned_to = "awaiting_supervisor", "E101"
    with session_for(demo) as s:
        message = s.scalars(
            select(WorkerMessageRow).where(WorkerMessageRow.exception_id == AMIT_P1)
        ).one()
        assert message.needs_actual_time is True
    assert AMIT_P1 not in queue_ids(demo, RAVI)


def test_escalated_cases_appear_only_for_the_assignee(demo):
    confirm_amit_clock_out(demo)
    assert queue_ids(demo, RAVI) == [AMIT_P1]
    r = post(demo, AMIT_P1, "reject", {"reason": "Not convinced by the 18:00 time"}, RAVI)
    assert r.status_code == 200, r.text
    assert queue_ids(demo, RAVI) == []
    assert queue_ids(demo, SUNITA) == []
    [item] = queue(demo, PRIYA)
    assert (item["exception_id"], item["status"]) == (AMIT_P1, "escalated")


def test_workers_and_strangers_cannot_read_the_queue(demo):
    assert_error(demo.get("/api/supervisor/queue", headers=AMIT), 403, "supervisor_only")
    assert_error(
        demo.get("/api/supervisor/queue", headers={"X-Actor-Id": "E999"}), 403, "unknown_actor"
    )
    assert_error(demo.get("/api/supervisor/queue"), 422, "validation_error")


# ---------------------------------------------------------------- card


def test_card_shows_worker_time_recheck_and_consequence(demo, monkeypatch, policy):
    amit_says_about_1930(demo, monkeypatch)
    stored = get(demo, AMIT_P1)["worker_recheck"]
    result = stored["result"]
    c = card(demo, AMIT_P1, RAVI)

    assert c["employee"] == {"employee_id": "E001", "name": "Amit Verma", "team": "Inbound"}
    assert c["policy"]["policy_id"] == "P1" and c["policy"]["cited_text"]
    assert c["policy"]["title"] and not c["policy"]["title"].startswith("P1")
    assert c["worker"]["reply_text"] == TEXT and c["worker"]["confirmed"] is False
    assert c["confirmed_time"] == {
        "timestamp": stored["timestamp"],
        "approximate": True,
        "source": "llm",
        "option_id": CLOCK_OUT,
    }
    assert c["recheck"] == result

    [option] = c["options"]
    assert option["params"]["timestamp"] == stored["timestamp"]
    assert "19:30" in option["label"] and "approximate" in option["label"]
    [stamp] = [f for f in option["fields"] if f["name"] == "timestamp"]
    assert stamp["editable"] is False and "Amit Verma must confirm" in stamp["locked_reason"]

    consequence = option["consequence"]
    assert consequence["source"] == "worker_recheck"
    assert consequence["new_violations"] == result["new_violations"]
    assert consequence["creates_violations"] is bool(result["new_violations"])
    note = consequence["note"]
    assert note.startswith("Approving a 19:30 clock-out")
    assert f"makes the day {result['day_worked_hours']:g} h" in note
    assert f"projects {result['week_projected_hours']:g} h for the week" in note
    new = {v["policy_id"] for v in result["new_violations"]}
    assert new  # 19:30 is over the daily limit
    if "P3" in new:
        assert f"over the {policy.number('P3', 'max_hours_per_day'):g} h limit (P3)" in note
    if "P5" in new:
        assert f"over {result['weekly_limit_hours']:g} h (P5)" in note
    assert "Approving creates" in note
    for policy_id in new:
        assert policy_id in note


def test_card_with_no_new_violations_says_so(demo):
    confirm_amit_clock_out(demo, "18:00")
    result = get(demo, AMIT_P1)["worker_recheck"]["result"]
    [option] = card(demo, AMIT_P1, RAVI)["options"]
    assert result["new_violations"] == []
    assert option["consequence"]["creates_violations"] is False
    assert option["consequence"]["note"].endswith("It creates no new exceptions.")


def test_card_notes_for_decision_and_unchecked_options(demo):
    store_test_investigation(demo, KARAN_P7)
    options = {o["option_id"]: o for o in card(demo, KARAN_P7, SUNITA)["options"]}
    accept = options["accept_reason"]
    assert accept["decision_only"] and accept["note_field"] == "reason"
    assert accept["consequence"]["source"] == "decision_only"
    store_test_investigation(demo, NEHA_P10)
    punches = next(
        o
        for o in card(demo, NEHA_P10, RAVI)["options"]
        if o["option_id"] == "add_scheduled_punches"
    )
    assert punches["consequence"]["source"] == "unchecked"
    assert {f["name"]: f["kind"] for f in punches["fields"]} == {
        "clock_in": "datetime",
        "clock_out": "datetime",
    }


def test_card_lists_p13_punches_for_the_edit_form(demo):
    worker_says_yes(demo, FARAH_P13, None, SUNITA, FARAH)
    edit = next(
        o for o in card(demo, FARAH_P13, SUNITA)["options"] if o["action"] == "edit_punches"
    )
    assert edit["worker_confirmed"] is True
    stored = next(o for o in get(demo, FARAH_P13)["fix_options"] if o["action"] == "edit_punches")
    assert [p["punch_id"] for p in edit["punches"]] == stored["params"]["punch_ids"]
    assert all(p["timestamp"] and p["type"] for p in edit["punches"])


def test_card_never_returns_other_workers_data(demo):
    confirm_amit_clock_out(demo)
    with session_for(demo) as s, s.begin():
        row = s.get(ExceptionRow, AMIT_P1)
        meena = s.get(EmployeeRow, "E002")
        row.evidence = [
            *row.evidence,
            {"employee_id": "E002", "punch_id": "P0036", "type": "in", "timestamp": "x"},
        ]
        row.summary = f"{row.summary}; same second as {meena.name} (E002)"
    c = card(demo, AMIT_P1, RAVI)
    text = json.dumps(c)
    assert c["other_workers_evidence_hidden"] == 1
    with session_for(demo) as s:
        others = [e for e in s.scalars(select(EmployeeRow)) if e.role == "worker"]
    for other in others:
        if other.employee_id != "E001":
            assert other.employee_id not in text and other.name not in text
    assert "another worker" in c["summary"]
    assert c["assigned_to"] == "E101"


# ---------------------------------------------------------------- decisions


def test_approve_needs_worker_confirmation_then_works(demo):
    store_test_investigation(demo, AMIT_P1)
    with session_for(demo) as s, s.begin():  # skip the worker by mistake
        s.get(ExceptionRow, AMIT_P1).status = "awaiting_supervisor"
    before = snapshot(demo)
    error = assert_error(
        post(demo, AMIT_P1, "approve", {"option_id": CLOCK_OUT}, RAVI), 409, "worker_not_confirmed"
    )
    assert "confirm" in error["message"]
    assert snapshot(demo) == before


def test_edit_validates_params_and_records_before_and_after(demo):
    worker_says_yes(demo, FARAH_P13, None, SUNITA, FARAH)
    stored = next(o for o in get(demo, FARAH_P13)["fix_options"] if o["action"] == "edit_punches")
    punch = stored["params"]["punch_ids"][-1]
    before = snapshot(demo)
    bad = {
        "option_id": "edit_punches",
        "params": {"changes": [{"punch_id": punch, "timestamp": "2026-04-15T25:00"}]},
        "reason": "Farah confirmed the time",
    }
    error = assert_error(post(demo, FARAH_P13, "edit", bad, SUNITA), 422, "invalid_params")
    assert error["details"]
    assert snapshot(demo) == before

    good = {**bad, "params": {"changes": [{"punch_id": punch, "timestamp": "2026-04-15T13:00"}]}}
    r = post(demo, FARAH_P13, "edit", good, SUNITA)
    assert r.status_code == 200, r.text
    audit = next(a for a in r.json()["audit_trail"] if a["action"] == "edit_and_approve")
    assert audit["before"]["params"] == stored["params"]
    assert audit["after"]["applied_fix"]["params"]["changes"] == [
        {"punch_id": punch, "timestamp": "2026-04-15T13:00:00"}
    ]
    assert audit["after"]["applied_fix"]["params_before"] == stored["params"]
    assert audit["reason"] == "Farah confirmed the time"


def test_reject_needs_a_reason_and_escalates_to_priya(demo):
    confirm_amit_clock_out(demo, "19:30")
    before = snapshot(demo)
    assert_error(
        post(demo, AMIT_P1, "reject", {"reason": "too short"}, RAVI), 422, "validation_error"
    )
    assert_error(post(demo, AMIT_P1, "reject", {"reason": "    "}, RAVI), 422, "validation_error")
    reason = "Gate camera shows Amit left at 18:05"
    r = post(demo, AMIT_P1, "reject", {"reason": reason}, RAVI)
    assert r.status_code == 200, r.text
    exc = r.json()
    assert (exc["status"], exc["assigned_to"]) == ("escalated", "E201")
    assert exc["audit_trail"][-1]["action"] == "reject_and_escalate"
    assert exc["audit_trail"][-1]["reason"] == reason
    assert snapshot(demo) == before
    assert card(demo, AMIT_P1, PRIYA)["status"] == "escalated"
    final = post(demo, AMIT_P1, "reject", {"reason": "Agree with Ravi, no change"}, PRIYA)
    assert final.status_code == 200 and final.json()["status"] == "rejected"
    assert snapshot(demo) == before


def test_decision_only_needs_a_note_and_changes_no_data(demo):
    store_test_investigation(demo, KARAN_P7)
    before = snapshot(demo)
    body = {"option_id": "accept_reason"}
    assert_error(post(demo, KARAN_P7, "approve", body, SUNITA), 422, "invalid_params")
    assert_error(
        post(demo, KARAN_P7, "approve", {**body, "reason": "ok"}, SUNITA), 422, "invalid_params"
    )
    r = post(demo, KARAN_P7, "approve", {**body, "reason": "Bus strike that morning"}, SUNITA)
    assert r.status_code == 200, r.text
    assert r.json()["applied_fix"]["params"]["reason"] == "Bus strike that morning"
    assert r.json()["detection"] == {
        "ran": False,
        "new_exception_ids": [],
        "closed_exception_ids": [],
        "error": None,
    }
    assert snapshot(demo) == before


def test_detection_failure_after_approve_keeps_the_approval(demo, monkeypatch):
    from attendflow.cases import service

    confirm_amit_clock_out(demo, "18:00")

    def broken(*args, **kwargs):
        raise RuntimeError("detection exploded")

    monkeypatch.setattr(service, "run_detection", broken)
    r = post(demo, AMIT_P1, "approve", {"option_id": CLOCK_OUT}, RAVI)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "resolved"
    assert r.json()["detection"]["ran"] is False and r.json()["detection"]["error"]
    assert r.json()["audit_trail"][-1]["action"] == "post_fix_detection_failed"


# ---------------------------------------------------------------- permission matrix


def _decide(client, exception_id: str, endpoint: str, headers):
    bodies = {
        "approve": {"option_id": CLOCK_OUT},
        "edit": {
            "option_id": CLOCK_OUT,
            "params": {"timestamp": "2026-04-14T18:00"},
            "reason": "matrix test",
        },
        "reject": {"reason": "permission matrix test"},
        "ask-worker": {},
    }
    return post(client, exception_id, endpoint, bodies[endpoint], headers)


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        (SUNITA, "not_assigned"),
        (PRIYA, "not_assigned"),
        (AMIT, "supervisor_only"),
        ({"X-Actor-Id": "E002"}, "supervisor_only"),
    ],
)
def test_permission_matrix_on_ravis_case(demo, headers, expected):
    confirm_amit_clock_out(demo)
    before = snapshot(demo)
    r = demo.get("/api/supervisor/queue", headers=headers)
    if expected == "supervisor_only":
        assert_error(r, 403, expected)
    else:
        assert AMIT_P1 not in [i["exception_id"] for i in r.json()["items"]]
    assert_error(demo.get(f"/api/supervisor/cases/{AMIT_P1}", headers=headers), 403, expected)
    for endpoint in ("approve", "edit", "reject", "ask-worker"):
        assert_error(_decide(demo, AMIT_P1, endpoint, headers), 403, expected)
    assert snapshot(demo) == before
    assert get(demo, AMIT_P1)["status"] == "awaiting_supervisor"
    assert card(demo, AMIT_P1, RAVI)["exception_id"] == AMIT_P1  # the assignee can


def test_permission_matrix_on_a_case_escalated_to_priya(demo):
    confirm_amit_clock_out(demo)
    post(demo, AMIT_P1, "reject", {"reason": "Send this one to payroll"}, RAVI)
    for headers, code in (
        (RAVI, "not_assigned"),
        (SUNITA, "not_assigned"),
        (AMIT, "supervisor_only"),
    ):
        assert_error(demo.get(f"/api/supervisor/cases/{AMIT_P1}", headers=headers), 403, code)
        for endpoint in ("approve", "edit", "reject"):
            assert_error(_decide(demo, AMIT_P1, endpoint, headers), 403, code)
    assert card(demo, AMIT_P1, PRIYA)["assigned_to"] == "E201"


# ---------------------------------------------------------------- Amit's story end to end


def test_amits_story_end_to_end(demo, monkeypatch, policy):
    from attendflow.agent.structured import investigate

    # 1. Investigate through the real job path, engine template (no provider call).
    monkeypatch.setattr(
        jobs, "investigate", lambda *a, **kw: investigate(*a, **kw, fallback_only=True)
    )
    queued = post(demo, AMIT_P1, "investigate", {}, RAVI)
    assert queued.status_code == 202
    assert demo.get(queued.headers["Location"], headers=RAVI).json()["status"] == "completed"
    assert AMIT_P1 not in queue_ids(demo, RAVI)  # routed to the worker first

    # 2. Ask Amit; he says No with free text; the scripted model reads "about 19:30".
    assert post(demo, AMIT_P1, "ask-worker", {}, RAVI).status_code == 200
    fake_model(monkeypatch, output("19:30", approximate=True))
    reply = post(demo, AMIT_P1, "worker-reply", {"confirmed": False, "text": TEXT}, AMIT)
    assert reply.status_code == 200
    assert AMIT_P1 not in queue_ids(demo, RAVI)  # waiting for Amit to confirm the time
    assert post(demo, AMIT_P1, "worker-confirm-time", {}, AMIT).status_code == 200

    # 3. The case is in Ravi's queue with the stored re-check.
    assert queue_ids(demo, RAVI)[0] == AMIT_P1  # high severity, oldest date
    stored = get(demo, AMIT_P1)["worker_recheck"]
    expected_new = {(v["policy_id"], v["kind"]) for v in stored["result"]["new_violations"]}
    assert {p for p, _ in expected_new} == {"P3", "P5"}
    [option] = card(demo, AMIT_P1, RAVI)["options"]
    assert option["consequence"]["creates_violations"] is True

    # 4. Ravi approves the confirmed time.
    before_ids = set(all_exception_ids(demo))
    r = post(demo, AMIT_P1, "approve", {"option_id": CLOCK_OUT}, RAVI)
    assert r.status_code == 200, r.text
    exc = r.json()
    assert exc["status"] == "resolved"
    assert exc["applied_fix"]["params"]["timestamp"] == stored["timestamp"]
    # The label names the time actually applied, not the engine's 18:00 default.
    assert exc["applied_fix"]["label"] == f"Set clock-out to {stored['timestamp'][11:16]}"

    # 5. The timecard has the correction punch at the confirmed time.
    with session_for(demo) as s:
        [punch] = s.scalars(select(PunchRow).where(PunchRow.created_by_exception == AMIT_P1)).all()
    assert punch.type == "out" and punch.source == "correction"
    assert punch.timestamp == datetime.fromisoformat(stored["timestamp"])

    # 6. The new P3 and P5 exceptions appear as open cases for Ravi, once.
    new_ids = exc["detection"]["new_exception_ids"]
    assert sorted(new_ids) == sorted(set(all_exception_ids(demo)) - before_ids)
    new_rows = [get(demo, i) for i in new_ids]
    assert {(n["policy_id"], n["kind"]) for n in new_rows} == expected_new
    assert all(
        n["status"] == "open" and n["employee_id"] == "E001" and n["assigned_to"] == "E101"
        for n in new_rows
    )
    p3 = next(n for n in new_rows if n["policy_id"] == "P3")
    assert p3["details"]["worked_hours"] == stored["result"]["day_worked_hours"]
    rerun = demo.post("/api/detection/run").json()
    assert rerun["created"] == 0
    ids = all_exception_ids(demo)
    assert len(ids) == len(set(ids))

    # 7. The audit trail tells the whole story in order.
    actions = [a["action"] for a in exc["audit_trail"]]
    story = [
        "detected",
        "investigation_case_stored",
        "ask_worker",
        "worker_message_sent",
        "worker_reply",
        "worker_time_extracted",
        "worker_time_confirmed",
        "approve",
        "post_fix_detection",
    ]
    positions = [actions.index(step) for step in story if step in actions]
    assert len(positions) == len(story), (story, actions)
    assert positions == sorted(positions)
    approve = next(a for a in exc["audit_trail"] if a["action"] == "approve")
    assert approve["actor_id"] == "E101"
    assert approve["before"]["params"]["timestamp"] == stored["timestamp"]
