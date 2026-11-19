from datetime import datetime
from types import SimpleNamespace

import pytest
from openai import APIConnectionError

from attendflow.config import Settings, get_settings, parse_local_timestamp
from attendflow.llm import LLMError, chat_once
from attendflow.llm import client as llm_client


def make_settings(**overrides) -> Settings:
    base = dict(
        data_dir=None,
        as_of=datetime(2026, 4, 16, 8),
        llm_base_url="http://example.invalid/v1",
        llm_model="test-model",
        llm_api_key="test-key",
        llm_timeout_seconds=5.0,
    )
    return Settings(**{**base, **overrides})


def test_local_timestamp_rejects_timezone():
    assert parse_local_timestamp("2026-04-16T08:00:00") == datetime(2026, 4, 16, 8)
    with pytest.raises(ValueError):
        parse_local_timestamp("2026-04-16T08:00:00+05:30")


def test_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("ATTENDFLOW_AS_OF", "2026-04-17T12:00:00")
    monkeypatch.setenv("LLM_MODEL", "some/model")
    monkeypatch.setenv("ATTENDFLOW_DATA_DIR", str(tmp_path))
    s = get_settings(env_file=None)
    assert s.as_of == datetime(2026, 4, 17, 12)
    assert s.llm_model == "some/model"
    assert s.data_dir == tmp_path


def test_missing_api_key_raises_llm_error():
    with pytest.raises(LLMError, match="LLM_API_KEY"):
        chat_once(make_settings(llm_api_key=None), "hi")


class FakeClient:
    def __init__(self, reply=None, exc=None):
        self.reply, self.exc = reply, exc
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.reply))],
            model="test-model",
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )


def test_chat_once_returns_reply(monkeypatch):
    fake = FakeClient(reply="  Hello there.  ")
    monkeypatch.setattr(llm_client, "_client", lambda s: fake)
    reply = chat_once(make_settings(), "hi", system="be brief")
    assert reply.text == "Hello there."
    assert reply.prompt_tokens == 10
    assert [m["role"] for m in fake.calls[0]["messages"]] == ["system", "user"]


def test_empty_reply_is_an_error(monkeypatch):
    monkeypatch.setattr(llm_client, "_client", lambda s: FakeClient(reply=""))
    with pytest.raises(LLMError, match="empty"):
        chat_once(make_settings(), "hi")


def test_provider_error_is_wrapped(monkeypatch):
    exc = APIConnectionError(request=SimpleNamespace(method="POST", url="x"))
    monkeypatch.setattr(llm_client, "_client", lambda s: FakeClient(exc=exc))
    with pytest.raises(LLMError, match="APIConnectionError"):
        chat_once(make_settings(), "hi")
