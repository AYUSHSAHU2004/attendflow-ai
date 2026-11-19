"""The operations dashboard reads current state, the P5 forecast, and the Phase 12 metric."""

import json
from dataclasses import replace

import pytest
from sqlalchemy import event

from attendflow.config import get_settings
from attendflow.policy.models import load_policy
from tests.api_helpers import (
    AMIT,
    AMIT_P1,
    MEENA_P5,
    PRIYA,
    RAVI,
    SANA_P2,
    SUNITA,
    assert_error,
    post,
)
from tests.test_e2e_scheduler import _clock, _cycle
from tests.test_ingest import NEHA_IN, NEHA_P1


def _get(client, route="/api/dashboard", headers=PRIYA, **filters):
    response = client.get(route, headers=headers, params=filters)
    assert response.status_code == 200, response.text
    return response.json()


def _match_admin(client, chart, **dates):
    def matched(**filters):
        return _get(client, "/api/admin/exceptions", **dates, **filters)["matched"]

    for status, count in chart["by_status"].items():
        assert count == matched(status=status)
    assert chart["active_total"] == matched(active_only=True)
    for severity, count in chart["by_severity"].items():
        assert count == matched(severity=severity, active_only=True)
    for policy, count in chart["by_policy"].items():
        assert count == matched(policy_id=policy, active_only=True)
    for step, count in chart["ladder"].items():
        assert count == matched(no_reply=step, active_only=True)
    for row in chart["workload"]:
        scope = {"supervisor_id": row["supervisor_id"]}
        assert row["active"] == matched(active_only=True, **scope)
        assert row["awaiting_worker"] == matched(status="awaiting_worker", **scope)
        assert row["awaiting_supervisor"] == matched(status="awaiting_supervisor", **scope)
    assert chart["stuck"] == matched(no_reply="any")
    assert chart["auto_resolve"] == _get(client, "/api/admin/metrics/auto-resolve", **dates)
    assert chart["auto_resolve"]["resolved_without_human"] == matched(auto_resolved=True)
    if not dates:
        counters = _get(client, "/api/admin/exceptions")["counters"]
        assert chart["stuck"] == counters["stuck"]
        assert chart["by_status"] == {key: counters[key] for key in chart["by_status"]}
        assert chart["auto_resolve"]["resolved_without_human"] == counters["auto_resolved"]


def test_seeded_dashboard_matches_admin_and_scopes_to_each_supervisor(demo):
    chart = _get(demo)
    _match_admin(demo, chart)
    assert chart["active_total"] == 16
    assert chart["auto_resolve"]["resolved_without_human"] == 1
    assert chart["auto_resolve"]["needed_handling"] == 17
    assert chart["aging"]["case_age"] == [16, 0, 0, 0]
    meena = next(row for row in chart["overtime"]["workers"] if row["employee_id"] == "E002")
    assert (
        meena["worked_hours"],
        meena["scheduled_remaining_hours"],
        meena["projected_hours"],
    ) == (36, 12, 48)
    assert meena["level"] == "projected_over"
    assert chart["overtime"]["limit_hours"] == 40
    p5 = _get(demo, f"/api/admin/exceptions/{MEENA_P5}")["details"]
    for key in ("worked_hours", "scheduled_remaining_hours", "projected_hours"):
        assert meena[key] == p5[key]

    for actor in (RAVI, SUNITA):
        team = _get(demo, headers=actor)
        assert team["scope"] == "team"
        assert [row["supervisor_id"] for row in team["workload"]] == [actor["X-Actor-Id"]]
        assert team["active_total"] == team["workload"][0]["active"]
    ravi, sunita = (_get(demo, headers=actor) for actor in (RAVI, SUNITA))
    assert ravi["active_total"] + sunita["active_total"] == chart["active_total"]
    assert ravi["auto_resolve"]["resolved_without_human"] == 1
    assert sunita["auto_resolve"]["resolved_without_human"] == 0
    assert "E002" in {row["employee_id"] for row in ravi["overtime"]["workers"]}
    assert "E002" not in {row["employee_id"] for row in sunita["overtime"]["workers"]}
    assert_error(demo.get("/api/dashboard", headers=AMIT), 403, "supervisor_only")


def test_exception_dates_are_inclusive_and_overtime_keeps_its_week(demo):
    day = {"date_from": "2026-04-13", "date_to": "2026-04-13"}
    chart = _get(demo, **day)
    assert 0 < chart["active_total"] < _get(demo)["active_total"]
    _match_admin(demo, chart, **day)
    empty = _get(demo, date_from="2026-04-20", date_to="2026-04-20")
    assert empty["active_total"] == empty["auto_resolve"]["needed_handling"] == 0
    assert empty["overtime"] == chart["overtime"]
    assert_error(
        demo.get(
            "/api/dashboard",
            headers=PRIYA,
            params={
                "date_from": "2026-04-16",
                "date_to": "2026-04-13",
            },
        ),
        422,
        "invalid_date_range",
    )


def test_dashboard_after_punch_reminder_and_undo(demo_client):
    c = demo_client
    assert c.post("/api/seed").status_code == 200
    assert c.post("/api/admin/demo/reset", headers=PRIYA).status_code == 200
    baseline = _get(c)
    response = c.post("/api/admin/demo/punch", json=NEHA_IN, headers=PRIYA)
    assert response.status_code == 201, response.text
    assert NEHA_P1 in c.post("/api/admin/scheduler/run-now", headers=PRIYA).json()["messages_sent"]
    waiting = _get(c)
    assert waiting["by_policy"]["P1"] == baseline["by_policy"]["P1"] + 1
    assert waiting["ladder"]["waiting"] == 1
    assert waiting["stuck"] == 0
    assert waiting["auto_resolve"]["closed_by_data_change"] == 1
    _match_admin(c, waiting)

    _clock(c, 8)
    assert _cycle(c)["reminded"] == [NEHA_P1]
    reminded = _get(c)
    assert reminded["ladder"]["waiting"] == 0
    assert reminded["ladder"]["reminded"] == reminded["stuck"] == 1
    assert reminded["aging"]["waiting_age"] == [0, 1, 0, 0]
    assert reminded["aging"]["case_age"] == [0, reminded["active_total"], 0, 0]
    assert reminded["overtime"] == waiting["overtime"]
    _match_admin(c, reminded)

    _clock(c, 16)
    assert _cycle(c)["to_supervisor"] == [NEHA_P1]
    with_supervisor = _get(c)
    assert with_supervisor["ladder"]["supervisor"] == with_supervisor["stuck"] == 1
    assert with_supervisor["ladder"]["reminded"] == 0
    _match_admin(c, with_supervisor)

    _clock(c, 24)
    assert _cycle(c)["to_admin"] == [NEHA_P1]
    with_payroll = _get(c)
    assert with_payroll["ladder"]["payroll_admin"] == with_payroll["stuck"] == 1
    assert with_payroll["aging"]["case_age"] == [0, 0, 0, with_payroll["active_total"]]

    undo = post(c, SANA_P2, "undo", {"reason": "Supervisor double checked the taps"}, RAVI)
    assert undo.status_code == 200, undo.text
    after = _get(c)
    _match_admin(c, after)
    assert after["active_total"] == with_payroll["active_total"] + 1
    assert after["by_policy"]["P2"] == 1
    assert after["auto_resolve"]["resolved_without_human"] == 0
    assert after["auto_resolve"]["undone"] == 1
    # Audit events are historical. The undo changes current state without erasing the event.
    audit = _get(c, "/api/activity/summary")["counts"]
    assert audit["auto_resolved"] == baseline["auto_resolve"]["resolved_without_human"]
    assert audit["auto_resolves_undone"] == after["auto_resolve"]["undone"]
    assert audit["reminders_sent"] == reminded["ladder"]["reminded"]
    assert audit["escalated_by_silence"] == after["ladder"]["payroll_admin"]
    neha = _get(c, "/api/activity/summary", headers=RAVI, exception_id=NEHA_P1)["counts"]
    assert neha["escalated_by_silence"] == _get(c, headers=RAVI)["ladder"]["payroll_admin"]
    assert _get(c, headers=SUNITA)["ladder"]["payroll_admin"] == 0
    amit = _get(c, f"/api/admin/exceptions/{AMIT_P1}")
    assert amit["status"] == "open"
    assert [item["action"] for item in amit["audit_trail"]] == ["detected"]


def test_policy_limit_and_warning_margin_change_the_forecast_display(demo, data_copy, monkeypatch):
    state = demo.app.state
    # Copy the real policy so the test exercises the same policy loader as startup.
    policy_path = data_copy / "policy.json"
    policy = json.loads(policy_path.read_text())
    policy["policies"]["P5"]["params"]["weekly_overtime_after_hours"] = 50
    policy_path.write_text(json.dumps(policy))
    state.policy = load_policy(policy_path)
    settings = state.settings

    def forecast(margin):
        monkeypatch.setenv("OVERTIME_WARNING_MARGIN_HOURS", str(margin))
        configured = get_settings(env_file=None).overtime_warning_margin_hours
        state.settings = replace(settings, overtime_warning_margin_hours=configured)
        return _get(demo)["overtime"]

    near = forecast(4)
    assert (near["limit_hours"], near["warning_margin_hours"]) == (50, 4)
    meena = next(row for row in near["workers"] if row["employee_id"] == "E002")
    assert meena["projected_hours"] == 48
    assert meena["level"] == "approaching"
    assert set(meena) == {
        "employee_id",
        "employee_name",
        "worked_hours",
        "scheduled_remaining_hours",
        "projected_hours",
        "level",
    }
    narrower = forecast(1)
    assert "E002" not in {row["employee_id"] for row in narrower["workers"]}


@pytest.mark.parametrize("margin", ["0", "-1", "nan", "inf"])
def test_overtime_warning_margin_must_be_positive_and_finite(monkeypatch, margin):
    monkeypatch.setenv("OVERTIME_WARNING_MARGIN_HOURS", margin)
    with pytest.raises(ValueError, match="OVERTIME_WARNING_MARGIN_HOURS"):
        get_settings(env_file=None)


def test_dashboard_uses_a_read_only_transaction(demo):
    statements = []
    engine = demo.app.state.engine

    def record(conn, cursor, statement, params, context, many):
        statements.append(statement.strip().upper())

    event.listen(engine, "before_cursor_execute", record)
    try:
        assert _get(demo)["active_total"] > 0
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert statements[0] == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
    assert all(statement.startswith("SELECT") for statement in statements[1:])
