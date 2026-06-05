"""Anthropic SDK wrapper.

Drop-in wrappers around ``anthropic.Anthropic`` (sync) and
``anthropic.AsyncAnthropic`` (async). Both forms support non-streaming and
``messages.create(stream=True)`` streaming. ``messages.stream(...)`` (the
context manager API) currently falls through unwrapped — capture for it
lands in a later version.

Usage (sync, non-streaming)::

    import anthropic
    from determs.anthropic import wrap as wrap_anthropic
    from determs.storage import FileStorage

    client = wrap_anthropic(
        anthropic.Anthropic(),
        agent_id="support-triage",
        storage=FileStorage("./records"),
    )
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=512,
        messages=[{"role": "user", "content": "Hi"}],
    )

Usage (sync, streaming)::

    stream = client.messages.create(stream=True, ...)
    for event in stream:
        ...
    # A record is emitted when the stream ends naturally.

Usage (async)::

    import anthropic
    from determs.anthropic import wrap_async as wrap_anthropic_async

    aclient = wrap_anthropic_async(
        anthropic.AsyncAnthropic(),
        agent_id="support-triage",
        storage=FileStorage("./records"),
    )
    response = await aclient.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=512,
        messages=[{"role": "user", "content": "Hi"}],
    )
"""

from __future__ import annotations

from typing import Any, Optional

from determs._capture import (
    AnthropicStreamAccumulator,
    build_anthropic_record,
)
from determs.storage import Storage, storage_from_env


# ============================================================
# Public entry points
# ============================================================


def wrap(
    client: Any,
    *,
    agent_id: str,
    storage: Optional[Storage] = None,
    context: Optional[dict[str, Any]] = None,
) -> Any:
    """Wrap a sync ``anthropic.Anthropic`` client."""
    if storage is None:
        storage = storage_from_env()
    return _SyncAnthropicProxy(client, agent_id=agent_id, storage=storage, context=context)


def wrap_async(
    client: Any,
    *,
    agent_id: str,
    storage: Optional[Storage] = None,
    context: Optional[dict[str, Any]] = None,
) -> Any:
    """Wrap an async ``anthropic.AsyncAnthropic`` client."""
    if storage is None:
        storage = storage_from_env()
    return _AsyncAnthropicProxy(client, agent_id=agent_id, storage=storage, context=context)


# ============================================================
# Sync
# ============================================================


class _SyncAnthropicProxy:
    def __init__(self, client, *, agent_id, storage, context):
        self._client = client
        self._agent_id = agent_id
        self._storage = storage
        self._context = context

    def __getattr__(self, name):
        if name == "messages":
            return _SyncMessages(
                self._client.messages,
                agent_id=self._agent_id,
                storage=self._storage,
                context=self._context,
            )
        return getattr(self._client, name)


class _SyncMessages:
    def __init__(self, messages_api, *, agent_id, storage, context):
        self._messages = messages_api
        self._agent_id = agent_id
        self._storage = storage
        self._context = context

    def __getattr__(self, name):
        return getattr(self._messages, name)

    def create(self, **kwargs):
        if kwargs.get("stream"):
            iterator = self._messages.create(**kwargs)
            return _SyncStream(
                iterator,
                request=kwargs,
                agent_id=self._agent_id,
                storage=self._storage,
                context=self._context,
            )
        response = self._messages.create(**kwargs)
        _emit_sync(
            self._storage,
            kwargs,
            response,
            agent_id=self._agent_id,
            context=self._context,
        )
        return response


class _SyncStream:
    def __init__(self, inner, *, request, agent_id, storage, context):
        self._inner = inner
        self._iter = iter(inner)
        self._request = request
        self._agent_id = agent_id
        self._storage = storage
        self._context = context
        self._acc = AnthropicStreamAccumulator()
        self._emitted = False

    def __iter__(self):
        return self

    def __next__(self):
        try:
            event = next(self._iter)
        except StopIteration:
            self._emit()
            raise
        self._acc.consume(event)
        return event

    def _emit(self):
        if self._emitted:
            return
        self._emitted = True
        response_like = self._acc.to_response_like()
        _emit_sync(
            self._storage,
            self._request,
            response_like,
            agent_id=self._agent_id,
            context=self._context,
        )


# ============================================================
# Async
# ============================================================


class _AsyncAnthropicProxy:
    def __init__(self, client, *, agent_id, storage, context):
        self._client = client
        self._agent_id = agent_id
        self._storage = storage
        self._context = context

    def __getattr__(self, name):
        if name == "messages":
            return _AsyncMessages(
                self._client.messages,
                agent_id=self._agent_id,
                storage=self._storage,
                context=self._context,
            )
        return getattr(self._client, name)


class _AsyncMessages:
    def __init__(self, messages_api, *, agent_id, storage, context):
        self._messages = messages_api
        self._agent_id = agent_id
        self._storage = storage
        self._context = context

    def __getattr__(self, name):
        return getattr(self._messages, name)

    async def create(self, **kwargs):
        if kwargs.get("stream"):
            iterator = await self._messages.create(**kwargs)
            return _AsyncStream(
                iterator,
                request=kwargs,
                agent_id=self._agent_id,
                storage=self._storage,
                context=self._context,
            )
        response = await self._messages.create(**kwargs)
        _emit_sync(
            self._storage,
            kwargs,
            response,
            agent_id=self._agent_id,
            context=self._context,
        )
        return response


class _AsyncStream:
    def __init__(self, inner, *, request, agent_id, storage, context):
        self._inner = inner
        self._iter = inner.__aiter__()
        self._request = request
        self._agent_id = agent_id
        self._storage = storage
        self._context = context
        self._acc = AnthropicStreamAccumulator()
        self._emitted = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            event = await self._iter.__anext__()
        except StopAsyncIteration:
            self._emit()
            raise
        self._acc.consume(event)
        return event

    def _emit(self):
        if self._emitted:
            return
        self._emitted = True
        response_like = self._acc.to_response_like()
        _emit_sync(
            self._storage,
            self._request,
            response_like,
            agent_id=self._agent_id,
            context=self._context,
        )


# ============================================================
# Internal — single emit point
# ============================================================


def _emit_sync(storage, request, response, *, agent_id, context):
    try:
        record = build_anthropic_record(
            request,
            response,
            agent_id=agent_id,
            context=context,
        )
        storage.put(record)
    except Exception:
        # Never let recording break the caller.
        pass
