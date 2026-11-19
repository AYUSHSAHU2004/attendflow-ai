"""The tool registry: OpenAI function-calling format, schemas generated from the Pydantic
models (so they cannot drift), and a static guard that the tools package cannot write."""

from __future__ import annotations

import ast
import json

import pytest

from attendflow.config import REPO_ROOT
from attendflow.tools import TOOLS, openai_tools
from attendflow.tools.registry import flatten_schema

TOOLS_DIR = REPO_ROOT / "backend" / "attendflow" / "tools"


def _walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def test_openai_format():
    specs = openai_tools()
    assert [s["function"]["name"] for s in specs] == list(TOOLS)
    assert len(set(TOOLS)) == 6
    for spec in specs:
        assert set(spec) == {"type", "function"} and spec["type"] == "function"
        fn = spec["function"]
        assert set(fn) == {"name", "description", "parameters"}
        assert fn["parameters"]["type"] == "object"
        assert fn["parameters"]["additionalProperties"] is False
        json.dumps(spec)  # serialisable as-is


@pytest.mark.parametrize("name", list(TOOLS))
def test_schema_matches_the_pydantic_model(name):
    tool = TOOLS[name]
    spec = next(s for s in openai_tools() if s["function"]["name"] == name)
    assert spec["function"]["parameters"] == flatten_schema(tool.input_model.model_json_schema())
    required = set(spec["function"]["parameters"]["required"])
    model_required = {n for n, f in tool.input_model.model_fields.items() if f.is_required()}
    assert required == model_required


@pytest.mark.parametrize("name", list(TOOLS))
def test_schema_is_flat_and_self_describing(name):
    params = TOOLS[name].parameters()
    for node in _walk(params):
        assert "$ref" not in node and "$defs" not in node and "discriminator" not in node
    for prop, schema in params["properties"].items():
        assert schema.get("description"), f"{name}.{prop} needs a description for the model"


@pytest.mark.parametrize("name", list(TOOLS))
def test_descriptions_are_short(name):
    desc = TOOLS[name].description
    assert 40 <= len(desc) <= 260
    assert desc.count(". ") <= 1  # one or two sentences


def test_run_checks_accepts_the_fix_option_actions():
    schema = TOOLS["run_checks"].parameters()
    variants = schema["properties"]["proposed_change"]["oneOf"]
    actions = {v["properties"]["action"]["const"] for v in variants}
    assert {
        "set_clock_out",
        "correct_clock_out",
        "add_break",
        "move_shift",
        "reduce_scheduled_hours",
        "record_leave",
        "cancel_leave",
    } <= actions


# ---------------------------------------------------------------- static read-only guard

FORBIDDEN_MODULES = (
    "attendflow.fixes.apply",
    "attendflow.cases",
    "attendflow.db.seed",
    "attendflow.db.models",
)
FORBIDDEN_CALLS = (".add(", ".delete(", ".commit(", ".merge(", "insert(", "update(")


def test_tools_never_import_a_writer():
    for path in TOOLS_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            for name in names:
                assert not name.startswith(FORBIDDEN_MODULES), f"{path.name} imports {name}"


def test_tools_never_call_write_methods():
    for path in TOOLS_DIR.glob("*.py"):
        src = path.read_text(encoding="utf-8")
        for call in FORBIDDEN_CALLS:
            assert call not in src, f"{path.name} contains {call!r}"
