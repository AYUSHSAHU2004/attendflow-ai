"""The read-only agent tools on the demo data (CSV, no database needed)."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from attendflow.policy import load_policy
from attendflow.policy.models import load_policy_text
from attendflow.tools import ToolCallEvent, ToolRunner
from tests.conftest import DATA_DIR

AS_OF = datetime(2026, 4, 16, 8, 0)
POLICY = load_policy(DATA_DIR / "policy.json")
TEXT = load_policy_text(DATA_DIR / "policy.md")
# Output budgets (JSON characters) for the model's small context window.
MAX_CHARS = {"get_policy": 2000, "run_checks": 1200}
DEFAULT_MAX = 1000


@pytest.fixture
def runner(dataset):
    return ToolRunner(lambda: dataset, POLICY, TEXT, AS_OF)


def call(runner: ToolRunner, name: str, **args) -> dict:
    out = runner.run(name, args)
    size = len(json.dumps(out))
    assert size <= MAX_CHARS.get(name, DEFAULT_MAX), f"{name} output is {size} chars"
    return out


def ok(out: dict) -> dict:
    assert out["ok"] is True, out
    return out


def err(out: dict, code: str) -> dict:
    assert out["ok"] is False, out
    assert out["error"]["code"] == code, out
    assert out["error"]["message"]
    return out["error"]


def change(employee_id: str, day: str, action: str, **params) -> dict:
    return {
        "employee_id": employee_id,
        "date": day,
        "proposed_change": {"action": action, "params": params},
    }


# ---------------------------------------------------------------- get_schedule


def test_schedule_amit_holiday_duty(runner):
    out = ok(call(runner, "get_schedule", employee_id="E001", date="2026-04-14"))
    assert (out["start"], out["end"], out["planned_hours"]) == ("09:00", "18:00", 8.0)
    assert out["holiday"] == "Ambedkar Jayanti (national)"
    assert out["ends_next_day"] is False


def test_schedule_meena_short_thursday(runner):
    out = ok(call(runner, "get_schedule", employee_id="E002", date="2026-04-16"))
    assert (out["start"], out["end"], out["planned_hours"]) == ("09:00", "15:00", 6.0)


def test_schedule_not_scheduled(runner):
    out = ok(call(runner, "get_schedule", employee_id="E001", date="2026-04-18"))
    assert out["scheduled"] is False and out["note"] == "not scheduled"
    assert "start" not in out  # empty fields are left out to keep it short


def test_schedule_night_shift_ends_next_day(runner):
    out = ok(call(runner, "get_schedule", employee_id="E003", date="2026-04-13"))
    assert out["ends_next_day"] is True and out["end"] == "06:00"


# ---------------------------------------------------------------- get_leave


def test_leave_dev_pending_sick_without_certificate(runner):
    out = ok(call(runner, "get_leave", employee_id="E007", date="2026-04-16"))
    assert out["on_leave"] is True
    assert (out["leave_type"], out["duration"], out["status"], out["certificate"]) == (
        "sick",
        "full",
        "pending",
        False,
    )


def test_leave_none_for_amit(runner):
    out = ok(call(runner, "get_leave", employee_id="E001", date="2026-04-14"))
    assert out == {
        "ok": True,
        "employee_id": "E001",
        "date": "2026-04-14",
        "on_leave": False,
        "note": "no leave",
    }


def test_leave_karan_on_leave_day(runner):
    out = ok(call(runner, "get_leave", employee_id="E006", date="2026-04-15"))
    assert out["on_leave"] is True and out["status"] == "approved"


# ---------------------------------------------------------------- get_leave_balance


def test_balance_dev_sick_is_computed(runner):
    out = ok(call(runner, "get_leave_balance", employee_id="E007", leave_type="sick"))
    assert out["total_per_year"] == 12 and out["used"] == 11
    assert out["balance"] == 1 and out["pending_days"] == 3
    assert out["balance_after_pending"] == -2 and out["year"] == 2026


def test_balance_unknown_type_is_an_argument_error(runner):
    e = err(
        call(runner, "get_leave_balance", employee_id="E007", leave_type="vacation"),
        "invalid_arguments",
    )
    assert "leave_type" in e["message"]


def test_balance_for_a_supervisor_without_one(runner):
    err(call(runner, "get_leave_balance", employee_id="E101", leave_type="sick"), "no_balance")


# ---------------------------------------------------------------- get_punches


def test_punches_amit_missing_clock_out(runner):
    out = ok(call(runner, "get_punches", employee_id="E001", date="2026-04-14"))
    [shift] = out["shifts"]
    assert shift["status"] == "missing_out" and shift["clock_in"] == "09:00"
    assert "clock_out" not in shift and "worked_hours" not in shift
    assert shift["break_minutes"] == 60
    assert [(p["id"], p["time"], p["type"]) for p in shift["punches"]] == [
        ("P0037", "09:00", "in"),
        ("P0040", "13:00", "break_start"),
        ("P0042", "14:00", "break_end"),
    ]


def test_punches_meena_twelve_hour_day(runner):
    out = ok(call(runner, "get_punches", employee_id="E002", date="2026-04-13"))
    [shift] = out["shifts"]
    assert (shift["clock_in"], shift["clock_out"], shift["worked_hours"]) == (
        "07:00",
        "19:30",
        12.0,
    )
    assert shift["scheduled"] == "07:00-19:30"


def test_punches_neha_no_break(runner):
    [shift] = ok(call(runner, "get_punches", employee_id="E004", date="2026-04-13"))["shifts"]
    assert shift["break_minutes"] == 0 and shift["worked_hours"] == 6.0


def test_punches_karan_late(runner):
    [shift] = ok(call(runner, "get_punches", employee_id="E006", date="2026-04-13"))["shifts"]
    assert shift["clock_in"] == "10:30" and shift["scheduled"] == "09:00-18:00"


def test_punches_night_shift_belongs_to_its_start_date(runner):
    [shift] = ok(call(runner, "get_punches", employee_id="E003", date="2026-04-13"))["shifts"]
    assert shift["clock_out"].startswith("2026-04-14 ")  # shown with its date
    tue = ok(call(runner, "get_punches", employee_id="E003", date="2026-04-14"))
    assert all(
        not p["time"].startswith("2026-04-14 0") for s in tue["shifts"] for p in s["punches"]
    )


def test_punches_shows_an_unvoided_duplicate_tap(runner):
    [shift] = ok(call(runner, "get_punches", employee_id="E005", date="2026-04-13"))["shifts"]
    dupes = [p for p in shift["punches"] if p.get("duplicate")]
    assert [p["id"] for p in dupes] == ["P0005"]


def test_punches_dev_on_sick_leave_has_none(runner):
    out = ok(call(runner, "get_punches", employee_id="E007", date="2026-04-14"))
    assert out["shifts"] == [] and out["note"] == "no punches for this shift date"


def test_punches_after_now(runner):
    out = ok(call(runner, "get_punches", employee_id="E001", date="2026-04-17"))
    assert out["shifts"] == [] and "after now" in out["note"]


def test_punches_for_a_supervisor(runner):
    out = ok(call(runner, "get_punches", employee_id="E101", date="2026-04-14"))
    assert "only workers punch" in out["note"]


# ---------------------------------------------------------------- get_policy


def test_policy_returns_the_real_section_and_limits(runner):
    out = ok(call(runner, "get_policy", policy_id="P3"))
    assert out["title"] == "Maximum hours per day"
    assert out["text"] == TEXT["P3"]  # word for word
    assert out["text"].startswith("## P3:") and "## P4" not in out["text"]
    assert out["limits"] == {"max_hours_per_day": 9}


@pytest.mark.parametrize("given", ["p3", "P03", " P3 "])
def test_policy_id_is_forgiving(runner, given):
    assert ok(call(runner, "get_policy", policy_id=given))["policy_id"] == "P3"


@pytest.mark.parametrize("pid", sorted(POLICY.policies))
def test_every_policy_fits_the_budget(runner, pid):
    ok(call(runner, "get_policy", policy_id=pid))


@pytest.mark.parametrize("pid", ["P99", "P0", "PX"])
def test_policy_unknown_id(runner, pid):
    e = err(call(runner, "get_policy", policy_id=pid), "unknown_policy")
    assert "P17" in e["hint"]


# ---------------------------------------------------------------- bad input (all tools)


@pytest.mark.parametrize("name", ["get_schedule", "get_leave", "get_punches"])
def test_unknown_employee(runner, name):
    e = err(call(runner, name, employee_id="E999", date="2026-04-14"), "unknown_employee")
    assert "E001" in e["hint"]


@pytest.mark.parametrize(
    "args",
    [
        {"employee_id": "E001", "date": "2026-02-30"},  # impossible date
        {"employee_id": "E001", "date": "14/04/2026"},  # wrong format
        {"employee_id": "Amit", "date": "2026-04-14"},  # a name, not an ID
        {"employee_id": "E001"},  # missing date
        {"employee_id": "E001", "date": "2026-04-14", "extra": 1},  # unknown field
    ],
)
def test_bad_arguments_are_results_not_exceptions(runner, args):
    err(runner.run("get_punches", args), "invalid_arguments")


def test_unknown_tool_and_bad_json(runner):
    e = err(runner.run("delete_everything", {}), "unknown_tool")
    assert "get_punches" in e["hint"]
    err(runner.run("get_schedule", "{not json"), "invalid_json")
    err(runner.run("get_schedule", "[1, 2]"), "invalid_arguments")


def test_json_string_arguments_work(runner):
    ok(runner.run("get_schedule", '{"employee_id": "E001", "date": "2026-04-14"}'))


def test_an_unexpected_error_is_a_result(dataset):
    def broken():
        raise RuntimeError("database fell over")

    out = ToolRunner(broken, POLICY, TEXT, AS_OF).run("get_policy", {"policy_id": "P3"})
    err(out, "internal_error")


# ---------------------------------------------------------------- the logging hook


def test_on_call_gets_every_call(dataset):
    events: list[ToolCallEvent] = []
    r = ToolRunner(lambda: dataset, POLICY, TEXT, AS_OF, on_call=events.append)
    r.run("get_schedule", {"employee_id": "E001", "date": "2026-04-14"})
    r.run("get_schedule", "{bad")
    assert [(e.name, e.ok) for e in events] == [("get_schedule", True), ("get_schedule", False)]
    assert events[0].arguments == {"employee_id": "E001", "date": "2026-04-14"}
    assert events[0].output["start"] == "09:00" and events[0].duration_ms >= 0
    assert events[1].arguments == "{bad"


def test_a_failing_callback_never_breaks_the_tool(dataset):
    def boom(_event):
        raise RuntimeError("log table down")

    r = ToolRunner(lambda: dataset, POLICY, TEXT, AS_OF, on_call=boom)
    ok(r.run("get_policy", {"policy_id": "P1"}))


# ---------------------------------------------------------------- run_checks


def test_run_checks_amit_leaves_at_six(runner):
    out = ok(
        call(
            runner,
            "run_checks",
            **change("E001", "2026-04-14", "set_clock_out", timestamp="2026-04-14T18:00"),
        )
    )
    assert out["new_violations"] == []
    assert out["verdict"].startswith("no new violations")
    assert [(f["policy_id"], f["date"]) for f in out["resolved"]] == [("P1", "2026-04-14")]
    assert out["day_worked_hours"] == 8 and out["week_projected_hours"] == 40


def test_run_checks_amit_leaves_at_seven_thirty(runner, dataset):
    out = ok(
        call(
            runner,
            "run_checks",
            **change("E001", "2026-04-14", "set_clock_out", timestamp="2026-04-14T19:30"),
        )
    )
    new = {f["policy_id"]: f for f in out["new_violations"]}
    assert set(new) == {"P3", "P5"}
    # Whatever the engine computes after his 60 min lunch (10.5 h span - 1 h).
    worked = new["P3"]["numbers"]["worked_hours"]
    assert worked == out["day_worked_hours"] and worked > 9
    assert new["P3"]["numbers"]["max_hours_per_day"] == 9
    assert new["P5"]["numbers"]["projected_hours"] == out["week_projected_hours"] > 40


def test_run_checks_never_changes_the_dataset(runner, dataset):
    before = (
        list(dataset.punches),
        list(dataset.schedule),
        list(dataset.leave_records),
        list(dataset.leave_balances),
    )
    call(
        runner,
        "run_checks",
        **change("E001", "2026-04-14", "set_clock_out", timestamp="2026-04-14T19:30"),
    )
    out = call(
        runner,
        "run_checks",
        **change(
            "E007", "2026-04-16", "cancel_leave", date="2026-04-16", leave_type="sick", days=1
        ),
    )
    assert out["ok"], out
    assert before == (
        dataset.punches,
        dataset.schedule,
        dataset.leave_records,
        dataset.leave_balances,
    )


def test_run_checks_meena_shorter_thursday_and_friday(runner):
    cuts = [
        {"date": "2026-04-17", "scheduled_hours": 6, "new_hours": 0},
        {"date": "2026-04-16", "scheduled_hours": 6, "new_hours": 4},
    ]
    out = ok(
        call(
            runner,
            "run_checks",
            **change("E002", "2026-04-16", "reduce_scheduled_hours", cuts=cuts),
        )
    )
    assert out["week_projected_hours"] <= 40
    assert ("P5", "2026-04-13") in [(f["policy_id"], f["date"]) for f in out["resolved"]]
    assert out["new_violations"] == []


def test_run_checks_meena_partial_cut_keeps_p5_with_new_numbers(runner):
    cuts = [{"date": "2026-04-17", "scheduled_hours": 6, "new_hours": 0}]
    out = ok(
        call(
            runner,
            "run_checks",
            **change("E002", "2026-04-17", "reduce_scheduled_hours", cuts=cuts),
        )
    )
    p5 = next(f for f in out["still_open"] if f["policy_id"] == "P5")
    assert "42 h" in p5["reason"] and out["week_projected_hours"] == 42


def test_run_checks_meena_clock_out_at_the_limit(runner):
    out = ok(
        call(
            runner,
            "run_checks",
            **change(
                "E002",
                "2026-04-13",
                "correct_clock_out",
                punch_id="P0031",
                timestamp="2026-04-13T16:29:47",
            ),
        )
    )
    assert ("P3", "2026-04-13") in [(f["policy_id"], f["date"]) for f in out["resolved"]]
    assert out["day_worked_hours"] == 9


def test_run_checks_neha_break(runner):
    out = ok(
        call(
            runner,
            "run_checks",
            **change(
                "E004",
                "2026-04-13",
                "add_break",
                break_start="2026-04-13T12:00",
                break_end="2026-04-13T12:30",
            ),
        )
    )
    assert [f["policy_id"] for f in out["resolved"]] == ["P4"]
    assert out["day_worked_hours"] == 5.5


def test_run_checks_dev_record_leave_needs_balance(runner):
    out = call(
        runner,
        "run_checks",
        **change(
            "E007", "2026-04-17", "record_leave", date="2026-04-18", leave_type="sick", days=1
        ),
    )
    assert ok(out)["new_violations"] == []  # 1 sick day left: allowed
    out = call(
        runner,
        "run_checks",
        **change(
            "E007", "2026-04-17", "record_leave", date="2026-04-18", leave_type="earned", days=5
        ),
    )
    err(out, "invalid_arguments")  # days must be <= 1


@pytest.mark.parametrize(
    "args,code",
    [
        (
            change("E001", "2026-04-14", "set_clock_out", timestamp="2026-04-17T19:30"),
            "punch_in_future",
        ),
        (
            change("E001", "2026-04-14", "set_clock_out", timestamp="2026-04-14T08:00"),
            "punch_outside_shift",
        ),
        (
            change("E001", "2026-04-14", "set_clock_out", timestamp="2026-04-14T25:00"),
            "invalid_arguments",
        ),
        (
            change(
                "E002",
                "2026-04-13",
                "correct_clock_out",
                punch_id="P0001",
                timestamp="2026-04-13T16:00",
            ),
            "wrong_punch_type",
        ),
        (change("E002", "2026-04-13", "void_punches", punch_ids=["P0037"]), "unknown_punch"),
        (
            change(
                "E002",
                "2026-04-13",
                "move_shift",
                date="2026-04-13",
                current_start="07:00",
                current_end="19:30",
                new_start="08:00",
                new_end="20:30",
            ),
            "shift_not_upcoming",
        ),
        (
            change(
                "E002",
                "2026-04-16",
                "move_shift",
                date="2026-04-17",
                current_start="07:00",
                current_end="13:00",
                new_start="10:00",
                new_end="16:00",
            ),
            "stale_change",
        ),
        (
            change(
                "E001",
                "2026-04-13",
                "add_break",
                break_start="2026-04-13T13:30",
                break_end="2026-04-13T14:30",
            ),
            "break_overlaps",
        ),
        (change("E001", "2026-04-14", "pay_double"), "invalid_arguments"),
        (
            change("E101", "2026-04-14", "set_clock_out", timestamp="2026-04-14T18:00"),
            "not_a_worker",
        ),
    ],
)
def test_run_checks_bad_changes_are_error_results(runner, args, code):
    err(call(runner, "run_checks", **args), code)


def test_run_checks_move_shift_resolves_a_synthetic_p6():
    from tests.engine_helpers import day_shift, make_dataset

    data = make_dataset(
        day_shift("2026-04-15", "14:00", "23:00", ("18:00", "19:00")),
        [("2026-04-15", "14:00", "23:00"), ("2026-04-16", "07:00", "16:00")],
    )
    r = ToolRunner(lambda: data, POLICY, TEXT, datetime(2026, 4, 16, 1, 0))
    out = ok(
        r.run(
            "run_checks",
            change(
                "E001",
                "2026-04-16",
                "move_shift",
                date="2026-04-16",
                current_start="07:00",
                current_end="16:00",
                new_start="10:00",
                new_end="19:00",
            ),
        )
    )
    assert [f["policy_id"] for f in out["resolved"]] == ["P6"]
    assert out["new_violations"] == []
