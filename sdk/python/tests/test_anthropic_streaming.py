"""Tests for the Anthropic wrapper with streaming (sync) and async."""

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from determs.anthropic import wrap, wrap_async
from determs.storage import CallbackStorage


# ============================================================
# Helpers — fake Anthropic streaming events
# ============================================================


@dataclass
class _Event:
    type: str
    message: Any = None
    content_block: Any = None
    delta: Any = None
    usage: Any = None
    index: int = 0


@dataclass
class _MessageEnvelope:
    usage: Any


@dataclass
class _Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class _ContentBlock:
    type: str
    text: str = ""
    id: str = ""
    name: str = ""


@dataclass
class _Delta:
    type: str = ""
    text: str = ""
    partial_json: str = ""
    stop_reason: str = ""


def _text_stream_events():
    """Stream of events that produces a text response in two fragments."""
    return [
        _Event(type="message_start", message=_MessageEnvelope(usage=_Usage(input_tokens=12))),
        _Event(type="content_block_start", content_block=_ContentBlock(type="text")),
        _Event(type="content_block_delta", delta=_Delta(type="text_delta", text="Hello ")),
        _Event(type="content_block_delta", delta=_Delta(type="text_delta", text="there.")),
        _Event(type="content_block_stop"),
        _Event(type="message_delta", delta=_Delta(stop_reason="end_turn"), usage=_Usage(output_tokens=4)),
        _Event(type="message_stop"),
    ]


def _tool_use_stream_events():
    """Stream that produces a single tool_use block with partial JSON."""
    return [
        _Event(type="message_start", message=_MessageEnvelope(usage=_Usage(input_tokens=20))),
        _Event(type="content_block_start", content_block=_ContentBlock(type="tool_use", id="tu_1", name="route")),
        _Event(type="content_block_delta", delta=_Delta(type="input_json_delta", partial_json='{"team":')),
        _Event(type="content_block_delta", delta=_Delta(type="input_json_delta", partial_json='"shipping"}')),
        _Event(type="content_block_stop"),
        _Event(type="message_delta", delta=_Delta(stop_reason="tool_use"), usage=_Usage(output_tokens=8)),
        _Event(type="message_stop"),
    ]


# ============================================================
# Fake sync streaming client
# ============================================================


class _SyncStreamMessages:
    def __init__(self, events):
        self._events = events

    def create(self, **kwargs):
        # Returns an iterable of events (Anthropic stream=True returns a Stream
        # object that is iterable). We mimic that with a list iterator.
        return iter(self._events)


class _SyncStreamClient:
    def __init__(self, events):
        self.messages = _SyncStreamMessages(events)


# ============================================================
# Fake async streaming client
# ============================================================


class _AsyncEventIterator:
    def __init__(self, events):
        self._events = list(events)
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._events):
            raise StopAsyncIteration
        event = self._events[self._index]
        self._index += 1
        return event


class _AsyncStreamMessages:
    def __init__(self, events):
        self._events = events

    async def create(self, **kwargs):
        return _AsyncEventIterator(self._events)


class _AsyncStreamClient:
    def __init__(self, events):
        self.messages = _AsyncStreamMessages(events)


# Async non-streaming fake
@dataclass
class _AnthropicTextBlock:
    text: str
    type: str = "text"


@dataclass
class _AnthropicResponse:
    content: list
    stop_reason: str
    usage: _Usage


class _AsyncMessagesNonStreaming:
    async def create(self, **kwargs):
        return _AnthropicResponse(
            content=[_AnthropicTextBlock(text="async hi")],
            stop_reason="end_turn",
            usage=_Usage(input_tokens=5, output_tokens=2),
        )


class _AsyncNonStreamingClient:
    def __init__(self):
        self.messages = _AsyncMessagesNonStreaming()


# ============================================================
# Tests — sync streaming
# ============================================================


def test_sync_streaming_text_emits_assembled_record():
    captured: list[dict] = []
    client = _SyncStreamClient(_text_stream_events())
    wrapped = wrap(
        client,
        agent_id="agent-sync-stream",
        storage=CallbackStorage(callback=captured.append),
    )

    stream = wrapped.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=64,
        messages=[{"role": "user", "content": "Hi"}],
        stream=True,
    )

    # Consume the stream like a caller would.
    events = list(stream)
    assert len(events) == 7
    assert len(captured) == 1

    record = captured[0]
    assert record["agent_id"] == "agent-sync-stream"
    assert record["output"]["content"] == "Hello there."
    assert record["output"]["finish_reason"] == "end_turn"
    assert record["output"]["usage"] == {"input_tokens": 12, "output_tokens": 4}


def test_sync_streaming_tool_use_emits_tool_call():
    captured: list[dict] = []
    client = _SyncStreamClient(_tool_use_stream_events())
    wrapped = wrap(
        client,
        agent_id="a",
        storage=CallbackStorage(callback=captured.append),
    )
    stream = wrapped.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=64,
        messages=[{"role": "user", "content": "Hi"}],
        stream=True,
    )
    list(stream)
    record = captured[0]
    assert record["output"]["finish_reason"] == "tool_use"
    assert record["output"]["tool_calls"] == [
        {"id": "tu_1", "name": "route", "input": {"team": "shipping"}}
    ]
    assert "content" not in record["output"]


def test_sync_streaming_abandoned_emits_no_record():
    """A stream the caller stops consuming mid-way must not emit a record."""
    captured: list[dict] = []
    client = _SyncStreamClient(_text_stream_events())
    wrapped = wrap(
        client,
        agent_id="a",
        storage=CallbackStorage(callback=captured.append),
    )
    stream = wrapped.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=64,
        messages=[{"role": "user", "content": "Hi"}],
        stream=True,
    )
    # Pull only one event then drop the iterator.
    first = next(iter(stream))
    assert first.type == "message_start"
    del stream
    assert captured == []


# ============================================================
# Tests — async non-streaming
# ============================================================


def test_async_non_streaming_emits_record():
    captured: list[dict] = []
    client = _AsyncNonStreamingClient()
    wrapped = wrap_async(
        client,
        agent_id="agent-async",
        storage=CallbackStorage(callback=captured.append),
    )

    async def run():
        response = await wrapped.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=64,
            messages=[{"role": "user", "content": "Hi"}],
        )
        return response

    response = asyncio.run(run())
    assert response.content[0].text == "async hi"
    assert len(captured) == 1
    record = captured[0]
    assert record["agent_id"] == "agent-async"
    assert record["output"]["content"] == "async hi"
    assert record["output"]["finish_reason"] == "end_turn"


# ============================================================
# Tests — async streaming
# ============================================================


def test_async_streaming_text_emits_assembled_record():
    captured: list[dict] = []
    client = _AsyncStreamClient(_text_stream_events())
    wrapped = wrap_async(
        client,
        agent_id="agent-async-stream",
        storage=CallbackStorage(callback=captured.append),
    )

    async def run():
        stream = await wrapped.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=64,
            messages=[{"role": "user", "content": "Hi"}],
            stream=True,
        )
        events: list[Any] = []
        async for event in stream:
            events.append(event)
        return events

    events = asyncio.run(run())
    assert len(events) == 7
    assert len(captured) == 1
    record = captured[0]
    assert record["agent_id"] == "agent-async-stream"
    assert record["output"]["content"] == "Hello there."
    assert record["output"]["finish_reason"] == "end_turn"


def test_async_streaming_abandoned_emits_no_record():
    captured: list[dict] = []
    client = _AsyncStreamClient(_text_stream_events())
    wrapped = wrap_async(
        client,
        agent_id="a",
        storage=CallbackStorage(callback=captured.append),
    )

    async def run():
        stream = await wrapped.messages.create(
            model="x",
            max_tokens=10,
            messages=[{"role": "user", "content": "Hi"}],
            stream=True,
        )
        # consume only one event
        it = stream.__aiter__()
        await it.__anext__()
        return None

    asyncio.run(run())
    assert captured == []
