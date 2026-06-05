"""Tests that exercise the Anthropic wrapper against a fake client.

No real anthropic SDK or API call is made. The wrapper duck-types the
client by attribute access, so we hand it a minimal stub that mirrors
the public surface used by the wrapper.
"""

from dataclasses import dataclass
from typing import Any

from determs.anthropic import wrap
from determs.storage import CallbackStorage


@dataclass
class _TextBlock:
    text: str
    type: str = "text"


@dataclass
class _ToolUseBlock:
    id: str
    name: str
    input: dict
    type: str = "tool_use"


@dataclass
class _Usage:
    input_tokens: int
    output_tokens: int


@dataclass
class _Response:
    content: list
    stop_reason: str
    usage: _Usage


class _MessagesAPI:
    def __init__(self, response: _Response):
        self._response = response
        self.received_kwargs: dict[str, Any] = {}

    def create(self, **kwargs):
        self.received_kwargs = kwargs
        return self._response


class _Client:
    def __init__(self, response: _Response):
        self.messages = _MessagesAPI(response)
        self.api_key = "test"


def _build_client_with_text_response() -> _Client:
    response = _Response(
        content=[_TextBlock(text="Hello there.")],
        stop_reason="end_turn",
        usage=_Usage(input_tokens=12, output_tokens=4),
    )
    return _Client(response)


def test_wrapper_emits_record_with_expected_fields():
    captured: list[dict] = []
    client = _build_client_with_text_response()
    wrapped = wrap(
        client,
        agent_id="my-agent",
        storage=CallbackStorage(callback=captured.append),
    )

    response = wrapped.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=512,
        temperature=0.0,
        messages=[{"role": "user", "content": "Hi"}],
    )

    assert response is client.messages._response
    assert len(captured) == 1
    record = captured[0]
    assert record["agent_id"] == "my-agent"
    assert record["model"] == {"provider": "anthropic", "name": "claude-3-5-sonnet-20241022"}
    assert record["params"] == {"temperature": 0.0, "max_tokens": 512}
    assert record["input"]["messages"] == [{"role": "user", "content": "Hi"}]
    assert record["output"]["content"] == "Hello there."
    assert record["output"]["finish_reason"] == "end_turn"
    assert record["output"]["usage"] == {"input_tokens": 12, "output_tokens": 4}


def test_wrapper_passes_system_message_as_system_role():
    captured: list[dict] = []
    client = _build_client_with_text_response()
    wrapped = wrap(
        client,
        agent_id="a",
        storage=CallbackStorage(callback=captured.append),
    )
    wrapped.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=64,
        system="You are helpful.",
        messages=[{"role": "user", "content": "Hi"}],
    )
    record = captured[0]
    assert record["input"]["messages"][0] == {"role": "system", "content": "You are helpful."}


def test_wrapper_captures_tool_use_blocks():
    response = _Response(
        content=[
            _TextBlock(text="Routing to shipping."),
            _ToolUseBlock(id="tu_1", name="route", input={"team": "shipping"}),
        ],
        stop_reason="tool_use",
        usage=_Usage(input_tokens=20, output_tokens=8),
    )
    client = _Client(response)
    captured: list[dict] = []
    wrapped = wrap(
        client,
        agent_id="a",
        storage=CallbackStorage(callback=captured.append),
    )
    wrapped.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=64,
        messages=[{"role": "user", "content": "Hi"}],
    )
    record = captured[0]
    assert record["output"]["content"] == "Routing to shipping."
    assert record["output"]["tool_calls"] == [
        {"id": "tu_1", "name": "route", "input": {"team": "shipping"}}
    ]
    assert record["output"]["finish_reason"] == "tool_use"


def test_wrapper_does_not_break_on_recording_failure(monkeypatch):
    """If storage raises, the wrapper still returns the upstream response."""
    client = _build_client_with_text_response()

    def boom(_record):
        raise RuntimeError("storage down")

    wrapped = wrap(
        client,
        agent_id="a",
        storage=CallbackStorage(callback=boom),
    )
    response = wrapped.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=64,
        messages=[{"role": "user", "content": "Hi"}],
    )
    assert response is client.messages._response
