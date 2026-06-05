use crate::capsule::{Capsule, ExecutionOutput, ExecutionStatus, Manifest, ProblemSeverity};
use crate::hash::{sha256, Digest};
use crate::json::to_canonical_string;
use crate::profiles;
use crate::value::Value;
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Receipt {
    pub capsule_id: String,
    pub capsule_digest: Digest,
    pub input_digest: Digest,
    pub output_digest: Digest,
    pub run_id: Digest,
    pub executed_at_unix_ms: u128,
}

impl Receipt {
    pub fn to_value(&self) -> Value {
        Value::object(vec![
            ("capsule_id", Value::from(self.capsule_id.clone())),
            ("capsule_digest", Value::from(self.capsule_digest.to_hex())),
            ("input_digest", Value::from(self.input_digest.to_hex())),
            ("output_digest", Value::from(self.output_digest.to_hex())),
            ("run_id", Value::from(self.run_id.to_hex())),
            (
                "executed_at_unix_ms",
                Value::from(self.executed_at_unix_ms.to_string()),
            ),
        ])
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct ExecutionRecord {
    pub manifest: Manifest,
    pub receipt: Receipt,
    pub output: ExecutionOutput,
}

impl ExecutionRecord {
    pub fn to_value(&self) -> Value {
        Value::object(vec![
            ("manifest", self.manifest.to_value()),
            ("receipt", self.receipt.to_value()),
            ("output", self.output.to_value()),
        ])
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum EngineError {
    UnknownCapsule(String),
}

impl core::fmt::Display for EngineError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            EngineError::UnknownCapsule(id) => write!(f, "Unknown capsule: {}", id),
        }
    }
}

pub fn list_manifests() -> Vec<Manifest> {
    profiles::registry()
        .into_iter()
        .map(Capsule::manifest)
        .collect()
}

pub fn manifest_for(id: &str) -> Option<Manifest> {
    profiles::find(id).map(Capsule::manifest)
}

pub fn execute_capsule(id: &str, input: &Value) -> Result<ExecutionRecord, EngineError> {
    let capsule = profiles::find(id).ok_or_else(|| EngineError::UnknownCapsule(id.to_string()))?;
    let manifest = capsule.manifest();

    let mut schema_problems = Vec::new();
    manifest
        .input_schema
        .validate(input, "", &mut schema_problems);

    let mut output = capsule.execute(input);
    if !schema_problems.is_empty() {
        let mut merged = schema_problems;
        merged.extend(output.problems);
        output.problems = merged;
    }

    if output
        .problems
        .iter()
        .any(|problem| matches!(problem.severity, ProblemSeverity::Error))
    {
        output.status = ExecutionStatus::Rejected;
    }

    let capsule_digest = digest_value(&manifest.to_value());
    let input_digest = digest_value(input);
    let output_digest = digest_value(&output.to_value());
    let executed_at_unix_ms = now_unix_ms();
    let seed = format!(
        "{}:{}:{}:{}",
        capsule_digest.to_hex(),
        input_digest.to_hex(),
        output_digest.to_hex(),
        executed_at_unix_ms
    );
    let run_id = sha256(seed.as_bytes());

    Ok(ExecutionRecord {
        manifest,
        receipt: Receipt {
            capsule_id: id.to_string(),
            capsule_digest,
            input_digest,
            output_digest,
            run_id,
            executed_at_unix_ms,
        },
        output,
    })
}

pub fn brief_manifest_value(manifest: &Manifest) -> Value {
    Value::object(vec![
        ("id", Value::from(manifest.id.clone())),
        ("name", Value::from(manifest.name.clone())),
        ("profile", Value::from(manifest.profile.clone())),
        ("summary", Value::from(manifest.summary.clone())),
        ("version", Value::from(manifest.version.clone())),
    ])
}

pub fn digest_value(value: &Value) -> Digest {
    let canonical = to_canonical_string(value);
    sha256(canonical.as_bytes())
}

fn now_unix_ms() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_unknown_capsule() {
        let input = Value::Null;
        let error = execute_capsule("missing", &input).unwrap_err();
        assert_eq!(error, EngineError::UnknownCapsule("missing".to_string()));
    }

    #[test]
    fn test_digest_is_stable_for_same_value() {
        let value = Value::object(vec![("a", Value::from(1usize)), ("b", Value::from(true))]);
        assert_eq!(digest_value(&value), digest_value(&value));
    }
}
