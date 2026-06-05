<!--
doc: SPEC — Registry Index
role: open-specification (companion to the VDR spec)
status: draft v0
canonical: true
-->

# Registry Index — Specification v0

Status: **Draft v0**. Companion to the
[Verifiable Decision Record](verifiable-decision-record-v0.md) spec (see §5.2).
Licensed CC-BY-4.0.

## 0. What it is — and is not

The registry is a **public, append-only index of anchored VDR
`record_digest`s**. Its job is **discovery and network effect**: a canonical
place to find that a record exists and was anchored in time.

It is **not a source of trust.** Each entry is self-verifying: its proof of
existence rests on its anchor (Bitcoin, via OpenTimestamps — VDR spec §5.1),
never on the index, never on the index operator, and never on the authors of
this spec. A Verifier re-checks each entry's anchor; it takes the index's word
for nothing.

It is **privacy-preserving.** The index records **only digests and anchor
metadata — never the `subject`.** The decision payload never leaves the
Producer's environment.

This shape is deliberate: because trust lives in the anchor, not the index, the
index can be a plain static file, anyone may mirror or host their own, and no
party — including us — becomes a trusted third party.

## 1. Entry

Each entry is a JSON object:

```
{
  "record_digest": "<hex sha-256>",      // REQUIRED — the registered record
  "profile": "<profile-id>",             // OPTIONAL — e.g. "ai.agent.action"
  "anchor": { ... VDR spec §5.1 ... },   // REQUIRED — the proof of existence
  "registered_at": "<RFC3339 UTC>"       // OPTIONAL — informational
}
```

`record_digest` and `anchor` are load-bearing; `profile` and `registered_at`
are informational. The entry MUST NOT contain the `subject` or any part of it.

## 2. Canonical instance & format

The canonical index is published as a **static newline-delimited JSON (JSONL)**
file — one entry per line — at `https://determs.com/registry/index.jsonl`.
There is **no server to operate**: the index is a static artifact, versioned in
the open. The format is open; anyone MAY host their own index, since trust never
rests on the host.

## 3. Verification

Given the index file, a Verifier:

1. Reads each line as one entry.
2. For each entry, verifies its `anchor` per VDR spec §5–§7: the anchor MUST
   commit to the entry's `record_digest`, and (for a `"complete"` anchor) MUST
   resolve to the claimed public infrastructure (a Bitcoin block for
   `opentimestamps`).
3. A `"pending"` anchor proves submission to a calendar, not yet existence in a
   block; it is not yet a time-proof.

An entry that fails (2) is invalid regardless of its presence in the index.

## 4. Appending (how the index grows, AI-operated)

The canonical instance grows without a live server:

- via the reference tooling (`determs.registry`) plus republication of the
  static file, and/or
- via open, GitHub-native submission (a digest + its anchor) reviewed and
  appended.

Because entries are self-verifying, appending is not a trusted operation: a bad
entry simply fails verification.

## 5. Status

Genesis. The reference `ai.agent.action` record (the example carried in the
VDR spec and on the site) is the first registered record. The index is the
discovery layer of the sequence — spec → registry → compliance — and grows as
records are anchored.
