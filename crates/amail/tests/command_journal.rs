//! Hosted subprocess coverage for local-only diagnostics without real accounts.

use rusqlite::Connection;
use std::{
    path::Path,
    process::{Command, Output},
};

/// Isolate every CLI invocation from real state, credentials and provider endpoints.
fn invoke(home: &Path, args: &[&str], enabled: bool) -> Output {
    Command::new(env!("CARGO_BIN_EXE_amail"))
        .args(args)
        .env("AMAIL_HOME", home)
        .env("AMAIL_TELEMETRY", if enabled { "on" } else { "off" })
        .env("AMAIL_API_BASE", "https://mail.example.test")
        .env("AMAIL_ISSUER", "https://identity.example.test")
        .env("AMAIL_CLIENT_ID", "")
        .env("AMAIL_REDIRECT_URI", "")
        .output()
        .unwrap()
}

/// Keep experimental/test files under the repository root.
fn home() -> tempfile::TempDir {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.temp");
    std::fs::create_dir_all(&root).unwrap();
    tempfile::tempdir_in(root).unwrap()
}

/// Read only local diagnostic operational labels and numeric measurements.
fn rows(home: &Path) -> Vec<(String, String, String)> {
    let conn = Connection::open(home.join("telemetry.sqlite3")).unwrap();
    let mut stmt = conn
        .prepare("SELECT command,phase,outcome FROM command_spans ORDER BY id")
        .unwrap();
    stmt.query_map([], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)))
        .unwrap()
        .map(|r| r.unwrap())
        .collect()
}

/// Public JSON remains byte-compatible except its documented opt-out boolean.
#[test]
fn config_and_off_preserve_stdout_exit_and_exclude_private_state() {
    let home = home();
    let enabled = invoke(home.path(), &["config"], true);
    assert!(enabled.status.success());
    assert!(enabled.stderr.is_empty());
    let config: serde_json::Value = serde_json::from_slice(&enabled.stdout).unwrap();
    assert_eq!(config["telemetry_enabled"], true);
    assert_eq!(
        rows(home.path()),
        vec![("config".into(), "command".into(), "success".into())]
    );
    let conn = Connection::open(home.path().join("telemetry.sqlite3")).unwrap();
    assert_eq!(
        conn.query_row("SELECT COUNT(*) FROM events", [], |r| r.get::<_, i64>(0))
            .unwrap(),
        0
    );
    let stored: String = conn
        .query_row(
            "SELECT command_id||command||phase||outcome FROM command_spans",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert!(!stored.contains("example.test"));
    assert!(!stored.contains(&home.path().display().to_string()));
    let off = invoke(home.path(), &["config"], false);
    assert!(off.status.success());
    assert!(off.stderr.is_empty());
    assert_eq!(rows(home.path()).len(), 1);
    let isolated = super_home();
    assert!(invoke(isolated.path(), &["config"], false).status.success());
    assert!(!isolated.path().join("telemetry.sqlite3").exists());
    let mut off_json: serde_json::Value = serde_json::from_slice(&off.stdout).unwrap();
    off_json["telemetry_enabled"] = serde_json::json!(true);
    assert_eq!(config, off_json);
}

/// Avoid shadowing the fixture factory in tests with a named home value.
fn super_home() -> tempfile::TempDir {
    home()
}

/// Failed local work records completion, not the private argument/error string.
#[test]
fn local_failures_keep_exit_and_do_not_poison_api_events() {
    let home = home();
    let missing = home.path().join("synthetic-private-path-missing.zip");
    let out = home.path().join("synthetic-private-output");
    let result = invoke(
        home.path(),
        &[
            "unpack",
            missing.to_str().unwrap(),
            "--out",
            out.to_str().unwrap(),
        ],
        true,
    );
    assert!(!result.status.success());
    assert!(result.stdout.is_empty());
    assert_eq!(
        rows(home.path()),
        vec![("unpack".into(), "command".into(), "failure".into())]
    );
    let conn = Connection::open(home.path().join("telemetry.sqlite3")).unwrap();
    assert_eq!(
        conn.query_row("SELECT COUNT(*) FROM events", [], |r| r.get::<_, i64>(0))
            .unwrap(),
        0
    );
    let bytes = std::fs::read(home.path().join("telemetry.sqlite3")).unwrap();
    assert!(!String::from_utf8_lossy(&bytes).contains("synthetic-private"));
}

/// Guard-only synthetic OAuth failures exercise aliases without keyring or network.
#[test]
fn auth_aliases_are_canonical_and_hidden_upload_is_excluded() {
    let home = home();
    for args in [
        vec!["login", "--no-browser"],
        vec!["auth", "login", "--no-browser"],
        vec!["logout"],
        vec!["auth", "logout"],
        vec!["auth", "status"],
        vec!["get", "synthetic-private-id"],
    ] {
        let result = invoke(home.path(), &args, true);
        assert!(!result.status.success());
        assert!(result.stdout.is_empty());
    }
    let records = rows(home.path());
    assert_eq!(records.iter().filter(|r| r.0 == "auth_login").count(), 2);
    assert_eq!(records.iter().filter(|r| r.0 == "auth_logout").count(), 2);
    assert!(records
        .iter()
        .any(|r| r.0 == "auth_status" && r.2 == "failure"));
    assert!(records
        .iter()
        .any(|r| r.0 == "get" && r.1 == "access_token" && r.2 == "failure"));
    // The actual get dispatch fails before HTTP, but still has an attempt identity.
    // Its local UUID links to the command and access-token boundary, not a native parent.
    let conn = Connection::open(home.path().join("telemetry.sqlite3")).unwrap();
    let linked: (String, String, String) = conn
        .query_row(
            "SELECT e.command_id,e.trace_id,e.span_id FROM events e
         JOIN command_spans c ON c.command_id=e.command_id
         WHERE c.command='get' AND c.phase='command' AND e.operation='messages.get'",
            [],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
        )
        .unwrap();
    assert!(uuid::Uuid::parse_str(&linked.0).is_ok());
    assert_eq!(linked.1.len(), 32);
    assert_eq!(linked.2.len(), 16);
    let before = records.len();
    assert!(invoke(home.path(), &["_telemetry-flush"], true)
        .status
        .success());
    assert_eq!(rows(home.path()).len(), before);
}

/// Synthetic ZIP creation/extraction proves local success boundaries and unchanged output.
#[test]
fn pack_unpack_success_keep_business_files_and_json() {
    let home = home();
    let draft = home.path().join("synthetic-private-draft");
    std::fs::create_dir(&draft).unwrap();
    std::fs::write(draft.join("manifest.toml"), "version=1\nfrom='sender@example.test'\nto=['recipient@example.test']\nsubject='synthetic-private-subject'\n").unwrap();
    std::fs::write(draft.join("body.txt"), "synthetic-private-body").unwrap();
    let archive = home.path().join("synthetic-private.zip");
    let out = home.path().join("synthetic-private-extracted");
    let packed = invoke(
        home.path(),
        &[
            "pack",
            draft.to_str().unwrap(),
            "--out",
            archive.to_str().unwrap(),
        ],
        true,
    );
    assert!(
        packed.status.success(),
        "{}",
        String::from_utf8_lossy(&packed.stderr)
    );
    assert_eq!(
        serde_json::from_slice::<serde_json::Value>(&packed.stdout).unwrap()["packed"],
        true
    );
    let unpacked = invoke(
        home.path(),
        &[
            "unpack",
            archive.to_str().unwrap(),
            "--out",
            out.to_str().unwrap(),
        ],
        true,
    );
    assert!(unpacked.status.success());
    assert_eq!(
        std::fs::read_to_string(out.join("body.txt")).unwrap(),
        "synthetic-private-body"
    );
    assert_eq!(
        rows(home.path()),
        vec![
            ("pack".into(), "command".into(), "success".into()),
            ("unpack".into(), "command".into(), "success".into())
        ]
    );
    let bytes = std::fs::read(home.path().join("telemetry.sqlite3")).unwrap();
    assert!(!String::from_utf8_lossy(&bytes).contains("synthetic-private"));
}

/// Store loss is a fixed stderr notice, never private path or SQLite exception text.
#[test]
fn poisoned_store_and_off_keep_successful_command_unchanged() {
    let home = home();
    std::fs::create_dir(home.path().join("telemetry.sqlite3")).unwrap();
    let result = invoke(home.path(), &["config"], true);
    assert!(result.status.success());
    assert!(serde_json::from_slice::<serde_json::Value>(&result.stdout).is_ok());
    let stderr = String::from_utf8(result.stderr).unwrap();
    assert!(stderr.contains("amail: local diagnostic records lost"));
    assert!(!stderr.contains(&home.path().display().to_string()));
    assert!(!stderr.contains("example.test"));
    let off = invoke(home.path(), &["config"], false);
    assert!(off.status.success());
    assert!(off.stderr.is_empty());
}
