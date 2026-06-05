"""Tests for the neutral registry index (determs.registry).

Offline + deterministic: anchors are built directly (no network), so entry
verification runs without OpenTimestamps calendars or a Bitcoin node.
"""

import hashlib
import os
import tempfile

import pytest

pytest.importorskip("opentimestamps")  # entries carry/verify OTS anchors

from determs.anchor import ANCHOR_TYPE, _serialize  # noqa: E402
from determs.registry import (  # noqa: E402
    append_entry,
    entry_from_vdr,
    make_entry,
    read_index,
    verify_entry,
    verify_index,
)

DIGEST = hashlib.sha256(b"determs-registry-test").hexdigest()
OTHER = hashlib.sha256(b"another-record").hexdigest()


def _pending_anchor(digest_hex: str) -> dict:
    from opentimestamps.core.notary import PendingAttestation
    from opentimestamps.core.op import OpSHA256
    from opentimestamps.core.timestamp import DetachedTimestampFile, Timestamp

    ts = Timestamp(bytes.fromhex(digest_hex))
    ts.attestations.add(PendingAttestation("https://example.test/calendar"))
    return {
        "type": ANCHOR_TYPE,
        "anchored_at": "2026-06-03T10:00:00Z",
        "proof": _serialize(DetachedTimestampFile(OpSHA256(), ts)),
        "status": "pending",
    }


def test_make_entry_records_only_digest_and_anchor():
    entry = make_entry(DIGEST, _pending_anchor(DIGEST), profile="ai.agent.action")
    assert entry["record_digest"] == DIGEST
    assert entry["profile"] == "ai.agent.action"
    assert entry["anchor"]["type"] == ANCHOR_TYPE
    assert "registered_at" in entry
    # the subject must never appear in an entry
    assert "subject" not in entry


def test_make_entry_requires_an_anchor():
    with pytest.raises(ValueError):
        make_entry(DIGEST, {"type": "none"})


def test_verify_entry_is_non_trust_bearing():
    entry = make_entry(DIGEST, _pending_anchor(DIGEST))
    rep = verify_entry(entry)
    assert rep["committed"] is True
    assert rep["record_digest"] == DIGEST
    # a tampered entry (anchor for a different digest) fails the commitment
    bad = make_entry(DIGEST, _pending_anchor(OTHER))
    assert verify_entry(bad)["committed"] is False


def test_entry_from_vdr_requires_anchor():
    vdr = {"profile": "ai.agent.action", "receipt": {"record_digest": DIGEST}}
    with pytest.raises(ValueError):
        entry_from_vdr(vdr)  # not anchored yet
    vdr["anchor"] = _pending_anchor(DIGEST)
    entry = entry_from_vdr(vdr)
    assert entry["record_digest"] == DIGEST
    assert entry["profile"] == "ai.agent.action"


def test_append_and_verify_index_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "index.jsonl")
        append_entry(path, make_entry(DIGEST, _pending_anchor(DIGEST), profile="ai.agent.action"))
        append_entry(path, make_entry(OTHER, _pending_anchor(OTHER)))
        entries = read_index(path)
        assert len(entries) == 2
        report = verify_index(path)
        assert report["count"] == 2
        assert report["all_committed"] is True
