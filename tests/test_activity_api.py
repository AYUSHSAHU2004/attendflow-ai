"""Phase 14: Activity Center API tests that need their own data (not the shared story)."""

from __future__ import annotations

from tests.api_helpers import PRIYA, RAVI, SANA_P2, get, post, snapshot


def test_empty_feed_and_zero_summary_before_anything_happened(client):
    assert client.post("/api/seed").status_code == 200  # employees only, no detection yet
    feed = client.get("/api/activity", headers=PRIYA).json()
    assert feed["items"] == [] and feed["next_before_id"] is None
    counts = client.get("/api/activity/summary", headers=RAVI).json()["counts"]
    assert set(counts.values()) == {0}


def test_failed_detection_after_an_undo_keeps_the_undo(demo, monkeypatch):
    from attendflow.cases import service

    def broken(*args, **kwargs):
        raise RuntimeError("detection exploded")

    monkeypatch.setattr(service, "run_detection", broken)
    r = post(demo, SANA_P2, "undo", {"reason": "The second tap was a real re-entry"}, RAVI)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "open" and r.json()["detection"]["ran"] is False
    trail = [a["action"] for a in get(demo, SANA_P2)["audit_trail"]]
    assert trail[-2:] == ["auto_resolve_undone", "post_undo_detection_failed"]
    feed = demo.get("/api/activity", headers=PRIYA, params={"exception_id": SANA_P2}).json()
    newest = feed["items"][0]
    assert newest["action"] == "post_undo_detection_failed"
    assert newest["sentence"] == "Detection after the undo failed; the next run picks it up."
    assert newest["reason"] is None  # the internal message stays out of the feed


def test_the_feed_and_summary_never_write(demo):
    before = snapshot(demo)
    for path in ("/api/activity", "/api/activity/summary", "/api/autonomy"):
        assert demo.get(path, headers=PRIYA).status_code == 200
    assert snapshot(demo) == before


def test_agent_rows_use_the_moved_demo_clock(demo_client, monkeypatch):
    """Regression check for the reported Phase 13 gap (tool-call rows stamped 08:00 after
    the demo clock moved): through the API every agent row, tool calls included, carries
    the moved workflow time. (Only the standalone attendflow-agent-smoke CLI uses the
    fixed as-of clock, agent/loop.py.)"""
    from datetime import datetime

    from sqlalchemy import select

    from attendflow.db.models import AuditLogRow, ToolCallRow
    from tests.api_helpers import AMIT_P1, session_for
    from tests.test_e2e_prototype import run_investigation, scripted_investigation
    from tests.test_scheduler import AnyCaseModel

    c = demo_client
    assert c.post("/api/seed").status_code == 200
    assert c.post("/api/admin/demo/reset", headers=PRIYA).status_code == 200
    moved = c.post("/api/admin/demo/clock", json={"hours": 8}, headers=PRIYA)
    assert moved.status_code == 200, moved.text
    scripted_investigation(monkeypatch, AnyCaseModel())
    assert run_investigation(c, AMIT_P1, RAVI)["reason"] == "validated"
    with session_for(c) as s:
        calls = s.scalars(select(ToolCallRow).where(ToolCallRow.exception_id == AMIT_P1)).all()
        agent = s.scalars(
            select(AuditLogRow).where(
                AuditLogRow.exception_id == AMIT_P1, AuditLogRow.actor == "agent"
            )
        ).all()
    assert calls and agent
    assert {r.created_at for r in [*calls, *agent]} == {datetime(2026, 4, 16, 16)}
