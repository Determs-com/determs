"""Tests for the OpenAI wrapper against a fake client."""

from dataclasses import dataclass
from typing import Any

from determs.openai import wrap
from determs.storage import CallbackStorage


@dataclass
class _Function:
    name: str
    arguments: str


@dataclass
class _ToolCall:
    id: str
    function: _Function
    type: str = "function"


@dataclass
class _Message:
    content: str = ""
    tool_calls: list = None  # type: ignore[assignment]


@dataclass
class _Choice:
    message: _Message
    finish_reason: str


@dataclass
class _Usage:
    prompt_tokens: int
    completion_tokens: int


@dataclass
class _Response:
    choices: list
    usage: _Usage


class _CompletionsAPI:
    def __init__(self, response: _Response):
        self._response = response
        self.received_kwargs: dict[str, Any] = {}

    def create(self, **kwargs):
        self.received_kwargs = kwargs
        return self._response


class _Chat:
    def __init__(self, response: _Response):
        self.completions = _CompletionsAPI(response)


class _Client:
    def __init__(self, response: _Response):
        self.chat = _Chat(response)


def _text_response() -> _Response:
    return _Response(
        choices=[
            _Choice(
                message=_Message(content="Hello there.", tool_calls=None),
                finish_reason="stop",
            )
        ],
        usage=_Usage(prompt_tokens=10, completion_tokens=3),
    )


def test_openai_wrapper_emits_record():
    captured: list[dict] = []
    client = _Client(_text_response())
    wrapped = wrap(
        client,
        agent_id="my-agent",
        storage=CallbackStorage(callback=captured.append),
    )
    response = wrapped.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.2,
        messages=[{"role": "user", "content": "Hi"}],
    )
    assert response is client.chat.completions._response
    assert len(captured) == 1
    record = captured[0]
    assert record["agent_id"] == "my-agent"
    assert record["model"] == {"provider": "openai", "name": "gpt-4o-mini"}
    assert record["params"] == {"temperature": 0.2}
    assert record["output"]["content"] == "Hello there."
    assert record["output"]["finish_reason"] == "stop"
    assert record["output"]["usage"] == {"input_tokens": 10, "output_tokens": 3}


def test_openai_wrapper_captures_tool_calls():
    response = _Response(
        choices=[
            _Choice(
                message=_Message(
                    content="",
                    tool_calls=[
                        _ToolCall(
                            id="call_1",
                            function=_Function(name="search", arguments='{"q":"foo"}'),
                        )
                    ],
                ),
                finish_reason="tool_calls",
            )
        ],
        usage=_Usage(prompt_tokens=12, completion_tokens=4),
    )
    captured: list[dict] = []
    wrapped = wrap(
        _Client(response),
        agent_id="a",
        storage=CallbackStorage(callback=captured.append),
    )
    wrapped.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Hi"}],
    )
    record = captured[0]
    assert record["output"]["tool_calls"] == [
        {"id": "call_1", "name": "search", "arguments": '{"q":"foo"}'}
    ]
    assert record["output"]["finish_reason"] == "tool_calls"
    assert "content" not in record["output"]
