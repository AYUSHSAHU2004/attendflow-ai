"""Chat and model discovery for OpenAI-compatible endpoints."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from math import isfinite
from typing import Any
from urllib.parse import urlsplit

from openai import APIStatusError, OpenAI, OpenAIError
from pydantic import BaseModel, Field, ValidationError

from attendflow.config import Settings


class LLMError(RuntimeError):
    """Any failure talking to the model. Callers fall back to non-LLM behaviour."""


@dataclass(frozen=True)
class LLMReply:
    text: str
    model: str
    latency_ms: int
    prompt_tokens: int | None
    completion_tokens: int | None


class ToolRequest(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    arguments: str

    def as_message_call(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments},
        }


class ChatMessage(BaseModel):
    text: str | None = None
    tool_calls: list[ToolRequest] = Field(default_factory=list)


def _retry_after(exc: APIStatusError) -> float:
    value = exc.response.headers.get("retry-after")
    if not value:
        return 0
    try:
        delay = float(value)
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
        except (ValueError, OverflowError):
            return 0
        if date.tzinfo is None:
            date = date.replace(tzinfo=UTC)
        delay = (date - datetime.now(UTC)).total_seconds()
    return max(0, delay) if isfinite(delay) else 0


def _provider_message(
    exc: APIStatusError, settings: Settings, messages: list[dict[str, Any]]
) -> str:
    # Read just the provider's diagnostic. SDK exception strings include the whole body.
    try:
        body = exc.response.json()
    except ValueError:
        return ""
    error = body.get("error") if isinstance(body, dict) else None
    message = error.get("message") if isinstance(error, dict) else None
    if not isinstance(message, str):
        return ""

    secrets = [settings.llm_api_key, *(item.get("content") for item in messages)]
    for secret in sorted(
        {value for value in secrets if isinstance(value, str) and value}, key=len, reverse=True
    ):
        for form in {
            secret,
            json.dumps(secret)[1:-1],
            json.dumps(secret, ensure_ascii=False)[1:-1],
        }:
            message = message.replace(form, "[redacted]")
    return " ".join(message.splitlines()).strip()


def _http_error(
    summary: str, exc: APIStatusError, settings: Settings, messages: list[dict[str, Any]]
) -> LLMError:
    diagnostic = _provider_message(exc, settings, messages)
    error = f"{summary} (HTTP {exc.status_code})"
    return LLMError(f"{error}: {diagnostic}" if diagnostic else error)


def _chat_completion(settings: Settings, messages: list[dict[str, Any]], **options: Any):
    client = _client(settings)
    for attempt in range(3):
        try:
            return client.chat.completions.create(
                model=settings.llm_model, messages=messages, **options
            )
        except APIStatusError as exc:
            status = exc.status_code
            if attempt == 2 or not (status == 429 or 500 <= status < 600):
                raise _http_error("chat request failed", exc, settings, messages) from None
            delay = max(2**attempt, _retry_after(exc))
            if delay > 60:
                raise _http_error(
                    "chat retry exceeds the 60-second limit", exc, settings, messages
                ) from None
            time.sleep(delay)
        except OpenAIError as exc:
            raise LLMError(f"chat request failed ({type(exc).__name__})") from None


def chat(
    settings: Settings,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    required_tool: str | None = None,
) -> ChatMessage:
    options: dict[str, Any] = {"tools": tools, "max_completion_tokens": 1024}
    if required_tool is not None:
        options["tool_choice"] = {"type": "function", "function": {"name": required_tool}}
    if settings.llm_reasoning_effort != "off":
        options["reasoning_effort"] = settings.llm_reasoning_effort
    if urlsplit(settings.llm_base_url).hostname == "api.groq.com" and settings.llm_model.startswith(
        "openai/gpt-oss-"
    ):
        options["extra_body"] = {"reasoning_format": "hidden"}
    response = _chat_completion(settings, messages, **options)
    if not response.choices:
        raise LLMError("model returned no choices")
    choice = response.choices[0]
    if choice.finish_reason not in {"stop", "tool_calls"}:
        raise LLMError("model response did not complete")
    message = choice.message
    try:
        calls = []
        for call in message.tool_calls or []:
            if call.type != "function":
                raise LLMError("model returned an unsupported tool call type")
            calls.append(
                ToolRequest(id=call.id, name=call.function.name, arguments=call.function.arguments)
            )
        reply = ChatMessage(text=message.content, tool_calls=calls)
    except ValidationError:
        raise LLMError("model returned an invalid message") from None
    if len({call.id for call in calls}) != len(calls):
        raise LLMError("model returned duplicate tool call IDs")
    if not calls and not (reply.text or "").strip():
        raise LLMError("model returned an empty reply")
    return reply


def _client(settings: Settings) -> OpenAI:
    if not settings.llm_api_key:
        raise LLMError("LLM_API_KEY is not set. Copy .env.example to .env and add your key.")
    return OpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout_seconds,
        max_retries=0,
    )


def chat_once(
    settings: Settings, prompt: str, system: str | None = None, temperature: float = 0.2
) -> LLMReply:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    started = time.perf_counter()
    resp = _chat_completion(settings, messages, temperature=temperature)
    latency_ms = int((time.perf_counter() - started) * 1000)

    text = (resp.choices[0].message.content or "").strip() if resp.choices else ""
    if not text:
        raise LLMError("model returned an empty reply")
    usage = resp.usage
    return LLMReply(
        text=text,
        model=resp.model,
        latency_ms=latency_ms,
        prompt_tokens=usage.prompt_tokens if usage else None,
        completion_tokens=usage.completion_tokens if usage else None,
    )


def list_models(settings: Settings) -> list[str]:
    try:
        return sorted(m.id for m in _client(settings).models.list())
    except APIStatusError as exc:
        raise _http_error("model listing failed", exc, settings, []) from None
    except OpenAIError as exc:
        raise LLMError(f"model listing failed ({type(exc).__name__})") from None
