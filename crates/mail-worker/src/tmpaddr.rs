//! Temporary addresses are bounded lifetimes, not reusable ownership identifiers.
//! Visibility expires synchronously; bounded maintenance removes physical content.

use serde::Deserialize;
use worker::{Env, Result};

use crate::database::Database;
use crate::maintenance::PhaseTurn;
use crate::{bind_num, bind_str, now, AppError, AppResult};

pub(crate) const LIFETIME_MS: i64 = 6 * 60 * 60_000;
pub(crate) const COOLDOWN_MS: i64 = 60 * 60_000;

pub(crate) struct Registration {
    pub kind: &'static str,
    pub generation: String,
    pub expires_at: Option<i64>,
}

pub(crate) fn registration(kind: &str) -> AppResult<Registration> {
    match kind {
        "mail" => Ok(Registration {
            kind: "mail",
            generation: String::new(),
            expires_at: None,
        }),
        "tmpaddr" => Ok(Registration {
            kind: "tmpaddr",
            generation: uuid::Uuid::new_v4().to_string(),
            expires_at: Some(now() + LIFETIME_MS),
        }),
        _ => Err(AppError::bad("invalid_address_kind")),
    }
}

/// Staging must explicitly configure its own domain; production defaults never
/// silently turn a staging mailbox into a production route.
pub(crate) fn domain(env: &Env, kind: &str) -> AppResult<String> {
    let domain = match kind {
        "mail" => env.var("MAIL_DOMAIN")?.to_string(),
        "tmpaddr" => match env.var("MAIL_TMP_DOMAIN") {
            Ok(value) => value.to_string(),
            Err(_)
                if env.var("IDENTITY_ISSUER")?.to_string()
                    == "https://identity.moesegfault.dev" =>
            {
                "tmpaddr.moesegfault.dev".into()
            }
            Err(_) => {
                return Err(AppError {
                    status: 503,
                    code: "tmpaddr_unconfigured",
                })
            }
        },
        _ => return Err(AppError::bad("invalid_address_kind")),
    };
    if !crate::valid_address(&format!("probe@{domain}")) || domain != domain.to_ascii_lowercase() {
        return Err(AppError {
            status: 503,
            code: "tmpaddr_unconfigured",
        });
    }
    Ok(domain)
}

/// Reuse is a database-guarded transition, never a caller's claim that cleanup
/// happened. Permanent names retain their original non-recycling semantics.
pub(crate) async fn prepare_registration(database: &Database, address: &str) -> AppResult<()> {
    database.prepare("DELETE FROM addresses WHERE address=?1 AND kind='tmpaddr' AND state='retired' AND cf_rule_id IS NULL AND needs_reconcile=0 AND purged_at IS NOT NULL AND cooldown_until<=?2 AND NOT EXISTS(SELECT 1 FROM messages m WHERE m.address=addresses.address) AND NOT EXISTS(SELECT 1 FROM send_requests s WHERE s.mailbox_address=addresses.address AND s.mailbox_generation=addresses.generation AND s.content_purged_at IS NULL) AND NOT EXISTS(SELECT 1 FROM storage_reservations r WHERE r.mailbox_address=addresses.address AND r.mailbox_generation=addresses.generation)")
        .bind(&[bind_str(address),bind_num(now())])?.run().await?;
    Ok(())
}

/// Fixed deadlines make idle mailbox expiration independent of daemon liveness.
/// The release trigger immediately hides content and invalidates search snapshots.
pub(crate) async fn expire(database: &Database) -> Result<()> {
    database.prepare("UPDATE addresses SET state='deleting',needs_reconcile=1,next_reconcile_at=-1 WHERE address IN (SELECT address FROM addresses WHERE kind='tmpaddr' AND released_at IS NULL AND expires_at<=?1 ORDER BY expires_at LIMIT 30)")
        .bind(&[bind_num(now())])?.run().await?;
    Ok(())
}

/// Scope this predicate to the actual messages alias; it also protects legacy
/// clients, which do not carry profile/lease headers.
pub(crate) fn message_filter(alias: &str) -> String {
    format!("NOT EXISTS(SELECT 1 FROM addresses ta WHERE ta.address={alias}.address AND ta.kind='tmpaddr' AND (ta.generation!={alias}.mailbox_generation OR ta.released_at IS NOT NULL OR ta.expires_at<=CAST(unixepoch('subsec')*1000 AS INTEGER) OR ta.state!='active'))")
}

#[derive(Deserialize)]
struct PurgeItem {
    id: String,
    r2_key: String,
}

/// Six items fit the existing Deleted phase's 65-statement allowance. R2
/// deletion precedes SQL destruction, so any failed read/write remains retryable.
/// Minimal submission commitments survive to prevent resending an unknown intent;
/// subjects, bodies, recipients and provider-event mail data do not.
pub(crate) async fn purge(env: &Env, database: &Database, turn: &mut PhaseTurn<'_>) -> Result<()> {
    let rows = database.prepare("SELECT m.id,m.r2_key FROM messages m JOIN addresses a ON a.address=m.address AND a.generation=m.mailbox_generation WHERE a.kind='tmpaddr' AND a.released_at IS NOT NULL UNION SELECT s.message_id AS id,'messages/'||s.message_id||'.zip' AS r2_key FROM send_requests s JOIN addresses a ON a.address=s.mailbox_address AND a.generation=s.mailbox_generation WHERE a.kind='tmpaddr' AND a.released_at IS NOT NULL AND s.content_purged_at IS NULL AND s.message_id IS NOT NULL UNION SELECT r.id,'messages/'||r.id||'.zip' AS r2_key FROM storage_reservations r JOIN addresses a ON a.address=r.mailbox_address AND a.generation=r.mailbox_generation WHERE a.kind='tmpaddr' AND a.released_at IS NOT NULL AND (r.tmpaddr_purged_at IS NULL OR a.released_at<=CAST(unixepoch('subsec')*1000 AS INTEGER)-3600000) LIMIT 6")
        .all().await?.results::<PurgeItem>()?;
    let bucket = env.bucket("MAIL_BODIES")?;
    for row in rows {
        let _permit = turn.admit()?;
        database.ensure_remaining(7)?;
        bucket.delete(&row.r2_key).await?;
        bucket.delete(format!("raw/{}.eml", row.id)).await?;
        database.batch(vec![
            database.prepare("UPDATE send_requests SET content_purged_at=?2,sender=NULL,envelope_json=NULL,index_projection_token=NULL,index_projection_lease_until=0 WHERE message_id=?1 AND mailbox_generation!=''")
                .bind(&[bind_str(&row.id),bind_num(now())])?,
            database.prepare("DELETE FROM provider_events WHERE local_message_id=?1").bind(&[bind_str(&row.id)])?,
            database.prepare("DELETE FROM recipient_outcomes WHERE local_message_id=?1").bind(&[bind_str(&row.id)])?,
            database.prepare("DELETE FROM message_text_chunks WHERE message_id=?1").bind(&[bind_str(&row.id)])?,
            database.prepare("DELETE FROM messages WHERE id=?1 AND mailbox_generation!=''").bind(&[bind_str(&row.id)])?,
            database.prepare("UPDATE storage_reservations SET tmpaddr_purged_at=?2 WHERE id=?1").bind(&[bind_str(&row.id),bind_num(now())])?,
            database.prepare("DELETE FROM storage_reservations WHERE id=?1 AND EXISTS(SELECT 1 FROM addresses a WHERE a.address=storage_reservations.mailbox_address AND a.generation=storage_reservations.mailbox_generation AND a.released_at<=?2)").bind(&[bind_str(&row.id),bind_num(now()-COOLDOWN_MS)])?,
        ]).await?;
    }
    database.ensure_remaining(2)?;
    database.prepare("UPDATE send_requests SET content_purged_at=?1,sender=NULL,envelope_json=NULL WHERE content_purged_at IS NULL AND message_id IS NULL AND EXISTS(SELECT 1 FROM addresses a WHERE a.address=send_requests.mailbox_address AND a.generation=send_requests.mailbox_generation AND a.kind='tmpaddr' AND a.released_at IS NOT NULL)")
        .bind(&[bind_num(now())])?.run().await?;
    database.prepare("UPDATE addresses SET purged_at=?1 WHERE kind='tmpaddr' AND released_at IS NOT NULL AND purged_at IS NULL AND NOT EXISTS(SELECT 1 FROM messages m WHERE m.address=addresses.address) AND NOT EXISTS(SELECT 1 FROM send_requests s WHERE s.mailbox_address=addresses.address AND s.mailbox_generation=addresses.generation AND s.content_purged_at IS NULL) AND NOT EXISTS(SELECT 1 FROM storage_reservations r WHERE r.mailbox_address=addresses.address AND r.mailbox_generation=addresses.generation)")
        .bind(&[bind_num(now())])?.run().await?;
    Ok(())
}

/// Bind the pre-write ledger before the first R2 write. Tombstones survive the
/// cooldown window to sweep late objects left by a crashed in-flight writer.
pub(crate) async fn track_reservation(
    database: &Database,
    id: &str,
    address: &str,
    generation: &str,
) -> AppResult<()> {
    if generation.is_empty() {
        return Ok(());
    }
    let row = database.prepare("UPDATE storage_reservations SET mailbox_address=?2,mailbox_generation=?3 WHERE id=?1 AND EXISTS(SELECT 1 FROM addresses a WHERE a.address=?2 AND a.generation=?3 AND a.owner_iss=storage_reservations.owner_iss AND a.owner_sub=storage_reservations.owner_sub AND a.kind='tmpaddr' AND a.state='active' AND a.released_at IS NULL AND a.expires_at>?4) RETURNING id")
        .bind(&[bind_str(id),bind_str(address),bind_str(generation),bind_num(now())])?
        .first::<serde_json::Value>(None).await?;
    if row.is_none() {
        return Err(AppError::conflict("mailbox_generation_expired"));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use rusqlite::{params, Connection};

    fn database() -> Connection {
        let connection = Connection::open_in_memory().unwrap();
        for migration in [
            include_str!("../migrations/0001_initial.sql"),
            include_str!("../migrations/0002_reservation_lease.sql"),
            include_str!("../migrations/0003_storage_budget.sql"),
            include_str!("../migrations/0004_storage_ledger.sql"),
            include_str!("../migrations/0005_search_jobs.sql"),
            include_str!("../migrations/0006_outbound_abuse.sql"),
            include_str!("../migrations/0007_embedding_work.sql"),
            include_str!("../migrations/0008_address_reconcile_schedule.sql"),
            include_str!("../migrations/0009_direct_role_contact.sql"),
            include_str!("../migrations/0010_accepted_projection.sql"),
            include_str!("../migrations/0011_accepted_projection_due.sql"),
            include_str!("../migrations/0012_owner_event_discovery.sql"),
            include_str!("../migrations/0013_resource_billing.sql"),
            include_str!("../migrations/0014_billing_sessions.sql"),
            include_str!("../migrations/0015_usd_resource_billing.sql"),
            include_str!("../migrations/0017_tmpaddr.sql"),
        ] {
            connection.execute_batch(migration).unwrap();
        }
        connection
    }

    fn account(connection: &Connection, plan: &str) {
        connection.execute("INSERT INTO resource_accounts(owner_iss,owner_sub,plan,included_addresses) VALUES('issuer','owner',?1,?2)",params![plan,match plan { "plus" =>5, "lite"=>3,_=>1 }]).unwrap();
        connection.execute("INSERT INTO resource_periods(owner_iss,owner_sub,period_start,period_end,accounted_at) VALUES('issuer','owner',unixepoch('now','start of month'),unixepoch('now','start of month','+1 month'),unixepoch())",[]).unwrap();
    }

    fn address(
        connection: &Connection,
        part: &str,
        kind: &str,
        slot: i64,
        generation: &str,
    ) -> rusqlite::Result<usize> {
        connection.execute("INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,state,created_at,kind,generation,expires_at) VALUES(?1,?2,'issuer','owner',?3,'active',CAST(unixepoch('subsec')*1000 AS INTEGER),?4,?5,CASE WHEN ?4='tmpaddr' THEN CAST(unixepoch('subsec')*1000 AS INTEGER)+21600000 ELSE NULL END)",params![format!("{part}@{}.moesegfault.dev",if kind=="tmpaddr" {"tmpaddr"} else {"mail"}),part,slot,kind,generation])
    }

    fn message(connection: &Connection, id: &str, generation: &str) -> rusqlite::Result<usize> {
        connection.execute("INSERT INTO messages(id,address,owner_iss,owner_sub,direction,sender,recipients_json,subject,body_text,metadata_json,received_at,has_html,has_text,attachment_count,r2_key,size_bytes,mailbox_generation) VALUES(?1,'a@tmpaddr.moesegfault.dev','issuer','owner','inbound','sender','[]','private subject','private body','{}',CAST(unixepoch('subsec')*1000 AS INTEGER),0,1,0,'messages/'||?1||'.zip',1,?2)",params![id,generation])
    }

    #[test]
    fn temporary_inclusion_is_larger_and_separate_but_storage_owner_is_shared() {
        for (plan, mail_limit, tmp_limit) in [("free", 1, 3), ("lite", 3, 6), ("plus", 5, 10)] {
            let connection = database();
            account(&connection, plan);
            for slot in 0..mail_limit {
                address(&connection, &format!("mail{slot}"), "mail", slot, "").unwrap();
            }
            for slot in 0..tmp_limit {
                address(
                    &connection,
                    &format!("tmp{slot}"),
                    "tmpaddr",
                    slot,
                    "11111111-1111-1111-1111-111111111111",
                )
                .unwrap();
            }
            let error = address(
                &connection,
                "over",
                "tmpaddr",
                0,
                "22222222-2222-2222-2222-222222222222",
            )
            .unwrap_err();
            assert!(error.to_string().contains("tmpaddr_limit"));
            let count: i64 = connection
                .query_row("SELECT address_count FROM resource_current", [], |row| {
                    row.get(0)
                })
                .unwrap();
            assert_eq!(count, mail_limit);
            connection.execute("INSERT INTO storage_reservations(id,owner_iss,owner_sub,bytes,state,created_at) VALUES('mail','issuer','owner',10,'reserved',1),('tmp','issuer','owner',20,'reserved',1)",[]).unwrap();
            let bytes: i64 = connection
                .query_row("SELECT used_bytes FROM storage_usage", [], |row| row.get(0))
                .unwrap();
            assert_eq!(bytes, 30);
        }
    }

    #[test]
    fn release_scrubs_content_and_old_generation_cannot_enter_reused_name() {
        let connection = database();
        account(&connection, "free");
        let old = "11111111-1111-1111-1111-111111111111";
        let new = "22222222-2222-2222-2222-222222222222";
        address(&connection, "a", "tmpaddr", 0, old).unwrap();
        message(&connection, "old", old).unwrap();
        assert!(message(&connection, "wrong", new).is_err());
        connection.execute("INSERT INTO search_jobs(id,owner_iss,owner_sub,request_json,state_json,state,created_at,expires_at) VALUES('search','issuer','owner','{}','{\"subject\":\"private\"}','done',0,9999999999999)",[]).unwrap();
        connection
            .execute("UPDATE addresses SET state='deleting'", [])
            .unwrap();
        let scrubbed: (String, String, Option<i64>) = connection
            .query_row(
                "SELECT subject,body_text,deleted_at FROM messages",
                [],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
            )
            .unwrap();
        assert_eq!(scrubbed.0, "");
        assert_eq!(scrubbed.1, "");
        assert!(scrubbed.2.is_some());
        let state: String = connection
            .query_row("SELECT state_json FROM search_jobs", [], |row| row.get(0))
            .unwrap();
        assert_eq!(state, "{}");
        assert!(message(&connection, "released", old).is_err());
        connection.execute("UPDATE addresses SET state='retired',cf_rule_id=NULL,needs_reconcile=0,purged_at=CAST(unixepoch('subsec')*1000 AS INTEGER)",[]).unwrap();
        assert!(connection.execute("DELETE FROM addresses", []).is_err());
        connection.execute("DELETE FROM messages", []).unwrap();
        connection
            .execute(
                "UPDATE addresses SET cooldown_until=CAST(unixepoch('subsec')*1000 AS INTEGER)-1",
                [],
            )
            .unwrap();
        connection.execute("INSERT INTO storage_reservations(id,owner_iss,owner_sub,bytes,state,created_at,mailbox_address,mailbox_generation) VALUES('late','issuer','owner',1,'reserved',1,'a@tmpaddr.moesegfault.dev',?1)",[old]).unwrap();
        assert!(connection.execute("DELETE FROM addresses", []).is_err());
        connection
            .execute("DELETE FROM storage_reservations", [])
            .unwrap();
        connection.execute("DELETE FROM addresses", []).unwrap();
        address(&connection, "a", "tmpaddr", 0, new).unwrap();
        assert!(message(&connection, "stale-writer", old).is_err());
        message(&connection, "fresh", new).unwrap();
        let query = format!(
            "SELECT COUNT(*) FROM messages m WHERE {}",
            message_filter("m")
        );
        let visible: i64 = connection.query_row(&query, [], |row| row.get(0)).unwrap();
        assert_eq!(visible, 1);
    }

    #[test]
    fn absolute_deadline_and_generation_are_database_invariants() {
        let connection = database();
        account(&connection, "free");
        address(
            &connection,
            "a",
            "tmpaddr",
            0,
            "11111111-1111-1111-1111-111111111111",
        )
        .unwrap();
        assert!(connection
            .execute("UPDATE addresses SET expires_at=expires_at+1", [])
            .is_err());
        assert!(connection
            .execute("UPDATE addresses SET generation='replacement'", [])
            .is_err());
        assert!(connection.execute("INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,state,created_at,kind,generation,expires_at) VALUES('long@tmpaddr.moesegfault.dev','long','issuer','owner',1,'active',1,'tmpaddr','22222222-2222-2222-2222-222222222222',21600002)",[]).is_err());
    }
}
