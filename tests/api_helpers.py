"""Helpers for API tests."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from attendflow.agent.case import ProposedFix, fallback_case, normalized_params, routing
from attendflow.db.models import (
    AuditLogRow,
    ExceptionRow,
    LeaveBalanceRow,
    LeaveRecordRow,
    PunchRow,
    ScheduleEntryRow,
)
from attendflow.policy.models import load_policy_text

RAVI = {"X-Actor-Id": "E101"}  # Inbound supervisor: Amit, Meena, Neha, Sana, Arjun
SUNITA = {"X-Actor-Id": "E102"}  # Outbound supervisor: Ramesh, Karan, Dev, Farah, Pooja
PRIYA = {"X-Actor-Id": "E201"}  # payroll admin
AMIT = {"X-Actor-Id": "E001"}
MEENA = {"X-Actor-Id": "E002"}

AMIT_P1 = "P1-E001-2026-04-14"
AMIT_P14 = "P14-E001-2026-04-14-P0037"
MEENA_P3_MON = "P3-E002-2026-04-13"
MEENA_P5 = "P5-E002-2026-04-13"
NEHA_P10 = "P10-E004-2026-04-15"
SANA_P2 = "P2-E005-2026-04-13-P0003"
SANA_P8 = "P8-E005-2026-04-14-P0038"
SANA_P14 = "P14-E005-2026-04-14-P0038"
KARAN_P9 = "P9-E006-2026-04-15"
DEV_P11 = "P11-E007-2026-04-13-sick"
FARAH_P13 = "P13-E008-2026-04-15"


def session_for(client) -> Session:
    return Session(client.app.state.engine)


def snapshot(client) -> dict[str, list[tuple]]:
    """Every source-data row, to prove a call changed nothing."""
    with session_for(client) as s:
        return {
            "timecards": [
                (p.punch_id, p.employee_id, p.timestamp, p.type, p.source, p.voided)
                for p in s.scalars(select(PunchRow).order_by(PunchRow.punch_id))
            ],
            "schedule": [
                (r.employee_id, r.date, r.shift_start, r.shift_end)
                for r in s.scalars(
                    select(ScheduleEntryRow).order_by(
                        ScheduleEntryRow.employee_id, ScheduleEntryRow.date
                    )
                )
            ],
            "leave_records": [
                (r.employee_id, r.date, r.leave_type, r.duration, r.status, r.unpaid)
                for r in s.scalars(
                    select(LeaveRecordRow).order_by(LeaveRecordRow.employee_id, LeaveRecordRow.date)
                )
            ],
            "leave_balances": [
                (b.employee_id, b.leave_type, b.total_per_year, b.used)
                for b in s.scalars(
                    select(LeaveBalanceRow).order_by(
                        LeaveBalanceRow.employee_id, LeaveBalanceRow.leave_type
                    )
                )
            ],
        }


def audit_count(client) -> int:
    with session_for(client) as s:
        return len(s.scalars(select(AuditLogRow.id)).all())


def get(client, exception_id: str) -> dict:
    r = client.get(f"/api/exceptions/{exception_id}")
    assert r.status_code == 200, r.text
    return r.json()


def post(client, exception_id: str, action: str, body: dict, headers: dict):
    return client.post(f"/api/exceptions/{exception_id}/{action}", json=body, headers=headers)


def assert_error(response, status: int, code: str) -> dict:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == code, body
    assert body["error"]["message"]
    return body["error"]


def store_test_investigation(client, exception_id: str, option_id: str | None = None) -> None:
    """Seed a trusted investigation without contacting a provider."""
    settings = client.app.state.settings
    sections = load_policy_text(settings.data_dir / "policy.md")
    with session_for(client) as session, session.begin():
        row = session.get(ExceptionRow, exception_id)
        case = fallback_case(row, sections[row.policy_id], 0)
        if option_id is not None:
            option = next(option for option in row.fix_options if option["option_id"] == option_id)
            proposal = ProposedFix(
                option_id=option_id, params=normalized_params(option, option["params"])
            )
            who, next_action = routing(row, option)
            case = case.model_copy(
                update={
                    "proposed_fix": proposal,
                    "who_to_ask": who,
                    "next_action": next_action,
                }
            )
        row.investigation_case = case.model_dump(mode="json")
        row.proposed_fix = case.proposed_fix.model_dump(mode="json") if case.proposed_fix else None


def worker_says_yes(
    client, exception_id: str, option_id: str | None, supervisor: dict, worker: dict
) -> None:
    """Investigate (template), ask the worker and record their Yes for this option."""
    store_test_investigation(client, exception_id, option_id)
    asked = post(client, exception_id, "ask-worker", {}, supervisor)
    assert asked.status_code == 200, asked.text
    reply = post(client, exception_id, "worker-reply", {"confirmed": True}, worker)
    assert reply.status_code == 200, reply.text


def confirm_amit_clock_out(client, time: str | None = None) -> None:
    store_test_investigation(client, AMIT_P1)
    assert post(client, AMIT_P1, "ask-worker", {}, RAVI).status_code == 200
    if time is None:
        reply = post(client, AMIT_P1, "worker-reply", {"confirmed": True}, AMIT)
    else:
        saved = post(
            client, AMIT_P1, "worker-reply", {"confirmed": False, "text": "I left late."}, AMIT
        )
        assert saved.status_code == 200, saved.text
        reply = post(client, AMIT_P1, "worker-manual-time", {"time": time}, AMIT)
    assert reply.status_code == 200, reply.text
