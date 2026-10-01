//! Publish accepted outbound projections without resubmitting their provider send.
//! A journal lease fences every write, including overlapping compiler revisions.
//! Publication and the terminal transition are one D1 transaction.

use wasm_bindgen::JsValue;
use worker::{D1Database, D1PreparedStatement, Error, Result};

use crate::{archive::Draft, bind_num, bind_str, outbound_metadata, text_parts};

/// Exact journal and immutable archive identity shared by HTTP and Cron recovery.
pub(crate) struct Projection<'a> {
    /// Stable delivery ID; never allocate a replacement during recovery.
    pub id: &'a str,
    /// Immutable Identity issuer owning the delivery.
    pub issuer: &'a str,
    /// Immutable Identity subject owning the delivery.
    pub subject: &'a str,
    /// Owner-scoped original idempotency key.
    pub idem: &'a str,
    /// SHA-256 commitment to the original ZIP bytes.
    pub hash: &'a str,
    /// Already-accepted provider identity; no provider call belongs in this module.
    pub provider: &'a str,
    /// Original journal timestamp, preserved across repair attempts.
    pub created_at: i64,
    /// Size of the original ZIP and its already-charged storage reservation.
    pub bytes: usize,
}

/// Outlive the platform's 15-minute invocation; a dead isolate recovers by expiry.
/// Durable leases use the platform clock, not a caller-supplied timestamp.
const LEASE_MS: i64 = 20 * 60_000;

/// The archive reservation and any legacy projection must belong to this journal.
const OWNERSHIP: &str = "EXISTS (SELECT 1 FROM storage_reservations r
        WHERE r.id=?1 AND r.owner_iss=?2 AND r.owner_sub=?3 AND r.bytes=?7)
    AND NOT EXISTS (SELECT 1 FROM messages m WHERE m.id=?1 AND (
        m.owner_iss!=?2 OR m.owner_sub!=?3 OR m.direction!='outbound'
        OR m.r2_key!=?8 OR m.storage_bytes!=?7
        OR COALESCE(json_extract(m.metadata_json,'$.message_id'),'')!=?6))";

/// Identity and live lease are checked inside each submitted SQL statement.
const JOURNAL: &str = "EXISTS (
    SELECT 1 FROM send_requests s
    WHERE s.message_id=?1 AND s.owner_iss=?2 AND s.owner_sub=?3
      AND s.idem_key=?4 AND s.payload_hash=?5 AND s.provider_id=?6
      AND s.state='accepted' AND s.index_projection_token=?9
      AND s.index_projection_lease_until>?10)";

/// Combine the two fixed predicates; values are always separate bound parameters.
fn guard() -> String {
    format!("{JOURNAL} AND {OWNERSHIP}")
}

impl Projection<'_> {
    /// Bind the common fence without interpolating any private value into SQL.
    fn bindings(&self, key: &str, token: &str) -> Vec<JsValue> {
        vec![
            bind_str(self.id),
            bind_str(self.issuer),
            bind_str(self.subject),
            bind_str(self.idem),
            bind_str(self.hash),
            bind_str(self.provider),
            bind_num(self.bytes as i64),
            bind_str(key),
            bind_str(token),
            bind_num(crate::now()),
        ]
    }
}

/// Stage deterministic UTF-8 chunks while accepted; every late statement is a
/// conditional no-op once another projector commits sent or deletion intervenes.
/// Chunks without a published message are invisible to every public reader.
async fn stage(
    db: &D1Database,
    projection: &Projection<'_>,
    key: &str,
    token: &str,
    parts: &[&str],
) -> Result<()> {
    let mut cleanup = projection.bindings(key, token);
    cleanup.push(bind_num(parts.len() as i64));
    let cleaned = db
        .prepare(format!(
            "DELETE FROM message_text_chunks
        WHERE message_id=?1 AND (chunk_index<1 OR chunk_index>=?11) AND {}
        AND NOT EXISTS (SELECT 1 FROM messages WHERE id=?1 AND deleted_at IS NOT NULL)",
            guard()
        ))
        .bind(&cleanup)?
        .run()
        .await?;
    if !cleaned.success() {
        return Err(pending());
    }
    let sql = format!(
        "INSERT INTO message_text_chunks(message_id,chunk_index,body)
        SELECT ?1,?11,?12 WHERE {}
        AND NOT EXISTS (SELECT 1 FROM messages WHERE id=?1 AND deleted_at IS NOT NULL)
        ON CONFLICT(message_id,chunk_index) DO UPDATE SET body=excluded.body",
        guard()
    );
    for (index, chunk) in parts.iter().enumerate().skip(1) {
        let mut values = projection.bindings(key, token);
        values.extend([bind_num(index as i64), bind_str(chunk)]);
        let result = db.prepare(&sql).bind(&values)?.run().await?;
        if !result.success() {
            return Err(pending());
        }
        if result.meta()?.and_then(|meta| meta.changes) != Some(1) {
            // A tombstone may still be safely terminalized by the final batch;
            // a lost journal/owner/storage fence will make that batch a no-op.
            break;
        }
    }
    Ok(())
}

/// An existing tombstone needs no text publication. Otherwise all additional
/// indices must be present exactly once; the primary key guarantees uniqueness.
fn ready() -> &'static str {
    "(EXISTS (SELECT 1 FROM messages WHERE id=?1 AND deleted_at IS NOT NULL)
      OR ((SELECT COUNT(*) FROM message_text_chunks WHERE message_id=?1)=?11
          AND NOT EXISTS (SELECT 1 FROM message_text_chunks
                          WHERE message_id=?1 AND (chunk_index<1 OR chunk_index>?11))))"
}

/// Prepare the message publication without changing an existing tombstone or
/// mutable read state. Legacy accepted rows stay hidden until this transaction.
fn message_statement(
    db: &D1Database,
    projection: &Projection<'_>,
    draft: &Draft,
    key: &str,
    token: &str,
    parts: &[&str],
) -> Result<D1PreparedStatement> {
    let mut values = projection.bindings(key, token);
    values.extend([
        bind_num(parts.len() as i64 - 1),
        bind_str(&draft.manifest.from),
        bind_str(&serde_json::to_string(&draft.manifest.to)?),
        bind_str(&draft.manifest.subject),
        bind_str(parts[0]),
        bind_str(&outbound_metadata(draft, projection.provider).to_string()),
        bind_num(projection.created_at),
        bind_num(draft.html.is_some() as i64),
        bind_num(draft.assets.len() as i64),
    ]);
    db.prepare(format!(
        "INSERT INTO messages(
        id,address,owner_iss,owner_sub,direction,sender,recipients_json,subject,
        body_text,metadata_json,received_at,is_read,has_html,has_text,
        attachment_count,r2_key,size_bytes,storage_bytes)
        SELECT ?1,?12,?2,?3,'outbound',?12,?13,?14,?15,?16,?17,1,?18,1,?19,?8,?7,?7
        WHERE {} AND {}
        ON CONFLICT(id) DO UPDATE SET body_text=excluded.body_text
        WHERE messages.deleted_at IS NULL",
        guard(),
        ready()
    ))
    .bind(&values)
}

/// Commit message visibility, storage state and terminal journal together.
/// D1 batch is transactional: failure of any statement rolls back all three.
/// A successful all-no-op batch is not evidence of publication or completion.
pub(crate) async fn publish(
    db: &D1Database,
    projection: &Projection<'_>,
    draft: &Draft,
) -> Result<()> {
    let key = format!("messages/{}.zip", projection.id);
    let token = uuid::Uuid::new_v4().to_string();
    let mut values = projection.bindings(&key, &token);
    values.push(bind_num(crate::now() + LEASE_MS));
    let claim = db
        .prepare(format!(
            "UPDATE send_requests
        SET index_projection_token=?9,index_projection_lease_until=?11
        WHERE message_id=?1 AND owner_iss=?2 AND owner_sub=?3 AND idem_key=?4
          AND payload_hash=?5 AND provider_id=?6 AND state='accepted'
          AND index_projection_lease_until<=?10 AND {OWNERSHIP}"
        ))
        .bind(&values)?
        .run()
        .await?;
    if !claim.success() {
        return Err(pending());
    }
    if claim.meta()?.and_then(|meta| meta.changes) != Some(1) {
        return finished(db, projection, &key, &token).await;
    }
    let result = publish_leased(db, projection, draft, &key, &token).await;
    if result.is_err() {
        // Release only our own token. Any in-flight stale statement subsequently
        // observes a missing/replaced token, so an uncertain error is not a resend.
        // If release itself fails, expiry retains safe bounded crash recovery.
        let _ = db
            .prepare(
                "UPDATE send_requests
            SET index_projection_token=NULL,index_projection_lease_until=0
            WHERE message_id=?1 AND owner_iss=?2 AND owner_sub=?3 AND idem_key=?4
              AND payload_hash=?5 AND provider_id=?6 AND state='accepted'
              AND index_projection_token=?9",
            )
            .bind(&projection.bindings(&key, &token)[..9])?
            .run()
            .await;
    }
    result
}

/// Finish one active lease without voluntarily exiting between batch statements.
async fn publish_leased(
    db: &D1Database,
    projection: &Projection<'_>,
    draft: &Draft,
    key: &str,
    token: &str,
) -> Result<()> {
    let parts = text_parts(&draft.text);
    stage(db, projection, key, token, &parts).await?;
    let message = message_statement(db, projection, draft, key, token, &parts)?;
    let mut values = projection.bindings(key, token);
    values.extend([bind_num(parts.len() as i64 - 1), bind_str(parts[0])]);
    let completed = format!(
        "{} AND {} AND EXISTS (
        SELECT 1 FROM messages m WHERE m.id=?1
        AND (m.deleted_at IS NOT NULL OR m.body_text=?12))",
        guard(),
        ready()
    );
    let ledger = db
        .prepare(format!(
            "UPDATE storage_reservations SET state='indexed'
        WHERE id=?1 AND {completed}"
        ))
        .bind(&values)?;
    let sent = db
        .prepare(format!(
            "UPDATE send_requests SET state='sent',index_projection_token=NULL,index_projection_lease_until=0
        WHERE message_id=?1 AND owner_iss=?2 AND owner_sub=?3 AND idem_key=?4
        AND payload_hash=?5 AND provider_id=?6 AND state='accepted'
        AND {completed} AND EXISTS (SELECT 1 FROM storage_reservations r
            WHERE r.id=?1 AND r.owner_iss=?2 AND r.owner_sub=?3
              AND r.bytes=?7 AND r.state='indexed')"
        ))
        .bind(&values)?;
    let results = db.batch(vec![message, ledger, sent]).await?;
    if results.len() != 3 || results.iter().any(|result| !result.success()) {
        return Err(pending());
    }
    if results[2].meta()?.and_then(|meta| meta.changes) == Some(1) {
        return Ok(());
    }
    finished(db, projection, key, token).await
}

/// Journal authority resolves a failed claim or an all-no-op final batch. GC may
/// have removed the user's tombstone, but sent can never authorize fresh writes.
async fn finished(
    db: &D1Database,
    projection: &Projection<'_>,
    key: &str,
    token: &str,
) -> Result<()> {
    let already_sent = db
        .prepare(
            "SELECT 1 AS sent FROM send_requests
        WHERE message_id=?1 AND owner_iss=?2 AND owner_sub=?3 AND idem_key=?4
        AND payload_hash=?5 AND provider_id=?6 AND state='sent'",
        )
        .bind(&projection.bindings(key, token)[..6])?
        .first::<serde_json::Value>(None)
        .await?
        .is_some();
    if already_sent {
        Ok(())
    } else {
        Err(pending())
    }
}

/// Return a fixed diagnostic without SQL, provider, owner or archive content.
fn pending() -> Error {
    Error::RustError("send_index_pending".into())
}
