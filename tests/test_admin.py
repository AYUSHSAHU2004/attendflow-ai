"""Phase 10: the payroll admin's overview, counters and read-only case detail.

No test needs a real LLM key. Counts are compared with the database, never hard-coded.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy import text

from attendflow.agent import jobs
from attendflow.agent.loop import SYSTEM_PROMPT as LOOP_PROMPT
from attendflow.agent.structured import SYSTEM_PROMPT as DRAFT_PROMPT
from attendflow.agent.structured import investigate
from attendflow.cases.time_extraction import PROMPT as EXTRACTION_PROMPT
from tests.api_helpers import (
    AMIT_P1,
    MEENA_P5,
    PRIYA,
    RAVI,
    SANA_P2,
    SUNITA,
    assert_error,
    post,
    session_for,
    snapshot,
    store_test_investigation,
)
from tests.test_investigation import Model, final, simulate
from tests.test_supervisor import amit_says_about_1930

AMIT = {"X-Actor-Id": "E001"}
STATUSES = ("open", "awaiting_worker", "awaiting_supervisor", "escalated", "resolved", "rejected")
SEVERITY = {"high": 0, "medium": 1, "low": 2}
FAKE_KEY = "gsk_test_secret_never_shown_123"


def overview(client, headers=PRIYA, **params) -> dict:
    r = client.get("/api/admin/exceptions", headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def detail(client, exception_id: str, headers=PRIYA) -> dict:
    r = client.get(f"/api/admin/exceptions/{exception_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def db_counts(client) -> dict[str, int]:
    with session_for(client) as s:
        counts = {
            status: s.execute(
                text("SELECT count(*) FROM exceptions WHERE status = :s"), {"s": status}
            ).scalar_one()
            for status in STATUSES
        }
        counts["total"] = s.execute(text("SELECT count(*) FROM exceptions")).scalar_one()
        counts["auto_resolved"] = s.execute(
            text("SELECT count(*) FROM exceptions WHERE auto_resolved")
        ).scalar_one()
    return counts


# ---------------------------------------------------------------- permissions


@pytest.mark.parametrize("headers", [RAVI, SUNITA, AMIT])
def test_only_the_payroll_admin_gets_the_overview(demo, headers):
    assert_error(demo.get("/api/admin/exceptions", headers=headers), 403, "admin_only")
    assert_error(demo.get(f"/api/admin/exceptions/{AMIT_P1}", headers=headers), 403, "admin_only")


def test_unknown_or_missing_actor_is_refused(demo):
    unknown = {"X-Actor-Id": "E999"}
    assert_error(demo.get("/api/admin/exceptions", headers=unknown), 403, "unknown_actor")
    assert_error(demo.get("/api/admin/exceptions"), 422, "validation_error")


# ---------------------------------------------------------------- overview


def test_overview_lists_every_exception_with_counters_from_the_database(demo):
    body = overview(demo)
    assert body["counters"] == db_counts(demo)
    assert body["matched"] == body["counters"]["total"] == len(body["items"])
    assert body["counters"]["auto_resolved"] >= 1
    stored = {e["id"] for e in demo.get("/api/exceptions").json()["items"]}
    assert {i["exception_id"] for i in body["items"]} == stored
    # Default sort: severity (high first), then date, then ID.
    keys = [(SEVERITY[i["severity"]], i["date"], i["exception_id"]) for i in body["items"]]
    assert keys == sorted(keys)
    # Names, teams and kinds come from the database.
    amit = next(i for i in body["items"] if i["exception_id"] == AMIT_P1)
    assert (amit["employee_name"], amit["team"], amit["kind"]) == (
        "Amit Verma",
        "Inbound",
        "breach",
    )
    assert (amit["assigned_to"], amit["assigned_to_name"]) == ("E101", "Ravi Kumar")
    assert amit["investigated"] is False and amit["who_to_ask"] is None
    options = body["filter_options"]
    assert options["teams"] == ["Inbound", "Outbound"]
    assert "Arjun" not in {e["name"].split()[0] for e in options["employees"]}  # clean control
    assert options["policy_ids"] == sorted(
        {i["policy_id"] for i in body["items"]}, key=lambda p: int(p[1:])
    )


def test_auto_resolved_cases_are_marked(demo):
    items = overview(demo, status="resolved")["items"]
    sana = next(i for i in items if i["exception_id"] == SANA_P2)
    assert sana["auto_resolved"] is True and sana["status"] == "resolved"
    with session_for(demo) as s:
        expected = set(
            s.execute(text("SELECT id FROM exceptions WHERE auto_resolved")).scalars().all()
        )
    assert {i["exception_id"] for i in overview(demo)["items"] if i["auto_resolved"]} == expected


@pytest.mark.parametrize(
    ("params", "check"),
    [
        ({"status": "resolved"}, lambda i: i["status"] == "resolved"),
        ({"policy_id": "P3"}, lambda i: i["policy_id"] == "P3"),
        ({"team": "outbound"}, lambda i: i["team"] == "Outbound"),
        ({"employee_id": "E002"}, lambda i: i["employee_id"] == "E002"),
        ({"severity": "high"}, lambda i: i["severity"] == "high"),
        (
            {"q": "meena"},
            lambda i: i["employee_name"] == "Meena Iyer" or i["employee_id"] == "E002",
        ),
        ({"q": "e00"}, lambda i: i["employee_id"].startswith("E00")),
    ],
)
def test_filters_match_and_counters_stay_whole(demo, params, check):
    everything = overview(demo)
    body = overview(demo, **params)
    expected = [i for i in everything["items"] if check(i)]
    assert expected, params  # every filter here matches something in the demo
    assert [i["exception_id"] for i in body["items"]] == [i["exception_id"] for i in expected]
    assert body["matched"] == len(expected)
    assert body["counters"] == everything["counters"]


def test_search_treats_wildcards_as_text(demo):
    assert overview(demo, q="%")["items"] == []
    assert overview(demo, q="_")["items"] == []


def test_sorting_and_paging(demo):
    everything = overview(demo)["items"]
    by_date = overview(demo, sort="date")["items"]
    assert [i["date"] for i in by_date] == sorted(i["date"] for i in everything)
    page = overview(demo, limit=5, offset=5)
    assert page["matched"] == len(everything) and page["limit"] == 5
    assert [i["exception_id"] for i in page["items"]] == [
        i["exception_id"] for i in everything[5:10]
    ]
    assert_error(
        demo.get("/api/admin/exceptions", headers=PRIYA, params={"limit": 0}),
        422,
        "validation_error",
    )
    assert_error(
        demo.get("/api/admin/exceptions", headers=PRIYA, params={"sort": "salary"}),
        422,
        "validation_error",
    )


def test_escalated_case_needs_priyas_decision(demo):
    store_test_investigation(demo, MEENA_P5)
    reason = "Overtime was not agreed with the team"
    assert post(demo, MEENA_P5, "reject", {"reason": reason}, RAVI).status_code == 200
    body = overview(demo, status="escalated")
    [item] = body["items"]
    assert item["exception_id"] == MEENA_P5 and item["needs_your_decision"] is True
    assert body["counters"]["escalated"] == 1 == db_counts(demo)["escalated"]
    case = detail(demo, MEENA_P5)
    assert case["needs_your_decision"] is True and case["assigned_to"] == "E201"
    escalation = case["audit_trail"][-1]
    assert escalation["action"] == "reject_and_escalate" and escalation["reason"] == reason
    assert escalation["actor_name"] == "Ravi Kumar"
    assert escalation["after_summary"] == "escalated, with Priya Sharma"


# ---------------------------------------------------------------- detail


def test_detail_is_read_only_and_complete_for_a_fresh_case(demo):
    before = snapshot(demo)
    case = detail(demo, AMIT_P1)
    assert snapshot(demo) == before
    assert case["can_investigate"] is True and case["needs_your_decision"] is False
    assert case["employee"] == {"employee_id": "E001", "name": "Amit Verma", "team": "Inbound"}
    assert case["policy"]["policy_id"] == "P1" and case["policy"]["cited_text"]
    assert case["evidence"] and case["options"]
    assert case["options"][0]["consequence"]["source"] == "unchecked"
    assert case["investigation"] is None and case["worker_messages"] == []
    assert [a["action"] for a in case["audit_trail"]] == ["detected"]
    assert_error(
        demo.get("/api/admin/exceptions/P1-E999-2026-04-14", headers=PRIYA),
        404,
        "exception_not_found",
    )


def test_detail_shows_recheck_reply_and_ordered_audit(demo, monkeypatch):
    amit_says_about_1930(demo, monkeypatch)
    case = detail(demo, AMIT_P1)
    stored = demo.get(f"/api/exceptions/{AMIT_P1}").json()
    assert case["recheck"] == stored["worker_recheck"]
    assert case["recheck"]["source"] == "llm" and case["recheck"]["approximate"] is True
    [message] = case["worker_messages"]
    assert message["confirmed"] is False and "7:30ish" in message["reply_text"]
    ids = [a["id"] for a in case["audit_trail"]]
    assert ids == sorted(ids) and len(ids) == len(stored["audit_trail"])
    assert [a["action"] for a in case["audit_trail"]] == [
        a["action"] for a in stored["audit_trail"]
    ]
    [option] = case["options"]
    assert option["consequence"]["source"] == "worker_recheck"
    assert option["consequence"]["creates_violations"] is True
    summaries = {a["action"]: a["summary"] for a in case["audit_trail"]}
    assert "7:30ish" in summaries["worker_reply"]
    assert summaries["worker_time_confirmed"].startswith(
        f"Worker confirmed {case['recheck']['timestamp'][11:16]}"
    )


def test_detail_never_returns_keys_prompts_or_tool_output(demo, monkeypatch):
    state = demo.app.state
    monkeypatch.setattr(state, "settings", replace(state.settings, llm_api_key=FAKE_KEY))
    model = Model(simulate, final)
    monkeypatch.setattr(
        jobs, "investigate", lambda *a, **kw: investigate(*a, **kw, chat_model=model)
    )
    started = demo.post(f"/api/exceptions/{AMIT_P1}/investigate", headers=PRIYA)
    assert started.status_code == 202
    case = detail(demo, AMIT_P1)
    assert case["investigation"]["fallback"] is False
    assert [c["tool_name"] for c in case["tool_calls"]] == [
        "get_schedule",
        "get_punches",
        "get_leave",
        "get_policy",
        "run_checks",
    ]
    assert all(
        set(c)
        == {"run_id", "step_no", "call_no", "tool_name", "input", "ok", "error_code", "duration_ms"}
        for c in case["tool_calls"]
    )
    raw = demo.get(f"/api/admin/exceptions/{AMIT_P1}", headers=PRIYA).text
    assert FAKE_KEY not in raw
    for prompt in (LOOP_PROMPT, DRAFT_PROMPT, EXTRACTION_PROMPT):
        assert prompt.splitlines()[0] not in raw
    assert '"role"' not in raw and "api_key" not in raw.lower()


# ---------------------------------------------------------------- investigate from the admin view


def test_investigate_from_the_admin_view_reuses_the_job(demo, monkeypatch):
    monkeypatch.setattr(jobs.InvestigationJobs, "run", lambda self, job_id: None)  # stay running
    route = f"/api/exceptions/{AMIT_P1}/investigate"
    first = demo.post(route, headers=PRIYA)
    second = demo.post(route, headers=PRIYA)
    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert first.headers["Location"] == second.headers["Location"]
    job = detail(demo, AMIT_P1)["latest_job"]
    assert job == {"id": first.json()["id"], "status": "running", "reason": None}
    assert demo.get(first.headers["Location"], headers=PRIYA).json()["status"] == "running"


def test_investigate_from_the_admin_view_stores_a_case(demo, monkeypatch):
    monkeypatch.setattr(
        jobs, "investigate", lambda *a, **kw: investigate(*a, **kw, fallback_only=True)
    )
    started = demo.post(f"/api/exceptions/{AMIT_P1}/investigate", headers=PRIYA)
    assert started.status_code == 202
    assert demo.get(started.headers["Location"], headers=PRIYA).json()["status"] == "completed"
    [item] = overview(demo, employee_id="E001", policy_id="P1")["items"]
    assert item["investigated"] and item["who_to_ask"] == "worker"
    assert item["investigation_fallback"] is True
    case = detail(demo, AMIT_P1)
    assert case["status"] == "open"  # investigating never changes the status
    assert case["audit_trail"][-1]["summary"].startswith(
        "Investigation stored from the engine template"
    )
