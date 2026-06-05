"""Tests for OpenTimestamps anchoring (determs.anchor).

Offline + deterministic: pending and Bitcoin attestations are built directly,
so no network or Bitcoin node is needed. A single live submission test is
gated behind DETERMS_OTS_LIVE=1.
"""

import hashlib
import os

import pytest

pytest.importorskip("opentimestamps")  # skip if the [anchor] extra isn't installed

from determs.anchor import (  # noqa: E402
    ANCHOR_TYPE,
    _digest_bytes,
    _serialize,
    anchor_digest,
    anchor_record,
    attach_anchor,
    verify_anchor,
)

DIGEST = hashlib.sha256(b"determs-test-record").hexdigest()
OTHER = hashlib.sha256(b"a-different-record").hexdigest()


def _pending_proof(digest_hex: str) -> str:
    from opentimestamps.core.notary import PendingAttestation
    from opentimestamps.core.op import OpSHA256
    from opentimestamps.core.timestamp import DetachedTimestampFile, Timestamp

    ts = Timestamp(bytes.fromhex(digest_hex))
    ts.attestations.add(PendingAttestation("https://example.test/calendar"))
    return _serialize(DetachedTimestampFile(OpSHA256(), ts))


def _bitcoin_proof(digest_hex: str, height: int = 800001) -> str:
    from opentimestamps.core.notary import BitcoinBlockHeaderAttestation
    from opentimestamps.core.op import OpSHA256
    from opentimestamps.core.timestamp import DetachedTimestampFile, Timestamp

    ts = Timestamp(bytes.fromhex(digest_hex))
    ts.attestations.add(BitcoinBlockHeaderAttestation(height))
    return _serialize(DetachedTimestampFile(OpSHA256(), ts))


def _anchor(proof: str, status: str = "pending") -> dict:
    return {
        "type": ANCHOR_TYPE,
        "anchored_at": "2026-06-03T10:00:00Z",
        "proof": proof,
        "status": status,
    }


def test_pending_anchor_commits_but_is_not_a_time_proof():
    rep = verify_anchor(_anchor(_pending_proof(DIGEST)), DIGEST)
    assert rep["committed"] is True
    assert rep["status"] == "pending"
    assert rep["bitcoin_block_height"] is None


def test_complete_anchor_reports_bitcoin_block():
    rep = verify_anchor(_anchor(_bitcoin_proof(DIGEST, 800123), "complete"), DIGEST)
    assert rep["committed"] is True
    assert rep["status"] == "complete"
    assert rep["bitcoin_block_height"] == 800123


def test_verify_detects_wrong_digest():
    rep = verify_anchor(_anchor(_pending_proof(DIGEST)), OTHER)
    assert rep["committed"] is False


def test_attach_anchor_is_additive_and_leaves_receipt_untouched():
    vdr = {
        "vdr_version": "0",
        "profile": "ai.agent.action",
        "subject": {"agent_id": "a"},
        "receipt": {"alg": "sha-256", "record_digest": DIGEST},
    }
    anchor = _anchor(_pending_proof(DIGEST))
    out = attach_anchor(vdr, anchor)
    assert out is vdr
    assert out["anchor"] is anchor
    assert out["receipt"]["record_digest"] == DIGEST  # unchanged


def test_anchor_record_uses_receipt_digest(monkeypatch):
    import determs.anchor as mod

    captured = {}

    def fake_anchor_digest(digest, **kwargs):
        captured["digest"] = digest
        return _anchor(_pending_proof(digest))

    monkeypatch.setattr(mod, "anchor_digest", fake_anchor_digest)
    vdr = {"receipt": {"record_digest": DIGEST}}
    out = anchor_record(vdr)
    assert captured["digest"] == DIGEST
    assert out["anchor"]["type"] == ANCHOR_TYPE


def test_attach_anchor_rejects_unknown_type():
    with pytest.raises(ValueError):
        attach_anchor({}, {"type": "rekor"})


def test_digest_bytes_rejects_bad_length():
    with pytest.raises(ValueError):
        _digest_bytes("abcd")  # not 32 bytes


def test_anchor_record_without_receipt_digest_raises():
    with pytest.raises(ValueError):
        anchor_record({"subject": {}})


@pytest.mark.skipif(
    os.environ.get("DETERMS_OTS_LIVE") != "1",
    reason="set DETERMS_OTS_LIVE=1 to run the live OpenTimestamps submission",
)
def test_live_submission_produces_a_committed_pending_proof():
    anchor = anchor_digest(DIGEST, timeout=20)
    assert anchor["type"] == ANCHOR_TYPE
    assert anchor["status"] == "pending"
    rep = verify_anchor(anchor, DIGEST)
    assert rep["committed"] is True
