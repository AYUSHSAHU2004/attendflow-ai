import ast
import json
from copy import deepcopy
from dataclasses import replace

from sqlalchemy import event, select

from attendflow.agent.loop import run_investigation
from attendflow.db.models import AuditLogRow, ToolCallRow
from attendflow.db.session import make_session_factory
from attendflow.llm.client import ChatMessage, LLMError, ToolRequest
from tests.api_helpers import AMIT_P1, get, session_for
from tests.conftest import DATA_DIR
from tests.test_tools_db import every_table


class ScriptedModel:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.messages = []
        self.required_tools = []

    def __call__(self, settings, messages, tools, required_tool):
        self.messages.append(deepcopy(messages))
        self.required_tools.append(required_tool)
        assert {tool["function"]["name"] for tool in tools} >= {"get_schedule", "run_checks"}
        response = next(self.responses)
        if isinstance(response, LLMError):
            raise response
        return response


def call(name, arguments, call_id=None):
    return ToolRequest(
        id=call_id or name,
        name=name,
        arguments=arguments if isinstance(arguments, str) else json.dumps(arguments),
    )


def run(demo, settings, model):
    return run_investigation(
        AMIT_P1,
        settings=settings,
        sessions=make_session_factory(demo.app.state.engine),
        chat_model=model,
    )


def journal_rows(demo, result):
    with session_for(demo) as session:
        tools = session.scalars(
            select(ToolCallRow).where(ToolCallRow.run_id == result.run_id).order_by(ToolCallRow.id)
        ).all()
        audit = session.scalars(
            select(AuditLogRow).where(AuditLogRow.actor == "agent").order_by(AuditLogRow.id)
        ).all()
        audit = [row for row in audit if row.after["run_id"] == result.run_id]
    assert [row.action for row in audit] == ["investigation_started", "investigation_finished"]
    assert audit[-1].after["stop_reason"] == result.stop_reason
    assert audit[-1].after["steps"] == len(result.steps)
    assert audit[-1].after["missing_required_tools"] == list(result.missing_required_tools)
    assert audit[-1].after["tool_calls"] == len(tools) == result.tool_calls_made
    return tools


def case_args(case):
    return {"employee_id": case["employee_id"], "date": case["date"]}


def test_tools_feed_back_and_multiple_calls_and_runs_are_logged(demo, api_settings):
    case = get(demo, AMIT_P1)
    args = case_args(case)
    option = case["fix_options"][0]
    writes = []

    def record_write(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "TRUNCATE")):
            writes.append(statement)

    engine = demo.app.state.engine
    before = every_table(demo)
    event.listen(engine, "before_cursor_execute", record_write)
    try:
        for _ in range(2):
            model = ScriptedModel(
                ChatMessage(
                    tool_calls=[
                        call("get_schedule", args),
                        call("get_punches", args),
                        call("get_leave", args),
                        call("get_policy", {"policy_id": case["policy_id"]}),
                    ]
                ),
                ChatMessage(
                    tool_calls=[
                        call(
                            "run_checks",
                            {
                                **args,
                                "proposed_change": {
                                    "action": option["action"],
                                    "params": option["params"],
                                },
                            },
                        )
                    ]
                ),
                ChatMessage(text="Ask Amit to confirm the proposed clock-out."),
            )
            result = run(demo, api_settings, model)
            assert result.stop_reason == "final"
            assert result.final_text == "Ask Amit to confirm the proposed clock-out."
            assert len(result.steps) == 3
            assert result.missing_required_tools == ()
            assert model.required_tools == ["get_schedule", None, None]
            request = json.loads(model.messages[0][1]["content"])
            assert request["case"]["fix_options"][0]["params"] == option["params"]
            required_calls = request["required_before_run_checks_or_final"]
            assert required_calls[-1]["arguments"] == {"policy_id": case["policy_id"]}
            feedback = model.messages[1][-4:]
            assert [message["tool_call_id"] for message in feedback] == [
                item["tool"] for item in required_calls
            ]
            assert all(json.loads(message["content"])["ok"] for message in feedback)
            check = json.loads(model.messages[2][-1]["content"])
            assert check["ok"] and check["new_violations"] == []
            assert any(row["policy_id"] == case["policy_id"] for row in check["resolved"])
            rows = journal_rows(demo, result)
            assert [(row.step_no, row.call_no) for row in rows] == [
                (1, 1),
                (1, 2),
                (1, 3),
                (1, 4),
                (2, 1),
            ]
            assert all(row.ok and row.duration_ms >= 0 for row in rows)
            assert rows[-1].output == check
    finally:
        event.remove(engine, "before_cursor_execute", record_write)
    assert {statement.split()[2] for statement in writes} == {"tool_calls", "audit_log"}
    after = every_table(demo)
    assert len(after["tool_calls"]) == 10
    for name in before.keys() - {"audit_log", "tool_calls"}:
        assert before[name] == after[name]


def test_max_steps(demo, api_settings):
    args = case_args(get(demo, AMIT_P1))
    reply = ChatMessage(tool_calls=[call("get_schedule", args)])
    result = run(demo, replace(api_settings, agent_max_steps=2), ScriptedModel(reply, reply))
    assert result.stop_reason == "max_steps"
    assert result.final_text is None
    assert result.missing_required_tools == ("get_punches", "get_leave", "get_policy")
    assert [row.step_no for row in journal_rows(demo, result)] == [1, 2]


def test_bad_calls_are_logged_and_returned_to_model(demo, api_settings):
    model = ScriptedModel(
        ChatMessage(tool_calls=[call("made_up_tool", {}), call("get_punches", "{bad JSON")]),
        ChatMessage(text="Ask the supervisor to review."),
    )
    result = run(demo, api_settings, model)
    assert result.stop_reason == "final"
    feedback = [json.loads(message["content"]) for message in model.messages[1][-2:]]
    assert [output["error"]["code"] for output in feedback] == ["unknown_tool", "invalid_json"]
    rows = journal_rows(demo, result)
    assert all(row.ok is False for row in rows)
    assert [row.output for row in rows] == feedback
    assert rows[1].input == {"raw_arguments": "{bad JSON"}


def test_llm_error_closes_audit_and_preserves_completed_calls(demo, api_settings):
    args = case_args(get(demo, AMIT_P1))
    model = ScriptedModel(
        ChatMessage(tool_calls=[call("get_leave", args)]), LLMError("provider unavailable")
    )
    before = every_table(demo)
    result = run(demo, api_settings, model)
    assert result.stop_reason == "llm_error"
    assert result.final_text is None and result.steps[-1].error == "provider unavailable"
    assert [row.step_no for row in journal_rows(demo, result)] == [1]
    after = every_table(demo)
    for name in before.keys() - {"audit_log", "tool_calls"}:
        assert before[name] == after[name]


def test_agent_never_imports_fix_writer():
    package = DATA_DIR.parent / "backend" / "attendflow" / "agent"
    for source in package.rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                assert all(
                    not alias.name.startswith("attendflow.fixes.apply") for alias in node.names
                )
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("attendflow.fixes.apply")
                if node.module == "attendflow.fixes":
                    assert all(alias.name != "apply" for alias in node.names)


def test_early_simulation_and_incomplete_evidence_are_reported(demo, api_settings):
    case = get(demo, AMIT_P1)
    args = case_args(case)
    option = case["fix_options"][0]
    model = ScriptedModel(
        ChatMessage(
            tool_calls=[
                call("get_schedule", args),
                call("get_punches", "{bad JSON"),
                call("get_leave", {**args, "employee_id": "E002"}),
                call("get_policy", {"policy_id": "P2"}),
                call(
                    "run_checks",
                    {
                        **args,
                        "proposed_change": {"action": option["action"], "params": option["params"]},
                    },
                ),
            ]
        ),
        ChatMessage(text="Premature final answer"),
    )
    result = run(demo, api_settings, model)
    assert result.stop_reason == "final"
    assert result.missing_required_tools == ("get_punches", "get_leave", "get_policy")
    assert model.required_tools == ["get_schedule", "get_punches"]
    feedback = json.loads(model.messages[1][-1]["content"])
    assert feedback["error"]["code"] == "required_tools_missing"
    rows = journal_rows(demo, result)
    assert rows[-1].ok is False and rows[-1].output == feedback
