use crate::capsule::{
    Capsule, ExecutionOutput, ExecutionStatus, FieldSpec, Manifest, Problem, SchemaNode,
};
use crate::value::Value;

pub const ID: &str = "agent.action.replay.v1";
pub const PROFILE: &str = "agent-replay";
pub const LOGIC_VERSION: &str = "1";

pub static AGENT_ACTION_REPLAY_V1: AgentActionReplayV1 = AgentActionReplayV1;

pub struct AgentActionReplayV1;

impl Capsule for AgentActionReplayV1 {
    fn id(&self) -> &'static str {
        ID
    }

    fn manifest(&self) -> Manifest {
        Manifest {
            id: ID.to_string(),
            name: "Agent action replay record".to_string(),
            version: "1.0".to_string(),
            profile: PROFILE.to_string(),
            summary: "Validates a single agent action against the ai.agent.action VDR profile.".to_string(),
            logic_version: LOGIC_VERSION.to_string(),
            tags: vec!["agent".to_string(), "replay".to_string(), "audit".to_string()],
            input_schema: input_schema(),
            output_schema: output_schema(),
        }
    }

    /// Validates a subject (an agent action) against the profile and returns
    /// a structural summary. Digests and the VDR envelope are owned by the
    /// `vdr` module, not by the capsule — there is a single digest
    /// vocabulary, defined by the specification.
    fn execute(&self, input: &Value) -> ExecutionOutput {
        let mut problems: Vec<Problem> = Vec::new();

        let agent_id = required_string(input, "agent_id", &mut problems);
        let action_id = required_string(input, "action_id", &mut problems);
        let occurred_at = required_string(input, "occurred_at_unix_ms", &mut problems);

        let model_value = input.get("model");
        let model_provider = model_value
            .and_then(|m| m.get("provider"))
            .and_then(Value::as_str)
            .map(str::to_string);
        let model_name = model_value
            .and_then(|m| m.get("name"))
            .and_then(Value::as_str)
            .map(str::to_string);
        let model_version = model_value
            .and_then(|m| m.get("version"))
            .and_then(Value::as_str)
            .map(str::to_string);

        let input_block = input.get("input");
        let output_block = input.get("output");

        let messages = input_block
            .and_then(|i| i.get("messages"))
            .and_then(Value::as_array);
        let message_count = messages.map(|m| m.len()).unwrap_or(0);

        let tool_calls = output_block
            .and_then(|o| o.get("tool_calls"))
            .and_then(Value::as_array);
        let tool_calls_emitted = tool_calls.map(|t| t.len()).unwrap_or(0);

        let content = output_block
            .and_then(|o| o.get("content"))
            .and_then(Value::as_str);
        let had_content = content.map(|s| !s.is_empty()).unwrap_or(false);
        let had_tool_calls = tool_calls_emitted > 0;

        if !had_content && !had_tool_calls {
            problems.push(Problem::error(
                "empty_output",
                "output",
                "An agent action must have either content or tool_calls",
            ));
        }

        let finish_reason = output_block
            .and_then(|o| o.get("finish_reason"))
            .and_then(Value::as_str)
            .map(str::to_string);

        let model_full_name = match (
            model_provider.clone(),
            model_name.clone(),
            model_version.clone(),
        ) {
            (Some(provider), Some(name), Some(version)) => Some(format!("{provider}/{name}/{version}")),
            (Some(provider), Some(name), None) => Some(format!("{provider}/{name}")),
            _ => None,
        };

        let summary = Value::object(vec![
            ("message_count", Value::from(message_count)),
            ("tool_calls_emitted", Value::from(tool_calls_emitted)),
            ("had_content", Value::from(had_content)),
            ("had_tool_calls", Value::from(had_tool_calls)),
            (
                "finish_reason",
                finish_reason.map(Value::from).unwrap_or(Value::Null),
            ),
        ]);

        let data = Value::object(vec![
            ("agent_id", agent_id.map(Value::from).unwrap_or(Value::Null)),
            ("action_id", action_id.map(Value::from).unwrap_or(Value::Null)),
            (
                "occurred_at_unix_ms",
                occurred_at.map(Value::from).unwrap_or(Value::Null),
            ),
            (
                "model_full_name",
                model_full_name.map(Value::from).unwrap_or(Value::Null),
            ),
            ("summary", summary),
        ]);

        let status = if problems.iter().any(|p| matches!(p.severity, crate::capsule::ProblemSeverity::Error)) {
            ExecutionStatus::Rejected
        } else {
            ExecutionStatus::Accepted
        };

        ExecutionOutput::new(status, problems, data)
    }
}

fn required_string(input: &Value, key: &str, problems: &mut Vec<Problem>) -> Option<String> {
    match input.get(key).and_then(Value::as_str) {
        Some(s) if !s.is_empty() => Some(s.to_string()),
        Some(_) => {
            problems.push(Problem::error(
                "empty_field",
                key,
                format!("Field '{key}' is empty"),
            ));
            None
        }
        None => None,
    }
}

fn input_schema() -> SchemaNode {
    SchemaNode::object(
        "Recorded agent action",
        vec![
            FieldSpec::required(
                "agent_id",
                "Logical identifier of the agent that took the action",
                SchemaNode::string("Stable identifier of the agent"),
            ),
            FieldSpec::required(
                "action_id",
                "Identifier of this specific action instance",
                SchemaNode::string("Unique action instance identifier"),
            ),
            FieldSpec::required(
                "occurred_at_unix_ms",
                "Timestamp of the action in milliseconds since epoch (as string for hash stability)",
                SchemaNode::string("Milliseconds since Unix epoch"),
            ),
            FieldSpec::required(
                "model",
                "Model used by the agent",
                SchemaNode::object(
                    "Model identification",
                    vec![
                        FieldSpec::required(
                            "provider",
                            "Provider of the model (openai, anthropic, local, ...)",
                            SchemaNode::string("Provider name"),
                        ),
                        FieldSpec::required(
                            "name",
                            "Name of the model",
                            SchemaNode::string("Model name"),
                        ),
                        FieldSpec::optional(
                            "version",
                            "Optional version pin",
                            SchemaNode::string("Version"),
                        ),
                    ],
                    false,
                ),
            ),
            FieldSpec::optional(
                "params",
                "Generation parameters",
                SchemaNode::object(
                    "Generation parameters",
                    vec![
                        FieldSpec::optional(
                            "temperature",
                            "Sampling temperature",
                            SchemaNode::number("Temperature", Some(0.0), Some(2.0)),
                        ),
                        FieldSpec::optional(
                            "top_p",
                            "Nucleus sampling",
                            SchemaNode::number("Top-p", Some(0.0), Some(1.0)),
                        ),
                        FieldSpec::optional(
                            "max_tokens",
                            "Maximum output tokens",
                            SchemaNode::number("Max tokens", Some(0.0), None),
                        ),
                        FieldSpec::optional(
                            "seed",
                            "Random seed if supported",
                            SchemaNode::number("Seed", None, None),
                        ),
                        FieldSpec::optional(
                            "stop",
                            "Stop sequences",
                            SchemaNode::array(
                                "Stop sequences",
                                SchemaNode::string("A stop sequence"),
                                None,
                            ),
                        ),
                    ],
                    true,
                ),
            ),
            FieldSpec::required(
                "input",
                "What the model saw",
                SchemaNode::object(
                    "Model input",
                    vec![
                        FieldSpec::required(
                            "messages",
                            "Chat messages provided to the model",
                            SchemaNode::array(
                                "Chat messages",
                                SchemaNode::object(
                                    "Chat message",
                                    vec![
                                        FieldSpec::required(
                                            "role",
                                            "Message role",
                                            SchemaNode::string("Role"),
                                        ),
                                        FieldSpec::required(
                                            "content",
                                            "Message content",
                                            SchemaNode::string("Content"),
                                        ),
                                    ],
                                    true,
                                ),
                                Some(1),
                            ),
                        ),
                        FieldSpec::optional(
                            "tools",
                            "Tool specifications available to the model",
                            SchemaNode::array(
                                "Tool specs",
                                SchemaNode::any("Tool spec object"),
                                None,
                            ),
                        ),
                    ],
                    true,
                ),
            ),
            FieldSpec::required(
                "output",
                "What the model produced",
                SchemaNode::object(
                    "Model output",
                    vec![
                        FieldSpec::optional(
                            "content",
                            "Text response from the model",
                            SchemaNode::string("Response text"),
                        ),
                        FieldSpec::optional(
                            "tool_calls",
                            "Tool calls emitted by the model",
                            SchemaNode::array(
                                "Tool calls",
                                SchemaNode::any("Tool call object"),
                                None,
                            ),
                        ),
                        FieldSpec::optional(
                            "finish_reason",
                            "Reason the generation stopped",
                            SchemaNode::string("Finish reason"),
                        ),
                        FieldSpec::optional(
                            "usage",
                            "Token usage if reported",
                            SchemaNode::object(
                                "Usage",
                                vec![
                                    FieldSpec::optional(
                                        "input_tokens",
                                        "Tokens consumed by the prompt",
                                        SchemaNode::number("Input tokens", Some(0.0), None),
                                    ),
                                    FieldSpec::optional(
                                        "output_tokens",
                                        "Tokens generated",
                                        SchemaNode::number("Output tokens", Some(0.0), None),
                                    ),
                                ],
                                true,
                            ),
                        ),
                    ],
                    true,
                ),
            ),
            FieldSpec::optional(
                "context",
                "Arbitrary context metadata (trace_id, session_id, labels...)",
                SchemaNode::any("Free-form context object"),
            ),
        ],
        false,
    )
}

fn output_schema() -> SchemaNode {
    SchemaNode::object(
        "Replayable action record",
        vec![
            FieldSpec::required(
                "agent_id",
                "Agent identifier",
                SchemaNode::string("Agent id"),
            ),
            FieldSpec::required(
                "action_id",
                "Action identifier",
                SchemaNode::string("Action id"),
            ),
            FieldSpec::required(
                "occurred_at_unix_ms",
                "Timestamp echoed from input",
                SchemaNode::string("Timestamp"),
            ),
            FieldSpec::required(
                "model_full_name",
                "Compact model identifier (provider/name[/version])",
                SchemaNode::string("Model full name"),
            ),
            FieldSpec::required(
                "summary",
                "Structural summary of the action",
                SchemaNode::object(
                    "Action summary",
                    vec![
                        FieldSpec::required(
                            "message_count",
                            "Number of input messages",
                            SchemaNode::number("Count", Some(0.0), None),
                        ),
                        FieldSpec::required(
                            "tool_calls_emitted",
                            "Number of tool calls in the output",
                            SchemaNode::number("Count", Some(0.0), None),
                        ),
                        FieldSpec::required(
                            "had_content",
                            "Whether the model returned text content",
                            SchemaNode::boolean("Had content"),
                        ),
                        FieldSpec::required(
                            "had_tool_calls",
                            "Whether the model emitted tool calls",
                            SchemaNode::boolean("Had tool calls"),
                        ),
                        FieldSpec::optional(
                            "finish_reason",
                            "Finish reason if reported",
                            SchemaNode::string("Finish reason"),
                        ),
                    ],
                    false,
                ),
            ),
        ],
        false,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::execute_capsule;
    use crate::json::parse as parse_json;

    const VALID_ACTION: &str = r#"
    {
      "agent_id": "support-triage-agent",
      "action_id": "act-2026-05-19-001",
      "occurred_at_unix_ms": "1747700000000",
      "model": {
        "provider": "anthropic",
        "name": "claude-3-5-sonnet",
        "version": "20250101"
      },
      "params": {
        "temperature": 0.0,
        "max_tokens": 512
      },
      "input": {
        "messages": [
          { "role": "system", "content": "You are a triage agent." },
          { "role": "user", "content": "My order #1234 hasn't shipped." }
        ]
      },
      "output": {
        "content": "Routing to shipping team.",
        "finish_reason": "stop"
      },
      "context": {
        "trace_id": "trace-001"
      }
    }
    "#;

    #[test]
    fn test_valid_action_is_accepted() {
        let input = parse_json(VALID_ACTION).unwrap();
        let record = execute_capsule(ID, &input).unwrap();
        assert_eq!(record.output.status, ExecutionStatus::Accepted);
        assert!(record.output.problems.is_empty());
    }

    #[test]
    fn test_output_has_expected_fields() {
        let input = parse_json(VALID_ACTION).unwrap();
        let record = execute_capsule(ID, &input).unwrap();
        let data = &record.output.data;
        assert_eq!(data.get("agent_id").and_then(Value::as_str), Some("support-triage-agent"));
        assert_eq!(data.get("action_id").and_then(Value::as_str), Some("act-2026-05-19-001"));
        assert_eq!(
            data.get("model_full_name").and_then(Value::as_str),
            Some("anthropic/claude-3-5-sonnet/20250101"),
        );
        // Digests live in the VDR layer (see src/vdr.rs), not in the capsule.
        assert!(data.get("input_digest").is_none());
        assert!(data.get("action_digest").is_none());
        let summary = data.get("summary").unwrap();
        assert_eq!(summary.get("message_count").and_then(Value::as_f64), Some(2.0));
        assert_eq!(summary.get("had_content").and_then(Value::as_bool), Some(true));
        assert_eq!(summary.get("had_tool_calls").and_then(Value::as_bool), Some(false));
    }

    #[test]
    fn test_validation_is_stable() {
        let input = parse_json(VALID_ACTION).unwrap();
        let first = execute_capsule(ID, &input).unwrap();
        let second = execute_capsule(ID, &input).unwrap();
        assert_eq!(first.output.data, second.output.data);
        assert_eq!(first.output.status, second.output.status);
    }

    #[test]
    fn test_missing_required_field_rejected() {
        let input = parse_json(
            r#"{ "action_id": "x", "occurred_at_unix_ms": "0", "model": {"provider":"o","name":"n"}, "input":{"messages":[{"role":"user","content":"hi"}]}, "output":{"content":"ok"} }"#,
        )
        .unwrap();
        let record = execute_capsule(ID, &input).unwrap();
        assert_eq!(record.output.status, ExecutionStatus::Rejected);
        assert!(record
            .output
            .problems
            .iter()
            .any(|p| p.path == "agent_id" && p.code == "missing_field"));
    }

    #[test]
    fn test_empty_output_rejected() {
        let input = parse_json(
            r#"{
                "agent_id":"a","action_id":"b","occurred_at_unix_ms":"0",
                "model":{"provider":"p","name":"n"},
                "input":{"messages":[{"role":"user","content":"hi"}]},
                "output":{}
            }"#,
        )
        .unwrap();
        let record = execute_capsule(ID, &input).unwrap();
        assert_eq!(record.output.status, ExecutionStatus::Rejected);
        assert!(record
            .output
            .problems
            .iter()
            .any(|p| p.code == "empty_output"));
    }

    #[test]
    fn test_tool_calls_count_reflects_output() {
        let input = parse_json(
            r#"{
                "agent_id":"a","action_id":"b","occurred_at_unix_ms":"0",
                "model":{"provider":"p","name":"n"},
                "input":{"messages":[{"role":"user","content":"hi"}]},
                "output":{
                    "tool_calls":[
                        {"name":"search","args":{"q":"foo"}},
                        {"name":"send","args":{}}
                    ],
                    "finish_reason":"tool_use"
                }
            }"#,
        )
        .unwrap();
        let record = execute_capsule(ID, &input).unwrap();
        assert_eq!(record.output.status, ExecutionStatus::Accepted);
        let summary = record.output.data.get("summary").unwrap();
        assert_eq!(summary.get("tool_calls_emitted").and_then(Value::as_f64), Some(2.0));
        assert_eq!(summary.get("had_tool_calls").and_then(Value::as_bool), Some(true));
        assert_eq!(summary.get("had_content").and_then(Value::as_bool), Some(false));
    }
}
