"""Determs Python SDK — capture each AI agent decision as a verifiable, replayable record.

Capture each LLM call as a structured, replayable record. Persist records
locally (or wherever you want). Verify and replay them later with the
``determs`` CLI.

Quick start::

    import determs
    from determs.anthropic import wrap as wrap_anthropic
    import anthropic

    storage = determs.storage.FileStorage("./determs_records")
    client = wrap_anthropic(
        anthropic.Anthropic(),
        agent_id="support-triage",
        storage=storage,
    )

    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=512,
        messages=[{"role": "user", "content": "Hi"}],
    )
    # A record has been written under ./determs_records/{action_id}.json.
"""

from determs.record import ActionRecord, build_record
from determs import storage
from determs import anchor
from determs import registry
from determs import compliance
from determs.anchor import anchor_digest, anchor_record, attach_anchor, verify_anchor
from determs.compliance import build_evidence_pack, pack_from_vdrs, verify_evidence_pack

__all__ = [
    "ActionRecord",
    "build_record",
    "storage",
    "anchor",
    "anchor_digest",
    "anchor_record",
    "attach_anchor",
    "verify_anchor",
    "registry",
    "compliance",
    "build_evidence_pack",
    "pack_from_vdrs",
    "verify_evidence_pack",
]
__version__ = "0.1.0"
