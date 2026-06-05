//! Verifiable Decision Record (VDR) — builder and verifier.
//!
//! Implements the format and the verification procedure specified in
//! `docs/spec/verifiable-decision-record-v0.md`. The capsule layer
//! (`profiles`) validates that a subject conforms to its profile; this
//! module owns the canonical digests and the VDR envelope.

use crate::engine::{digest_value, execute_capsule, EngineError};
use crate::capsule::ExecutionStatus;
use crate::value::Value;

pub const VDR_VERSION: &str = "0";
pub const AGENT_PROFILE: &str = "ai.agent.action";
pub const AGENT_CAPSULE_ID: &str = "agent.action.replay.v1";

#[derive(Debug)]
pub enum VdrError {
    Engine(EngineError),
    Rejected(Vec<Value>),
    Malformed(String),
}

impl core::fmt::Display for VdrError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            VdrError::Engine(err) => write!(f, "{}", err),
            VdrError::Rejected(_) => write!(f, "subject rejected by its profile capsule"),
            VdrError::Malformed(msg) => write!(f, "malformed record: {}", msg),
        }
    }
}

/// Map a capsule id to its VDR profile id.
pub fn profile_for_capsule(capsule_id: &str) -> Option<&'static str> {
    match capsule_id {
        AGENT_CAPSULE_ID => Some(AGENT_PROFILE),
        _ => None,
    }
}

/// Map a VDR profile id to the capsule that validates it.
pub fn capsule_for_profile(profile: &str) -> Option<&'static str> {
    match profile {
        AGENT_PROFILE => Some(AGENT_CAPSULE_ID),
        _ => None,
    }
}

/// Build a conforming VDR from a subject, validating it through its capsule.
///
/// `subject` is the profile-defined decision payload (for the agent
/// profile: the recorded action). Returns the full VDR object including the
/// receipt, ready to persist.
pub fn build_record(capsule_id: &str, subject: &Value) -> Result<Value, VdrError> {
    let profile = profile_for_capsule(capsule_id)
        .ok_or_else(|| VdrError::Malformed(format!("unknown capsule/profile: {capsule_id}")))?;

    // Validate the subject against its profile capsule.
    let execution = execute_capsule(capsule_id, subject).map_err(VdrError::Engine)?;
    if execution.output.status == ExecutionStatus::Rejected {
        let problems = execution
            .output
            .problems
            .iter()
            .map(|p| p.to_value())
            .collect();
        return Err(VdrError::Rejected(problems));
    }

    let receipt = compute_receipt(profile, subject);
    Ok(Value::object(vec![
        ("vdr_version", Value::from(VDR_VERSION)),
        ("profile", Value::from(profile)),
        ("subject", subject.clone()),
        ("receipt", receipt),
    ]))
}

/// Compute the receipt (digests) for a subject under a profile.
fn compute_receipt(profile: &str, subject: &Value) -> Value {
    let subject_digest = digest_value(subject).to_hex();
    let record_digest = digest_value(&record_core(profile, subject)).to_hex();

    let mut entries: Vec<(&'static str, Value)> = vec![
        ("alg", Value::from("sha-256")),
        ("subject_digest", Value::from(subject_digest)),
        ("record_digest", Value::from(record_digest)),
    ];

    // Profile-specific sub-digests.
    if profile == AGENT_PROFILE {
        entries.push(("input_digest", Value::from(digest_value(&stimulus(subject)).to_hex())));
        entries.push((
            "output_digest",
            Value::from(digest_value(&subject.get("output").cloned().unwrap_or(Value::Null)).to_hex()),
        ));
    }

    Value::object(entries)
}

/// The object hashed for `record_digest`: { vdr_version, profile, subject }.
fn record_core(profile: &str, subject: &Value) -> Value {
    Value::object(vec![
        ("vdr_version", Value::from(VDR_VERSION)),
        ("profile", Value::from(profile)),
        ("subject", subject.clone()),
    ])
}

/// The stimulus hashed for the agent profile `input_digest`:
/// { model, params, input }. `params` is null when absent.
fn stimulus(subject: &Value) -> Value {
    Value::object(vec![
        ("model", subject.get("model").cloned().unwrap_or(Value::Null)),
        ("params", subject.get("params").cloned().unwrap_or(Value::Null)),
        ("input", subject.get("input").cloned().unwrap_or(Value::Null)),
    ])
}

/// Outcome of verifying a VDR.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VerifyReport {
    pub verified: bool,
    pub vdr_version: String,
    pub profile: String,
    pub record_digest: String,
    pub checks: Vec<(String, bool)>,
}

impl VerifyReport {
    pub fn to_value(&self) -> Value {
        Value::object(vec![
            ("verified", Value::from(self.verified)),
            ("vdr_version", Value::from(self.vdr_version.clone())),
            ("profile", Value::from(self.profile.clone())),
            ("record_digest", Value::from(self.record_digest.clone())),
            (
                "checks",
                Value::object(
                    self.checks
                        .iter()
                        .map(|(k, v)| (k.clone(), Value::from(*v)))
                        .collect(),
                ),
            ),
        ])
    }
}

/// Verify a VDR per spec §7: recompute every digest from the stored subject
/// and compare to the stored receipt. Pure integrity check — depends only on
/// the record and maths, never on trusting the producer.
pub fn verify_record(vdr: &Value) -> Result<VerifyReport, VdrError> {
    let vdr_version = vdr
        .get("vdr_version")
        .and_then(Value::as_str)
        .ok_or_else(|| VdrError::Malformed("missing vdr_version".into()))?;
    if vdr_version != VDR_VERSION {
        return Err(VdrError::Malformed(format!(
            "unsupported vdr_version: {vdr_version}"
        )));
    }
    let profile = vdr
        .get("profile")
        .and_then(Value::as_str)
        .ok_or_else(|| VdrError::Malformed("missing profile".into()))?;
    let subject = vdr
        .get("subject")
        .ok_or_else(|| VdrError::Malformed("missing subject".into()))?;
    let receipt = vdr
        .get("receipt")
        .ok_or_else(|| VdrError::Malformed("missing receipt".into()))?;

    let alg = receipt.get("alg").and_then(Value::as_str).unwrap_or("");
    if alg != "sha-256" {
        return Err(VdrError::Malformed(format!("unsupported alg: {alg}")));
    }

    let fresh = compute_receipt(profile, subject);
    let mut checks: Vec<(String, bool)> = Vec::new();
    let mut all_ok = true;

    for key in ["subject_digest", "record_digest", "input_digest", "output_digest"] {
        let stored = receipt.get(key).and_then(Value::as_str);
        let recomputed = fresh.get(key).and_then(Value::as_str);
        match (stored, recomputed) {
            (Some(s), Some(r)) => {
                let ok = s == r;
                checks.push((key.to_string(), ok));
                all_ok = all_ok && ok;
            }
            (None, None) => {} // digest not used by this profile
            _ => {
                // present on one side only → mismatch
                checks.push((key.to_string(), false));
                all_ok = false;
            }
        }
    }

    let record_digest = fresh
        .get("record_digest")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();

    Ok(VerifyReport {
        verified: all_ok,
        vdr_version: vdr_version.to_string(),
        profile: profile.to_string(),
        record_digest,
        checks,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::json::parse as parse_json;

    const SUBJECT: &str = r#"
    {
      "agent_id": "support-triage-agent",
      "action_id": "act-2026-05-19-001",
      "occurred_at_unix_ms": "1747700000000",
      "model": { "provider": "anthropic", "name": "claude-3-5-sonnet", "version": "20250101" },
      "params": { "temperature": 0, "max_tokens": 512 },
      "input": { "messages": [ { "role": "user", "content": "Hi" } ] },
      "output": { "content": "Hello.", "finish_reason": "end_turn" }
    }
    "#;

    fn subject() -> Value {
        parse_json(SUBJECT).unwrap()
    }

    #[test]
    fn test_build_record_shape() {
        let vdr = build_record(AGENT_CAPSULE_ID, &subject()).unwrap();
        assert_eq!(vdr.get("vdr_version").and_then(Value::as_str), Some("0"));
        assert_eq!(vdr.get("profile").and_then(Value::as_str), Some(AGENT_PROFILE));
        assert!(vdr.get("subject").is_some());
        let receipt = vdr.get("receipt").unwrap();
        assert_eq!(receipt.get("alg").and_then(Value::as_str), Some("sha-256"));
        for key in ["subject_digest", "record_digest", "input_digest", "output_digest"] {
            let d = receipt.get(key).and_then(Value::as_str).unwrap();
            assert_eq!(d.len(), 64, "{key} must be 64 hex chars");
        }
    }

    #[test]
    fn test_build_is_deterministic() {
        let a = build_record(AGENT_CAPSULE_ID, &subject()).unwrap();
        let b = build_record(AGENT_CAPSULE_ID, &subject()).unwrap();
        assert_eq!(a, b);
    }

    #[test]
    fn test_verify_accepts_untampered() {
        let vdr = build_record(AGENT_CAPSULE_ID, &subject()).unwrap();
        let report = verify_record(&vdr).unwrap();
        assert!(report.verified);
        assert!(report.checks.iter().all(|(_, ok)| *ok));
    }

    #[test]
    fn test_verify_detects_tampered_subject() {
        let mut vdr = build_record(AGENT_CAPSULE_ID, &subject()).unwrap();
        // Tamper: change output content in the stored subject without
        // recomputing the receipt.
        let mut obj = vdr.as_object().unwrap().clone();
        let mut subj = obj.get("subject").unwrap().as_object().unwrap().clone();
        let mut output = subj.get("output").unwrap().as_object().unwrap().clone();
        output.insert("content".to_string(), Value::from("TAMPERED"));
        subj.insert("output".to_string(), Value::Object(output));
        obj.insert("subject".to_string(), Value::Object(subj));
        vdr = Value::Object(obj);

        let report = verify_record(&vdr).unwrap();
        assert!(!report.verified);
        // subject/record/output digests break; input_digest still matches.
        let map: std::collections::HashMap<_, _> = report.checks.iter().cloned().collect();
        assert_eq!(map.get("output_digest"), Some(&false));
        assert_eq!(map.get("record_digest"), Some(&false));
        assert_eq!(map.get("input_digest"), Some(&true));
    }

    #[test]
    fn test_record_digest_differs_from_subject_digest() {
        let vdr = build_record(AGENT_CAPSULE_ID, &subject()).unwrap();
        let receipt = vdr.get("receipt").unwrap();
        assert_ne!(
            receipt.get("subject_digest").and_then(Value::as_str),
            receipt.get("record_digest").and_then(Value::as_str),
        );
    }

    #[test]
    fn test_build_rejects_invalid_subject() {
        let bad = parse_json(r#"{ "action_id": "x" }"#).unwrap();
        let err = build_record(AGENT_CAPSULE_ID, &bad).unwrap_err();
        matches!(err, VdrError::Rejected(_));
    }

    /// The published conformance vectors (docs/spec/test-vectors/) MUST be
    /// reproduced exactly by the reference engine. This locks the standard:
    /// any independent RFC 8785 implementation that matches these digests is
    /// interoperable with Determs.
    #[test]
    fn test_conformance_vectors() {
        let raw = include_str!("../docs/spec/test-vectors/ai.agent.action-v0.json");
        let doc = parse_json(raw).unwrap();
        let vectors = doc
            .get("vectors")
            .and_then(Value::as_array)
            .expect("vectors array");
        assert!(!vectors.is_empty(), "no vectors found");
        for vector in vectors {
            let name = vector.get("name").and_then(Value::as_str).unwrap_or("?");
            let profile = vector
                .get("profile")
                .and_then(Value::as_str)
                .expect("vector profile");
            let subject = vector.get("subject").expect("vector subject");
            let expected = vector.get("expected").expect("vector expected");
            let capsule = capsule_for_profile(profile)
                .unwrap_or_else(|| panic!("unknown profile in vector {name}"));

            let vdr = build_record(capsule, subject)
                .unwrap_or_else(|e| panic!("build_record failed for {name}: {e}"));
            let receipt = vdr.get("receipt").expect("receipt");

            for key in [
                "alg",
                "subject_digest",
                "record_digest",
                "input_digest",
                "output_digest",
            ] {
                if let Some(exp) = expected.get(key).and_then(Value::as_str) {
                    let got = receipt.get(key).and_then(Value::as_str);
                    assert_eq!(got, Some(exp), "vector {name}: {key} mismatch");
                }
            }

            let report = verify_record(&vdr).unwrap();
            assert!(report.verified, "vector {name}: VDR must verify");
        }
    }
}
