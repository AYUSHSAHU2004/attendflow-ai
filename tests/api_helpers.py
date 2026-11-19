"""Helpers for API tests."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from attendflow.db.models import (
    AuditLogRow,
    LeaveBalanceRow,
    LeaveRecordRow,
    PunchRow,
    ScheduleEntryRow,
)

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
