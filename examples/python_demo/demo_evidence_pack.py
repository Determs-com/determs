"""Demo: build and verify a compliance evidence pack (EU AI Act Art. 12 & 19).

Shows the evidence layer of the sequence spec -> registry -> compliance: take
anchored decision records, bundle them into a self-verifying pack scoped to one
system and period, then verify it the way an auditor would -- against public
infrastructure, trusting no one.

Offline by design: the anchors here are constructed locally so the demo runs
with just ``pip install "determs[anchor]"`` and no network. In production you
would anchor real records with ``determs.anchor.anchor_record`` (which submits
only the digest to public timestamp infrastructure).
"""

import hashlib

from determs.anchor import ANCHOR_TYPE, _serialize
from determs.compliance import build_evidence_pack, verify_evidence_pack
from determs.registry import make_entry


def offline_anchor(digest_hex: str) -> dict:
    """A pending anchor built locally (no network) -- for the demo only."""
    from opentimestamps.core.notary import PendingAttestation
    from opentimestamps.core.op import OpSHA256
    from opentimestamps.core.timestamp import DetachedTimestampFile, Timestamp

    ts = Timestamp(bytes.fromhex(digest_hex))
    ts.attestations.add(PendingAttestation("https://example.test/calendar"))
    return {
        "type": ANCHOR_TYPE,
        "anchored_at": "2026-06-04T09:00:00Z",
        "proof": _serialize(DetachedTimestampFile(OpSHA256(), ts)),
        "status": "pending",
    }


def main() -> None:
    # Three decisions made by one system over a period. Only their digests +
    # anchors enter the pack; the decision payloads stay home.
    digests = [hashlib.sha256(f"decision-{i}".encode()).hexdigest() for i in range(3)]
    entries = [make_entry(d, offline_anchor(d), profile="ai.agent.action") for d in digests]

    pack = build_evidence_pack(
        entries,
        system="support-triage",
        period_from="2026-01-01T00:00:00Z",
        period_to="2026-06-30T23:59:59Z",
    )

    print("evidence pack")
    print("  system     :", pack["scope"]["system"])
    print("  period     :", pack["scope"]["period"]["from"], "->", pack["scope"]["period"]["to"])
    print("  articles   :", ", ".join(pack["regulation"]["articles"]),
          f'({pack["regulation"]["framework"]})')
    print("  records    :", pack["count"])
    print("  pack_digest:", pack["pack_digest"])

    print("\nverification (as an auditor would -- against public infrastructure):")
    report = verify_evidence_pack(pack)
    print("  membership intact                    :", report["pack_digest_ok"])
    print("  every record committed to its anchor :", report["all_committed"])
    print("  coverage                             :", report["coverage"])
    print("  fully confirmed in a block           :", report["all_complete"],
          "(pending here -- offline demo)")

    print("\nregulation mapping carried in the pack:")
    for art, m in pack["regulation"]["mapping"].items():
        print(f"  Art. {art} -- {m['title']}")
        print(f"      requires: {m['requires']}")
        print(f"      evidence: {m['evidence']}")


if __name__ == "__main__":
    main()
