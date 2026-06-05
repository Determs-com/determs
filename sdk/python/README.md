# Determs Python SDK

Verifiable Decision Records for AI agents — Python client.

Capture each LLM call as a structured, verifiable record. Persist records
wherever you want. Verify and replay them later with the `determs` CLI.

This SDK is the **open-core** reference client for the
[Verifiable Decision Record](../../docs/spec/verifiable-decision-record-v0.md)
specification.

## Install

```bash
pip install determs

# With optional client SDKs:
pip install "determs[anthropic,openai]"
```

(Until the first public release, install from the built wheel in `dist/`:
`pip install dist/determs-0.1.0-py3-none-any.whl`.)

## Quick start — Anthropic

```python
import anthropic
from determs.anthropic import wrap as wrap_anthropic
from determs.storage import FileStorage

client = wrap_anthropic(
    anthropic.Anthropic(),
    agent_id="support-triage",
    storage=FileStorage("./determs_records"),
)

response = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=512,
    messages=[{"role": "user", "content": "Hi"}],
)
# A record file landed under ./determs_records/{action_id}.json.
```

## Quick start — OpenAI

```python
from openai import OpenAI
from determs.openai import wrap as wrap_openai
from determs.storage import FileStorage

client = wrap_openai(
    OpenAI(),
    agent_id="support-triage",
    storage=FileStorage("./determs_records"),
)

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hi"}],
)
```

## Storage backends

```python
from determs.storage import FileStorage, StdoutStorage, CallbackStorage

# Write each record as <dir>/<action_id>.json
FileStorage("./records")

# Print each record as one JSON line on stdout — pipeable.
StdoutStorage()

# Hand the record dict to your own callback — for queues, custom sinks, tests.
CallbackStorage(callback=lambda record: print(record["agent_id"]))
```

Or pick a backend from environment variables:

```python
from determs.storage import storage_from_env
storage = storage_from_env()   # honours DETERMS_STORAGE and DETERMS_DIR
```

## Manual records

If you don't use the Anthropic or OpenAI SDKs directly (e.g. you call an
inference service through your own HTTP client), build records explicitly:

```python
from determs import build_record
from determs.storage import FileStorage

storage = FileStorage("./records")
record = build_record(
    agent_id="my-agent",
    model={"provider": "anthropic", "name": "claude-3-5"},
    params={"temperature": 0.0},
    input={"messages": [{"role": "user", "content": "Hi"}]},
    output={"content": "Hello.", "finish_reason": "stop"},
    context={"trace_id": "trace-001"},
)
storage.put(record)
```

## Verify and replay

The `determs` binary is the verification surface. The SDK emits the record
JSON; the CLI handles capture, replay, and verify.

```bash
# Bundle the action into a full record (input + execution + receipt):
determs capture --input ./records/act-xxx.json --output ./full.record.json

# Replay it later: returns 0 if bit-exact.
determs replay --record ./full.record.json

# Verify: returns 0 if no tampering, 1 if any digest mismatches.
determs verify --record ./full.record.json
```

## Async clients

```python
import anthropic
from determs.anthropic import wrap_async as wrap_anthropic_async

aclient = wrap_anthropic_async(
    anthropic.AsyncAnthropic(),
    agent_id="support-triage",
    storage=FileStorage("./records"),
)

response = await aclient.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=512,
    messages=[{"role": "user", "content": "Hi"}],
)
```

`determs.openai.wrap_async(...)` works the same way for `AsyncOpenAI`.

## Streaming

```python
stream = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=512,
    messages=[{"role": "user", "content": "Hi"}],
    stream=True,
)
for event in stream:
    handle(event)
# A record is emitted only when the stream completes naturally.
# If the caller stops iterating before the end, no record is written.
```

Async streaming uses `async for` after `await client.messages.create(stream=True, ...)`.

## What this SDK does and does not do

**Does**:

- intercept `messages.create` (Anthropic, sync + async, streaming + non-streaming)
- intercept `chat.completions.create` (OpenAI, sync + async, streaming + non-streaming)
- accumulate streamed text, tool_use blocks, and tool_calls into a final record
- emit records only on complete streams; abandoned streams produce nothing
- build a well-formed action record consumable by the Determs CLI
- persist records via a swappable storage backend
- never let recording failures break the upstream LLM call

**Does not yet**:

- support Anthropic's `messages.stream(...)` context manager (use `messages.create(stream=True)` instead)
- support the OpenAI Responses API (use `chat.completions` instead)
- talk to a Determs Cloud endpoint (phase 3)
- ship a replay UI

## Tests

```bash
cd sdk/python
pip install -e ".[dev]"
pytest tests/
```

The end-to-end tests in `test_cli_compatibility.py` require the `determs`
binary built from the workspace root (`cargo build` or `cargo build --release`).

## Build the wheel

```bash
cd sdk/python
pip install build
python -m build
# Produces dist/determs-0.1.0-py3-none-any.whl and dist/determs-0.1.0.tar.gz
```
