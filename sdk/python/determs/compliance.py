"""Evidence packs for verifiable AI-decision compliance (VDR spec; EU AI Act).

An **evidence pack** is a self-contained, self-verifying bundle of anchored VDR
``record_digest``s for one system over one period, mapped to the record-keeping
and retention duties of a regulation (EU AI Act Articles 12 & 19). It is built
from registry entries — **only digests and anchors, never the subject** — so the
decision payload never leaves the Producer's environment.

What it is, precisely:

- an **aggregate over registry entries** (VDR spec §5.2): the evidence layer of
  the sequence spec -> registry -> compliance, each layer thin and built on the
  one below;
- **non-trust-bearing**, like the registry: the pack vouches for nothing on its
  own authority. Its evidentiary weight is the union of its members' anchors,
  each re-verified against public infrastructure. An auditor trusts the maths,
  not the pack, and not us;
- the **evidence layer, not a compliance certificate**. It proves the records
  exist, are intact, and were anchored in time. It does **not** classify your
  system, write your risk assessment, or stand in for the rest of your
  compliance programme.

Building a pack needs no network. Verifying one re-checks every anchor and needs
the optional anchoring dependency::

    pip install "determs[anchor]"

See ``docs/spec/evidence-pack-v0.md`` for the format.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

from determs.registry import entry_from_vdr, verify_entry

EVIDENCE_PACK_VERSION = "0"

# Machine-readable mapping from a regulation's record duties to what a pack of
# anchored VDRs provides as evidence. Descriptive and citable — the pack carries
# the relevant slice so an auditor needs no external lookup. Not a legal opinion.
REGULATIONS: Dict[str, dict] = {
    "eu-ai-act": {
        "framework": "eu-ai-act",
        "name": "EU Artificial Intelligence Act (Regulation (EU) 2024/1689)",
        "articles": {
            "12": {
                "title": "Record-keeping",
                "requires": (
                    "High-risk AI systems must technically allow for the "
                    "automatic recording of events (logs) over the lifetime of "
                    "the system."
                ),
                "evidence": (
                    "Each decision is captured at the moment it happens as a "
                    "structured, self-describing Verifiable Decision Record."
                ),
            },
            "19": {
                "title": "Retention of automatically generated logs",
                "requires": (
                    "Providers must retain the automatically generated logs for "
                    "a period appropriate to the purpose, at least six months."
                ),
                "evidence": (
                    "Each record's digest is anchored to public infrastructure, "
                    "so its existence in time is provable -- not merely asserted "
                    "-- across the retention window."
                ),
            },
        },
    },
}

DEFAULT_ARTICLES = ("12", "19")


def _now_rfc3339() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def pack_digest(record_digests: Iterable[str]) -> str:
    r"""Content address of an evidence pack's membership set.

    Defined as the SHA-256 of the sorted, de-duplicated member ``record_digest``s
    (lowercase hex), each followed by a newline::

        sha256( "".join(d + "\n" for d in sorted(set(digests))) )

    Pure hex + ASCII: reproducible in any language, with no canonicalization
    ambiguity. It binds the *membership* of the pack -- you cannot add or drop a
    record without changing it -- but it is **not** a VDR ``record_digest`` and
    makes no claim about the scope or regulation metadata.
    """
    uniq = sorted({d.strip().lower() for d in record_digests})
    preimage = "".join(d + "\n" for d in uniq).encode("ascii")
    return hashlib.sha256(preimage).hexdigest()


def _regulation_slice(framework: str, articles: Sequence[str]) -> dict:
    reg = REGULATIONS.get(framework)
    if reg is None:
        raise ValueError(f"unknown regulation framework: {framework!r}")
    missing = [a for a in articles if a not in reg["articles"]]
    if missing:
        raise ValueError(f"{framework}: no mapping for article(s) {missing}")
    return {
        "framework": reg["framework"],
        "name": reg["name"],
        "articles": list(articles),
        "mapping": {a: reg["articles"][a] for a in articles},
    }


def build_evidence_pack(
    entries: Sequence[dict],
    *,
    system: str,
    period_from: Optional[str] = None,
    period_to: Optional[str] = None,
    framework: str = "eu-ai-act",
    articles: Sequence[str] = DEFAULT_ARTICLES,
    generated_at: Optional[str] = None,
) -> dict:
    """Assemble an evidence pack from registry entries (digest + anchor, no subject).

    ``entries`` are registry entries (see :mod:`determs.registry`). Each MUST
    carry a ``record_digest`` and an ``anchor``, and MUST NOT carry the subject.
    Building needs no network.
    """
    entries = list(entries)
    for e in entries:
        if "record_digest" not in e or "anchor" not in e:
            raise ValueError("each entry needs a record_digest and an anchor")
        if "subject" in e:
            raise ValueError("an evidence pack entry must never carry the subject")

    profiles = sorted({e["profile"] for e in entries if e.get("profile")})
    scope: Dict[str, Any] = {"system": system, "profiles": profiles}
    if period_from or period_to:
        scope["period"] = {"from": period_from, "to": period_to}

    return {
        "evidence_pack_version": EVIDENCE_PACK_VERSION,
        "scope": scope,
        "regulation": _regulation_slice(framework, articles),
        "count": len(entries),
        "records": entries,
        "pack_digest": pack_digest(e["record_digest"] for e in entries),
        "generated_at": generated_at or _now_rfc3339(),
    }


def pack_from_vdrs(vdrs: Iterable[dict], **kwargs: Any) -> dict:
    """Build an evidence pack directly from anchored VDRs.

    Convenience over :func:`build_evidence_pack`: maps each VDR to a registry
    entry (``determs.registry.entry_from_vdr`` -- digest + anchor, never the
    subject) first. Every VDR MUST already be anchored.
    """
    return build_evidence_pack([entry_from_vdr(v) for v in vdrs], **kwargs)


def verify_evidence_pack(pack: dict) -> dict:
    """Verify a pack *without trusting it*.

    Recomputes ``pack_digest`` from the members and re-verifies every member's
    anchor against public infrastructure (via
    :func:`determs.registry.verify_entry`).

    Returns::

        {
          "pack_digest_ok": bool,        # membership intact
          "count": int,
          "all_committed": bool,         # every anchor commits to its digest
          "all_complete": bool,          # every anchor reached a Bitcoin block
          "coverage": {"complete": int, "pending": int, "uncommitted": int},
          "entries": [ ...per-entry anchor reports... ],
        }

    This reports **integrity and existence-in-time**. It does not -- and cannot
    -- certify legal compliance.
    """
    records: List[dict] = list(pack.get("records", []))
    recomputed = pack_digest(r.get("record_digest", "") for r in records)
    results = [verify_entry(r) for r in records]

    complete = sum(1 for r in results if r["status"] == "complete")
    pending = sum(1 for r in results if r["status"] == "pending")
    uncommitted = sum(1 for r in results if not r["committed"])

    return {
        "pack_digest_ok": recomputed == pack.get("pack_digest"),
        "count": len(results),
        "all_committed": all(r["committed"] for r in results) if results else True,
        "all_complete": bool(results) and complete == len(results),
        "coverage": {
            "complete": complete,
            "pending": pending,
            "uncommitted": uncommitted,
        },
        "entries": results,
    }
