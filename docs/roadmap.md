# Roadmap

Determs is the open standard — the **Verifiable Decision Record (VDR)** — and the
deterministic replay & proof engine that implements it. The goal: any automated
decision can become a record anyone verifies with mathematics and public
infrastructure. **AI agents are the first profile.**

This is a high-level, capability-oriented roadmap — intentionally not a dated
commitment. The spec evolves in the open; see [GOVERNANCE.md](../GOVERNANCE.md)
for how to influence it.

## Shipped

- **VDR specification, draft v0** — canonical form (RFC 8785 / JCS), the digests,
  optional public anchoring, and a vendor-independent verification procedure.
  See [the spec](spec/verifiable-decision-record-v0.md).
- **Reference engine (Rust)** — `capture` / `verify` / `replay`, zero runtime
  dependencies.
- **Python SDK** — wrap an LLM client (Anthropic, OpenAI) and capture records.
- **Public anchoring** — anchor a record's digest to public infrastructure
  (OpenTimestamps) for provable existence in time; only the digest ever leaves
  your environment.
- **Neutral registry index** — a static, append-only index of anchored digests,
  non-trust-bearing (each entry self-verifies against its anchor).
- **Conformance [test vectors](spec/test-vectors/)** — pinned digests an
  independent implementation must reproduce.
- **Evidence pack** — bundle anchored records for one system over one period,
  mapped to the EU AI Act record-keeping duties (Articles 12 & 19); self-verifying.

## In progress / next

- **Spec toward v1** — harden v0 with community feedback; more worked examples;
  sharpen the canonicalization value space.
- **More profiles** — the format is domain-agnostic; profiles beyond
  `ai.agent.action` as real needs appear.
- **More regulation mappings** — extend the evidence-pack mapping beyond the
  EU AI Act.
- **Independent implementations** — the test vectors exist so the VDR can be
  implemented by others; more than one conforming implementation is a goal, not a
  threat.
- **Toward a neutral home** — move the specification into a neutral standards
  body as adoption grows.

## How to influence it

Open a Discussion or Issue on [GitHub](https://github.com/determs-com). Proposals
are discussed in the open before they land.
