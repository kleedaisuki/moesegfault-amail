//! Public billing command contracts without account, network, or browser side effects.
use serde_json::Value;
use std::{path::Path, process::Command};

/// Keep all CLI fixtures within the repository scratch directory.
fn home() -> tempfile::TempDir {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.temp");
    std::fs::create_dir_all(&root).unwrap();
    tempfile::tempdir_in(root).unwrap()
}

#[test]
fn billing_discovery_explains_human_consent_and_unsettled_usage_offline() {
    let home = home();
    let output = Command::new(env!("CARGO_BIN_EXE_amail"))
        .args(["discover", "billing"])
        .env("AMAIL_HOME", home.path())
        .env("AMAIL_API_BASE", "deliberately-invalid")
        .output()
        .unwrap();
    assert!(output.status.success());
    assert!(output.stderr.is_empty());
    let body: Value = serde_json::from_slice(&output.stdout).unwrap();
    let contract = body["capabilities"]["contract"].as_str().unwrap();
    assert!(contract.contains("human browser"));
    assert!(contract.contains("not payment settled"));
    assert_eq!(std::fs::read_dir(home.path()).unwrap().count(), 0);
}

#[test]
fn billing_rejects_unknown_plans_invalid_ids_and_unbounded_polling_before_runtime() {
    for args in [
        vec!["--machine", "billing", "subscribe", "enterprise"],
        vec![
            "--machine",
            "billing",
            "subscribe",
            "plus",
            "--wait-seconds",
            "901",
        ],
        vec![
            "--machine",
            "billing",
            "manage",
            "--idempotency-key",
            "private-invalid",
        ],
        vec!["--machine", "billing", "session", "private-invalid"],
        vec![
            "--machine",
            "billing",
            "session",
            "123e4567-e89b-12d3-a456-426614174000",
        ],
    ] {
        let home = home();
        let output = Command::new(env!("CARGO_BIN_EXE_amail"))
            .args(args)
            .env("AMAIL_HOME", home.path())
            .output()
            .unwrap();
        assert!(!output.status.success());
        assert!(output.stdout.is_empty());
        let body: Value = serde_json::from_slice(&output.stderr).unwrap();
        assert_eq!(body["data"]["code"], "invalid_arguments");
        assert!(!String::from_utf8_lossy(&output.stderr).contains("private-invalid"));
        assert_eq!(std::fs::read_dir(home.path()).unwrap().count(), 0);
    }
}
