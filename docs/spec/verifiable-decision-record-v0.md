<!--
doc: SPEC — Verifiable Decision Record
role: open-specification
audience: implementers (any vendor), maintainer, ai-assistant
lifetime: project
status: draft v0
canonical: true
-->

# Verifiable Decision Record (VDR) — Specification v0

Status: **Draft v0**. Open specification. Vendor-neutral.

Licensed under Creative Commons Attribution 4.0 International (CC-BY-4.0):
<https://creativecommons.org/licenses/by/4.0/>. You may implement,
redistribute, and build on this specification, including commercially, with
attribution. The reference implementation (engine, CLI, SDK) is licensed
separately under Apache-2.0.

## 0. Why this exists

Automated systems — AI agents above all — make decisions whose
consequences are real, but whose record is not trustworthy. A log produced
by the party that made the decision is not evidence: the counterparty, the
auditor, the regulator have no reason to trust it. Observability tools
describe what happened; they do not let an independent party *prove* it.

The Verifiable Decision Record (VDR) is an open format for representing a
single automated decision such that **anyone can verify it independently**,
using only mathematics and (optionally) public infrastructure — never the
reputation of the party that produced it, and never the reputation of any
vendor, including the authors of this spec.

A VDR is:

- **portable** — a self-contained JSON object
- **canonical** — it has exactly one byte representation for hashing
- **verifiable** — its integrity can be checked by recomputation
- **anchorable** — its digest can be committed to a public append-only log
  so that its existence at a point in time is provable
- **privacy-preserving** — only digests need ever be made public; the
  decision payload can stay entirely in the producer's environment

This document specifies the format and the verification procedure. It does
not require any particular product. Determs is one reference implementation.

## 1. Terminology

The key words MUST, MUST NOT, SHOULD, MAY are to be interpreted as in
RFC 2119.

- **Decision** — a single discrete act of an automated system (e.g. an AI
  agent action: a model call with its inputs and the produced output).
- **Record** — the structured representation of a Decision per this spec.
- **Canonical form** — the unique byte serialization of a Record used for
  hashing, per §3.
- **Digest** — a SHA-256 hash, lowercase hex, of a canonical form.
- **Receipt** — the set of digests that identify a Record (§4).
- **Anchor** — a commitment of a digest to public infrastructure that
  provides a tamper-evident proof of existence in time (§5).
- **Producer** — the party that creates a Record.
- **Verifier** — any party that checks a Record. The Verifier need not
  trust the Producer.

## 2. Record structure

A VDR is a JSON object with the following top-level members.

```
{
  "vdr_version": "0",
  "profile": "<profile-id>",
  "subject": { ... profile-defined decision payload ... },
  "receipt": { ... see §4 ... },
  "anchor": { ... optional, see §5 ... },
  "producer": { ... optional, non-load-bearing metadata ... }
}
```

- `vdr_version` (string, REQUIRED) — MUST be `"0"` for this version.
- `profile` (string, REQUIRED) — identifies the schema of `subject`. See
  §6 for the AI agent action profile.
- `subject` (object, REQUIRED) — the decision payload, structured per
  `profile`. The time the decision occurred is carried inside `subject` in
  a profile-defined field (the AI agent profile uses
  `occurred_at_unix_ms`), as a string, for hash stability and to avoid a
  date-formatting dependency in implementations.
- `receipt` (object, REQUIRED) — digests, per §4.
- `anchor` (object, OPTIONAL) — public-log commitment, per §5.
- `producer` (object, OPTIONAL) — free-form metadata about the producing
  system. MUST NOT affect verification; Verifiers MUST ignore it when
  recomputing digests (it is excluded from the canonical form per §4).

## 3. Canonicalization

To be hashable to a single value, a Record fragment MUST be serialized to
its **canonical form** using JSON Canonicalization Scheme (JCS),
**RFC 8785**:

- UTF-8 encoding
- object members sorted by key, ordered by Unicode code point of the
  UTF-16 representation as specified in RFC 8785
- no insignificant whitespace
- numbers serialized per RFC 8785 §3.2.2
- strings escaped per RFC 8785 §3.2.2

Reusing an existing IETF standard for canonicalization is deliberate: it
removes us as a source of truth. Any RFC 8785 implementation produces the
same bytes.

Supported value space (v0). The reference implementation conforms to
RFC 8785 over the value space that Records actually use:

- member names are ASCII (so code-point ordering and UTF-16 ordering
  coincide)
- numbers are finite and within the range where JCS uses plain decimal
  notation (no exponent) — i.e. token counts, rates, and small parameters

Producers SHOULD keep Records within this value space in v0. Inputs outside
it (non-ASCII member names, numbers requiring exponential notation) are not
guaranteed to canonicalize identically across implementations until v1
pins the full numeric rules. String values may contain arbitrary UTF-8;
only member *names* are constrained.

## 4. Receipt and digests

The `receipt` object binds a Record to stable identifiers:

```
"receipt": {
  "alg": "sha-256",
  "subject_digest": "<hex>",
  "record_digest": "<hex>"
}
```

- `alg` (string, REQUIRED) — MUST be `"sha-256"` for this version.
- `subject_digest` (string, REQUIRED) — SHA-256 over the JCS canonical
  form of the `subject` object alone.
- `record_digest` (string, REQUIRED) — SHA-256 over the JCS canonical form
  of the object `{ vdr_version, profile, subject }` (i.e. the Record
  **excluding** `receipt`, `anchor`, and `producer`). This is the stable
  identifier of the Decision.

A profile MAY define additional named digests inside `receipt` over
sub-parts of `subject` (the AI agent action profile defines
`input_digest` and `output_digest`, §6). Additional digests MUST NOT
change how `record_digest` is computed.

Rationale for the exclusions: `producer` is non-neutral metadata; `anchor`
is added *after* the digest exists; `receipt` cannot contain its own hash.
Excluding them keeps `record_digest` reproducible by anyone.

## 5. Anchoring (optional, enables proof of existence in time)

A digest proves integrity (the Record was not altered). To also prove
**existence at a point in time** — that the Record was not back-dated — the
`record_digest` MAY be committed ("anchored") to public infrastructure that
yields a verifiable, tamper-evident timestamp. Anchoring is **trustless** when
a Verifier can check the resulting proof without trusting the party that
produced the anchor, without trusting any log operator's word, and without
trusting the authors of this spec.

Only the `record_digest` is ever transmitted to anchor. The `subject` and the
full Record never leave the Producer's environment.

```
"anchor": {
  "type": "<anchor type, e.g. \"opentimestamps\">",
  "anchored_at": "<RFC3339 UTC timestamp, informational>",
  "proof": "<type-specific proof material>",
  "status": "pending" | "complete"
}
```

- `type` (string, REQUIRED) — identifies the anchoring method, and therefore
  the shape of `proof` and the verification procedure. A Verifier selects the
  procedure by `type`.
- `anchored_at` (string, OPTIONAL) — informational submission time. It is NOT
  load-bearing: the authoritative time comes from the verified `proof`.
- `proof` (REQUIRED) — the type-specific evidence a Verifier checks.
- `status` (string, OPTIONAL) — `"pending"` while the anchor is not yet
  confirmed by the underlying public infrastructure, `"complete"` once it is.

This spec is **anchor-agnostic**: new `type`s MAY be defined without changing
the core. v0 defines one type, `opentimestamps` (§5.1). A transparency-log
type (e.g. a Rekor-style Merkle inclusion proof) MAY be defined later.

### 5.1 Anchor type: `opentimestamps`

The bytes of `record_digest` are submitted to one or more OpenTimestamps
calendar servers, which aggregate submissions and commit the aggregate into
the Bitcoin blockchain — the most widely-replicated public append-only
timestamp available. No account, key, or payment is involved.

```
"anchor": {
  "type": "opentimestamps",
  "anchored_at": "2026-06-03T10:00:00Z",
  "proof": "<base64 of the binary .ots proof for record_digest>",
  "status": "complete"
}
```

A freshly created proof is `"pending"` (it commits to a calendar but not yet
to a confirmed block). Once the calendar's Bitcoin transaction confirms, the
proof is **upgraded** to include the block attestation and becomes
`"complete"`.

Verification (trustless): a Verifier confirms the proof commits the value
`record_digest`, follows the proof to its Bitcoin block attestation, and
checks that the committed value appears in the claimed block. With a Bitcoin
full node this needs no trusted third party. A Verifier MAY instead consult a
block explorer, which introduces trust in that explorer **for the lookup step
only** — never in the Producer, the calendar, or this spec. A `"pending"`
anchor proves submission to a calendar but not yet existence in a block;
Verifiers SHOULD treat only `"complete"` anchors as time-proofs.

### 5.2 Registry (discovery, non-load-bearing)

A registry MAY index anchored Records — by `record_digest`, `profile`, and
`anchored_at` — to make them discoverable. A registry is a **convenience and
network layer, not a source of trust**: the proof of existence rests on the
anchor (§5.1), never on the registry. A registry MUST receive only digests
and anchor metadata, **never** `subject`, and is never required to verify a
Record. A Verifier with a Record and §7 needs no registry.

## 6. Profile: AI agent action (`ai.agent.action`)

The first standard profile. `subject` represents one AI model invocation
by an agent.

```
"subject": {
  "agent_id": "<string>",
  "action_id": "<string>",
  "occurred_at_unix_ms": "<string: milliseconds since Unix epoch>",
  "model": { "provider": "<string>", "name": "<string>", "version": "<string?>" },
  "params": { "temperature": <num?>, "top_p": <num?>, "max_tokens": <num?>, "seed": <num?>, ... },
  "input": {
    "messages": [ { "role": "<string>", "content": "<string>" }, ... ],
    "tools": [ ... ]?
  },
  "output": {
    "content": "<string?>",
    "tool_calls": [ ... ]?,
    "finish_reason": "<string?>",
    "usage": { "input_tokens": <num?>, "output_tokens": <num?> }?
  },
  "context": { ... }?
}
```

Required in `subject`: `agent_id`, `action_id`, `occurred_at_unix_ms`,
`model.provider`, `model.name`, `input.messages` (≥ 1), and at least one of
`output.content` or `output.tool_calls`.

For this profile, `receipt` SHOULD include:

- `input_digest` — SHA-256 over JCS canonical form of
  `{ model, params, input }` (the stimulus presented to the model)
- `output_digest` — SHA-256 over JCS canonical form of `output`

These let a Verifier reason separately about "what the model was asked" and
"what it produced".

What this profile does NOT claim: it does not assert that re-invoking the
model would reproduce `output`. LLM sampling is non-deterministic. The VDR
records the output that *did* occur and binds it verifiably to the inputs
that produced it. Determinism is a property of the *record and its
verification*, not of the model.

## 7. Verification procedure

A Verifier, given a candidate VDR and nothing else, performs:

1. Check `vdr_version == "0"` and `receipt.alg == "sha-256"`.
2. Validate `subject` against the declared `profile`'s required fields.
3. Recompute `subject_digest` = SHA-256(JCS(`subject`)); MUST equal
   `receipt.subject_digest`.
4. Recompute `record_digest` = SHA-256(JCS({ `vdr_version`, `profile`,
   `subject` })); MUST equal `receipt.record_digest`.
5. Recompute any profile sub-digests (e.g. `input_digest`,
   `output_digest`); each MUST equal the stored value.
6. If `anchor` is present and `status` is `"complete"`: verify `proof`
   according to `anchor.type` (§5); the committed value MUST equal
   `record_digest`, and the proof MUST resolve to the claimed public
   infrastructure (e.g. a Bitcoin block for `opentimestamps`). A `"pending"`
   anchor is not a time-proof and MUST NOT be treated as one. Absence of an
   `anchor` does not fail verification; it only means no time-proof is claimed.

If any check fails, the Record is **not verified**. A Verifier MUST be
implementable from this section alone, with no reference to any vendor.

## 8. Versioning and extensibility

- The format is versioned by `vdr_version`. Breaking changes increment it.
- New profiles MAY be defined without changing the core. A profile is
  identified by its `profile` string and defines the schema of `subject`
  and any additional `receipt` digests.
- Producers MAY add members under `subject` per their profile; Verifiers
  hash whatever `subject` contains, so additive changes are safe as long
  as both sides share the profile definition.

## 9. Out of scope

- model-internal reproducibility / sampling determinism
- storage, retention, access control of Records
- transport and authentication of any API that produces or serves Records
- the economic or compliance interpretation of a Record (these live in
  products built *on top* of VDR, not in the format)

## 10. Conformance

- A **conforming Producer** emits Records whose `receipt` digests are
  correct per §3–§6.
- A **conforming Verifier** implements §7 exactly.
- A **conforming Log** provides append-only semantics and verifiable
  inclusion proofs for anchored digests per §5.

**Conformance test vectors** live in `docs/spec/test-vectors/`: given a
`profile` and `subject`, they pin the exact digests a conforming Producer
MUST reproduce. Any RFC 8785 implementation that matches them interoperates
with Determs; the reference engine reproduces them in its test suite.

Determs is the reference implementation: the Rust engine produces
conforming Records (the `agent.action.replay.v1` capsule maps to the
`ai.agent.action` profile), the CLI `verify` implements §7, and the Python
SDK emits conforming `subject` payloads.

## 11. Open questions (v0 → v1)

- pin the full RFC 8785 numeric rules so the supported value space (§3) can
  be widened (exponential notation, non-ASCII member names)
- standardize the `tools` / `tool_calls` sub-structure across providers
- define a transparency-log anchor type (e.g. a Rekor-style Merkle inclusion
  proof) as an alternative to `opentimestamps` (§5)
- decide whether to add an OPTIONAL producer signature (authorship /
  non-repudiation — "who") without weakening trustless verification of the
  Record itself ("what" + "when")
- multi-step decisions (chains of actions) as a first-class profile
