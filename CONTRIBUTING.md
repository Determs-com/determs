# Contributing to Determs

Thanks for your interest. A few honest expectations up front.

## How this project is run

Determs is built by a very small team. Issues and pull requests are reviewed
on a **best-effort basis** — responses may be slow, and some may be closed
without action if they fall outside the current direction. This is not
indifference; it is a deliberate scope choice to keep the project focused.

If you need a guarantee of support or a feature, the managed/commercial layer
is the place for that — see [determs.com](https://determs.com).

## Licensing of contributions

The reference implementation (engine, CLI, SDK) is licensed under
**Apache-2.0**. By submitting a contribution, you agree that it is provided
under the same Apache-2.0 license and that you have the right to submit it
(inbound = outbound). No separate CLA is required.

The specification under `docs/spec/` is licensed under **CC-BY-4.0**;
contributions to the spec are made under those terms.

## What makes a good contribution

- a clear, minimal change with a stated rationale
- tests for any behavior change (`cargo test`, `pytest sdk/python/tests`)
- consistency with the [Verifiable Decision Record spec](docs/spec/verifiable-decision-record-v0.md)
  — the spec is the source of truth; the code conforms to it
- no new runtime dependencies in the Rust engine without discussion

## What is out of scope

- changes that make verification depend on trusting a brand or a server
  rather than maths + public infrastructure (this is the core invariant)
- features that turn the open-core layer into the commercial layer

## Security

Do not open public issues for vulnerabilities. See [SECURITY.md](SECURITY.md).
