# Security Policy

## Reporting a vulnerability

Email **contact@determs.com** with details. Please do not open a public
issue for security matters.

Because Determs is about verifiable, tamper-evident records, we take
integrity and verification issues seriously — in particular:

- any way to make `verify` accept a record whose content was altered
- any divergence between the specified canonicalization (RFC 8785 over the
  supported value space) and the reference implementation that could let two
  parties compute different digests for the same record
- any way to forge or replay a receipt

We review reports on a best-effort basis and will acknowledge what we can.
There is no formal bounty program at this stage.

## Supported versions

Determs is pre-1.0. Only the latest version is supported.
