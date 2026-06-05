"""Tests for evidence packs (determs.compliance).

Offline + deterministic: anchors are built directly (no network), so pack
verification runs without OpenTimestamps calendars or a Bitcoin node.
"""

import hashlib

import pytest

pytest.importorskip("opentimestamps")  # packs carry/verify OTS anchors

from determs.anchor import ANCHOR_TYPE, _serialize  # noqa: E402
from determs.compliance import (  # noqa: E402
    build_evidence_pack,
    pack_digest,
    pack_from_vdrs,
    verify_evidence_pack,
)
from determs.registry import make_entry  # noqa: E402

A = hashlib.sha256(b"record-a").hexdigest()
B = hashlib.sha256(b"record-b").hexdigest()


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


def _entry(digest: str, profile: str = "ai.agent.action") -> dict:
    return make_entry(digest, _pending_anchor(digest), profile=profile)


def test_pack_digest_is_membership_content_address():
    # order-independent and de-duplicating
    assert pack_digest([A, B]) == pack_digest([B, A, A])
    # changing membership changes the digest
    assert pack_digest([A]) != pack_digest([A, B])
    # reproducible from the documented preimage
    preimage = "".join(d + "\n" for d in sorted({A, B})).encode("ascii")
    assert pack_digest([A, B]) == hashlib.sha256(preimage).hexdigest()


def test_build_pack_shape_and_no_subject():
    pack = build_evidence_pack(
        [_entry(A), _entry(B)],
        system="support-triage",
        period_from="2026-01-01T00:00:00Z",
        period_to="2026-06-30T23:59:59Z",
    )
    assert pack["evidence_pack_version"] == "0"
    assert pack["scope"]["system"] == "support-triage"
    assert pack["scope"]["period"]["from"] == "2026-01-01T00:00:00Z"
    assert pack["scope"]["profiles"] == ["ai.agent.action"]
    assert pack["count"] == 2
    assert pack["pack_digest"] == pack_digest([A, B])
    # the subject never appears anywhere in the pack
    for rec in pack["records"]:
        assert "subject" not in rec


def test_regulation_mapping_is_embedded():
    pack = build_evidence_pack([_entry(A)], system="s", articles=("12", "19"))
    reg = pack["regulation"]
    assert reg["framework"] == "eu-ai-act"
    assert set(reg["articles"]) == {"12", "19"}
    # self-contained + citable: each article carries requires/evidence prose
    assert reg["mapping"]["12"]["title"]
    assert reg["mapping"]["19"]["requires"]
    assert reg["mapping"]["19"]["evidence"]


def test_unknown_framework_or_article_raises():
    with pytest.raises(ValueError):
        build_evidence_pack([_entry(A)], system="s", framework="nope")
    with pytest.raises(ValueError):
        build_evidence_pack([_entry(A)], system="s", articles=("99",))


def test_entry_without_anchor_is_rejected():
    with pytest.raises(ValueError):
        build_evidence_pack([{"record_digest": A}], system="s")


def test_verify_pack_ok_pending_coverage():
    pack = build_evidence_pack([_entry(A), _entry(B)], system="s")
    rep = verify_evidence_pack(pack)
    assert rep["pack_digest_ok"] is True
    assert rep["count"] == 2
    assert rep["all_committed"] is True
    assert rep["all_complete"] is False  # pending anchors, no block yet
    assert rep["coverage"] == {"complete": 0, "pending": 2, "uncommitted": 0}


def test_verify_detects_tampered_membership():
    pack = build_evidence_pack([_entry(A), _entry(B)], system="s")
    pack["records"].pop()  # drop a record but keep the old pack_digest
    rep = verify_evidence_pack(pack)
    assert rep["pack_digest_ok"] is False  # membership no longer matches


def test_verify_detects_bad_anchor():
    # an entry whose anchor commits to a *different* digest
    bad = make_entry(A, _pending_anchor(B))
    pack = build_evidence_pack([bad], system="s")
    rep = verify_evidence_pack(pack)
    assert rep["all_committed"] is False
    assert rep["coverage"]["uncommitted"] == 1


def test_pack_from_vdrs():
    vdr = {
        "profile": "ai.agent.action",
        "receipt": {"record_digest": A},
        "anchor": _pending_anchor(A),
    }
    pack = pack_from_vdrs([vdr], system="s")
    assert pack["count"] == 1
    assert pack["records"][0]["record_digest"] == A
    assert "subject" not in pack["records"][0]
