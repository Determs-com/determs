<!--
doc: README
role: public-entrypoint
audience: human, external
lifetime: project
ai_editable: true
canonical: true
-->

<div align="center">

# determs

### Replay any automated decision. Prove it to anyone.

**Turn any automated decision into a record anyone can verify — with maths and public infrastructure, never by trusting a vendor. Today, that starts with AI agents.**

[![license](https://img.shields.io/badge/code-Apache--2.0-7af2a1?style=flat-square)](LICENSE)
[![spec](https://img.shields.io/badge/spec-CC--BY--4.0-7af2a1?style=flat-square)](docs/spec/verifiable-decision-record-v0.md)
[![status](https://img.shields.io/badge/status-draft%20v0-8b8b8b?style=flat-square)](ROADMAP.md)

</div>

---

Your agent did something yesterday at 14:23. Today, can you reproduce it? Prove
to an auditor what it did, and why? Tell a real regression from noise after a
prompt change?

Observability tools (Langfuse, Helicone, Phoenix) show you traces. They don't
give you **replay** or **proof**. That gap is what determs fills.

```
┌─ verifiable decision record ────────────────────────────────┐
│  profile        ai.agent.action                              │
│  subject        { model, params, input, output }             │
│  record_digest  44f2b549…c4b581fe4   ← sha-256, reproducible │
│  verify         ✓ trustless — maths + public infra           │
└──────────────────────────────────────────────────────────────┘
```

## The idea

Determs is an open standard — the **Verifiable Decision Record** — and the
deterministic replay & proof engine that implements it.

A log your own system wrote about itself is not evidence — a counterparty, an
auditor, or a regulator has no reason to trust it. determs turns each automated
decision into a **Verifiable Decision Record (VDR)**: a portable, canonical
object whose integrity *anyone* can check, using only mathematics and (optionally)
public infrastructure.

Three primitives:

- **Capsule** — a unit of execution: typed input, deterministic logic, typed output.
- **Receipt** — a stable, hash-anchored proof that a capsule ran on a given input and produced a given output.
- **Replay** — re-running a capsule from a recorded input produces the same output, byte for byte.

> **"But the LLM is stochastic."** Right — and that's not the obstacle people
> assume. determs records the output that *did* occur and binds it verifiably to
> the inputs that produced it. Determinism is a property of the **record and its
> verification**, not of the model.

## Quickstart

Wrap your LLM client. Every call becomes a record.

```bash
pip install "determs[anthropic]"
```

```python
import anthropic
from determs.anthropic import wrap
from determs.storage import FileStorage

client = wrap(
    anthropic.Anthropic(),
    agent_id="support-triage",
    storage=FileStorage("./records"),
)

resp = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=512,
    messages=[{"role": "user", "content": "My order #1234 hasn't shipped."}],
)
# → ./records/<action_id>.json  (a VDR subject)
```

Then capture, verify, and replay with the engine (`cargo install determs`):

```bash
determs capture --input ./records/act-xxx.json --output ./record.json
determs verify  --record ./record.json     # 0 if untampered, 1 otherwise
determs replay  --record ./record.json     # rebuilds & compares, bit-exact
```

`verify` recomputes every digest from the stored record. Change one character —
a content string, a tool argument, a token count — and the digest diverges and
`verify` exits non-zero. No silent corruption.

## Verify it yourself

You don't have to trust us — that's the point. Any SHA-256 implementation
reproduces a determs digest. Even the project's website is itself a record:

```bash
printf '%s' '{"site":"determs.com","standard":"verifiable-decision-record/0","claim":"every automated decision can become a verifiable, replayable record"}' | sha256sum
# 33a0bfac250e303a6765456366dd3e8d19709f4adf5b5b8c4541bcca95f2f8b1
```

To prove *when* a record existed — not just its integrity — anchor its digest to
public infrastructure: `pip install "determs[anchor]"` commits it via
OpenTimestamps to the Bitcoin blockchain. Only the digest leaves your
environment; verification needs no one's permission.

## What determs is — and is not

| determs is | determs is not |
|---|---|
| a replay & verifiable-audit layer | a tracing/observability tool |
| an open record format (VDR) | a prompt evaluator or LLM gateway |
| a neutral verification primitive | an orchestration framework |
| trustless by construction | a system you have to trust |

**Neutral by construction.** Tracing tools and agent-governance toolkits keep
their own records, in their own systems, attested with their own keys — you
verify by trusting them. A VDR is checked against public infrastructure, never a
vendor's word, ours included: a signature proves *who*; a public anchor proves
*what* and *when*. The format is domain-agnostic and portable, and only the
digest is ever published — the decision payload never leaves your environment.

## The standard

The record format is an open specification — the
[**Verifiable Decision Record**](docs/spec/verifiable-decision-record-v0.md)
(CC-BY-4.0). It defines the canonical form (RFC 8785 / JCS), the digests, the
optional public-log anchoring, and a verification procedure any vendor can
implement independently. determs (this repo) is the reference implementation.

Conformance [test vectors](docs/spec/test-vectors/) pin the exact digests a
conforming implementation must reproduce — so independent implementations
interoperate, not just ours.

A neutral [registry index](docs/spec/registry-index-v0.md) of anchored
`record_digest`s is published as a static file — for discovery, never trust:
each entry self-verifies against its anchor, and only digests are indexed,
never the subject.

An [evidence pack](docs/spec/evidence-pack-v0.md) bundles anchored records for
one system over one period and maps them to a regulation's record-keeping duties
(EU AI Act Art. 12 & 19) — a self-verifying artefact an auditor checks against
public infrastructure, not against your word or ours. It is the open, trustless
primitive of the compliance layer (`determs.compliance`).

## Architecture

```
  SDK (Python)            Engine (Rust)                 Spec
  ───────────             ─────────────                 ────
  wrap(client)   ──→      capture  → VDR record         docs/spec/
  emits a subject         verify   → recompute digests  (vendor-neutral,
  (the action)            replay   → rebuild & compare    CC-BY-4.0)
```

- `src/` — Rust engine + CLI (Apache-2.0)
- `sdk/python/` — Python SDK: Anthropic & OpenAI wrappers, sync/async, streaming
- `docs/spec/` — the Verifiable Decision Record specification
- `examples/` — sample records and runnable demos

## Status

Pre-1.0. The engine, the `agent.action.replay.v1` capsule, the CLI
(`capture`/`verify`/`replay`), and the Python SDK are working today. The VDR
spec is at draft v0, with a neutral registry index and an open, self-verifying
compliance evidence pack (EU AI Act Art. 12 & 19) alongside it. A managed
evidence layer — hosted retention and auditor-ready export over those same
packs — is the active commercial build. See [ROADMAP.md](ROADMAP.md).

## Further reading

- [Agent governance prevents. It can't prove.](https://determs.com/blog/agent-governance-needs-proof/) — prevention and proof are different layers; you need both.
- [Observability shows you what happened. It can't prove it.](https://determs.com/blog/observability-is-not-proof/) — why tracing tools (Langfuse, Helicone, Arize) aren't an audit layer.
- [The EU AI Act wants logs you can prove](https://determs.com/blog/eu-ai-act-verifiable-logs/) — Articles 12 & 19, and the mapping to a verifiable record.
- [Logs are not proofs](https://determs.com/blog/logs-are-not-proofs/) — the case for deterministic replay in AI agents.

## Model & license

Open-core. The specification and the reference implementation (engine, CLI, SDK)
are open source:

- **Code** — [Apache-2.0](LICENSE)
- **Specification** (`docs/spec/`) — CC-BY-4.0
- A managed registry and a compliance layer are the commercial surface.

## Contributing & security

- [CONTRIBUTING.md](CONTRIBUTING.md) — best-effort, no CLA (inbound = outbound).
- [SECURITY.md](SECURITY.md) — report integrity/verification issues privately.

The one invariant: **verification must depend on maths and public
infrastructure, never on trusting a brand.** Contributions that break that are
out of scope.

---

<div align="center">
<sub>determs — open standard for verifiable AI decisions · <a href="https://determs.com">determs.com</a></sub>
</div>
