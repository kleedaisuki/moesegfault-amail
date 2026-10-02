//! Hosted binary-contract checks with no network or real mailbox credentials.
use serde_json::Value;
use std::{
    path::Path,
    process::{Command, Output},
};

/// Isolate fixtures under the repository scratch directory.
fn home() -> tempfile::TempDir {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.temp");
    std::fs::create_dir_all(&root).unwrap();
    tempfile::tempdir_in(root).unwrap()
}
/// Intentionally invalid runtime configuration proves discovery is truly offline.
fn invoke(home: &Path, args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_amail"))
        .args(args)
        .env("AMAIL_HOME", home)
        .env("AMAIL_TELEMETRY", "off")
        .env("AMAIL_API_BASE", "not-a-url")
        .output()
        .unwrap()
}

#[test]
fn discovery_needs_no_runtime_and_leaves_no_state() {
    let home = home();
    let output = invoke(home.path(), &["discover"]);
    assert!(output.status.success());
    assert!(output.stderr.is_empty());
    let root: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(root["schema"], "amail.discover.v1");
    for topic in root["capabilities"]["topics"].as_array().unwrap() {
        let output = invoke(home.path(), &["discover", topic.as_str().unwrap()]);
        assert!(output.status.success());
        assert!(output.stderr.is_empty());
        let leaf: Value = serde_json::from_slice(&output.stdout).unwrap();
        if let Some(children) = leaf["capabilities"]["children"].as_array() {
            for child in children {
                assert!(invoke(home.path(), &["discover", child.as_str().unwrap()])
                    .status
                    .success());
            }
        }
    }
    assert_eq!(std::fs::read_dir(home.path()).unwrap().count(), 0);
}

#[test]
fn machine_parse_failure_is_structured_and_excludes_argument_prose() {
    let home = home();
    let output = invoke(
        home.path(),
        &["--machine", "events", "--limit", "private-invalid-value"],
    );
    assert!(!output.status.success());
    assert!(output.stdout.is_empty());
    let value: Value = serde_json::from_slice(&output.stderr).unwrap();
    assert_eq!(value["schema"], "amail.machine.v1");
    assert_eq!(value["event"], "error");
    assert_eq!(value["data"]["code"], "invalid_arguments");
    assert_eq!(value["data"]["next_action"], "fix_input");
    assert!(!String::from_utf8_lossy(&output.stderr).contains("private-invalid-value"));
    assert_eq!(std::fs::read_dir(home.path()).unwrap().count(), 0);
}
