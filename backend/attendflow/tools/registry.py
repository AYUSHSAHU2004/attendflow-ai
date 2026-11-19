"""Every tool with its name, LLM-facing description and JSON schema.

openai_tools() returns the list in the OpenAI-compatible function-calling format, ready to
pass as `tools=` to the chat endpoint (Groq). The parameter schemas are generated from
the Pydantic input models, flattened (no $ref) because some providers reject $ref.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from attendflow.tools.context import ToolContext
from attendflow.tools.models import (
    EmployeeDayIn,
    LeaveBalanceIn,
    LeaveBalanceOut,
    LeaveOut,
    PolicyIn,
    PolicyOut,
    PunchesOut,
    RunChecksIn,
    RunChecksOut,
    ScheduleOut,
)
from attendflow.tools.read_tools import (
    get_leave,
    get_leave_balance,
    get_policy,
    get_punches,
    get_schedule,
)
from attendflow.tools.run_checks import run_checks


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    fn: Callable[[ToolContext, Any], BaseModel]

    def parameters(self) -> dict[str, Any]:
        return flatten_schema(self.input_model.model_json_schema())

    def openai(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters(),
            },
        }


_TOOL_LIST = [
    Tool(
        "get_schedule",
        "Get a worker's scheduled shift on one date (start, end, planned hours) and whether "
        "the date is a holiday. Returns scheduled=false if there is no shift.",
        EmployeeDayIn,
        ScheduleOut,
        get_schedule,
    ),
    Tool(
        "get_leave",
        "Get a worker's approved or pending leave on one date (type, full or half day, "
        "status, certificate). Returns on_leave=false if there is none.",
        EmployeeDayIn,
        LeaveOut,
        get_leave,
    ),
    Tool(
        "get_leave_balance",
        "Get a worker's leave balance for one leave type this year: total, used, pending "
        "days and balance (total minus used).",
        LeaveBalanceIn,
        LeaveBalanceOut,
        get_leave_balance,
    ),
    Tool(
        "get_punches",
        "Get a worker's punches for one shift date, grouped into shifts with clock-in, "
        "clock-out, break minutes and worked hours. A night shift belongs to the date it started.",
        EmployeeDayIn,
        PunchesOut,
        get_punches,
    ),
    Tool(
        "get_policy",
        "Get the exact text of one attendance policy (P1 to P17) and its numeric limits. "
        "Quote this text when you explain a rule.",
        PolicyIn,
        PolicyOut,
        get_policy,
    ),
    Tool(
        "run_checks",
        "Test a proposed data change without saving it: re-runs every rule for that worker's "
        "week and returns the new violations it would cause and the ones it would resolve.",
        RunChecksIn,
        RunChecksOut,
        run_checks,
    ),
]

TOOLS: dict[str, Tool] = {t.name: t for t in _TOOL_LIST}


def openai_tools() -> list[dict[str, Any]]:
    return [t.openai() for t in _TOOL_LIST]


def flatten_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Inline every $ref, drop titles and the pydantic-only 'discriminator' keyword."""
    schema = copy.deepcopy(schema)
    defs = schema.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(x) for x in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            target = defs[node["$ref"].rsplit("/", 1)[-1]]
            extra = {k: v for k, v in node.items() if k != "$ref"}
            return walk({**copy.deepcopy(target), **extra})
        out = {}
        for key, value in node.items():
            if key == "discriminator" or (key == "title" and isinstance(value, str)):
                continue
            if key == "properties":
                out[key] = {name: walk(prop) for name, prop in value.items()}
            else:
                out[key] = walk(value)
        return out

    return walk(schema)
