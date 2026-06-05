"""Shared capture logic.

The SDK has four code paths per provider:

- sync, non-streaming
- sync, streaming
- async, non-streaming
- async, streaming

Building the record requires the same inputs in all four:

- the request kwargs as the caller passed them
- a "final response" — either the response object directly (non-streaming)
  or a reconstructed equivalent assembled from streamed events.

This module centralizes the record builders and the stream accumulators.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from determs.record import ActionRecord, build_record


# ============================================================
# Provider-agnostic helpers
# ============================================================


def _safe_attr(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _as_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for chunk in content:
            if isinstance(chunk, dict):
                if chunk.get("type") == "text":
                    parts.append(chunk.get("text", ""))
                else:
                    parts.append(str(chunk))
            else:
                parts.append(str(chunk))
        return "".join(parts)
    return str(content)


# ============================================================
# Anthropic — record builder for a final response
# ============================================================


_ANTHROPIC_PARAM_KEYS = ("temperature", "top_p", "max_tokens", "top_k", "stop_sequences")


def build_anthropic_record(
    request: dict[str, Any],
    response: Any,
    *,
    agent_id: str,
    context: Optional[dict[str, Any]],
) -> ActionRecord:
    model_name = request.get("model", "unknown")
    params: dict[str, Any] = {}
    for key in _ANTHROPIC_PARAM_KEYS:
        if key in request and request[key] is not None:
            params[key] = request[key]

    messages: list[dict[str, Any]] = []
    system = request.get("system")
    if system:
        messages.append({"role": "system", "content": _as_text(system)})
    for msg in request.get("messages") or []:
        if isinstance(msg, dict):
            messages.append(
                {
                    "role": msg.get("role", "user"),
                    "content": _as_text(msg.get("content")),
                }
            )
        else:
            messages.append({"role": "user", "content": _as_text(msg)})

    tools = request.get("tools")
    inp: dict[str, Any] = {"messages": messages}
    if tools:
        inp["tools"] = tools

    content_text, tool_calls = _extract_anthropic_output(response)
    finish_reason = _safe_attr(response, "stop_reason")
    usage_obj = _safe_attr(response, "usage")
    usage: dict[str, Any] = {}
    if usage_obj is not None:
        in_t = _safe_attr(usage_obj, "input_tokens")
        out_t = _safe_attr(usage_obj, "output_tokens")
        if in_t is not None:
            usage["input_tokens"] = in_t
        if out_t is not None:
            usage["output_tokens"] = out_t

    output: dict[str, Any] = {}
    if content_text:
        output["content"] = content_text
    if tool_calls:
        output["tool_calls"] = tool_calls
    if finish_reason:
        output["finish_reason"] = finish_reason
    if usage:
        output["usage"] = usage

    return build_record(
        agent_id=agent_id,
        model={"provider": "anthropic", "name": model_name},
        params=params or None,
        input=inp,
        output=output,
        context=context,
    )


def _extract_anthropic_output(response: Any) -> tuple[str, list[dict[str, Any]]]:
    content_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    content = _safe_attr(response, "content") or []
    for block in content:
        block_type = _safe_attr(block, "type")
        if block_type == "text":
            text = _safe_attr(block, "text") or ""
            content_parts.append(text)
        elif block_type == "tool_use":
            tool_calls.append(
                {
                    "id": _safe_attr(block, "id"),
                    "name": _safe_attr(block, "name"),
                    "input": _safe_attr(block, "input"),
                }
            )
    return ("".join(content_parts), tool_calls)


# ============================================================
# Anthropic — stream accumulator
# ============================================================


@dataclass
class _AnthropicBlock:
    type: str
    text: str = ""
    id: Optional[str] = None
    name: Optional[str] = None
    input_json: str = ""  # for tool_use, accumulated JSON deltas

    def to_response_block(self) -> Any:
        if self.type == "text":
            return _SimpleBlock(type="text", text=self.text)
        if self.type == "tool_use":
            try:
                import json

                parsed = json.loads(self.input_json) if self.input_json else {}
            except Exception:
                parsed = {}
            return _SimpleBlock(type="tool_use", id=self.id, name=self.name, input=parsed)
        return _SimpleBlock(type=self.type)


@dataclass
class _SimpleBlock:
    type: str
    text: Optional[str] = None
    id: Optional[str] = None
    name: Optional[str] = None
    input: Optional[dict[str, Any]] = None


@dataclass
class _SimpleUsage:
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


@dataclass
class _SimpleResponse:
    content: list = field(default_factory=list)
    stop_reason: Optional[str] = None
    usage: Optional[_SimpleUsage] = None


@dataclass
class AnthropicStreamAccumulator:
    """Accumulates events from ``messages.create(stream=True)``.

    Events that we handle (per Anthropic streaming spec):
    - ``message_start``: contains initial usage (input_tokens)
    - ``content_block_start``: opens a text or tool_use block
    - ``content_block_delta``: text delta or input_json delta
    - ``content_block_stop``: closes the current block
    - ``message_delta``: contains stop_reason and updated output_tokens
    - ``message_stop``: end of message
    """

    blocks: list[_AnthropicBlock] = field(default_factory=list)
    stop_reason: Optional[str] = None
    usage: _SimpleUsage = field(default_factory=_SimpleUsage)
    _current: Optional[_AnthropicBlock] = None

    def consume(self, event: Any) -> None:
        et = _safe_attr(event, "type")

        if et == "message_start":
            message = _safe_attr(event, "message")
            initial_usage = _safe_attr(message, "usage")
            if initial_usage is not None:
                in_t = _safe_attr(initial_usage, "input_tokens")
                out_t = _safe_attr(initial_usage, "output_tokens")
                if in_t is not None:
                    self.usage.input_tokens = in_t
                if out_t is not None:
                    self.usage.output_tokens = out_t

        elif et == "content_block_start":
            block = _safe_attr(event, "content_block") or event
            block_type = _safe_attr(block, "type") or "text"
            self._current = _AnthropicBlock(
                type=block_type,
                id=_safe_attr(block, "id"),
                name=_safe_attr(block, "name"),
            )

        elif et == "content_block_delta":
            delta = _safe_attr(event, "delta")
            delta_type = _safe_attr(delta, "type")
            if self._current is None:
                return
            if delta_type == "text_delta":
                text = _safe_attr(delta, "text") or ""
                self._current.text += text
            elif delta_type == "input_json_delta":
                partial = _safe_attr(delta, "partial_json") or ""
                self._current.input_json += partial

        elif et == "content_block_stop":
            if self._current is not None:
                self.blocks.append(self._current)
                self._current = None

        elif et == "message_delta":
            delta = _safe_attr(event, "delta")
            stop_reason = _safe_attr(delta, "stop_reason")
            if stop_reason:
                self.stop_reason = stop_reason
            usage = _safe_attr(event, "usage")
            if usage is not None:
                out_t = _safe_attr(usage, "output_tokens")
                if out_t is not None:
                    self.usage.output_tokens = out_t

        elif et == "message_stop":
            # If a block is still open (defensive), close it.
            if self._current is not None:
                self.blocks.append(self._current)
                self._current = None

    def to_response_like(self) -> _SimpleResponse:
        content = [b.to_response_block() for b in self.blocks]
        usage = self.usage if (self.usage.input_tokens is not None or self.usage.output_tokens is not None) else None
        return _SimpleResponse(content=content, stop_reason=self.stop_reason, usage=usage)


# ============================================================
# OpenAI — record builder
# ============================================================


_OPENAI_PARAM_KEYS = (
    "temperature",
    "top_p",
    "max_tokens",
    "presence_penalty",
    "frequency_penalty",
    "seed",
    "stop",
)


def build_openai_record(
    request: dict[str, Any],
    response: Any,
    *,
    agent_id: str,
    context: Optional[dict[str, Any]],
) -> ActionRecord:
    model_name = request.get("model", "unknown")
    params: dict[str, Any] = {}
    for key in _OPENAI_PARAM_KEYS:
        if key in request and request[key] is not None:
            params[key] = request[key]

    messages: list[dict[str, Any]] = []
    for msg in request.get("messages") or []:
        if isinstance(msg, dict):
            content = msg.get("content")
            if isinstance(content, list):
                content = "".join(
                    c.get("text", "") if isinstance(c, dict) else str(c) for c in content
                )
            messages.append({"role": msg.get("role", "user"), "content": str(content or "")})
        else:
            messages.append({"role": "user", "content": str(msg)})

    tools = request.get("tools")
    inp: dict[str, Any] = {"messages": messages}
    if tools:
        inp["tools"] = tools

    content, tool_calls, finish_reason = _extract_openai_output(response)
    usage = _extract_usage_openai(response)

    output: dict[str, Any] = {}
    if content:
        output["content"] = content
    if tool_calls:
        output["tool_calls"] = tool_calls
    if finish_reason:
        output["finish_reason"] = finish_reason
    if usage:
        output["usage"] = usage

    return build_record(
        agent_id=agent_id,
        model={"provider": "openai", "name": model_name},
        params=params or None,
        input=inp,
        output=output,
        context=context,
    )


def _extract_openai_output(response: Any) -> tuple[str, list[dict[str, Any]], Optional[str]]:
    choices = _safe_attr(response, "choices") or []
    if not choices:
        return ("", [], None)
    first = choices[0]
    message = _safe_attr(first, "message")
    content = _safe_attr(message, "content") or ""
    finish_reason = _safe_attr(first, "finish_reason")

    raw_tool_calls = _safe_attr(message, "tool_calls") or []
    tool_calls: list[dict[str, Any]] = []
    for tc in raw_tool_calls:
        function = _safe_attr(tc, "function")
        tool_calls.append(
            {
                "id": _safe_attr(tc, "id"),
                "name": _safe_attr(function, "name") if function else None,
                "arguments": _safe_attr(function, "arguments") if function else None,
            }
        )
    return (str(content), tool_calls, finish_reason)


def _extract_usage_openai(response: Any) -> dict[str, Any]:
    usage = _safe_attr(response, "usage")
    if not usage:
        return {}
    out: dict[str, Any] = {}
    prompt = _safe_attr(usage, "prompt_tokens")
    completion = _safe_attr(usage, "completion_tokens")
    if prompt is not None:
        out["input_tokens"] = prompt
    if completion is not None:
        out["output_tokens"] = completion
    return out


# ============================================================
# OpenAI — stream accumulator
# ============================================================


@dataclass
class _OpenAIToolCall:
    id: Optional[str] = None
    name: Optional[str] = None
    arguments: str = ""

    def to_message_tool_call(self) -> Any:
        return _SimpleOpenAIToolCall(
            id=self.id,
            function=_SimpleOpenAIFunction(name=self.name, arguments=self.arguments),
        )


@dataclass
class _SimpleOpenAIFunction:
    name: Optional[str] = None
    arguments: str = ""


@dataclass
class _SimpleOpenAIToolCall:
    id: Optional[str] = None
    function: Optional[_SimpleOpenAIFunction] = None


@dataclass
class _SimpleOpenAIMessage:
    content: str = ""
    tool_calls: list = field(default_factory=list)


@dataclass
class _SimpleOpenAIChoice:
    message: _SimpleOpenAIMessage = field(default_factory=_SimpleOpenAIMessage)
    finish_reason: Optional[str] = None


@dataclass
class _SimpleOpenAIUsage:
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None


@dataclass
class _SimpleOpenAIResponse:
    choices: list = field(default_factory=list)
    usage: Optional[_SimpleOpenAIUsage] = None


@dataclass
class OpenAIStreamAccumulator:
    """Accumulates chunks from ``chat.completions.create(stream=True)``.

    Each chunk has ``choices[0].delta`` with either ``content`` (text
    fragment) or ``tool_calls`` (list of partial tool calls keyed by
    ``index``). The final chunk has ``finish_reason``. ``usage`` shows up
    only when ``stream_options={"include_usage": True}``.
    """

    content_parts: list[str] = field(default_factory=list)
    tool_calls_by_index: dict[int, _OpenAIToolCall] = field(default_factory=dict)
    finish_reason: Optional[str] = None
    usage: _SimpleOpenAIUsage = field(default_factory=_SimpleOpenAIUsage)

    def consume(self, chunk: Any) -> None:
        choices = _safe_attr(chunk, "choices") or []
        for choice in choices:
            delta = _safe_attr(choice, "delta")
            if delta is not None:
                content = _safe_attr(delta, "content")
                if content:
                    self.content_parts.append(str(content))
                tool_calls = _safe_attr(delta, "tool_calls") or []
                for tc in tool_calls:
                    index = _safe_attr(tc, "index")
                    if index is None:
                        index = 0
                    acc = self.tool_calls_by_index.setdefault(index, _OpenAIToolCall())
                    tc_id = _safe_attr(tc, "id")
                    if tc_id:
                        acc.id = tc_id
                    function = _safe_attr(tc, "function")
                    if function is not None:
                        name = _safe_attr(function, "name")
                        if name:
                            acc.name = name
                        args = _safe_attr(function, "arguments")
                        if args:
                            acc.arguments += str(args)
            finish_reason = _safe_attr(choice, "finish_reason")
            if finish_reason:
                self.finish_reason = finish_reason

        usage = _safe_attr(chunk, "usage")
        if usage is not None:
            prompt = _safe_attr(usage, "prompt_tokens")
            completion = _safe_attr(usage, "completion_tokens")
            if prompt is not None:
                self.usage.prompt_tokens = prompt
            if completion is not None:
                self.usage.completion_tokens = completion

    def to_response_like(self) -> _SimpleOpenAIResponse:
        tool_calls_list = [
            self.tool_calls_by_index[k].to_message_tool_call()
            for k in sorted(self.tool_calls_by_index)
        ]
        message = _SimpleOpenAIMessage(
            content="".join(self.content_parts),
            tool_calls=tool_calls_list,
        )
        choice = _SimpleOpenAIChoice(message=message, finish_reason=self.finish_reason)
        usage = (
            self.usage
            if (
                self.usage.prompt_tokens is not None
                or self.usage.completion_tokens is not None
            )
            else None
        )
        return _SimpleOpenAIResponse(choices=[choice], usage=usage)
