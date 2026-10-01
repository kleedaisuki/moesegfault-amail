//! Local redacted operation journal / 本地脱敏操作日志。

use anyhow::Result;
use rand::RngCore;
use rusqlite::{params, Connection, TransactionBehavior};
use serde::Serialize;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use crate::{config::Runtime, local_store};
mod capability;
mod delivery;
mod upload;

/// Legacy upload shape: never append fields rejected by older deployed servers.
/// Mail content and personal identity are excluded, not operational identifiers.
#[derive(Debug, Serialize)]
struct Event {
    operation: String,
    status: u16,
    duration_ms: u64,
    bytes_bucket: u64,
    trace_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    span_id: Option<String>,
    correlation_id: Option<String>,
}

fn db(cfg: &Runtime) -> Result<Connection> {
    // A contended journal must not add the command-state store's 30-second wait.
    let mut conn = local_store::open(cfg, Duration::from_millis(250))?;
    conn.execute_batch(
        "CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY, operation TEXT NOT NULL, status INTEGER NOT NULL,
        duration_ms INTEGER NOT NULL, bytes_bucket INTEGER NOT NULL,
        trace_id TEXT NOT NULL, correlation_id TEXT, uploaded INTEGER NOT NULL DEFAULT 0,
        span_id TEXT, started_at_ms INTEGER, elapsed_ms INTEGER, phase TEXT, error_kind TEXT
    ); CREATE INDEX IF NOT EXISTS events_pending ON events(uploaded, id);
    CREATE TABLE IF NOT EXISTS journal_state (
        key TEXT PRIMARY KEY, value INTEGER NOT NULL
    );",
    )?;
    ensure_event_columns(&mut conn)?;
    delivery::schema(&conn)?;
    capability::schema(&conn)?;
    Ok(conn)
}

/// Serialize the legacy schema check and ALTER across concurrent CLI processes.
fn ensure_event_columns(conn: &mut Connection) -> Result<()> {
    let tx = conn.transaction_with_behavior(TransactionBehavior::Immediate)?;
    let names = tx
        .prepare("PRAGMA table_info(events)")?
        .query_map([], |row| row.get::<_, String>(1))?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    for (name, declaration) in [
        ("span_id", "ALTER TABLE events ADD COLUMN span_id TEXT"),
        (
            "started_at_ms",
            "ALTER TABLE events ADD COLUMN started_at_ms INTEGER",
        ),
        (
            "elapsed_ms",
            "ALTER TABLE events ADD COLUMN elapsed_ms INTEGER",
        ),
        ("phase", "ALTER TABLE events ADD COLUMN phase TEXT"),
        (
            "error_kind",
            "ALTER TABLE events ADD COLUMN error_kind TEXT",
        ),
    ] {
        if !names.iter().any(|column| column == name) {
            tx.execute(declaration, [])?;
        }
    }
    tx.commit()?;
    Ok(())
}

/// Prepare the diagnostic schema without taking ownership of auth/send tables.
pub fn init(cfg: &Runtime) -> Result<()> {
    if std::env::var("AMAIL_TELEMETRY").ok().as_deref() == Some("off") {
        return Ok(());
    }
    let conn = db(cfg)?;
    let tx = delivery::transaction(&conn)?;
    delivery::prune(&tx)?;
    tx.commit()?;
    delivery::report(&conn)
}

/// Failure boundaries contain static labels only, never error messages or URLs.
#[derive(Clone, Copy, Debug)]
pub enum Phase {
    /// Credential acquisition failed before an HTTP request was sent.
    Auth,
    /// No HTTP response headers were received.
    Transport,
    /// Headers arrived but reading the complete body failed.
    ResponseBody,
    /// The HTTP exchange completed (including HTTP error responses).
    Complete,
}

impl Phase {
    /// Stable local journal value; this is not part of the legacy upload schema.
    fn as_str(self) -> &'static str {
        match self {
            Self::Auth => "auth",
            Self::Transport => "transport",
            Self::ResponseBody => "response_body",
            Self::Complete => "complete",
        }
    }
}

/// One HTTP attempt's causal identity and clocks, created before credential work.
/// Call finish exactly once at the observed boundary. No user data is stored here.
pub struct RequestSpan<'a> {
    cfg: &'a Runtime,
    operation: &'a str,
    trace_id: String,
    span_id: String,
    started_at_ms: Option<i64>,
    start: Instant,
    /// Header metadata remains in memory until the actual attempt clock is frozen.
    observation: Option<capability::Observation>,
}

impl<'a> RequestSpan<'a> {
    /// Start a request attempt with random W3C identifiers and both clock types.
    pub fn new(cfg: &'a Runtime, operation: &'a str) -> Self {
        let mut random = [0u8; 24];
        rand::thread_rng().fill_bytes(&mut random);
        let hex = |bytes: &[u8]| bytes.iter().map(|b| format!("{b:02x}")).collect();
        Self {
            cfg,
            operation,
            trace_id: hex(&random[..16]),
            span_id: hex(&random[16..]),
            started_at_ms: SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .ok()
                .and_then(|value| i64::try_from(value.as_millis()).ok()),
            start: Instant::now(),
            observation: None,
        }
    }

    /// Propagate the same identity as the journaled HTTP attempt.
    pub fn traceparent(&self) -> String {
        format!("00-{}-{}-01", self.trace_id, self.span_id)
    }

    /// Observe complete HTTP headers without adding diagnostic SQLite latency to the exchange.
    pub(crate) fn observe_response(
        &mut self,
        headers: &reqwest::header::HeaderMap,
        response_url: &url::Url,
        status: u16,
    ) {
        self.observation = Some(capability::Observation::headers(
            self.cfg,
            headers,
            response_url,
            status,
        ));
    }

    /// Finish consumes the span to prevent two rows for one HTTP attempt.
    /// Status zero means no HTTP headers, not an invented provider error code.
    pub fn finish(
        self,
        status: u16,
        bytes: usize,
        correlation: Option<&str>,
        phase: Phase,
        error_kind: Option<&'static str>,
    ) {
        // Freeze at the observed attempt boundary, before SQLite opens or waits.
        let elapsed = self.start.elapsed().as_millis().min(i64::MAX as u128) as i64;
        if std::env::var("AMAIL_TELEMETRY").ok().as_deref() == Some("off") {
            return;
        }
        let result = (|| -> Result<()> {
            let conn = db(self.cfg)?;
            self.insert(
                &conn,
                status,
                bytes,
                correlation,
                phase,
                error_kind,
                elapsed,
            )?;
            if let Some(observation) = self.observation {
                if let Err(error) = observation.store(&conn, self.cfg) {
                    report_loss("capability_update", &error);
                }
            }
            maybe_spawn_flush(&conn)
        })();
        if let Err(error) = result {
            report_loss("record_or_schedule", &error);
        }
    }

    /// Retain exact elapsed time locally; the old wire field keeps its old bound.
    fn insert(
        &self,
        conn: &Connection,
        status: u16,
        bytes: usize,
        correlation: Option<&str>,
        phase: Phase,
        error_kind: Option<&str>,
        elapsed: i64,
    ) -> Result<()> {
        // Message/archive sizes remain bucketed because they describe user data.
        let bucket = if bytes == 0 {
            0
        } else {
            1u64 << (usize::BITS - (bytes - 1).leading_zeros()).min(30)
        };
        let tx = delivery::transaction(conn)?;
        tx.execute("INSERT INTO events(operation,status,duration_ms,bytes_bucket,trace_id,span_id,correlation_id,
            started_at_ms,elapsed_ms,phase,error_kind) VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11)",
            params![self.operation, status, elapsed.min(120_000), bucket, self.trace_id,
                self.span_id, correlation, self.started_at_ms, elapsed, phase.as_str(), error_kind])?;
        delivery::prune(&tx)?;
        tx.commit()?;
        Ok(())
    }
}

/// Report lost diagnostics on stderr without changing the command's result.
/// Library error text can contain private paths, so retain structured codes only.
pub fn report_loss(stage: &str, error: &anyhow::Error) {
    if let Some(rusqlite::Error::SqliteFailure(code, _)) = error.downcast_ref::<rusqlite::Error>() {
        eprintln!(
            "amail: telemetry unavailable stage={stage} sqlite_code={:?} extended_code={}",
            code.code, code.extended_code
        );
    } else if let Some(error) = error.downcast_ref::<std::io::Error>() {
        eprintln!(
            "amail: telemetry unavailable stage={stage} io_kind={:?}",
            error.kind()
        );
    } else {
        eprintln!("amail: telemetry unavailable stage={stage}");
    }
}

fn maybe_spawn_flush(conn: &Connection) -> Result<()> {
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)?
        .as_secs() as i64;
    let tx = delivery::transaction(conn)?;
    let updated = tx.execute(
        "INSERT INTO journal_state(key,value) VALUES('last_flush',?1)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value WHERE value < excluded.value-30",
        [now],
    )?;
    if updated == 0 {
        tx.commit()?;
        return Ok(());
    }
    let attempt_id = uuid::Uuid::new_v4().to_string();
    delivery::scheduled(&tx, &attempt_id)?;
    tx.commit()?;
    let exe = match std::env::current_exe() {
        Ok(exe) => exe,
        Err(error) => {
            delivery::spawn_failed(conn, &attempt_id, "spawn_executable", error.raw_os_error())?;
            return Err(error.into());
        }
    };
    let mut command = std::process::Command::new(exe);
    command
        .arg("_telemetry-flush")
        .arg("--attempt-id")
        .arg(&attempt_id)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000); // CREATE_NO_WINDOW / 不创建窗口
    }
    spawn_detached(conn, &attempt_id, &mut command)
}

/// Preserve an actual spawn failure despite null child stderr; never retain executable paths.
fn spawn_detached(
    conn: &Connection,
    attempt_id: &str,
    command: &mut std::process::Command,
) -> Result<()> {
    if let Err(error) = command.spawn() {
        delivery::spawn_failed(conn, attempt_id, "spawn_io", error.raw_os_error())?;
        return Err(error.into());
    }
    Ok(())
}

/// Upload a bounded pending batch in a separate short-lived process.
/// 在独立短生命周期进程中上传有界的待处理批次。
pub fn flush_pending(cfg: &Runtime, attempt_id: Option<&uuid::Uuid>) -> Result<()> {
    if std::env::var("AMAIL_TELEMETRY").ok().as_deref() == Some("off") {
        return Ok(());
    }
    upload::run(cfg, attempt_id)
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;

    /// The real spawn error path stores a safe OS code and does not fabricate child duration.
    #[test]
    fn failed_detached_spawn_has_durable_status_without_executable_path() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.temp");
        std::fs::create_dir_all(&root).unwrap();
        let home = tempfile::tempdir_in(root).unwrap();
        let cfg = config(home.path());
        let conn = db(&cfg).unwrap();
        let id = uuid::Uuid::new_v4().to_string();
        delivery::scheduled(&conn, &id).unwrap();
        let mut command =
            std::process::Command::new(home.path().join("SYNTHETIC_PRIVATE_EXECUTABLE"));
        assert!(spawn_detached(&conn, &id, &mut command).is_err());
        let row: (String, String, Option<i32>, Option<i64>, Option<i64>) = conn.query_row(
            "SELECT outcome,error_kind,os_error_code,started_at_ms,elapsed_ms FROM journal_upload", [],
            |r| Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?,r.get(4)?))).unwrap();
        assert_eq!((row.0.as_str(), row.1.as_str()), ("failed", "spawn_io"));
        assert!(row.2.is_some());
        assert_eq!((row.3, row.4), (None, None));
        let image = std::fs::read(cfg.home.join("telemetry.sqlite3")).unwrap();
        assert!(!image
            .windows(b"SYNTHETIC_PRIVATE_EXECUTABLE".len())
            .any(|bytes| bytes == b"SYNTHETIC_PRIVATE_EXECUTABLE"));
    }

    /// Synthetic configuration never opens the real user credential store.
    pub(crate) fn config(home: &std::path::Path) -> Runtime {
        Runtime {
            home: home.to_owned(),
            api_base: "https://mail.example.test".into(),
            issuer: "https://identity.example.test".into(),
            client_id: "synthetic".into(),
            redirect_uri: "http://127.0.0.1/callback".into(),
        }
    }

    /// Existing rows must survive the additive span-ID migration unchanged.
    #[test]
    fn upgrades_legacy_journal_without_losing_rows() {
        let mut conn = Connection::open_in_memory().unwrap();
        conn.execute_batch(
            "CREATE TABLE events (id INTEGER PRIMARY KEY, trace_id TEXT NOT NULL);
             INSERT INTO events(trace_id) VALUES('0123456789abcdef0123456789abcdef');",
        )
        .unwrap();
        ensure_event_columns(&mut conn).unwrap();
        ensure_event_columns(&mut conn).unwrap();
        let row: (String, Option<String>, Option<i64>, Option<i64>) = conn
            .query_row(
                "SELECT trace_id,span_id,started_at_ms,elapsed_ms FROM events",
                [],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
            )
            .unwrap();
        assert_eq!(row.0, "0123456789abcdef0123456789abcdef");
        assert_eq!(row.1, None);
        assert_eq!(row.2, None);
        assert_eq!(row.3, None);
    }

    /// Two old-CLI processes must not race into a duplicate-column startup failure.
    #[test]
    fn concurrent_legacy_upgrade_is_idempotent() {
        use std::sync::{Arc, Barrier};

        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.temp");
        std::fs::create_dir_all(&root).unwrap();
        let temp = tempfile::tempdir_in(root).unwrap();
        let path = temp.path().join("telemetry.sqlite3");
        Connection::open(&path)
            .unwrap()
            .execute_batch("CREATE TABLE events (id INTEGER PRIMARY KEY, trace_id TEXT NOT NULL)")
            .unwrap();

        let barrier = Arc::new(Barrier::new(3));
        let workers: Vec<_> = (0..2)
            .map(|_| {
                let path = path.clone();
                let barrier = barrier.clone();
                std::thread::spawn(move || {
                    let mut conn = Connection::open(path).unwrap();
                    conn.busy_timeout(Duration::from_secs(5)).unwrap();
                    barrier.wait();
                    ensure_event_columns(&mut conn).unwrap();
                })
            })
            .collect();
        barrier.wait();
        for worker in workers {
            worker.join().unwrap();
        }
        let conn = Connection::open(path).unwrap();
        let names: Vec<String> = conn
            .prepare("PRAGMA table_info(events)")
            .unwrap()
            .query_map([], |row| row.get(1))
            .unwrap()
            .collect::<std::result::Result<_, _>>()
            .unwrap();
        for column in [
            "span_id",
            "started_at_ms",
            "elapsed_ms",
            "phase",
            "error_kind",
        ] {
            assert_eq!(names.iter().filter(|name| *name == column).count(), 1);
        }
    }

    /// Exact local clocks and observed failure phase do not change legacy wire fields.
    #[test]
    fn records_exact_time_and_phase_with_matching_trace_identity() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.temp");
        std::fs::create_dir_all(&root).unwrap();
        let temp = tempfile::tempdir_in(root).unwrap();
        let cfg = config(temp.path());
        let conn = db(&cfg).unwrap();
        let mut span = RequestSpan::new(&cfg, "messages.list");
        span.start -= Duration::from_secs(121);
        let parent = span.traceparent();
        let elapsed = span.start.elapsed().as_millis() as i64;
        span.insert(
            &conn,
            200,
            0,
            None,
            Phase::ResponseBody,
            Some("decode"),
            elapsed,
        )
        .unwrap();
        let row: (i64, i64, i64, String, String, String, String) = conn.query_row(
            "SELECT started_at_ms,elapsed_ms,duration_ms,phase,error_kind,trace_id,span_id FROM events",
            [], |row| Ok((row.get(0)?,row.get(1)?,row.get(2)?,row.get(3)?,row.get(4)?,row.get(5)?,row.get(6)?))
        ).unwrap();
        assert!(row.0 > 0);
        assert!(row.1 >= 121_000);
        assert_eq!(row.2, 120_000);
        assert_eq!(row.3, "response_body");
        assert_eq!(row.4, "decode");
        assert_eq!(parent, format!("00-{}-{}-01", row.5, row.6));
    }

    /// Persistence latency cannot inflate the elapsed time captured at completion.
    #[test]
    fn journal_uses_frozen_attempt_duration_not_persistence_time() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.temp");
        std::fs::create_dir_all(&root).unwrap();
        let temp = tempfile::tempdir_in(root).unwrap();
        let cfg = config(temp.path());
        let conn = db(&cfg).unwrap();
        let mut span = RequestSpan::new(&cfg, "messages.list");
        // Model time spent opening/waiting for diagnostics after a 7ms exchange.
        // No scheduler sleep or timing tolerance is required for this invariant.
        span.start -= Duration::from_secs(20);
        span.insert(&conn, 200, 0, None, Phase::Complete, None, 7)
            .unwrap();
        let recorded: (i64, i64) = conn
            .query_row("SELECT elapsed_ms,duration_ms FROM events", [], |row| {
                Ok((row.get(0)?, row.get(1)?))
            })
            .unwrap();
        assert_eq!(recorded, (7, 7));
    }

    /// Older upload rows omit span_id instead of inventing a parent.
    #[test]
    fn legacy_upload_shape_is_unchanged() {
        let event = Event {
            operation: "messages.list".into(),
            status: 200,
            duration_ms: 1,
            bytes_bucket: 0,
            trace_id: "0123456789abcdef0123456789abcdef".into(),
            span_id: None,
            correlation_id: None,
        };
        let encoded = serde_json::to_value(event).unwrap();
        assert!(encoded.get("span_id").is_none());
        let current = Event {
            operation: "messages.list".into(),
            status: 200,
            duration_ms: 1,
            bytes_bucket: 0,
            trace_id: "0123456789abcdef0123456789abcdef".into(),
            span_id: Some("0123456789abcdef".into()),
            correlation_id: None,
        };
        assert_eq!(
            serde_json::to_value(current).unwrap()["span_id"],
            "0123456789abcdef"
        );
    }
}
