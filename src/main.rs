use std::env;
use std::fs;
use std::io::{self, Read};
use std::process::ExitCode;

use determs::{
    brief_manifest_value, build_record, execute_capsule, list_manifests, manifest_for, parse_json,
    sha256, to_canonical_string, to_pretty_string, verify_record, Value, AGENT_CAPSULE_ID,
};

const NAME: &str = "determs";
const VERSION: &str = env!("CARGO_PKG_VERSION");

fn print_usage() {
    eprintln!(
        r#"{NAME} — Verifiable Decision Records for AI agents

USAGE:
    {NAME} list
    {NAME} describe <capsule-id>
    {NAME} execute <capsule-id> [--input <file>|-] [--canonical]
    {NAME} capture [--input <subject>|-] [--output <file>] [--capsule <id>]
    {NAME} verify  [--record <file>|-]
    {NAME} replay  [--record <file>|-] [--canonical]
    {NAME} hash <text>
    {NAME} version
    {NAME} help

A "subject" is a decision payload (for the agent profile: a recorded
action). `capture` wraps a subject into a Verifiable Decision Record (VDR)
with a receipt; `verify` recomputes every digest and checks integrity;
`replay` rebuilds the record from the stored subject and confirms it is
bit-identical. Verification depends only on maths — never on trusting us.

EXAMPLES:
    {NAME} capture --input examples/agent_action_example.json --output /tmp/record.json
    {NAME} verify  --record /tmp/record.json
    {NAME} replay  --record /tmp/record.json
"#
    );
}

fn print_version() {
    println!("{NAME} {VERSION}");
    println!("Verifiable Decision Records for AI agents — reference implementation");
}

fn read_input_source(path: Option<&str>) -> Result<String, String> {
    match path {
        Some("-") | None => {
            let mut input = String::new();
            io::stdin()
                .read_to_string(&mut input)
                .map_err(|err| err.to_string())?;
            Ok(input)
        }
        Some(path) => {
            fs::read_to_string(path).map_err(|err| format!("Cannot read {}: {}", path, err))
        }
    }
}

fn write_output(path: Option<&str>, content: &str) -> Result<(), String> {
    match path {
        Some(path) => fs::write(path, content).map_err(|err| format!("Cannot write {}: {}", path, err)),
        None => {
            println!("{content}");
            Ok(())
        }
    }
}

fn cmd_list() {
    let manifests = list_manifests();
    let payload = Value::array(manifests.iter().map(brief_manifest_value).collect());
    println!("{}", to_pretty_string(&payload));
}

fn cmd_describe(id: &str) -> Result<(), String> {
    let manifest = manifest_for(id).ok_or_else(|| format!("Unknown capsule: {}", id))?;
    println!("{}", to_pretty_string(&manifest.to_value()));
    Ok(())
}

fn cmd_execute(args: &[String]) -> Result<(), String> {
    if args.is_empty() {
        return Err("Missing capsule id".to_string());
    }
    let capsule_id = &args[0];
    let mut input_path: Option<&str> = None;
    let mut canonical = false;
    let mut index = 1;
    while index < args.len() {
        match args[index].as_str() {
            "--input" => {
                index += 1;
                input_path = Some(
                    args.get(index)
                        .ok_or_else(|| "Missing value after --input".to_string())?
                        .as_str(),
                );
            }
            "--canonical" => canonical = true,
            other => return Err(format!("Unknown option: {}", other)),
        }
        index += 1;
    }

    let payload = read_input_source(input_path)?;
    let input = parse_json(&payload).map_err(|err| err.to_string())?;
    let record = execute_capsule(capsule_id, &input).map_err(|err| err.to_string())?;
    let output = record.to_value();
    if canonical {
        println!("{}", to_canonical_string(&output));
    } else {
        println!("{}", to_pretty_string(&output));
    }
    Ok(())
}

fn cmd_capture(args: &[String]) -> Result<(), String> {
    let mut input_path: Option<&str> = None;
    let mut output_path: Option<&str> = None;
    let mut capsule_id: &str = AGENT_CAPSULE_ID;
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--input" => {
                index += 1;
                input_path = Some(
                    args.get(index)
                        .ok_or_else(|| "Missing value after --input".to_string())?
                        .as_str(),
                );
            }
            "--output" => {
                index += 1;
                output_path = Some(
                    args.get(index)
                        .ok_or_else(|| "Missing value after --output".to_string())?
                        .as_str(),
                );
            }
            "--capsule" => {
                index += 1;
                capsule_id = args
                    .get(index)
                    .ok_or_else(|| "Missing value after --capsule".to_string())?
                    .as_str();
            }
            other => return Err(format!("Unknown option: {}", other)),
        }
        index += 1;
    }

    let payload = read_input_source(input_path)?;
    let subject = parse_json(&payload).map_err(|err| err.to_string())?;
    let vdr = build_record(capsule_id, &subject).map_err(|err| err.to_string())?;
    write_output(output_path, &to_pretty_string(&vdr))
}

fn load_record(path: Option<&str>) -> Result<Value, String> {
    let raw = read_input_source(path)?;
    parse_json(&raw).map_err(|err| err.to_string())
}

fn cmd_verify(args: &[String]) -> Result<(), String> {
    let mut record_path: Option<&str> = None;
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--record" => {
                index += 1;
                record_path = Some(
                    args.get(index)
                        .ok_or_else(|| "Missing value after --record".to_string())?
                        .as_str(),
                );
            }
            other => return Err(format!("Unknown option: {}", other)),
        }
        index += 1;
    }

    let vdr = load_record(record_path)?;
    let report = verify_record(&vdr).map_err(|err| err.to_string())?;
    println!("{}", to_pretty_string(&report.to_value()));
    if report.verified {
        Ok(())
    } else {
        Err("verification failed: a digest does not match the stored record".to_string())
    }
}

fn cmd_replay(args: &[String]) -> Result<(), String> {
    let mut record_path: Option<&str> = None;
    let mut canonical = false;
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--record" => {
                index += 1;
                record_path = Some(
                    args.get(index)
                        .ok_or_else(|| "Missing value after --record".to_string())?
                        .as_str(),
                );
            }
            "--canonical" => canonical = true,
            other => return Err(format!("Unknown option: {}", other)),
        }
        index += 1;
    }

    let stored = load_record(record_path)?;
    let capsule_id = stored
        .get("profile")
        .and_then(Value::as_str)
        .and_then(determs::vdr::capsule_for_profile)
        .ok_or_else(|| "Record has no known profile".to_string())?;
    let subject = stored
        .get("subject")
        .ok_or_else(|| "Record is missing 'subject'".to_string())?;

    let rebuilt = build_record(capsule_id, subject).map_err(|err| err.to_string())?;
    let matches = stored.get("receipt") == rebuilt.get("receipt");

    let report = Value::object(vec![
        ("replay_matches", Value::from(matches)),
        ("stored_receipt", stored.get("receipt").cloned().unwrap_or(Value::Null)),
        ("rebuilt_receipt", rebuilt.get("receipt").cloned().unwrap_or(Value::Null)),
    ]);
    if canonical {
        println!("{}", to_canonical_string(&report));
    } else {
        println!("{}", to_pretty_string(&report));
    }

    if matches {
        Ok(())
    } else {
        Err("replay mismatch: rebuilt receipt differs from stored receipt".to_string())
    }
}

fn cmd_hash(args: &[String]) -> Result<(), String> {
    if args.is_empty() {
        return Err("Missing text to hash".to_string());
    }
    let digest = sha256(args.join(" ").as_bytes());
    println!("{}", digest);
    Ok(())
}

fn main() -> ExitCode {
    let args: Vec<String> = env::args().collect();

    if args.len() < 2 {
        print_usage();
        return ExitCode::from(1);
    }

    let result = match args[1].as_str() {
        "help" | "--help" | "-h" => {
            print_usage();
            Ok(())
        }
        "version" | "--version" | "-V" => {
            print_version();
            Ok(())
        }
        "list" => {
            cmd_list();
            Ok(())
        }
        "describe" => match args.get(2) {
            Some(id) => cmd_describe(id),
            None => Err("Missing capsule id".to_string()),
        },
        "execute" => cmd_execute(&args[2..]),
        "capture" => cmd_capture(&args[2..]),
        "verify" => cmd_verify(&args[2..]),
        "replay" => cmd_replay(&args[2..]),
        "hash" => cmd_hash(&args[2..]),
        other => Err(format!("Unknown command: {}", other)),
    };

    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(err) => {
            eprintln!("Error: {}", err);
            ExitCode::from(1)
        }
    }
}
