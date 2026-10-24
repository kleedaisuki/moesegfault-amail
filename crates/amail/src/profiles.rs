//! Terminal reservations and local profile state. Cloud leases remain authoritative.

use crate::config::Runtime;
use anyhow::{ensure, Context, Result};
use rusqlite::{params, Connection, OptionalExtension, Transaction, TransactionBehavior};
use serde::{Deserialize, Serialize};
use std::time::Duration;

pub const IDLE_SECONDS: i64 = 30 * 60;

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
pub struct ActiveProfile {
    pub id: String,
    pub name: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct Profile {
    pub id: String,
    pub name: String,
    pub durable: bool,
    pub owned: bool,
    pub active: bool,
    pub last_used_at: i64,
}

/// Intentionally not Debug or Serialize: a session token is a local capability.
#[derive(Clone)]
pub struct CloudSession {
    pub profile_id: String,
    pub session_token: String,
    pub expires_at: i64,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum Mode {
    Read,
    Write,
}

impl Mode {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Read => "read",
            Self::Write => "write",
        }
    }
}

pub struct Store {
    conn: Connection,
    realm: String,
}

impl Store {
    pub fn open(cfg: &Runtime) -> Result<Self> {
        // Capability-bearing sessions never share a database with diagnostics.
        let path = cfg.home.join("profiles.sqlite3");
        let conn = Connection::open(&path)?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600))?;
        }
        conn.busy_timeout(Duration::from_secs(5))?;
        conn.execute_batch(
            "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA foreign_keys=ON;",
        )?;
        let realm = serde_json::to_string(&(
            &cfg.api_base,
            &cfg.issuer,
            &cfg.client_id,
            crate::session::account_scope(),
        ))?;
        Self::from_connection(conn, realm)
    }

    fn from_connection(conn: Connection, realm: String) -> Result<Self> {
        conn.execute_batch(
            "PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS local_profiles (
                realm TEXT NOT NULL,
                id TEXT NOT NULL,
                name TEXT NOT NULL,
                durable INTEGER NOT NULL CHECK(durable IN (0,1)),
                terminal TEXT,
                last_used_at INTEGER NOT NULL,
                PRIMARY KEY(realm,id), UNIQUE(realm,name)
            );
            CREATE TABLE IF NOT EXISTS local_profile_sessions (
                realm TEXT NOT NULL,
                terminal TEXT NOT NULL,
                profile_id TEXT NOT NULL,
                PRIMARY KEY(realm,terminal), UNIQUE(realm,profile_id),
                FOREIGN KEY(realm,profile_id) REFERENCES local_profiles(realm,id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS local_profile_mailboxes (
                realm TEXT NOT NULL,
                mailbox TEXT NOT NULL,
                profile_id TEXT NOT NULL,
                mode TEXT NOT NULL CHECK(mode IN ('read','write')),
                PRIMARY KEY(realm,mailbox,profile_id),
                FOREIGN KEY(realm,profile_id) REFERENCES local_profiles(realm,id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS local_profiles_expiry
                ON local_profiles(realm,last_used_at);
            CREATE TABLE IF NOT EXISTS local_profile_cloud_sessions (
                realm TEXT NOT NULL,
                local_profile_id TEXT NOT NULL,
                cloud_profile_id TEXT NOT NULL,
                session_token TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                PRIMARY KEY(realm,local_profile_id),
                FOREIGN KEY(realm,local_profile_id) REFERENCES local_profiles(realm,id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS cloud_mailbox_leases (
                realm TEXT NOT NULL,
                local_profile_id TEXT NOT NULL,
                address TEXT NOT NULL,
                generation TEXT NOT NULL,
                mode TEXT NOT NULL CHECK(mode IN ('read','write')),
                lease_token TEXT NOT NULL,
                PRIMARY KEY(realm,local_profile_id,address),
                FOREIGN KEY(realm,local_profile_id)
                    REFERENCES local_profile_cloud_sessions(realm,local_profile_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS local_profile_terminal_state (
                realm TEXT NOT NULL,
                terminal TEXT NOT NULL,
                PRIMARY KEY(realm,terminal)
            );",
        )?;
        conn.execute(
            "INSERT OR IGNORE INTO local_profiles
             (realm,id,name,durable,terminal,last_used_at) VALUES (?1,?2,'user',1,NULL,?3)",
            params![realm, uuid::Uuid::new_v4().to_string(), now()],
        )?;
        Ok(Self { conn, realm })
    }

    pub fn set_cloud_session(
        &mut self,
        local_profile_id: &str,
        profile_id: &str,
        session_token: &str,
        expires_at: i64,
    ) -> Result<()> {
        ensure!(
            !profile_id.is_empty() && !session_token.is_empty() && expires_at > 0,
            "invalid cloud session"
        );
        let tx = self
            .conn
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let exists: bool = tx.query_row(
            "SELECT EXISTS(SELECT 1 FROM local_profiles WHERE realm=?1 AND id=?2)",
            params![self.realm, local_profile_id],
            |row| row.get(0),
        )?;
        ensure!(exists, "profile_not_found");
        tx.execute(
            "DELETE FROM cloud_mailbox_leases WHERE realm=?1 AND local_profile_id=?2
             AND EXISTS(SELECT 1 FROM local_profile_cloud_sessions s
                 WHERE s.realm=?1 AND s.local_profile_id=?2
                 AND (s.cloud_profile_id<>?3 OR s.session_token<>?4))",
            params![self.realm, local_profile_id, profile_id, session_token],
        )?;
        tx.execute(
            "INSERT INTO local_profile_cloud_sessions
                (realm,local_profile_id,cloud_profile_id,session_token,expires_at)
             VALUES (?1,?2,?3,?4,?5)
             ON CONFLICT(realm,local_profile_id) DO UPDATE SET
                cloud_profile_id=excluded.cloud_profile_id,
                session_token=excluded.session_token,expires_at=excluded.expires_at",
            params![
                self.realm,
                local_profile_id,
                profile_id,
                session_token,
                expires_at
            ],
        )?;
        tx.commit()?;
        Ok(())
    }

    pub fn cloud_session(&self, local_profile_id: &str) -> Result<Option<CloudSession>> {
        Ok(self
            .conn
            .query_row(
                "SELECT cloud_profile_id,session_token,expires_at FROM local_profile_cloud_sessions
             WHERE realm=?1 AND local_profile_id=?2",
                params![self.realm, local_profile_id],
                |row| {
                    Ok(CloudSession {
                        profile_id: row.get(0)?,
                        session_token: row.get(1)?,
                        expires_at: row.get(2)?,
                    })
                },
            )
            .optional()?)
    }

    pub fn clear_cloud_session(&mut self, local_profile_id: &str) -> Result<()> {
        self.conn.execute(
            "DELETE FROM local_profile_cloud_sessions WHERE realm=?1 AND local_profile_id=?2",
            params![self.realm, local_profile_id],
        )?;
        Ok(())
    }

    pub fn terminal_initialized(&self, terminal: &str) -> Result<bool> {
        valid_terminal(terminal)?;
        Ok(self.conn.query_row(
            "SELECT EXISTS(SELECT 1 FROM local_profile_terminal_state WHERE realm=?1 AND terminal=?2)",
            params![self.realm, terminal], |row| row.get(0),
        )?)
    }

    pub fn mark_terminal_initialized(&mut self, terminal: &str) -> Result<()> {
        valid_terminal(terminal)?;
        self.conn.execute(
            "INSERT OR IGNORE INTO local_profile_terminal_state(realm,terminal) VALUES (?1,?2)",
            params![self.realm, terminal],
        )?;
        Ok(())
    }

    pub fn set_lease(
        &mut self,
        local_profile_id: &str,
        address: &str,
        lease_token: &str,
        generation: &str,
        mode: &str,
    ) -> Result<()> {
        ensure!(
            !address.is_empty()
                && address.len() <= 254
                && address.is_ascii()
                && !lease_token.is_empty()
                && !generation.is_empty()
                && matches!(mode, "read" | "write"),
            "invalid mailbox lease"
        );
        self.conn.execute(
            "INSERT INTO cloud_mailbox_leases
                (realm,local_profile_id,address,lease_token,generation,mode)
             VALUES (?1,?2,?3,?4,?5,?6)
             ON CONFLICT(realm,local_profile_id,address) DO UPDATE SET
                lease_token=excluded.lease_token,generation=excluded.generation,mode=excluded.mode
             WHERE cloud_mailbox_leases.lease_token<>excluded.lease_token
                OR cloud_mailbox_leases.generation<>excluded.generation
                OR cloud_mailbox_leases.mode<>excluded.mode",
            params![
                self.realm,
                local_profile_id,
                address,
                lease_token,
                generation,
                mode
            ],
        )?;
        Ok(())
    }

    /// This value contains a capability and must never be printed as CLI output.
    pub fn lease(
        &self,
        local_profile_id: &str,
        address: &str,
    ) -> Result<Option<serde_json::Value>> {
        Ok(self
            .conn
            .query_row(
                "SELECT address,lease_token,generation,mode FROM cloud_mailbox_leases
             WHERE realm=?1 AND local_profile_id=?2 AND address=?3",
                params![self.realm, local_profile_id, address],
                |row| {
                    Ok(serde_json::json!({
                        "address":row.get::<_,String>(0)?, "lease_token":row.get::<_,String>(1)?,
                        "generation":row.get::<_,String>(2)?, "mode":row.get::<_,String>(3)?,
                    }))
                },
            )
            .optional()?)
    }

    pub fn remove_lease(&mut self, local_profile_id: &str, address: &str) -> Result<()> {
        self.conn.execute(
            "DELETE FROM cloud_mailbox_leases WHERE realm=?1 AND local_profile_id=?2 AND address=?3",
            params![self.realm, local_profile_id, address],
        )?;
        Ok(())
    }

    pub fn active(&mut self, terminal: &str) -> Result<Option<ActiveProfile>> {
        self.active_at(terminal, now())
    }

    /// Inspect consent requirements without renewing a reservation before consent.
    pub fn peek_active(&mut self, terminal: &str) -> Result<Option<ActiveProfile>> {
        self.peek_active_at(terminal, now())
    }

    pub fn peek_active_at(&mut self, terminal: &str, time: i64) -> Result<Option<ActiveProfile>> {
        valid_terminal(terminal)?;
        let tx = self
            .conn
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        expire(&tx, &self.realm, time)?;
        let profile = current(&tx, &self.realm, terminal)?;
        tx.commit()?;
        Ok(profile)
    }

    pub fn active_at(&mut self, terminal: &str, time: i64) -> Result<Option<ActiveProfile>> {
        valid_terminal(terminal)?;
        let tx = self
            .conn
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        expire(&tx, &self.realm, time)?;
        let profile = current(&tx, &self.realm, terminal)?;
        if let Some(profile) = &profile {
            touch(&tx, &self.realm, &profile.id, time)?;
        }
        tx.commit()?;
        Ok(profile)
    }

    pub fn activate(&mut self, terminal: &str, name: &str) -> Result<ActiveProfile> {
        self.activate_at(terminal, name, now())
    }

    pub fn activate_at(&mut self, terminal: &str, name: &str, time: i64) -> Result<ActiveProfile> {
        valid_terminal(terminal)?;
        valid_name(name)?;
        let tx = self
            .conn
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        expire(&tx, &self.realm, time)?;
        let (id, owner): (String, Option<String>) = tx
            .query_row(
                "SELECT id,terminal FROM local_profiles WHERE realm=?1 AND name=?2",
                params![self.realm, name],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .optional()?
            .context("profile_not_found: create the profile first")?;
        ensure!(
            owner.as_deref().is_none_or(|owner| owner == terminal),
            "profile_busy: another terminal owns this profile"
        );
        if let Some(active) = current(&tx, &self.realm, terminal)? {
            ensure!(
                active.id == id,
                "profile_active: deactivate the current profile before activating another"
            );
        }
        tx.execute(
            "UPDATE local_profiles SET terminal=?3,last_used_at=?4 WHERE realm=?1 AND id=?2",
            params![self.realm, id, terminal, time],
        )?;
        tx.execute(
            "INSERT OR IGNORE INTO local_profile_sessions(realm,terminal,profile_id) VALUES (?1,?2,?3)",
            params![self.realm, terminal, id],
        )?;
        tx.execute(
            "INSERT OR IGNORE INTO local_profile_terminal_state(realm,terminal) VALUES (?1,?2)",
            params![self.realm, terminal],
        )?;
        tx.commit()?;
        Ok(ActiveProfile {
            id,
            name: name.to_owned(),
        })
    }

    pub fn create(&mut self, terminal: &str, name: &str) -> Result<Profile> {
        self.create_at(terminal, name, now())
    }

    pub fn import_cloud_profile(&mut self, name: &str, durable: bool) -> Result<()> {
        valid_name(name)?;
        self.conn.execute(
            "INSERT OR IGNORE INTO local_profiles(realm,id,name,durable,terminal,last_used_at)
             VALUES (?1,?2,?3,?4,NULL,?5)",
            params![
                self.realm,
                uuid::Uuid::new_v4().to_string(),
                name,
                durable,
                now()
            ],
        )?;
        Ok(())
    }

    pub fn create_at(&mut self, terminal: &str, name: &str, time: i64) -> Result<Profile> {
        valid_terminal(terminal)?;
        valid_name(name)?;
        ensure!(
            name != "user",
            "profile_exists: user is the built-in profile"
        );
        let tx = self
            .conn
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        expire(&tx, &self.realm, time)?;
        let creator = require_current(&tx, &self.realm, terminal)?;
        let durable = creator.name == "user";
        let exists: bool = tx.query_row(
            "SELECT EXISTS(SELECT 1 FROM local_profiles WHERE realm=?1 AND name=?2)",
            params![self.realm, name],
            |row| row.get(0),
        )?;
        ensure!(!exists, "profile_exists: choose another name");
        let id = uuid::Uuid::new_v4().to_string();
        tx.execute(
            "INSERT INTO local_profiles(realm,id,name,durable,terminal,last_used_at)
             VALUES (?1,?2,?3,?4,NULL,?5)",
            params![self.realm, id, name, durable, time],
        )?;
        touch(&tx, &self.realm, &creator.id, time)?;
        tx.commit()?;
        Ok(Profile {
            id,
            name: name.to_owned(),
            durable,
            owned: false,
            active: false,
            last_used_at: time,
        })
    }

    pub fn deactivate(&mut self, terminal: &str) -> Result<Option<ActiveProfile>> {
        self.deactivate_at(terminal, now())
    }

    pub fn deactivate_at(&mut self, terminal: &str, time: i64) -> Result<Option<ActiveProfile>> {
        valid_terminal(terminal)?;
        let tx = self
            .conn
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        expire(&tx, &self.realm, time)?;
        let profile = current(&tx, &self.realm, terminal)?;
        tx.execute(
            "DELETE FROM local_profile_sessions WHERE realm=?1 AND terminal=?2",
            params![self.realm, terminal],
        )?;
        tx.execute(
            "INSERT OR IGNORE INTO local_profile_terminal_state(realm,terminal) VALUES (?1,?2)",
            params![self.realm, terminal],
        )?;
        if let Some(profile) = &profile {
            touch(&tx, &self.realm, &profile.id, time)?;
        }
        tx.commit()?;
        Ok(profile)
    }

    pub fn release(&mut self, terminal: &str, name: &str) -> Result<ActiveProfile> {
        self.release_at(terminal, name, now())
    }

    pub fn release_at(&mut self, terminal: &str, name: &str, time: i64) -> Result<ActiveProfile> {
        valid_terminal(terminal)?;
        valid_name(name)?;
        let tx = self
            .conn
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        expire(&tx, &self.realm, time)?;
        let (id, owner): (String, Option<String>) = tx
            .query_row(
                "SELECT id,terminal FROM local_profiles WHERE realm=?1 AND name=?2",
                params![self.realm, name],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .optional()?
            .context("profile_not_found")?;
        ensure!(
            owner.as_deref() == Some(terminal),
            "profile_not_owned: only the reserving terminal can release this profile"
        );
        release_id(&tx, &self.realm, &id, time)?;
        tx.commit()?;
        Ok(ActiveProfile {
            id,
            name: name.to_owned(),
        })
    }

    pub fn list(&mut self, terminal: &str) -> Result<Vec<Profile>> {
        self.list_at(terminal, now())
    }

    pub fn list_at(&mut self, terminal: &str, time: i64) -> Result<Vec<Profile>> {
        valid_terminal(terminal)?;
        let tx = self
            .conn
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        expire(&tx, &self.realm, time)?;
        let rows = {
            let mut stmt = tx.prepare(
                "SELECT p.id,p.name,p.durable,p.terminal=?2,
                    EXISTS(SELECT 1 FROM local_profile_sessions s
                        WHERE s.realm=p.realm AND s.profile_id=p.id AND s.terminal=?2),p.last_used_at
                 FROM local_profiles p WHERE p.realm=?1 ORDER BY p.name",
            )?;
            let mapped = stmt.query_map(params![self.realm, terminal], |row| {
                Ok(Profile {
                    id: row.get(0)?,
                    name: row.get(1)?,
                    durable: row.get(2)?,
                    owned: row.get::<_, Option<bool>>(3)?.unwrap_or(false),
                    active: row.get(4)?,
                    last_used_at: row.get(5)?,
                })
            })?;
            mapped.collect::<rusqlite::Result<Vec<_>>>()?
        };
        if let Some(profile) = current(&tx, &self.realm, terminal)? {
            touch(&tx, &self.realm, &profile.id, time)?;
        }
        tx.commit()?;
        Ok(rows)
    }

    pub fn sweep(&mut self) -> Result<Vec<ActiveProfile>> {
        self.sweep_at(now())
    }

    pub fn sweep_all(&mut self) -> Result<Vec<ActiveProfile>> {
        let time = now();
        let tx = self
            .conn
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let realms = {
            let mut statement = tx.prepare("SELECT DISTINCT realm FROM local_profiles WHERE last_used_at<=?1 AND (terminal IS NOT NULL OR durable=0)")?;
            let rows = statement.query_map([time.saturating_sub(IDLE_SECONDS)], |row| {
                row.get::<_, String>(0)
            })?;
            rows.collect::<rusqlite::Result<Vec<_>>>()?
        };
        let mut released = Vec::new();
        for realm in realms {
            released.extend(expire(&tx, &realm, time)?);
        }
        tx.commit()?;
        Ok(released)
    }

    pub fn sweep_at(&mut self, time: i64) -> Result<Vec<ActiveProfile>> {
        let tx = self
            .conn
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let released = expire(&tx, &self.realm, time)?;
        tx.commit()?;
        Ok(released)
    }

    pub fn claim(&mut self, terminal: &str, mailbox: &str, mode: Mode) -> Result<ActiveProfile> {
        self.claim_at(terminal, mailbox, mode, now())
    }

    pub fn claim_at(
        &mut self,
        terminal: &str,
        mailbox: &str,
        mode: Mode,
        time: i64,
    ) -> Result<ActiveProfile> {
        valid_terminal(terminal)?;
        ensure!(
            !mailbox.is_empty() && mailbox.len() <= 254 && mailbox.is_ascii(),
            "invalid mailbox"
        );
        let tx = self
            .conn
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        expire(&tx, &self.realm, time)?;
        let profile = require_current(&tx, &self.realm, terminal)?;
        let busy: bool = tx.query_row(
            "SELECT EXISTS(SELECT 1 FROM local_profile_mailboxes
                WHERE realm=?1 AND mailbox=?2 AND profile_id<>?3 AND (mode='write' OR ?4='write'))",
            params![self.realm, mailbox, profile.id, mode.as_str()],
            |row| row.get(0),
        )?;
        ensure!(
            !busy,
            "mailbox_busy: ownership cannot preempt another profile"
        );
        tx.execute(
            "INSERT INTO local_profile_mailboxes(realm,mailbox,profile_id,mode) VALUES (?1,?2,?3,?4)
             ON CONFLICT(realm,mailbox,profile_id) DO UPDATE SET mode=excluded.mode",
            params![self.realm, mailbox, profile.id, mode.as_str()],
        )?;
        touch(&tx, &self.realm, &profile.id, time)?;
        tx.commit()?;
        Ok(profile)
    }

    pub fn unclaim(&mut self, terminal: &str, mailbox: &str) -> Result<ActiveProfile> {
        let time = now();
        valid_terminal(terminal)?;
        let tx = self
            .conn
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        expire(&tx, &self.realm, time)?;
        let profile = require_current(&tx, &self.realm, terminal)?;
        tx.execute(
            "DELETE FROM local_profile_mailboxes WHERE realm=?1 AND mailbox=?2 AND profile_id=?3",
            params![self.realm, mailbox, profile.id],
        )?;
        touch(&tx, &self.realm, &profile.id, time)?;
        tx.commit()?;
        Ok(profile)
    }
}

fn now() -> i64 {
    chrono::Utc::now().timestamp()
}

fn valid_terminal(terminal: &str) -> Result<()> {
    ensure!(
        !terminal.is_empty() && terminal.len() <= 512 && !terminal.chars().any(char::is_control),
        "invalid terminal identity"
    );
    Ok(())
}

fn valid_name(name: &str) -> Result<()> {
    ensure!(
        !name.is_empty()
            && name.len() <= 64
            && name
                .bytes()
                .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == b'-' || c == b'_'),
        "invalid profile name: use 1-64 lowercase ASCII letters, digits, '-' or '_'"
    );
    Ok(())
}

fn current(tx: &Transaction<'_>, realm: &str, terminal: &str) -> Result<Option<ActiveProfile>> {
    Ok(tx
        .query_row(
            "SELECT p.id,p.name FROM local_profile_sessions s JOIN local_profiles p
         ON p.realm=s.realm AND p.id=s.profile_id
         WHERE s.realm=?1 AND s.terminal=?2 AND p.terminal=?2",
            params![realm, terminal],
            |row| {
                Ok(ActiveProfile {
                    id: row.get(0)?,
                    name: row.get(1)?,
                })
            },
        )
        .optional()?)
}

fn require_current(tx: &Transaction<'_>, realm: &str, terminal: &str) -> Result<ActiveProfile> {
    current(tx, realm, terminal)?.context("profile_inactive: activate a profile first")
}

fn touch(tx: &Transaction<'_>, realm: &str, id: &str, time: i64) -> Result<()> {
    tx.execute(
        "UPDATE local_profiles SET last_used_at=max(last_used_at,?3) WHERE realm=?1 AND id=?2",
        params![realm, id, time],
    )?;
    Ok(())
}

fn release_id(tx: &Transaction<'_>, realm: &str, id: &str, time: i64) -> Result<()> {
    tx.execute(
        "DELETE FROM local_profile_cloud_sessions WHERE realm=?1 AND local_profile_id=?2",
        params![realm, id],
    )?;
    tx.execute(
        "DELETE FROM local_profile_sessions WHERE realm=?1 AND profile_id=?2",
        params![realm, id],
    )?;
    tx.execute(
        "DELETE FROM local_profile_mailboxes WHERE realm=?1 AND profile_id=?2",
        params![realm, id],
    )?;
    tx.execute(
        "DELETE FROM local_profiles WHERE realm=?1 AND id=?2 AND durable=0",
        params![realm, id],
    )?;
    tx.execute(
        "UPDATE local_profiles SET terminal=NULL,last_used_at=?3 WHERE realm=?1 AND id=?2",
        params![realm, id, time],
    )?;
    Ok(())
}

fn expire(tx: &Transaction<'_>, realm: &str, time: i64) -> Result<Vec<ActiveProfile>> {
    let expired = {
        let mut stmt = tx.prepare(
            "SELECT id,name FROM local_profiles WHERE realm=?1 AND last_used_at<=?2
             AND (terminal IS NOT NULL OR durable=0)",
        )?;
        let mapped = stmt.query_map(params![realm, time.saturating_sub(IDLE_SECONDS)], |row| {
            Ok(ActiveProfile {
                id: row.get(0)?,
                name: row.get(1)?,
            })
        })?;
        mapped.collect::<rusqlite::Result<Vec<_>>>()?
    };
    for profile in &expired {
        release_id(tx, realm, &profile.id, time)?;
    }
    Ok(expired)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn store() -> Store {
        Store::from_connection(Connection::open_in_memory().unwrap(), "test".to_owned()).unwrap()
    }

    fn agents(store: &mut Store) {
        store.activate_at("human", "user", 100).unwrap();
        store.create_at("human", "alice", 100).unwrap();
        store.create_at("human", "bob", 100).unwrap();
        store.activate_at("terminal-a", "alice", 100).unwrap();
        store.activate_at("terminal-b", "bob", 100).unwrap();
    }

    #[test]
    fn daemon_sweep_expires_profiles_outside_its_thread_account_realm() {
        let mut store = store();
        let expired = now() - IDLE_SECONDS - 10;
        store.activate_at("owner", "user", expired).unwrap();
        store
            .conn
            .execute(
                "INSERT INTO local_profiles(realm,id,name,durable,terminal,last_used_at)
             VALUES ('other-account','other-id','temporary',0,'other-terminal',?1)",
                [expired],
            )
            .unwrap();
        let released = store.sweep_all().unwrap();
        assert!(released.iter().any(|profile| profile.id == "other-id"));
        let remaining: i64 = store
            .conn
            .query_row(
                "SELECT COUNT(*) FROM local_profiles WHERE realm='other-account'",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(remaining, 0);
        assert!(store.peek_active("owner").unwrap().is_none());
    }

    #[test]
    fn importing_cloud_names_is_idempotent_and_preserves_local_identity() {
        let mut store = store();
        store.import_cloud_profile("shared", true).unwrap();
        let first = store
            .list("viewer")
            .unwrap()
            .into_iter()
            .find(|profile| profile.name == "shared")
            .unwrap();
        store.import_cloud_profile("shared", true).unwrap();
        let second = store
            .list("viewer")
            .unwrap()
            .into_iter()
            .find(|profile| profile.name == "shared")
            .unwrap();
        assert_eq!(first.id, second.id);
        assert!(second.durable);
        assert!(store.import_cloud_profile("../unsafe", true).is_err());
    }

    #[test]
    fn deactivate_retains_exclusive_reservation_until_expiry() {
        let mut store = store();
        let profile = store.activate_at("a", "user", 100).unwrap();
        store.deactivate_at("a", 110).unwrap();
        assert!(store.active_at("a", 120).unwrap().is_none());
        assert!(store.activate_at("b", "user", 120).is_err());
        assert_eq!(store.activate_at("a", "user", 130).unwrap(), profile);
        assert!(store.activate_at("b", "user", 1929).is_err());
        assert_eq!(store.activate_at("b", "user", 1930).unwrap(), profile);
    }

    #[test]
    fn terminal_must_explicitly_deactivate_before_switching() {
        let mut store = store();
        agents(&mut store);
        assert!(store.activate_at("human", "alice", 101).is_err());
        store.create_at("human", "charlie", 101).unwrap();
        assert!(store.activate_at("human", "charlie", 101).is_err());
        store.deactivate_at("human", 102).unwrap();
        store.activate_at("human", "charlie", 103).unwrap();
        assert!(store.activate_at("other", "user", 104).is_err());
    }

    #[test]
    fn ephemeral_release_deletes_and_name_reuse_gets_new_identity() {
        let mut store = store();
        agents(&mut store);
        let first = store.create_at("terminal-a", "child", 100).unwrap();
        assert!(!first.durable);
        store.activate_at("child-terminal", "child", 100).unwrap();
        store.release_at("child-terminal", "child", 101).unwrap();
        assert!(store.activate_at("child-terminal", "child", 102).is_err());
        let next = store.create_at("terminal-a", "child", 102).unwrap();
        assert_ne!(first.id, next.id);
        store.sweep_at(1902).unwrap();
        let remaining = store.list_at("nobody", 1902).unwrap();
        assert_eq!(
            remaining
                .iter()
                .map(|p| p.name.as_str())
                .collect::<Vec<_>>(),
            vec!["alice", "bob", "user"]
        );
        assert!(remaining.iter().all(|p| !p.owned && !p.active));
    }

    #[test]
    fn read_sharing_and_exclusive_write_are_nonpreemptible() {
        for first in [Mode::Read, Mode::Write] {
            for second in [Mode::Read, Mode::Write] {
                let mut store = store();
                agents(&mut store);
                store
                    .claim_at("terminal-a", "box@example.test", first, 101)
                    .unwrap();
                let acquired = store.claim_at("terminal-b", "box@example.test", second, 101);
                assert_eq!(
                    acquired.is_ok(),
                    first == Mode::Read && second == Mode::Read
                );
                store.release_at("terminal-a", "alice", 102).unwrap();
                store
                    .claim_at("terminal-b", "box@example.test", Mode::Write, 103)
                    .unwrap();
            }
        }
    }

    #[test]
    fn same_terminal_processes_share_activity_and_release_clears_claims() {
        let mut store = store();
        agents(&mut store);
        let first = store.active_at("terminal-a", 1000).unwrap().unwrap();
        assert_eq!(store.active_at("terminal-a", 2000).unwrap().unwrap(), first);
        store
            .claim_at("terminal-a", "box@example.test", Mode::Write, 2000)
            .unwrap();
        store.activate_at("terminal-b", "bob", 2000).unwrap();
        assert!(store
            .claim_at("terminal-b", "box@example.test", Mode::Read, 2001)
            .is_err());
        store.sweep_at(3800).unwrap();
        store.activate_at("terminal-b", "bob", 3800).unwrap();
        store
            .claim_at("terminal-b", "box@example.test", Mode::Write, 3800)
            .unwrap();
    }

    #[test]
    fn realms_are_isolated_in_shared_database() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("profiles.sqlite3");
        let mut a =
            Store::from_connection(Connection::open(&path).unwrap(), "a".to_owned()).unwrap();
        let mut b =
            Store::from_connection(Connection::open(&path).unwrap(), "b".to_owned()).unwrap();
        let first = a.activate_at("one", "user", 100).unwrap();
        let other = b.activate_at("two", "user", 100).unwrap();
        assert_ne!(first.id, other.id);
        assert!(a.activate_at("two", "user", 100).is_err());
    }

    #[test]
    fn consent_peek_does_not_extend_session_and_release_discards_capability() {
        let mut store = store();
        let user = store.activate_at("a", "user", 100).unwrap();
        store
            .set_cloud_session(&user.id, "cloud-id", "private-token", 1900)
            .unwrap();
        let session = store.cloud_session(&user.id).unwrap().unwrap();
        assert_eq!(session.profile_id, "cloud-id");
        assert_eq!(session.session_token, "private-token");
        assert_eq!(session.expires_at, 1900);
        assert!(store.peek_active_at("a", 1899).unwrap().is_some());
        assert!(store.peek_active_at("a", 1900).unwrap().is_none());
        assert!(store.cloud_session(&user.id).unwrap().is_none());
        store.activate_at("a", "user", 1901).unwrap();
        store.deactivate_at("a", 1902).unwrap();
        store.release_at("a", "user", 1903).unwrap();
        store.activate_at("b", "user", 1904).unwrap();
    }

    #[test]
    fn mailbox_capabilities_follow_session_generation_and_release() {
        let mut store = store();
        let user = store.activate_at("a", "user", 100).unwrap();
        let address = "box@tmpaddr.moesegfault.dev";
        assert!(store
            .set_lease(&user.id, address, "lease-a", "gen-a", "read")
            .is_err());
        store
            .set_cloud_session(&user.id, "cloud-a", "session-a", 1900)
            .unwrap();
        store
            .set_lease(&user.id, address, "lease-a", "gen-a", "read")
            .unwrap();
        store
            .set_cloud_session(&user.id, "cloud-a", "session-a", 2000)
            .unwrap();
        assert_eq!(
            store.lease(&user.id, address).unwrap().unwrap()["lease_token"],
            "lease-a"
        );
        store
            .set_lease(&user.id, address, "lease-b", "gen-b", "write")
            .unwrap();
        let lease = store.lease(&user.id, address).unwrap().unwrap();
        assert_eq!(lease["generation"], "gen-b");
        assert_eq!(lease["mode"], "write");
        store
            .set_cloud_session(&user.id, "cloud-a", "session-b", 2100)
            .unwrap();
        assert!(store.lease(&user.id, address).unwrap().is_none());
        store
            .set_lease(&user.id, address, "lease-c", "gen-b", "read")
            .unwrap();
        store.remove_lease(&user.id, address).unwrap();
        assert!(store.lease(&user.id, address).unwrap().is_none());
        store
            .set_lease(&user.id, address, "lease-d", "gen-b", "read")
            .unwrap();
        store.clear_cloud_session(&user.id).unwrap();
        assert!(store.lease(&user.id, address).unwrap().is_none());
        store
            .set_cloud_session(&user.id, "cloud-a", "session-c", 2200)
            .unwrap();
        store
            .set_lease(&user.id, address, "lease-e", "gen-b", "read")
            .unwrap();
        store.release_at("a", "user", 101).unwrap();
        assert!(store.lease(&user.id, address).unwrap().is_none());
    }

    #[test]
    fn terminal_initialization_survives_expiry_and_explicit_deactivation() {
        let mut store = store();
        assert!(!store.terminal_initialized("a").unwrap());
        store.deactivate_at("a", 100).unwrap();
        assert!(store.terminal_initialized("a").unwrap());
        assert!(store.peek_active_at("a", 101).unwrap().is_none());
        store.activate_at("b", "user", 100).unwrap();
        store.sweep_at(1900).unwrap();
        assert!(store.terminal_initialized("b").unwrap());
        store.mark_terminal_initialized("c").unwrap();
        assert!(store.terminal_initialized("c").unwrap());
        assert!(!store.terminal_initialized("d").unwrap());
    }
}
