import json

from determs.record import ActionRecord, build_record


def test_build_record_defaults():
    record = build_record(
        agent_id="a",
        model={"provider": "anthropic", "name": "claude-3-5"},
        input={"messages": [{"role": "user", "content": "hi"}]},
        output={"content": "ok"},
    )
    assert isinstance(record, ActionRecord)
    assert record.agent_id == "a"
    assert record.action_id.startswith("act-")
    assert record.occurred_at_unix_ms.isdigit()


def test_record_to_dict_only_includes_provided_optional_fields():
    record = build_record(
        agent_id="a",
        model={"provider": "x", "name": "y"},
        input={"messages": [{"role": "user", "content": "hi"}]},
        output={"content": "ok"},
    )
    data = record.to_dict()
    assert set(data.keys()) == {
        "agent_id",
        "action_id",
        "occurred_at_unix_ms",
        "model",
        "input",
        "output",
    }
    # params and context absent when not provided
    assert "params" not in data
    assert "context" not in data


def test_record_to_dict_includes_optional_fields_when_set():
    record = build_record(
        agent_id="a",
        model={"provider": "x", "name": "y"},
        input={"messages": [{"role": "user", "content": "hi"}]},
        output={"content": "ok"},
        params={"temperature": 0.0},
        context={"trace_id": "t1"},
    )
    data = record.to_dict()
    assert data["params"] == {"temperature": 0.0}
    assert data["context"] == {"trace_id": "t1"}


def test_record_to_json_is_sorted_and_parseable():
    record = build_record(
        agent_id="a",
        model={"provider": "x", "name": "y"},
        input={"messages": [{"role": "user", "content": "hi"}]},
        output={"content": "ok"},
    )
    blob = record.to_json()
    parsed = json.loads(blob)
    assert parsed["agent_id"] == "a"
    # sorted keys at top level
    assert list(parsed.keys()) == sorted(parsed.keys())
