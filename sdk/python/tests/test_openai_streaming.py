"""Tests for the OpenAI wrapper with streaming (sync) and async."""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

from determs.openai import wrap, wrap_async
from determs.storage import CallbackStorage


# ============================================================
# Helpers — fake OpenAI streaming chunks
# ============================================================


@dataclass
class _DeltaToolCallFunction:
    name: Optional[str] = None
    arguments: Optional[str] = None


@dataclass
class _DeltaToolCall:
    index: int = 0
    id: Optional[str] = None
    function: Optional[_DeltaToolCallFunction] = None


@dataclass
class _Delta:
    content: Optional[str] = None
    tool_calls: Optional[list] = None


@dataclass
class _ChunkChoice:
    delta: _Delta
    finish_reason: Optional[str] = None


@dataclass
class _ChunkUsage:
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None


@dataclass
class _Chunk:
    choices: list = field(default_factory=list)
    usage: Optional[_ChunkUsage] = None


def _text_chunks():
    return [
        _Chunk(choices=[_ChunkChoice(delta=_Delta(content="Hello "))]),
        _Chunk(choices=[_ChunkChoice(delta=_Delta(content="there."))]),
        _Chunk(choices=[_ChunkChoice(delta=_Delta(), finish_reason="stop")]),
        _Chunk(choices=[], usage=_ChunkUsage(prompt_tokens=10, completion_tokens=3)),
    ]


def _tool_call_chunks():
    return [
        _Chunk(
            choices=[
                _ChunkChoice(
                    delta=_Delta(
                        tool_calls=[
                            _DeltaToolCall(
                                index=0,
                                id="call_1",
                                function=_DeltaToolCallFunction(name="search", arguments=""),
                            )
                        ]
                    )
                )
            ]
        ),
        _Chunk(
            choices=[
                _ChunkChoice(
                    delta=_Delta(
                        tool_calls=[
                            _DeltaToolCall(
                                index=0,
                                function=_DeltaToolCallFunction(arguments='{"q":'),
                            )
                        ]
                    )
                )
            ]
        ),
        _Chunk(
            choices=[
                _ChunkChoice(
                    delta=_Delta(
                        tool_calls=[
                            _DeltaToolCall(
                                index=0,
                                function=_DeltaToolCallFunction(arguments='"foo"}'),
                            )
                        ]
                    )
                )
            ]
        ),
        _Chunk(choices=[_ChunkChoice(delta=_Delta(), finish_reason="tool_calls")]),
    ]


# Fake clients
class _SyncStreamCompletions:
    def __init__(self, chunks):
        self._chunks = chunks

    def create(self, **kwargs):
        return iter(self._chunks)


class _SyncStreamChat:
    def __init__(self, chunks):
        self.completions = _SyncStreamCompletions(chunks)


class _SyncStreamClient:
    def __init__(self, chunks):
        self.chat = _SyncStreamChat(chunks)


class _AsyncChunkIterator:
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk


class _AsyncStreamCompletions:
    def __init__(self, chunks):
        self._chunks = chunks

    async def create(self, **kwargs):
        return _AsyncChunkIterator(self._chunks)


class _AsyncStreamChat:
    def __init__(self, chunks):
        self.completions = _AsyncStreamCompletions(chunks)


class _AsyncStreamClient:
    def __init__(self, chunks):
        self.chat = _AsyncStreamChat(chunks)


# Async non-streaming
@dataclass
class _Message:
    content: str = ""
    tool_calls: list = field(default_factory=list)


@dataclass
class _Choice:
    message: _Message
    finish_reason: str = "stop"


@dataclass
class _Usage:
    prompt_tokens: int = 10
    completion_tokens: int = 3


@dataclass
class _Response:
    choices: list
    usage: _Usage


class _AsyncNonStreamingCompletions:
    async def create(self, **kwargs):
        return _Response(
            choices=[_Choice(message=_Message(content="async hi"))],
            usage=_Usage(),
        )


class _AsyncNonStreamingChat:
    def __init__(self):
        self.completions = _AsyncNonStreamingCompletions()


class _AsyncNonStreamingClient:
    def __init__(self):
        self.chat = _AsyncNonStreamingChat()


# ============================================================
# Tests — sync streaming
# ============================================================


def test_openai_sync_streaming_text():
    captured: list[dict] = []
    client = _SyncStreamClient(_text_chunks())
    wrapped = wrap(
        client,
        agent_id="agent-sync-stream",
        storage=CallbackStorage(callback=captured.append),
    )
    stream = wrapped.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Hi"}],
        stream=True,
    )
    chunks = list(stream)
    assert len(chunks) == 4
    assert len(captured) == 1
    record = captured[0]
    assert record["output"]["content"] == "Hello there."
    assert record["output"]["finish_reason"] == "stop"
    assert record["output"]["usage"] == {"input_tokens": 10, "output_tokens": 3}


def test_openai_sync_streaming_tool_calls_accumulate():
    captured: list[dict] = []
    client = _SyncStreamClient(_tool_call_chunks())
    wrapped = wrap(
        client,
        agent_id="a",
        storage=CallbackStorage(callback=captured.append),
    )
    stream = wrapped.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Hi"}],
        stream=True,
    )
    list(stream)
    record = captured[0]
    assert record["output"]["finish_reason"] == "tool_calls"
    assert record["output"]["tool_calls"] == [
        {"id": "call_1", "name": "search", "arguments": '{"q":"foo"}'}
    ]
    assert "content" not in record["output"]


def test_openai_sync_streaming_abandoned_no_record():
    captured: list[dict] = []
    client = _SyncStreamClient(_text_chunks())
    wrapped = wrap(
        client,
        agent_id="a",
        storage=CallbackStorage(callback=captured.append),
    )
    stream = wrapped.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Hi"}],
        stream=True,
    )
    next(iter(stream))
    del stream
    assert captured == []


# ============================================================
# Tests — async non-streaming
# ============================================================


def test_openai_async_non_streaming():
    captured: list[dict] = []
    wrapped = wrap_async(
        _AsyncNonStreamingClient(),
        agent_id="agent-async",
        storage=CallbackStorage(callback=captured.append),
    )

    async def run():
        return await wrapped.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Hi"}],
        )

    response = asyncio.run(run())
    assert response.choices[0].message.content == "async hi"
    assert captured[0]["output"]["content"] == "async hi"


# ============================================================
# Tests — async streaming
# ============================================================


def test_openai_async_streaming_text():
    captured: list[dict] = []
    client = _AsyncStreamClient(_text_chunks())
    wrapped = wrap_async(
        client,
        agent_id="agent-async-stream",
        storage=CallbackStorage(callback=captured.append),
    )

    async def run():
        stream = await wrapped.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Hi"}],
            stream=True,
        )
        return [chunk async for chunk in stream]

    chunks = asyncio.run(run())
    assert len(chunks) == 4
    record = captured[0]
    assert record["output"]["content"] == "Hello there."
    assert record["output"]["finish_reason"] == "stop"
