"""Record model and builder.

A record matches the format consumed by the Determs CLI binary:

    {
      "kind": "determs.action_record/v1",
      "capsule_id": "agent.action.replay.v1",
      "input": { ... full action payload ... }
    }

The CLI ``determs capture`` accepts the inner ``input`` JSON; the wrapper
form (with ``kind``, ``capsule_id``, ``execution``, ``receipt``) is what
``determs capture --output ...`` produces. For the Python SDK we emit the
input-side form; the CLI tools fill in the execution+receipt at capture
time.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


DEFAULT_CAPSULE_ID = "agent.action.replay.v1"
RECORD_INPUT_VERSION = "agent-action-record-input/v1"


def _now_unix_ms() -> str:
    return str(int(time.time() * 1000))


def _new_action_id(prefix: str = "act") -> str:
    return f"{prefix}-{uuid.uuid4()}"


@dataclass
class ActionRecord:
    """Self-contained record of one agent action.

    Maps directly to the ``input`` schema of the capsule
    ``agent.action.replay.v1``. Serialize via :meth:`to_dict` or
    :meth:`to_json`.
    """

    agent_id: str
    model: dict[str, Any]
    input: dict[str, Any]
    output: dict[str, Any]
    action_id: str = field(default_factory=_new_action_id)
    occurred_at_unix_ms: str = field(default_factory=_now_unix_ms)
    params: Optional[dict[str, Any]] = None
    context: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "agent_id": self.agent_id,
            "action_id": self.action_id,
            "occurred_at_unix_ms": self.occurred_at_unix_ms,
            "model": self.model,
            "input": self.input,
            "output": self.output,
        }
        if self.params is not None:
            d["params"] = self.params
        if self.context is not None:
            d["context"] = self.context
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


def build_record(
    *,
    agent_id: str,
    model: dict[str, Any],
    input: dict[str, Any],
    output: dict[str, Any],
    params: Optional[dict[str, Any]] = None,
    context: Optional[dict[str, Any]] = None,
    action_id: Optional[str] = None,
    occurred_at_unix_ms: Optional[str] = None,
) -> ActionRecord:
    """Construct an :class:`ActionRecord` with sensible defaults."""
    return ActionRecord(
        agent_id=agent_id,
        model=model,
        input=input,
        output=output,
        params=params,
        context=context,
        action_id=action_id or _new_action_id(),
        occurred_at_unix_ms=occurred_at_unix_ms or _now_unix_ms(),
    )
