"""Neutral registry index for Verifiable Decision Records (spec §5.2).

The registry is a public, append-only index of anchored ``record_digest``s — a
**discovery and network layer, not a source of trust**. Each entry is
self-verifying: its proof of existence rests on its anchor (Bitcoin, via
OpenTimestamps — spec §5.1), never on the index operator, and never on us. A
Verifier re-checks each entry's anchor; it does not take the index's word.

The index receives **only digests and anchor metadata — never the subject**.
The decision payload never leaves the Producer's environment.

An entry::

    {
      "record_digest": "<hex>",
      "profile": "<profile-id>",          # optional
      "anchor": { ...spec §5.1 anchor... },
      "registered_at": "<RFC3339 UTC>"
    }

The canonical instance is published as a static newline-delimited JSON file
(JSONL) — no server to operate. The format is open: anyone may host their own
index, since trust never rests on the host.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, List, Optional

from determs.anchor import ANCHOR_TYPE, verify_anchor


def _now_rfc3339() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _check_digest(record_digest: str) -> None:
    if len(bytes.fromhex(record_digest.strip())) != 32:
        raise ValueError("record_digest must be a 32-byte (64 hex char) SHA-256")


def make_entry(
    record_digest: str,
    anchor: dict,
    *,
    profile: Optional[str] = None,
    registered_at: Optional[str] = None,
) -> dict:
    """Build a registry index entry from a record_digest and its anchor.

    Only the digest, profile, anchor and a timestamp are recorded — never the
    subject.
    """
    _check_digest(record_digest)
    if not isinstance(anchor, dict) or anchor.get("type") != ANCHOR_TYPE:
        raise ValueError(f"entry requires an anchor of type {ANCHOR_TYPE!r}")
    entry: dict = {"record_digest": record_digest}
    if profile:
        entry["profile"] = profile
    entry["anchor"] = anchor
    entry["registered_at"] = registered_at or _now_rfc3339()
    return entry


def entry_from_vdr(vdr: dict) -> dict:
    """Build an index entry from an anchored VDR (see determs.anchor.anchor_record)."""
    try:
        digest = vdr["receipt"]["record_digest"]
    except (KeyError, TypeError):
        raise ValueError("vdr has no receipt.record_digest")
    anchor = vdr.get("anchor")
    if not anchor:
        raise ValueError("vdr has no anchor — anchor it first (determs.anchor.anchor_record)")
    return make_entry(digest, anchor, profile=vdr.get("profile"))


def verify_entry(entry: dict) -> dict:
    """Verify an entry *without trusting the index*: re-check that the anchor
    commits to the entry's record_digest. Returns the anchor report plus the
    digest. ``committed`` is the integrity check; ``status`` is pending/complete.
    """
    digest = entry.get("record_digest", "")
    report = verify_anchor(entry["anchor"], digest)
    return {"record_digest": digest, **report}


def append_entry(index_path: str, entry: dict) -> None:
    """Append one entry as a JSON line to a JSONL index file."""
    with open(index_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, separators=(",", ":"), ensure_ascii=False) + "\n")


def read_index(index_path: str) -> List[dict]:
    """Read all entries from a JSONL index file."""
    entries: List[dict] = []
    with open(index_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def verify_index(index_path: str) -> dict:
    """Verify every entry in an index (each against its own anchor)."""
    results = [verify_entry(e) for e in read_index(index_path)]
    return {
        "count": len(results),
        "all_committed": all(r["committed"] for r in results),
        "entries": results,
    }
