//! Account-level consent is independent of retained semantic projections.

use serde::Deserialize;
use worker::{Method, Request, Response};

use crate::{auth::Principal, bind_num, bind_str, database::Database, now, AppError, AppResult};

pub(crate) const MODEL: &str = crate::platform::EMBEDDING_MODEL;
const POLICY_ID: &str = "voyage4_no_training_retention_v1";

pub(crate) async fn require_enabled(database: &Database, user: &Principal) -> AppResult<i64> {
    #[derive(Deserialize)]
    struct Consent {
        generation: i64,
    }
    let row = database
        .prepare("SELECT generation FROM semantic_preferences WHERE owner_iss=?1 AND owner_sub=?2 AND enabled=1")
        .bind(&[bind_str(&user.iss), bind_str(&user.sub)])?
        .first::<Consent>(None)
        .await?
        .ok_or_else(|| AppError::conflict("semantic_disabled"))?;
    Ok(row.generation)
}

pub(crate) fn is_route(method: Method, path: &str) -> bool {
    path == "/v1/semantic" && matches!(method, Method::Get | Method::Post)
}

#[derive(Deserialize)]
struct Status {
    enabled: i64,
    generation: i64,
    pending_messages: i64,
    indexed_messages: i64,
}

pub(crate) async fn dispatch(
    req: &mut Request,
    database: &Database,
    user: &Principal,
) -> AppResult<Response> {
    if req.method() == Method::Post {
        update(req, database, user).await?;
    }
    status(database, user).await
}

async fn status(database: &Database, user: &Principal) -> AppResult<Response> {
    let sql = format!(
        "SELECT COALESCE(p.enabled,0) AS enabled,COALESCE(p.generation,0) AS generation,
         (SELECT COUNT(*) FROM embedding_work w JOIN messages m ON m.id=w.message_id
          WHERE w.owner_iss=?1 AND w.owner_sub=?2 AND m.deleted_at IS NULL AND {}) AS pending_messages,
         (SELECT COUNT(*) FROM messages m WHERE m.owner_iss=?1 AND m.owner_sub=?2
          AND m.deleted_at IS NULL AND m.embedding_json IS NOT NULL
          AND m.embedding_model=?3 AND m.embedding_dimensions=256 AND m.embedding_input_version=1
          AND m.embedding_consent_generation=p.generation AND {}) AS indexed_messages
         FROM (SELECT 1) seed LEFT JOIN semantic_preferences p ON p.owner_iss=?1 AND p.owner_sub=?2",
        crate::tmpaddr::message_filter("m"),
        crate::tmpaddr::message_filter("m"),
    );
    let row = database
        .prepare(sql)
        .bind(&[bind_str(&user.iss), bind_str(&user.sub), bind_str(MODEL)])?
        .first::<Status>(None)
        .await?
        .ok_or_else(|| AppError::conflict("semantic_state_changed"))?;
    Response::from_json(&serde_json::json!({
        "enabled":row.enabled==1,"generation":row.generation,
        "model":MODEL,"dimensions":256,"policy_id":POLICY_ID,
        "pending_messages":row.pending_messages,"indexed_messages":row.indexed_messages,
    }))
    .map_err(Into::into)
}

// The expected generation binds a browser approval to the state displayed then.
// Same-state retries are harmless; stale opposite-state requests never take effect.
const UPDATE_SQL: &str = "INSERT INTO semantic_preferences(owner_iss,owner_sub,enabled,generation)
    SELECT ?1,?2,?3,?3 WHERE EXISTS(SELECT 1 FROM mail_profiles p
        WHERE p.id=?5 AND p.owner_iss=?1 AND p.owner_sub=?2 AND p.is_user=1
        AND p.session_token=?6 AND p.session_expires_at>?7)
    AND (EXISTS(SELECT 1 FROM semantic_preferences s WHERE s.owner_iss=?1 AND s.owner_sub=?2
        AND (s.generation=?4 OR s.enabled=?3))
        OR (?4=0 AND NOT EXISTS(SELECT 1 FROM semantic_preferences s
            WHERE s.owner_iss=?1 AND s.owner_sub=?2)))
    ON CONFLICT(owner_iss,owner_sub) DO UPDATE SET enabled=excluded.enabled,
        generation=semantic_preferences.generation+(semantic_preferences.enabled!=excluded.enabled)
    RETURNING enabled,generation";

async fn update(req: &mut Request, database: &Database, user: &Principal) -> AppResult<()> {
    let profile = user
        .profile
        .as_ref()
        .filter(|p| p.is_user)
        .ok_or(AppError {
            status: 403,
            code: "user_profile_required",
        })?;
    #[derive(Deserialize)]
    #[serde(deny_unknown_fields)]
    struct Input {
        enabled: bool,
        expected_generation: i64,
        policy_id: String,
    }
    let input: Input = req
        .json()
        .await
        .map_err(|_| AppError::bad("invalid_semantic_preference"))?;
    verify_policy(&input.policy_id)?;
    if input.expected_generation < 0 {
        return Err(AppError::bad("invalid_semantic_preference"));
    }
    let updated = database
        .prepare(UPDATE_SQL)
        .bind(&[
            bind_str(&user.iss),
            bind_str(&user.sub),
            bind_num(i64::from(input.enabled)),
            bind_num(input.expected_generation),
            bind_str(&profile.profile_id),
            bind_str(&profile.session_token),
            bind_num(now()),
        ])?
        .first::<serde_json::Value>(None)
        .await?;
    if updated.is_none() {
        return Err(AppError::conflict("semantic_state_changed"));
    }
    Ok(())
}

fn verify_policy(policy_id: &str) -> AppResult<()> {
    if policy_id != POLICY_ID {
        return Err(AppError::conflict("semantic_policy_changed"));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use rusqlite::{params, Connection, OptionalExtension};

    #[test]
    fn consent_names_the_reviewed_retention_policy() {
        assert!(verify_policy("voyage4_no_training_retention_v1").is_ok());
        for old in ["", "zdr", "qwen", "voyage4_no_training_retention_v2"] {
            assert_eq!(
                verify_policy(old).unwrap_err().code,
                "semantic_policy_changed"
            );
        }
    }

    fn database() -> Connection {
        let db = Connection::open_in_memory().unwrap();
        db.execute_batch(
            "CREATE TABLE messages(id TEXT PRIMARY KEY,owner_iss TEXT,owner_sub TEXT,
                address TEXT,direction TEXT,body_text TEXT,received_at INTEGER,deleted_at INTEGER,
                embedding_json TEXT,embedding_model TEXT,embedding_dimensions INTEGER,
                mailbox_generation TEXT NOT NULL DEFAULT '');
             CREATE TABLE addresses(address TEXT,kind TEXT,generation TEXT,released_at INTEGER,
                expires_at INTEGER,state TEXT);
             CREATE TABLE send_requests(message_id TEXT,owner_iss TEXT,owner_sub TEXT,state TEXT);
             CREATE TABLE search_generations(owner_iss TEXT,owner_sub TEXT,generation INTEGER,
                PRIMARY KEY(owner_iss,owner_sub));
             CREATE TABLE search_jobs(owner_iss TEXT,owner_sub TEXT);
             CREATE TABLE mail_profiles(id TEXT,owner_iss TEXT,owner_sub TEXT,is_user INTEGER,
                session_token TEXT,session_expires_at INTEGER);",
        )
        .unwrap();
        db.execute_batch(include_str!("../migrations/0007_embedding_work.sql"))
            .unwrap();
        db.execute_batch("CREATE TRIGGER messages_outbound_projection_requeue AFTER UPDATE OF body_text ON messages BEGIN SELECT 1; END;
            INSERT INTO mail_profiles VALUES('user','iss','sub',1,'session',9999999999999);
            INSERT INTO mail_profiles VALUES('agent','iss','sub',0,'agent-session',9999999999999);").unwrap();
        db
    }

    fn insert(db: &Connection, id: &str, owner: &str) {
        db.execute(
            "INSERT INTO messages(id,owner_iss,owner_sub,address,direction,body_text,received_at)
            VALUES(?1,'iss',?2,'mail','inbound','body',0)",
            params![id, owner],
        )
        .unwrap();
    }

    fn change(db: &Connection, enabled: bool, generation: i64, profile: &str, token: &str) -> bool {
        db.query_row(
            UPDATE_SQL,
            params![
                "iss",
                "sub",
                i64::from(enabled),
                generation,
                profile,
                token,
                1
            ],
            |_| Ok(()),
        )
        .optional()
        .unwrap()
        .is_some()
    }

    #[test]
    fn migration_preserves_vectors_and_defaults_all_accounts_off() {
        let db = database();
        insert(&db, "old", "sub");
        insert(&db, "pending", "sub");
        db.execute("UPDATE messages SET embedding_json='[0.5,0.5]',embedding_model='qwen/qwen3-embedding-8b',embedding_dimensions=256,embedding_input_version=1 WHERE id='old'",[]).unwrap();
        db.execute("UPDATE embedding_work SET lease_token='before',lease_until=99 WHERE message_id='pending'",[]).unwrap();
        db.execute_batch(include_str!("../migrations/0018_semantic_consent.sql"))
            .unwrap();
        assert_eq!(
            db.query_row("SELECT COUNT(*) FROM semantic_preferences", [], |r| r
                .get::<_, i64>(0))
                .unwrap(),
            0
        );
        assert_eq!(
            db.query_row(
                "SELECT embedding_json FROM messages WHERE id='old'",
                [],
                |r| r.get::<_, String>(0)
            )
            .unwrap(),
            "[0.5,0.5]"
        );
        assert_eq!(
            db.query_row(
                "SELECT lease_token FROM embedding_work WHERE message_id='pending'",
                [],
                |r| r.get::<_, Option<String>>(0)
            )
            .unwrap(),
            None
        );
        assert_eq!(db.execute("UPDATE embedding_work SET lease_token='legacy',lease_until=99 WHERE message_id='pending'",[]).unwrap(),0);
    }

    #[test]
    fn each_enable_rebuilds_every_live_message_and_disable_keeps_vectors() {
        let db = database();
        insert(&db, "one", "sub");
        insert(&db, "foreign", "other");
        db.execute_batch(include_str!("../migrations/0018_semantic_consent.sql"))
            .unwrap();
        assert!(change(&db, true, 0, "user", "session"));
        assert_eq!(
            db.query_row(
                "SELECT consent_generation FROM embedding_work WHERE message_id='one'",
                [],
                |r| r.get::<_, i64>(0)
            )
            .unwrap(),
            1
        );
        db.execute("UPDATE messages SET embedding_json='[1]',embedding_consent_generation=1 WHERE id='one'",[]).unwrap();
        assert_eq!(
            db.query_row(
                "SELECT COUNT(*) FROM embedding_work WHERE message_id='one'",
                [],
                |r| r.get::<_, i64>(0)
            )
            .unwrap(),
            0
        );
        assert!(change(&db, false, 1, "user", "session"));
        insert(&db, "two", "sub");
        assert_eq!(
            db.query_row(
                "SELECT embedding_json FROM messages WHERE id='one'",
                [],
                |r| r.get::<_, String>(0)
            )
            .unwrap(),
            "[1]"
        );
        assert!(change(&db, true, 2, "user", "session"));
        assert_eq!(db.query_row("SELECT COUNT(*) FROM embedding_work WHERE owner_sub='sub' AND consent_generation=3",[],|r|r.get::<_,i64>(0)).unwrap(),2);
        assert_eq!(
            db.query_row(
                "SELECT consent_generation FROM embedding_work WHERE message_id='foreign'",
                [],
                |r| r.get::<_, i64>(0)
            )
            .unwrap(),
            0
        );
        // A metadata/body update must not delete rebuild work while an old vector remains.
        db.execute(
            "UPDATE messages SET embedding_json=embedding_json WHERE id='one'",
            [],
        )
        .unwrap();
        assert_eq!(
            db.query_row(
                "SELECT COUNT(*) FROM embedding_work WHERE message_id='one'",
                [],
                |r| r.get::<_, i64>(0)
            )
            .unwrap(),
            1
        );
        assert!(change(&db, true, 0, "user", "session"));
        assert_eq!(
            db.query_row("SELECT generation FROM semantic_preferences", [], |r| r
                .get::<_, i64>(0))
                .unwrap(),
            3
        );
        assert!(!change(&db, false, 0, "user", "session"));
    }

    #[test]
    fn only_live_user_session_can_change_consent_and_old_claims_never_return() {
        let db = database();
        insert(&db, "one", "sub");
        db.execute_batch(include_str!("../migrations/0018_semantic_consent.sql"))
            .unwrap();
        assert!(!change(&db, true, 0, "agent", "agent-session"));
        assert!(!change(&db, true, 0, "user", "stale"));
        assert!(change(&db, true, 0, "user", "session"));
        assert_eq!(db.execute("UPDATE embedding_work SET lease_token='legacy',lease_until=99 WHERE message_id='one'",[]).unwrap(),0);
        assert_eq!(db.execute("UPDATE embedding_work SET lease_token='new',consent_lease_token='new',lease_until=99 WHERE message_id='one'",[]).unwrap(),1);
        // Even after expiry, an old Worker cannot reuse a new Worker's consent mirror.
        assert_eq!(db.execute("UPDATE embedding_work SET lease_token='legacy-next',lease_until=199 WHERE message_id='one'",[]).unwrap(),0);
        assert!(change(&db, false, 1, "user", "session"));
        assert_eq!(
            db.query_row(
                "SELECT lease_token FROM embedding_work WHERE message_id='one'",
                [],
                |r| r.get::<_, Option<String>>(0)
            )
            .unwrap(),
            None
        );
        assert_eq!(db.execute("UPDATE embedding_work SET lease_token='new-next',consent_lease_token='new-next',lease_until=299 WHERE message_id='one'",[]).unwrap(),0);
    }
}
