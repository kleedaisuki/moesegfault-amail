//! Bounded local-only command diagnostics, separate from uploadable API events.
//!
//! Values are closed operational labels and measurements, never caller text.
//! No credential, send-state or uploader table is read, changed or exported here.

use crate::{config::Runtime, local_store};
use anyhow::Result;
use rusqlite::{params, Connection, TransactionBehavior};
use std::{
    cell::{Cell, RefCell},
    collections::VecDeque,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

/// Canonical public commands; aliases deliberately share the same identity.
#[derive(Clone, Copy)]
pub enum CommandKind {
    /// Non-secret configuration display.
    Config,
    /// Local ZIP creation.
    Pack,
    /// Local ZIP extraction.
    Unpack,
    /// Browser authorization and persistence.
    AuthLogin,
    /// Local session inspection.
    AuthStatus,
    /// Best-effort revocation and local credential removal.
    AuthLogout,
    /// Address listing.
    AddressList,
    /// Address registration.
    AddressAdd,
    /// Address retirement.
    AddressDelete,
    /// Summary sync and optional local export.
    Sync,
    /// Search including optional polling.
    Search,
    /// Message metadata retrieval.
    Get,
    /// Archive retrieval and local write/extraction.
    Read,
    /// Explicit read-state mutation.
    Mark,
    /// Message deletion.
    Delete,
    /// ZIP validation and send.
    Send,
}

impl CommandKind {
    /// Return an argument-independent operational name.
    fn label(self) -> &'static str {
        match self {
            Self::Config => "config",
            Self::Pack => "pack",
            Self::Unpack => "unpack",
            Self::AuthLogin => "auth_login",
            Self::AuthStatus => "auth_status",
            Self::AuthLogout => "auth_logout",
            Self::AddressList => "address_list",
            Self::AddressAdd => "address_add",
            Self::AddressDelete => "address_delete",
            Self::Sync => "sync",
            Self::Search => "search",
            Self::Get => "get",
            Self::Read => "read",
            Self::Mark => "mark",
            Self::Delete => "delete",
            Self::Send => "send",
        }
    }
}

/// Dependency phases are defined at actual source boundaries, not guessed causes.
#[derive(Clone, Copy)]
pub enum Phase {
    /// Entire public command, including output and local filesystem work.
    Command,
    /// Credential acquisition, including serialized refresh if necessary.
    AccessToken,
    /// OIDC discovery HTTP exchange and decoding.
    Discovery,
    /// Authorization code HTTP exchange and decoding.
    TokenExchange,
    /// Refresh token HTTP exchange and decoding.
    TokenRefresh,
    /// Signing-key HTTP exchange and decoding.
    Jwks,
    /// Revocation HTTP headers; logout still clears credentials on failure.
    Revocation,
}

impl Phase {
    /// Return the fixed persisted source-boundary name.
    fn label(self) -> &'static str {
        match self {
            Self::Command => "command",
            Self::AccessToken => "access_token",
            Self::Discovery => "discovery",
            Self::TokenExchange => "token_exchange",
            Self::TokenRefresh => "token_refresh",
            Self::Jwks => "jwks",
            Self::Revocation => "revocation",
        }
    }
}

thread_local! {
    /// Only an ordinary command scope enables dependency collection on its thread.
    static CURRENT: Cell<Option<(CommandKind, uuid::Uuid)>> = const { Cell::new(None) };
    /// Bound memory as well as stored records during long-running poll/sync commands.
    static PENDING: RefCell<Pending> = RefCell::new(Pending::default());
}

/// Restore scope even if a caller unwinds; detached flush has no ordinary scope.
struct Scope {
    /// Previous ordinary command context, if scopes are nested.
    command: Option<(CommandKind, uuid::Uuid)>,
    /// Previous pending buffer, restored independently on unwind.
    pending: Pending,
}

/// Recent in-memory completions; older records count as evictions, not success.
#[derive(Default)]
struct Pending {
    /// At most 200 recent completed boundaries.
    records: VecDeque<Record>,
    /// Records evicted before persistence during this command.
    pruned: i64,
}
impl Drop for Scope {
    fn drop(&mut self) {
        CURRENT.with(|current| current.set(self.command));
        PENDING.with(|pending| *pending.borrow_mut() = std::mem::take(&mut self.pending));
    }
}

/// Execute without changing result or stdout; hidden workers never enter a scope.
///
/// Dependency calls use the active canonical command automatically. Persistence
/// happens after the operation's end clock is frozen, outside network work.
pub fn run<T>(
    cfg: &Runtime,
    command: Option<CommandKind>,
    work: impl FnOnce() -> Result<T>,
) -> Result<T> {
    run_with_context(cfg, command, |_| work())
}

/// Pass a generated local command identity explicitly to HTTP request diagnostics.
/// The UUID is not exported and is absent for opt-out or detached upload commands.
pub fn run_with_context<T>(
    cfg: &Runtime,
    command: Option<CommandKind>,
    work: impl FnOnce(Option<uuid::Uuid>) -> Result<T>,
) -> Result<T> {
    let command = command
        .filter(|_| enabled())
        .map(|kind| (kind, uuid::Uuid::new_v4()));
    let _scope = Scope {
        command: CURRENT.with(|current| current.replace(command)),
        pending: PENDING.with(|pending| std::mem::take(&mut *pending.borrow_mut())),
    };
    let span = Span::start(Phase::Command);
    let result = work(command.map(|(_, id)| id));
    span.finish(cfg, result.is_ok(), None, None);
    let pending = PENDING.with(|pending| std::mem::take(&mut *pending.borrow_mut()));
    if !pending.records.is_empty() && persist_batch(cfg, &pending).is_err() {
        // Never format arbitrary SQL, filesystem, HTTP or exception text.
        use std::io::Write;
        let _ = writeln!(
            std::io::stderr().lock(),
            "amail: local diagnostic records lost"
        );
    }
    result
}

/// True only for enabled local diagnostics; opt-out must not open the store.
fn enabled() -> bool {
    std::env::var("AMAIL_TELEMETRY").ok().as_deref() != Some("off")
}

/// An in-memory boundary; construction does no filesystem or credential work.
pub struct Span {
    /// Active ordinary command, absent for opt-out and detached upload.
    command: Option<(CommandKind, uuid::Uuid)>,
    /// Fixed source boundary.
    phase: Phase,
    /// UTC epoch milliseconds, not inferred from delivery time.
    started_at_ms: i64,
    /// Monotonic source duration clock.
    started: Instant,
}

impl Span {
    /// Capture source clocks before the dependency begins.
    pub fn start(phase: Phase) -> Self {
        Self {
            command: CURRENT.with(Cell::get),
            phase,
            started_at_ms: utc_ms(),
            started: Instant::now(),
        }
    }

    /// Record completion without allowing diagnostic failures to escape.
    pub fn finish(
        self,
        _cfg: &Runtime,
        success: bool,
        status: Option<u16>,
        code: Option<&'static str>,
    ) {
        let elapsed_ms = self.started.elapsed().as_millis().min(i64::MAX as u128) as i64;
        let ended_at_ms = utc_ms();
        let Some((command, command_id)) = self.command else {
            return;
        };
        if !enabled() {
            return;
        }
        let record = Record {
            command,
            command_id,
            phase: self.phase,
            started_at_ms: self.started_at_ms,
            ended_at_ms,
            elapsed_ms,
            success,
            status,
            code,
        };
        PENDING.with(|pending| {
            let mut pending = pending.borrow_mut();
            if pending.records.len() == 200 {
                pending.records.pop_front();
                pending.pruned = pending.pruned.saturating_add(1);
            }
            pending.records.push_back(record);
        });
    }
}

/// Measurements for one completed boundary, not an uploadable API event.
struct Record {
    /// Canonical public operation.
    command: CommandKind,
    /// Generated command correlation, never an existing user or mail identifier.
    command_id: uuid::Uuid,
    /// Source boundary within the operation.
    phase: Phase,
    /// Source UTC start.
    started_at_ms: i64,
    /// Source UTC end; wall-clock adjustment may put it before start.
    ended_at_ms: i64,
    /// Nonnegative monotonic elapsed milliseconds.
    elapsed_ms: i64,
    /// Whether this boundary returned success.
    success: bool,
    /// Actual received HTTP status, including successful headers on decode failure.
    status: Option<u16>,
    /// Closed dependency code; no exception message.
    code: Option<&'static str>,
}

/// Best-effort source UTC time, independent of monotonic duration.
fn utc_ms() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
        .min(i64::MAX as u128) as i64
}

/// Own only local diagnostic tables, without changing SQLite journal policy.
fn schema(conn: &Connection) -> Result<()> {
    conn.execute_batch("CREATE TABLE IF NOT EXISTS command_spans (
        id INTEGER PRIMARY KEY, command_id TEXT NOT NULL, command TEXT NOT NULL, phase TEXT NOT NULL,
        started_at_ms INTEGER NOT NULL, ended_at_ms INTEGER NOT NULL,
        elapsed_ms INTEGER NOT NULL CHECK(elapsed_ms >= 0),
        outcome TEXT NOT NULL CHECK(outcome IN ('success','failure')),
        http_status INTEGER, dependency_code TEXT
    ); CREATE TABLE IF NOT EXISTS command_journal_state (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1), discarded_count INTEGER NOT NULL
    ); INSERT OR IGNORE INTO command_journal_state VALUES(1,0);")?;
    Ok(())
}

/// Atomically insert, prune oldest completed records and account for eviction.
/// No write transaction is held while command, HTTP or credential work runs.
fn persist_batch(cfg: &Runtime, pending: &Pending) -> Result<()> {
    let mut conn = local_store::open(cfg, Duration::from_millis(250))?;
    schema(&conn)?;
    let tx = conn.transaction_with_behavior(TransactionBehavior::Immediate)?;
    for record in &pending.records {
        tx.execute("INSERT INTO command_spans(command_id,command,phase,started_at_ms,ended_at_ms,elapsed_ms,outcome,http_status,dependency_code)
        VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9)", params![record.command_id.to_string(), record.command.label(), record.phase.label(), record.started_at_ms,
        record.ended_at_ms, record.elapsed_ms, if record.success {"success"} else {"failure"}, record.status, record.code])?;
    }
    let pruned = tx.execute(
        "DELETE FROM command_spans WHERE id NOT IN
        (SELECT id FROM command_spans ORDER BY id DESC LIMIT 200)",
        [],
    )?;
    tx.execute("UPDATE command_journal_state SET discarded_count =
        CASE WHEN discarded_count > ?1 THEN 9223372036854775807 ELSE discarded_count + ?2 END WHERE singleton=1",
        params![i64::MAX - (pruned as i64).saturating_add(pending.pruned), (pruned as i64).saturating_add(pending.pruned)])?;
    tx.commit()?;
    Ok(())
}

/// Classify only reqwest's typed predicates, never its URL-bearing display text.
pub fn dependency_code(error: &reqwest::Error) -> &'static str {
    if error.is_timeout() {
        "timeout"
    } else if error.is_connect() {
        "connect"
    } else if error.is_status() {
        "http_status"
    } else if error.is_decode() {
        "decode"
    } else if error.is_body() {
        "body"
    } else if error.is_request() {
        "request"
    } else {
        "transport"
    }
}
#[cfg(test)]
mod tests {
    use super::*;

    /// Dedicated synthetic state under the repository, never a real CLI home.
    fn fixture() -> (tempfile::TempDir, Runtime) {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.temp");
        std::fs::create_dir_all(&root).unwrap();
        let home = tempfile::tempdir_in(root).unwrap();
        let cfg = Runtime {
            home: home.path().to_owned(),
            api_base: "https://mail.example.test".into(),
            issuer: "https://identity.example.test".into(),
            client_id: String::new(),
            redirect_uri: String::new(),
        };
        (home, cfg)
    }

    /// Explicit API context uses the same UUID as retained command completion.
    #[test]
    fn explicit_context_matches_completion_and_hidden_scope_is_absent() {
        let (_home, cfg) = fixture();
        let observed = run_with_context(&cfg, Some(CommandKind::Search), |id| Ok(id)).unwrap();
        let conn = local_store::open(&cfg, Duration::from_millis(250)).unwrap();
        let stored: String = conn
            .query_row(
                "SELECT command_id FROM command_spans WHERE phase='command'",
                [],
                |r| r.get(0),
            )
            .unwrap();
        assert_eq!(observed.unwrap().to_string(), stored);
        assert!(run_with_context(&cfg, None, |id| Ok(id)).unwrap().is_none());
    }

    /// Insertion, bounded retention and cumulative eviction do not touch command state.
    #[test]
    fn bounded_rows_preserve_other_owners_and_saturate_count() {
        let (_home, cfg) = fixture();
        let conn = local_store::open(&cfg, Duration::from_millis(250)).unwrap();
        schema(&conn).unwrap();
        conn.execute_batch("CREATE TABLE send_attempts (key TEXT); INSERT INTO send_attempts VALUES('synthetic-key');
            CREATE TABLE refresh_state (in_progress INTEGER); INSERT INTO refresh_state VALUES(1);
            CREATE TABLE events (operation TEXT); INSERT INTO events VALUES('synthetic-api-event');").unwrap();
        for _ in 0..205 {
            run(&cfg, Some(CommandKind::Config), || Ok(())).unwrap();
        }
        assert_eq!(
            conn.query_row("SELECT COUNT(*) FROM command_spans", [], |r| r
                .get::<_, i64>(0))
                .unwrap(),
            200
        );
        assert_eq!(
            conn.query_row(
                "SELECT discarded_count FROM command_journal_state",
                [],
                |r| { r.get::<_, i64>(0) }
            )
            .unwrap(),
            5
        );
        conn.execute(
            "UPDATE command_journal_state SET discarded_count=?1",
            [i64::MAX],
        )
        .unwrap();
        run(&cfg, Some(CommandKind::Config), || Ok(())).unwrap();
        assert_eq!(
            conn.query_row(
                "SELECT discarded_count FROM command_journal_state",
                [],
                |r| { r.get::<_, i64>(0) }
            )
            .unwrap(),
            i64::MAX
        );
        assert_eq!(
            conn.query_row("SELECT key FROM send_attempts", [], |r| r
                .get::<_, String>(0))
                .unwrap(),
            "synthetic-key"
        );
        assert_eq!(
            conn.query_row("SELECT in_progress FROM refresh_state", [], |r| r
                .get::<_, i64>(0))
                .unwrap(),
            1
        );
        assert_eq!(
            conn.query_row("SELECT COUNT(*) FROM events", [], |r| r.get::<_, i64>(0))
                .unwrap(),
            1
        );
    }

    /// A failed prune-counter write rolls back both insertion and deletion.
    #[test]
    fn failed_counter_update_rolls_back_the_whole_record() {
        let (_home, cfg) = fixture();
        for _ in 0..200 {
            run(&cfg, Some(CommandKind::Config), || Ok(())).unwrap();
        }
        let conn = local_store::open(&cfg, Duration::from_millis(250)).unwrap();
        conn.execute_batch(
            "CREATE TRIGGER reject_counter BEFORE UPDATE ON command_journal_state
            BEGIN SELECT RAISE(ABORT,'synthetic-private-error'); END;",
        )
        .unwrap();
        let record = Record {
            command: CommandKind::Pack,
            command_id: uuid::Uuid::new_v4(),
            phase: Phase::Command,
            started_at_ms: 7,
            ended_at_ms: 6,
            elapsed_ms: 2,
            success: false,
            status: None,
            code: None,
        };
        assert!(persist_batch(
            &cfg,
            &Pending {
                records: [record].into(),
                pruned: 0
            }
        )
        .is_err());
        assert_eq!(
            conn.query_row(
                "SELECT MIN(id),MAX(id),COUNT(*) FROM command_spans",
                [],
                |r| Ok((
                    r.get::<_, i64>(0)?,
                    r.get::<_, i64>(1)?,
                    r.get::<_, i64>(2)?
                ))
            )
            .unwrap(),
            (1, 200, 200)
        );
        assert_eq!(
            conn.query_row(
                "SELECT discarded_count FROM command_journal_state",
                [],
                |r| { r.get::<_, i64>(0) }
            )
            .unwrap(),
            0
        );
    }

    /// Dependency and command share generated correlation and private errors stay out.
    #[test]
    fn scopes_correlate_and_preserve_result_without_exception_text() {
        let (_home, cfg) = fixture();
        let result: Result<()> = run(&cfg, Some(CommandKind::Read), || {
            Span::start(Phase::AccessToken).finish(&cfg, false, None, None);
            anyhow::bail!("synthetic-private-exception-and-path");
        });
        assert_eq!(
            result.unwrap_err().to_string(),
            "synthetic-private-exception-and-path"
        );
        let conn = local_store::open(&cfg, Duration::from_millis(250)).unwrap();
        let mut stmt = conn.prepare("SELECT command_id,command,phase,outcome,elapsed_ms,started_at_ms FROM command_spans ORDER BY id").unwrap();
        let rows: Vec<_> = stmt
            .query_map([], |r| {
                Ok((
                    r.get::<_, String>(0)?,
                    r.get::<_, String>(1)?,
                    r.get::<_, String>(2)?,
                    r.get::<_, String>(3)?,
                    r.get::<_, i64>(4)?,
                    r.get::<_, i64>(5)?,
                ))
            })
            .unwrap()
            .map(|r| r.unwrap())
            .collect();
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].0, rows[1].0);
        assert!(uuid::Uuid::parse_str(&rows[0].0).is_ok());
        assert_eq!(
            (&rows[0].1, &rows[0].2, &rows[0].3),
            (&"read".into(), &"access_token".into(), &"failure".into())
        );
        assert_eq!(rows[1].2, "command");
        assert!(rows.iter().all(|r| r.4 >= 0 && r.5 > 0));
        assert!(!format!("{rows:?}").contains("synthetic-private"));
    }

    /// No active ordinary scope means auth inside the uploader creates no local table.
    #[test]
    fn hidden_scope_and_unwind_restore_suppression() {
        let (_home, cfg) = fixture();
        run(&cfg, None, || {
            Span::start(Phase::AccessToken).finish(&cfg, false, None, None);
            Ok(())
        })
        .unwrap();
        assert!(!cfg.home.join("telemetry.sqlite3").exists());
        let _ = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            let _: Result<()> = run(&cfg, Some(CommandKind::Pack), || panic!("synthetic unwind"));
        }));
        Span::start(Phase::AccessToken).finish(&cfg, false, None, None);
        assert!(!cfg.home.join("telemetry.sqlite3").exists());
    }

    /// All source clocks freeze before any new diagnostic database initialization.
    #[test]
    fn dependency_buffer_is_bounded_and_persistence_wait_is_outside_clocks() {
        let (_home, cfg) = fixture();
        run(&cfg, Some(CommandKind::Search), || {
            for _ in 0..205 {
                Span::start(Phase::AccessToken).finish(&cfg, true, None, None);
            }
            assert!(!cfg.home.join("telemetry.sqlite3").exists());
            PENDING.with(|pending| {
                assert_eq!(pending.borrow().records.len(), 200);
                assert_eq!(pending.borrow().pruned, 5);
            });
            Ok(())
        })
        .unwrap();
        let conn = local_store::open(&cfg, Duration::from_millis(250)).unwrap();
        assert_eq!(
            conn.query_row("SELECT COUNT(*) FROM command_spans", [], |r| r
                .get::<_, i64>(0))
                .unwrap(),
            200
        );
        assert_eq!(
            conn.query_row(
                "SELECT discarded_count FROM command_journal_state",
                [],
                |r| r.get::<_, i64>(0)
            )
            .unwrap(),
            6
        );
        assert_eq!(
            conn.query_row(
                "SELECT phase FROM command_spans ORDER BY id DESC LIMIT 1",
                [],
                |r| r.get::<_, String>(0)
            )
            .unwrap(),
            "command"
        );
    }

    /// Overlapping scopes get independent identities and buffers, not guaranteed lock admission.
    #[test]
    fn simultaneous_commands_do_not_cross_correlations() {
        let (_home, cfg) = fixture();
        let barrier = std::sync::Arc::new(std::sync::Barrier::new(5));
        let workers: Vec<_> = (0..4)
            .map(|_| {
                let cfg = cfg.clone();
                let barrier = barrier.clone();
                let (release, wait) = std::sync::mpsc::channel();
                let worker = std::thread::spawn(move || {
                    run(&cfg, Some(CommandKind::Config), || {
                        Span::start(Phase::AccessToken).finish(&cfg, true, None, None);
                        barrier.wait();
                        wait.recv().unwrap();
                        Ok(())
                    })
                    .unwrap()
                });
                (release, worker)
            })
            .collect();
        // All four scopes and pending dependency buffers are live together.
        // Release persistence sequentially: bounded best-effort SQLite admission
        // is tested separately and cannot promise four contending writers succeed.
        barrier.wait();
        for (release, worker) in workers {
            release.send(()).unwrap();
            worker.join().unwrap();
        }
        let conn = local_store::open(&cfg, Duration::from_millis(250)).unwrap();
        assert_eq!(
            conn.query_row(
                "SELECT COUNT(DISTINCT command_id) FROM command_spans",
                [],
                |r| r.get::<_, i64>(0)
            )
            .unwrap(),
            4
        );
        assert_eq!(
            conn.query_row("SELECT COUNT(*) FROM command_spans", [], |r| r
                .get::<_, i64>(0))
                .unwrap(),
            8
        );
    }

    /// Writer contention is best effort and cannot replace a successful command.
    #[test]
    fn locked_store_does_not_escape_into_command_result() {
        let (_home, cfg) = fixture();
        let conn = local_store::open(&cfg, Duration::from_millis(250)).unwrap();
        schema(&conn).unwrap();
        conn.execute_batch("BEGIN IMMEDIATE").unwrap();
        assert_eq!(run(&cfg, Some(CommandKind::Config), || Ok(42)).unwrap(), 42);
        conn.execute_batch("ROLLBACK").unwrap();
        assert_eq!(
            conn.query_row("SELECT COUNT(*) FROM command_spans", [], |r| r
                .get::<_, i64>(0))
                .unwrap(),
            0
        );
    }
}
