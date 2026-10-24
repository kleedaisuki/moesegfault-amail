//! Profile sessions and non-preemptible mailbox capabilities on D1's primary.
//! Conditional writes, not a read-then-write decision, arbitrate contenders.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use worker::{Env, Method, Request, Response};

use crate::{auth::Principal, bind_num, bind_str, database::Database, now, AppError, AppResult};

const IDLE_MS: i64 = 30 * 60_000;

#[derive(Clone, Debug, Deserialize, Serialize)]
pub(crate) struct Session {
    pub profile_id: String,
    pub name: String,
    pub session_token: String,
    pub is_user: bool,
    pub expires_at: i64,
    #[serde(skip)]
    pub lease_tokens: BTreeMap<String, String>,
}

#[derive(Deserialize)]
struct Profile {
    id: String,
    name: String,
    durable: i64,
    is_user: i64,
    session_token: Option<String>,
}

fn denied(code: &'static str) -> AppError {
    AppError { status: 403, code }
}

fn valid_name(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= 64
        && name
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-' || b == b'_')
}

fn valid_terminal(id: &str) -> bool {
    id.len() >= 32
        && id.len() <= 128
        && id
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
}

pub(crate) async fn cleanup(db: &Database) -> worker::Result<()> {
    let at = now();
    db.batch(vec![
        db.prepare("DELETE FROM mail_profiles WHERE durable=0 AND (session_expires_at<=?1 OR (session_token IS NULL AND created_at<=?2))")
            .bind(&[bind_num(at),bind_num(at-IDLE_MS)])?,
        db.prepare("UPDATE mail_profiles SET terminal_id=NULL,session_token=NULL,session_expires_at=NULL WHERE session_expires_at<=?1")
            .bind(&[bind_num(at)])?,
    ]).await?;
    Ok(())
}

/// Missing sessions remain compatible only until this owner opts into profiles.
pub(crate) async fn resolve(
    req: &Request,
    db: &Database,
    user: &Principal,
) -> AppResult<Option<Session>> {
    let token = req.headers().get("x-amail-profile-session")?;
    let Some(token) = token else {
        let enrolled = db.prepare("SELECT 1 AS present FROM mail_profiles WHERE owner_iss=?1 AND owner_sub=?2 LIMIT 1")
            .bind(&[bind_str(&user.iss),bind_str(&user.sub)])?
            .first::<serde_json::Value>(None).await?.is_some();
        return if enrolled {
            Err(denied("profile_session_required"))
        } else {
            Ok(None)
        };
    };
    if uuid::Uuid::parse_str(&token).is_err() {
        return Err(denied("profile_session_expired"));
    }
    let expires = now() + IDLE_MS;
    let row = db.prepare("UPDATE mail_profiles SET session_expires_at=?1 WHERE owner_iss=?2 AND owner_sub=?3 AND session_token=?4 AND session_expires_at>?5 RETURNING id,name,durable,is_user,terminal_id,session_token,session_expires_at")
        .bind(&[bind_num(expires),bind_str(&user.iss),bind_str(&user.sub),bind_str(&token),bind_num(now())])?
        .first::<Profile>(None).await?.ok_or_else(|| denied("profile_session_expired"))?;
    let leases=db.prepare("SELECT l.address,l.lease_token FROM mailbox_leases l JOIN addresses a ON a.address=l.address AND a.generation=l.address_generation WHERE l.profile_id=?1 AND l.session_token=?2 AND a.state='active' AND (a.expires_at IS NULL OR a.expires_at>CAST(unixepoch('subsec')*1000 AS INTEGER)) LIMIT 256")
        .bind(&[bind_str(&row.id),bind_str(&token)])?.all().await?.results::<LeaseSnapshot>()?;
    Ok(Some(Session {
        profile_id: row.id,
        name: row.name,
        session_token: token,
        is_user: row.is_user == 1,
        expires_at: expires / 1000,
        lease_tokens: leases
            .into_iter()
            .map(|lease| (lease.address, lease.lease_token))
            .collect(),
    }))
}

pub(crate) fn is_route(method: Method, path: &str) -> bool {
    matches!(
        (method, path),
        (Method::Get, "/v1/profiles")
            | (
                Method::Post,
                "/v1/profiles"
                    | "/v1/profiles/activate"
                    | "/v1/profiles/release"
                    | "/v1/leases/acquire"
                    | "/v1/leases/renew"
                    | "/v1/leases/release"
            )
    )
}

pub(crate) async fn dispatch(
    req: &mut Request,
    _env: &Env,
    db: &Database,
    user: &Principal,
    path: &str,
) -> AppResult<Option<Response>> {
    if !is_route(req.method(), path) {
        return Ok(None);
    }
    cleanup(db).await?;
    if path == "/v1/profiles/activate" && req.method() == Method::Post {
        return activate(req, db, user).await.map(Some);
    }
    let session = resolve(req, db, user)
        .await?
        .ok_or_else(|| denied("profile_session_required"))?;
    match (req.method(), path) {
        (Method::Get, "/v1/profiles") => {
            let rows = db.prepare("SELECT id AS profile_id,name,durable,is_user,session_expires_at/1000 AS expires_at FROM mail_profiles WHERE owner_iss=?1 AND owner_sub=?2 ORDER BY name LIMIT 128")
                .bind(&[bind_str(&user.iss),bind_str(&user.sub)])?.all().await?.results::<serde_json::Value>()?;
            Ok(Some(Response::from_json(
                &serde_json::json!({"profiles":rows}),
            )?))
        }
        (Method::Post, "/v1/profiles") => create(req, db, user, &session).await.map(Some),
        (Method::Post, "/v1/profiles/release") => {
            db.batch(vec![
                db.prepare("DELETE FROM mail_profiles WHERE id=?1 AND session_token=?2 AND durable=0")
                    .bind(&[bind_str(&session.profile_id),bind_str(&session.session_token)])?,
                db.prepare("UPDATE mail_profiles SET terminal_id=NULL,session_token=NULL,session_expires_at=NULL WHERE id=?1 AND session_token=?2")
                    .bind(&[bind_str(&session.profile_id),bind_str(&session.session_token)])?,
            ]).await?;
            Ok(Some(Response::from_json(
                &serde_json::json!({"released":true}),
            )?))
        }
        (Method::Post, "/v1/leases/acquire") => acquire(req, db, user, &session).await.map(Some),
        (Method::Post, "/v1/leases/renew") => renew(req, db, &session).await.map(Some),
        (Method::Post, "/v1/leases/release") => release(req, db, &session).await.map(Some),
        _ => Err(AppError::not_found()),
    }
}

async fn activate(req: &mut Request, db: &Database, user: &Principal) -> AppResult<Response> {
    #[derive(Deserialize)]
    struct Input {
        name: String,
        terminal_id: String,
        session_token: Option<String>,
    }
    let input: Input = req
        .json()
        .await
        .map_err(|_| AppError::bad("invalid_profile"))?;
    if !valid_name(&input.name) || !valid_terminal(&input.terminal_id) {
        return Err(AppError::bad("invalid_profile"));
    }
    if input.name == "user" {
        db.prepare("INSERT INTO mail_profiles(id,owner_iss,owner_sub,name,durable,is_user,created_at) VALUES(?1,?2,?3,'user',1,1,?4) ON CONFLICT(owner_iss,owner_sub,name) DO NOTHING")
            .bind(&[bind_str(&uuid::Uuid::new_v4().to_string()),bind_str(&user.iss),bind_str(&user.sub),bind_num(now())])?.run().await?;
    }
    // A random terminal capability permits recovery after an unacknowledged activation.
    // A supplied session token is an additional fence, never a terminal takeover.
    let token = uuid::Uuid::new_v4().to_string();
    let expires = now() + IDLE_MS;
    let row = db.prepare("UPDATE mail_profiles SET terminal_id=?1,session_token=COALESCE(session_token,?2),session_expires_at=?3 WHERE owner_iss=?4 AND owner_sub=?5 AND name=?6 AND (terminal_id IS NULL OR terminal_id=?1) AND (?7='' OR session_token IS NULL OR session_token=?7) RETURNING id,name,durable,is_user,terminal_id,session_token,session_expires_at")
        .bind(&[bind_str(&input.terminal_id),bind_str(&token),bind_num(expires),bind_str(&user.iss),bind_str(&user.sub),bind_str(&input.name),bind_str(input.session_token.as_deref().unwrap_or(""))])?
        .first::<Profile>(None).await?;
    let Some(row) = row else {
        let exists=db.prepare("SELECT 1 AS present FROM mail_profiles WHERE owner_iss=?1 AND owner_sub=?2 AND name=?3")
            .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(&input.name)])?.first::<serde_json::Value>(None).await?.is_some();
        return Err(if exists {
            AppError::conflict("profile_in_use")
        } else {
            AppError {
                status: 404,
                code: "profile_not_registered",
            }
        });
    };
    Response::from_json(&Session {
        profile_id: row.id,
        name: row.name,
        session_token: row.session_token.unwrap_or(token),
        is_user: row.is_user == 1,
        expires_at: expires / 1000,
        lease_tokens: BTreeMap::new(),
    })
    .map_err(Into::into)
}

async fn create(
    req: &mut Request,
    db: &Database,
    user: &Principal,
    session: &Session,
) -> AppResult<Response> {
    #[derive(Deserialize)]
    struct Input {
        name: String,
        durable: Option<bool>,
    }
    let input: Input = req
        .json()
        .await
        .map_err(|_| AppError::bad("invalid_profile"))?;
    if !valid_name(&input.name) || input.name == "user" {
        return Err(AppError::bad("invalid_profile"));
    }
    let id = uuid::Uuid::new_v4().to_string();
    let row = db.prepare("INSERT INTO mail_profiles(id,owner_iss,owner_sub,name,durable,is_user,created_at) SELECT ?1,?2,?3,?4,?5,0,?6 WHERE (SELECT COUNT(*) FROM mail_profiles WHERE owner_iss=?2 AND owner_sub=?3)<128 AND EXISTS(SELECT 1 FROM mail_profiles WHERE id=?7 AND session_token=?8 AND session_expires_at>?6) ON CONFLICT(owner_iss,owner_sub,name) DO NOTHING RETURNING id,name,durable,is_user,terminal_id,session_token,session_expires_at")
            .bind(&[bind_str(&id),bind_str(&user.iss),bind_str(&user.sub),bind_str(&input.name),bind_num(i64::from(session.is_user && input.durable.unwrap_or(true))),bind_num(now()),bind_str(&session.profile_id),bind_str(&session.session_token)])?
        .first::<Profile>(None).await?.ok_or_else(|| AppError::conflict("profile_exists_or_limit"))?;
    Response::from_json(&serde_json::json!({"profile_id":row.id,"name":row.name,"durable":row.durable==1,"is_user":false})).map_err(Into::into)
}

const ACQUIRE_SQL: &str = "INSERT INTO mailbox_leases(address,address_generation,profile_id,session_token,mode,lease_token,acquired_at) SELECT a.address,a.generation,?3,?4,?5,?6,?7 FROM addresses a WHERE a.address=?1 AND a.owner_iss=?8 AND a.owner_sub=?9 AND a.state='active' AND (a.expires_at IS NULL OR a.expires_at>?7) AND EXISTS(SELECT 1 FROM mail_profiles p WHERE p.id=?3 AND p.session_token=?4 AND p.session_expires_at>?7) AND NOT EXISTS(SELECT 1 FROM mailbox_leases l JOIN mail_profiles p ON p.id=l.profile_id AND p.session_token=l.session_token WHERE l.address=a.address AND l.address_generation=a.generation AND p.session_expires_at>?7 AND l.profile_id!=?3 AND (l.mode='write' OR ?5='write')) ON CONFLICT(address,profile_id) DO UPDATE SET address_generation=excluded.address_generation,session_token=excluded.session_token,mode=CASE WHEN mailbox_leases.session_token=excluded.session_token AND mailbox_leases.address_generation=excluded.address_generation AND mailbox_leases.mode='write' THEN 'write' ELSE excluded.mode END,lease_token=CASE WHEN mailbox_leases.session_token=excluded.session_token AND (mailbox_leases.mode=excluded.mode OR mailbox_leases.mode='write') AND mailbox_leases.address_generation=excluded.address_generation THEN mailbox_leases.lease_token ELSE excluded.lease_token END,acquired_at=excluded.acquired_at RETURNING address,address_generation AS generation,mode,lease_token";

#[derive(Deserialize, Serialize)]
struct Lease {
    address: String,
    generation: String,
    mode: String,
    lease_token: String,
}

async fn acquire(
    req: &mut Request,
    db: &Database,
    user: &Principal,
    session: &Session,
) -> AppResult<Response> {
    #[derive(Deserialize)]
    struct Input {
        address: String,
        mode: String,
    }
    let input: Input = req
        .json()
        .await
        .map_err(|_| AppError::bad("invalid_lease"))?;
    let lease = claim(db, user, session, &input.address, &input.mode).await?;
    Response::from_json(&lease).map_err(Into::into)
}

/// Used immediately after provisioning so a new address is usable by its creator.
pub(crate) async fn claim(
    db: &Database,
    user: &Principal,
    session: &Session,
    address: &str,
    mode: &str,
) -> AppResult<serde_json::Value> {
    if mode != "read" && mode != "write" {
        return Err(AppError::bad("invalid_lease_mode"));
    }
    let token = uuid::Uuid::new_v4().to_string();
    let lease = db
        .prepare(ACQUIRE_SQL)
        .bind(&[
            bind_str(address),
            bind_str(""),
            bind_str(&session.profile_id),
            bind_str(&session.session_token),
            bind_str(mode),
            bind_str(&token),
            bind_num(now()),
            bind_str(&user.iss),
            bind_str(&user.sub),
        ])?
        .first::<Lease>(None)
        .await?
        .ok_or_else(|| AppError::conflict("mailbox_in_use"))?;
    Ok(lease_value(lease, session))
}

#[derive(Deserialize)]
struct LeaseInput {
    address: String,
    #[serde(alias = "lease_token")]
    token: String,
}

async fn renew(req: &mut Request, db: &Database, session: &Session) -> AppResult<Response> {
    let input: LeaseInput = req
        .json()
        .await
        .map_err(|_| AppError::bad("invalid_lease"))?;
    let lease=db.prepare("SELECT l.address,l.address_generation AS generation,l.mode,l.lease_token FROM mailbox_leases l JOIN addresses a ON a.address=l.address AND a.generation=l.address_generation WHERE l.address=?1 AND l.profile_id=?2 AND l.session_token=?3 AND l.lease_token=?4 AND a.state='active' AND (a.expires_at IS NULL OR a.expires_at>?5)")
        .bind(&[bind_str(&input.address),bind_str(&session.profile_id),bind_str(&session.session_token),bind_str(&input.token),bind_num(now())])?.first::<Lease>(None).await?.ok_or_else(||denied("mailbox_lease_expired"))?;
    lease_response(lease, session)
}

async fn release(req: &mut Request, db: &Database, session: &Session) -> AppResult<Response> {
    let input: LeaseInput = req
        .json()
        .await
        .map_err(|_| AppError::bad("invalid_lease"))?;
    db.prepare("DELETE FROM mailbox_leases WHERE address=?1 AND profile_id=?2 AND session_token=?3 AND lease_token=?4")
        .bind(&[bind_str(&input.address),bind_str(&session.profile_id),bind_str(&session.session_token),bind_str(&input.token)])?.run().await?;
    Response::from_json(&serde_json::json!({"released":true})).map_err(Into::into)
}

fn lease_response(lease: Lease, session: &Session) -> AppResult<Response> {
    Response::from_json(&lease_value(lease, session)).map_err(Into::into)
}

fn lease_value(lease: Lease, session: &Session) -> serde_json::Value {
    serde_json::json!({"address":lease.address,"generation":lease.generation,"mode":lease.mode,"lease_token":lease.lease_token,"expires_at":session.expires_at})
}

#[derive(Deserialize)]
struct LeaseSnapshot {
    address: String,
    lease_token: String,
}

fn literal(value: &str) -> String {
    format!("'{}'", value.replace('\'', "''"))
}

pub(crate) fn scope(user: &Principal) -> String {
    let Some(session) = &user.profile else {
        return String::new();
    };
    let mut hash = Sha256::new();
    hash.update(session.profile_id.as_bytes());
    hash.update([0]);
    hash.update(session.session_token.as_bytes());
    for (address, token) in &session.lease_tokens {
        hash.update([0]);
        hash.update(address.as_bytes());
        hash.update([0]);
        hash.update(token.as_bytes());
    }
    format!("{:x}", hash.finalize())
}

pub(crate) fn send_scope(user: &Principal) -> String {
    user.profile
        .as_ref()
        .map(|p| format!("{:x}", Sha256::digest(p.profile_id.as_bytes())))
        .unwrap_or_default()
}

pub(crate) fn address_filter(user: &Principal, alias: &str, write: bool) -> String {
    let Some(session) = &user.profile else {
        return legacy_filter(user);
    };
    let mode = if write { " AND l.mode='write'" } else { "" };
    let tokens = session
        .lease_tokens
        .iter()
        .map(|(address, token)| {
            format!(
                "(l.address={} AND l.lease_token={})",
                literal(address),
                literal(token)
            )
        })
        .collect::<Vec<_>>()
        .join(" OR ");
    let tokens = if tokens.is_empty() { "0" } else { &tokens };
    format!("EXISTS(SELECT 1 FROM mailbox_leases l JOIN mail_profiles p ON p.id=l.profile_id AND p.session_token=l.session_token WHERE l.address={alias}.address AND l.address_generation={alias}.generation AND l.profile_id={} AND l.session_token={} AND p.session_expires_at>CAST(unixepoch('subsec')*1000 AS INTEGER) AND ({tokens}) {mode}) AND {alias}.state='active' AND ({alias}.expires_at IS NULL OR {alias}.expires_at>CAST(unixepoch('subsec')*1000 AS INTEGER))",literal(&session.profile_id),literal(&session.session_token))
}

pub(crate) fn message_filter(user: &Principal, alias: &str) -> String {
    message_mode_filter(user, alias, false)
}

pub(crate) fn message_write_filter(user: &Principal, alias: &str) -> String {
    message_mode_filter(user, alias, true)
}

fn message_mode_filter(user: &Principal, alias: &str, write: bool) -> String {
    if user.profile.is_none() {
        return legacy_filter(user);
    }
    format!("EXISTS(SELECT 1 FROM addresses profile_address WHERE profile_address.address={alias}.address AND profile_address.generation={alias}.mailbox_generation AND {})",address_filter(user,"profile_address",write))
}

fn legacy_filter(user: &Principal) -> String {
    if !user.enrollment_fence {
        return "1=1".into();
    }
    format!("NOT EXISTS(SELECT 1 FROM mail_profiles enrollment WHERE enrollment.owner_iss={} AND enrollment.owner_sub={})",literal(&user.iss),literal(&user.sub))
}

pub(crate) async fn authorized_address(
    db: &Database,
    user: &Principal,
    session: &Session,
    address: &str,
    write: bool,
) -> AppResult<()> {
    let mut scoped = user.clone();
    scoped.profile = Some(session.clone());
    let sql=format!("SELECT 1 AS present FROM addresses a WHERE a.address=?1 AND a.owner_iss=?2 AND a.owner_sub=?3 AND {}",address_filter(&scoped,"a",write));
    let found = db
        .prepare(sql)
        .bind(&[bind_str(address), bind_str(&user.iss), bind_str(&user.sub)])?
        .first::<serde_json::Value>(None)
        .await?
        .is_some();
    if found {
        Ok(())
    } else {
        Err(denied("mailbox_lease_required"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rusqlite::{params, Connection, OptionalExtension};

    fn database() -> Connection {
        let db = Connection::open_in_memory().unwrap();
        db.execute_batch("PRAGMA foreign_keys=ON;
            CREATE TABLE addresses(address TEXT PRIMARY KEY,owner_iss TEXT,owner_sub TEXT,generation TEXT,state TEXT,expires_at INTEGER);
            CREATE TABLE search_jobs(id TEXT);
            CREATE TABLE send_requests(id TEXT);").unwrap();
        db.execute_batch(include_str!("../migrations/0016_profiles.sql"))
            .unwrap();
        db.execute("INSERT INTO addresses VALUES('test@tmpaddr.moesegfault.dev','iss','sub','generation-1','active',NULL)",[]).unwrap();
        for id in ["one", "two", "three"] {
            db.execute("INSERT INTO mail_profiles(id,owner_iss,owner_sub,name,durable,is_user,terminal_id,session_token,session_expires_at,created_at) VALUES(?1,'iss','sub',?1,0,0,?1,?1,9999999999999,0)", [id]).unwrap();
        }
        db
    }

    fn acquire_for(db: &Connection, id: &str, mode: &str, token: &str, at: i64) -> Option<String> {
        db.query_row(
            ACQUIRE_SQL,
            params![
                "test@tmpaddr.moesegfault.dev",
                "",
                id,
                id,
                mode,
                token,
                at,
                "iss",
                "sub"
            ],
            |row| row.get("lease_token"),
        )
        .optional()
        .unwrap()
    }

    #[test]
    fn shared_readers_block_writer_and_cannot_be_preempted() {
        let db = database();
        assert_eq!(
            acquire_for(&db, "one", "read", "r1", 10).as_deref(),
            Some("r1")
        );
        assert_eq!(
            acquire_for(&db, "two", "read", "r2", 10).as_deref(),
            Some("r2")
        );
        assert!(acquire_for(&db, "three", "write", "w3", 10).is_none());
        assert!(acquire_for(&db, "one", "write", "w1", 10).is_none());
        assert_eq!(
            acquire_for(&db, "one", "read", "retry", 10).as_deref(),
            Some("r1")
        );
        db.execute("DELETE FROM mailbox_leases WHERE profile_id='two'", [])
            .unwrap();
        assert_eq!(
            acquire_for(&db, "one", "write", "upgrade", 10).as_deref(),
            Some("upgrade")
        );
        assert!(acquire_for(&db, "two", "read", "r2-new", 10).is_none());
        assert!(acquire_for(&db, "two", "write", "w2", 10).is_none());
    }

    #[test]
    fn expired_session_cannot_renew_and_stale_release_cannot_delete_successor() {
        let db = database();
        acquire_for(&db, "one", "write", "old", 10).unwrap();
        db.execute(
            "UPDATE mail_profiles SET session_expires_at=15 WHERE id='one'",
            [],
        )
        .unwrap();
        assert!(acquire_for(&db, "one", "write", "renew", 20).is_none());
        assert!(acquire_for(&db, "two", "write", "new", 20).is_some());
        db.execute("DELETE FROM mailbox_leases WHERE address=?1 AND profile_id=?2 AND session_token=?3 AND lease_token=?4",params!["test@tmpaddr.moesegfault.dev","two","two","old"]).unwrap();
        assert_eq!(
            db.query_row(
                "SELECT lease_token FROM mailbox_leases WHERE profile_id='two'",
                [],
                |r| r.get::<_, String>(0)
            )
            .unwrap(),
            "new"
        );
    }

    #[test]
    fn read_acquisition_recovers_stronger_writer_without_downgrade_or_rotation() {
        let db = database();
        assert_eq!(
            acquire_for(&db, "one", "write", "writer", 10).as_deref(),
            Some("writer")
        );
        assert_eq!(
            acquire_for(&db, "one", "read", "read-retry", 20).as_deref(),
            Some("writer")
        );
        let mode: String = db
            .query_row(
                "SELECT mode FROM mailbox_leases WHERE profile_id='one'",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(mode, "write");
        assert!(acquire_for(&db, "two", "read", "foreign-reader", 20).is_none());
        db.execute("DELETE FROM mailbox_leases WHERE profile_id='one'", [])
            .unwrap();
        assert_eq!(
            acquire_for(&db, "one", "read", "reader", 30).as_deref(),
            Some("reader")
        );
        assert!(acquire_for(&db, "two", "read", "shared-reader", 30).is_some());
    }

    #[test]
    fn profile_release_fences_session_and_name_reuse() {
        let db = database();
        acquire_for(&db, "one", "write", "old", 10).unwrap();
        db.execute("DELETE FROM mail_profiles WHERE id='one'", [])
            .unwrap();
        db.execute("INSERT INTO mail_profiles(id,owner_iss,owner_sub,name,durable,is_user,created_at) VALUES('successor','iss','sub','one',1,0,20)",[]).unwrap();
        let remaining: i64 = db
            .query_row(
                "SELECT COUNT(*) FROM mailbox_leases WHERE profile_id='one'",
                [],
                |r| r.get(0),
            )
            .unwrap();
        assert_eq!(remaining, 0);
        assert!(acquire_for(&db, "one", "write", "old", 30).is_none());
        db.execute("UPDATE mail_profiles SET session_token='rotated',terminal_id='next',session_expires_at=100 WHERE id='two'",[]).unwrap();
        assert!(acquire_for(&db, "two", "write", "wrong-session", 30).is_none());
    }

    #[test]
    fn mailbox_generation_and_expiry_invalidate_prior_capability() {
        let db = database();
        acquire_for(&db, "one", "write", "old-generation", 10).unwrap();
        db.execute("UPDATE addresses SET generation='generation-2'", [])
            .unwrap();
        assert!(acquire_for(&db, "two", "write", "successor", 20).is_some());
        db.execute("UPDATE addresses SET expires_at=25", [])
            .unwrap();
        assert!(acquire_for(&db, "two", "write", "expired", 30).is_none());
    }

    #[test]
    fn profile_labels_and_terminal_capabilities_are_bounded() {
        assert!(valid_name("agent_12"));
        assert!(!valid_name("user' OR 1=1"));
        assert!(!valid_name(""));
        assert!(!valid_terminal("tty1"));
        assert!(valid_terminal("3ac165e6-1ab7-44af-832c-8cce66bbc281"));
    }

    #[test]
    fn deterministic_operation_schedules_preserve_the_rw_model() {
        let names = ["one", "two", "three"];
        for initial in 1_u64..=12 {
            let db = database();
            let mut seed = initial;
            let mut expires = [i64::MAX; 3];
            let mut modes: [Option<&str>; 3] = [None; 3];
            for at in 1_i64..=128 {
                seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1);
                let id = (seed as usize >> 16) % 3;
                match seed % 5 {
                    operation @ 0..=1 => {
                        let mode = if operation == 0 { "read" } else { "write" };
                        let permitted = expires[id] > at
                            && (0..3).all(|other| {
                                other == id
                                    || expires[other] <= at
                                    || modes[other].is_none()
                                    || (mode == "read" && modes[other] == Some("read"))
                            });
                        let granted =
                            acquire_for(&db, names[id], mode, &format!("token-{at}-{id}"), at)
                                .is_some();
                        assert_eq!(
                            granted, permitted,
                            "seed={initial} step={at} profile={id} mode={mode}"
                        );
                        if granted && modes[id] != Some("write") {
                            modes[id] = Some(mode);
                        }
                    }
                    2 => {
                        db.execute(
                            "DELETE FROM mailbox_leases WHERE profile_id=?1",
                            [names[id]],
                        )
                        .unwrap();
                        modes[id] = None;
                    }
                    3 => {
                        db.execute(
                            "UPDATE mail_profiles SET session_expires_at=?1 WHERE id=?2",
                            params![at, names[id]],
                        )
                        .unwrap();
                        expires[id] = at;
                    }
                    _ => {
                        if expires[id] <= at {
                            db.execute("UPDATE mail_profiles SET terminal_id=NULL,session_token=NULL,session_expires_at=NULL WHERE id=?1",[names[id]]).unwrap();
                            db.execute("UPDATE mail_profiles SET terminal_id=?1,session_token=?1,session_expires_at=?2 WHERE id=?1",params![names[id],at+8]).unwrap();
                            expires[id] = at + 8;
                            modes[id] = None;
                        }
                    }
                }
                let (holders,writers):(i64,i64)=db.query_row("SELECT COUNT(*),COALESCE(SUM(l.mode='write'),0) FROM mailbox_leases l JOIN mail_profiles p ON p.id=l.profile_id AND p.session_token=l.session_token WHERE p.session_expires_at>?1",[at],|row|Ok((row.get(0)?,row.get(1)?))).unwrap();
                assert!(
                    writers == 0 || (writers == 1 && holders == 1),
                    "seed={initial} step={at}"
                );
            }
        }
    }
}
