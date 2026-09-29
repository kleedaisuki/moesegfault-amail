//! amail mail service. / amail 邮件服务。

mod address_diag;
mod archive;
mod auth;
mod platform;
mod search_jobs;
mod trace;

use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use subtle::ConstantTimeEq;
use wasm_bindgen::JsValue;
use worker::*;

use crate::address_diag::{AddressDiag, Kind as AddressDiagKind, Stage as AddressDiagStage};
use crate::archive::{parse_draft, Draft};
use crate::auth::Principal;
use crate::trace::{Operation, Phase, Trace};

/// Bound one synchronous search below D1's request query cap and Worker memory. / 将同步搜索限制在 D1 单次请求查询上限与 Worker 内存以内。
const SEARCH_SQL_BUDGET: usize = 400;
const SEARCH_TRANSFER_BUDGET: usize = 32 * 1024 * 1024;
const SEARCH_BODY_BUDGET: usize = 64 * 1024 * 1024;
const SEARCH_PAGE_SIZE: usize = 64;
/// Two of Cloudflare's 200 literal rules are reserved for abuse and postmaster.
/// Cloudflare 的 200 条精确路由规则中保留 2 条用于滥用举报及邮政主管入口。
const USER_ADDRESS_CAPACITY: i64 = 198;
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

/// Only documented, structured provider refusals are definitive; an unknown
/// exception may have submitted the mail and must never trigger blind retry.
/// 仅文档化的结构化提供商拒绝属于确定结果；未知异常可能已提交邮件，绝不可盲重试。
fn definitive_send_error(err: &worker::Error) -> Option<AppError> {
    let (status, code) = match err {
        worker::Error::EmailRecipientSuppressed(_) => (403, "recipient_suppressed"),
        worker::Error::EmailRecipientNotAllowed(_) => (403, "recipient_not_allowed"),
        worker::Error::RateLimitExceeded(_) => (429, "provider_rate_limited"),
        worker::Error::DailyLimitExceeded(_) => (429, "provider_daily_limit"),
        _ => return None,
    };
    Some(AppError { status, code })
}

/// Reproduce a terminal rejection on idempotent retry without another provider call.
/// 幂等重试时重现确定性拒绝，不再调用提供商。
fn stored_rejection(code: &str) -> Option<AppError> {
    let status = match code {
        "recipient_suppressed" | "recipient_not_allowed" => 403,
        "provider_rate_limited" | "provider_daily_limit" => 429,
        _ => return None,
    };
    let code = match code {
        "recipient_suppressed" => "recipient_suppressed",
        "recipient_not_allowed" => "recipient_not_allowed",
        "provider_rate_limited" => "provider_rate_limited",
        "provider_daily_limit" => "provider_daily_limit",
        _ => unreachable!(),
    };
    Some(AppError { status, code })
}

/// Preserve established client codes while keeping provider failure details private.
fn rule_create_app_error(error: &platform::RuleCreateFailure) -> AppError {
    if error.is_capacity() {
        AppError::conflict("capacity_exhausted")
    } else {
        AppError {
            status: 503,
            code: "routing_unavailable",
        }
    }
}

/// Main API entry point; authentication precedes mailbox access. / 主 API 入口；邮箱访问始终在身份认证之后。
#[event(fetch)]
pub async fn main(req: Request, env: Env, _ctx: Context) -> Result<Response> {
    let request_id = uuid::Uuid::new_v4().to_string();
    let start = js_sys::Date::now();
    let mut trace = Trace::new();
    let result = dispatch(req, env, &request_id, &mut trace).await;
    let mut response = match result {
        Ok(response) => response,
        Err(err) => problem(&request_id, err)?,
    };
    response
        .headers_mut()
        .set("x-amail-request-id", &request_id)?;
    response.headers_mut().set("Cache-Control", "no-store")?;
    trace.exit(
        &request_id,
        response.status_code(),
        trace::elapsed_ms(start),
    );
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
    if let Err(_) = search_jobs::cleanup(&env).await {
        console_warn!("amail search job cleanup failed");
    }
    if let Err(_) = expire_abuse_data(&env).await {
        console_warn!("amail abuse data cleanup failed");
    }
}

/// Retain the restricted envelope only for 90 days after submission. This
/// deliberately outlives user archive deletion so late complaints still hold
/// the responsible sender; complaint blocks and audit decisions are separate.
/// 受限信封自提交起仅保留 90 天；有意晚于用户归档删除，以处理迟到投诉；
/// 投诉封锁及审计决策另行保存。
async fn expire_abuse_data(env: &Env) -> Result<()> {
    let cutoff_ms = now() - 90 * 86_400_000;
    let cutoff_sec = cutoff_ms / 1000;
    let database = env.d1("MAIL_DB")?;
    database.prepare("UPDATE send_requests SET sender=NULL,envelope_json=NULL WHERE rowid IN (SELECT rowid FROM send_requests WHERE created_at<?1 AND (sender IS NOT NULL OR envelope_json IS NOT NULL) ORDER BY created_at LIMIT 100)")
        .bind(&[bind_num(cutoff_ms)])?.run().await?;
    database.prepare("DELETE FROM provider_events WHERE rowid IN (SELECT rowid FROM provider_events WHERE received_at<?1 ORDER BY received_at LIMIT 100)")
        .bind(&[bind_num(cutoff_sec)])?.run().await?;
    database.prepare("DELETE FROM recipient_outcomes WHERE rowid IN (SELECT rowid FROM recipient_outcomes WHERE occurred_at<?1 ORDER BY occurred_at LIMIT 100)")
        .bind(&[bind_num(cutoff_sec)])?.run().await?;
    Ok(())
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
    let rows = database.prepare("SELECT address,state,cf_rule_id,created_at FROM addresses WHERE state IN ('provisioning','deleting') OR needs_reconcile=1 ORDER BY CASE state WHEN 'provisioning' THEN 0 WHEN 'deleting' THEN 1 WHEN 'active' THEN 2 ELSE 3 END,created_at ASC LIMIT 30")
        .all().await?.results::<Row>()?;
    for row in rows {
        let mut ids = platform::rules_for_address(env, &row.address).await?;
        if row.state == "active" {
            // Only prune duplicates after the committed active rule is known
            // to exist at the provider. Never treat active as a delete state.
            let Some(saved) = row.cf_rule_id.as_deref() else {
                continue;
            };
            if !ids.iter().any(|id| id == saved) {
                continue;
            }
            for extra in ids.iter().filter(|id| id.as_str() != saved) {
                platform::delete_rule(env, extra).await?;
            }
            database.prepare("UPDATE addresses SET needs_reconcile=0 WHERE address=?1 AND state='active' AND cf_rule_id=?2")
                .bind(&[bind_str(&row.address), bind_str(saved)])?.run().await?;
            continue;
        }
        if let Some(saved) = row.cf_rule_id.clone() {
            if !ids.contains(&saved) {
                ids.push(saved);
            }
        }
        if row.state == "provisioning" {
            if let Some(first) = ids.first() {
                if ids.len() > 1 {
                    // Record duplicate evidence before a racing add can choose
                    // a different rule from a later, narrower provider view.
                    database.prepare("UPDATE addresses SET needs_reconcile=1 WHERE address=?1 AND state='provisioning'")
                        .bind(&[bind_str(&row.address)])?.run().await?;
                }
                let result = database.prepare("UPDATE addresses SET state='active',cf_rule_id=?1,needs_reconcile=MAX(needs_reconcile,?2) WHERE address=?3 AND state='provisioning'")
                    .bind(&[bind_str(first),bind_num((ids.len() > 1) as i64),bind_str(&row.address)])?.run().await?;
                if result.meta()?.and_then(|meta| meta.changes) == Some(0) && ids.len() > 1 {
                    // Another actor may have activated a different rule. Mark
                    // the active row for state-aware pruning, never delete here.
                    database.prepare("UPDATE addresses SET needs_reconcile=1 WHERE address=?1 AND state='active'")
                        .bind(&[bind_str(&row.address)])?.run().await?;
                }
            } else if row.created_at < now() - 10 * 60_000 {
                database.prepare("UPDATE addresses SET state='pending',needs_reconcile=0 WHERE address=?1 AND state='provisioning'")
                    .bind(&[bind_str(&row.address)])?.run().await?;
            }
            continue;
        }
        if row.state == "pending" {
            // A stale duplicate marker must never send pending through the
            // deletion path. If a route exists, restore the repair journal.
            let query = if ids.is_empty() {
                "UPDATE addresses SET needs_reconcile=0 WHERE address=?1 AND state='pending'"
            } else {
                "UPDATE addresses SET state='provisioning' WHERE address=?1 AND state='pending'"
            };
            database
                .prepare(query)
                .bind(&[bind_str(&row.address)])?
                .run()
                .await?;
            continue;
        }
        if !matches!(row.state.as_str(), "deleting" | "retired") {
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
        let envelope = outbound_envelope_json(&draft)?;
        if row.created_at >= now() - 90 * 86_400_000 {
            database.prepare("UPDATE send_requests SET sender=COALESCE(sender,?1),envelope_json=COALESCE(envelope_json,?2) WHERE message_id=?3 AND provider_id=?4")
                .bind(&[bind_str(&m.from),bind_str(&envelope),bind_str(&row.message_id),bind_str(&row.provider_id)])?.run().await?;
        }
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

/// Return the longest UTF-8 prefix accepted by the embedding provider's byte limit.
/// A boundary inside a multibyte character must not fall back to the whole input.
fn embedding_prefix(source: &str) -> &str {
    let mut end = source.len().min(platform::EMBEDDING_INPUT_MAX_BYTES);
    while !source.is_char_boundary(end) {
        end -= 1;
    }
    &source[..end]
}

/// Retry schedule in milliseconds. Jitter is deterministic per message so retries
/// do not synchronize, and an indefinitely unavailable provider cannot hot-loop.
fn embedding_retry_delay(attempts: i64, id: &str) -> i64 {
    let base: i64 = match attempts {
        0 | 1 => 5 * 60_000,
        2 => 15 * 60_000,
        3 => 60 * 60_000,
        4 => 6 * 60 * 60_000,
        _ => 20 * 60 * 60_000,
    };
    let hash = id.bytes().fold(0u64, |hash, byte| {
        hash.wrapping_mul(16_777_619) ^ u64::from(byte)
    });
    base + (hash % (base as u64 / 5 + 1)) as i64
}

/// Separate per-message defects from provider-wide outages without inspecting
/// or logging the provider's response body.
fn embedding_failure_policy(error: platform::EmbeddingFailure, attempts: i64) -> (bool, i64) {
    // HTTP 400/413/422 may be a globally bad model or route, not bad content.
    let quarantine = error == platform::EmbeddingFailure::InvalidInput
        || (error == platform::EmbeddingFailure::Malformed && attempts >= 3);
    let cooldown = match error {
        platform::EmbeddingFailure::Dependency => 60 * 60_000,
        platform::EmbeddingFailure::RateLimited => 15 * 60_000,
        platform::EmbeddingFailure::Transient => 5 * 60_000,
        _ => 0,
    };
    (quarantine, cooldown)
}

/// D1 supplies work durability; Cron is only a wake-up, never the work ledger.
/// The due query transfers IDs, not content. Each lease holder reads one active
/// message immediately before the provider call and commits only under that lease.
/// Cloudflare's scheduled invocation has a 15-minute maximum wall time, so the
/// lease must outlive that invocation to prevent an overlapping Cron transfer.
const EMBEDDING_LEASE_MS: i64 = 20 * 60_000;

/// Opaque work identity returned by the bounded owner-fair due query.
#[derive(Deserialize)]
struct EmbeddingDue {
    message_id: String,
}

/// Active message projection read only after the work item is leased.
#[derive(Deserialize)]
struct EmbeddingPending {
    subject: String,
    body_text: String,
    attempts: i64,
}

/// Provider-wide cooldown; only this timestamp is needed by the sweep.
#[derive(Deserialize)]
struct EmbeddingDependency {
    blocked_until: i64,
}

/// Identifies a conditional claim; no provider call may precede the active-row read.
struct EmbeddingLease<'a> {
    message_id: &'a str,
    token: String,
}

/// Sweep a bounded, owner-fair set of due IDs until a provider cooldown begins.
async fn reindex(env: &Env) -> Result<()> {
    let database = env.d1("MAIL_DB")?;
    let current = now();
    let dependency = database
        .prepare("SELECT blocked_until FROM embedding_dependency WHERE id=1")
        .first::<EmbeddingDependency>(None)
        .await?;
    if dependency.is_some_and(|row| row.blocked_until > current) {
        return Ok(());
    }
    let due = embedding_due(&database, current).await?;
    let mut invalid_requests = 0;
    for item in due {
        let Some(lease) = claim_embedding(&database, &item.message_id).await? else {
            continue;
        };
        let Some(row) = read_leased_embedding(&database, &lease).await? else {
            continue;
        };
        if process_embedding(env, &database, &lease, row, &mut invalid_requests).await? {
            break;
        }
    }
    Ok(())
}

/// Read only due work IDs, preserving the SQL's per-owner and global caps.
async fn embedding_due(database: &D1Database, current: i64) -> Result<Vec<EmbeddingDue>> {
    database
        .prepare(EMBEDDING_DUE_SQL)
        .bind(&[bind_num(current)])?
        .all()
        .await?
        .results::<EmbeddingDue>()
}

/// Claim one still-eligible item and account for its owner's service time.
async fn claim_embedding<'a>(
    database: &D1Database,
    message_id: &'a str,
) -> Result<Option<EmbeddingLease<'a>>> {
    let token = uuid::Uuid::new_v4().to_string();
    let claimed_at = now();
    let claim = database
        .prepare(
            "UPDATE embedding_work SET lease_until=?1,lease_token=?2
             WHERE message_id=?3 AND state='pending'
               AND next_attempt_at<=?4 AND lease_until<=?4
               AND EXISTS (SELECT 1 FROM messages
                           WHERE id=?3 AND deleted_at IS NULL AND embedding_json IS NULL)",
        )
        .bind(&[
            bind_num(claimed_at + EMBEDDING_LEASE_MS),
            bind_str(&token),
            bind_str(message_id),
            bind_num(claimed_at),
        ])?
        .run()
        .await?;
    if claim.meta()?.and_then(|meta| meta.changes).unwrap_or(0) != 1 {
        return Ok(None);
    }
    database
        .prepare(
            "UPDATE embedding_owner_schedule SET last_served_at=?1
             WHERE EXISTS (SELECT 1 FROM embedding_work w
                           WHERE w.message_id=?2 AND w.lease_token=?3
                             AND w.owner_iss=embedding_owner_schedule.owner_iss
                             AND w.owner_sub=embedding_owner_schedule.owner_sub)",
        )
        .bind(&[bind_num(claimed_at), bind_str(message_id), bind_str(&token)])?
        .run()
        .await?;
    Ok(Some(EmbeddingLease { message_id, token }))
}

/// Recheck active, unindexed content under the live lease before transfer.
async fn read_leased_embedding(
    database: &D1Database,
    lease: &EmbeddingLease<'_>,
) -> Result<Option<EmbeddingPending>> {
    database
        .prepare(
            "SELECT m.subject,m.body_text,w.attempts
             FROM messages m JOIN embedding_work w ON w.message_id=m.id
             WHERE m.id=?1 AND m.deleted_at IS NULL AND m.embedding_json IS NULL
               AND w.lease_token=?2 AND w.lease_until>?3",
        )
        .bind(&[
            bind_str(lease.message_id),
            bind_str(&lease.token),
            bind_num(now()),
        ])?
        .first::<EmbeddingPending>(None)
        .await
}

/// Return true when a provider-wide cooldown ends the current sweep.
async fn process_embedding(
    env: &Env,
    database: &D1Database,
    lease: &EmbeddingLease<'_>,
    row: EmbeddingPending,
    invalid_requests: &mut i32,
) -> Result<bool> {
    let source = format!("{}\n{}", row.subject, row.body_text);
    let input = embedding_prefix(&source);
    match platform::embed_classified(env, input, "search_document").await {
        Ok(vector) => {
            persist_embedding_success(env, database, lease, &vector, input.len() < source.len())
                .await?;
            Ok(false)
        }
        Err(error) => {
            persist_embedding_failure(database, lease, row.attempts, error, invalid_requests).await
        }
    }
}

/// Commit only if the message remains active, unindexed, and leased to us.
async fn persist_embedding_success(
    env: &Env,
    database: &D1Database,
    lease: &EmbeddingLease<'_>,
    vector: &[f32],
    truncated: bool,
) -> Result<()> {
    let serialized = serde_json::to_string(vector)?;
    let model = env.var("OPENROUTER_EMBEDDING_MODEL")?.to_string();
    // The trigger removes work only after this conditional active-row update.
    database
        .prepare(
            "UPDATE messages
             SET embedding_json=?1,embedding_model=?2,embedding_dimensions=256,
                 embedding_input_version=1,embedding_truncated=?3
             WHERE id=?4 AND deleted_at IS NULL AND embedding_json IS NULL
               AND EXISTS (SELECT 1 FROM embedding_work
                           WHERE message_id=?4 AND lease_token=?5 AND lease_until>?6)",
        )
        .bind(&[
            bind_str(&serialized),
            bind_str(&model),
            bind_num(truncated as i64),
            bind_str(lease.message_id),
            bind_str(&lease.token),
            bind_num(now()),
        ])?
        .run()
        .await?;
    Ok(())
}

/// Persist bounded retry or quarantine, and stop on the established cooldown rule.
async fn persist_embedding_failure(
    database: &D1Database,
    lease: &EmbeddingLease<'_>,
    previous_attempts: i64,
    error: platform::EmbeddingFailure,
    invalid_requests: &mut i32,
) -> Result<bool> {
    let attempts = previous_attempts + 1;
    let (quarantine, mut cooldown) = embedding_failure_policy(error, attempts);
    if error == platform::EmbeddingFailure::InvalidRequest {
        *invalid_requests += 1;
        if *invalid_requests >= 3 {
            cooldown = 60 * 60_000;
        }
    }
    let next = now() + embedding_retry_delay(attempts, lease.message_id);
    database
        .prepare(
            "UPDATE embedding_work
             SET attempts=?1,next_attempt_at=?2,lease_until=0,lease_token=NULL,
                 state=?3,last_error_code=?4
             WHERE message_id=?5 AND lease_token=?6",
        )
        .bind(&[
            bind_num(attempts),
            bind_num(next),
            bind_str(if quarantine { "quarantined" } else { "pending" }),
            bind_str(error.code()),
            bind_str(lease.message_id),
            bind_str(&lease.token),
        ])?
        .run()
        .await?;
    if quarantine {
        console_warn!("amail semantic document quarantined");
    }
    if cooldown == 0 {
        return Ok(false);
    }
    database
        .prepare(
            "UPDATE embedding_dependency
             SET blocked_until=MAX(blocked_until,?1),last_error_code=?2 WHERE id=1",
        )
        .bind(&[bind_num(now() + cooldown), bind_str(error.code())])?
        .run()
        .await?;
    console_warn!("amail semantic provider cooldown");
    Ok(true)
}

/// Owner rank and least-recently-served order avoid starvation across accounts.
const EMBEDDING_DUE_SQL: &str = "SELECT message_id FROM (
       SELECT w.message_id,w.next_attempt_at,w.received_at,
              COALESCE(o.last_served_at,0) AS last_served_at,
              ROW_NUMBER() OVER (
                PARTITION BY w.owner_iss,w.owner_sub
                ORDER BY w.next_attempt_at,w.received_at,w.message_id
              ) AS owner_rank
       FROM embedding_work w
       LEFT JOIN embedding_owner_schedule o
         ON o.owner_iss=w.owner_iss AND o.owner_sub=w.owner_sub
       WHERE w.state='pending' AND w.next_attempt_at<=?1 AND w.lease_until<=?1
     ) WHERE owner_rank<=4
     ORDER BY owner_rank,last_served_at,next_attempt_at,received_at,message_id LIMIT 20";

async fn dispatch(
    mut req: Request,
    env: Env,
    request_id: &str,
    trace: &mut Trace,
) -> AppResult<Response> {
    let path = req.path();
    if req.method() == Method::Get && path == "/health" {
        trace.operation(Operation::Health);
        return Ok(Response::from_json(
            &serde_json::json!({"status":"ok","request_id":request_id}),
        )?);
    }
    if path == "/internal/inbound" && req.method() == Method::Post {
        return inbound(&mut req, &env, request_id, trace).await;
    }
    let user = auth::authenticate(&req, &env).await.map_err(|_| AppError {
        status: 401,
        code: "unauthorized",
    })?;
    let segments = path.trim_matches('/').split('/').collect::<Vec<_>>();
    trace.accept_parent(req.headers().get("traceparent").ok().flatten().as_deref());
    trace.operation(operation_for(req.method(), &segments));
    match (req.method(), segments.as_slice()) {
        (Method::Get, ["v1", "addresses"]) => list_addresses(&env, &user, request_id).await,
        (Method::Post, ["v1", "addresses"]) => {
            let mut diagnostic = AddressDiag::new();
            let result =
                add_address(&mut req, &env, &user, request_id, trace, &mut diagnostic).await;
            if !address_diagnostics_enabled(&env) {
                return result;
            }
            let success = result.is_ok();
            let mut response = match result {
                Ok(response) => response,
                Err(error) => problem(request_id, error)?,
            };
            response
                .headers_mut()
                .set("x-amail-address-diag", &diagnostic.header(success))?;
            Ok(response)
        }
        (Method::Delete, ["v1", "addresses"]) => {
            delete_address(&mut req, &env, &user, request_id).await
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
            search_jobs::search(
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
            search_jobs::search(&env, &user, query, request_id).await
        }
        (Method::Get, ["v1", "messages", "search", "jobs", id]) => {
            search_jobs::poll(&env, &user, id, request_id).await
        }
        (Method::Post, ["v1", "messages", "send"]) => {
            send_message(&mut req, &env, &user, request_id, trace).await
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

/// Diagnostics require both an explicit staging switch and the exact isolated domain.
fn address_diagnostics_enabled(env: &Env) -> bool {
    env.var("ADDRESS_DIAGNOSTICS")
        .ok()
        .is_some_and(|value| value.to_string() == "v1")
        && env
            .var("MAIL_DOMAIN")
            .ok()
            .is_some_and(|value| value.to_string() == "mail-staging.moesegfault.dev")
}

/// Classify only known routes after authentication; never retain URL segments.
fn operation_for(method: Method, segments: &[&str]) -> Operation {
    match (method, segments) {
        (Method::Get, ["v1", "addresses"]) => Operation::AddressesList,
        (Method::Post, ["v1", "addresses"]) => Operation::AddressesAdd,
        (Method::Delete, ["v1", "addresses"]) => Operation::AddressesDelete,
        (Method::Get, ["v1", "messages"]) => Operation::MessagesList,
        (Method::Post, ["v1", "messages", "search"]) => Operation::MessagesSearch,
        (Method::Get, ["v1", "messages", "search", "jobs", _]) => Operation::SearchPoll,
        (Method::Post, ["v1", "messages", "send"]) => Operation::MessagesSend,
        (Method::Get, ["v1", "messages", _, "archive"]) => Operation::MessagesArchive,
        (Method::Get, ["v1", "messages", _]) => Operation::MessagesGet,
        (Method::Patch, ["v1", "messages", _]) => Operation::MessagesMark,
        (Method::Delete, ["v1", "messages", _]) => Operation::MessagesDelete,
        (Method::Post, ["v1", "telemetry"]) => Operation::TelemetryUpload,
        _ => Operation::Unknown,
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

/// Reassemble exact text in small D1 pages, charging each query and byte. / 以小页重建精确正文，并计入每次查询及字节预算。
async fn full_text(
    database: &D1Database,
    row: &MessageRow,
    sql_calls: &mut usize,
    prior_body_bytes: usize,
) -> AppResult<String> {
    #[derive(Deserialize)]
    struct Chunk {
        chunk_index: i64,
        body: String,
    }
    let mut body = row.body_text.clone();
    // The first UTF-8-safe 60,000-byte slice cannot have a successor below 59,997 bytes.
    // UTF-8 安全的首个 60,000 字节切片若短于 59,997 字节，不可能还有后续分块。
    if body.len() < 59_997 {
        if search_budget_exceeded(0, 0, prior_body_bytes.saturating_add(body.len())) {
            return Err(search_resource_limit());
        }
        return Ok(body);
    }
    let mut next_index = 1i64;
    loop {
        if search_budget_exceeded(*sql_calls, 0, prior_body_bytes.saturating_add(body.len())) {
            return Err(search_resource_limit());
        }
        let chunks = database
            .prepare("SELECT chunk_index,body FROM message_text_chunks WHERE message_id=?1 AND chunk_index>=?2 ORDER BY chunk_index LIMIT 16")
            .bind(&[bind_str(&row.id), bind_num(next_index)])?
            .all()
            .await?
            .results::<Chunk>()?;
        *sql_calls += 1;
        let count = chunks.len();
        for chunk in chunks {
            if chunk.chunk_index != next_index {
                return Err(AppError {
                    status: 503,
                    code: "search_index_corrupt",
                });
            }
            next_index = chunk.chunk_index + 1;
            body.push_str(&chunk.body);
            if search_budget_exceeded(0, 0, prior_body_bytes.saturating_add(body.len())) {
                return Err(search_resource_limit());
            }
        }
        if count < 16 {
            break;
        }
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
    reserve_window_quota(database, kind, user, units, limit, 86_400_000).await
}

/// A separate hourly bucket bounds bursts without weakening daily recipient accounting.
/// 独立小时桶限制突发量，同时不削弱每日收件人数核算。
async fn reserve_window_quota(
    database: &D1Database,
    kind: &str,
    user: &Principal,
    units: i64,
    limit: i64,
    window_ms: i64,
) -> AppResult<()> {
    if units < 0 || units > limit {
        return Err(AppError {
            status: 429,
            code: "quota_exhausted",
        });
    }
    let day = now() / window_ms;
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

/// The role-mail monitor owns this isolated D1 row; no user-mail migration may
/// manufacture a healthy lease. An absent binding, row, or readable lease fails closed.
/// 角色邮件监控器独占此隔离 D1 记录；用户邮件迁移不得伪造健康租约。绑定、记录或可读租约缺失时拒绝发送。
async fn role_monitor_healthy(env: &Env) -> bool {
    #[derive(Deserialize)]
    struct HealthRow {
        lease_until: i64,
    }
    let Ok(database) = env.d1("ROLE_MONITOR") else {
        return false;
    };
    let result = database
        .prepare("SELECT lease_until FROM role_monitor_health WHERE singleton=1")
        .first::<HealthRow>(None)
        .await;
    matches!(result, Ok(Some(row)) if lease_is_current(row.lease_until, now()))
}

/// Equality is expired; both timestamps are Unix milliseconds. / 相等即过期；两个时间戳均为 Unix 毫秒。
fn lease_is_current(lease_until: i64, now_ms: i64) -> bool {
    lease_until > now_ms
}

/// The SQL trigger consumes a canary key only under the global hold. / SQL 触发器仅在全局停发时消费金丝雀键。
fn canary_fallback_available(global_state: &str) -> bool {
    global_state == "held"
}

/// Fail closed unless the manual release gates, global policy, and separately
/// renewed role-monitor lease all permit public sending. A separately authorized
/// one-use canary may test delivery only while the global switch is held, which
/// is when the SQL admission trigger atomically consumes its idempotency key.
/// 公开发信须同时满足人工上线确认、全局策略及独立续期的角色邮件监控租约；单次金丝雀仅在全局停发时可用，由 SQL 准入触发器原子消费幂等键。
async fn check_send_policy(
    env: &Env,
    database: &D1Database,
    user: &Principal,
    draft: &Draft,
    idem: &str,
) -> AppResult<()> {
    #[derive(Deserialize)]
    struct PolicyRow {
        state: String,
    }
    #[derive(Deserialize)]
    struct CanaryRow {
        canary_recipient_sha256: String,
        canary_used_by: Option<String>,
    }
    let global = database
        .prepare("SELECT state FROM send_policy WHERE scope='global' AND owner_iss='*' AND owner_sub='*'")
        .first::<PolicyRow>(None)
        .await?;
    let global = global.ok_or(AppError {
        status: 403,
        code: "send_held",
    })?;
    let account = database
        .prepare(
            "SELECT state FROM send_policy WHERE scope='account' AND owner_iss=?1 AND owner_sub=?2",
        )
        .bind(&[bind_str(&user.iss), bind_str(&user.sub)])?
        .first::<PolicyRow>(None)
        .await?;
    if account.is_some_and(|row| row.state != "allowed") {
        return Err(AppError {
            status: 403,
            code: "send_held",
        });
    }
    let verified = database.prepare("SELECT 1 AS verified FROM send_release_gates WHERE id=1 AND feedback_verified=1 AND abuse_contact_verified=1 AND delivery_canary_verified=1 AND preview_reviewed=1")
        .first::<serde_json::Value>(None).await?.is_some();
    let public_ready = global.state == "allowed" && verified && role_monitor_healthy(env).await;
    if !public_ready {
        // The SQL canary guard consumes a key only under a global hold. If the
        // monitor fails after a public launch, do not bypass the lease with an
        // unconsumed grant; first return the global switch to held.
        // SQL 金丝雀保护仅在全局停发时消费键；上线后监控失效不得通过未消费授权绕过租约。
        if !canary_fallback_available(&global.state) {
            return Err(AppError {
                status: 403,
                code: "send_held",
            });
        }
        let grant = database.prepare("SELECT canary_recipient_sha256,canary_used_by FROM send_release_gates WHERE id=1 AND canary_owner_iss=?1 AND canary_owner_sub=?2 AND canary_expires_at>unixepoch() AND canary_recipient_sha256 IS NOT NULL")
            .bind(&[bind_str(&user.iss),bind_str(&user.sub)])?
            .first::<CanaryRow>(None).await?;
        let permitted = grant.is_some_and(|grant| {
            canary_matches(
                draft,
                idem,
                &grant.canary_recipient_sha256,
                grant.canary_used_by.as_deref(),
            )
        });
        if !permitted {
            return Err(AppError {
                status: 403,
                code: "send_held",
            });
        }
    }
    let recipients = draft
        .manifest
        .to
        .iter()
        .chain(&draft.manifest.cc)
        .chain(&draft.manifest.bcc)
        .map(|recipient| recipient.to_ascii_lowercase())
        .collect::<Vec<_>>();
    let recipients_json =
        serde_json::to_string(&recipients).map_err(|_| AppError::bad("invalid_mail_fields"))?;
    let blocked = database.prepare("SELECT 1 AS blocked FROM recipient_blocks WHERE owner_iss=?1 AND owner_sub=?2 AND recipient IN (SELECT value FROM json_each(?3)) LIMIT 1")
        .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(&recipients_json)])?
        .first::<serde_json::Value>(None).await?.is_some();
    if blocked {
        return Err(AppError {
            status: 403,
            code: "recipient_blocked",
        });
    }
    Ok(())
}

/// The canary grant authorizes one exact recipient and idempotency key; it is
/// not a general user-account exception to the launch hold.
/// 金丝雀授权仅允许一个精确收件人和幂等键，不是用户账户的通用上线豁免。
fn canary_matches(draft: &Draft, idem: &str, recipient_hash: &str, used_by: Option<&str>) -> bool {
    if draft.manifest.to.len() != 1
        || !draft.manifest.cc.is_empty()
        || !draft.manifest.bcc.is_empty()
        || used_by.is_some_and(|used| used != idem)
    {
        return false;
    }
    let recipient = draft.manifest.to[0].to_ascii_lowercase();
    format!("{:x}", Sha256::digest(recipient.as_bytes())) == recipient_hash
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

/// Schedule state-aware duplicate pruning when a provider side effect may have
/// raced with activation. The caller must not treat a failed mark as a license
/// to delete any provider rule.
async fn flag_active_address(database: &D1Database, address: &str, user: &Principal) -> Result<()> {
    database.prepare("UPDATE addresses SET needs_reconcile=1 WHERE address=?1 AND owner_iss=?2 AND owner_sub=?3 AND state='active'")
        .bind(&[bind_str(address), bind_str(&user.iss), bind_str(&user.sub)])?.run().await?;
    Ok(())
}

async fn list_addresses(env: &Env, user: &Principal, request_id: &str) -> AppResult<Response> {
    let database = db(env)?;
    let result = database.prepare("SELECT address,state,created_at,cf_rule_id FROM addresses WHERE owner_iss=?1 AND owner_sub=?2 AND state!='retired' ORDER BY created_at")
        .bind(&[bind_str(&user.iss), bind_str(&user.sub)])?.all().await?;
    let addresses = result.results::<AddressRow>()?.into_iter().map(|a| serde_json::json!({"address":a.address,"state":if a.state=="provisioning" {"pending"} else {a.state.as_str()},"created_at":iso(a.created_at)})).collect::<Vec<_>>();
    #[derive(Deserialize)]
    struct CapacityRow {
        n: i64,
    }
    // D1 shows known allocations; Cloudflare's route-limit response remains authoritative.
    // D1 显示已知分配量；Cloudflare 的路由上限响应仍是最终依据。
    let used = database
        .prepare("SELECT COUNT(*) AS n FROM addresses WHERE state!='retired'")
        .first::<CapacityRow>(None)
        .await?
        .map_or(0, |row| row.n);
    Ok(Response::from_json(
        &serde_json::json!({"addresses":addresses,"limit":10,"capacity":{"limit":USER_ADDRESS_CAPACITY,"registered":used,"remaining_estimate":(USER_ADDRESS_CAPACITY-used).max(0)},"request_id":request_id}),
    )?)
}

async fn add_address(
    req: &mut Request,
    env: &Env,
    user: &Principal,
    request_id: &str,
    trace: &Trace,
    diagnostic: &mut AddressDiag,
) -> AppResult<Response> {
    diagnostic.enter(AddressDiagStage::Input);
    let input: AddAddress = req
        .json()
        .await
        .map_err(|_| AppError::bad("invalid_json"))?;
    let part = local_part(&input.local_part)
        .ok_or_else(|| AppError::conflict("reserved_or_invalid_name"))?;
    let address = format!("{part}@{}", env.var("MAIL_DOMAIN")?.to_string());
    diagnostic.enter(AddressDiagStage::D1Lookup);
    let database = db(env)?;
    let existing = database
        .prepare("SELECT address,state,created_at,cf_rule_id FROM addresses WHERE address=?1")
        .bind(&[bind_str(&address)])?
        .first::<AddressRow>(None)
        .await?;
    if let Some(row) = existing {
        if row.state == "retired" {
            diagnostic.fail(AddressDiagKind::State, None, None);
            return Err(AppError::conflict("address_retired"));
        }
        let mine = database.prepare("SELECT 1 AS mine FROM addresses WHERE address=?1 AND owner_iss=?2 AND owner_sub=?3")
            .bind(&[bind_str(&address),bind_str(&user.iss),bind_str(&user.sub)])?.first::<serde_json::Value>(None).await?.is_some();
        if !mine {
            diagnostic.fail(AddressDiagKind::State, None, None);
            return Err(AppError::conflict("address_unavailable"));
        }
        if row.state == "active" {
            diagnostic.enter(AddressDiagStage::ResponseEncode);
            let response = Response::from_json(
                &serde_json::json!({"address":address,"state":"active","created_at":iso(row.created_at),"request_id":request_id}),
            )?;
            diagnostic.success();
            return Ok(response);
        }
        if row.state == "deleting" {
            diagnostic.fail(AddressDiagKind::State, None, None);
            return Err(AppError::conflict("address_deleting"));
        }
        if row.state == "provisioning" {
            diagnostic.enter(AddressDiagStage::ResponseEncode);
            let response = Response::from_json(&serde_json::json!({"address":address,"state":"pending","created_at":iso(row.created_at),"request_id":request_id}))?.with_status(202);
            diagnostic.success();
            return Ok(response);
        }
    } else {
        diagnostic.enter(AddressDiagStage::D1Allocate);
        #[derive(Deserialize)]
        struct CountRow {
            n: i64,
        }
        let count = database
            .prepare("SELECT COUNT(*) AS n FROM addresses WHERE state!='retired'")
            .first::<CountRow>(None)
            .await?
            .map_or(0, |r| r.n);
        if count >= USER_ADDRESS_CAPACITY {
            diagnostic.fail(AddressDiagKind::State, None, None);
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
            diagnostic.fail(AddressDiagKind::D1, None, None);
            return Err(AppError::conflict("address_unavailable"));
        }
        let owned = database.prepare("SELECT address,state,created_at,cf_rule_id FROM addresses WHERE address=?1 AND owner_iss=?2 AND owner_sub=?3")
            .bind(&[bind_str(&address),bind_str(&user.iss),bind_str(&user.sub)])?.first::<AddressRow>(None).await?;
        if owned.is_none() {
            diagnostic.fail(AddressDiagKind::State, None, None);
            return Err(AppError::conflict("address_limit"));
        }
    }
    diagnostic.enter(AddressDiagStage::D1Claim);
    let claim = database.prepare("UPDATE addresses SET state='provisioning' WHERE address=?1 AND owner_iss=?2 AND owner_sub=?3 AND state='pending'")
        .bind(&[bind_str(&address),bind_str(&user.iss),bind_str(&user.sub)])?.run().await?;
    if claim.meta()?.and_then(|m| m.changes).unwrap_or(0) != 1 {
        diagnostic.enter(AddressDiagStage::ResponseEncode);
        let response = Response::from_json(
            &serde_json::json!({"address":address,"state":"pending","request_id":request_id}),
        )?
        .with_status(202);
        diagnostic.success();
        return Ok(response);
    }
    diagnostic.enter(AddressDiagStage::RoutingList);
    let list_start = js_sys::Date::now();
    let existing_rules = platform::rules_for_address_typed(env, &address).await;
    trace.phase(
        request_id,
        Phase::RoutingList,
        existing_rules.is_ok(),
        trace::elapsed_ms(list_start),
    );
    let existing_rules = existing_rules.map_err(|error| {
        let kind = match &error {
            platform::RuleListFailure::Request => AddressDiagKind::Request,
            platform::RuleListFailure::Http { .. } => AddressDiagKind::Http,
            platform::RuleListFailure::Provider { .. } => AddressDiagKind::Provider,
            platform::RuleListFailure::Decode { .. } => AddressDiagKind::Decode,
        };
        diagnostic.fail(kind, error.provider_status(), None);
        AppError::from(worker::Error::RustError("routing_list_failed".into()))
    })?;
    let rule_id = if let Some(id) = existing_rules.first() {
        id.clone()
    } else {
        diagnostic.enter(AddressDiagStage::RoutingCreate);
        let create_start = js_sys::Date::now();
        let created = platform::create_rule(env, &address).await;
        trace.routing_create(
            request_id,
            created.is_ok(),
            created
                .as_ref()
                .err()
                .and_then(|error| error.provider_status()),
            created
                .as_ref()
                .err()
                .and_then(|error| error.provider_code()),
            trace::elapsed_ms(create_start),
        );
        match created {
            Ok(id) => id,
            Err(error) => {
                // A failed response may still follow a provider-side create.
                // If Cron activated another exact rule, revisit duplicates.
                let _ = flag_active_address(&database, &address, user).await;
                let kind = match &error {
                    platform::RuleCreateFailure::Request => AddressDiagKind::Request,
                    platform::RuleCreateFailure::UnexpectedResponse { .. } => {
                        AddressDiagKind::Decode
                    }
                    platform::RuleCreateFailure::Provider { .. } => AddressDiagKind::Provider,
                };
                diagnostic.fail(kind, error.provider_status(), error.provider_code());
                return Err(rule_create_app_error(&error));
            }
        }
    };
    // Defer duplicate pruning until an active D1 row names the surviving rule.
    let duplicate_rules = existing_rules.len() > 1;
    diagnostic.enter(AddressDiagStage::D1Activate);
    let transition = database.prepare("UPDATE addresses SET state='active',cf_rule_id=?1,needs_reconcile=MAX(needs_reconcile,?2) WHERE address=?3 AND owner_iss=?4 AND owner_sub=?5 AND state='provisioning'")
        .bind(&[bind_str(&rule_id),bind_num(duplicate_rules as i64),bind_str(&address),bind_str(&user.iss),bind_str(&user.sub)])?.run().await;
    let no_change = match transition {
        Ok(result) => match result.meta().ok().flatten().and_then(|meta| meta.changes) {
            Some(0) => true,
            _ => false,
        },
        Err(_) => false,
    };
    diagnostic.enter(AddressDiagStage::D1Readback);
    // A failed D1 response does not prove the write failed: deleting the route
    // could strand an already-committed active address. Read the exact owned row
    // before acknowledging activation or classifying a concurrent deletion.
    let row = database
        .prepare("SELECT address,state,created_at,cf_rule_id FROM addresses WHERE address=?1 AND owner_iss=?2 AND owner_sub=?3")
        .bind(&[bind_str(&address), bind_str(&user.iss), bind_str(&user.sub)])?
        .first::<AddressRow>(None)
        .await;
    let row = match row {
        Ok(Some(row)) => row,
        _ => {
            diagnostic.fail(AddressDiagKind::D1, None, None);
            return Err(AppError {
                status: 503,
                code: "address_provision_unknown",
            });
        }
    };
    if row.state == "active" && row.cf_rule_id.as_deref() != Some(rule_id.as_str()) {
        // Cron may have adopted a different exact rule concurrently. Preserve
        // duplicate evidence without changing its committed active rule.
        let _ = flag_active_address(&database, &address, user).await;
    }
    if row.state != "active" || row.cf_rule_id.as_deref() != Some(rule_id.as_str()) {
        // Provisioning and deleting are reconciled by cron. Do not destroy a
        // possibly committed route, including when the UPDATE reported zero.
        if no_change && matches!(row.state.as_str(), "deleting" | "retired") {
            diagnostic.fail(AddressDiagKind::State, None, None);
            return Err(AppError::conflict("address_state_changed"));
        }
        diagnostic.fail(AddressDiagKind::D1, None, None);
        return Err(AppError {
            status: 503,
            code: "address_provision_unknown",
        });
    }
    diagnostic.enter(AddressDiagStage::ResponseEncode);
    let response = Response::from_json(&serde_json::json!({"address":address,"state":row.state,"created_at":iso(row.created_at),"request_id":request_id}))?.with_status(201);
    diagnostic.success();
    Ok(response)
}

async fn delete_address(
    req: &mut Request,
    env: &Env,
    user: &Principal,
    request_id: &str,
) -> AppResult<Response> {
    #[derive(Deserialize)]
    #[serde(deny_unknown_fields)]
    struct DeleteAddress {
        address: String,
    }
    let input: DeleteAddress = req
        .json()
        .await
        .map_err(|_| AppError::bad("invalid_json"))?;
    let address = input.address.to_ascii_lowercase();
    if !address.ends_with(&format!("@{}", env.var("MAIL_DOMAIN")?.to_string()))
        || !valid_address(&address)
    {
        return Err(AppError::bad("invalid_address"));
    }
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
    #[serde(default)]
    subject_truncated: i64,
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
    #[serde(default)]
    embedding_model: Option<String>,
    #[serde(default)]
    embedding_dimensions: Option<i64>,
    #[serde(default)]
    embedding_input_version: Option<i64>,
}

/// A query and document may be compared only in the same configured vector space.
fn semantic_document_compatible(row: &MessageRow, query_model: Option<&str>) -> bool {
    query_model.is_some_and(|model| row.embedding_model.as_deref() == Some(model))
        && row.embedding_dimensions == Some(256)
        && row.embedding_input_version == Some(1)
}

fn summary(row: &MessageRow, score: Option<f64>) -> serde_json::Value {
    let to = serde_json::from_str::<Vec<String>>(&row.recipients_json).unwrap_or_default();
    let mut value = serde_json::json!({
        "id":row.id,"mailbox":row.address,"direction":row.direction,"from":row.sender,
        "to":to,"subject":row.subject,"subject_truncated":row.subject_truncated != 0,"received_at":iso(row.received_at),"read":row.is_read != 0,
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
    version: u8,
    hash: String,
    high_water: i64,
    generation: i64,
    last_time: i64,
    last_id: String,
    last_score_bits: Option<u64>,
}

/// Only rank keys, not message bodies, survive a continuation boundary. / 续扫边界只持久化排序键，不持久化邮件正文。
#[derive(Clone, Serialize, Deserialize)]
struct SearchHit {
    id: String,
    time: i64,
    score_bits: Option<u64>,
}

impl SearchHit {
    fn rank(&self) -> (f64, i64, &str) {
        (
            self.score_bits.map(f64::from_bits).unwrap_or_default(),
            self.time,
            self.id.as_str(),
        )
    }
}

/// A checkpoint is committed only after its marker row is fully examined. / 仅在游标指向的记录被完整处理后提交检查点。
#[derive(Serialize, Deserialize)]
struct SearchState {
    high_water: i64,
    generation: i64,
    marker: Option<(i64, String)>,
    hits: Vec<SearchHit>,
    query_vector: Option<Vec<f32>>,
    #[serde(default)]
    query_model: Option<String>,
}

#[derive(Deserialize)]
struct SearchJobRow {
    id: String,
    request_json: String,
    state_json: String,
    state: String,
    version: i64,
    lease_started_at: Option<i64>,
    expires_at: i64,
    current_generation: i64,
}

#[derive(Deserialize)]
struct SearchGeneration {
    generation: i64,
}

/// Keep a bounded synchronous scan honest: a budget breach is an error, never a partial page. / 同步扫描有界；触及预算必须报错，不能返回不完整结果。
fn search_resource_limit() -> AppError {
    AppError {
        status: 422,
        code: "search_resource_limit",
    }
}

/// Check whether issuing one more D1 call or retaining measured bytes would exceed the synchronous budget. / 判断再发一次 D1 查询或当前字节占用是否超出同步预算。
pub fn search_budget_exceeded(sql_calls: usize, transfer_bytes: usize, body_bytes: usize) -> bool {
    sql_calls >= SEARCH_SQL_BUDGET
        || transfer_bytes > SEARCH_TRANSFER_BUDGET
        || body_bytes > SEARCH_BODY_BUDGET
}

/// Compare semantic results in public order: score, time, then ID, all descending. / 按分数、时间、ID 全部降序比较语义结果。
pub fn semantic_rank(a: (f64, i64, &str), b: (f64, i64, &str)) -> std::cmp::Ordering {
    b.0.total_cmp(&a.0)
        .then_with(|| b.1.cmp(&a.1))
        .then_with(|| b.2.cmp(a.2))
}

/// True when a row follows a keyset marker in descending time/ID order. / 判断降序时间与 ID 排序中记录是否位于游标之后。
pub fn search_keyset_before(row: (i64, &str), marker: (i64, &str)) -> bool {
    row.0 < marker.0 || (row.0 == marker.0 && row.1 < marker.1)
}

/// Keep only the best K semantic hits while visiting every eligible row. / 遍历全部符合条件的记录时，仅保留最优 K 条语义结果。
pub fn retain_semantic<T, F>(selected: &mut Vec<T>, candidate: T, keep: usize, rank: F)
where
    F: for<'a> Fn(&'a T) -> (f64, i64, &'a str),
{
    if keep == 0 {
        return;
    }
    if selected.len() < keep {
        selected.push(candidate);
        return;
    }
    let Some(worst) = selected
        .iter()
        .enumerate()
        .max_by(|(_, a), (_, b)| semantic_rank(rank(a), rank(b)))
        .map(|(index, _)| index)
    else {
        return;
    };
    if semantic_rank(rank(&candidate), rank(&selected[worst])) == std::cmp::Ordering::Less {
        selected[worst] = candidate;
    }
}

/// Select only columns needed by the predicates or response. / 只读取谓词或响应需要的列。
fn search_projection(input: &SearchRequest) -> String {
    let subject = if input.title.is_some() {
        "subject"
    } else {
        "'' AS subject"
    };
    let sender = if input.from.is_some() {
        "sender"
    } else {
        "'' AS sender"
    };
    let recipients = if input.to.is_some() {
        "recipients_json"
    } else {
        "'[]' AS recipients_json"
    };
    let body = if input.body.is_some() {
        "body_text"
    } else {
        "'' AS body_text"
    };
    let metadata = if input.metadata.as_ref().is_some_and(|m| !m.is_empty()) {
        "metadata_json"
    } else {
        "'{}' AS metadata_json"
    };
    let vector = if input.semantic.is_some() {
        "embedding_json,embedding_model,embedding_dimensions,embedding_input_version"
    } else {
        "NULL AS embedding_json"
    };
    format!("SELECT id,address,direction,{sender},{recipients},{subject},{body},{metadata},received_at,is_read,has_html,has_text,attachment_count,'' AS r2_key,size_bytes,{vector} FROM messages WHERE owner_iss=?1 AND owner_sub=?2 AND deleted_at IS NULL")
}

/// Large title/metadata values use smaller pages; ordinary summaries can scan 64 IDs at once. / 大型主题或元数据使用小页，普通摘要每次可扫描 64 个 ID。
fn search_page_size(input: &SearchRequest) -> usize {
    if input.title.is_some() || input.metadata.as_ref().is_some_and(|map| !map.is_empty()) {
        16
    } else {
        SEARCH_PAGE_SIZE
    }
}

/// Rehydrate compact summaries without loading unbounded subject headers. / 重建紧凑摘要时避免载入无界的主题头字段。
fn search_summary_projection() -> &'static str {
    "SELECT id,address,direction,sender,recipients_json,substr(subject,1,2048) AS subject,CASE WHEN length(subject)>2048 THEN 1 ELSE 0 END AS subject_truncated,'' AS body_text,'{}' AS metadata_json,received_at,is_read,has_html,has_text,attachment_count,'' AS r2_key,size_bytes,NULL AS embedding_json FROM messages WHERE owner_iss=?1 AND owner_sub=?2 AND deleted_at IS NULL"
}

/// Make the indexed structural predicates explicit; never use SQLite LIKE as an exact text oracle. / 显式构造可索引的结构谓词，不将 SQLite LIKE 当作精确文本判定。
fn search_page_query(
    input: &SearchRequest,
    user: &Principal,
    after: Option<i64>,
    before: Option<i64>,
    high_water: i64,
    marker: Option<&(i64, String)>,
) -> (String, Vec<JsValue>) {
    let mut sql = search_projection(input);
    let mut binds = vec![bind_str(&user.iss), bind_str(&user.sub)];
    if let Some(mailbox) = input.mailbox.as_deref() {
        sql.push_str(&format!(" AND address=?{}", binds.len() + 1));
        binds.push(bind_str(mailbox));
    }
    if let Some(read) = input.read {
        sql.push_str(&format!(" AND is_read=?{}", binds.len() + 1));
        binds.push(bind_num(read as i64));
    }
    if let Some(after) = after {
        sql.push_str(&format!(" AND received_at>=?{}", binds.len() + 1));
        binds.push(bind_num(after));
    }
    if let Some(before) = before {
        sql.push_str(&format!(" AND received_at<?{}", binds.len() + 1));
        binds.push(bind_num(before));
    }
    sql.push_str(&format!(" AND received_at<?{}", binds.len() + 1));
    binds.push(bind_num(high_water));
    if let Some((time, id)) = marker {
        let index = binds.len() + 1;
        sql.push_str(&format!(
            " AND (received_at<?{index} OR (received_at=?{index} AND id<?{}))",
            index + 1
        ));
        binds.push(bind_num(*time));
        binds.push(bind_str(id));
    }
    sql.push_str(&format!(
        " ORDER BY received_at DESC,id DESC LIMIT {}",
        search_page_size(input)
    ));
    (sql, binds)
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

/// A text predicate is compiled once per request, not once per candidate. / 文本谓词每次请求仅编译一次，不按候选邮件重复编译。
struct TextPredicate(regex::Regex);

impl TextPredicate {
    fn new(value: &str, regex: bool, case_sensitive: bool) -> AppResult<Self> {
        if value.len() > 256 {
            return Err(AppError::bad("invalid_pattern"));
        }
        let expression = if regex {
            value.to_owned()
        } else {
            regex::escape(value)
        };
        regex::RegexBuilder::new(&expression)
            .case_insensitive(!case_sensitive)
            .size_limit(1 << 20)
            .dfa_size_limit(1 << 20)
            .build()
            .map(Self)
            .map_err(|_| AppError::bad("invalid_pattern"))
    }

    fn matches(&self, value: &str) -> bool {
        self.0.is_match(value)
    }
}

struct SearchMatcher {
    title: Option<TextPredicate>,
    from: Option<TextPredicate>,
    to: Option<TextPredicate>,
    body: Option<TextPredicate>,
    metadata: Vec<(String, TextPredicate)>,
}

impl SearchMatcher {
    fn new(input: &SearchRequest) -> AppResult<Self> {
        let regex = input.regex.unwrap_or(false);
        let case = input.case_sensitive.unwrap_or(false);
        let compile = |term: &Option<String>| {
            term.as_deref()
                .map(|s| TextPredicate::new(s, regex, case))
                .transpose()
        };
        let mut metadata = Vec::new();
        for (key, value) in input.metadata.as_ref().into_iter().flat_map(|m| m.iter()) {
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
            metadata.push((key.clone(), TextPredicate::new(value, regex, case)?));
        }
        Ok(Self {
            title: compile(&input.title)?,
            from: compile(&input.from)?,
            to: compile(&input.to)?,
            body: compile(&input.body)?,
            metadata,
        })
    }

    fn has_body(&self) -> bool {
        self.body.is_some()
    }

    fn matches_without_body(&self, row: &MessageRow) -> bool {
        if self
            .title
            .as_ref()
            .is_some_and(|p| !p.matches(&row.subject))
            || self.from.as_ref().is_some_and(|p| !p.matches(&row.sender))
            || self
                .to
                .as_ref()
                .is_some_and(|p| !p.matches(&row.recipients_json))
        {
            return false;
        }
        if self.metadata.is_empty() {
            return true;
        }
        let metadata: serde_json::Value =
            serde_json::from_str(&row.metadata_json).unwrap_or_default();
        self.metadata.iter().all(|(key, term)| {
            metadata
                .get(key)
                .and_then(|value| value.as_str())
                .is_some_and(|value| term.matches(value))
        })
    }

    fn matches_body(&self, body: &str) -> bool {
        self.body
            .as_ref()
            .is_none_or(|predicate| predicate.matches(body))
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

/// Reserve all exposure dimensions before submission. Earlier buckets remain
/// conservatively charged if a later bucket fails; no provider call occurs.
/// 提交前预留所有风险维度；后续额度失败时前序桶保守计费，但不调用提供商。
async fn charge_outbound_quotas(
    database: &D1Database,
    user: &Principal,
    draft: &Draft,
) -> AppResult<()> {
    let recipients = outbound_recipient_count(draft);
    reserve_quota(database, "send", user, recipients, 50).await?;
    let global = Principal {
        iss: "_global".into(),
        sub: "_global".into(),
    };
    reserve_quota(database, "send_global", &global, recipients, 10_000).await?;
    reserve_quota(database, "send_messages", user, 1, 20).await?;
    reserve_window_quota(database, "send_hour", user, 1, 5, 3_600_000).await?;
    for recipient in draft
        .manifest
        .to
        .iter()
        .chain(&draft.manifest.cc)
        .chain(&draft.manifest.bcc)
    {
        reserve_quota(database, &recipient_quota_kind(recipient), user, 1, 10).await?;
    }
    Ok(())
}

/// A single CAS winner claims quota; a quota failure releases its local claim
/// and removes a never-submitted newly created key to prevent D1 growth.
/// 单个 CAS 胜者预留额度；额度失败时释放本地占有，并清除从未提交的新键以防 D1 膨胀。
async fn reserve_outbound_budget(
    database: &D1Database,
    user: &Principal,
    draft: &Draft,
    idem: &str,
    inserted_new: bool,
) -> AppResult<()> {
    let claim = database.prepare("UPDATE send_requests SET state='reserving',reservation_started_at=?4 WHERE owner_iss=?1 AND owner_sub=?2 AND idem_key=?3 AND state='preparing' AND quota_reserved=0")
        .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(idem),bind_num(now())])?.run().await?;
    if claim.meta()?.and_then(|m| m.changes).unwrap_or(0) != 1 {
        return Err(AppError::conflict("send_in_progress"));
    }
    let charged = charge_outbound_quotas(database, user, draft).await;
    if charged.is_err() {
        let _ = database.prepare("UPDATE send_requests SET state='preparing',reservation_started_at=NULL WHERE owner_iss=?1 AND owner_sub=?2 AND idem_key=?3 AND state='reserving'")
            .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(idem)])?.run().await;
        if inserted_new {
            let _ = database.prepare("DELETE FROM send_requests WHERE owner_iss=?1 AND owner_sub=?2 AND idem_key=?3 AND state='preparing' AND quota_reserved=0")
                .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(idem)])?.run().await;
        }
    }
    charged?;
    database.prepare("UPDATE send_requests SET quota_reserved=1,state='preparing',reservation_started_at=NULL WHERE owner_iss=?1 AND owner_sub=?2 AND idem_key=?3 AND state='reserving'")
        .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(idem)])?.run().await?;
    Ok(())
}

async fn send_message(
    req: &mut Request,
    env: &Env,
    user: &Principal,
    request_id: &str,
    trace: &Trace,
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
    let envelope_json =
        outbound_envelope_json(&draft).map_err(|_| AppError::bad("invalid_mail_fields"))?;
    #[derive(Deserialize)]
    struct SendRow {
        payload_hash: String,
        message_id: Option<String>,
        state: String,
        quota_reserved: i64,
        rejection_code: Option<String>,
    }
    let existing = database.prepare("SELECT payload_hash,message_id,state,quota_reserved,rejection_code FROM send_requests WHERE owner_iss=?1 AND owner_sub=?2 AND idem_key=?3")
        .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(&idem)])?.first::<SendRow>(None).await?;
    let (id, quota_reserved, inserted_new) = if let Some(row) = existing {
        if row.payload_hash != payload_hash {
            return Err(AppError::conflict("idempotency_payload_mismatch"));
        }
        if row.state == "sent" || row.state == "accepted" {
            return Ok(Response::from_json(&serde_json::json!({"id":row.message_id,"state":"accepted","request_id":request_id}))?.with_status(202));
        }
        if row.state == "rejected" {
            return Err(row
                .rejection_code
                .as_deref()
                .and_then(stored_rejection)
                .unwrap_or_else(|| AppError::conflict("send_outcome_unknown")));
        }
        if row.state != "preparing" {
            return Err(AppError::conflict("send_outcome_unknown"));
        }
        check_send_policy(env, &database, user, &draft, &idem).await?;
        (
            row.message_id
                .ok_or_else(|| AppError::conflict("send_outcome_unknown"))?,
            row.quota_reserved != 0,
            false,
        )
    } else {
        // A held account must not manufacture unbounded idempotency rows.
        // 被停用账户不得通过生成幂等键无限填充 D1。
        check_send_policy(env, &database, user, &draft, &idem).await?;
        let id = uuid::Uuid::new_v4().to_string();
        let admitted = database.prepare("INSERT INTO send_requests(owner_iss,owner_sub,idem_key,payload_hash,message_id,state,created_at) VALUES(?1,?2,?3,?4,?5,'preparing',?6)")
            .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(&idem),bind_str(&payload_hash),bind_str(&id),bind_num(now())])?.run().await;
        if admitted.is_err() {
            // The SQL trigger may have raced an operator hold; preserve the
            // public hold code instead of misreporting that race as a replay.
            // SQL 触发器可能与管理员停用竞争；应返回停用码而非误报幂等冲突。
            check_send_policy(env, &database, user, &draft, &idem).await?;
            return Err(AppError::conflict("send_in_progress"));
        }
        (id, false, true)
    };
    if !quota_reserved {
        reserve_outbound_budget(&database, user, &draft, &idem, inserted_new).await?;
    }
    let r2_key = format!("messages/{id}.zip");
    if let Err(err) = reserve_storage(&database, &id, user, bytes.len() as i64).await {
        // A full mailbox is definitive: retain charged quota but not a fresh
        // never-submitted idempotency row that could accumulate every day.
        // 邮箱满为确定性拒绝：额度照常消耗，但不永久保留尚未提交的新幂等记录。
        if inserted_new && err.code == "mailbox_full" {
            let _ = database.prepare("DELETE FROM send_requests WHERE owner_iss=?1 AND owner_sub=?2 AND idem_key=?3 AND state='preparing'")
                .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(&idem)])?.run().await;
        }
        return Err(err);
    }
    let started = js_sys::Date::now();
    let archive_write = env
        .bucket("MAIL_BODIES")?
        .put(&r2_key, bytes.clone())
        .execute()
        .await;
    trace.phase(
        request_id,
        Phase::R2Write,
        archive_write.is_ok(),
        trace::elapsed_ms(started),
    );
    archive_write?;
    let transition = database.prepare("UPDATE send_requests SET state='submitting' WHERE owner_iss=?1 AND owner_sub=?2 AND idem_key=?3 AND state='preparing' AND quota_reserved=1")
        .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(&idem)])?.run().await?;
    if transition.meta()?.and_then(|m| m.changes).unwrap_or(0) != 1 {
        return Err(AppError::conflict("send_in_progress"));
    }
    if let Err(err) = check_send_policy(env, &database, user, &draft, &idem).await {
        // No provider call has happened; release the local claim for safe later retry.
        // 尚未调用提供商；释放本地占有状态，允许日后安全重试。
        database.prepare("UPDATE send_requests SET state='preparing' WHERE owner_iss=?1 AND owner_sub=?2 AND idem_key=?3 AND state='submitting'")
            .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(&idem)])?.run().await?;
        return Err(err);
    }
    let started = js_sys::Date::now();
    let send_result = platform::send(env, &draft).await;
    trace.phase(
        request_id,
        Phase::ProviderSend,
        send_result.is_ok(),
        trace::elapsed_ms(started),
    );
    let provider_id = match send_result {
        Ok(id) => id,
        Err(err) => {
            if let Some(rejection) = definitive_send_error(&err) {
                database.prepare("UPDATE send_requests SET state='rejected',rejection_code=?1 WHERE owner_iss=?2 AND owner_sub=?3 AND idem_key=?4 AND state='submitting'")
                    .bind(&[bind_str(rejection.code),bind_str(&user.iss),bind_str(&user.sub),bind_str(&idem)])?.run().await?;
                return Err(rejection);
            }
            let _ = database.prepare("UPDATE send_requests SET state='unknown' WHERE owner_iss=?1 AND owner_sub=?2 AND idem_key=?3")
                .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(&idem)])?.run().await;
            return Err(AppError {
                status: 503,
                code: "send_outcome_unknown",
            });
        }
    };
    database.prepare("UPDATE send_requests SET state='accepted',provider_id=?1,sender=?2,envelope_json=?3,request_id=?4 WHERE owner_iss=?5 AND owner_sub=?6 AND idem_key=?7 AND state='submitting'")
        .bind(&[bind_str(&provider_id),bind_str(&draft.manifest.from),bind_str(&envelope_json),bind_str(request_id),bind_str(&user.iss),bind_str(&user.sub),bind_str(&idem)])?.run().await?;
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

/// Count every To/Cc/Bcc envelope entry for daily sender exposure, not one ZIP per send. / 每个 To/Cc/Bcc 信封条目均计入每日发件风险，而非每 ZIP 只计一次。
fn outbound_recipient_count(draft: &Draft) -> i64 {
    (draft.manifest.to.len() + draft.manifest.cc.len() + draft.manifest.bcc.len()) as i64
}

/// Keep the complete private envelope on the idempotency row for late feedback,
/// independent of whether the user later deletes the message ZIP/index.
/// 在幂等记录中保留完整私密信封供延迟反馈使用，不依赖用户日后是否删除邮件 ZIP/索引。
fn outbound_envelope_json(draft: &Draft) -> serde_json::Result<String> {
    let envelope = draft
        .manifest
        .to
        .iter()
        .chain(&draft.manifest.cc)
        .chain(&draft.manifest.bcc)
        .map(|recipient| recipient.to_ascii_lowercase())
        .collect::<Vec<_>>();
    serde_json::to_string(&envelope)
}

/// Hash normalized recipients before storing per-recipient quota keys; never expose
/// the hash as a stable public identifier or use it instead of a D1 recipient block.
/// 收件人标准化后哈希用于额度键；哈希既不是公开稳定标识，也不代替 D1 禁止联系记录。
fn recipient_quota_kind(recipient: &str) -> String {
    let hash = Sha256::digest(recipient.to_ascii_lowercase().as_bytes());
    format!("send_recipient:{hash:x}")
}

/// Persist owner-visible recipient roles and the full envelope for later provider feedback attribution. / 为后续供应商反馈归因持久化仅所有者可见的收件人角色和完整信封。
fn outbound_metadata(draft: &Draft, provider_id: &str) -> serde_json::Value {
    let envelope_recipients = draft
        .manifest
        .to
        .iter()
        .chain(&draft.manifest.cc)
        .chain(&draft.manifest.bcc)
        .collect::<Vec<_>>();
    serde_json::json!({
        "message_id":provider_id,"in_reply_to":draft.manifest.in_reply_to,
        "content_type":if draft.html.is_some() {"multipart/alternative"} else {"text/plain"},
        "cc":&draft.manifest.cc,"bcc":&draft.manifest.bcc,
        "envelope_recipients":envelope_recipients,
        "attachment_name":draft.assets.iter().filter_map(|(m,_)|m.filename.as_deref()).collect::<Vec<_>>().join(" "),
        "attachments":draft.assets.iter().map(|(m,_)|m).collect::<Vec<_>>()
    })
}

async fn inbound(
    req: &mut Request,
    env: &Env,
    request_id: &str,
    trace: &mut Trace,
) -> AppResult<Response> {
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
    trace.accept_parent(req.headers().get("traceparent").ok().flatten().as_deref());
    trace.operation(Operation::Inbound);
    let envelope_to = req
        .headers()
        .get("x-amail-envelope-to")?
        .unwrap_or_default()
        .to_ascii_lowercase();
    let raw = req.bytes().await?;
    trace.measured_request_bytes(raw.len());
    if raw.is_empty() || raw.len() > 25 * 1024 * 1024 {
        return Err(AppError::bad("inbound_size"));
    }
    let database = db(env)?;
    #[derive(Deserialize)]
    struct Owner {
        owner_iss: String,
        owner_sub: String,
    }
    let started = js_sys::Date::now();
    let owner_result = database
        .prepare("SELECT owner_iss,owner_sub FROM addresses WHERE address=?1 AND state='active'")
        .bind(&[bind_str(&envelope_to)])?
        .first::<Owner>(None)
        .await;
    trace.phase(
        request_id,
        Phase::D1Read,
        owner_result.is_ok(),
        trace::elapsed_ms(started),
    );
    let owner = owner_result?.ok_or_else(AppError::not_found)?;
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
    let started = js_sys::Date::now();
    let raw_write = env
        .bucket("MAIL_BODIES")?
        .put(format!("raw/{id}.eml"), raw)
        .execute()
        .await;
    trace.phase(
        request_id,
        Phase::R2Write,
        raw_write.is_ok(),
        trace::elapsed_ms(started),
    );
    raw_write?;
    let started = js_sys::Date::now();
    let archive_write = env
        .bucket("MAIL_BODIES")?
        .put(&r2_key, archive.clone())
        .execute()
        .await;
    trace.phase(
        request_id,
        Phase::R2Write,
        archive_write.is_ok(),
        trace::elapsed_ms(started),
    );
    archive_write?;
    let attachments = metadata
        .get("attachments")
        .and_then(|v| v.as_array())
        .map_or(0, Vec::len);
    let metadata = metadata.to_string();
    let first_text = store_text(&database, &id, &text).await?;
    let started = js_sys::Date::now();
    let insert = database.prepare("INSERT INTO messages(id,address,owner_iss,owner_sub,direction,sender,recipients_json,subject,body_text,metadata_json,received_at,is_read,has_html,has_text,attachment_count,r2_key,size_bytes,storage_bytes,embedding_json,embedding_model,embedding_dimensions) VALUES(?1,?2,?3,?4,'inbound',?5,?6,?7,?8,?9,?10,0,?11,?12,?13,?14,?15,?16,?17,?18,?19)")
        .bind(&[bind_str(&id),bind_str(&envelope_to),bind_str(&owner.owner_iss),bind_str(&owner.owner_sub),bind_str(&sender),bind_str(&serde_json::to_string(&to).unwrap_or_default()),bind_str(&subject),bind_str(&first_text),bind_str(&metadata),bind_num(received_at),bind_num(has_html as i64),bind_num(has_text as i64),bind_num(attachments as i64),bind_str(&r2_key),bind_num(archive.len() as i64),bind_num(storage_bytes),JsValue::NULL,JsValue::NULL,JsValue::NULL])?.run().await;
    trace.phase(
        request_id,
        Phase::D1Write,
        insert.is_ok(),
        trace::elapsed_ms(started),
    );
    insert?;
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
    span_id: Option<String>,
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
    if batch.events.len() > 100
        || batch.events.iter().any(|e| {
            Operation::from_cli(&e.operation).is_none()
                || e.trace_id.len() > 64
                || !e
                    .trace_id
                    .chars()
                    .all(|c| c.is_ascii_hexdigit() || c == '-')
                || e.span_id
                    .as_ref()
                    .is_some_and(|id| !trace::valid_hex_id(id, 16))
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
        if trace::valid_hex_id(&event.trace_id, 32)
            && (event.status == 0 || (100..=599).contains(&event.status))
        {
            trace::client_event(
                Operation::from_cli(&event.operation).unwrap_or(Operation::Unknown),
                &event.trace_id,
                event.span_id.as_deref(),
                event.correlation_id.as_deref(),
                event.status,
                event.duration_ms,
                event.bytes_bucket,
            );
        }
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

    /// Multibyte content crossing the byte ceiling is clipped to a valid prefix.
    #[test]
    fn embedding_prefix_respects_utf8_and_provider_limit() {
        let cjk = format!("{}中", "a".repeat(11_999));
        let emoji = format!("{}😀", "a".repeat(11_998));
        assert_eq!(embedding_prefix(&cjk).len(), 11_999);
        assert_eq!(embedding_prefix(&emoji).len(), 11_998);
        assert_eq!(embedding_prefix(&"中".repeat(4_000)).len(), 12_000);
        assert_eq!(embedding_prefix(""), "");
        assert_eq!(embedding_prefix("short"), "short");
    }

    /// Atomic insert/backfill, tombstones, owner fairness and claim exclusion use
    /// the same SQL as the Worker rather than a provider-facing integration test.
    #[test]
    fn embedding_work_survives_poison_and_deletion() {
        let db = rusqlite::Connection::open_in_memory().unwrap();
        db.execute_batch(include_str!("../migrations/0001_initial.sql"))
            .unwrap();
        db.execute("INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,state,created_at) VALUES('a','a','i','a',0,'active',0)", [])
            .unwrap();
        for n in 0..25 {
            db.execute("INSERT INTO messages(id,address,owner_iss,owner_sub,direction,sender,recipients_json,subject,body_text,metadata_json,received_at,has_html,has_text,attachment_count,r2_key,size_bytes) VALUES(?1,'a','i','a','inbound','s','[]','subject','body','{}',?2,0,1,0,'k',1)", rusqlite::params![format!("old-{n:02}"),n]).unwrap();
        }
        let valid = serde_json::to_string(&[vec![1.0f32], vec![0.0; 255]].concat()).unwrap();
        db.execute("INSERT INTO messages(id,address,owner_iss,owner_sub,direction,sender,recipients_json,subject,body_text,metadata_json,received_at,has_html,has_text,attachment_count,r2_key,size_bytes,embedding_json,embedding_model,embedding_dimensions) VALUES('legacy-valid','a','i','a','inbound','s','[]','subject','body','{}',30,0,1,0,'k',1,?1,'qwen/qwen3-embedding-8b',256)",rusqlite::params![valid]).unwrap();
        db.execute("INSERT INTO messages(id,address,owner_iss,owner_sub,direction,sender,recipients_json,subject,body_text,metadata_json,received_at,has_html,has_text,attachment_count,r2_key,size_bytes,embedding_json,embedding_model,embedding_dimensions) VALUES('legacy-invalid','a','i','a','inbound','s','[]','subject','body','{}',31,0,1,0,'k',1,'[1]','qwen/qwen3-embedding-8b',256)",[]).unwrap();
        db.execute_batch(include_str!("../migrations/0007_embedding_work.sql"))
            .unwrap();
        assert_eq!(
            db.query_row(
                "SELECT embedding_input_version FROM messages WHERE id='legacy-valid'",
                [],
                |row| row.get::<_, i64>(0)
            )
            .unwrap(),
            1
        );
        assert_eq!(
            db.query_row(
                "SELECT COUNT(*) FROM embedding_work WHERE message_id='legacy-valid'",
                [],
                |row| row.get::<_, i64>(0)
            )
            .unwrap(),
            0
        );
        assert_eq!(
            db.query_row(
                "SELECT COUNT(*) FROM embedding_work WHERE message_id='legacy-invalid'",
                [],
                |row| row.get::<_, i64>(0)
            )
            .unwrap(),
            1
        );
        db.execute("INSERT INTO messages(id,address,owner_iss,owner_sub,direction,sender,recipients_json,subject,body_text,metadata_json,received_at,has_html,has_text,attachment_count,r2_key,size_bytes) VALUES('new','a','i','b','inbound','s','[]','subject','body','{}',100,0,1,0,'k',1)",[]).unwrap();
        let due = db
            .prepare(EMBEDDING_DUE_SQL)
            .unwrap()
            .query_map([0], |row| row.get::<_, String>(0))
            .unwrap()
            .collect::<rusqlite::Result<Vec<_>>>()
            .unwrap();
        assert_eq!(due.len(), 5); // Four old-owner rows, one new-owner row.
        assert_eq!(due[0], "old-00");
        assert_eq!(due[1], "new");
        db.execute("UPDATE embedding_work SET state='quarantined',last_error_code='invalid_request' WHERE message_id='old-00'",[]).unwrap();
        let due = db
            .prepare(EMBEDDING_DUE_SQL)
            .unwrap()
            .query_map([0], |row| row.get::<_, String>(0))
            .unwrap()
            .collect::<rusqlite::Result<Vec<_>>>()
            .unwrap();
        assert_eq!(due[0], "old-01");
        for n in 0..25 {
            db.execute("INSERT INTO messages(id,address,owner_iss,owner_sub,direction,sender,recipients_json,subject,body_text,metadata_json,received_at,has_html,has_text,attachment_count,r2_key,size_bytes) VALUES(?1,'a','i',?2,'inbound','s','[]','subject','body','{}',?3,0,1,0,'k',1)",rusqlite::params![format!("fresh-{n:02}"),format!("fresh-owner-{n:02}"),200+n]).unwrap();
        }
        db.execute(
            "UPDATE embedding_owner_schedule SET last_served_at=10 WHERE owner_sub='a'",
            [],
        )
        .unwrap();
        let many_owners = db
            .prepare(EMBEDDING_DUE_SQL)
            .unwrap()
            .query_map([0], |row| row.get::<_, String>(0))
            .unwrap()
            .collect::<rusqlite::Result<Vec<_>>>()
            .unwrap();
        assert_eq!(many_owners.len(), 20);
        assert!(!many_owners.iter().any(|id| id.starts_with("old-")));
        db.execute("UPDATE messages SET deleted_at=1 WHERE id='old-01'", [])
            .unwrap();
        assert_eq!(
            db.query_row(
                "SELECT COUNT(*) FROM embedding_work WHERE message_id='old-01'",
                [],
                |row| row.get::<_, i64>(0)
            )
            .unwrap(),
            0
        );
        let claim = format!("UPDATE embedding_work SET lease_until={EMBEDDING_LEASE_MS},lease_token='one' WHERE message_id='new' AND state='pending' AND next_attempt_at<=0 AND lease_until<=0 AND EXISTS (SELECT 1 FROM messages WHERE id='new' AND deleted_at IS NULL AND embedding_json IS NULL)");
        assert_eq!(db.execute(&claim, []).unwrap(), 1);
        assert_eq!(db.execute(&claim, []).unwrap(), 0);
        db.execute("UPDATE messages SET deleted_at=1 WHERE id='new'", [])
            .unwrap();
        assert_eq!(db.execute("UPDATE messages SET embedding_json='[1]' WHERE id='new' AND deleted_at IS NULL AND EXISTS (SELECT 1 FROM embedding_work WHERE message_id='new' AND lease_token='one')",[]).unwrap(),0);
    }

    /// Retry intervals are bounded but owner-specific, and transient errors are
    /// never implicitly treated as a permanent content defect.
    #[test]
    fn embedding_backoff_is_bounded() {
        assert!(EMBEDDING_LEASE_MS > 15 * 60_000);
        assert!(embedding_retry_delay(1, "a") >= 5 * 60_000);
        assert!(embedding_retry_delay(2, "a") >= 15 * 60_000);
        assert!(embedding_retry_delay(3, "a") >= 60 * 60_000);
        assert!(embedding_retry_delay(4, "a") >= 6 * 60 * 60_000);
        assert!(embedding_retry_delay(999, "a") <= 24 * 60 * 60_000);
        assert_ne!(embedding_retry_delay(2, "a"), embedding_retry_delay(2, "b"));
        use platform::EmbeddingFailure as Failure;
        assert_eq!(
            embedding_failure_policy(Failure::InvalidRequest, 1),
            (false, 0)
        );
        assert_eq!(
            embedding_failure_policy(Failure::InvalidInput, 1),
            (true, 0)
        );
        assert_eq!(embedding_failure_policy(Failure::Malformed, 2), (false, 0));
        assert_eq!(embedding_failure_policy(Failure::Malformed, 3), (true, 0));
        assert_eq!(
            embedding_failure_policy(Failure::RateLimited, 1),
            (false, 15 * 60_000)
        );
        assert_eq!(
            embedding_failure_policy(Failure::Dependency, 1),
            (false, 60 * 60_000)
        );
    }

    /// Provider internals never become public codes, including uncertain responses.
    #[test]
    fn rule_create_public_error_contract() {
        let cases = [
            (
                platform::RuleCreateFailure::Provider {
                    status: 403,
                    code: Some(10000),
                    capacity: false,
                },
                503,
                "routing_unavailable",
            ),
            (
                platform::RuleCreateFailure::Provider {
                    status: 400,
                    code: Some(1000),
                    capacity: true,
                },
                409,
                "capacity_exhausted",
            ),
            (
                platform::RuleCreateFailure::UnexpectedResponse { status: 200 },
                503,
                "routing_unavailable",
            ),
            (
                platform::RuleCreateFailure::Request,
                503,
                "routing_unavailable",
            ),
        ];
        for (provider, status, code) in cases {
            let public = rule_create_app_error(&provider);
            assert_eq!(public.status, status);
            assert_eq!(public.code, code);
        }
    }

    /// Legacy uploads remain valid while new uploads carry the client span ID.
    #[test]
    fn telemetry_span_is_optional_on_the_wire() {
        let base = serde_json::json!({
            "events":[{"operation":"messages.list","status":200,"duration_ms":1,
                "bytes_bucket":0,"trace_id":"0123456789abcdef0123456789abcdef",
                "correlation_id":null}]
        });
        let old: TelemetryBatch = serde_json::from_value(base.clone()).unwrap();
        assert!(old.events[0].span_id.is_none());
        let mut current = base;
        current["events"][0]["span_id"] = "0123456789abcdef".into();
        let new: TelemetryBatch = serde_json::from_value(current).unwrap();
        assert_eq!(new.events[0].span_id.as_deref(), Some("0123456789abcdef"));
    }

    /// Even an authenticated malicious URL can only become a fixed operation label.
    #[test]
    fn route_classification_does_not_retain_path_segments() {
        assert!(matches!(
            operation_for(Method::Get, &["v1", "messages", "secret@example.test"]),
            Operation::MessagesGet
        ));
        assert!(matches!(
            operation_for(Method::Get, &["secret@example.test"]),
            Operation::Unknown
        ));
    }

    /// A lease must be strictly in the future, independent of the manually
    /// attested send gates and the single-use canary exception.
    /// 租约必须严格晚于当前时间，与人工发信确认和单次金丝雀例外相互独立。
    #[test]
    fn role_monitor_lease_boundary_is_fail_closed() {
        assert!(!lease_is_current(0, 1_700_000_000_000));
        assert!(!lease_is_current(1_700_000_000_000, 1_700_000_000_000));
        assert!(lease_is_current(1_700_000_000_001, 1_700_000_000_000));
        assert!(canary_fallback_available("held"));
        assert!(!canary_fallback_available("allowed"));
    }

    /// Only structured provider refusals can be replayed as terminal; uncertain
    /// transport outcomes must remain unknown rather than being sent twice.
    /// 仅结构化提供商拒绝可作为终态重放；不确定的传输结果不能再次发送。
    #[test]
    fn provider_refusal_is_typed_and_terminal() {
        let suppressed = worker::Error::EmailRecipientSuppressed("private".into());
        let refusal = definitive_send_error(&suppressed).unwrap();
        assert_eq!(
            (refusal.status, refusal.code),
            (403, "recipient_suppressed")
        );
        assert_eq!(stored_rejection(refusal.code).unwrap().status, 403);
        assert!(definitive_send_error(&worker::Error::RustError("timeout".into())).is_none());
    }

    /// Equivalent-case recipients share one private quota key, unlike distinct recipients.
    /// 大小写等价的收件人共用私密额度键，不同收件人则不同。
    #[test]
    fn recipient_quota_key_is_canonical_and_not_plaintext() {
        let first = recipient_quota_kind("Person@Example.net");
        assert_eq!(first, recipient_quota_kind("person@example.net"));
        assert_ne!(first, recipient_quota_kind("other@example.net"));
        assert!(!first.contains("example"));
    }

    /// A launch canary cannot fan out, switch recipient, or use a second key.
    /// 上线金丝雀不能群发、替换收件人或使用第二个幂等键。
    #[test]
    fn canary_grant_is_single_recipient_and_key() {
        let mut draft = Draft {
            manifest: archive::SendManifest {
                version: 1,
                from: "a@mail.example.test".into(),
                to: vec!["Owner@Example.net".into()],
                cc: Vec::new(),
                bcc: Vec::new(),
                subject: "canary".into(),
                reply_to: None,
                in_reply_to: None,
                references: Vec::new(),
                assets: Vec::new(),
            },
            text: "test".into(),
            html: None,
            assets: Vec::new(),
        };
        let hash = format!("{:x}", Sha256::digest(b"owner@example.net"));
        assert!(canary_matches(&draft, "key", &hash, None));
        assert!(canary_matches(&draft, "key", &hash, Some("key")));
        assert!(!canary_matches(&draft, "other", &hash, Some("key")));
        draft.manifest.bcc.push("another@example.net".into());
        assert!(!canary_matches(&draft, "key", &hash, None));
    }

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
            subject_truncated: 0,
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
            embedding_model: None,
            embedding_dimensions: None,
            embedding_input_version: None,
        };
        let request = SearchRequest {
            title: Some("release [0-9]+".into()),
            metadata: Some([("message_id".into(), "abc@".into())].into()),
            regex: Some(true),
            case_sensitive: Some(false),
            ..Default::default()
        };
        assert!(SearchMatcher::new(&request)
            .unwrap()
            .matches_without_body(&row));
        let strict = SearchRequest {
            case_sensitive: Some(true),
            ..request
        };
        assert!(!SearchMatcher::new(&strict)
            .unwrap()
            .matches_without_body(&row));
        let body = SearchRequest {
            body: Some("rollback safely".into()),
            ..Default::default()
        };
        assert!(SearchMatcher::new(&body)
            .unwrap()
            .matches_body(&row.body_text));
        let strict_body = SearchRequest {
            body: Some("rollback safely".into()),
            case_sensitive: Some(true),
            ..Default::default()
        };
        assert!(!SearchMatcher::new(&strict_body)
            .unwrap()
            .matches_body(&row.body_text));
        let literal = TextPredicate::new("[0-9]+", false, true).unwrap();
        assert!(!literal.matches("Release 42"));
        assert!(literal.matches("Release [0-9]+"));
        assert!(!semantic_document_compatible(
            &row,
            Some("qwen/qwen3-embedding-8b")
        ));
        let mut row = row;
        row.embedding_model = Some("qwen/qwen3-embedding-8b".into());
        row.embedding_dimensions = Some(256);
        row.embedding_input_version = Some(1);
        assert!(semantic_document_compatible(
            &row,
            Some("qwen/qwen3-embedding-8b")
        ));
        assert!(!semantic_document_compatible(&row, Some("other-model")));
        assert!(!semantic_document_compatible(&row, None));
    }

    /// Score, time and ID form a total deterministic order for semantic cursors. / 分数、时间及 ID 为语义游标提供确定性全序。
    #[test]
    fn semantic_cursor_rank_is_lossless() {
        use std::cmp::Ordering;
        let best = (0.9000000000000001, 10, "z");
        let next = (0.9, 99, "z");
        assert_eq!(semantic_rank(best, next), Ordering::Less);
        assert_eq!(semantic_rank(next, best), Ordering::Greater);
        assert_eq!(
            semantic_rank((0.9, 10, "z"), (0.9, 10, "a")),
            Ordering::Less
        );
        let cursor = SearchCursor {
            version: 3,
            hash: "h".into(),
            high_water: 100,
            generation: 0,
            last_time: 10,
            last_id: "z".into(),
            last_score_bits: Some(best.0.to_bits()),
        };
        let decoded: SearchCursor =
            serde_json::from_slice(&serde_json::to_vec(&cursor).unwrap()).unwrap();
        assert_eq!(decoded.last_score_bits, Some(best.0.to_bits()));
    }

    /// Response-only searches must not project body, vector or archive keys. / 仅请求摘要时不得读取正文、向量或归档键。
    #[test]
    fn search_projection_is_minimal() {
        let list = search_projection(&SearchRequest::default());
        assert!(list.contains("'' AS body_text"));
        assert!(list.contains("NULL AS embedding_json"));
        assert!(list.contains("'' AS r2_key"));
        let detailed = search_projection(&SearchRequest {
            body: Some("hello".into()),
            semantic: Some("meaning".into()),
            metadata: Some([("message_id".into(), "id".into())].into()),
            ..Default::default()
        });
        assert!(detailed.contains("body_text,metadata_json"));
        assert!(detailed.contains("embedding_json,embedding_model,embedding_dimensions,embedding_input_version FROM messages"));
        assert!(search_summary_projection().contains("substr(subject,1,2048)"));
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

    /// One send to To, Cc and Bcc reserves three credits and retains owner-only attribution fields. / 一封发给 To、Cc、Bcc 的邮件预留三份额度，并保留仅所有者可读的归因字段。
    #[test]
    fn outbound_recipients_count_and_metadata() {
        let mut draft = Draft {
            manifest: archive::SendManifest {
                version: 1,
                from: "alice@mail.moesegfault.dev".into(),
                to: vec!["to@example.org".into()],
                cc: vec!["cc@example.org".into()],
                bcc: vec!["bcc@example.org".into()],
                subject: "hello".into(),
                reply_to: None,
                in_reply_to: None,
                references: Vec::new(),
                assets: Vec::new(),
            },
            text: "hello".into(),
            html: None,
            assets: Vec::new(),
        };
        assert_eq!(outbound_recipient_count(&draft), 3);
        let metadata = outbound_metadata(&draft, "provider-123");
        assert_eq!(metadata["message_id"], "provider-123");
        assert_eq!(metadata["cc"], serde_json::json!(["cc@example.org"]));
        assert_eq!(metadata["bcc"], serde_json::json!(["bcc@example.org"]));
        assert_eq!(
            metadata["envelope_recipients"],
            serde_json::json!(["to@example.org", "cc@example.org", "bcc@example.org"])
        );
        assert_eq!(
            serde_json::json!(&draft.manifest.to),
            serde_json::json!(["to@example.org"])
        );
        draft.manifest.cc.push("to@example.org".into());
        assert_eq!(outbound_recipient_count(&draft), 4);
    }

    /// Daily D1 upsert limits recipient entries rather than the number of ZIP submissions. / D1 每日 upsert 限制收件人条目数，而非 ZIP 提交次数。
    #[test]
    fn outbound_recipient_daily_limit() {
        let db = rusqlite::Connection::open_in_memory().unwrap();
        db.execute_batch(include_str!("../migrations/0001_initial.sql"))
            .unwrap();
        let reserve = "INSERT INTO daily_usage(kind,owner_iss,owner_sub,day,used) VALUES('send','iss','sub',7,?1) ON CONFLICT(kind,owner_iss,owner_sub,day) DO UPDATE SET used=used+excluded.used WHERE used+excluded.used<=100";
        for _ in 0..33 {
            assert_eq!(db.execute(reserve, [3]).unwrap(), 1);
        }
        assert_eq!(db.execute(reserve, [2]).unwrap(), 0);
        assert_eq!(db.execute(reserve, [1]).unwrap(), 1);
        assert_eq!(db.execute(reserve, [1]).unwrap(), 0);
        let used: i64 = db.query_row("SELECT used FROM daily_usage WHERE kind='send' AND owner_iss='iss' AND owner_sub='sub' AND day=7", [], |row| row.get(0)).unwrap();
        assert_eq!(used, 100);
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

    /// Search generation advances for inserts, read changes, and hard cleanup. / 插入、已读更新与最终清理均推进检索代际。
    #[test]
    fn search_generation_triggers_and_job_lease() {
        let db = rusqlite::Connection::open_in_memory().unwrap();
        for sql in [
            include_str!("../migrations/0001_initial.sql"),
            include_str!("../migrations/0002_reservation_lease.sql"),
            include_str!("../migrations/0003_storage_budget.sql"),
            include_str!("../migrations/0004_storage_ledger.sql"),
            include_str!("../migrations/0005_search_jobs.sql"),
        ] {
            db.execute_batch(sql).unwrap();
        }
        db.execute("INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,state,created_at) VALUES('a@mail.moesegfault.dev','a','iss','sub',0,'active',0)", []).unwrap();
        db.execute("INSERT INTO messages(id,address,owner_iss,owner_sub,direction,sender,recipients_json,subject,body_text,metadata_json,received_at,has_html,has_text,attachment_count,r2_key,size_bytes) VALUES('m','a@mail.moesegfault.dev','iss','sub','inbound','sender','[]','subject','body','{}',1,0,1,0,'r2',4)",[]).unwrap();
        let generation = |db: &rusqlite::Connection| -> i64 {
            db.query_row("SELECT generation FROM search_generations WHERE owner_iss='iss' AND owner_sub='sub'",[],|row| row.get(0)).unwrap()
        };
        assert_eq!(generation(&db), 1);
        db.execute("UPDATE messages SET is_read=1 WHERE id='m'", [])
            .unwrap();
        assert_eq!(generation(&db), 2);
        db.execute("DELETE FROM messages WHERE id='m'", []).unwrap();
        assert_eq!(generation(&db), 3);

        db.execute("INSERT INTO search_jobs(id,owner_iss,owner_sub,request_json,state_json,state,created_at,expires_at) VALUES('j','iss','sub','{}','{}','running',0,100)",[]).unwrap();
        assert_eq!(db.execute("UPDATE search_jobs SET state='advancing',version=version+1 WHERE id='j' AND state='running' AND version=0",[]).unwrap(),1);
        let checkpoint = "UPDATE search_jobs SET state_json='checkpoint',state='running',version=version+1 WHERE id='j' AND state='advancing' AND version=?1 AND COALESCE((SELECT generation FROM search_generations WHERE owner_iss='iss' AND owner_sub='sub'),0)=?2";
        assert_eq!(db.execute(checkpoint, [0, 3]).unwrap(), 0);
        assert_eq!(db.execute(checkpoint, [1, 2]).unwrap(), 0);
        assert_eq!(db.execute(checkpoint, [1, 3]).unwrap(), 1);
    }

    /// A long subject remains searchable but only a bounded preview enters replay summaries. / 长主题仍可检索，但重放摘要只载入有界预览。
    #[test]
    fn search_summary_subject_preview_bounds_response() {
        let db = rusqlite::Connection::open_in_memory().unwrap();
        db.execute_batch(include_str!("../migrations/0001_initial.sql"))
            .unwrap();
        db.execute("INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,state,created_at) VALUES('a@mail.moesegfault.dev','a','iss','sub',0,'active',0)", []).unwrap();
        let subject = "a".repeat(25_000);
        for index in 0..100 {
            db.execute("INSERT INTO messages(id,address,owner_iss,owner_sub,direction,sender,recipients_json,subject,body_text,metadata_json,received_at,has_html,has_text,attachment_count,r2_key,size_bytes) VALUES(?1,'a@mail.moesegfault.dev','iss','sub','inbound','sender','[]',?2,'','{}',1,0,1,0,'r2',1)",rusqlite::params![format!("m{index}"),&subject]).unwrap();
        }
        let mut query = search_summary_projection().to_owned();
        query.push_str(" ORDER BY id");
        let mut statement = db.prepare(&query).unwrap();
        let previews: Vec<(String, i64)> = statement
            .query_map(["iss", "sub"], |row| Ok((row.get(5)?, row.get(6)?)))
            .unwrap()
            .map(|item| item.unwrap())
            .collect();
        assert_eq!(previews.len(), 100);
        assert!(previews
            .iter()
            .all(|(preview, truncated)| preview.len() == 2048 && *truncated == 1));
        assert!(
            previews
                .iter()
                .map(|(preview, _)| preview.len())
                .sum::<usize>()
                < 2 * 1024 * 1024
        );
    }
}
