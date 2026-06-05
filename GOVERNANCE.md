# Governance

Determs is an open standard — the **Verifiable Decision Record (VDR)** — and an
open-core reference implementation (engine, SDK). This document describes, in
minimal form, how it is stewarded and how it changes.

## Principles (load-bearing)

- **Trustless.** Verification depends on mathematics and public infrastructure —
  never on the reputation of any party, the maintainers included. No governance
  decision may compromise this.
- **Vendor-neutral.** The format is not bound to one vendor, cloud, or industry.
  AI agents are the first profile, not the ceiling.
- **Conformance is proven, not granted.** Any implementation demonstrates
  conformance *for itself* against the public
  [test vectors](docs/spec/test-vectors/). Conformance is never certified,
  endorsed, or sold by the project.
- **Sponsorship buys recognition, never influence.** See [SPONSORS.md](SPONSORS.md).

## How it changes

- **Discuss first.** Proposals — spec changes, new profiles, engine/SDK
  behaviour — start as a GitHub Discussion or Issue, so the rationale is public.
- **Then a PR.** Concrete changes land as pull requests that reference the
  discussion. Maintainers review for correctness, neutrality, and consistency
  with the principles above.
- **The spec is versioned.** A breaking change to a published profile produces a
  new version; published digests and test vectors are never silently altered.
- **No CLA** (inbound = outbound): code under Apache-2.0, spec under CC-BY-4.0.

## Stewardship

The project is currently maintained by its founding maintainer(s). The intent is
to keep the **standard** (the VDR spec, the test vectors, the registry format)
governable independently of any single implementer, and — as adoption grows — to
move the specification into a neutral standards body. Until then, the principles
above are the guardrails.

## Conduct

Be respectful and constructive; harassment or bad-faith participation isn't
welcome. Report conduct or security concerns privately via [SECURITY.md](SECURITY.md)
or to the maintainers.
