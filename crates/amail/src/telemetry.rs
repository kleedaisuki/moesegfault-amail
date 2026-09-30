//! Local redacted operation journal / 本地脱敏操作日志。

use anyhow::Result;
use reqwest::blocking::Client;
use rusqlite::{params, Connection, TransactionBehavior};
use serde::Serialize;
use std::time::Duration;

use crate::config::Runtime;

/// Only operational dimensions are retained; mail content and identifiers are forbidden.
/// 仅保留运行维度；禁止邮件内容和个人标识。
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
    let path = cfg.home.join("telemetry.sqlite3");
    let mut conn = Connection::open(&path)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600))?;
    }
    conn.busy_timeout(Duration::from_secs(30))?;
    conn.execute_batch("CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY, operation TEXT NOT NULL, status INTEGER NOT NULL,
        duration_ms INTEGER NOT NULL, bytes_bucket INTEGER NOT NULL,
        trace_id TEXT NOT NULL, correlation_id TEXT, uploaded INTEGER NOT NULL DEFAULT 0,
        span_id TEXT
    ); CREATE INDEX IF NOT EXISTS events_pending ON events(uploaded, id);
    CREATE TABLE IF NOT EXISTS send_attempts (
        payload_hash TEXT PRIMARY KEY, attempt_key TEXT NOT NULL, accepted INTEGER NOT NULL DEFAULT 0
    ); CREATE TABLE IF NOT EXISTS journal_state (
        key TEXT PRIMARY KEY, value INTEGER NOT NULL
    );")?;
    ensure_span_column(&mut conn)?;
    Ok(conn)
}

/// Serialize the legacy schema check and ALTER across concurrent CLI processes.
fn ensure_span_column(conn: &mut Connection) -> Result<()> {
    let tx = conn.transaction_with_behavior(TransactionBehavior::Immediate)?;
    let has_span_id = tx
        .prepare("PRAGMA table_info(events)")?
        .query_map([], |row| row.get::<_, String>(1))?
        .collect::<std::result::Result<Vec<_>, _>>()?
        .iter()
        .any(|name| name == "span_id");
    if !has_span_id {
        tx.execute("ALTER TABLE events ADD COLUMN span_id TEXT", [])?;
    }
    tx.commit()?;
    Ok(())
}

/// Prepare local tables before the first OAuth refresh lock.
/// 在首次 OAuth 刷新锁之前准备本地表。
pub fn init(cfg: &Runtime) -> Result<()> {
    db(cfg).map(|_| ())
}

/// Record safe timing/status dimensions, then start a detached bounded uploader.
/// 记录安全的耗时和状态维度，再启动分离式有界上传器。
pub fn record(
    cfg: &Runtime,
    operation: &str,
    status: u16,
    duration_ms: u64,
    bytes: usize,
    trace_id: &str,
    span_id: &str,
    correlation_id: Option<&str>,
) {
    if std::env::var("AMAIL_TELEMETRY").ok().as_deref() == Some("off") {
        return;
    }
    let Ok(conn) = db(cfg) else {
        return;
    };
    // Powers of two hide exact message/archive sizes while preserving useful scale.
    // 2 的幂次桶隐藏精确邮件大小，同时保留调试需要的量级。
    let bucket = if bytes == 0 {
        0
    } else {
        1u64 << (usize::BITS - (bytes - 1).leading_zeros()).min(30)
    };
    let _ = conn.execute("INSERT INTO events(operation,status,duration_ms,bytes_bucket,trace_id,span_id,correlation_id) VALUES(?1,?2,?3,?4,?5,?6,?7)",
        params![operation, status, duration_ms.min(120_000), bucket, trace_id, span_id, correlation_id]);
    let _ = maybe_spawn_flush(&conn);
}

fn maybe_spawn_flush(conn: &Connection) -> Result<()> {
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)?
        .as_secs() as i64;
    let updated = conn.execute(
        "INSERT INTO journal_state(key,value) VALUES('last_flush',?1)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value WHERE value < excluded.value-30",
        [now],
    )?;
    if updated == 0 {
        return Ok(());
    }
    let exe = std::env::current_exe()?;
    let mut command = std::process::Command::new(exe);
    command
        .arg("_telemetry-flush")
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000); // CREATE_NO_WINDOW / 不创建窗口
    }
    command.spawn()?;
    Ok(())
}

/// Upload a bounded pending batch in a separate short-lived process.
/// 在独立短生命周期进程中上传有界的待处理批次。
pub fn flush_pending(cfg: &Runtime) -> Result<()> {
    if std::env::var("AMAIL_TELEMETRY").ok().as_deref() == Some("off") {
        return Ok(());
    }
    let conn = db(cfg)?;
    let token = crate::auth::access_token(cfg)?;
    flush(cfg, &token, &conn)
}

fn flush(cfg: &Runtime, token: &str, conn: &Connection) -> Result<()> {
    let mut stmt = conn.prepare("SELECT id,operation,status,duration_ms,bytes_bucket,trace_id,span_id,correlation_id FROM events WHERE uploaded=0 ORDER BY id LIMIT 20")?;
    let rows = stmt.query_map([], |row| {
        Ok((
            row.get::<_, i64>(0)?,
            Event {
                operation: row.get(1)?,
                status: row.get(2)?,
                duration_ms: row.get(3)?,
                bytes_bucket: row.get(4)?,
                trace_id: row.get(5)?,
                span_id: row.get(6)?,
                correlation_id: row.get(7)?,
            },
        ))
    })?;
    let items: Vec<_> = rows.collect::<std::result::Result<_, _>>()?;
    if items.is_empty() {
        return Ok(());
    }
    let ids: Vec<i64> = items.iter().map(|(id, _)| *id).collect();
    let events: Vec<_> = items.into_iter().map(|(_, event)| event).collect();
    let http = Client::builder().timeout(Duration::from_secs(5)).build()?;
    let response = http
        .post(format!("{}/v1/telemetry", cfg.api_base))
        .bearer_auth(token)
        .json(&serde_json::json!({"events": events}))
        .send()?;
    if response.status().is_success() {
        for id in ids {
            conn.execute("UPDATE events SET uploaded=1 WHERE id=?1", [id])?;
        }
        conn.execute("DELETE FROM events WHERE uploaded=1 AND id < (SELECT COALESCE(MAX(id),0)-200 FROM events)", [])?;
    }
    Ok(())
}

/// Reuse one idempotency key for an unresolved identical payload.
/// 对相同但尚未确定结果的载荷复用同一个幂等键。
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

/// Release the key only after a definitive accepted response.
/// 仅在明确获得接受响应后释放幂等键。
pub fn accepted(cfg: &Runtime, hash: &str) -> Result<()> {
    db(cfg)?.execute("DELETE FROM send_attempts WHERE payload_hash=?1", [hash])?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Existing rows must survive the additive span-ID migration unchanged.
    #[test]
    fn upgrades_legacy_journal_without_losing_rows() {
        let mut conn = Connection::open_in_memory().unwrap();
        conn.execute_batch(
            "CREATE TABLE events (id INTEGER PRIMARY KEY, trace_id TEXT NOT NULL);
             INSERT INTO events(trace_id) VALUES('0123456789abcdef0123456789abcdef');",
        )
        .unwrap();
        ensure_span_column(&mut conn).unwrap();
        ensure_span_column(&mut conn).unwrap();
        let row: (String, Option<String>) = conn
            .query_row("SELECT trace_id,span_id FROM events", [], |row| {
                Ok((row.get(0)?, row.get(1)?))
            })
            .unwrap();
        assert_eq!(row.0, "0123456789abcdef0123456789abcdef");
        assert_eq!(row.1, None);
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
                    ensure_span_column(&mut conn).unwrap();
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
        assert_eq!(names.iter().filter(|name| *name == "span_id").count(), 1);
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
