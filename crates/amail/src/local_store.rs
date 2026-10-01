//! Shared physical store access; table ownership belongs to each subsystem.
//!
//! Keep the historical filename for older CLI processes and credential refresh
//! crash markers. Moving it would lose unresolved send keys during upgrades.

use crate::config::Runtime;
use anyhow::Result;
use rusqlite::Connection;
use std::time::Duration;

/// Open the compatible local store with the caller's lock-wait budget.
/// Operational state may wait for a writer; best-effort diagnostics must not
/// inherit that latency. This helper does not create subsystem tables.
pub fn open(cfg: &Runtime, lock_wait: Duration) -> Result<Connection> {
    let path = cfg.home.join("telemetry.sqlite3");
    let conn = Connection::open(&path)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600))?;
    }
    conn.busy_timeout(lock_wait)?;
    Ok(conn)
}
