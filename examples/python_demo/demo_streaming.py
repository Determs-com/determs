"""Streaming demo: SDK accumulates streamed events, emits one record on completion.

Uses a fake Anthropic streaming client to keep the demo fully offline.

Run from the repo root:

    cargo build --release
    .venv/bin/python examples/python_demo/demo_streaming.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from determs.anthropic import wrap as wrap_anthropic
from determs.storage import FileStorage


REPO_ROOT = Path(__file__).resolve().parents[2]


def find_determs() -> str:
    for candidate in (
        REPO_ROOT / "target" / "release" / "determs",
        REPO_ROOT / "target" / "debug" / "determs",
    ):
        if candidate.exists():
            return str(candidate)
    found = shutil.which("determs")
    if not found:
        sys.exit("determs binary not found. Run `cargo build` first.")
    return found


# Fake Anthropic streaming surface — mirrors the shape the wrapper expects.
@dataclass
class _Event:
    type: str
    message: object = None
    content_block: object = None
    delta: object = None
    usage: object = None


@dataclass
class _Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class _ContentBlock:
    type: str
    text: str = ""


@dataclass
class _Delta:
    type: str = ""
    text: str = ""
    stop_reason: str = ""


@dataclass
class _MessageEnvelope:
    usage: _Usage


def _streamed_events():
    return [
        _Event(type="message_start", message=_MessageEnvelope(usage=_Usage(input_tokens=18))),
        _Event(type="content_block_start", content_block=_ContentBlock(type="text")),
        _Event(type="content_block_delta", delta=_Delta(type="text_delta", text="Routing ")),
        _Event(type="content_block_delta", delta=_Delta(type="text_delta", text="to ")),
        _Event(type="content_block_delta", delta=_Delta(type="text_delta", text="shipping team.")),
        _Event(type="content_block_stop"),
        _Event(
            type="message_delta",
            delta=_Delta(stop_reason="end_turn"),
            usage=_Usage(output_tokens=6),
        ),
        _Event(type="message_stop"),
    ]


class _FakeMessages:
    def create(self, **kwargs):
        # Stream=True returns an iterable of events; ignore other kwargs.
        return iter(_streamed_events())


class _FakeClient:
    def __init__(self):
        self.messages = _FakeMessages()


def main() -> None:
    determs_bin = find_determs()
    print(f"[demo] using determs binary: {determs_bin}")

    with tempfile.TemporaryDirectory() as tmp:
        records_dir = Path(tmp) / "records"
        client = wrap_anthropic(
            _FakeClient(),
            agent_id="support-triage",
            storage=FileStorage(str(records_dir)),
        )

        print("[demo] calling wrapped client with stream=True ...")
        stream = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=64,
            messages=[{"role": "user", "content": "My order is late"}],
            stream=True,
        )
        text = ""
        for event in stream:
            if event.type == "content_block_delta":
                text += event.delta.text
        print(f"[demo] reconstructed text from stream: {text!r}")

        emitted = list(records_dir.glob("*.json"))
        assert emitted, "SDK did not emit any record"
        emitted_path = emitted[0]
        print(f"[demo] SDK emitted record after stream completion: {emitted_path.name}")

        # Verify the emitted record is accepted by the binary.
        record_path = Path(tmp) / "record.json"
        subprocess.run(
            [
                determs_bin,
                "capture",
                "--input",
                str(emitted_path),
                "--output",
                str(record_path),
            ],
            check=True,
            capture_output=True,
        )
        verify = subprocess.run(
            [determs_bin, "verify", "--record", str(record_path)],
            capture_output=True,
            text=True,
            check=True,
        )
        report = json.loads(verify.stdout)
        assert report["verified"] is True
        print(f"[demo] record_digest: {report['record_digest']}")
        print("[demo] PASS — streaming → record → capture → verify loop works.")


if __name__ == "__main__":
    main()
