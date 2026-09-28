//! amail mail service. / amail 邮件服务。

mod archive;
mod auth;
mod platform;

use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use subtle::ConstantTimeEq;
use wasm_bindgen::JsValue;
use worker::*;

use crate::archive::{parse_draft, Draft};
use crate::auth::Principal;

const MAX_SCAN: usize = 2000;
const RESERVED: &[&str] = &[
    "admin",
    "administrator",
    "amail",
    "moesegfault",
    "mail",
    "login",
    "identity",
    "account",
    "api",
    "auth",
    "support",
    "security",
    "postmaster",
    "abuse",
    "noreply",
    "no-reply",
    "billing",
    "status",
    "cdn",
    "www",
    "root",
    "hostmaster",
    "webmaster",
    "help",
    "contact",
];

/// Stable public error code with no secret-bearing detail. / 稳定的公开错误码，不包含秘密信息。
#[derive(Debug)]
struct AppError {
    status: u16,
    code: &'static str,
}
type AppResult<T> = std::result::Result<T, AppError>;

impl From<worker::Error> for AppError {
    fn from(_: worker::Error) -> Self {
        Self {
            status: 503,
            code: "service_unavailable",
        }
    }
}

impl AppError {
    fn bad(code: &'static str) -> Self {
        Self { status: 400, code }
    }
    fn conflict(code: &'static str) -> Self {
        Self { status: 409, code }
    }
    fn not_found() -> Self {
        Self {
            status: 404,
            code: "not_found",
        }
    }
}

/// Main API entry point; authentication precedes mailbox access. / 主 API 入口；邮箱访问始终在身份认证之后。
#[event(fetch)]
pub async fn main(req: Request, env: Env, _ctx: Context) -> Result<Response> {
    let request_id = uuid::Uuid::new_v4().to_string();
    let result = dispatch(req, env, &request_id).await;
    let mut response = match result {
        Ok(response) => response,
        Err(err) => problem(&request_id, err)?,
    };
    response
        .headers_mut()
        .set("x-amail-request-id", &request_id)?;
    response.headers_mut().set("Cache-Control", "no-store")?;
    Ok(response)
}

/// Retry missing semantic projections outside SMTP and user send critical paths. / 在 SMTP 与用户发送关键路径之外重试缺失的语义投影。
#[event(scheduled)]
pub async fn scheduled(_event: ScheduledEvent, env: Env, _ctx: ScheduleContext) {
    if let Err(_) = reconcile_addresses(&env).await {
        console_warn!("amail routing reconciliation failed");
    }
    if let Err(_) = reconcile_outbound(&env).await {
        console_warn!("amail outbound reconciliation failed");
    }
    if let Err(_) = reindex(&env).await {
        console_warn!("amail semantic index retry failed");
    }
    if let Err(_) = reconcile_storage(&env).await {
        console_warn!("amail storage ledger reconciliation failed");
    }
    if let Err(_) = garbage_collect(&env).await {
        console_warn!("amail deleted message cleanup failed");
    }
    if let Err(_) = clean_orphans(&env).await {
        console_warn!("amail orphan object cleanup failed");
    }
}

/// Finish ledger state changes after an indexed message survived an uncertain D1 response. / 在邮件索引已落盘但 D1 响应不确定时完成账本状态变更。
async fn reconcile_storage(env: &Env) -> Result<()> {
    env.d1("MAIL_DB")?.prepare("UPDATE storage_reservations SET state='indexed' WHERE state='reserved' AND EXISTS(SELECT 1 FROM messages WHERE messages.id=storage_reservations.id)")
        .run().await?;
    Ok(())
}

/// Reclaim deleted per-delivery content after D1 tombstones hide it from readers. / D1 墓碑阻止读取后，回收已删除投递的内容。
async fn garbage_collect(env: &Env) -> Result<()> {
    #[derive(Deserialize)]
    struct Deleted {
        id: String,
        r2_key: String,
    }
    let database = env.d1("MAIL_DB")?;
    let rows = database
        .prepare("SELECT id,r2_key FROM messages WHERE deleted_at IS NOT NULL LIMIT 20")
        .all()
        .await?
        .results::<Deleted>()?;
    let bucket = env.bucket("MAIL_BODIES")?;
    for row in rows {
        bucket.delete(&row.r2_key).await?;
        bucket.delete(format!("raw/{}.eml", row.id)).await?;
        database
            .prepare("DELETE FROM message_text_chunks WHERE message_id=?1")
            .bind(&[bind_str(&row.id)])?
            .run()
            .await?;
        database
            .prepare("DELETE FROM messages WHERE id=?1 AND deleted_at IS NOT NULL")
            .bind(&[bind_str(&row.id)])?
            .run()
            .await?;
        database
            .prepare("DELETE FROM storage_reservations WHERE id=?1")
            .bind(&[bind_str(&row.id)])?
            .run()
            .await?;
    }
    Ok(())
}

/// Remove old R2 objects whose pre-write ledger never reached a visible message row. / 清除预写入账本未转为可见邮件的陈旧 R2 对象。
async fn clean_orphans(env: &Env) -> Result<()> {
    #[derive(Deserialize)]
    struct Orphan {
        id: String,
    }
    #[derive(Deserialize)]
    struct SendState {
        state: String,
    }
    let database = env.d1("MAIL_DB")?;
    let rows=database.prepare("SELECT r.id FROM storage_reservations r LEFT JOIN messages m ON m.id=r.id WHERE m.id IS NULL AND r.created_at<?1 LIMIT 20")
        .bind(&[bind_num(now()-60*60_000)])?.all().await?.results::<Orphan>()?;
    let bucket = env.bucket("MAIL_BODIES")?;
    for row in rows {
        let send = database
            .prepare("SELECT state FROM send_requests WHERE message_id=?1")
            .bind(&[bind_str(&row.id)])?
            .first::<SendState>(None)
            .await?;
        if send.as_ref().is_some_and(|record| {
            matches!(record.state.as_str(), "submitting" | "unknown" | "accepted")
        }) {
            continue;
        }
        bucket.delete(format!("messages/{}.zip", row.id)).await?;
        bucket.delete(format!("raw/{}.eml", row.id)).await?;
        database
            .prepare("DELETE FROM message_text_chunks WHERE message_id=?1")
            .bind(&[bind_str(&row.id)])?
            .run()
            .await?;
        database
            .prepare("DELETE FROM storage_reservations WHERE id=?1")
            .bind(&[bind_str(&row.id)])?
            .run()
            .await?;
    }
    Ok(())
}

/// Reconcile non-atomic D1/Email Routing transitions, including orphan provider rules. / 协调非原子的 D1/邮件路由状态，包括供应商孤儿规则。
async fn reconcile_addresses(env: &Env) -> Result<()> {
    #[derive(Deserialize)]
    struct Row {
        address: String,
        state: String,
        cf_rule_id: Option<String>,
        created_at: i64,
    }
    let database = env.d1("MAIL_DB")?;
    let rows = database.prepare("SELECT address,state,cf_rule_id,created_at FROM addresses WHERE state IN ('provisioning','deleting') OR needs_reconcile=1 ORDER BY CASE WHEN state='retired' THEN 1 ELSE 0 END,created_at ASC LIMIT 30")
        .all().await?.results::<Row>()?;
    for row in rows {
        let mut ids = platform::rules_for_address(env, &row.address).await?;
        if let Some(saved) = row.cf_rule_id.clone() {
            if !ids.contains(&saved) {
                ids.push(saved);
            }
        }
        if row.state == "provisioning" {
            if let Some(first) = ids.first() {
                database.prepare("UPDATE addresses SET state='active',cf_rule_id=?1 WHERE address=?2 AND state='provisioning'")
                    .bind(&[bind_str(first),bind_str(&row.address)])?.run().await?;
                for extra in ids.iter().skip(1) {
                    let _ = platform::delete_rule(env, extra).await;
                }
            } else if row.created_at < now() - 10 * 60_000 {
                database.prepare("UPDATE addresses SET state='pending' WHERE address=?1 AND state='provisioning'")
                    .bind(&[bind_str(&row.address)])?.run().await?;
            }
            continue;
        }
        for id in ids {
            platform::delete_rule(env, &id).await?;
        }
        if row.state == "deleting" {
            database.prepare("UPDATE addresses SET state='retired',cf_rule_id=NULL,needs_reconcile=1 WHERE address=?1 AND state='deleting'")
                .bind(&[bind_str(&row.address)])?.run().await?;
        } else {
            database
                .prepare(
                    "UPDATE addresses SET needs_reconcile=0 WHERE address=?1 AND state='retired'",
                )
                .bind(&[bind_str(&row.address)])?
                .run()
                .await?;
        }
    }
    Ok(())
}

async fn reconcile_outbound(env: &Env) -> Result<()> {
    #[derive(Deserialize)]
    struct Pending {
        owner_iss: String,
        owner_sub: String,
        message_id: String,
        provider_id: String,
        created_at: i64,
    }
    let database = env.d1("MAIL_DB")?;
    database
        .prepare(
            "UPDATE send_requests SET state='preparing',reservation_started_at=NULL WHERE state='reserving' AND reservation_started_at<?1",
        )
        .bind(&[bind_num(now() - 10 * 60_000)])?
        .run()
        .await?;
    let rows = database.prepare("SELECT owner_iss,owner_sub,message_id,provider_id,created_at FROM send_requests WHERE state='accepted' AND message_id IS NOT NULL AND provider_id IS NOT NULL LIMIT 20")
        .all().await?.results::<Pending>()?;
    for row in rows {
        let key = format!("messages/{}.zip", row.message_id);
        let Some(object) = env.bucket("MAIL_BODIES")?.get(&key).execute().await? else {
            continue;
        };
        let Some(body) = object.body() else {
            continue;
        };
        let bytes = body.bytes().await?;
        let Ok(draft) = parse_draft(&bytes) else {
            continue;
        };
        let m = &draft.manifest;
        let metadata = outbound_metadata(&draft, &row.provider_id).to_string();
        let recipients = serde_json::to_string(&m.to)?;
        let first_text = store_text(&database, &row.message_id, &draft.text)
            .await
            .map_err(|_| worker::Error::RustError("reconcile_text_failed".into()))?;
        database.prepare("INSERT OR IGNORE INTO messages(id,address,owner_iss,owner_sub,direction,sender,recipients_json,subject,body_text,metadata_json,received_at,is_read,has_html,has_text,attachment_count,r2_key,size_bytes,storage_bytes) VALUES(?1,?2,?3,?4,'outbound',?5,?6,?7,?8,?9,?10,1,?11,1,?12,?13,?14,?15)")
            .bind(&[bind_str(&row.message_id),bind_str(&m.from),bind_str(&row.owner_iss),bind_str(&row.owner_sub),bind_str(&m.from),bind_str(&recipients),bind_str(&m.subject),bind_str(&first_text),bind_str(&metadata),bind_num(row.created_at),bind_num(draft.html.is_some() as i64),bind_num(draft.assets.len() as i64),bind_str(&key),bind_num(bytes.len() as i64),bind_num(bytes.len() as i64)])?.run().await?;
        mark_storage_indexed(&database, &row.message_id).await?;
        database
            .prepare(
                "UPDATE send_requests SET state='sent' WHERE message_id=?1 AND state='accepted'",
            )
            .bind(&[bind_str(&row.message_id)])?
            .run()
            .await?;
    }
    Ok(())
}

async fn reindex(env: &Env) -> Result<()> {
    #[derive(Deserialize)]
    struct Pending {
        id: String,
        subject: String,
        body_text: String,
    }
    let database = env.d1("MAIL_DB")?;
    let result = database.prepare("SELECT id,subject,body_text FROM messages WHERE embedding_json IS NULL AND deleted_at IS NULL ORDER BY received_at LIMIT 20").all().await?;
    for row in result.results::<Pending>()? {
        let source = format!("{}\n{}", row.subject, row.body_text);
        let truncated = source.get(..source.len().min(12_000)).unwrap_or(&source);
        let Ok(vector) = platform::embed(env, truncated, "search_document").await else {
            continue;
        };
        let serialized = serde_json::to_string(&vector)?;
        database.prepare("UPDATE messages SET embedding_json=?1,embedding_model='qwen/qwen3-embedding-8b',embedding_dimensions=256 WHERE id=?2 AND embedding_json IS NULL")
            .bind(&[bind_str(&serialized),bind_str(&row.id)])?.run().await?;
    }
    Ok(())
}

async fn dispatch(mut req: Request, env: Env, request_id: &str) -> AppResult<Response> {
    let path = req.path();
    if req.method() == Method::Get && path == "/health" {
        return Ok(Response::from_json(
            &serde_json::json!({"status":"ok","request_id":request_id}),
        )?);
    }
    if path == "/internal/inbound" && req.method() == Method::Post {
        return inbound(&mut req, &env, request_id).await;
    }
    let user = auth::authenticate(&req, &env).await.map_err(|_| AppError {
        status: 401,
        code: "unauthorized",
    })?;
    let segments = path.trim_matches('/').split('/').collect::<Vec<_>>();
    match (req.method(), segments.as_slice()) {
        (Method::Get, ["v1", "addresses"]) => list_addresses(&env, &user, request_id).await,
        (Method::Post, ["v1", "addresses"]) => add_address(&mut req, &env, &user, request_id).await,
        (Method::Delete, ["v1", "addresses", address]) => {
            let address = percent_encoding::percent_decode_str(address)
                .decode_utf8()
                .map_err(|_| AppError::bad("invalid_address"))?;
            delete_address(&env, &user, &address, request_id).await
        }
        (Method::Get, ["v1", "messages"]) => {
            let url = req.url()?;
            let limit = url
                .query_pairs()
                .find(|(k, _)| k == "limit")
                .and_then(|(_, v)| v.parse().ok());
            let cursor = url
                .query_pairs()
                .find(|(k, _)| k == "cursor")
                .map(|(_, v)| v.to_string());
            search(
                &env,
                &user,
                SearchRequest {
                    limit,
                    cursor,
                    ..Default::default()
                },
                request_id,
            )
            .await
        }
        (Method::Post, ["v1", "messages", "search"]) => {
            let query: SearchRequest = req
                .json()
                .await
                .map_err(|_| AppError::bad("invalid_json"))?;
            search(&env, &user, query, request_id).await
        }
        (Method::Post, ["v1", "messages", "send"]) => {
            send_message(&mut req, &env, &user, request_id).await
        }
        (Method::Get, ["v1", "messages", id]) => get_message(&env, &user, id, request_id).await,
        (Method::Get, ["v1", "messages", id, "archive"]) => get_archive(&env, &user, id).await,
        (Method::Patch, ["v1", "messages", id]) => {
            mark_message(&mut req, &env, &user, id, request_id).await
        }
        (Method::Delete, ["v1", "messages", id]) => delete_message(&env, &user, id).await,
        (Method::Post, ["v1", "telemetry"]) => telemetry(&mut req, request_id).await,
        _ => Err(AppError::not_found()),
    }
}

fn problem(request_id: &str, err: AppError) -> Result<Response> {
    let mut response = Response::from_json(&serde_json::json!({
        "type":"about:blank", "title":err.code, "status":err.status,
        "code":err.code, "detail":err.code, "request_id":request_id
    }))?
    .with_status(err.status);
    response
        .headers_mut()
        .set("Content-Type", "application/problem+json")?;
    Ok(response)
}

fn db(env: &Env) -> AppResult<D1Database> {
    Ok(env.d1("MAIL_DB")?)
}
fn bind_str(value: &str) -> JsValue {
    JsValue::from_str(value)
}
fn bind_num(value: i64) -> JsValue {
    JsValue::from_f64(value as f64)
}
fn now() -> i64 {
    js_sys::Date::now() as i64
}
fn iso(ms: i64) -> String {
    js_sys::Date::new(&JsValue::from_f64(ms as f64))
        .to_iso_string()
        .as_string()
        .unwrap_or_default()
}
fn parse_date(value: &str) -> Option<i64> {
    let ms = js_sys::Date::new(&JsValue::from_str(value)).get_time();
    if ms.is_finite() {
        Some(ms as i64)
    } else {
        None
    }
}

/// Segment body text without losing a UTF-8 boundary; each D1 value stays small. / 在 UTF-8 边界拆分正文，使每个 D1 值保持较小。
fn text_parts(text: &str) -> Vec<&str> {
    let mut parts = Vec::new();
    let mut rest = text;
    while !rest.is_empty() {
        let mut end = rest.len().min(60_000);
        while !rest.is_char_boundary(end) {
            end -= 1;
        }
        parts.push(&rest[..end]);
        rest = &rest[end..];
    }
    if parts.is_empty() {
        parts.push("");
    }
    parts
}

async fn store_text(database: &D1Database, id: &str, text: &str) -> AppResult<String> {
    if text.len() > 25 * 1024 * 1024 {
        return Err(AppError::bad("body_too_large"));
    }
    let parts = text_parts(text);
    for (index, chunk) in parts.iter().enumerate().skip(1) {
        database.prepare("INSERT OR REPLACE INTO message_text_chunks(message_id,chunk_index,body) VALUES(?1,?2,?3)")
            .bind(&[bind_str(id),bind_num(index as i64),bind_str(chunk)])?.run().await?;
    }
    Ok(parts[0].to_string())
}

async fn full_text(database: &D1Database, row: &MessageRow) -> AppResult<String> {
    #[derive(Deserialize)]
    struct Chunk {
        body: String,
    }
    let mut body = row.body_text.clone();
    let chunks = database
        .prepare("SELECT body FROM message_text_chunks WHERE message_id=?1 ORDER BY chunk_index")
        .bind(&[bind_str(&row.id)])?
        .all()
        .await?
        .results::<Chunk>()?;
    for chunk in chunks {
        body.push_str(&chunk.body);
    }
    Ok(body)
}

/// Reserve daily budget atomically, counting failed submissions conservatively. / 原子预留每日额度；失败提交也保守计入。
async fn reserve_quota(
    database: &D1Database,
    kind: &str,
    user: &Principal,
    units: i64,
    limit: i64,
) -> AppResult<()> {
    if units < 0 || units > limit {
        return Err(AppError {
            status: 429,
            code: "quota_exhausted",
        });
    }
    let day = now() / 86_400_000;
    let result = database.prepare("INSERT INTO daily_usage(kind,owner_iss,owner_sub,day,used) VALUES(?1,?2,?3,?4,?5) ON CONFLICT(kind,owner_iss,owner_sub,day) DO UPDATE SET used=used+excluded.used WHERE used+excluded.used<=?6")
        .bind(&[bind_str(kind),bind_str(&user.iss),bind_str(&user.sub),bind_num(day),bind_num(units),bind_num(limit)])?.run().await?;
    if result.meta()?.and_then(|m| m.changes).unwrap_or(0) != 1 {
        return Err(AppError {
            status: 429,
            code: "quota_exhausted",
        });
    }
    Ok(())
}

/// Atomically reserve retained bytes before any R2 write; repeat IDs never double-charge. / 在任何 R2 写入前原子预留保留字节；重复 ID 不会重复计费。
async fn reserve_storage(
    database: &D1Database,
    id: &str,
    user: &Principal,
    bytes: i64,
) -> AppResult<()> {
    #[derive(Deserialize)]
    struct Row {
        owner_iss: String,
        owner_sub: String,
        bytes: i64,
    }
    if bytes < 0 || bytes > 1024 * 1024 * 1024 {
        return Err(AppError {
            status: 429,
            code: "mailbox_full",
        });
    }
    let insert = database.prepare("INSERT OR IGNORE INTO storage_reservations(id,owner_iss,owner_sub,bytes,state,created_at) VALUES(?1,?2,?3,?4,'reserved',?5)")
        .bind(&[bind_str(id),bind_str(&user.iss),bind_str(&user.sub),bind_num(bytes),bind_num(now())])?.run().await;
    if let Err(err) = insert {
        return if err.to_string().contains("mailbox_full") {
            Err(AppError {
                status: 429,
                code: "mailbox_full",
            })
        } else {
            Err(err.into())
        };
    }
    let row = database
        .prepare("SELECT owner_iss,owner_sub,bytes FROM storage_reservations WHERE id=?1")
        .bind(&[bind_str(id)])?
        .first::<Row>(None)
        .await?
        .ok_or_else(|| AppError {
            status: 503,
            code: "storage_reservation_missing",
        })?;
    if row.owner_iss != user.iss || row.owner_sub != user.sub || row.bytes != bytes {
        return Err(AppError::conflict("storage_reservation_conflict"));
    }
    Ok(())
}

async fn mark_storage_indexed(database: &D1Database, id: &str) -> Result<()> {
    database
        .prepare("UPDATE storage_reservations SET state='indexed' WHERE id=?1")
        .bind(&[bind_str(id)])?
        .run()
        .await?;
    Ok(())
}

fn local_part(raw: &str) -> Option<String> {
    let part = raw.to_ascii_lowercase();
    if (3..=32).contains(&part.len())
        && !part.starts_with('.')
        && !part.starts_with('-')
        && !part.ends_with('.')
        && !part.ends_with('-')
        && part
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'.' || b == b'-')
        && !part.contains("..")
        && !RESERVED.contains(&part.as_str())
    {
        Some(part)
    } else {
        None
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct AddAddress {
    local_part: String,
}

#[derive(Serialize, Deserialize)]
struct AddressRow {
    address: String,
    state: String,
    created_at: i64,
    cf_rule_id: Option<String>,
}

async fn list_addresses(env: &Env, user: &Principal, request_id: &str) -> AppResult<Response> {
    let result = db(env)?.prepare("SELECT address,state,created_at,cf_rule_id FROM addresses WHERE owner_iss=?1 AND owner_sub=?2 AND state!='retired' ORDER BY created_at")
        .bind(&[bind_str(&user.iss), bind_str(&user.sub)])?.all().await?;
    let addresses = result.results::<AddressRow>()?.into_iter().map(|a| serde_json::json!({"address":a.address,"state":if a.state=="provisioning" {"pending"} else {a.state.as_str()},"created_at":iso(a.created_at)})).collect::<Vec<_>>();
    Ok(Response::from_json(
        &serde_json::json!({"addresses":addresses,"limit":10,"request_id":request_id}),
    )?)
}

async fn add_address(
    req: &mut Request,
    env: &Env,
    user: &Principal,
    request_id: &str,
) -> AppResult<Response> {
    let input: AddAddress = req
        .json()
        .await
        .map_err(|_| AppError::bad("invalid_json"))?;
    let part = local_part(&input.local_part)
        .ok_or_else(|| AppError::conflict("reserved_or_invalid_name"))?;
    let address = format!("{part}@{}", env.var("MAIL_DOMAIN")?.to_string());
    let database = db(env)?;
    let existing = database
        .prepare("SELECT address,state,created_at,cf_rule_id FROM addresses WHERE address=?1")
        .bind(&[bind_str(&address)])?
        .first::<AddressRow>(None)
        .await?;
    if let Some(row) = existing {
        if row.state == "retired" {
            return Err(AppError::conflict("address_retired"));
        }
        let mine = database.prepare("SELECT 1 AS mine FROM addresses WHERE address=?1 AND owner_iss=?2 AND owner_sub=?3")
            .bind(&[bind_str(&address),bind_str(&user.iss),bind_str(&user.sub)])?.first::<serde_json::Value>(None).await?.is_some();
        if !mine {
            return Err(AppError::conflict("address_unavailable"));
        }
        if row.state == "active" {
            return Ok(Response::from_json(
                &serde_json::json!({"address":address,"state":"active","created_at":iso(row.created_at),"request_id":request_id}),
            )?);
        }
        if row.state == "deleting" {
            return Err(AppError::conflict("address_deleting"));
        }
        if row.state == "provisioning" {
            return Ok(Response::from_json(&serde_json::json!({"address":address,"state":"pending","created_at":iso(row.created_at),"request_id":request_id}))?.with_status(202));
        }
    } else {
        #[derive(Deserialize)]
        struct CountRow {
            n: i64,
        }
        let count = database
            .prepare("SELECT COUNT(*) AS n FROM addresses WHERE state!='retired'")
            .first::<CountRow>(None)
            .await?
            .map_or(0, |r| r.n);
        if count >= 200 {
            return Err(AppError::conflict("capacity_exhausted"));
        }
        // One conditional SQLite statement allocates a free slot; a partial unique index resolves races.
        let query = "WITH slots(slot) AS (VALUES(0),(1),(2),(3),(4),(5),(6),(7),(8),(9)) INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,cf_rule_id,state,created_at) SELECT ?1,?2,?3,?4,slots.slot,NULL,'pending',?5 FROM slots WHERE NOT EXISTS (SELECT 1 FROM addresses a WHERE a.owner_iss=?3 AND a.owner_sub=?4 AND a.slot=slots.slot AND a.state!='retired') ORDER BY slots.slot LIMIT 1";
        let result = database
            .prepare(query)
            .bind(&[
                bind_str(&address),
                bind_str(&part),
                bind_str(&user.iss),
                bind_str(&user.sub),
                bind_num(now()),
            ])?
            .run()
            .await;
        if result.is_err() {
            return Err(AppError::conflict("address_unavailable"));
        }
        let owned = database.prepare("SELECT address,state,created_at,cf_rule_id FROM addresses WHERE address=?1 AND owner_iss=?2 AND owner_sub=?3")
            .bind(&[bind_str(&address),bind_str(&user.iss),bind_str(&user.sub)])?.first::<AddressRow>(None).await?;
        if owned.is_none() {
            return Err(AppError::conflict("address_limit"));
        }
    }
    let claim = database.prepare("UPDATE addresses SET state='provisioning' WHERE address=?1 AND owner_iss=?2 AND owner_sub=?3 AND state='pending'")
        .bind(&[bind_str(&address),bind_str(&user.iss),bind_str(&user.sub)])?.run().await?;
    if claim.meta()?.and_then(|m| m.changes).unwrap_or(0) != 1 {
        return Ok(Response::from_json(
            &serde_json::json!({"address":address,"state":"pending","request_id":request_id}),
        )?
        .with_status(202));
    }
    let mut existing_rules = platform::rules_for_address(env, &address).await?;
    let rule_id = if let Some(id) = existing_rules.first() {
        id.clone()
    } else {
        platform::create_rule(env, &address).await.map_err(|e| {
            if e.to_string().contains("routing_capacity_exhausted") {
                AppError::conflict("capacity_exhausted")
            } else {
                AppError {
                    status: 503,
                    code: "routing_unavailable",
                }
            }
        })?
    };
    for extra in existing_rules.drain(1..) {
        let _ = platform::delete_rule(env, &extra).await;
    }
    let transition = database.prepare("UPDATE addresses SET state='active',cf_rule_id=?1 WHERE address=?2 AND owner_iss=?3 AND owner_sub=?4 AND state='provisioning'")
        .bind(&[bind_str(&rule_id),bind_str(&address),bind_str(&user.iss),bind_str(&user.sub)])?.run().await;
    let changed = transition
        .as_ref()
        .ok()
        .and_then(|r| r.meta().ok().flatten())
        .and_then(|m| m.changes)
        .unwrap_or(0);
    if changed != 1 {
        // Persist ID even if DELETE won; cron can then complete cleanup if provider deletion fails.
        let _ = database
            .prepare("UPDATE addresses SET cf_rule_id=?1 WHERE address=?2 AND state='deleting'")
            .bind(&[bind_str(&rule_id), bind_str(&address)])?
            .run()
            .await;
        if platform::delete_rule(env, &rule_id).await.is_err() {
            let _ = database
                .prepare("UPDATE addresses SET needs_reconcile=1 WHERE address=?1")
                .bind(&[bind_str(&address)])?
                .run()
                .await;
        }
        return if changed == 0 {
            Err(AppError::conflict("address_state_changed"))
        } else {
            Err(AppError {
                status: 503,
                code: "address_provision_unknown",
            })
        };
    }
    let row = database
        .prepare("SELECT address,state,created_at,cf_rule_id FROM addresses WHERE address=?1")
        .bind(&[bind_str(&address)])?
        .first::<AddressRow>(None)
        .await?
        .ok_or_else(AppError::not_found)?;
    Ok(Response::from_json(&serde_json::json!({"address":address,"state":row.state,"created_at":iso(row.created_at),"request_id":request_id}))?.with_status(201))
}

async fn delete_address(
    env: &Env,
    user: &Principal,
    name: &str,
    request_id: &str,
) -> AppResult<Response> {
    let address = if name.contains('@') {
        name.to_ascii_lowercase()
    } else {
        format!(
            "{}@{}",
            name.to_ascii_lowercase(),
            env.var("MAIL_DOMAIN")?.to_string()
        )
    };
    let database = db(env)?;
    let row = database.prepare("SELECT address,state,created_at,cf_rule_id FROM addresses WHERE address=?1 AND owner_iss=?2 AND owner_sub=?3")
        .bind(&[bind_str(&address),bind_str(&user.iss),bind_str(&user.sub)])?.first::<AddressRow>(None).await?.ok_or_else(AppError::not_found)?;
    if row.state == "retired" {
        return Ok(Response::from_json(
            &serde_json::json!({"state":"deleting","request_id":request_id}),
        )?
        .with_status(202));
    }
    database.prepare("UPDATE addresses SET state='deleting' WHERE address=?1 AND owner_iss=?2 AND owner_sub=?3 AND state!='retired'")
        .bind(&[bind_str(&address),bind_str(&user.iss),bind_str(&user.sub)])?.run().await?;
    // Re-read after transition: creation may have installed a rule between first read and UPDATE.
    let current = database.prepare("SELECT address,state,created_at,cf_rule_id FROM addresses WHERE address=?1 AND owner_iss=?2 AND owner_sub=?3")
        .bind(&[bind_str(&address),bind_str(&user.iss),bind_str(&user.sub)])?.first::<AddressRow>(None).await?.ok_or_else(AppError::not_found)?;
    // A provisioning lease may still be creating a rule. Leave deleting until its owner or cron reconciles.
    if current.cf_rule_id.is_some() || row.state != "provisioning" {
        let mut rules = platform::rules_for_address(env, &address).await?;
        if let Some(saved) = current.cf_rule_id {
            if !rules.contains(&saved) {
                rules.push(saved);
            }
        }
        for rule_id in rules {
            platform::delete_rule(env, &rule_id).await?;
        }
        database.prepare("UPDATE addresses SET state='retired',cf_rule_id=NULL,needs_reconcile=1 WHERE address=?1 AND owner_iss=?2 AND owner_sub=?3 AND state='deleting'")
            .bind(&[bind_str(&address),bind_str(&user.iss),bind_str(&user.sub)])?.run().await?;
    }
    Ok(
        Response::from_json(&serde_json::json!({"state":"deleting","request_id":request_id}))?
            .with_status(202),
    )
}

#[derive(Clone, Serialize, Deserialize)]
struct MessageRow {
    id: String,
    address: String,
    direction: String,
    sender: String,
    recipients_json: String,
    subject: String,
    body_text: String,
    metadata_json: String,
    received_at: i64,
    is_read: i64,
    has_html: i64,
    has_text: i64,
    attachment_count: i64,
    r2_key: String,
    size_bytes: i64,
    embedding_json: Option<String>,
}

fn summary(row: &MessageRow, score: Option<f64>) -> serde_json::Value {
    let to = serde_json::from_str::<Vec<String>>(&row.recipients_json).unwrap_or_default();
    let mut value = serde_json::json!({
        "id":row.id,"mailbox":row.address,"direction":row.direction,"from":row.sender,
        "to":to,"subject":row.subject,"received_at":iso(row.received_at),"read":row.is_read != 0,
        "size_bytes":row.size_bytes,"has_attachments":row.attachment_count > 0,
        "has_html":row.has_html != 0,"has_text":row.has_text != 0,"attachment_count":row.attachment_count
    });
    if let Some(score) = score {
        value["score"] = serde_json::json!(score);
    }
    value
}

async fn one_message(env: &Env, user: &Principal, id: &str) -> AppResult<MessageRow> {
    db(env)?.prepare("SELECT id,address,direction,sender,recipients_json,subject,body_text,metadata_json,received_at,is_read,has_html,has_text,attachment_count,r2_key,size_bytes,embedding_json FROM messages WHERE id=?1 AND owner_iss=?2 AND owner_sub=?3 AND deleted_at IS NULL")
        .bind(&[bind_str(id),bind_str(&user.iss),bind_str(&user.sub)])?.first::<MessageRow>(None).await?.ok_or_else(AppError::not_found)
}

async fn get_message(
    env: &Env,
    user: &Principal,
    id: &str,
    request_id: &str,
) -> AppResult<Response> {
    let row = one_message(env, user, id).await?;
    let mut value = summary(&row, None);
    let metadata: serde_json::Value = serde_json::from_str(&row.metadata_json).unwrap_or_default();
    value["attachments"] = metadata
        .get("attachments")
        .cloned()
        .unwrap_or_else(|| serde_json::json!([]));
    value["metadata"] = metadata;
    value["request_id"] = request_id.into();
    Ok(Response::from_json(&value)?)
}

async fn get_archive(env: &Env, user: &Principal, id: &str) -> AppResult<Response> {
    let row = one_message(env, user, id).await?;
    let object = env
        .bucket("MAIL_BODIES")?
        .get(row.r2_key)
        .execute()
        .await?
        .ok_or_else(AppError::not_found)?;
    let bytes = object
        .body()
        .ok_or_else(AppError::not_found)?
        .bytes()
        .await?;
    let mut response = Response::from_bytes(bytes)?;
    response
        .headers_mut()
        .set("Content-Type", "application/zip")?;
    response.headers_mut().set(
        "Content-Disposition",
        &format!("attachment; filename=\"{}.zip\"", row.id),
    )?;
    Ok(response)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct MarkRequest {
    read: bool,
}

async fn mark_message(
    req: &mut Request,
    env: &Env,
    user: &Principal,
    id: &str,
    request_id: &str,
) -> AppResult<Response> {
    let input: MarkRequest = req
        .json()
        .await
        .map_err(|_| AppError::bad("invalid_json"))?;
    one_message(env, user, id).await?;
    db(env)?.prepare("UPDATE messages SET is_read=?1 WHERE id=?2 AND owner_iss=?3 AND owner_sub=?4 AND deleted_at IS NULL")
        .bind(&[bind_num(input.read as i64),bind_str(id),bind_str(&user.iss),bind_str(&user.sub)])?.run().await?;
    get_message(env, user, id, request_id).await
}

async fn delete_message(env: &Env, user: &Principal, id: &str) -> AppResult<Response> {
    one_message(env, user, id).await?;
    db(env)?.prepare("UPDATE messages SET deleted_at=?1 WHERE id=?2 AND owner_iss=?3 AND owner_sub=?4 AND deleted_at IS NULL")
        .bind(&[bind_num(now()),bind_str(id),bind_str(&user.iss),bind_str(&user.sub)])?.run().await?;
    Ok(Response::empty()?.with_status(204))
}

#[derive(Default, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct SearchRequest {
    mailbox: Option<String>,
    after: Option<String>,
    before: Option<String>,
    title: Option<String>,
    from: Option<String>,
    to: Option<String>,
    body: Option<String>,
    metadata: Option<std::collections::BTreeMap<String, String>>,
    semantic: Option<String>,
    regex: Option<bool>,
    case_sensitive: Option<bool>,
    read: Option<bool>,
    limit: Option<usize>,
    cursor: Option<String>,
}

#[derive(Serialize, Deserialize)]
struct SearchCursor {
    hash: String,
    offset: usize,
}

async fn search(
    env: &Env,
    user: &Principal,
    input: SearchRequest,
    request_id: &str,
) -> AppResult<Response> {
    let limit = input.limit.unwrap_or(20);
    if !(1..=100).contains(&limit) {
        return Err(AppError::bad("invalid_limit"));
    }
    let after = input
        .after
        .as_deref()
        .map(parse_date)
        .transpose_option()
        .ok_or_else(|| AppError::bad("invalid_date"))?;
    let before = input
        .before
        .as_deref()
        .map(parse_date)
        .transpose_option()
        .ok_or_else(|| AppError::bad("invalid_date"))?;
    if after.zip(before).is_some_and(|(a, b)| a >= b) {
        return Err(AppError::bad("invalid_date_range"));
    }
    let mut canonical =
        serde_json::to_value(&input).map_err(|_| AppError::bad("invalid_search"))?;
    canonical["cursor"] = serde_json::Value::Null;
    let hash = format!(
        "{:x}",
        Sha256::digest(format!("{}:{}:{}", user.iss, user.sub, canonical).as_bytes())
    );
    let offset = if let Some(cursor) = &input.cursor {
        let bytes = URL_SAFE_NO_PAD
            .decode(cursor)
            .map_err(|_| AppError::bad("invalid_cursor"))?;
        let decoded: SearchCursor =
            serde_json::from_slice(&bytes).map_err(|_| AppError::bad("invalid_cursor"))?;
        if decoded.hash != hash || decoded.offset > 100_000 {
            return Err(AppError::bad("invalid_cursor"));
        }
        decoded.offset
    } else {
        0
    };
    let matcher = SearchMatcher::new(&input)?;
    let database = db(env)?;
    let mut rows = Vec::new();
    let mut scanned = 0usize;
    let mut marker: Option<(i64, String)> = None;
    loop {
        let result = database.prepare("SELECT id,address,direction,sender,recipients_json,subject,body_text,metadata_json,received_at,is_read,has_html,has_text,attachment_count,r2_key,size_bytes,embedding_json FROM messages WHERE owner_iss=?1 AND owner_sub=?2 AND deleted_at IS NULL AND (?3 IS NULL OR address=?3) AND (?4 IS NULL OR is_read=?4) AND (?5 IS NULL OR received_at>=?5) AND (?6 IS NULL OR received_at<?6) AND (?7 IS NULL OR received_at<?7 OR (received_at=?7 AND id<?8)) ORDER BY received_at DESC,id DESC LIMIT 200")
            .bind(&[
                bind_str(&user.iss),bind_str(&user.sub),
                input.mailbox.as_deref().map(bind_str).unwrap_or(JsValue::NULL),
                input.read.map(|v|bind_num(v as i64)).unwrap_or(JsValue::NULL),
                after.map(bind_num).unwrap_or(JsValue::NULL),before.map(bind_num).unwrap_or(JsValue::NULL),
                marker.as_ref().map(|(t,_)|bind_num(*t)).unwrap_or(JsValue::NULL),
                marker.as_ref().map(|(_,id)|bind_str(id)).unwrap_or(JsValue::NULL)
            ])?.all().await?;
        let page = result.results::<MessageRow>()?;
        let page_len = page.len();
        marker = page.last().map(|row| (row.received_at, row.id.clone()));
        for mut row in page {
            if input.body.is_some() {
                row.body_text = full_text(&database, &row).await?;
            }
            if !matcher.matches(&row) {
                continue;
            }
            rows.push(row);
            if input.semantic.is_some() && rows.len() > MAX_SCAN {
                return Err(AppError {
                    status: 422,
                    code: "search_candidate_limit",
                });
            }
        }
        scanned += page_len;
        if page_len < 200 || (input.semantic.is_none() && rows.len() > offset + limit) {
            break;
        }
        if scanned >= 100_000 {
            return Err(AppError {
                status: 422,
                code: "search_scan_limit",
            });
        }
    }
    let query_vector = if let Some(term) = input.semantic.as_deref() {
        Some(
            platform::embed(env, term, "search_query")
                .await
                .map_err(|_| AppError {
                    status: 503,
                    code: "semantic_unavailable",
                })?,
        )
    } else {
        None
    };
    let mut matches = Vec::new();
    for row in rows {
        let score = if let Some(query) = &query_vector {
            let saved = row.embedding_json.as_deref().ok_or(AppError {
                status: 503,
                code: "semantic_index_incomplete",
            })?;
            let vector: Vec<f32> = serde_json::from_str(saved).map_err(|_| AppError {
                status: 503,
                code: "semantic_index_corrupt",
            })?;
            Some(cosine_exact(query, &vector).ok_or(AppError {
                status: 503,
                code: "semantic_index_corrupt",
            })?)
        } else {
            None
        };
        matches.push((row, score));
    }
    if query_vector.is_some() {
        matches.sort_by(|(a, sa), (b, sb)| {
            sb.unwrap_or_default()
                .total_cmp(&sa.unwrap_or_default())
                .then_with(|| b.received_at.cmp(&a.received_at))
                .then_with(|| b.id.cmp(&a.id))
        });
    }
    let next_cursor = if matches.len() > offset + limit {
        let cursor = SearchCursor {
            hash,
            offset: offset + limit,
        };
        Some(
            URL_SAFE_NO_PAD
                .encode(serde_json::to_vec(&cursor).map_err(|_| AppError::bad("invalid_cursor"))?),
        )
    } else {
        None
    };
    let messages = matches
        .into_iter()
        .skip(offset)
        .take(limit)
        .map(|(row, score)| summary(&row, score))
        .collect::<Vec<_>>();
    Ok(Response::from_json(
        &serde_json::json!({"messages":messages,"next_cursor":next_cursor,"request_id":request_id}),
    )?)
}

trait OptionTranspose<T> {
    fn transpose_option(self) -> Option<Option<T>>;
}
impl<T> OptionTranspose<T> for Option<Option<T>> {
    fn transpose_option(self) -> Option<Option<T>> {
        match self {
            None => Some(None),
            Some(Some(v)) => Some(Some(v)),
            Some(None) => None,
        }
    }
}

struct SearchMatcher {
    fields: Vec<(String, String)>,
    regex: bool,
    case_sensitive: bool,
    metadata: Vec<(String, String)>,
}
impl SearchMatcher {
    fn new(input: &SearchRequest) -> AppResult<Self> {
        let fields = [
            ("title", &input.title),
            ("from", &input.from),
            ("to", &input.to),
            ("body", &input.body),
        ]
        .into_iter()
        .filter_map(|(k, v)| v.as_ref().map(|s| (k.to_string(), s.clone())))
        .collect::<Vec<_>>();
        let metadata = input
            .metadata
            .clone()
            .unwrap_or_default()
            .into_iter()
            .collect::<Vec<_>>();
        for (key, value) in &metadata {
            if ![
                "message_id",
                "in_reply_to",
                "content_type",
                "attachment_name",
            ]
            .contains(&key.as_str())
                || value.len() > 256
            {
                return Err(AppError::bad("invalid_metadata_filter"));
            }
        }
        let regex = input.regex.unwrap_or(false);
        for (_, term) in &fields {
            if term.len() > 256
                || (regex
                    && regex::RegexBuilder::new(term)
                        .case_insensitive(!input.case_sensitive.unwrap_or(false))
                        .size_limit(1 << 20)
                        .build()
                        .is_err())
            {
                return Err(AppError::bad("invalid_pattern"));
            }
        }
        Ok(Self {
            fields,
            regex,
            case_sensitive: input.case_sensitive.unwrap_or(false),
            metadata,
        })
    }
    fn matches(&self, row: &MessageRow) -> bool {
        let to = row.recipients_json.as_str();
        for (field, term) in &self.fields {
            let value = match field.as_str() {
                "title" => &row.subject,
                "from" => &row.sender,
                "to" => to,
                _ => &row.body_text,
            };
            if !self.test(value, term) {
                return false;
            }
        }
        let metadata: serde_json::Value =
            serde_json::from_str(&row.metadata_json).unwrap_or_default();
        for (key, term) in &self.metadata {
            let Some(value) = metadata.get(key).and_then(|v| v.as_str()) else {
                return false;
            };
            if !self.test(value, term) {
                return false;
            }
        }
        true
    }
    fn test(&self, value: &str, term: &str) -> bool {
        if self.regex {
            return regex::RegexBuilder::new(term)
                .case_insensitive(!self.case_sensitive)
                .size_limit(1 << 20)
                .build()
                .is_ok_and(|re| re.is_match(value));
        }
        if self.case_sensitive {
            value.contains(term)
        } else {
            value.to_lowercase().contains(&term.to_lowercase())
        }
    }
}

fn valid_address(address: &str) -> bool {
    let Some((_, domain)) = address.split_once('@') else {
        return false;
    };
    address.len() <= 254
        && address.is_ascii()
        && domain.contains('.')
        && !address
            .chars()
            .any(|c| c.is_ascii_control() || c.is_whitespace() || "<>\"(),;\\".contains(c))
        && email_address::EmailAddress::is_valid(address)
}

fn validate_draft(draft: &Draft) -> AppResult<()> {
    let m = &draft.manifest;
    if !valid_address(&m.from)
        || m.to.is_empty()
        || m.to.len() + m.cc.len() + m.bcc.len() > 50
        || m.to
            .iter()
            .chain(&m.cc)
            .chain(&m.bcc)
            .any(|addr| !valid_address(addr))
        || m.reply_to
            .as_deref()
            .is_some_and(|addr| !valid_address(addr))
        || m.subject.chars().any(|c| c == '\r' || c == '\n')
        || draft.assets.len() > 32
        || m.in_reply_to
            .as_deref()
            .is_some_and(|s| !valid_message_id(s))
        || m.references.len() > 100
        || m.references.iter().any(|s| !valid_message_id(s))
    {
        return Err(AppError::bad("invalid_mail_fields"));
    }
    let estimate = draft.text.len()
        + draft.html.as_ref().map_or(0, String::len)
        + draft
            .assets
            .iter()
            .map(|(_, b)| ((b.len() + 2) / 3) * 4)
            .sum::<usize>();
    if estimate > 4_000_000 {
        return Err(AppError::bad("message_too_large"));
    }
    Ok(())
}

fn valid_message_id(id: &str) -> bool {
    id.len() <= 512
        && id.starts_with('<')
        && id.ends_with('>')
        && id.contains('@')
        && !id
            .chars()
            .any(|c| c.is_ascii_control() || c.is_whitespace())
}

async fn send_message(
    req: &mut Request,
    env: &Env,
    user: &Principal,
    request_id: &str,
) -> AppResult<Response> {
    if req.headers().get("Content-Type")?.as_deref() != Some("application/zip") {
        return Err(AppError::bad("content_type"));
    }
    let idem = req
        .headers()
        .get("Idempotency-Key")?
        .ok_or_else(|| AppError::bad("idempotency_key_required"))?;
    if uuid::Uuid::parse_str(&idem).is_err() {
        return Err(AppError::bad("idempotency_key_invalid"));
    }
    let bytes = req.bytes().await?;
    let draft = parse_draft(&bytes).map_err(|_| AppError::bad("invalid_archive"))?;
    validate_draft(&draft)?;
    let database = db(env)?;
    let mine = database.prepare("SELECT 1 AS mine FROM addresses WHERE address=?1 AND owner_iss=?2 AND owner_sub=?3 AND state='active'")
        .bind(&[bind_str(&draft.manifest.from),bind_str(&user.iss),bind_str(&user.sub)])?.first::<serde_json::Value>(None).await?.is_some();
    if !mine {
        return Err(AppError {
            status: 403,
            code: "sender_not_owned",
        });
    }
    if let Some(reply) = &draft.manifest.reply_to {
        let owned = database.prepare("SELECT 1 AS mine FROM addresses WHERE address=?1 AND owner_iss=?2 AND owner_sub=?3 AND state='active'")
            .bind(&[bind_str(reply),bind_str(&user.iss),bind_str(&user.sub)])?.first::<serde_json::Value>(None).await?.is_some();
        if !owned {
            return Err(AppError {
                status: 403,
                code: "reply_to_not_owned",
            });
        }
    }
    let payload_hash = format!("{:x}", Sha256::digest(&bytes));
    #[derive(Deserialize)]
    struct SendRow {
        payload_hash: String,
        message_id: Option<String>,
        state: String,
        quota_reserved: i64,
    }
    let existing = database.prepare("SELECT payload_hash,message_id,state,quota_reserved FROM send_requests WHERE owner_iss=?1 AND owner_sub=?2 AND idem_key=?3")
        .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(&idem)])?.first::<SendRow>(None).await?;
    let (id, quota_reserved) = if let Some(row) = existing {
        if row.payload_hash != payload_hash {
            return Err(AppError::conflict("idempotency_payload_mismatch"));
        }
        if row.state == "sent" || row.state == "accepted" {
            return Ok(Response::from_json(&serde_json::json!({"id":row.message_id,"state":"accepted","request_id":request_id}))?.with_status(202));
        }
        if row.state != "preparing" {
            return Err(AppError::conflict("send_outcome_unknown"));
        }
        (
            row.message_id
                .ok_or_else(|| AppError::conflict("send_outcome_unknown"))?,
            row.quota_reserved != 0,
        )
    } else {
        let id = uuid::Uuid::new_v4().to_string();
        database.prepare("INSERT INTO send_requests(owner_iss,owner_sub,idem_key,payload_hash,message_id,state,created_at) VALUES(?1,?2,?3,?4,?5,'preparing',?6)")
            .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(&idem),bind_str(&payload_hash),bind_str(&id),bind_num(now())])?.run().await.map_err(|_| AppError::conflict("send_in_progress"))?;
        (id, false)
    };
    if !quota_reserved {
        let claim = database.prepare("UPDATE send_requests SET state='reserving',reservation_started_at=?4 WHERE owner_iss=?1 AND owner_sub=?2 AND idem_key=?3 AND state='preparing' AND quota_reserved=0")
            .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(&idem),bind_num(now())])?.run().await?;
        if claim.meta()?.and_then(|m| m.changes).unwrap_or(0) != 1 {
            return Err(AppError::conflict("send_in_progress"));
        }
        let account = reserve_quota(&database, "send", user, 1, 100).await;
        if account.is_err() {
            let _ = database.prepare("UPDATE send_requests SET state='preparing',reservation_started_at=NULL WHERE owner_iss=?1 AND owner_sub=?2 AND idem_key=?3 AND state='reserving'")
                .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(&idem)])?.run().await;
        }
        account?;
        let global = Principal {
            iss: "_global".into(),
            sub: "_global".into(),
        };
        let global_result = reserve_quota(&database, "send_global", &global, 1, 10_000).await;
        if global_result.is_err() {
            let _ = database.prepare("UPDATE send_requests SET state='preparing',reservation_started_at=NULL WHERE owner_iss=?1 AND owner_sub=?2 AND idem_key=?3 AND state='reserving'")
                .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(&idem)])?.run().await;
        }
        global_result?;
        database.prepare("UPDATE send_requests SET quota_reserved=1,state='preparing',reservation_started_at=NULL WHERE owner_iss=?1 AND owner_sub=?2 AND idem_key=?3 AND state='reserving'")
            .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(&idem)])?.run().await?;
    }
    let r2_key = format!("messages/{id}.zip");
    reserve_storage(&database, &id, user, bytes.len() as i64).await?;
    env.bucket("MAIL_BODIES")?
        .put(&r2_key, bytes.clone())
        .execute()
        .await?;
    let transition = database.prepare("UPDATE send_requests SET state='submitting' WHERE owner_iss=?1 AND owner_sub=?2 AND idem_key=?3 AND state='preparing' AND quota_reserved=1")
        .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(&idem)])?.run().await?;
    if transition.meta()?.and_then(|m| m.changes).unwrap_or(0) != 1 {
        return Err(AppError::conflict("send_in_progress"));
    }
    let provider_id = match platform::send(env, &draft).await {
        Ok(id) => id,
        Err(_) => {
            let _ = database.prepare("UPDATE send_requests SET state='unknown' WHERE owner_iss=?1 AND owner_sub=?2 AND idem_key=?3")
                .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(&idem)])?.run().await;
            return Err(AppError {
                status: 503,
                code: "send_outcome_unknown",
            });
        }
    };
    database.prepare("UPDATE send_requests SET state='accepted',provider_id=?1 WHERE owner_iss=?2 AND owner_sub=?3 AND idem_key=?4 AND state='submitting'")
        .bind(&[bind_str(&provider_id),bind_str(&user.iss),bind_str(&user.sub),bind_str(&idem)])?.run().await?;
    let metadata = outbound_metadata(&draft, &provider_id);
    let recipients = serde_json::to_string(&draft.manifest.to)
        .map_err(|_| AppError::bad("invalid_mail_fields"))?;
    let first_text = store_text(&database, &id, &draft.text).await?;
    let inserted = database.prepare("INSERT INTO messages(id,address,owner_iss,owner_sub,direction,sender,recipients_json,subject,body_text,metadata_json,received_at,is_read,has_html,has_text,attachment_count,r2_key,size_bytes,storage_bytes,embedding_json,embedding_model,embedding_dimensions) VALUES(?1,?2,?3,?4,'outbound',?5,?6,?7,?8,?9,?10,1,?11,1,?12,?13,?14,?15,?16,?17,?18)")
        .bind(&[bind_str(&id),bind_str(&draft.manifest.from),bind_str(&user.iss),bind_str(&user.sub),bind_str(&draft.manifest.from),bind_str(&recipients),bind_str(&draft.manifest.subject),bind_str(&first_text),bind_str(&metadata.to_string()),bind_num(now()),bind_num(draft.html.is_some() as i64),bind_num(draft.assets.len() as i64),bind_str(&r2_key),bind_num(bytes.len() as i64),bind_num(bytes.len() as i64),JsValue::NULL,JsValue::NULL,JsValue::NULL])?.run().await;
    if inserted.is_err() {
        return Err(AppError {
            status: 503,
            code: "send_index_pending",
        });
    }
    if mark_storage_indexed(&database, &id).await.is_err() {
        console_warn!("amail storage ledger state deferred");
    }
    database.prepare("UPDATE send_requests SET state='sent' WHERE owner_iss=?1 AND owner_sub=?2 AND idem_key=?3")
        .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(&idem)])?.run().await?;
    Ok(Response::from_json(
        &serde_json::json!({"id":id,"state":"accepted","request_id":request_id}),
    )?
    .with_status(202))
}

fn outbound_metadata(draft: &Draft, provider_id: &str) -> serde_json::Value {
    serde_json::json!({
        "message_id":provider_id,"in_reply_to":draft.manifest.in_reply_to,
        "content_type":if draft.html.is_some() {"multipart/alternative"} else {"text/plain"},
        "attachment_name":draft.assets.iter().filter_map(|(m,_)|m.filename.as_deref()).collect::<Vec<_>>().join(" "),
        "attachments":draft.assets.iter().map(|(m,_)|m).collect::<Vec<_>>()
    })
}

async fn inbound(req: &mut Request, env: &Env, request_id: &str) -> AppResult<Response> {
    let provided = req
        .headers()
        .get("x-amail-ingress-secret")?
        .unwrap_or_default();
    let expected = env.secret("INGRESS_SECRET")?.to_string();
    if provided.len() < 32 || provided.as_bytes().ct_eq(expected.as_bytes()).unwrap_u8() != 1 {
        return Err(AppError {
            status: 403,
            code: "forbidden",
        });
    }
    let envelope_to = req
        .headers()
        .get("x-amail-envelope-to")?
        .unwrap_or_default()
        .to_ascii_lowercase();
    let raw = req.bytes().await?;
    let trace = req.headers().get("traceparent")?.unwrap_or_default();
    if trace.len() == 55
        && trace.starts_with("00-")
        && trace.chars().all(|c| c.is_ascii_hexdigit() || c == '-')
    {
        let bucket = if raw.is_empty() {
            0
        } else {
            1u64 << (usize::BITS - (raw.len() - 1).leading_zeros()).min(30)
        };
        console_log!(
            "amail.inbound traceparent={} bytes_bucket={}",
            trace,
            bucket
        );
    }
    if raw.is_empty() || raw.len() > 25 * 1024 * 1024 {
        return Err(AppError::bad("inbound_size"));
    }
    let database = db(env)?;
    #[derive(Deserialize)]
    struct Owner {
        owner_iss: String,
        owner_sub: String,
    }
    let owner = database
        .prepare("SELECT owner_iss,owner_sub FROM addresses WHERE address=?1 AND state='active'")
        .bind(&[bind_str(&envelope_to)])?
        .first::<Owner>(None)
        .await?
        .ok_or_else(AppError::not_found)?;
    let id = uuid::Uuid::new_v4().to_string();
    let received_at = now();
    let (archive, sender, subject, to, text, has_html, has_text, metadata) =
        archive::inbound_archive(&raw, &id, &iso(received_at))
            .map_err(|_| AppError::bad("invalid_mime"))?;
    if archive.len() > 25 * 1024 * 1024 {
        return Err(AppError::bad("archive_size"));
    }
    let user = Principal {
        iss: owner.owner_iss.clone(),
        sub: owner.owner_sub.clone(),
    };
    let storage_bytes = (raw.len() + archive.len()) as i64;
    reserve_storage(&database, &id, &user, storage_bytes).await?;
    reserve_quota(
        &database,
        "inbound_bytes",
        &user,
        raw.len() as i64,
        100 * 1024 * 1024,
    )
    .await?;
    let r2_key = format!("messages/{id}.zip");
    // Preserve original MIME separately for forensic recovery; never expose raw headers to the agent archive.
    env.bucket("MAIL_BODIES")?
        .put(format!("raw/{id}.eml"), raw)
        .execute()
        .await?;
    env.bucket("MAIL_BODIES")?
        .put(&r2_key, archive.clone())
        .execute()
        .await?;
    let attachments = metadata
        .get("attachments")
        .and_then(|v| v.as_array())
        .map_or(0, Vec::len);
    let metadata = metadata.to_string();
    let first_text = store_text(&database, &id, &text).await?;
    database.prepare("INSERT INTO messages(id,address,owner_iss,owner_sub,direction,sender,recipients_json,subject,body_text,metadata_json,received_at,is_read,has_html,has_text,attachment_count,r2_key,size_bytes,storage_bytes,embedding_json,embedding_model,embedding_dimensions) VALUES(?1,?2,?3,?4,'inbound',?5,?6,?7,?8,?9,?10,0,?11,?12,?13,?14,?15,?16,?17,?18,?19)")
        .bind(&[bind_str(&id),bind_str(&envelope_to),bind_str(&owner.owner_iss),bind_str(&owner.owner_sub),bind_str(&sender),bind_str(&serde_json::to_string(&to).unwrap_or_default()),bind_str(&subject),bind_str(&first_text),bind_str(&metadata),bind_num(received_at),bind_num(has_html as i64),bind_num(has_text as i64),bind_num(attachments as i64),bind_str(&r2_key),bind_num(archive.len() as i64),bind_num(storage_bytes),JsValue::NULL,JsValue::NULL,JsValue::NULL])?.run().await?;
    if mark_storage_indexed(&database, &id).await.is_err() {
        console_warn!("amail storage ledger state deferred");
    }
    Ok(
        Response::from_json(&serde_json::json!({"id":id,"request_id":request_id}))?
            .with_status(201),
    )
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct TelemetryEvent {
    operation: String,
    status: u16,
    duration_ms: u64,
    bytes_bucket: u64,
    trace_id: String,
    correlation_id: Option<String>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct TelemetryBatch {
    events: Vec<TelemetryEvent>,
}

async fn telemetry(req: &mut Request, request_id: &str) -> AppResult<Response> {
    let batch: TelemetryBatch = req
        .json()
        .await
        .map_err(|_| AppError::bad("invalid_json"))?;
    const OPS: &[&str] = &[
        "addresses.list",
        "addresses.add",
        "addresses.delete",
        "messages.list",
        "messages.search",
        "messages.get",
        "messages.archive",
        "messages.mark",
        "messages.delete",
        "messages.send",
    ];
    if batch.events.len() > 100
        || batch.events.iter().any(|e| {
            !OPS.contains(&e.operation.as_str())
                || e.trace_id.len() > 64
                || !e
                    .trace_id
                    .chars()
                    .all(|c| c.is_ascii_hexdigit() || c == '-')
                || e.correlation_id.as_ref().is_some_and(|v| {
                    v.len() > 64 || !v.chars().all(|c| c.is_ascii_alphanumeric() || c == '-')
                })
                || e.duration_ms > 3_600_000
                || e.bytes_bucket > (1 << 31)
        })
    {
        return Err(AppError::bad("invalid_telemetry"));
    }
    for event in &batch.events {
        console_log!(
            "amail.telemetry operation={} status={} duration_ms={} bytes_bucket={} trace_id={}",
            event.operation,
            event.status,
            event.duration_ms,
            event.bytes_bucket,
            event.trace_id
        );
    }
    Ok(Response::from_json(
        &serde_json::json!({"accepted":batch.events.len(),"request_id":request_id}),
    )?
    .with_status(202))
}

/// Compute exact cosine over all 256 persisted f32 coordinates, including their actual norms. / 基于持久化的全部 256 个 f32 坐标及其实际范数计算精确余弦。
fn cosine_exact(left: &[f32], right: &[f32]) -> Option<f64> {
    if left.len() != 256 || right.len() != 256 || left.iter().chain(right).any(|x| !x.is_finite()) {
        return None;
    }
    let mut dot = 0.0f64;
    let mut left_norm = 0.0f64;
    let mut right_norm = 0.0f64;
    for (a, b) in left.iter().zip(right) {
        let a = *a as f64;
        let b = *b as f64;
        dot += a * b;
        left_norm += a * a;
        right_norm += b * b;
    }
    let denominator = (left_norm * right_norm).sqrt();
    if denominator <= 0.0 || !denominator.is_finite() {
        return None;
    }
    Some((dot / denominator).clamp(-1.0, 1.0))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// User names are canonical and service names are never allocated. / 用户名规范化，服务名永不分配。
    #[test]
    fn address_policy() {
        assert_eq!(local_part("Alice"), Some("alice".into()));
        for name in [
            "admin",
            "MOESEGFAULT",
            "mail",
            "login",
            "security",
            "abuse",
            "a",
            "a..b",
            "-bad",
        ] {
            assert!(local_part(name).is_none(), "{name}");
        }
    }

    /// UTF-8 segmentation is lossless and respects D1 row sizes. / UTF-8 分段无损且符合 D1 单行大小约束。
    #[test]
    fn text_segments_roundtrip() {
        let body = "邮".repeat(50_000);
        let chunks = text_parts(&body);
        assert!(chunks.iter().all(|part| part.len() <= 60_000));
        assert_eq!(chunks.concat(), body);
    }

    /// Exact cosine rejects dimensions and nonfinite coordinates. / 精确余弦拒绝维度错误及非有限坐标。
    #[test]
    fn exact_cosine_256() {
        let mut a = vec![0.0f32; 256];
        let mut b = a.clone();
        a[0] = 1.0;
        b[1] = 1.0;
        assert_eq!(cosine_exact(&a, &b), Some(0.0));
        assert_eq!(cosine_exact(&a, &a), Some(1.0));
        assert_eq!(cosine_exact(&a[..255], &b), None);
        b[5] = f32::NAN;
        assert_eq!(cosine_exact(&a, &b), None);
        assert_eq!(cosine_exact(&vec![0.0; 256], &a), None);
        let mut scaled = a.clone();
        scaled[0] = 2.0;
        assert_eq!(cosine_exact(&a, &scaled), Some(1.0));
        let mut query = a.clone();
        query[1] = 0.02;
        let mut near = a.clone();
        near[1] = 0.019;
        assert!(cosine_exact(&query, &near).unwrap() > cosine_exact(&query, &a).unwrap());
    }

    /// Server filters remain exact for regex, case and metadata. / 服务端正则、大小写及元数据筛选保持精确。
    #[test]
    fn matcher_exactness() {
        let row = MessageRow {
            id: "1".into(),
            address: "a@mail.moesegfault.dev".into(),
            direction: "inbound".into(),
            sender: "From@Example.org".into(),
            recipients_json: "[]".into(),
            subject: "Release 42".into(),
            body_text: "Rollback safely".into(),
            metadata_json: r#"{"message_id":"<abc@example.org>"}"#.into(),
            received_at: 0,
            is_read: 0,
            has_html: 0,
            has_text: 1,
            attachment_count: 0,
            r2_key: "k".into(),
            size_bytes: 1,
            embedding_json: None,
        };
        let request = SearchRequest {
            title: Some("release [0-9]+".into()),
            metadata: Some([("message_id".into(), "abc@".into())].into()),
            regex: Some(true),
            case_sensitive: Some(false),
            ..Default::default()
        };
        assert!(SearchMatcher::new(&request).unwrap().matches(&row));
        let strict = SearchRequest {
            case_sensitive: Some(true),
            ..request
        };
        assert!(!SearchMatcher::new(&strict).unwrap().matches(&row));
    }

    /// A quota-denied preparing request cannot transition to provider submission on retry. / 额度拒绝后的预备请求重试不得进入供应商提交态。
    #[test]
    fn quota_and_idempotency_gate() {
        let db = rusqlite::Connection::open_in_memory().unwrap();
        db.execute_batch(include_str!("../migrations/0001_initial.sql"))
            .unwrap();
        db.execute_batch(include_str!("../migrations/0002_reservation_lease.sql"))
            .unwrap();
        db.execute("INSERT INTO send_requests(owner_iss,owner_sub,idem_key,payload_hash,message_id,state,created_at) VALUES('i','s','k','h','m','preparing',0)",[]).unwrap();
        assert_eq!(db.execute("UPDATE send_requests SET state='submitting' WHERE idem_key='k' AND state='preparing' AND quota_reserved=1",[]).unwrap(),0);
        db.execute(
            "UPDATE send_requests SET quota_reserved=1 WHERE idem_key='k'",
            [],
        )
        .unwrap();
        assert_eq!(db.execute("UPDATE send_requests SET state='submitting' WHERE idem_key='k' AND state='preparing' AND quota_reserved=1",[]).unwrap(),1);
        assert_eq!(db.execute("UPDATE send_requests SET state='submitting' WHERE idem_key='k' AND state='preparing' AND quota_reserved=1",[]).unwrap(),0);
    }

    /// Lease cleanup follows claim time, not the age of the original request. / 租约清理依据认领时间，而非原请求年龄。
    #[test]
    fn quota_lease_uses_claim_time() {
        let db = rusqlite::Connection::open_in_memory().unwrap();
        db.execute_batch(include_str!("../migrations/0001_initial.sql"))
            .unwrap();
        db.execute_batch(include_str!("../migrations/0002_reservation_lease.sql"))
            .unwrap();
        db.execute("INSERT INTO send_requests(owner_iss,owner_sub,idem_key,payload_hash,message_id,state,created_at,reservation_started_at) VALUES('i','s','k','h','m','reserving',0,1000)",[]).unwrap();
        assert_eq!(db.execute("UPDATE send_requests SET state='preparing' WHERE state='reserving' AND reservation_started_at<500",[]).unwrap(),0);
        assert_eq!(db.execute("UPDATE send_requests SET state='preparing' WHERE state='reserving' AND reservation_started_at<1500",[]).unwrap(),1);
    }

    /// The trigger reserves atomically, rejects over-cap writes, and releases after cleanup. / 触发器原子预留，拒绝超额写入，并在清理后释放额度。
    #[test]
    fn storage_ledger_cap_and_recovery() {
        let db = rusqlite::Connection::open_in_memory().unwrap();
        for sql in [
            include_str!("../migrations/0001_initial.sql"),
            include_str!("../migrations/0002_reservation_lease.sql"),
            include_str!("../migrations/0003_storage_budget.sql"),
            include_str!("../migrations/0004_storage_ledger.sql"),
        ] {
            db.execute_batch(sql).unwrap();
        }
        db.execute("INSERT INTO storage_reservations(id,owner_iss,owner_sub,bytes,state,created_at) VALUES('one','iss','sub',1073741824,'reserved',0)",[]).unwrap();
        db.execute("INSERT OR IGNORE INTO storage_reservations(id,owner_iss,owner_sub,bytes,state,created_at) VALUES('one','iss','sub',1073741824,'reserved',0)",[]).unwrap();
        let used: i64 = db
            .query_row(
                "SELECT used_bytes FROM storage_usage WHERE owner_iss='iss' AND owner_sub='sub'",
                [],
                |r| r.get(0),
            )
            .unwrap();
        assert_eq!(used, 1073741824);
        assert!(db.execute("INSERT INTO storage_reservations(id,owner_iss,owner_sub,bytes,state,created_at) VALUES('two','iss','sub',1,'reserved',0)",[]).is_err());
        db.execute("DELETE FROM storage_reservations WHERE id='one'", [])
            .unwrap();
        db.execute("INSERT INTO storage_reservations(id,owner_iss,owner_sub,bytes,state,created_at) VALUES('two','iss','sub',1,'reserved',0)",[]).unwrap();
        let used: i64 = db
            .query_row(
                "SELECT used_bytes FROM storage_usage WHERE owner_iss='iss' AND owner_sub='sub'",
                [],
                |r| r.get(0),
            )
            .unwrap();
        assert_eq!(used, 1);
    }
}
