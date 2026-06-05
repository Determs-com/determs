"""End-to-end: SDK-emitted record must be accepted by the Determs CLI.

This test invokes the real ``determs`` binary built from the workspace
root. It is skipped if the binary cannot be found.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from determs.record import build_record
from determs.storage import FileStorage


REPO_ROOT = Path(__file__).resolve().parents[3]
DETERMS_BIN_CANDIDATES = [
    REPO_ROOT / "target" / "release" / "determs",
    REPO_ROOT / "target" / "debug" / "determs",
]


def _find_determs() -> str | None:
    for candidate in DETERMS_BIN_CANDIDATES:
        if candidate.exists():
            return str(candidate)
    on_path = shutil.which("determs")
    return on_path


@pytest.fixture(scope="module")
def determs_bin() -> str:
    bin_path = _find_determs()
    if not bin_path:
        pytest.skip("determs binary not built; run `cargo build` from the repo root")
    return bin_path


def test_sdk_record_is_accepted_by_cli_execute(determs_bin: str):
    record = build_record(
        agent_id="sdk-test-agent",
        model={"provider": "anthropic", "name": "claude-3-5"},
        params={"temperature": 0.0},
        input={"messages": [{"role": "user", "content": "Hi"}]},
        output={"content": "Hello.", "finish_reason": "stop"},
    )
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "action.json"
        target.write_text(record.to_json(), encoding="utf-8")
        result = subprocess.run(
            [
                determs_bin,
                "execute",
                "agent.action.replay.v1",
                "--input",
                str(target),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        parsed = json.loads(result.stdout)
        data = parsed["output"]["data"]
        assert parsed["output"]["status"] == "accepted"
        assert data["agent_id"] == "sdk-test-agent"
        # Digests live in the VDR layer (capture), not in capsule execute output.
        assert "summary" in data


def test_sdk_capture_via_cli_roundtrips_verify(determs_bin: str):
    """Capture (wrap subject into a VDR), then verify integrity."""
    record = build_record(
        agent_id="sdk-test-agent",
        action_id="act-fixed-001",
        occurred_at_unix_ms="1747700000000",
        model={"provider": "openai", "name": "gpt-4o-mini"},
        input={"messages": [{"role": "user", "content": "Hello"}]},
        output={"content": "Hi back.", "finish_reason": "stop"},
    )
    with tempfile.TemporaryDirectory() as tmp:
        action_path = Path(tmp) / "action.json"
        record_path = Path(tmp) / "record.json"
        action_path.write_text(record.to_json(), encoding="utf-8")

        capture = subprocess.run(
            [
                determs_bin,
                "capture",
                "--input",
                str(action_path),
                "--output",
                str(record_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert capture.returncode == 0, capture.stderr
        assert record_path.exists()
        vdr = json.loads(record_path.read_text())
        assert vdr["vdr_version"] == "0"
        assert vdr["profile"] == "ai.agent.action"
        assert len(vdr["receipt"]["record_digest"]) == 64

        verify = subprocess.run(
            [determs_bin, "verify", "--record", str(record_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert verify.returncode == 0, verify.stderr
        report = json.loads(verify.stdout)
        assert report["verified"] is True
        assert all(report["checks"].values())


def test_filestorage_then_cli_verify_roundtrips(determs_bin: str):
    """The most realistic path: SDK writes file, CLI verifies."""
    with tempfile.TemporaryDirectory() as tmp:
        records_dir = Path(tmp) / "records"
        storage = FileStorage(str(records_dir))
        record = build_record(
            agent_id="sdk-test-agent",
            model={"provider": "anthropic", "name": "claude-3-5"},
            input={"messages": [{"role": "user", "content": "Hi"}]},
            output={"content": "Hello.", "finish_reason": "stop"},
        )
        emitted_path = Path(storage.put(record))
        record_path = Path(tmp) / "record.json"

        capture = subprocess.run(
            [
                determs_bin,
                "capture",
                "--input",
                str(emitted_path),
                "--output",
                str(record_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert capture.returncode == 0, capture.stderr

        verify = subprocess.run(
            [determs_bin, "verify", "--record", str(record_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert verify.returncode == 0, verify.stderr
