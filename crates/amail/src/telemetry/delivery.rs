//! Bounded diagnostic receipts and retention, independent of auth/send state.

use anyhow::Result;
use rusqlite::{params, Connection, OptionalExtension, Transaction, TransactionBehavior};
use serde::Serialize;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

/// Live diagnostic row bounds, not a physical shared database-file size cap.
pub(super) const PENDING_LIMIT: i64 = 1000;
/// Locally accepted history is retained independently of offline pending events.
pub(super) const HISTORY_LIMIT: i64 = 200;

/// One bounded last attempt; no outcome asserts retention by the remote Queue sink.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub(super) enum Outcome {
    /// A detached process was requested, not observed to have started.
    Scheduled,
    /// Work started but its result has not been persisted.
    Running,
    /// A complete API acknowledgement confirmed this batch count.
    Accepted,
    /// No pending events existed; no remote acceptance is asserted.
    Empty,
    /// A local dependency or HTTP status definitively refused this attempt.
    Failed,
    /// Network/body/acknowledgement failure leaves API acceptance unknown.
    Unknown,
}

impl Outcome {
    /// Stable SQLite labels; decoding never exposes arbitrary stored strings.
    fn label(self) -> &'static str {
        match self {
            Self::Scheduled => "scheduled",
            Self::Running => "running",
            Self::Accepted => "accepted",
            Self::Failed => "failed",
            Self::Unknown => "unknown",
            Self::Empty => "empty",
        }
    }

    /// Refuse an invalid diagnostic state without dumping database text.
    fn parse(value: &str) -> rusqlite::Result<Self> {
        match value {
            "scheduled" => Ok(Self::Scheduled),
            "running" => Ok(Self::Running),
            "accepted" => Ok(Self::Accepted),
            "failed" => Ok(Self::Failed),
            "empty" => Ok(Self::Empty),
            "unknown" => Ok(Self::Unknown),
            _ => Err(rusqlite::Error::InvalidQuery),
        }
    }
}

/// An upload's causal identity and monotonic clock; never a business operation span.
pub(super) struct Attempt {
    /// Generated UUID used for compare-and-swap completion of the last receipt.
    pub id: String,
    /// Monotonic start before credential acquisition.
    start: Instant,
}

/// Best-effort UTC milliseconds; never fabricate a clock when it is unavailable.
pub(super) fn utc_ms() -> Option<i64> {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .ok()
        .and_then(|time| i64::try_from(time.as_millis()).ok())
}

/// Add diagnostic-only state in the existing shared physical database.
pub(super) fn schema(conn: &Connection) -> Result<()> {
    conn.execute_batch(
        "CREATE TABLE IF NOT EXISTS journal_health (
        id INTEGER PRIMARY KEY CHECK(id=1), pending_evicted INTEGER NOT NULL DEFAULT 0,
        history_pruned INTEGER NOT NULL DEFAULT 0, upload_failed INTEGER NOT NULL DEFAULT 0,
        upload_unknown INTEGER NOT NULL DEFAULT 0, last_pruned_at_ms INTEGER,
        reported_evicted INTEGER NOT NULL DEFAULT 0, reported_failed INTEGER NOT NULL DEFAULT 0,
        reported_unknown INTEGER NOT NULL DEFAULT 0, reported_receipt TEXT
    ); INSERT OR IGNORE INTO journal_health(id) VALUES(1);
    CREATE TABLE IF NOT EXISTS journal_upload (
        id INTEGER PRIMARY KEY CHECK(id=1), attempt_id TEXT NOT NULL,
        scheduled_at_ms INTEGER, started_at_ms INTEGER, finished_at_ms INTEGER,
        elapsed_ms INTEGER, outcome TEXT NOT NULL, phase TEXT NOT NULL,
        error_kind TEXT, http_status INTEGER, correlation_id TEXT, batch_count INTEGER NOT NULL,
        os_error_code INTEGER
    );",
    )?;
    Ok(())
}

/// Begin a short write transaction, never retained over credentials/network I/O.
pub(super) fn transaction(conn: &Connection) -> Result<Transaction<'_>> {
    Ok(Transaction::new_unchecked(
        conn,
        TransactionBehavior::Immediate,
    )?)
}

/// Prune only owned event rows, atomically accounting for pending versus accepted history.
/// The caller commits this with insertion/acceptance or startup maintenance.
pub(super) fn prune(conn: &Connection) -> Result<()> {
    let evicted = conn.execute(
        "DELETE FROM events WHERE uploaded=0 AND id NOT IN (
        SELECT id FROM events WHERE uploaded=0 ORDER BY id DESC LIMIT ?1)",
        [PENDING_LIMIT],
    )? as i64;
    let history = conn.execute(
        "DELETE FROM events WHERE uploaded=1 AND id NOT IN (
        SELECT id FROM events WHERE uploaded=1 ORDER BY id DESC LIMIT ?1)",
        [HISTORY_LIMIT],
    )? as i64;
    if evicted != 0 || history != 0 {
        conn.execute(
            "UPDATE journal_health SET
            pending_evicted=pending_evicted+MIN(?1,9223372036854775807-pending_evicted),
            history_pruned=history_pruned+MIN(?2,9223372036854775807-history_pruned),
            last_pruned_at_ms=?3 WHERE id=1",
            params![evicted, history, utc_ms()],
        )?;
    }
    Ok(())
}

/// Record scheduling in the same transaction as the existing 30-second throttle claim.
pub(super) fn scheduled(conn: &Connection, id: &str) -> Result<()> {
    conn.execute(
        "INSERT INTO journal_upload(id,attempt_id,scheduled_at_ms,outcome,phase,batch_count)
        VALUES(1,?1,?2,'scheduled','spawn',0) ON CONFLICT(id) DO UPDATE SET
        attempt_id=excluded.attempt_id,scheduled_at_ms=excluded.scheduled_at_ms,
        started_at_ms=NULL,finished_at_ms=NULL,elapsed_ms=NULL,outcome='scheduled',phase='spawn',
        error_kind=NULL,http_status=NULL,correlation_id=NULL,batch_count=0,os_error_code=NULL",
        params![id, utc_ms()],
    )?;
    Ok(())
}

/// Start a manual attempt, or claim only the matching scheduled child's receipt.
/// A late older child cannot replace a newer receipt or begin a duplicate upload.
pub(super) fn begin(
    conn: &Connection,
    scheduled_id: Option<&uuid::Uuid>,
    count: usize,
) -> Result<Option<Attempt>> {
    let start = Instant::now();
    let tx = transaction(conn)?;
    let id = scheduled_id
        .copied()
        .unwrap_or_else(uuid::Uuid::new_v4)
        .to_string();
    let changed = if scheduled_id.is_some() {
        tx.execute("UPDATE journal_upload SET started_at_ms=?2,outcome='running',phase='journal',batch_count=?3
            WHERE id=1 AND attempt_id=?1 AND outcome='scheduled'", params![id, utc_ms(), count as i64])?
    } else {
        tx.execute("INSERT INTO journal_upload(id,attempt_id,started_at_ms,outcome,phase,batch_count)
            VALUES(1,?1,?2,'running','journal',?3) ON CONFLICT(id) DO UPDATE SET
            attempt_id=excluded.attempt_id,scheduled_at_ms=NULL,started_at_ms=excluded.started_at_ms,
            finished_at_ms=NULL,elapsed_ms=NULL,outcome='running',phase='journal',error_kind=NULL,
            http_status=NULL,correlation_id=NULL,batch_count=excluded.batch_count,os_error_code=NULL", params![id, utc_ms(), count as i64])?
    };
    tx.commit()?;
    Ok((changed != 0).then_some(Attempt { id, start }))
}

impl Attempt {
    /// Persist the last observed dependency boundary before entering it.
    pub(super) fn phase(
        &self,
        conn: &Connection,
        phase: &'static str,
        status: Option<u16>,
        correlation: Option<&str>,
    ) -> Result<()> {
        conn.execute(
            "UPDATE journal_upload SET phase=?2,http_status=?3,correlation_id=?4
            WHERE id=1 AND attempt_id=?1 AND outcome='running'",
            params![self.id, phase, status, correlation],
        )?;
        Ok(())
    }

    /// Store the selected batch before credentials are consulted.
    pub(super) fn batch_count(&self, conn: &Connection, count: usize) -> Result<()> {
        conn.execute(
            "UPDATE journal_upload SET batch_count=?2 WHERE id=1 AND attempt_id=?1",
            params![self.id, count as i64],
        )?;
        Ok(())
    }

    /// Freeze clocks before final persistence; atomically mark API acceptance and account loss.
    /// Stale completions may update their selected rows/counters, never the newer last receipt.
    pub(super) fn finish(
        self,
        conn: &Connection,
        ids: &[i64],
        outcome: Outcome,
        phase: &'static str,
        kind: Option<&'static str>,
        status: Option<u16>,
        correlation: Option<&str>,
    ) -> Result<()> {
        let elapsed = self.start.elapsed().as_millis().min(i64::MAX as u128) as i64;
        let finished = utc_ms();
        let tx = transaction(conn)?;
        if outcome == Outcome::Accepted {
            for id in ids {
                tx.execute("UPDATE events SET uploaded=1 WHERE id=?1", [id])?;
            }
        }
        tx.execute(
            "UPDATE journal_health SET
            upload_failed=upload_failed+MIN(?1,9223372036854775807-upload_failed),
            upload_unknown=upload_unknown+MIN(?2,9223372036854775807-upload_unknown) WHERE id=1",
            params![
                (outcome == Outcome::Failed) as i64,
                (outcome == Outcome::Unknown) as i64
            ],
        )?;
        tx.execute(
            "UPDATE journal_upload SET finished_at_ms=?2,elapsed_ms=?3,outcome=?4,
            phase=?5,error_kind=?6,http_status=?7,correlation_id=?8 WHERE id=1 AND attempt_id=?1",
            params![
                self.id,
                finished,
                elapsed,
                outcome.label(),
                phase,
                kind,
                status,
                correlation
            ],
        )?;
        prune(&tx)?;
        tx.commit()?;
        Ok(())
    }
}

/// A spawn failure is definite before network delivery, even though child stderr is discarded.
pub(super) fn spawn_failed(
    conn: &Connection,
    id: &str,
    kind: &'static str,
    os_code: Option<i32>,
) -> Result<()> {
    let tx = transaction(conn)?;
    tx.execute(
        "UPDATE journal_health SET upload_failed=upload_failed+
        MIN(1,9223372036854775807-upload_failed) WHERE id=1",
        [],
    )?;
    tx.execute(
        "UPDATE journal_upload SET finished_at_ms=?2,outcome='failed',error_kind=?3,os_error_code=?4
        WHERE id=1 AND attempt_id=?1 AND outcome='scheduled'",
        params![id, utc_ms(), kind, os_code],
    )?;
    tx.commit()?;
    Ok(())
}

/// Safe last-attempt coordinates for one concise stderr notice.
#[derive(Serialize)]
struct Receipt {
    /// Public generated operational ID, independent of mail/user identity.
    attempt_id: String,
    /// UTC scheduling coordinate, absent for manual flushes.
    scheduled_at_ms: Option<i64>,
    /// UTC credential/network attempt start, absent when child did not start.
    started_at_ms: Option<i64>,
    /// Actual persisted completion time; absent means unresolved.
    finished_at_ms: Option<i64>,
    /// Exact monotonic upload-attempt elapsed time, not pure HTTP latency.
    elapsed_ms: Option<i64>,
    /// Accepted is API acknowledgement only, not remote retained delivery.
    outcome: Outcome,
    /// Reviewed dependency boundary, never arbitrary diagnostic text.
    phase: &'static str,
    /// Reviewed library/acknowledgement cause, never error messages.
    error_kind: Option<&'static str>,
    /// Exact received headers, absent before any headers arrived.
    http_status: Option<u16>,
    /// Canonical API request UUID, never arbitrary response headers.
    correlation_id: Option<String>,
    /// Number of selected safe events, not mail content size.
    batch_count: i64,
    /// Numeric platform spawn failure, without executable path or error text.
    os_error_code: Option<i32>,
}

/// Allow only labels emitted by this module's reviewed upload boundaries.
fn phase_label(value: &str) -> &'static str {
    match value {
        "spawn" => "spawn",
        "journal" => "journal",
        "auth" => "auth",
        "transport" => "transport",
        "response_headers" => "response_headers",
        "response_body" => "response_body",
        "acknowledgement" => "acknowledgement",
        "complete" => "complete",
        _ => "unknown",
    }
}

/// Safe finite diagnostic causes; malformed local metadata cannot pollute terminal output.
fn error_label(value: &str) -> &'static str {
    match value {
        "credential_unavailable" => "credential_unavailable",
        "timeout" => "timeout",
        "connect" => "connect",
        "body" => "body",
        "decode" => "decode",
        "request" => "request",
        "ack_invalid" => "ack_invalid",
        "ack_oversize" => "ack_oversize",
        "journal_read" => "journal_read",
        "spawn_io" => "spawn_io",
        "spawn_executable" => "spawn_executable",
        _ => "other",
    }
}

/// Canonical response/attempt IDs remain useful; arbitrary strings are never copied to stderr.
fn canonical_id(value: String) -> Option<String> {
    uuid::Uuid::parse_str(&value)
        .ok()
        .filter(|id| id.to_string() == value)
        .map(|_| value)
}

/// Claim one newly changed diagnostic notice; never enqueue another telemetry event.
/// This is best effort stderr reporting, not a guarantee that the terminal consumed it.
pub(super) fn report(conn: &Connection) -> Result<()> {
    let tx = transaction(conn)?;
    let receipt = tx
        .query_row(
            "SELECT attempt_id,scheduled_at_ms,started_at_ms,finished_at_ms,
        elapsed_ms,outcome,phase,error_kind,http_status,correlation_id,batch_count,os_error_code
        FROM journal_upload WHERE id=1",
            [],
            |row| {
                let outcome: String = row.get(5)?;
                let phase: String = row.get(6)?;
                let kind: Option<String> = row.get(7)?;
                let correlation: Option<String> = row.get(9)?;
                Ok(Receipt {
                    attempt_id: canonical_id(row.get(0)?).unwrap_or_else(|| "invalid_id".into()),
                    scheduled_at_ms: row.get(1)?,
                    started_at_ms: row.get(2)?,
                    finished_at_ms: row.get(3)?,
                    elapsed_ms: row.get(4)?,
                    outcome: Outcome::parse(&outcome)?,
                    phase: phase_label(&phase),
                    error_kind: kind.as_deref().map(error_label),
                    http_status: row.get(8)?,
                    correlation_id: correlation.and_then(canonical_id),
                    batch_count: row.get(10)?,
                    os_error_code: row.get(11)?,
                })
            },
        )
        .optional()?;
    let (evicted, history, failed, unknown, reported_evicted, reported_failed, reported_unknown, reported_receipt):
        (i64,i64,i64,i64,i64,i64,i64,Option<String>) = tx.query_row(
        "SELECT pending_evicted,history_pruned,upload_failed,upload_unknown,
        reported_evicted,reported_failed,reported_unknown,reported_receipt FROM journal_health WHERE id=1",
        [], |r| Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?,r.get(4)?,r.get(5)?,r.get(6)?,r.get(7)?)))?;
    let key = receipt.as_ref().map(|r| {
        format!(
            "{}:{}:{}:{:?}",
            r.attempt_id,
            r.outcome.label(),
            r.phase,
            r.http_status
        )
    });
    let unresolved_or_failed = receipt
        .as_ref()
        .is_some_and(|r| !matches!(r.outcome, Outcome::Accepted | Outcome::Empty))
        && key != reported_receipt;
    let changed_loss =
        evicted != reported_evicted || failed != reported_failed || unknown != reported_unknown;
    if !unresolved_or_failed && !changed_loss {
        tx.commit()?;
        return Ok(());
    }
    let pending: i64 = tx.query_row("SELECT COUNT(*) FROM events WHERE uploaded=0", [], |r| {
        r.get(0)
    })?;
    tx.execute(
        "UPDATE journal_health SET reported_evicted=?1,reported_failed=?2,
        reported_unknown=?3,reported_receipt=?4 WHERE id=1",
        params![evicted, failed, unknown, key],
    )?;
    tx.commit()?;
    let summary = serde_json::json!({"upload": receipt,
        "pending_events":pending,"pending_evicted":evicted,"history_pruned":history,
        "upload_failed":failed,"upload_unknown":unknown});
    if crate::machine::enabled() {
        crate::machine::event("diagnostic_status", summary);
    } else {
        eprintln!("amail: telemetry diagnostic {summary}");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Fixtures share the historical physical file, never a real account credential store.
    fn fixture() -> (tempfile::TempDir, crate::config::Runtime, Connection) {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.temp");
        std::fs::create_dir_all(&root).unwrap();
        let home = tempfile::tempdir_in(root).unwrap();
        let cfg = super::super::tests::config(home.path());
        let conn = super::super::db(&cfg).unwrap();
        (home, cfg, conn)
    }

    /// Model an older CLI's oversized backlog without invoking current insertion pruning.
    fn seed(conn: &Connection, count: i64, uploaded: i64) {
        let tx = transaction(conn).unwrap();
        for _ in 0..count {
            tx.execute(
                "INSERT INTO events(operation,status,duration_ms,bytes_bucket,trace_id,uploaded)
                VALUES('messages.list',200,7,0,'0123456789abcdef0123456789abcdef',?1)",
                [uploaded],
            )
            .unwrap();
        }
        tx.commit().unwrap();
    }

    /// Pending loss and accepted-history pruning have distinct counters and ownership.
    #[test]
    fn retention_has_exact_bounds_and_preserves_send_refresh_and_encrypted_sessions() {
        let (_home, cfg, conn) = fixture();
        conn.execute_batch("CREATE TABLE send_attempts(payload_hash TEXT PRIMARY KEY,
            attempt_key TEXT NOT NULL,accepted INTEGER NOT NULL DEFAULT 0);
            INSERT INTO send_attempts VALUES('hash','legacy-key',0);
            CREATE TABLE refresh_state(session_key TEXT PRIMARY KEY,in_progress INTEGER NOT NULL);
            INSERT INTO refresh_state VALUES('synthetic',1);
            CREATE TABLE sessions(session_key TEXT PRIMARY KEY,nonce BLOB NOT NULL,ciphertext BLOB NOT NULL);
            INSERT INTO sessions VALUES('synthetic',x'0123',x'4567');").unwrap();
        seed(&conn, PENDING_LIMIT + 5, 0);
        seed(&conn, HISTORY_LIMIT + 7, 1);
        let tx = transaction(&conn).unwrap();
        prune(&tx).unwrap();
        tx.commit().unwrap();
        let counts: (i64, i64) = conn.query_row("SELECT
            (SELECT COUNT(*) FROM events WHERE uploaded=0),(SELECT COUNT(*) FROM events WHERE uploaded=1)",
            [], |r| Ok((r.get(0)?,r.get(1)?))).unwrap();
        assert_eq!(counts, (PENDING_LIMIT, HISTORY_LIMIT));
        let health: (i64, i64, i64) = conn
            .query_row(
                "SELECT pending_evicted,history_pruned,last_pruned_at_ms FROM journal_health",
                [],
                |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
            )
            .unwrap();
        assert_eq!((health.0, health.1), (5, 7));
        assert!(health.2 > 0);
        assert_eq!(
            crate::send_state::send_key(&cfg, "hash", "replacement").unwrap(),
            "legacy-key"
        );
        assert_eq!(
            conn.query_row("SELECT in_progress FROM refresh_state", [], |r| r
                .get::<_, i64>(0))
                .unwrap(),
            1
        );
        let encrypted: (Vec<u8>, Vec<u8>) = conn
            .query_row("SELECT nonce,ciphertext FROM sessions", [], |r| {
                Ok((r.get(0)?, r.get(1)?))
            })
            .unwrap();
        assert_eq!(encrypted, (vec![1, 35], vec![69, 103]));
        super::super::init(&cfg).unwrap();
        assert_eq!(
            conn.query_row("SELECT pending_evicted FROM journal_health", [], |r| r
                .get::<_, i64>(0))
                .unwrap(),
            5
        );
    }

    /// Failed counter persistence rolls back pruning instead of losing unaccounted events.
    #[test]
    fn retention_rolls_back_and_counters_saturate_without_precision_loss() {
        let (_home, _cfg, conn) = fixture();
        seed(&conn, PENDING_LIMIT + 5, 0);
        conn.execute_batch(
            "CREATE TRIGGER refuse_counter BEFORE UPDATE ON journal_health
            BEGIN SELECT RAISE(ABORT,'synthetic'); END;",
        )
        .unwrap();
        {
            let tx = transaction(&conn).unwrap();
            assert!(prune(&tx).is_err());
        }
        assert_eq!(
            conn.query_row("SELECT COUNT(*) FROM events", [], |r| r.get::<_, i64>(0))
                .unwrap(),
            PENDING_LIMIT + 5
        );
        conn.execute_batch("DROP TRIGGER refuse_counter").unwrap();
        conn.execute(
            "UPDATE journal_health SET pending_evicted=?1",
            [i64::MAX - 2],
        )
        .unwrap();
        let tx = transaction(&conn).unwrap();
        prune(&tx).unwrap();
        tx.commit().unwrap();
        assert_eq!(
            conn.query_row("SELECT pending_evicted FROM journal_health", [], |r| r
                .get::<_, i64>(0))
                .unwrap(),
            i64::MAX
        );
    }

    /// A late old child/result can neither replace a newer receipt nor erase failure totals.
    #[test]
    fn scheduled_claim_and_completion_use_attempt_identity() {
        let (_home, _cfg, conn) = fixture();
        let old_id = uuid::Uuid::new_v4();
        scheduled(&conn, &old_id.to_string()).unwrap();
        let old = begin(&conn, Some(&old_id), 1).unwrap().unwrap();
        let new_id = uuid::Uuid::new_v4();
        scheduled(&conn, &new_id.to_string()).unwrap();
        assert!(begin(&conn, Some(&old_id), 1).unwrap().is_none());
        old.phase(&conn, "response_body", Some(202), None).unwrap();
        old.finish(
            &conn,
            &[],
            Outcome::Unknown,
            "response_body",
            Some("timeout"),
            Some(202),
            None,
        )
        .unwrap();
        let state: (String, String, String) = conn
            .query_row(
                "SELECT attempt_id,outcome,phase FROM journal_upload",
                [],
                |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
            )
            .unwrap();
        assert_eq!(
            state,
            (new_id.to_string(), "scheduled".into(), "spawn".into())
        );
        let new = begin(&conn, Some(&new_id), 0).unwrap().unwrap();
        new.finish(&conn, &[], Outcome::Empty, "complete", None, None, None)
            .unwrap();
        assert_eq!(
            conn.query_row("SELECT upload_unknown FROM journal_health", [], |r| r
                .get::<_, i64>(0))
                .unwrap(),
            1
        );
        assert!(
            begin(&conn, Some(&new_id), 0).unwrap().is_none(),
            "replayed child identity must not restart completed work"
        );
        spawn_failed(&conn, &old_id.to_string(), "spawn_io", Some(13)).unwrap();
        assert_eq!(
            conn.query_row("SELECT outcome FROM journal_upload", [], |r| r
                .get::<_, String>(0))
                .unwrap(),
            "empty"
        );
    }

    /// Concurrent insertion/pruning cannot race the bound or lose exact pending eviction counts.
    #[test]
    fn concurrent_writers_account_for_each_pruned_pending_row() {
        let (_home, cfg, conn) = fixture();
        seed(&conn, PENDING_LIMIT, 0);
        let workers: Vec<_> = (0..2)
            .map(|_| {
                let cfg = cfg.clone();
                std::thread::spawn(move || {
                    let conn = Connection::open(cfg.home.join("telemetry.sqlite3")).unwrap();
                    // Test coordination can wait; production diagnostic access still uses 250ms.
                    conn.busy_timeout(std::time::Duration::from_secs(5))
                        .unwrap();
                    for _ in 0..20 {
                        super::super::RequestSpan::new(&cfg, "messages.list")
                            .insert(&conn, 200, 0, None, super::super::Phase::Complete, None, 7)
                            .unwrap();
                    }
                })
            })
            .collect();
        for worker in workers {
            worker.join().unwrap();
        }
        assert_eq!(
            conn.query_row("SELECT COUNT(*) FROM events", [], |r| r.get::<_, i64>(0))
                .unwrap(),
            PENDING_LIMIT
        );
        assert_eq!(
            conn.query_row("SELECT pending_evicted FROM journal_health", [], |r| r
                .get::<_, i64>(0))
                .unwrap(),
            40
        );
    }
}
