"""The tools on the real database: they never write (not even run_checks), the read-only
session is enforced by PostgreSQL itself, and run_checks predicts what the real fix
writer + detection then find (parity)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from attendflow.db.models import Base, ExceptionRow, PunchRow
from attendflow.engine import run_engine
from attendflow.engine.rules import week_start
from attendflow.policy import load_policy
from attendflow.policy.models import load_policy_text
from attendflow.tools import TOOLS, ToolRunner
from attendflow.tools.context import ReadOnlyViolation, read_only_session
from tests.api_helpers import MEENA_P3_MON, MEENA_P5, RAVI, post, session_for
from tests.conftest import DATA_DIR
from tests.test_tools import AS_OF, change

POLICY = load_policy(DATA_DIR / "policy.json")
TEXT = load_policy_text(DATA_DIR / "policy.md")


def factory(client) -> sessionmaker:
    return sessionmaker(bind=client.app.state.engine)


def runner(client) -> ToolRunner:
    return ToolRunner.for_database(factory(client), POLICY, TEXT, AS_OF)


def every_table(client) -> dict[str, list[tuple]]:
    """Every row of every table (source data, exceptions, audit log, tool calls, settings)."""
    with session_for(client) as s:
        return {
            t.name: [tuple(r) for r in s.execute(t.select().order_by(*t.primary_key.columns))]
            for t in Base.metadata.sorted_tables
        }


CALLS = [
    ("get_schedule", {"employee_id": "E001", "date": "2026-04-14"}),
    ("get_leave", {"employee_id": "E007", "date": "2026-04-16"}),
    ("get_leave_balance", {"employee_id": "E007", "leave_type": "sick"}),
    ("get_punches", {"employee_id": "E002", "date": "2026-04-13"}),
    ("get_policy", {"policy_id": "P3"}),
    ("run_checks", change("E001", "2026-04-14", "set_clock_out", timestamp="2026-04-14T19:30")),
    (
        "run_checks",
        change(
            "E002",
            "2026-04-13",
            "correct_clock_out",
            punch_id="P0031",
            timestamp="2026-04-13T16:29:47",
        ),
    ),
    (
        "run_checks",
        change(
            "E002",
            "2026-04-16",
            "reduce_scheduled_hours",
            cuts=[{"date": "2026-04-17", "scheduled_hours": 6, "new_hours": 0}],
        ),
    ),
    (
        "run_checks",
        change(
            "E004",
            "2026-04-13",
            "add_break",
            break_start="2026-04-13T12:00",
            break_end="2026-04-13T12:30",
        ),
    ),
    (
        "run_checks",
        change("E007", "2026-04-16", "cancel_leave", date="2026-04-16", leave_type="sick", days=1),
    ),
    ("run_checks", change("E009", "2026-04-15", "void_punches", punch_ids=["P0001"])),  # error
    ("get_punches", {"employee_id": "E999", "date": "2026-04-13"}),  # error
]


def test_no_tool_writes_anything(demo):
    assert {name for name, _ in CALLS} == set(TOOLS)  # every tool is covered
    before = every_table(demo)
    r = runner(demo)
    results = [r.run(name, args) for name, args in CALLS]
    assert [x["ok"] for x in results].count(True) == len(CALLS) - 2
    assert every_table(demo) == before


def test_run_checks_on_amit_reports_p3_and_leaves_the_db_identical(demo):
    before = every_table(demo)
    out = runner(demo).run(
        "run_checks", change("E001", "2026-04-14", "set_clock_out", timestamp="2026-04-14T19:30")
    )
    assert "P3" in {f["policy_id"] for f in out["new_violations"]}
    assert every_table(demo) == before


def test_postgres_refuses_writes_in_the_tool_session(demo):
    with pytest.raises(DBAPIError, match="read-only transaction"):
        with read_only_session(factory(demo)) as s:
            s.execute(text("UPDATE timecards SET voided = true"))


def test_orm_flush_is_blocked_in_the_tool_session(demo):
    with pytest.raises(ReadOnlyViolation):
        with read_only_session(factory(demo)) as s:
            s.get(PunchRow, "P0001").voided = True
            s.flush()
    with session_for(demo) as s:
        assert s.get(PunchRow, "P0001").voided is False


def test_read_only_session_never_commits(demo):
    with read_only_session(factory(demo)) as s:
        assert s.execute(text("SHOW transaction_read_only")).scalar_one() == "on"
        assert s.scalars(select(ExceptionRow.id)).first() is not None


# ---------------------------------------------------------------- parity with the real writer


def _after_approval(client, employee_id: str, day: str) -> set[str]:
    """Open exception IDs the engine finds on the DB for that worker's week."""
    from attendflow.db.dataset import load_dataset_from_db

    wk = week_start(date.fromisoformat(day))
    with session_for(client) as s:
        ds = load_dataset_from_db(s)
    return {
        e.exception_id
        for e in run_engine(ds, POLICY, AS_OF).exceptions
        if e.employee_id == employee_id
        and e.status == "open"
        and wk <= e.date < wk + timedelta(days=7)
    }


def _predicted(client, employee_id: str, day: str, action: str, params: dict) -> set[str]:
    out = runner(client).run("run_checks", change(employee_id, day, action, **params))
    assert out["ok"], out
    ids = {(f["policy_id"], f["date"]) for f in out["new_violations"] + out["still_open"]}
    return ids


def _ids_as_pairs(ids: set[str]) -> set[tuple[str, str]]:
    return {(i.split("-")[0], "-".join(i.split("-")[2:5])) for i in ids}


@pytest.mark.parametrize(
    "exception_id,option_id,employee_id,day,confirm",
    [
        ("P1-E001-2026-04-14", "set_clock_out_to_scheduled_end", "E001", "2026-04-14", None),
        (MEENA_P5, "reduce_upcoming_shifts", "E002", "2026-04-16", None),
        (MEENA_P3_MON, "correct_clock_out", "E002", "2026-04-13", {"X-Actor-Id": "E002"}),
        ("P4-E004-2026-04-13", "record_break", "E004", "2026-04-13", {"X-Actor-Id": "E004"}),
    ],
)
def test_run_checks_predicts_what_the_real_fix_gives(
    demo, exception_id, option_id, employee_id, day, confirm
):
    exc = demo.get(f"/api/exceptions/{exception_id}").json()
    option = next(o for o in exc["fix_options"] if o["option_id"] == option_id)
    predicted = _predicted(demo, employee_id, day, option["action"], option["params"])

    if confirm:
        assert post(demo, exception_id, "ask-worker", {}, RAVI).status_code == 200
        assert (
            post(demo, exception_id, "worker-reply", {"confirmed": True}, confirm).status_code
            == 200
        )
    r = post(demo, exception_id, "approve", {"option_id": option_id}, RAVI)
    assert r.status_code == 200, r.text

    assert _ids_as_pairs(_after_approval(demo, employee_id, day)) == predicted
