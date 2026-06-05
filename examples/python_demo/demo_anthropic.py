"""End-to-end demo: SDK record → CLI capture → CLI verify.

Runs without any real LLM API call by using a fake Anthropic client.
Shows the full proprietary record loop you would get in production.

Run from the repo root:

    cargo build --release
    .venv/bin/python examples/python_demo/demo_anthropic.py
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


# A minimal fake Anthropic client that mirrors what the wrapper expects.
@dataclass
class _Text:
    text: str
    type: str = "text"


@dataclass
class _Usage:
    input_tokens: int
    output_tokens: int


@dataclass
class _Response:
    content: list
    stop_reason: str
    usage: _Usage


class _FakeMessages:
    def create(self, **kwargs):
        return _Response(
            content=[_Text(text="Routing to shipping team.")],
            stop_reason="end_turn",
            usage=_Usage(input_tokens=24, output_tokens=8),
        )


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

        print("[demo] calling wrapped client (no real API call) ...")
        client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=512,
            temperature=0.0,
            messages=[
                {"role": "user", "content": "My order #1234 hasn't shipped."}
            ],
        )

        emitted = list(records_dir.glob("*.json"))
        assert emitted, "SDK did not emit any record"
        emitted_path = emitted[0]
        print(f"[demo] SDK emitted record: {emitted_path.name}")

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
        )
        print(f"[demo] CLI captured into: {record_path.name}")

        verify = subprocess.run(
            [determs_bin, "verify", "--record", str(record_path)],
            capture_output=True,
            text=True,
            check=True,
        )
        report = json.loads(verify.stdout)
        print(f"[demo] verify report:")
        print(json.dumps(report, indent=2))
        print()
        assert report["verified"] is True
        print(f"[demo] record_digest: {report['record_digest']}")
        print("[demo] PASS — full SDK → CLI loop verified.")


if __name__ == "__main__":
    main()
