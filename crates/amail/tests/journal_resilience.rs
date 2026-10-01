//! Hosted process-level checks for best-effort diagnostic storage.

use std::process::Command;
use std::process::Stdio;

/// Run ordinary config commands with synthetic homes and no business network activity.
fn config_command(home: &std::path::Path, enabled: bool) -> std::process::Output {
    Command::new(env!("CARGO_BIN_EXE_amail"))
        .arg("config")
        .env("AMAIL_HOME", home)
        .env("AMAIL_TELEMETRY", if enabled { "on" } else { "off" })
        .env("AMAIL_API_BASE", "https://mail.example.test")
        .env("AMAIL_ISSUER", "https://identity.example.test")
        .output()
        .unwrap()
}

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

/// The actual hidden child persists auth failure despite null stdout/stderr.
#[test]
fn next_normal_command_reports_child_failure_once_without_changing_json_or_exit() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.temp");
    std::fs::create_dir_all(&root).unwrap();
    let home = tempfile::tempdir_in(root).unwrap();
    assert!(config_command(home.path(), true).status.success());
    let conn = rusqlite::Connection::open(home.path().join("telemetry.sqlite3")).unwrap();
    conn.execute(
        "INSERT INTO events(operation,status,duration_ms,bytes_bucket,trace_id)
        VALUES('messages.list',200,7,0,'0123456789abcdef0123456789abcdef')",
        [],
    )
    .unwrap();
    let child = Command::new(env!("CARGO_BIN_EXE_amail"))
        .arg("_telemetry-flush")
        .env("AMAIL_HOME", home.path())
        .env("AMAIL_TELEMETRY", "on")
        .env("AMAIL_API_BASE", "https://mail.example.test")
        .env("AMAIL_ISSUER", "https://identity.example.test")
        // Guard fails before looking up OS credentials or making any request.
        .env("AMAIL_CLIENT_ID", "")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .unwrap();
    assert!(child.success());
    let output = config_command(home.path(), true);
    assert!(output.status.success());
    let config: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(config["telemetry_enabled"], true);
    let stderr = String::from_utf8(output.stderr).unwrap();
    let notice: serde_json::Value = serde_json::from_str(
        stderr
            .trim()
            .strip_prefix("amail: telemetry diagnostic ")
            .unwrap(),
    )
    .unwrap();
    assert_eq!(notice["upload"]["outcome"], "failed");
    assert_eq!(notice["upload"]["phase"], "auth");
    assert_eq!(notice["upload"]["error_kind"], "credential_unavailable");
    assert!(notice["upload"]["started_at_ms"].as_i64().unwrap() > 0);
    assert_eq!(notice["pending_events"], 1);
    assert_eq!(notice["upload_failed"], 1);
    assert!(!stderr.contains(&home.path().display().to_string()));
    assert!(!stderr.contains("mail.example.test"));
    let repeated = config_command(home.path(), true);
    assert!(repeated.status.success() && repeated.stderr.is_empty());
    assert_eq!(
        conn.query_row("SELECT COUNT(*) FROM events", [], |r| r.get::<_, i64>(0))
            .unwrap(),
        1
    );
}

/// Interrupted scheduled/running receipts are unresolved, never invented failures or acceptance.
#[test]
fn unresolved_receipts_and_retention_loss_are_visible_but_opt_out_does_not_touch_existing_store() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.temp");
    std::fs::create_dir_all(&root).unwrap();
    let home = tempfile::tempdir_in(root).unwrap();
    assert!(config_command(home.path(), true).status.success());
    let path = home.path().join("telemetry.sqlite3");
    let conn = rusqlite::Connection::open(&path).unwrap();
    conn.execute(
        "INSERT INTO journal_upload(id,attempt_id,started_at_ms,outcome,phase,batch_count)
        VALUES(1,'00000000-0000-4000-8000-000000000001',1790000000123,'running','transport',20)",
        [],
    )
    .unwrap();
    let tx = conn.unchecked_transaction().unwrap();
    for _ in 0..1005 {
        tx.execute(
            "INSERT INTO events(operation,status,duration_ms,bytes_bucket,trace_id)
            VALUES('messages.list',200,7,0,'0123456789abcdef0123456789abcdef')",
            [],
        )
        .unwrap();
    }
    tx.commit().unwrap();
    let before = std::fs::read(&path).unwrap();
    let disabled = config_command(home.path(), false);
    assert!(disabled.status.success() && disabled.stderr.is_empty());
    assert_eq!(std::fs::read(&path).unwrap(), before);
    let enabled = config_command(home.path(), true);
    assert!(enabled.status.success());
    serde_json::from_slice::<serde_json::Value>(&enabled.stdout).unwrap();
    let stderr = String::from_utf8(enabled.stderr).unwrap();
    let notice: serde_json::Value = serde_json::from_str(
        stderr
            .trim()
            .strip_prefix("amail: telemetry diagnostic ")
            .unwrap(),
    )
    .unwrap();
    assert_eq!(notice["upload"]["outcome"], "running");
    assert!(notice["upload"]["finished_at_ms"].is_null());
    assert_eq!(notice["upload_failed"], 0);
    assert_eq!(notice["pending_events"], 1000);
    assert_eq!(notice["pending_evicted"], 5);
    assert!(config_command(home.path(), true).stderr.is_empty());
}
