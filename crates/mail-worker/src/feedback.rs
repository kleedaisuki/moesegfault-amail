//! Owner-scoped progressive reads of existing submission and provider journals.
//! Mail content and provider prose never become event fields or trace records.

use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use worker::{Env, Request, Response};

use crate::{
    auth::Principal, bind_num, bind_str, db, direct_role_contact_ready, iso, now, parse_date,
    stored_rejection, AppError, AppResult, Database,
};

/// Closed provider feedback vocabulary; no arbitrary reason or payload is accepted.
const KINDS: &[&str] = &[
    "deferred",
    "delivered",
    "bounced",
    "failed",
    "rejected",
    "complained",
];
/// Limit continuation age; retention may remove old history during pagination.
const CURSOR_LIFETIME_MS: i64 = 3_600_000;

/// Check only visibility, never retrieve body/metadata to authorize feedback.
/// Match ordinary message reads' deletion/projection guard and require outbound.
const OUTBOUND_VISIBLE_SQL: &str = "SELECT 1 AS visible FROM messages m WHERE m.id=?1 AND m.owner_iss=?2 AND m.owner_sub=?3 AND m.direction='outbound' AND m.deleted_at IS NULL AND NOT EXISTS (SELECT 1 FROM send_requests s WHERE s.message_id=m.id AND s.owner_iss=m.owner_iss AND s.owner_sub=m.owner_sub AND s.state='accepted')";

/// Preserve database failures as failures; only a missing visible row means false.
async fn outbound_visible(env: &Env, user: &Principal, id: &str) -> AppResult<bool> {
    #[derive(Deserialize)]
    struct Witness {
        visible: i64,
    }
    Ok(db(env)?
        .prepare(OUTBOUND_VISIBLE_SQL)
        .bind(&[bind_str(id), bind_str(&user.iss), bind_str(&user.sub)])?
        .first::<Witness>(None)
        .await?
        .is_some_and(|row| row.visible == 1))
}

/// Links reveal deeper spaces without embedding their results in every summary.
pub(crate) fn message_links(id: &str, outbound: bool) -> serde_json::Value {
    let mut links = serde_json::json!({"archive":format!("/v1/messages/{id}/archive")});
    if outbound {
        links["outcomes"] = format!("/v1/messages/{id}/outcomes").into();
        links["events"] = format!("/v1/messages/{id}/events").into();
    }
    links
}

/// Read-only submission receipt: `accepted` never means delivered or read.
#[derive(Deserialize)]
struct SendRow {
    message_id: Option<String>,
    state: String,
    created_at: i64,
    rejection_code: Option<String>,
}

/// Recover the same sending intent, including accepted sends not yet archived.
/// A missing receipt is not authorization to create a new intent or retry unknown work.
pub(crate) async fn send_receipt(
    env: &Env,
    user: &Principal,
    key: &str,
    request_id: &str,
) -> AppResult<Response> {
    uuid::Uuid::parse_str(key).map_err(|_| AppError::bad("invalid_idempotency_key"))?;
    let row = db(env)?.prepare("SELECT message_id,state,created_at,rejection_code FROM send_requests WHERE owner_iss=?1 AND owner_sub=?2 AND idem_key=?3")
        .bind(&[bind_str(&user.iss), bind_str(&user.sub), bind_str(key)])?
        .first::<SendRow>(None).await?.ok_or_else(AppError::not_found)?;
    let mut value = serde_json::json!({
        "idempotency_key":key, "id":row.message_id,
        "state":if row.state == "sent" { "accepted" } else { &row.state },
        "projection_state":match row.state.as_str() { "sent" => "archived", "accepted" => "pending", _ => "not_applicable" },
        "created_at":iso(row.created_at), "request_id":request_id,
        "interpretation":"provider_acceptance_not_delivery_confirmation"
    });
    if let Some(code) = row.rejection_code.as_deref().and_then(stored_rejection) {
        value["rejection_code"] = code.code.into();
    }
    if let Some(id) = row.message_id {
        // Deleted content stays deleted. The non-content submission receipt remains
        // available for deduplication, but cannot revive archive or event access.
        if outbound_visible(env, user, &id).await? {
            value["links"] = message_links(&id, true);
            value["links"]["message"] = format!("/v1/messages/{id}").into();
        }
    }
    Ok(Response::from_json(&value)?)
}

/// Stored risk-precedence projection, not a chronological delivery-state machine.
#[derive(Deserialize, Serialize)]
struct OutcomeRow {
    recipient: String,
    kind: String,
    occurred_at: i64,
    event_id: String,
}

/// Require the caller's undeleted, visible outbound delivery before exposing recipients.
async fn outbound_owned(env: &Env, user: &Principal, id: &str) -> AppResult<()> {
    if !outbound_visible(env, user, id).await? {
        return Err(AppError::not_found());
    }
    Ok(())
}

/// Query only known recipient outcomes. An empty result means no retained feedback,
/// not delivery, failure, permission to resend, or proof that all recipients are listed.
pub(crate) async fn outcomes(
    env: &Env,
    user: &Principal,
    id: &str,
    request_id: &str,
) -> AppResult<Response> {
    outbound_owned(env, user, id).await?;
    let rows = db(env)?.prepare("SELECT recipient,kind,occurred_at,event_id FROM recipient_outcomes WHERE local_message_id=?1 AND owner_iss=?2 AND owner_sub=?3 ORDER BY recipient LIMIT 50")
        .bind(&[bind_str(id), bind_str(&user.iss), bind_str(&user.sub)])?
        .all().await?.results::<OutcomeRow>()?;
    let outcomes = rows.into_iter().map(|row| serde_json::json!({
        "recipient":row.recipient,"kind":row.kind,"occurred_at":iso(row.occurred_at * 1000),"event_id":row.event_id
    })).collect::<Vec<_>>();
    Ok(Response::from_json(&serde_json::json!({
        "id":id,"outcomes":outcomes,"retention_days":90,
        "interpretation":"risk_precedence_provider_feedback_not_read_confirmation",
        "links":{"events":format!("/v1/messages/{id}/events")},"request_id":request_id
    }))?)
}

/// Owner/filter-bound request shape; limit may change between pages without changing scope.
#[derive(Default, Serialize)]
struct EventQuery {
    kind: Option<String>,
    since: Option<i64>,
    message_id: Option<String>,
    #[serde(skip)]
    limit: usize,
    #[serde(skip)]
    cursor: Option<String>,
}

/// Strict bounded queries prevent ambiguous duplicate or silently ignored filters.
fn event_query(req: &Request, message: Option<&str>) -> AppResult<EventQuery> {
    let mut query = EventQuery {
        limit: 20,
        message_id: message.map(str::to_owned),
        ..Default::default()
    };
    let mut seen = std::collections::HashSet::new();
    for (key, value) in req.url()?.query_pairs() {
        if value.len() > 2048 || !seen.insert(key.to_string()) {
            return Err(AppError::bad("invalid_events_query"));
        }
        match key.as_ref() {
            "kind" if KINDS.contains(&value.as_ref()) => query.kind = Some(value.into_owned()),
            "since" => {
                let rfc3339 = regex::Regex::new(
                    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$",
                )
                .map_err(|_| AppError::bad("invalid_events_query"))?;
                if !rfc3339.is_match(&value) {
                    return Err(AppError::bad("invalid_events_query"));
                }
                let at = parse_date(&value)
                    .filter(|at| *at >= 0)
                    .ok_or_else(|| AppError::bad("invalid_events_query"))?;
                // Provider journal timestamps are Unix seconds; ceil preserves
                // an inclusive RFC3339 lower bound with fractional seconds.
                query.since = Some((at + 999) / 1000);
            }
            "message_id" if message.is_none() && uuid::Uuid::parse_str(&value).is_ok() => {
                query.message_id = Some(value.into_owned());
            }
            "limit" => {
                query.limit = value
                    .parse::<usize>()
                    .ok()
                    .filter(|n| (1..=100).contains(n))
                    .ok_or_else(|| AppError::bad("invalid_events_query"))?;
            }
            "cursor" if !value.is_empty() => query.cursor = Some(value.into_owned()),
            _ => return Err(AppError::bad("invalid_events_query")),
        }
    }
    Ok(query)
}

/// Opaque continuation carries no addresses or mail content. This is a scope-binding
/// token, not an authorization credential: every database query separately checks owner.
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct EventCursor {
    version: u8,
    scope: String,
    high_water: i64,
    expires_at: i64,
    received_at: i64,
    event_id: String,
}

/// Bind a continuation to canonical filters and the authenticated immutable identity.
fn scope(query: &EventQuery, user: &Principal) -> String {
    let bytes = serde_json::to_vec(&(query, &user.iss, &user.sub)).unwrap_or_default();
    format!("{:x}", Sha256::digest(bytes))
}

/// Validate all untrusted coordinates before SQL; retained old history is not a snapshot.
fn decode_cursor(raw: &str, expected: &str, at: i64) -> AppResult<EventCursor> {
    let bad = || AppError::bad("invalid_events_cursor");
    let bytes = URL_SAFE_NO_PAD.decode(raw).map_err(|_| bad())?;
    let cursor: EventCursor = serde_json::from_slice(&bytes).map_err(|_| bad())?;
    if cursor.version != 1
        || cursor.scope != expected
        || cursor.high_water < 1
        || cursor.received_at < 0
        || cursor.event_id.is_empty()
        || cursor.event_id.len() > 512
        || cursor.expires_at > at + CURSOR_LIFETIME_MS
    {
        return Err(bad());
    }
    if cursor.expires_at <= at {
        return Err(AppError {
            status: 410,
            code: "events_cursor_expired",
        });
    }
    Ok(cursor)
}

/// Fields come only from the normalized lifecycle journal, never raw provider payloads.
#[derive(Deserialize)]
struct EventRow {
    event_id: String,
    local_message_id: String,
    recipient: String,
    kind: String,
    occurred_at: i64,
    received_at: i64,
}

/// Shared owner-scoped SQL construction keeps account discovery and message history
/// identical. Indexed filters are assembled only from this fixed allowlist.
fn event_sql(query: &EventQuery, cursor: Option<&EventCursor>) -> String {
    let mut sql = String::from("SELECT e.event_id,e.local_message_id,e.recipient,e.kind,e.occurred_at,e.received_at FROM provider_events e WHERE e.owner_iss=?1 AND e.owner_sub=?2 AND e.rowid<=?3 AND EXISTS (SELECT 1 FROM messages m WHERE m.id=e.local_message_id AND m.owner_iss=e.owner_iss AND m.owner_sub=e.owner_sub AND m.direction='outbound' AND m.deleted_at IS NULL) AND NOT EXISTS (SELECT 1 FROM send_requests s WHERE s.message_id=e.local_message_id AND s.owner_iss=e.owner_iss AND s.owner_sub=e.owner_sub AND s.state='accepted')");
    if query.kind.is_some() {
        sql.push_str(" AND e.kind=?4");
    }
    if query.message_id.is_some() {
        sql.push_str(" AND e.local_message_id=?5");
    }
    if query.since.is_some() {
        sql.push_str(" AND e.received_at>=?6");
    }
    if cursor.is_some() {
        sql.push_str(" AND (e.received_at<?7 OR (e.received_at=?7 AND e.event_id<?8))");
    }
    sql.push_str(" ORDER BY e.received_at DESC,e.event_id DESC LIMIT ?9");
    sql
}

/// Explore account changes without first knowing the changed message ID. New appends
/// are excluded during continuation under the service receipt-time/90-day retention
/// contract; retention/deletion may remove rows. Reclaimed old rowids cannot admit
/// fresh service-timestamped events behind the older keyset boundary. This is not
/// a snapshot under arbitrary SQL rewriting or a multi-month backwards clock jump.
/// Start a fresh query to observe later events; this is a bounded journal.
pub(crate) async fn events(
    req: &Request,
    env: &Env,
    user: &Principal,
    message: Option<&str>,
    request_id: &str,
) -> AppResult<Response> {
    let query = event_query(req, message)?;
    if let Some(id) = &query.message_id {
        outbound_owned(env, user, id).await?;
    }
    let hash = scope(&query, user);
    let at = now();
    let cursor = query
        .cursor
        .as_deref()
        .map(|raw| decode_cursor(raw, &hash, at))
        .transpose()?;
    let database = db(env)?;
    #[derive(Deserialize)]
    struct HighWater {
        high_water: i64,
    }
    let high_water = if let Some(cursor) = &cursor {
        cursor.high_water
    } else {
        database.prepare("SELECT COALESCE(MAX(rowid),0) AS high_water FROM provider_events WHERE owner_iss=?1 AND owner_sub=?2")
            .bind(&[bind_str(&user.iss),bind_str(&user.sub)])?
            .first::<HighWater>(None).await?.map_or(0, |row| row.high_water)
    };
    let sql = event_sql(&query, cursor.as_ref());
    let mut rows = database
        .prepare(&sql)
        .bind(&[
            bind_str(&user.iss),
            bind_str(&user.sub),
            bind_num(high_water),
            bind_str(query.kind.as_deref().unwrap_or("")),
            bind_str(query.message_id.as_deref().unwrap_or("")),
            bind_num(query.since.unwrap_or(0)),
            bind_num(cursor.as_ref().map_or(0, |c| c.received_at)),
            bind_str(cursor.as_ref().map_or("", |c| c.event_id.as_str())),
            bind_num(query.limit as i64 + 1),
        ])?
        .all()
        .await?
        .results::<EventRow>()?;
    let more = rows.len() > query.limit;
    rows.truncate(query.limit);
    let next = if more {
        rows.last().map(|last| {
            URL_SAFE_NO_PAD.encode(
                serde_json::to_vec(&EventCursor {
                    version: 1,
                    scope: hash,
                    high_water,
                    expires_at: cursor
                        .as_ref()
                        .map_or(at + CURSOR_LIFETIME_MS, |c| c.expires_at),
                    received_at: last.received_at,
                    event_id: last.event_id.clone(),
                })
                .unwrap_or_default(),
            )
        })
    } else {
        None
    };
    let events = rows.into_iter().map(|row| serde_json::json!({
        "event_id":row.event_id,"message_id":row.local_message_id,"recipient":row.recipient,
        "kind":row.kind,"occurred_at":iso(row.occurred_at * 1000),"received_at":iso(row.received_at * 1000)
    })).collect::<Vec<_>>();
    Ok(Response::from_json(&serde_json::json!({
        "events":events,"next_cursor":next,"retention_days":90,"request_id":request_id
    }))?)
}

/// Read only effective applicable public policy and this owner's quota buckets.
/// These observations are advisory, not reservations or recipient-specific authorization.
pub(crate) async fn sending_status(
    env: &Env,
    user: &Principal,
    request_id: &str,
) -> AppResult<Response> {
    let database = db(env)?;
    let policy = sending_policy(&database, user).await?;
    let allowed = policy.public_allowed;
    let at = now();
    #[derive(Deserialize)]
    struct Quota {
        kind: String,
        used: i64,
    }
    let rows = database.prepare("SELECT kind,used FROM daily_usage WHERE owner_iss=?1 AND owner_sub=?2 AND ((kind IN ('send','send_messages') AND day=?3) OR (kind='send_hour' AND day=?4))")
        .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_num(at / 86_400_000),bind_num(at / 3_600_000)])?
        .all().await?.results::<Quota>()?;
    let quota = |kind: &str, limit: i64, window: i64| {
        let used = rows
            .iter()
            .find(|row| row.kind == kind)
            .map_or(0, |row| row.used);
        serde_json::json!({"kind":kind,"used":used,"limit":limit,
            "remaining":(limit-used).max(0),"reset_at":iso((at/window+1)*window)})
    };
    Ok(Response::from_json(&serde_json::json!({
        "policy":{"state":if allowed {"allowed"} else {"held"},"code":if allowed {serde_json::Value::Null} else {"send_held".into()}},
        "canary":{"active":policy.canary_active,"new_intent_available":policy.canary_unused,"scope":"single_recipient_single_intent"},
        "quotas":[quota("send",50,86_400_000),quota("send_messages",20,86_400_000),quota("send_hour",5,3_600_000)],
        "limits":{"recipients_per_message":50,"attachments_per_message":32,"per_recipient_daily":10},
        "interpretation":"advisory_not_reservation_or_recipient_authorization",
        "links":{"events":"/v1/events","send_receipt":"/v1/sends/{idempotency_key}"},
        "request_id":request_id
    }))?)
}

/// Shared applicability snapshot, used by mutation admission and read-only discovery.
/// Operator reason text, destinations and canary keys never leave this structure.
pub(crate) struct SendingPolicy {
    /// Global switch used only for existing canary fallback semantics.
    pub(crate) global_state: Option<String>,
    /// Missing account override permits sending; a held override denies it.
    pub(crate) account_allowed: bool,
    /// Ordinary public submission requires gates and ready direct contacts too.
    pub(crate) public_allowed: bool,
    /// An applicable owner-bound temporary grant exists, not general permission.
    canary_active: bool,
    /// The one-use grant has not yet reserved a new intent.
    canary_unused: bool,
}

/// Fetch fixed policy predicates once; the send trigger remains the final atomic guard.
pub(crate) async fn sending_policy(
    database: &Database,
    user: &Principal,
) -> AppResult<SendingPolicy> {
    #[derive(Deserialize)]
    struct PolicyRow {
        global_state: Option<String>,
        account_allowed: i64,
        gates_verified: i64,
        canary_active: i64,
        canary_unused: i64,
    }
    let row = database.prepare("SELECT (SELECT state FROM send_policy WHERE scope='global' AND owner_iss='*' AND owner_sub='*') AS global_state, NOT EXISTS(SELECT 1 FROM send_policy WHERE scope='account' AND owner_iss=?1 AND owner_sub=?2 AND state!='allowed') AS account_allowed, EXISTS(SELECT 1 FROM send_release_gates WHERE id=1 AND feedback_verified=1 AND abuse_contact_verified=1 AND delivery_canary_verified=1 AND preview_reviewed=1) AS gates_verified, EXISTS(SELECT 1 FROM send_release_gates WHERE id=1 AND canary_owner_iss=?1 AND canary_owner_sub=?2 AND canary_expires_at>unixepoch() AND canary_recipient_sha256 IS NOT NULL) AS canary_active, EXISTS(SELECT 1 FROM send_release_gates WHERE id=1 AND canary_owner_iss=?1 AND canary_owner_sub=?2 AND canary_expires_at>unixepoch() AND canary_recipient_sha256 IS NOT NULL AND canary_used_by IS NULL) AS canary_unused")
        .bind(&[bind_str(&user.iss), bind_str(&user.sub)])?
        .first::<PolicyRow>(None).await?.ok_or_else(|| AppError::bad("invalid_policy_state"))?;
    let account_allowed = row.account_allowed != 0;
    let public_allowed = account_allowed
        && row.global_state.as_deref() == Some("allowed")
        && row.gates_verified != 0
        && direct_role_contact_ready(database).await;
    let canary_permitted = account_allowed && row.global_state.as_deref() == Some("held");
    Ok(SendingPolicy {
        global_state: row.global_state,
        account_allowed,
        public_allowed,
        canary_active: canary_permitted && row.canary_active != 0,
        canary_unused: canary_permitted && row.canary_unused != 0,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Canonical query binding excludes page size but never identity or filters.
    #[test]
    fn scope_binds_identity_and_filters() {
        let owner = Principal {
            iss: "issuer".into(),
            sub: "owner".into(),
        };
        let mut query = EventQuery::default();
        let hash = scope(&query, &owner);
        query.limit = 100;
        assert_eq!(hash, scope(&query, &owner));
        query.kind = Some("bounced".into());
        assert_ne!(hash, scope(&query, &owner));
        assert_ne!(
            hash,
            scope(
                &EventQuery::default(),
                &Principal {
                    iss: "issuer".into(),
                    sub: "other".into()
                }
            )
        );
    }

    /// Foreign-scope, malformed and expired continuations cannot initiate a scan.
    #[test]
    fn cursor_contract() {
        let cursor = EventCursor {
            version: 1,
            scope: "scope".into(),
            high_water: 4,
            expires_at: 1000,
            received_at: 1,
            event_id: "event".into(),
        };
        let token = URL_SAFE_NO_PAD.encode(serde_json::to_vec(&cursor).unwrap());
        assert!(decode_cursor(&token, "scope", 1).is_ok());
        assert_eq!(
            decode_cursor(&token, "foreign", 1).err().unwrap().code,
            "invalid_events_cursor"
        );
        assert_eq!(
            decode_cursor(&token, "scope", 1000).err().unwrap().code,
            "events_cursor_expired"
        );
        assert!(decode_cursor("not-json", "scope", 1).is_err());
    }

    /// Public discovery adds only links; inbound messages do not advertise send outcomes.
    #[test]
    fn links_are_progressive() {
        assert!(message_links("id", false).get("outcomes").is_none());
        assert!(message_links("id", true).get("outcomes").is_some());
    }

    /// Feedback authorization transfers one integer, independent of content size
    /// or representation, and retains owner/direction/deletion/projection guards.
    #[test]
    fn visibility_projects_no_content() {
        let db = rusqlite::Connection::open_in_memory().unwrap();
        db.execute_batch("CREATE TABLE messages(id TEXT PRIMARY KEY,owner_iss TEXT,owner_sub TEXT,direction TEXT,deleted_at INTEGER,body_text BLOB,metadata_json BLOB); CREATE TABLE send_requests(message_id TEXT,owner_iss TEXT,owner_sub TEXT,state TEXT);").unwrap();
        db.execute(
            "INSERT INTO messages VALUES('m','iss','owner','outbound',NULL,?1,X'FF')",
            [vec![0_u8; 2_200_000]],
        )
        .unwrap();
        let visible = |owner: &str| {
            let mut statement = db.prepare(OUTBOUND_VISIBLE_SQL).unwrap();
            assert_eq!(statement.column_names(), ["visible"]);
            let values = statement
                .query_map(["m", "iss", owner], |row| row.get::<_, i64>(0))
                .unwrap()
                .collect::<Result<Vec<_>, _>>()
                .unwrap();
            values
        };
        assert_eq!(visible("owner"), [1]);
        assert!(visible("foreign").is_empty());
        db.execute(
            "INSERT INTO send_requests VALUES('m','iss','owner','accepted')",
            [],
        )
        .unwrap();
        assert!(visible("owner").is_empty());
        db.execute("UPDATE send_requests SET state='sent'", [])
            .unwrap();
        assert_eq!(visible("owner"), [1]);
        db.execute("UPDATE messages SET direction='inbound'", [])
            .unwrap();
        assert!(visible("owner").is_empty());
        db.execute("UPDATE messages SET direction='outbound',deleted_at=1", [])
            .unwrap();
        assert!(visible("owner").is_empty());
        db.execute("DELETE FROM messages", []).unwrap();
        assert!(visible("owner").is_empty());
    }

    /// The exact production SQL uses covering order indexes and numbered bindings;
    /// appends cannot enter an existing fence and foreign/deleted history stays hidden.
    #[test]
    fn event_query_sql_and_indexes() {
        let db = rusqlite::Connection::open_in_memory().unwrap();
        db.execute_batch("CREATE TABLE messages(id TEXT PRIMARY KEY,owner_iss TEXT,owner_sub TEXT,direction TEXT,deleted_at INTEGER); CREATE TABLE send_requests(message_id TEXT,owner_iss TEXT,owner_sub TEXT,state TEXT); CREATE TABLE provider_events(event_id TEXT PRIMARY KEY,local_message_id TEXT,owner_iss TEXT,owner_sub TEXT,recipient TEXT,kind TEXT,occurred_at INTEGER,received_at INTEGER);").unwrap();
        db.execute_batch(include_str!("../migrations/0012_owner_event_discovery.sql"))
            .unwrap();
        db.execute(
            "INSERT INTO messages VALUES('m','iss','owner','outbound',NULL)",
            [],
        )
        .unwrap();
        let insert =
            "INSERT INTO provider_events VALUES(?1,'m','iss',?2,'recipient','delivered',10,10)";
        db.execute(insert, ["a", "owner"]).unwrap();
        db.execute(insert, ["b", "owner"]).unwrap();
        db.execute(insert, ["foreign", "other"]).unwrap();
        let mut query = EventQuery {
            limit: 1,
            ..Default::default()
        };
        let cursor = EventCursor {
            version: 1,
            scope: String::new(),
            high_water: 2,
            expires_at: 1000,
            received_at: 10,
            event_id: "b".into(),
        };
        db.execute(insert, ["c", "owner"]).unwrap();
        let sql = event_sql(&query, Some(&cursor));
        let ids = |sql: &str, kind: &str, message: &str| {
            db.prepare(sql)
                .unwrap()
                .query_map(
                    rusqlite::params!["iss", "owner", 2, kind, message, 0, 10, "b", 2],
                    |row| row.get::<_, String>(0),
                )
                .unwrap()
                .map(Result::unwrap)
                .collect::<Vec<_>>()
        };
        assert_eq!(ids(&sql, "", ""), vec!["a"]);
        query.kind = Some("delivered".into());
        let sql = event_sql(&query, Some(&cursor));
        assert_eq!(ids(&sql, "delivered", ""), vec!["a"]);
        let plan: String = db
            .prepare(&format!("EXPLAIN QUERY PLAN {sql}"))
            .unwrap()
            .query_map(
                rusqlite::params!["iss", "owner", 2, "delivered", "", 0, 10, "b", 2],
                |row| row.get::<_, String>(3),
            )
            .unwrap()
            .map(Result::unwrap)
            .collect::<Vec<_>>()
            .join(" ");
        assert!(plan.contains("provider_events_owner_kind_order"));
        assert!(!plan.contains("USE TEMP B-TREE"));
        query.message_id = Some("m".into());
        assert_eq!(
            ids(&event_sql(&query, Some(&cursor)), "delivered", "m"),
            vec!["a"]
        );
        db.execute("UPDATE messages SET deleted_at=1 WHERE id='m'", [])
            .unwrap();
        assert!(ids(&sql, "delivered", "").is_empty());
        db.execute("DELETE FROM messages WHERE id='m'", []).unwrap();
        assert!(ids(&sql, "delivered", "").is_empty());

        // Retention may reclaim every old rowid. The consumer assigns fresh
        // receipt time (100), even to an occurrence older than this page (1).
        // Descending keyset excludes it despite recycled rowid <= old fence.
        db.execute(
            "INSERT INTO messages VALUES('m','iss','owner','outbound',NULL)",
            [],
        )
        .unwrap();
        db.execute("DELETE FROM provider_events", []).unwrap();
        db.execute("INSERT INTO provider_events VALUES('fresh','m','iss','owner','recipient','delivered',1,100)", []).unwrap();
        let reused: i64 = db
            .query_row("SELECT rowid FROM provider_events", [], |row| row.get(0))
            .unwrap();
        assert!(reused <= cursor.high_water);
        assert!(ids(&sql, "delivered", "").is_empty());
    }
}
