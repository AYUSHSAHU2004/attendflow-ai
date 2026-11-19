"""Thin wrapper over any OpenAI-compatible chat endpoint (Groq, Together, Ollama).

Phase 0 only needs a single round trip. Tool calling, Pydantic-validated outputs,
retry-once and template fallbacks are added in later phases on top of this.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from openai import OpenAI, OpenAIError

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


def _client(settings: Settings) -> OpenAI:
    if not settings.llm_api_key:
        raise LLMError("LLM_API_KEY is not set. Copy .env.example to .env and add your key.")
    # max_retries=1: one quick retry on network blips, then fail fast so the app can fall back.
    return OpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout_seconds,
        max_retries=1,
    )


def chat_once(
    settings: Settings, prompt: str, system: str | None = None, temperature: float = 0.2
) -> LLMReply:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    started = time.perf_counter()
    try:
        resp = _client(settings).chat.completions.create(
            model=settings.llm_model, messages=messages, temperature=temperature
        )
    except OpenAIError as exc:
        raise LLMError(f"{type(exc).__name__}: {exc}") from exc
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
    except OpenAIError as exc:
        raise LLMError(f"{type(exc).__name__}: {exc}") from exc
