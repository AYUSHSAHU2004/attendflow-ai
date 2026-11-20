"""Phase 14: the Activity Center over the shared end-to-end story (tests/activity_story.py).

All tests here only read, so the story runs once for the module (`story_client`). The
non-story API tests (empty state, failed detection after an undo) are in
tests/test_activity_api.py, because another fixture would wipe the story's database.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from attendflow.activity import autonomy
from attendflow.agent.structured import SYSTEM_PROMPT
from attendflow.cases.time_extraction import PROMPT as EXTRACTION_PROMPT
from attendflow.config import REPO_ROOT
from attendflow.db.models import AuditLogRow, EmployeeRow, ExceptionRow
from tests.activity_story import LEAK_OUTPUT, LEAK_PROVIDER, LEAKS, UNDO_REASON
from tests.api_helpers import (
    AMIT,
    AMIT_P1,
    MEENA_P3_MON,
    MEENA_P5,
    PRIYA,
    RAVI,
    SANA_P2,
    SUNITA,
    assert_error,
    post,
)
from tests.test_ingest import NEHA_P1

ITEM_KEYS = {
    "id",
    "at",
    "actor_type",
    "actor_label",
    "actor_name",
    "autonomous",
    "action",
    "capability",
    "sentence",
    "reason",
    "case",
    "employee",
}


@pytest.fixture(scope="module")
def c(story_client):
    return story_client


def feed(client, headers=PRIYA, **params) -> dict:
    r = client.get("/api/activity", headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def all_items(client, headers=PRIYA, limit=200, **params) -> list[dict]:
    items, before = [], None
    while True:
        page = feed(
            client, headers, limit=limit, **({"before_id": before} if before else {}), **params
        )
        items += page["items"]
        before = page["next_before_id"]
        if before is None:
            return items


def summary(client, headers=PRIYA, **params) -> dict:
    r = client.get("/api/activity/summary", headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()["counts"]


def session(client) -> Session:
    return Session(client.app.state.engine)


# ---------------------------------------------------------------- the story, in order


def test_feed_tells_the_story_in_order_with_the_right_actors(c):
    items = all_items(c)
    ids = [i["id"] for i in items]
    assert ids == sorted(ids, reverse=True) and len(set(ids)) == len(ids)  # newest first
    assert all(set(i) == ITEM_KEYS for i in items)
    oldest_first = list(reversed(items))
    # Workflow time never goes backwards along the story (the demo clock only moves forward).
    times = [datetime.fromisoformat(i["at"]) for i in oldest_first]
    assert times == sorted(times)

    def first(action, case=None, actor=None):
        return next(
            i
            for i in oldest_first
            if i["action"] == action
            and (case is None or (i["case"] or {}).get("exception_id") == case)
            and (actor is None or i["actor_type"] == actor)
        )

    steps = [
        first("auto_resolve", SANA_P2),
        first("punch_ingested"),
        first("detected", NEHA_P1),  # detection runs inside the punch request ...
        first("post_punch_detection"),  # ... and its summary row is written last
        first("auto_investigation_started", NEHA_P1),
        first("investigation_case_stored", NEHA_P1),
        first("ask_worker", NEHA_P1),
        first("worker_message_sent", NEHA_P1),
        first("structured_model_failed", MEENA_P5),
        first("ask_worker", AMIT_P1),
        first("demo_clock_moved"),
        first("no_reply_reminder", NEHA_P1),
        first("worker_reply", AMIT_P1),
        first("no_reply_ladder_stopped", AMIT_P1),
        first("worker_time_extraction_rejected", AMIT_P1),
        first("worker_time_confirmed", AMIT_P1),
        first("no_reply_to_supervisor", NEHA_P1),
        first("no_reply_to_admin", NEHA_P1),
        first("approve", AMIT_P1),
        first("post_fix_detection", AMIT_P1),
        first("auto_resolve_undone", SANA_P2),
    ]
    assert [s["id"] for s in steps] == sorted(s["id"] for s in steps)
    who = {s["action"] + ":" + ((s["case"] or {}).get("exception_id") or ""): s for s in steps}
    expected_actors = {
        "auto_resolve": ("system", "Rule engine", True),
        "punch_ingested": ("device", None, True),
        "post_punch_detection": ("system", "Rule engine", True),
        "auto_investigation_started": ("system", "Scheduler", True),
        "investigation_case_stored": ("agent", "LLM agent", True),
        "structured_model_failed": ("agent", "LLM agent", True),
        "demo_clock_moved": ("admin", "Priya Sharma", False),
        "no_reply_reminder": ("system", "No-reply ladder", True),
        "worker_reply": ("worker", "Amit Verma", False),
        "no_reply_to_admin": ("system", "No-reply ladder", True),
        "approve": ("supervisor", "Ravi Kumar", False),
        "auto_resolve_undone": ("supervisor", "Ravi Kumar", False),
    }
    for step in steps:
        if step["action"] in expected_actors:
            actor, name, autonomous = expected_actors[step["action"]]
            assert (step["actor_type"], step["autonomous"]) == (actor, autonomous), step
            if name:
                assert step["actor_name"] == name, step
        assert step["capability"] == autonomy.capability_for(step["action"], step["actor_type"]).key
    ask = [s for s in steps if s["action"] == "ask_worker"]
    assert [(s["actor_type"], s["actor_name"]) for s in ask] == [
        ("system", "Scheduler"),
        ("supervisor", "Ravi Kumar"),
    ]
    punch = who["punch_ingested:"]
    assert punch["employee"]["name"] == "Neha Gupta" and punch["case"] is None
    assert punch["sentence"].endswith("recorded a clock-in for Neha Gupta at Wed 15 Apr 08:58.")
    sent = who[f"worker_message_sent:{NEHA_P1}"]
    assert (sent["actor_type"], sent["actor_name"]) == ("agent", "LLM agent")
    assert who[f"no_reply_to_admin:{NEHA_P1}"]["at"] == "2026-04-18T08:00:00"
    assert who[f"approve:{AMIT_P1}"]["case"]["policy_id"] == "P1"
    assert who[f"auto_resolve_undone:{SANA_P2}"]["reason"] == UNDO_REASON
    assert not [i for i in items if i["action"] in autonomy.HIDDEN_FROM_FEED]


def test_amits_seeded_p1_story_only_has_what_people_did(c):
    trail = [i["action"] for i in reversed(all_items(c, exception_id=AMIT_P1))]
    assert trail[0] == "detected" and trail[-1] == "post_fix_detection"
    assert "no_reply_to_supervisor" not in trail  # he answered after the reminder


# ---------------------------------------------------------------- filters and paging


def test_filters(c):
    every = all_items(c)
    device = all_items(c, actor_type="device")
    assert device and {i["action"] for i in device} == {"punch_ingested"}
    autonomous = all_items(c, mode="autonomous")
    human = all_items(c, mode="human")
    assert {i["actor_type"] for i in autonomous} == {"system", "agent", "device"}
    assert {i["actor_type"] for i in human} == {"worker", "supervisor", "admin"}
    assert all(i["autonomous"] for i in autonomous) and not any(i["autonomous"] for i in human)
    assert len(autonomous) + len(human) == len(every)

    p2 = all_items(c, policy_id="P2")
    assert p2 and {i["case"]["policy_id"] for i in p2} == {"P2"}
    neha = all_items(c, employee_id="E004")
    assert {i["employee"]["employee_id"] for i in neha} == {"E004"}
    assert "punch_ingested" in {i["action"] for i in neha}  # a row without a case, by subject
    case = all_items(c, exception_id=MEENA_P5)
    assert case and {i["case"]["exception_id"] for i in case} == {MEENA_P5}

    late = all_items(c, date_from="2026-04-17")
    early = all_items(c, date_to="2026-04-16")
    assert late and early and len(late) + len(early) == len(every)
    assert all(i["at"] >= "2026-04-17" for i in late)
    assert {"no_reply_to_supervisor", "no_reply_to_admin"} <= {i["action"] for i in late}
    assert all_items(c, date_from="2026-04-17", date_to="2026-04-17", mode="human") != []
    assert all_items(c, policy_id="P2", actor_type="device") == []


def test_pagination_has_no_gaps_or_overlaps(c):
    every = all_items(c)
    paged = all_items(c, limit=7)
    assert [i["id"] for i in paged] == [i["id"] for i in every]
    first = feed(c, limit=7)
    assert len(first["items"]) == 7 and first["next_before_id"] == first["items"][-1]["id"]
    assert feed(c, limit=len(every))["next_before_id"] is None
    for bad in ({"limit": 0}, {"limit": 201}, {"before_id": 0}, {"mode": "everything"}):
        assert_error(c.get("/api/activity", headers=PRIYA, params=bad), 422, "validation_error")


# ---------------------------------------------------------------- summary strip


def _db_count(client, actions, distinct_cases=False) -> int:
    with session(client) as s:
        what = (
            func.count(func.distinct(AuditLogRow.exception_id))
            if distinct_cases
            else func.count(AuditLogRow.id)
        )
        return s.scalar(select(what).where(AuditLogRow.action.in_(actions)))


def test_summary_counts_match_the_story_and_the_database(c):
    counts = summary(c)
    assert counts == {
        "investigated": 4,  # Neha (scheduler), Amit, Meena P5 (template), Meena P3 (template)
        "messages_sent": 2,  # Neha (scheduler), Amit (Ravi)
        "reminders_sent": 2,
        "auto_resolved": 1,  # Sana's P2 at the demo reset
        "auto_resolves_undone": 1,  # ... which Ravi undid
        "escalated_by_silence": 1,  # Neha: to Ravi, then to Priya (one case)
        "human_approvals": 1,
        "decided_without_worker": 0,
        "human_rejections": 0,
        "device_punches": 1,
    }
    from attendflow.activity.feed import DISTINCT_CASES, SUMMARY_ACTIONS

    for key, actions in SUMMARY_ACTIONS.items():
        assert counts[key] == _db_count(c, actions, key in DISTINCT_CASES), key


def test_summary_follows_the_period_and_the_scope(c):
    thursday = summary(c, date_to="2026-04-16")  # the reminders fire at Thu 16:00
    assert thursday["escalated_by_silence"] == 0 and thursday["reminders_sent"] == 2
    before_ladder = thursday
    assert before_ladder["auto_resolved"] == 1 and before_ladder["device_punches"] == 1
    after = summary(c, date_from="2026-04-16", date_to="2026-04-16")
    assert after["auto_resolved"] == 1
    ravi = summary(c, RAVI)
    assert ravi["device_punches"] == 0  # rows without a case are payroll-only
    assert ravi["escalated_by_silence"] == 1 and ravi["human_approvals"] == 1
    sunita = summary(c, SUNITA)
    assert sum(sunita.values()) == 0  # nothing happened on Outbound cases but detection
    assert summary(c, policy_id="P2")["auto_resolved"] == 1
    assert summary(c, policy_id="P1")["auto_resolved"] == 0


# ---------------------------------------------------------------- who sees what


def _team(client, supervisor: str) -> set[str]:
    with session(client) as s:
        return set(
            s.scalars(
                select(EmployeeRow.employee_id).where(EmployeeRow.supervisor_id == supervisor)
            )
        )


def test_supervisors_see_only_their_team(c):
    ravi = all_items(c, RAVI)
    sunita = all_items(c, SUNITA)
    assert ravi and sunita
    assert {i["employee"]["employee_id"] for i in ravi} <= _team(c, "E101")
    assert {i["employee"]["employee_id"] for i in sunita} <= _team(c, "E102")
    assert all(i["case"] is not None for i in ravi + sunita)  # no rows without a case
    assert all_items(c, RAVI, exception_id="P9-E006-2026-04-15") == []  # Karan: Outbound
    assert all_items(c, SUNITA, employee_id="E004") == []
    with session(client := c) as s:
        inbound_rows = s.scalar(
            select(func.count(AuditLogRow.id))
            .join(ExceptionRow, AuditLogRow.exception_id == ExceptionRow.id)
            .where(
                ExceptionRow.employee_id.in_(_team(client, "E101")),
                AuditLogRow.action.notin_(autonomy.HIDDEN_FROM_FEED),
            )
        )
    assert len(ravi) == inbound_rows
    assert feed(c, RAVI)["viewer"] == {"employee_id": "E101", "role": "supervisor"}


@pytest.mark.parametrize("path", ["/api/activity", "/api/activity/summary", "/api/autonomy"])
def test_workers_and_strangers_get_403(c, path):
    assert_error(c.get(path, headers=AMIT), 403, "supervisor_only")
    assert_error(c.get(path, headers={"X-Actor-Id": "E999"}), 403, "unknown_actor")
    assert_error(c.get(path), 422, "validation_error")


# ---------------------------------------------------------------- nothing leaks


def test_the_story_really_recorded_diagnostics_and_previews(c):
    """Precondition for the leak test: the audit log holds the planted diagnostic text."""
    with session(c) as s:
        rows = s.scalars(select(AuditLogRow)).all()
    stored = json.dumps([[r.after, r.reason] for r in rows], default=str)
    assert LEAK_PROVIDER in stored  # structured_model_failed.after.diagnostic
    assert LEAK_OUTPUT in stored  # worker_time_extraction_rejected.after.preview
    assert c.app.state.settings.llm_diagnostics is True


def _everything_shown(c) -> str:
    texts = []
    for headers in (PRIYA, RAVI, SUNITA):
        texts.append(json.dumps(all_items(c, headers)))
        texts.append(json.dumps(all_items(c, headers, limit=3)))
        texts.append(c.get("/api/activity/summary", headers=headers).text)
        texts.append(c.get("/api/autonomy", headers=headers).text)
    for case in (MEENA_P5, MEENA_P3_MON, AMIT_P1, NEHA_P1):
        texts.append(c.get(f"/api/supervisor/cases/{case}", headers=RAVI).text)
    return "\n".join(texts)


def test_no_diagnostics_previews_prompts_or_keys_in_any_response(c):
    shown = _everything_shown(c)
    for leak in LEAKS:
        assert leak not in shown, leak
    assert '"preview"' not in shown and "diagnostic" not in shown.lower()
    assert '"before"' not in shown and '"after"' not in shown
    assert "test-device-key" not in shown  # the device API key
    assert SYSTEM_PROMPT[:60] not in shown and EXTRACTION_PROMPT[:60] not in shown
    rejected = next(i for i in all_items(c) if i["action"] == "structured_draft_rejected")
    assert rejected["sentence"] == "The model's draft failed code validation and was not used."
    assert rejected["reason"] is None


# ---------------------------------------------------------------- autonomous rows happen


# Autonomous actions this story cannot produce, and the existing test that does.
COVERED_ELSEWHERE = {
    "updated_by_detection": "tests/test_api_system.py::test_detection_refreshes_open_exceptions",
    "options_added": (
        "tests/test_api_fixes_phase4.py::test_detection_adds_options_to_a_case_in_progress_that_had_none"
    ),
    "auto_resolve_held": (
        "tests/test_api_auto_resolve.py::test_kill_switch_off_nothing_auto_resolves"
    ),
    "post_fix_detection_failed": (
        "tests/test_supervisor.py::test_detection_failure_after_approve_keeps_the_approval"
    ),
    "post_undo_detection_failed": (
        "tests/test_activity_api.py::test_failed_detection_after_an_undo_keeps_the_undo"
    ),
    "post_punch_detection_failed": (
        "tests/test_ingest.py::test_failed_detection_keeps_the_punch_and_is_audited"
    ),
    "no_longer_detected": None,  # in the story (Neha's P10)
    "investigation_started": (
        "tests/test_agent_loop.py::test_tools_feed_back_and_multiple_calls_and_runs_are_logged"
    ),
    "investigation_finished": (
        "tests/test_agent_loop.py::test_tools_feed_back_and_multiple_calls_and_runs_are_logged"
    ),
    # Phase 17: the story has no LLM key and no briefing refresh.
    "briefing_generated": (
        "tests/test_briefing_api.py::test_refresh_stores_an_llm_briefing_and_audits_it"
    ),
    "briefing_fallback": (
        "tests/test_briefing_api.py::test_scheduled_briefing_once_per_workflow_day_after_new_activity"
    ),
}


def test_autonomous_rows_happen_with_their_actor_in_the_end_to_end_story(c):
    from tests.test_autonomy import _test_source

    with session(c) as s:
        seen = set(s.execute(select(AuditLogRow.action, AuditLogRow.actor)).all())
    for row in autonomy.CAPABILITIES:
        if not row.autonomous:
            continue
        for action in row.audit_actions:
            # ask_worker is also a person's action: count only this row's actors.
            if {actor for a, actor in seen if a == action} & set(row.audit_actors):
                continue
            covering = COVERED_ELSEWHERE.get(action)
            assert covering, f"{action} ({row.key}) never happened in the story"
            _test_source(covering)  # the named test exists
            assert f'"{action}"' in (REPO_ROOT / covering.split("::")[0]).read_text(
                encoding="utf-8"
            ), covering
    # The autonomous rows' actions show up as autonomous actors only.
    for action, actor in seen:
        row = autonomy.capability_for(action, actor)
        assert row is not None, (action, actor)
        assert row.autonomous == (actor in autonomy.AUTONOMOUS_AUDIT_ACTORS), (action, actor)


# ---------------------------------------------------------------- case links and trace


def test_a_supervisor_opens_a_team_case_from_the_feed_read_only_with_the_trace(c):
    escalated = c.get(f"/api/supervisor/cases/{NEHA_P1}", headers=RAVI)
    assert escalated.status_code == 200, escalated.text
    body = escalated.json()
    assert (body["status"], body["assigned_to"], body["can_decide"]) == ("escalated", "E201", False)
    assert [t["tool_name"] for t in body["trace"]] == [
        "get_schedule",
        "get_punches",
        "get_leave",
        "get_policy",
        "run_checks",
    ]
    assert body["trace"][-1]["result_summary"].startswith(("No new violations", "New violations"))
    assert body["trace"][0]["result_summary"].startswith("Scheduled ")
    assert_error(c.get(f"/api/supervisor/cases/{NEHA_P1}", headers=SUNITA), 403, "not_assigned")
    assert_error(
        post(c, NEHA_P1, "reject", {"reason": "reading is not deciding"}, RAVI),
        403,
        "not_assigned",
    )
    assert c.get(f"/api/supervisor/cases/{AMIT_P1}", headers=RAVI).json()["can_decide"] is True
    admin = c.get(f"/api/admin/exceptions/{NEHA_P1}", headers=PRIYA).json()
    assert [t["result_summary"] for t in admin["tool_calls"]] == [
        t["result_summary"] for t in body["trace"]
    ]


def test_autonomy_endpoint_is_the_registry(c):
    rows = c.get("/api/autonomy", headers=RAVI).json()["items"]
    assert [r["key"] for r in rows] == [c.key for c in autonomy.CAPABILITIES]
    auto = next(r for r in rows if r["key"] == "auto_resolve")
    assert (auto["actor_label"], auto["approval_label"], auto["reversible_label"]) == (
        "Code",
        "None",
        "Yes, with undo",
    )
    assert {r["kind"] for r in rows} == {"allowed", "never"}
