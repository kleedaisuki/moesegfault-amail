//! Durable send idempotency state, independent of diagnostic collection.
//!
//! Telemetry opt-out and journal failures must not rotate unresolved keys. The
//! legacy table and filename are retained for concurrent older CLI processes.

use crate::{config::Runtime, local_store};
use anyhow::{Context, Result};
use rusqlite::{params, Connection};
use serde_json::{json, Value};
use std::time::Duration;

/// Initialize only the command-state table, preserving every existing key.
fn db(cfg: &Runtime) -> Result<Connection> {
    let conn = local_store::open(cfg, Duration::from_secs(30))?;
    conn.execute_batch("CREATE TABLE IF NOT EXISTS send_attempts (
        payload_hash TEXT PRIMARY KEY, attempt_key TEXT NOT NULL, accepted INTEGER NOT NULL DEFAULT 0
    )")?;
    conn.execute_batch(
        "CREATE TABLE IF NOT EXISTS send_receipts (
        attempt_key TEXT PRIMARY KEY, receipt TEXT NOT NULL, accepted_at INTEGER NOT NULL
    )",
    )?;
    Ok(conn)
}

/// Reuse one idempotency key for an unresolved identical payload.
/// A racing caller reads the winner of INSERT OR IGNORE, never its own proposal.
pub fn send_key(cfg: &Runtime, hash: &str, random_key: &str) -> Result<String> {
    let conn = db(cfg)?;
    conn.execute(
        "INSERT OR IGNORE INTO send_attempts(payload_hash,attempt_key) VALUES(?1,?2)",
        params![hash, random_key],
    )?;
    Ok(conn.query_row(
        "SELECT attempt_key FROM send_attempts WHERE payload_hash=?1",
        [hash],
        |r| r.get(0),
    )?)
}

/// Release a saved key only after a definitive accepted response.
/// An unknown/failed network result must leave this row intact.
#[cfg(test)]
pub fn accepted(cfg: &Runtime, hash: &str) -> Result<()> {
    db(cfg)?.execute("DELETE FROM send_attempts WHERE payload_hash=?1", [hash])?;
    Ok(())
}

/// Commit a bounded acceptance receipt before rotating an unresolved payload key.
/// An explicit intent cannot accidentally release another concurrent default intent.
/// Stored records prove only past API acceptance, never delivery or read state.
pub fn record_accepted(cfg: &Runtime, hash: &str, key: &str, response: &Value) -> Result<()> {
    let mut conn = db(cfg)?;
    let tx = conn.transaction()?;
    let receipt = json!({"schema":"amail.send-receipt.v1", "idempotency_key":key,
        "id":response.get("id").cloned().unwrap_or(Value::Null),
        "state":"accepted", "source":"local", "interpretation":"past_api_acceptance_not_current_delivery"});
    tx.execute("INSERT INTO send_receipts(attempt_key,receipt,accepted_at) VALUES(?1,?2,unixepoch())
        ON CONFLICT(attempt_key) DO UPDATE SET receipt=excluded.receipt,accepted_at=excluded.accepted_at",
        params![key, receipt.to_string()])?;
    tx.execute("DELETE FROM send_receipts WHERE attempt_key NOT IN
        (SELECT attempt_key FROM send_receipts ORDER BY accepted_at DESC,attempt_key DESC LIMIT 100)", [])?;
    tx.execute(
        "DELETE FROM send_attempts WHERE payload_hash=?1 AND attempt_key=?2",
        params![hash, key],
    )?;
    tx.commit()?;
    Ok(())
}

/// Read one accepted receipt, without implying that local state is server authority.
pub fn receipt(cfg: &Runtime, key: &str) -> Result<Value> {
    if uuid::Uuid::parse_str(key).is_err() {
        return Err(crate::machine::invalid_input(
            "idempotency key must be a UUID",
        ));
    }
    let conn = db(cfg)?;
    let encoded: String = conn
        .query_row(
            "SELECT receipt FROM send_receipts WHERE attempt_key=?1",
            [key],
            |r| r.get(0),
        )
        .context("local accepted receipt not found; query send-status without --local")?;
    Ok(serde_json::from_str(&encoded)?)
}

/// Discover recent receipts after losing process output; retain at most 100 intents.
pub fn receipts(cfg: &Runtime, limit: u32) -> Result<Value> {
    if !(1..=100).contains(&limit) {
        return Err(crate::machine::invalid_input("limit must be 1..100"));
    }
    let conn = db(cfg)?;
    let mut statement = conn.prepare("SELECT receipt,accepted_at FROM send_receipts ORDER BY accepted_at DESC,attempt_key DESC LIMIT ?1")?;
    let rows = statement.query_map([limit], |row| {
        Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)?))
    })?;
    let mut values = Vec::new();
    for row in rows {
        let (encoded, time) = row?;
        let mut value: Value = serde_json::from_str(&encoded)?;
        value["accepted_at"] = json!(time);
        values.push(value);
    }
    Ok(json!({"receipts":values, "retained_max":100}))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Acceptance is discoverable before stdout; explicit acceptance cannot rotate a different intent.
    #[test]
    fn receipt_survives_output_loss_without_permanent_payload_dedup() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.temp");
        std::fs::create_dir_all(&root).unwrap();
        let temp = tempfile::tempdir_in(root).unwrap();
        let cfg = crate::telemetry::tests::config(temp.path());
        let key = uuid::Uuid::new_v4().to_string();
        let explicit = uuid::Uuid::new_v4().to_string();
        assert_eq!(send_key(&cfg, "hash", &key).unwrap(), key);
        record_accepted(&cfg, "hash", &explicit, &json!({"id":"message"})).unwrap();
        assert_eq!(send_key(&cfg, "hash", "replacement").unwrap(), key);
        record_accepted(&cfg, "hash", &key, &json!({"id":"message"})).unwrap();
        assert_eq!(receipt(&cfg, &key).unwrap()["id"], "message");
        assert_eq!(
            receipts(&cfg, 20).unwrap()["receipts"]
                .as_array()
                .unwrap()
                .len(),
            2
        );
        assert_eq!(send_key(&cfg, "hash", "new-intent").unwrap(), "new-intent");
    }

    /// Receipt discovery is bounded without dropping any unresolved attempt.
    #[test]
    fn accepted_receipts_are_bounded_at_one_hundred() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.temp");
        std::fs::create_dir_all(&root).unwrap();
        let temp = tempfile::tempdir_in(root).unwrap();
        let cfg = crate::telemetry::tests::config(temp.path());
        send_key(&cfg, "unresolved", "original").unwrap();
        for _ in 0..101 {
            let key = uuid::Uuid::new_v4().to_string();
            record_accepted(&cfg, "different-hash", &key, &json!({"id":"m"})).unwrap();
        }
        assert_eq!(
            receipts(&cfg, 100).unwrap()["receipts"]
                .as_array()
                .unwrap()
                .len(),
            100
        );
        assert_eq!(
            send_key(&cfg, "unresolved", "replacement").unwrap(),
            "original"
        );
    }

    /// An older CLI's unresolved key survives independent telemetry migration.
    #[test]
    fn reuses_legacy_key_until_definitive_acceptance() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.temp");
        std::fs::create_dir_all(&root).unwrap();
        let temp = tempfile::tempdir_in(root).unwrap();
        let cfg = crate::telemetry::tests::config(temp.path());
        let conn = local_store::open(&cfg, Duration::from_secs(1)).unwrap();
        conn.execute_batch("CREATE TABLE send_attempts (
            payload_hash TEXT PRIMARY KEY, attempt_key TEXT NOT NULL, accepted INTEGER NOT NULL DEFAULT 0
        ); INSERT INTO send_attempts VALUES ('hash', 'legacy-key', 0)").unwrap();
        crate::telemetry::init(&cfg).unwrap();
        assert_eq!(send_key(&cfg, "hash", "replacement").unwrap(), "legacy-key");
        // Repeated calls model an unresolved transport outcome, not acceptance.
        assert_eq!(send_key(&cfg, "hash", "another").unwrap(), "legacy-key");
        accepted(&cfg, "hash").unwrap();
        assert_eq!(send_key(&cfg, "hash", "next").unwrap(), "next");
    }

    /// New command state does not require a diagnostic schema or migration.
    #[test]
    fn independent_writers_share_one_key_without_creating_event_tables() {
        use std::sync::{Arc, Barrier};
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.temp");
        std::fs::create_dir_all(&root).unwrap();
        let temp = tempfile::tempdir_in(root).unwrap();
        let cfg = crate::telemetry::tests::config(temp.path());
        let barrier = Arc::new(Barrier::new(3));
        let workers: Vec<_> = ["proposal-one", "proposal-two"]
            .into_iter()
            .map(|key| {
                let cfg = cfg.clone();
                let barrier = barrier.clone();
                std::thread::spawn(move || {
                    barrier.wait();
                    send_key(&cfg, "same-hash", key).unwrap()
                })
            })
            .collect();
        barrier.wait();
        let keys: Vec<_> = workers
            .into_iter()
            .map(|worker| worker.join().unwrap())
            .collect();
        assert_eq!(keys[0], keys[1]);
        let conn = db(&cfg).unwrap();
        let event_tables: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM sqlite_master WHERE name IN ('events','journal_state')",
                [],
                |r| r.get(0),
            )
            .unwrap();
        assert_eq!(event_tables, 0);
    }
}
