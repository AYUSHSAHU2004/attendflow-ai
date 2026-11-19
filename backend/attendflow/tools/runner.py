"""ToolRunner: validate the arguments, load the data read-only, call the tool, and report
the call to an optional callback (Phase 5 uses it to write the tool_calls table).

A tool call never raises: bad JSON, an unknown tool, invalid arguments or a tool error all
come back as {"ok": false, "error": {code, message, hint}}.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from attendflow.data.loader import Dataset
from attendflow.db.dataset import load_dataset_from_db
from attendflow.policy.models import PolicyConfig
from attendflow.tools.context import ToolContext, read_only_session
from attendflow.tools.models import ToolError, ToolErrorResult, ToolInputError
from attendflow.tools.registry import TOOLS

log = logging.getLogger("attendflow.tools")


@dataclass(frozen=True)
class ToolCallEvent:
    name: str
    arguments: dict[str, Any] | str  # the raw string when it was not valid JSON
    output: dict[str, Any]
    ok: bool
    duration_ms: float


OnCall = Callable[[ToolCallEvent], None]


def _error(code: str, message: str, hint: str | None = None) -> dict[str, Any]:
    return ToolErrorResult(error=ToolError(code=code, message=message, hint=hint)).model_dump(
        exclude_none=True
    )


def _validation_message(exc: ValidationError) -> str:
    parts = []
    for e in exc.errors()[:4]:
        loc = ".".join(str(p) for p in e["loc"])
        parts.append(f"{loc}: {e['msg']}" if loc else e["msg"])
    return "; ".join(parts)


class ToolRunner:
    """Runs tools by name. `load_dataset` supplies the data for each call: the database
    version (for_database) opens a READ ONLY transaction, reads, and closes it before the
    tool runs, so tools only ever see an in-memory copy."""

    def __init__(
        self,
        load_dataset: Callable[[], Dataset],
        policy: PolicyConfig,
        policy_text: dict[str, str],
        as_of: datetime,
        on_call: OnCall | None = None,
    ):
        self._load = load_dataset
        self.policy = policy
        self.policy_text = policy_text
        self.as_of = as_of
        self.on_call = on_call

    @classmethod
    def for_database(
        cls,
        session_factory: sessionmaker[Session],
        policy: PolicyConfig,
        policy_text: dict[str, str],
        as_of: datetime,
        on_call: OnCall | None = None,
    ) -> ToolRunner:
        def load() -> Dataset:
            with read_only_session(session_factory) as session:
                return load_dataset_from_db(session)

        return cls(load, policy, policy_text, as_of, on_call)

    def run(self, name: str, arguments: str | dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        args: dict[str, Any] | str = arguments
        output = self._run(name, arguments)
        if isinstance(arguments, str):
            try:
                args = json.loads(arguments)
            except ValueError:
                args = arguments
        event = ToolCallEvent(
            name=name,
            arguments=args,
            output=output,
            ok=bool(output.get("ok")),
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        log.info(
            "tool call",
            extra={"event": "tool_call", "tool": name, "ok": event.ok, "ms": event.duration_ms},
        )
        if self.on_call is not None:
            try:
                self.on_call(event)
            except Exception:  # noqa: BLE001 - logging must never break the agent loop
                log.exception("tool call callback failed", extra={"tool": name})
        return output

    def _run(self, name: str, arguments: str | dict[str, Any]) -> dict[str, Any]:
        tool = TOOLS.get(name)
        if tool is None:
            return _error("unknown_tool", f"no tool named {name!r}", f"tools: {', '.join(TOOLS)}")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments or "{}")
            except ValueError as exc:
                return _error("invalid_json", f"arguments are not valid JSON: {exc}")
        if not isinstance(arguments, dict):
            return _error("invalid_arguments", "arguments must be a JSON object")
        try:
            args = tool.input_model.model_validate(arguments)
        except ValidationError as exc:
            return _error(
                "invalid_arguments", _validation_message(exc), "check the tool's parameter schema"
            )
        try:
            ctx = ToolContext(self._load(), self.policy, self.policy_text, self.as_of)
            result = tool.fn(ctx, args)
        except ToolInputError as exc:
            return {"ok": False, "error": exc.error.model_dump(exclude_none=True)}
        except ValidationError as exc:  # e.g. a simulated row that is not valid
            return _error("invalid_change", _validation_message(exc))
        except Exception:  # noqa: BLE001 - an agent must get an answer, never a crash
            log.exception("tool failed", extra={"tool": name})
            return _error("internal_error", f"{name} failed; try another tool or ask a human")
        return result.model_dump(mode="json", exclude_none=True)
