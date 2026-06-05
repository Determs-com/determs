<!--
doc: SPEC — Evidence Pack
role: open-specification (companion to the VDR spec)
status: draft v0
canonical: true
-->

# Evidence Pack — Specification v0

Status: **Draft v0**. Companion to the
[Verifiable Decision Record](verifiable-decision-record-v0.md) spec and the
[Registry Index](registry-index-v0.md). Licensed CC-BY-4.0.

## 0. What it is — and is not

An **evidence pack** is a self-contained bundle of anchored VDR
`record_digest`s for **one system over one period**, mapped to the
record-keeping and retention duties of a regulation (here, the EU AI Act,
Articles 12 and 19). It is the **evidence layer** of the sequence
spec → registry → compliance: an aggregate built over registry entries
(VDR spec §5.2), each layer thin and resting on the one below.

It is **the evidence, not a compliance certificate.** A pack proves that a set
of records exists, is intact, and was anchored in time. It does **not** classify
your system, write your risk assessment, stand in for a data-protection impact
assessment, or assert that you are compliant. It makes the *records* auditable —
the part that is hardest to retrofit and easiest to be caught without.

It is **non-trust-bearing**, exactly like the registry. The pack vouches for
nothing on its own authority. Its evidentiary weight is the **union of its
members' anchors**, each re-verified against public infrastructure (VDR spec
§5–§7). An auditor trusts the mathematics — not the pack, not its producer, and
not the authors of this spec.

It is **privacy-preserving.** A pack carries **only digests and anchor
metadata — never the `subject`.** The decision payload never leaves the
Producer's environment, which keeps the pack compatible with data-protection
obligations (e.g. the GDPR) that arrive alongside the AI Act.

## 1. Structure

An evidence pack is a JSON object:

```
{
  "evidence_pack_version": "0",
  "scope": {
    "system": "support-triage",            // REQUIRED — the system/agent under audit
    "profiles": ["ai.agent.action"],       // VDR profiles present in the pack
    "period": {                            // OPTIONAL — the retention window covered
      "from": "2026-01-01T00:00:00Z",
      "to":   "2026-06-30T23:59:59Z"
    }
  },
  "regulation": {                          // the duties this pack provides evidence for
    "framework": "eu-ai-act",
    "name": "EU Artificial Intelligence Act (Regulation (EU) 2024/1689)",
    "articles": ["12", "19"],
    "mapping": { "12": { ... }, "19": { ... } }   // §3 — carried in the pack, self-contained
  },
  "count": 3,
  "records": [                             // registry entries — digest + anchor, NEVER the subject
    { "record_digest": "<hex>", "profile": "<id>", "anchor": { ... §5.1 ... }, "registered_at": "..." },
    ...
  ],
  "pack_digest": "<hex sha-256>",          // §2 — content address of the membership set
  "generated_at": "2026-06-04T09:00:00Z"   // informational
}
```

Each element of `records` is a **registry index entry** (Registry Index spec
§1): it MUST carry a `record_digest` and an `anchor`, and MUST NOT carry the
`subject` or any part of it.

## 2. `pack_digest` — membership content address

`pack_digest` binds **which records** are in the pack. It is defined as the
SHA-256 of the sorted, de-duplicated member `record_digest`s (lowercase hex),
each followed by a newline (`U+000A`):

```
pack_digest = SHA-256( concat( d + "\n" for d in sorted(unique(record_digests)) ) )
```

The preimage is pure hex and ASCII, so the value is reproducible in any language
with no canonicalization ambiguity — it does not depend on RFC 8785 (JCS), key
order, or number formatting. Trivially:

```bash
# given one digest per line in digests.txt
sort -u digests.txt | awk '{printf "%s\n", $0}' | sha256sum
```

`pack_digest` is **not** a VDR `record_digest` and makes no claim about the
`scope` or `regulation` metadata; it binds membership only. You cannot add or
drop a record without changing it. Because every member is independently
anchored, you cannot smuggle in a record that does not carry its own proof.

A pack may itself be anchored (VDR spec §5) by anchoring its `pack_digest`, to
prove that *this exact set of records* was assembled at a point in time.

## 3. Regulation mapping

The pack carries the relevant slice of the regulation mapping so it is
self-contained — an auditor reads what each duty requires and what the pack
provides without an external lookup. For the EU AI Act:

| Article | Requires | What the pack provides |
|---|---|---|
| **12 — Record-keeping** | High-risk AI systems must technically allow automatic recording of events (logs) over the lifetime of the system. | Each decision is captured at the moment it happens as a structured, self-describing VDR. The pack enumerates them for the scope. |
| **19 — Retention** | Providers must retain the automatically generated logs for an appropriate period, **at least six months**. | Each record's digest is anchored to public infrastructure, so its existence in time is provable — not merely asserted — across the retention window. |

The mapping is descriptive and citable. It is **not** a legal opinion; it states
which technical property answers which duty. Article coverage is declared in
`regulation.articles`; other frameworks MAY be added under their own `framework`
key without changing the format.

## 4. Verification

Given a pack, a Verifier — typically an auditor or a market-surveillance
authority (AI Act Art. 72) — establishes two things, **trusting no one**:

1. **Membership is intact.** Recompute `pack_digest` from `records` (§2) and
   compare. A mismatch means the set was altered after assembly.
2. **Each record exists and is unaltered.** For every entry, verify its `anchor`
   per VDR spec §5–§7: the anchor MUST commit to the entry's `record_digest`,
   and a `"complete"` anchor MUST resolve to the claimed public infrastructure
   (a Bitcoin block for `opentimestamps`). A `"pending"` anchor proves
   submission to a calendar, not yet existence in a block — it is not yet a
   time-proof.

A conforming verifier reports **integrity and existence-in-time**: how many
records are committed, how many anchors are `complete` vs `pending`. It does
**not** — and cannot — certify legal compliance. The reference implementation
(`determs.compliance.verify_evidence_pack`) returns this report.

An entry that fails (2) is invalid regardless of its presence in the pack, and a
pack that fails (1) has been tampered with.

## 5. Status

Draft v0, with a reference implementation in the Python SDK
(`determs.compliance`: `build_evidence_pack`, `pack_from_vdrs`,
`verify_evidence_pack`). The evidence pack is the **open, self-verifiable
primitive** of the compliance layer — you can produce and check your own pack,
in your own environment, against public infrastructure, with no account and no
trusted third party. A managed evidence layer (continuous capture, hosted
retention across the multi-year window, auditor-facing export and monitoring)
sits on top of these same packs — a hosted convenience over the open primitive,
which never becomes a source of trust.
