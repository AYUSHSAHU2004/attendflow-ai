from types import SimpleNamespace

import httpx
import pytest
from openai import APIStatusError

from attendflow.llm import client
from tests.test_config_and_llm import make_settings


def fail(status, retry_after=None):
    request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    headers = {"Retry-After": retry_after} if retry_after else {}
    response = httpx.Response(status, request=request, headers=headers)
    return APIStatusError("private provider body", response=response, body=None)


def mock_responses(monkeypatch, *replies):
    pending = iter(replies)
    calls = []
    sleeps = []

    def create(**options):
        calls.append(options)
        result = next(pending)
        if isinstance(result, APIStatusError):
            raise result
        return SimpleNamespace(choices=[result])

    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(client, "_client", lambda settings: fake)
    monkeypatch.setattr(client.time, "sleep", sleeps.append)
    return calls, sleeps


def test_retry_honors_provider_delay_and_exponential_backoff(monkeypatch):
    tool = SimpleNamespace(
        type="function", id="tool1", function=SimpleNamespace(name="get_policy", arguments="{bad")
    )
    response = SimpleNamespace(
        finish_reason="tool_calls", message=SimpleNamespace(content=None, tool_calls=[tool])
    )
    calls, sleeps = mock_responses(monkeypatch, fail(429, "1.5"), fail(502), response)
    settings = make_settings(
        llm_base_url="https://api.groq.com/openai/v1", llm_model="openai/gpt-oss-120b"
    )
    message = client.chat(settings, [], [])
    assert message.tool_calls[0].arguments == "{bad"
    assert sleeps == [1.5, 2]
    assert len(calls) == 3
    assert all(call["reasoning_effort"] == "low" for call in calls)
    assert calls[0]["extra_body"] == {"reasoning_format": "hidden"}


def test_large_retry_after_stops_and_can_omit_reasoning(monkeypatch):
    calls, sleeps = mock_responses(monkeypatch, fail(429, "61"))
    with pytest.raises(client.LLMError, match="60-second limit"):
        client.chat(make_settings(llm_reasoning_effort="off"), [], [])
    assert sleeps == []
    assert "reasoning_effort" not in calls[0]
    assert "extra_body" not in calls[0]


def test_retries_are_bounded_and_provider_body_stays_private(monkeypatch):
    calls, sleeps = mock_responses(monkeypatch, fail(429), fail(429), fail(429))
    with pytest.raises(client.LLMError, match=r"^chat request failed \(HTTP 429\)$"):
        client.chat(make_settings(), [], [])
    assert len(calls) == 3
    assert sleeps == [1, 2]


def test_http_error_reports_provider_message_without_key_or_prompt(monkeypatch):
    prompt = 'private prompt with "quotes" and\na second line'
    settings = make_settings(llm_api_key="private-key")
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(
        400,
        request=request,
        json={
            "error": {
                "message": "Bad argument. private-key echoed private prompt with "
                '\\"quotes\\" and\\na second line',
                "failed_generation": "unrelated sensitive text",
            }
        },
    )
    mock_responses(monkeypatch, APIStatusError("raw exception", response=response, body=None))
    with pytest.raises(client.LLMError) as err:
        client.chat(settings, [{"role": "user", "content": prompt}], [])
    assert (
        str(err.value)
        == "chat request failed (HTTP 400): Bad argument. [redacted] echoed [redacted]"
    )


def test_chat_requests_the_named_required_tool(monkeypatch):
    response = SimpleNamespace(
        finish_reason="stop", message=SimpleNamespace(content="Done", tool_calls=[])
    )
    calls, _ = mock_responses(monkeypatch, response)
    client.chat(make_settings(), [], [], "get_policy")
    assert calls[0]["tool_choice"] == {"type": "function", "function": {"name": "get_policy"}}


def test_chat_can_request_json_without_advertising_tools(monkeypatch):
    response = SimpleNamespace(
        finish_reason="stop", message=SimpleNamespace(content='{"policy_id":"P1"}', tool_calls=[])
    )
    calls, _ = mock_responses(monkeypatch, response)
    reply = client.chat(make_settings(), [], [], json_output=True)
    assert reply.text == '{"policy_id":"P1"}'
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert "tools" not in calls[0]


def test_chat_can_stop_on_first_transient_error(monkeypatch):
    calls, sleeps = mock_responses(monkeypatch, fail(429), fail(429))
    with pytest.raises(client.LLMError, match="HTTP 429"):
        client.chat(make_settings(), [], [], retry_transient=False)
    assert len(calls) == 1
    assert sleeps == []
