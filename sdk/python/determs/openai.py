"""OpenAI SDK wrapper.

Drop-in wrappers around ``openai.OpenAI`` (sync) and ``openai.AsyncOpenAI``
(async). Both support non-streaming and streaming
``chat.completions.create(stream=True)``.

Usage (sync, non-streaming)::

    from openai import OpenAI
    from determs.openai import wrap as wrap_openai
    from determs.storage import FileStorage

    client = wrap_openai(
        OpenAI(),
        agent_id="support-triage",
        storage=FileStorage("./records"),
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Hi"}],
    )

Usage (async)::

    from openai import AsyncOpenAI
    from determs.openai import wrap_async as wrap_openai_async

    aclient = wrap_openai_async(AsyncOpenAI(), agent_id="...", storage=...)
    response = await aclient.chat.completions.create(model=..., messages=[...])
"""

from __future__ import annotations

from typing import Any, Optional

from determs._capture import (
    OpenAIStreamAccumulator,
    build_openai_record,
)
from determs.storage import Storage, storage_from_env


def wrap(
    client: Any,
    *,
    agent_id: str,
    storage: Optional[Storage] = None,
    context: Optional[dict[str, Any]] = None,
) -> Any:
    """Wrap a sync ``openai.OpenAI`` client."""
    if storage is None:
        storage = storage_from_env()
    return _SyncOpenAIProxy(client, agent_id=agent_id, storage=storage, context=context)


def wrap_async(
    client: Any,
    *,
    agent_id: str,
    storage: Optional[Storage] = None,
    context: Optional[dict[str, Any]] = None,
) -> Any:
    """Wrap an async ``openai.AsyncOpenAI`` client."""
    if storage is None:
        storage = storage_from_env()
    return _AsyncOpenAIProxy(client, agent_id=agent_id, storage=storage, context=context)


# ============================================================
# Sync
# ============================================================


class _SyncOpenAIProxy:
    def __init__(self, client, *, agent_id, storage, context):
        self._client = client
        self._agent_id = agent_id
        self._storage = storage
        self._context = context

    def __getattr__(self, name):
        if name == "chat":
            return _SyncChat(
                self._client.chat,
                agent_id=self._agent_id,
                storage=self._storage,
                context=self._context,
            )
        return getattr(self._client, name)


class _SyncChat:
    def __init__(self, chat, *, agent_id, storage, context):
        self._chat = chat
        self._agent_id = agent_id
        self._storage = storage
        self._context = context

    def __getattr__(self, name):
        if name == "completions":
            return _SyncCompletions(
                self._chat.completions,
                agent_id=self._agent_id,
                storage=self._storage,
                context=self._context,
            )
        return getattr(self._chat, name)


class _SyncCompletions:
    def __init__(self, completions, *, agent_id, storage, context):
        self._completions = completions
        self._agent_id = agent_id
        self._storage = storage
        self._context = context

    def __getattr__(self, name):
        return getattr(self._completions, name)

    def create(self, **kwargs):
        if kwargs.get("stream"):
            iterator = self._completions.create(**kwargs)
            return _SyncStream(
                iterator,
                request=kwargs,
                agent_id=self._agent_id,
                storage=self._storage,
                context=self._context,
            )
        response = self._completions.create(**kwargs)
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
        self._acc = OpenAIStreamAccumulator()
        self._emitted = False

    def __iter__(self):
        return self

    def __next__(self):
        try:
            chunk = next(self._iter)
        except StopIteration:
            self._emit()
            raise
        self._acc.consume(chunk)
        return chunk

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


class _AsyncOpenAIProxy:
    def __init__(self, client, *, agent_id, storage, context):
        self._client = client
        self._agent_id = agent_id
        self._storage = storage
        self._context = context

    def __getattr__(self, name):
        if name == "chat":
            return _AsyncChat(
                self._client.chat,
                agent_id=self._agent_id,
                storage=self._storage,
                context=self._context,
            )
        return getattr(self._client, name)


class _AsyncChat:
    def __init__(self, chat, *, agent_id, storage, context):
        self._chat = chat
        self._agent_id = agent_id
        self._storage = storage
        self._context = context

    def __getattr__(self, name):
        if name == "completions":
            return _AsyncCompletions(
                self._chat.completions,
                agent_id=self._agent_id,
                storage=self._storage,
                context=self._context,
            )
        return getattr(self._chat, name)


class _AsyncCompletions:
    def __init__(self, completions, *, agent_id, storage, context):
        self._completions = completions
        self._agent_id = agent_id
        self._storage = storage
        self._context = context

    def __getattr__(self, name):
        return getattr(self._completions, name)

    async def create(self, **kwargs):
        if kwargs.get("stream"):
            iterator = await self._completions.create(**kwargs)
            return _AsyncStream(
                iterator,
                request=kwargs,
                agent_id=self._agent_id,
                storage=self._storage,
                context=self._context,
            )
        response = await self._completions.create(**kwargs)
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
        self._acc = OpenAIStreamAccumulator()
        self._emitted = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            chunk = await self._iter.__anext__()
        except StopAsyncIteration:
            self._emit()
            raise
        self._acc.consume(chunk)
        return chunk

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


def _emit_sync(storage, request, response, *, agent_id, context):
    try:
        record = build_openai_record(
            request,
            response,
            agent_id=agent_id,
            context=context,
        )
        storage.put(record)
    except Exception:
        pass
