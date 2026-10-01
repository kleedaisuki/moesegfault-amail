//! Hosted process-level checks for best-effort diagnostic storage.

use std::process::Command;

/// A diagnostic-only SQLite failure cannot break a successful public command.
#[test]
fn config_survives_journal_failure_without_polluting_json_stdout() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.temp");
    std::fs::create_dir_all(&root).unwrap();
    let temp = tempfile::tempdir_in(root).unwrap();
    std::fs::create_dir(temp.path().join("telemetry.sqlite3")).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_amail"))
        .args(["config"])
        .env("AMAIL_HOME", temp.path())
        .env("AMAIL_TELEMETRY", "on")
        .output()
        .unwrap();
    assert!(output.status.success());
    let config: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(config["telemetry_enabled"], true);
    let stderr = String::from_utf8(output.stderr).unwrap();
    assert!(stderr.contains("telemetry unavailable stage=initialize sqlite_code="));
    assert!(!stderr.contains(&temp.path().display().to_string()));
}

/// Opt-out skips even initialization, not just uploads and event insertion.
#[test]
fn telemetry_opt_out_does_not_open_a_diagnostic_store() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.temp");
    std::fs::create_dir_all(&root).unwrap();
    let temp = tempfile::tempdir_in(root).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_amail"))
        .args(["config"])
        .env("AMAIL_HOME", temp.path())
        .env("AMAIL_TELEMETRY", "off")
        .output()
        .unwrap();
    assert!(output.status.success());
    assert!(output.stderr.is_empty());
    assert!(!temp.path().join("telemetry.sqlite3").exists());
    let config: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(config["telemetry_enabled"], false);
}
