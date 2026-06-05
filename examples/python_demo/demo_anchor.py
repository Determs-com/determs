"""Anchor a record_digest to public infrastructure (OpenTimestamps → Bitcoin).

    pip install "determs[anchor]"
    python demo_anchor.py

Submits the digest to public OpenTimestamps calendars (free, no account) and
prints the resulting anchor object. The proof starts ``"pending"``; ~1–2h later
``determs.anchor.upgrade(anchor)`` folds in the Bitcoin block attestation and it
becomes ``"complete"``. Only the digest is ever transmitted — never the
decision payload.
"""

import hashlib
import json

from determs.anchor import anchor_digest, upgrade, verify_anchor

# In practice this is receipt.record_digest from a VDR. Any SHA-256 hex works.
record_digest = hashlib.sha256(b"a verifiable decision record").hexdigest()
print("record_digest:", record_digest)

anchor = anchor_digest(record_digest)
shown = {**anchor, "proof": anchor["proof"][:48] + "…"}
print("anchor:", json.dumps(shown, indent=2))

print("verify:", verify_anchor(anchor, record_digest))

# Later (after the calendar's Bitcoin tx confirms, ~1–2h):
anchor = upgrade(anchor)
print("after upgrade — status:", anchor["status"])
print(
    "\nWhile 'pending', this proves submission to a calendar, not yet existence "
    "in a block.\nOnce 'complete', anyone can verify it against Bitcoin — no "
    "trust in Determs required."
)
