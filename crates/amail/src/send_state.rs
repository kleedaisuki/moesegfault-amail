//! Durable send idempotency state, independent of diagnostic collection.
//!
//! Telemetry opt-out and journal failures must not rotate unresolved keys. The
//! legacy table and filename are retained for concurrent older CLI processes.

use crate::{config::Runtime, local_store};
use anyhow::Result;
use rusqlite::{params, Connection};
use std::time::Duration;

/// Initialize only the command-state table, preserving every existing key.
fn db(cfg: &Runtime) -> Result<Connection> {
    let conn = local_store::open(cfg, Duration::from_secs(30))?;
    conn.execute_batch("CREATE TABLE IF NOT EXISTS send_attempts (
        payload_hash TEXT PRIMARY KEY, attempt_key TEXT NOT NULL, accepted INTEGER NOT NULL DEFAULT 0
    )")?;
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
pub fn accepted(cfg: &Runtime, hash: &str) -> Result<()> {
    db(cfg)?.execute("DELETE FROM send_attempts WHERE payload_hash=?1", [hash])?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

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
