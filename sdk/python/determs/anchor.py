"""OpenTimestamps anchoring for Verifiable Decision Records (VDR spec §5).

Anchors a ``record_digest`` to public infrastructure — the Bitcoin blockchain,
via OpenTimestamps calendar servers — to obtain a *trustless* proof of
existence in time. Only the ``record_digest`` is ever transmitted; the
``subject`` and the full Record never leave the Producer's environment.

The resulting ``anchor`` object matches spec §5.1::

    {
      "type": "opentimestamps",
      "anchored_at": "2026-06-03T10:00:00Z",   # informational, not load-bearing
      "proof": "<base64 of the .ots proof for record_digest>",
      "status": "pending" | "complete"
    }

A fresh proof is ``"pending"`` (committed to a calendar, not yet to a confirmed
Bitcoin block). Call :func:`upgrade` after ~1–2h to fold in the Bitcoin block
attestation and reach ``"complete"``.

Requires the optional dependency::

    pip install "determs[anchor]"
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any, Iterator, Optional, Tuple

ANCHOR_TYPE = "opentimestamps"

# Public OpenTimestamps calendar servers (free, no account). A proof is valid
# as soon as at least one accepts the submission.
DEFAULT_CALENDARS: Tuple[str, ...] = (
    "https://alice.btc.calendar.opentimestamps.org",
    "https://bob.btc.calendar.opentimestamps.org",
    "https://finney.calendar.eternitywall.com",
)

_MISSING = (
    "OpenTimestamps anchoring requires the optional dependency. "
    'Install it with:  pip install "determs[anchor]"'
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _now_rfc3339() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _digest_bytes(record_digest: str) -> bytes:
    """Decode a hex SHA-256 record_digest to its 32 raw bytes."""
    raw = bytes.fromhex(record_digest.strip())
    if len(raw) != 32:
        raise ValueError(
            f"record_digest must be a 32-byte (64 hex char) SHA-256, got {len(raw)} bytes"
        )
    return raw


def _check_type(anchor: Any) -> None:
    t = anchor.get("type") if isinstance(anchor, dict) else None
    if t != ANCHOR_TYPE:
        raise ValueError(f"unsupported anchor type: {t!r} (expected {ANCHOR_TYPE!r})")


def _serialize(detached: Any) -> str:
    from opentimestamps.core.serialize import BytesSerializationContext

    ctx = BytesSerializationContext()
    detached.serialize(ctx)
    return base64.b64encode(ctx.getbytes()).decode("ascii")


def _deserialize(proof_b64: str) -> Any:
    from opentimestamps.core.serialize import BytesDeserializationContext
    from opentimestamps.core.timestamp import DetachedTimestampFile

    return DetachedTimestampFile.deserialize(
        BytesDeserializationContext(base64.b64decode(proof_b64))
    )


def _iter_timestamps(ts: Any) -> Iterator[Tuple[bytes, Any]]:
    """Yield ``(msg, timestamp)`` for every node in the timestamp tree."""
    yield ts.msg, ts
    for _op, sub in ts.ops.items():
        yield from _iter_timestamps(sub)


def _bitcoin_height(ts: Any) -> Optional[int]:
    from opentimestamps.core.notary import BitcoinBlockHeaderAttestation

    for _msg, node in _iter_timestamps(ts):
        for att in node.attestations:
            if isinstance(att, BitcoinBlockHeaderAttestation):
                return att.height
    return None


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #

def anchor_digest(
    record_digest: str,
    *,
    calendars: Tuple[str, ...] = DEFAULT_CALENDARS,
    timeout: float = 20.0,
    anchored_at: Optional[str] = None,
) -> dict:
    """Submit ``record_digest`` (hex) to OpenTimestamps calendars and return a
    *pending* anchor object (spec §5.1).

    Only the digest is transmitted. Raises if no calendar accepts it.
    """
    try:
        from opentimestamps.core.op import OpSHA256
        from opentimestamps.core.timestamp import DetachedTimestampFile, Timestamp
        from opentimestamps.calendar import RemoteCalendar
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(_MISSING) from exc

    digest = _digest_bytes(record_digest)
    ts = Timestamp(digest)

    submitted = 0
    errors = []
    for url in calendars:
        try:
            ts.merge(RemoteCalendar(url).submit(ts.msg, timeout=timeout))
            submitted += 1
        except Exception as exc:  # network/calendar hiccup: tolerate if ≥1 succeeds
            errors.append(f"{url}: {exc}")

    if submitted == 0:
        raise RuntimeError(
            "no OpenTimestamps calendar accepted the submission — " + "; ".join(errors)
        )

    return {
        "type": ANCHOR_TYPE,
        "anchored_at": anchored_at or _now_rfc3339(),
        "proof": _serialize(DetachedTimestampFile(OpSHA256(), ts)),
        "status": "pending",
    }


def upgrade(anchor: dict, *, timeout: float = 20.0) -> dict:
    """Best-effort upgrade of a pending anchor: query the calendars for the
    Bitcoin attestation and fold it in. Returns a new anchor dict whose
    ``status`` is ``"complete"`` once a Bitcoin attestation is present.

    Safe to call repeatedly; it is a no-op once complete or while the calendar
    has not yet committed to a confirmed Bitcoin block (~1–2h after anchoring).
    """
    _check_type(anchor)
    try:
        from opentimestamps.core.notary import PendingAttestation
        from opentimestamps.calendar import RemoteCalendar
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(_MISSING) from exc

    detached = _deserialize(anchor["proof"])

    # collect pending (commitment, calendar uri, node) before mutating the tree
    todo = []
    for msg, node in list(_iter_timestamps(detached.timestamp)):
        for att in list(node.attestations):
            if isinstance(att, PendingAttestation):
                todo.append((msg, att.uri, node))

    changed = False
    for msg, uri, node in todo:
        try:
            node.merge(RemoteCalendar(uri).get_timestamp(msg))
            changed = True
        except Exception:
            pass  # not yet available, or calendar unreachable

    out = dict(anchor)
    if changed:
        out["proof"] = _serialize(detached)
    out["status"] = "complete" if _bitcoin_height(detached.timestamp) is not None else "pending"
    return out


def verify_anchor(anchor: dict, record_digest: str) -> dict:
    """Verify that ``anchor``'s proof commits to ``record_digest`` and report
    the Bitcoin attestation if present.

    Returns ``{"committed": bool, "status": "pending"|"complete",
    "bitcoin_block_height": int|None}``.

    ``committed`` is the trustless integrity check (the proof is about this
    exact digest). Confirming that the named Bitcoin block actually contains
    the attested value is a separate step requiring a Bitcoin node or block
    explorer — out of scope here; the proof is self-describing (it names the
    block height). A ``"pending"`` anchor is not yet a time-proof.
    """
    _check_type(anchor)
    expected = _digest_bytes(record_digest)
    detached = _deserialize(anchor["proof"])
    height = _bitcoin_height(detached.timestamp)
    return {
        "committed": detached.file_digest == expected,
        "status": "complete" if height is not None else "pending",
        "bitcoin_block_height": height,
    }


def attach_anchor(vdr: dict, anchor: dict) -> dict:
    """Attach an ``anchor`` object to a VDR dict (sets ``vdr["anchor"]``).

    Anchoring is additive: it does not affect any digest in ``receipt`` (spec
    §4 excludes ``anchor`` from ``record_digest``). Returns the same ``vdr``.
    """
    _check_type(anchor)
    vdr["anchor"] = anchor
    return vdr


def anchor_record(vdr: dict, **kwargs: Any) -> dict:
    """Anchor a full VDR by its ``receipt.record_digest`` and attach the result.

    Extra keyword arguments are forwarded to :func:`anchor_digest`.
    """
    try:
        digest = vdr["receipt"]["record_digest"]
    except (KeyError, TypeError):
        raise ValueError("vdr has no receipt.record_digest to anchor")
    return attach_anchor(vdr, anchor_digest(digest, **kwargs))
