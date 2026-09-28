//! Isolated operator abuse/postmaster intake. / 独立的 abuse/postmaster 运营收件服务。
//!
//! Mail is durable in dedicated R2/D1, never in a user mailbox or search index.
//! 投诉邮件仅存于专属 R2/D1，不进入用户邮箱或检索索引。

use futures_util::StreamExt;
use jsonwebtoken::{decode, decode_header, Algorithm, DecodingKey, Validation};
use serde::Deserialize;
use std::cell::RefCell;
use worker::{
    console_warn, event, Context, Env, Fetch, ForwardableEmailMessage, Method, Range, Request,
    Response, Result, ScheduleContext, ScheduledEvent, SendEmail, SendEmailBuilder, Url,
};

/// Cloudflare's inbound cap; enforce while streaming rather than trusting rawSize.
/// Cloudflare 入站上限；流式读取时再次验证，不信任 rawSize 元数据。
const MAX_MIME_BYTES: usize = 25 * 1024 * 1024;
/// Bound browser preview and render it as escaped text, never as sender HTML.
/// 浏览器预览有界且仅以转义文本呈现，不执行发件方 HTML。
const PREVIEW_BYTES: usize = 16 * 1024;
const ACCESS_CACHE_MS: f64 = 300_000.0;

thread_local! {
    static ACCESS_KEYS: RefCell<Option<(f64, Vec<Jwk>)>> = const { RefCell::new(None) };
}

/// One Cloudflare Access RSA verification key. / 一把 Cloudflare Access RSA 验证公钥。
#[derive(Clone, Deserialize)]
struct Jwk {
    /// Key identifier. / 公钥标识。
    kid: String,
    /// Key type; only RSA is accepted. / 密钥类型；仅接受 RSA。
    kty: String,
    /// RSA modulus. / RSA 模数。
    n: String,
    /// RSA exponent. / RSA 指数。
    e: String,
    /// Optional algorithm constraint. / 可选的算法约束。
    alg: Option<String>,
    /// Optional signature-use constraint. / 可选的签名用途约束。
    #[serde(rename = "use")]
    usage: Option<String>,
}

/// Access team's public JWKS response. / Access 团队的公开 JWKS 响应。
#[derive(Deserialize)]
struct Jwks {
    /// Bounded key set. / 有界公钥集合。
    keys: Vec<Jwk>,
}

/// Identity-bearing application token, never a service token. / 带操作者身份的应用令牌，非服务令牌。
#[derive(Deserialize)]
struct AccessClaims {
    /// Exact Access issuer. / 精确 Access 签发者。
    iss: String,
    /// Stable per-account operator subject. / 操作者在该账户中的稳定主体 ID。
    sub: String,
    /// IdP-verified operator email. / IdP 核验的运营邮箱。
    email: String,
    /// Access app token kind. / Access 应用令牌类别。
    #[serde(rename = "type")]
    token_type: String,
    /// Application audience validated by the JWT library. / 由 JWT 库校验的应用受众。
    #[allow(dead_code)]
    aud: serde_json::Value,
    /// Expiry validated by the JWT library. / 由 JWT 库校验的过期时间。
    #[allow(dead_code)]
    exp: usize,
}

/// Privacy-minimal operator case projection. / 最小化个人信息的运营工单投影。
#[derive(Deserialize)]
struct CaseRow {
    /// Opaque case identifier. / 不透明工单标识。
    id: String,
    /// System role, never a user address. / 系统角色，非用户地址。
    route: String,
    /// Opaque private R2 object key. / 不透明的私有 R2 对象键。
    object_key: String,
    /// Durable review state. / 持久审查状态。
    state: String,
    /// Original MIME byte count. / 原始 MIME 字节数。
    size_bytes: i64,
    /// Unix creation seconds. / Unix 创建时间秒数。
    created_at: i64,
    /// Optional display-only UTC timestamp. / 可选的 UTC 展示时间。
    #[serde(default)]
    created_utc: Option<String>,
}

/// Cursor for bounded raw-object reconciliation. / 有界原文对象核对游标。
#[derive(Deserialize)]
struct GcCursor {
    /// Opaque R2 pagination cursor. / 不透明的 R2 分页游标。
    cursor: Option<String>,
}

/// Count-only D1 existence projection. / 仅计数的 D1 存在性投影。
#[derive(Deserialize)]
struct CountRow {
    /// Number of indexed cases for one object key. / 某对象键对应的工单数。
    count: i64,
}

/// Receive only the four exact, system-owned role aliases. / 仅接收四个精确的系统角色地址。
///
/// Storage failures are surfaced to SMTP, never acknowledged as successful intake.
/// 存储失败会反馈至 SMTP，绝不会假装报告已收妥。
#[event(email)]
pub async fn email(message: ForwardableEmailMessage, env: Env, _ctx: Context) -> Result<()> {
    receive(message, env)
        .await
        .map_err(|_| worker::Error::RustError("operator intake unavailable".into()))
}

/// Reserve, store and commit one bounded system report. / 预留、保存并提交一封有界系统报告。
async fn receive(message: ForwardableEmailMessage, env: Env) -> Result<()> {
    configured(&env)?;
    let role_domain = env.var("ROLE_DOMAIN")?.to_string();
    let allow_apex = env.var("ALLOW_APEX_ROLES")?.to_string() == "true";
    if !valid_role_config(&role_domain, allow_apex) {
        return Err(denied());
    }
    let Some(route) = role(&message.to(), &role_domain, allow_apex) else {
        message.set_reject("Recipient unavailable");
        return Ok(());
    };
    let raw_size = message.raw_size();
    if !raw_size.is_finite() || !(0.0..=MAX_MIME_BYTES as f64).contains(&raw_size) {
        message.set_reject("Message exceeds the 25 MiB intake limit");
        return Ok(());
    }
    let db = env.d1("OPS_DB")?;
    let bucket = env.bucket("OPS_REPORTS")?;
    let mut raw = Vec::with_capacity((raw_size as usize).min(MAX_MIME_BYTES));
    let mut stream = message.raw_byte_stream();
    while let Some(chunk) = stream.next().await {
        let chunk = chunk?;
        if chunk.len() > MAX_MIME_BYTES - raw.len() {
            message.set_reject("Message exceeds the 25 MiB intake limit");
            return Ok(());
        }
        raw.extend_from_slice(&chunk);
    }
    let id = uuid::Uuid::new_v4().to_string();
    let key = format!("reports/{id}.eml");
    db.prepare(
        "INSERT INTO cases(id,route,object_key,state,size_bytes) VALUES(?1,?2,?3,'receiving',?4)",
    )
    .bind(&[s(&id), s(route), s(&key), n(raw.len() as i64)])?
    .run()
    .await?;
    if bucket.put(&key, raw).execute().await.is_err() {
        // A completed failed PUT followed by a strongly consistent R2 miss is
        // safe to retire best-effort. If the follow-up read also fails, retain
        // the reservation for cron; orphan GC covers an unusual late commit.
        // PUT 失败后再次读取；确认缺失则尽力清理预留，读也失败则交给 cron。
        match bucket.get(&key).execute().await {
            Ok(None) => {
                let _ = db
                    .prepare("DELETE FROM cases WHERE id=?1 AND state='receiving'")
                    .bind(&[s(&id)])?
                    .run()
                    .await;
            }
            _ => {
                let _ = db
                    .prepare("UPDATE cases SET state='failed' WHERE id=?1 AND state='receiving'")
                    .bind(&[s(&id)])?
                    .run()
                    .await;
            }
        }
        return Err(worker::Error::RustError(
            "operator report storage failed".into(),
        ));
    }
    let committed = db.prepare(
        "UPDATE cases SET state='open',updated_at=unixepoch() WHERE id=?1 AND state IN ('receiving','failed')",
    )
    .bind(&[s(&id)])?
    .run()
    .await?;
    if committed.meta()?.and_then(|meta| meta.changes).unwrap_or(0) != 1 {
        let reconciled = case(&env, &id).await;
        if reconciled.is_err() {
            let _ = bucket.delete(&key).await;
        }
        let reconciled = reconciled?;
        if reconciled.object_key != key {
            return Err(worker::Error::RustError(
                "operator report commit lost".into(),
            ));
        }
    }
    Ok(())
}

/// An Access-only review UI; signature, issuer, audience and exact operator email
/// are checked inside the Worker even when an Access application fronts it.
/// Access 专用审查界面；即使外围已有 Access 应用，Worker 仍校验签名、签发者、受众和运营邮箱。
#[event(fetch)]
pub async fn fetch(req: Request, env: Env, _ctx: Context) -> Result<Response> {
    let response = match operator(&req, &env).await {
        Ok(actor) => match dispatch(req, env, &actor).await {
            Ok(response) => response,
            Err(_) => {
                console_warn!("operator intake UI unavailable");
                Response::error("Unavailable", 503)?
            }
        },
        Err(_) => Response::error("Unauthorized", 403)?,
    };
    private_response(response)
}

/// Route an already-authenticated operator request. / 路由已完成身份认证的运营请求。
async fn dispatch(req: Request, env: Env, actor: &str) -> Result<Response> {
    let path = req.path();
    match (req.method(), path.as_str()) {
        (Method::Get, "/") => list(&env, &req).await,
        (Method::Get, "/health") => health(&env).await,
        _ => {
            let segments: Vec<_> = path.trim_matches('/').split('/').collect();
            if segments.len() < 2 || segments[0] != "cases" || !valid_id(segments[1]) {
                return Response::error("Not found", 404);
            }
            match (req.method(), segments.as_slice()) {
                (Method::Get, ["cases", id]) => detail(&env, id).await,
                (Method::Get, ["cases", id, "raw"]) => raw(&env, id).await,
                (Method::Post, ["cases", id, "reviewed"]) => {
                    post_transition(&req, &env, id, actor, "reviewed").await
                }
                (Method::Post, ["cases", id, "closed"]) => {
                    post_transition(&req, &env, id, actor, "closed").await
                }
                (Method::Post, ["cases", id, "reopen"]) => {
                    post_transition(&req, &env, id, actor, "open").await
                }
                _ => Response::error("Not found", 404),
            }
        }
    }
}

/// Enforce same-origin form submission before state mutation. / 状态变更前强制表单同源提交。
async fn post_transition(
    req: &Request,
    env: &Env,
    id: &str,
    actor: &str,
    target: &str,
) -> Result<Response> {
    if verify_origin(req, env).is_err() {
        return Response::error("Unauthorized", 403);
    }
    transition(env, id, actor, target).await
}

/// Probe the dedicated case schema and R2 binding behind Access. / 在 Access 后探测专属工单表和 R2 绑定。
async fn health(env: &Env) -> Result<Response> {
    env.d1("OPS_DB")?
        .prepare("SELECT id FROM cases LIMIT 1")
        .all()
        .await?;
    let _ = env.bucket("OPS_REPORTS")?;
    Response::ok("operator access and case store ready")
}

/// List one bounded, state-filtered keyset page. / 列出一页有界、按状态筛选的键集结果。
async fn list(env: &Env, req: &Request) -> Result<Response> {
    let url = req.url()?;
    let state = url
        .query_pairs()
        .find(|(name, _)| name == "state")
        .map(|(_, value)| value.into_owned())
        .unwrap_or_else(|| "open".into());
    if !matches!(state.as_str(), "open" | "reviewed" | "closed") {
        return Response::error("Unknown case state", 400);
    }
    let cursor = url
        .query_pairs()
        .find(|(name, _)| name == "before")
        .map(|(_, value)| value.into_owned());
    let (before_time, before_id) = match cursor {
        Some(value) => {
            let (timestamp, id) = value.split_once('.').ok_or_else(denied)?;
            if !valid_id(id) {
                return Err(denied());
            }
            (
                timestamp.parse::<i64>().map_err(|_| denied())?,
                id.to_string(),
            )
        }
        None => (9_999_999_999_999, "~".into()),
    };
    let mut rows = env.d1("OPS_DB")?.prepare("SELECT id,route,object_key,state,size_bytes,created_at,strftime('%Y-%m-%d %H:%M:%SZ',created_at,'unixepoch') AS created_utc FROM cases WHERE state=?1 AND (created_at<?2 OR (created_at=?2 AND id<?3)) ORDER BY created_at DESC,id DESC LIMIT 101")
        .bind(&[s(&state), n(before_time), s(&before_id)])?
        .all().await?.results::<CaseRow>()?;
    let has_more = rows.len() > 100;
    rows.truncate(100);
    let mut body = String::from("<h1>Operator intake</h1><p>Private abuse and postmaster reports. Raw mail stays on Cloudflare.</p><nav><a href=\"/?state=open\">Open</a> · <a href=\"/?state=reviewed\">Reviewed</a> · <a href=\"/?state=closed\">Closed</a></nav><table><tr><th>Case</th><th>Role</th><th>State</th><th>UTC timestamp</th></tr>");
    for row in &rows {
        body.push_str(&format!(
            "<tr><td><a href=\"/cases/{}\">{}</a></td><td>{}</td><td>{}</td><td>{}</td></tr>",
            escape(&row.id),
            escape(&row.id),
            escape(&row.route),
            escape(&row.state),
            row.created_utc.as_deref().unwrap_or("unknown")
        ));
    }
    body.push_str("</table>");
    if has_more {
        if let Some(last) = rows.last() {
            body.push_str(&format!(
                "<p><a href=\"/?state={}&amp;before={}.{}\">Next 100 cases →</a></p>",
                state,
                last.created_at,
                escape(&last.id)
            ));
        }
    }
    page(body)
}

/// Resolve a visible case by opaque ID only. / 仅凭不透明 ID 解析可见工单。
async fn case(env: &Env, id: &str) -> Result<CaseRow> {
    env.d1("OPS_DB")?.prepare("SELECT id,route,object_key,state,size_bytes,created_at,strftime('%Y-%m-%d %H:%M:%SZ',created_at,'unixepoch') AS created_utc FROM cases WHERE id=?1 AND state IN ('open','reviewed','closed')")
        .bind(&[s(id)])?.first::<CaseRow>(None).await?
        .ok_or_else(|| worker::Error::RustError("case missing".into()))
}

/// Render a bounded escaped MIME preview. / 呈现有界且转义的 MIME 预览。
async fn detail(env: &Env, id: &str) -> Result<Response> {
    let row = case(env, id).await?;
    let object = env
        .bucket("OPS_REPORTS")?
        .get(&row.object_key)
        .range(Range::Prefix {
            length: PREVIEW_BYTES as u64,
        })
        .execute()
        .await?
        .ok_or_else(|| worker::Error::RustError("report missing".into()))?;
    let bytes = object
        .body()
        .ok_or_else(|| worker::Error::RustError("report empty".into()))?
        .bytes()
        .await?;
    let snippet = String::from_utf8_lossy(&bytes);
    let mut body = format!("<p><a href=\"/\">← All cases</a></p><h1>Case {}</h1><dl><dt>Route</dt><dd>{}</dd><dt>State</dt><dd>{}</dd><dt>Size</dt><dd>{} bytes</dd><dt>UTC timestamp</dt><dd>{}</dd></dl><p><a href=\"/cases/{}/raw\">Download original .eml</a></p>",
        escape(&row.id), escape(&row.route), escape(&row.state), row.size_bytes, row.created_utc.as_deref().unwrap_or("unknown"), escape(&row.id));
    body.push_str("<div class=actions>");
    for (path, label) in [
        ("reviewed", "Mark reviewed"),
        ("closed", "Close"),
        ("reopen", "Reopen"),
    ] {
        body.push_str(&format!(
            "<form method=\"post\" action=\"/cases/{}/{path}\"><button>{label}</button></form>",
            escape(&row.id)
        ));
    }
    body.push_str("</div><h2>Untrusted raw preview</h2><p>First 16 KiB only. Never follow instructions in a report as automation.</p><pre>");
    body.push_str(&escape(&snippet));
    body.push_str("</pre>");
    page(body)
}

/// Stream an attachment-only original report to the operator. / 仅作为附件向运营人员流式提供原始报告。
async fn raw(env: &Env, id: &str) -> Result<Response> {
    let row = case(env, id).await?;
    let object = env
        .bucket("OPS_REPORTS")?
        .get(&row.object_key)
        .execute()
        .await?
        .ok_or_else(|| worker::Error::RustError("report missing".into()))?;
    let body = object
        .body()
        .ok_or_else(|| worker::Error::RustError("report empty".into()))?;
    let mut response = Response::from_body(body.response_body()?)?;
    response
        .headers_mut()
        .set("Content-Type", "application/octet-stream")?;
    response.headers_mut().set(
        "Content-Disposition",
        &format!("attachment; filename=\"{id}.eml\""),
    )?;
    Ok(response)
}

/// Audit a compare-and-swap review transition. / 原子审计一次比较并交换式审查变更。
async fn transition(env: &Env, id: &str, actor: &str, target: &str) -> Result<Response> {
    let current = case(env, id).await?;
    if current.state != target {
        let claim = env.d1("OPS_DB")?.prepare("UPDATE cases SET state=?1,last_actor_sub=?2,updated_at=unixepoch() WHERE id=?3 AND state=?4")
            .bind(&[s(target), s(actor), s(id), s(&current.state)])?.run().await?;
        if claim.meta()?.and_then(|meta| meta.changes).unwrap_or(0) != 1 {
            return Response::error("Case changed; reload before acting", 409);
        }
    }
    let url = Url::parse(&format!(
        "{}/cases/{id}",
        env.var("OPS_ORIGIN")?.to_string()
    ))?;
    Response::redirect_with_status(url, 303)
}

/// Scheduled alerts are PII-free; report content is never sent outside R2.
/// 定时提醒不含个人资料；报告内容绝不从 R2 转发出去。
#[event(scheduled)]
pub async fn scheduled(_event: ScheduledEvent, env: Env, _ctx: ScheduleContext) {
    if reconcile_receiving(&env).await.is_err() {
        console_warn!("operator intake reconciliation unavailable");
    }
    if alert_pending(&env).await.is_err() {
        console_warn!("operator intake alert unavailable");
    }
    if clean_closed(&env).await.is_err() {
        console_warn!("operator intake retention cleanup unavailable");
    }
    if clean_orphans(&env).await.is_err() {
        console_warn!("operator intake orphan cleanup unavailable");
    }
}

/// Retry metadata-only official-sender notices. / 重试仅含元数据的官方发件提醒。
async fn alert_pending(env: &Env) -> Result<()> {
    let rows = env.d1("OPS_DB")?.prepare("SELECT id,route,object_key,state,size_bytes,created_at FROM cases WHERE state='open' AND alert_state='pending' ORDER BY created_at LIMIT 10")
        .all().await?.results::<CaseRow>()?;
    if rows.is_empty() {
        return Ok(());
    }
    let recipient = env.secret("OPERATOR_ALERT_EMAIL")?.to_string();
    if recipient.is_empty() || !recipient.contains('@') {
        return Err(worker::Error::RustError(
            "alert recipient not configured".into(),
        ));
    }
    let origin = env.var("OPS_ORIGIN")?.to_string();
    let binding: SendEmail = env.get_binding("OFFICIAL_EMAIL")?;
    for row in rows {
        let recipients = vec![recipient.clone()];
        let subject = "moeSegFault operator mail requires review";
        let builder =
            SendEmailBuilder::new_with_str_and_slice("mail@moesegfault.dev", &recipients, subject);
        builder.set_text(&format!("A system mail report is ready for operator review.\nCase: {}\nRole: {}\nOpen: {origin}/cases/{}\nNo report content is included in this alert.\n", row.id, row.route, row.id));
        binding.send_with_builder(&builder).await?;
        env.d1("OPS_DB")?
            .prepare("UPDATE cases SET alert_state='sent' WHERE id=?1 AND alert_state='pending'")
            .bind(&[s(&row.id)])?
            .run()
            .await?;
    }
    Ok(())
}

/// Complete an interrupted R2→D1 transition. Retire missing-R2 metadata only
/// after seven days, far beyond an SMTP invocation, so an in-flight PUT cannot
/// be acknowledged without a committed case.
/// 完成中断的 R2→D1 转换；缺失对象的元数据七天后才清理，远超 SMTP 执行窗口。
async fn reconcile_receiving(env: &Env) -> Result<()> {
    let now = (js_sys::Date::now() / 1000.0) as i64;
    let cutoff = now - 600;
    let retire_before = now - 7 * 86_400;
    let rows = env.d1("OPS_DB")?.prepare("SELECT id,route,object_key,state,size_bytes,created_at FROM cases WHERE state IN ('receiving','failed') AND created_at<?1 ORDER BY created_at LIMIT 20")
        .bind(&[n(cutoff)])?.all().await?.results::<CaseRow>()?;
    for row in rows {
        if env
            .bucket("OPS_REPORTS")?
            .get(&row.object_key)
            .execute()
            .await?
            .is_some()
        {
            env.d1("OPS_DB")?.prepare("UPDATE cases SET state='open',updated_at=unixepoch() WHERE id=?1 AND state IN ('receiving','failed')")
                .bind(&[s(&row.id)])?.run().await?;
        } else if row.created_at < retire_before {
            env.d1("OPS_DB")?.prepare("DELETE FROM cases WHERE id=?1 AND state IN ('receiving','failed') AND created_at<?2")
                .bind(&[s(&row.id), n(retire_before)])?.run().await?;
        }
    }
    Ok(())
}

/// Hide then retire closed cases after 180 days. / 结案 180 天后先隐藏再清理工单。
async fn clean_closed(env: &Env) -> Result<()> {
    let cutoff = (js_sys::Date::now() / 1000.0) as i64 - 180 * 86_400;
    let rows = env.d1("OPS_DB")?.prepare("SELECT id,route,object_key,state,size_bytes,created_at FROM cases WHERE state='expiring' OR (state='closed' AND updated_at<?1) ORDER BY updated_at LIMIT 20")
        .bind(&[n(cutoff)])?.all().await?.results::<CaseRow>()?;
    for row in rows {
        if row.state == "closed" {
            let claim = env.d1("OPS_DB")?
                .prepare("UPDATE cases SET state='expiring' WHERE id=?1 AND state='closed' AND updated_at<?2")
                .bind(&[s(&row.id), n(cutoff)])?
                .run()
                .await?;
            if claim.meta()?.and_then(|meta| meta.changes).unwrap_or(0) != 1 {
                continue;
            }
        }
        env.bucket("OPS_REPORTS")?.delete(&row.object_key).await?;
        env.d1("OPS_DB")?
            .prepare("DELETE FROM case_audit WHERE case_id=?1")
            .bind(&[s(&row.id)])?
            .run()
            .await?;
        env.d1("OPS_DB")?
            .prepare("DELETE FROM cases WHERE id=?1 AND state='expiring'")
            .bind(&[s(&row.id)])?
            .run()
            .await?;
    }
    Ok(())
}

/// Walk at most 100 R2 keys per cron tick and delete unindexed originals only
/// after seven days. The cursor avoids repeatedly scanning a hot first page.
/// 每次定时最多检查 100 个 R2 键；七天后才清理无索引原文，游标避免反复扫描首页。
async fn clean_orphans(env: &Env) -> Result<()> {
    let db = env.d1("OPS_DB")?;
    let bucket = env.bucket("OPS_REPORTS")?;
    let cursor = db
        .prepare("SELECT cursor FROM gc_cursor WHERE id=1")
        .first::<GcCursor>(None)
        .await?
        .ok_or_else(|| worker::Error::RustError("operator GC cursor missing".into()))?;
    let mut listing = bucket.list().prefix("reports/").limit(100);
    if let Some(cursor) = cursor.cursor {
        listing = listing.cursor(cursor);
    }
    let page = listing.execute().await?;
    let cutoff_ms = js_sys::Date::now() as u64 - 7 * 86_400_000;
    for object in page.objects() {
        if object.uploaded().as_millis() >= cutoff_ms {
            continue;
        }
        let key = object.key();
        let count = db
            .prepare("SELECT COUNT(*) AS count FROM cases WHERE object_key=?1")
            .bind(&[s(&key)])?
            .first::<CountRow>(None)
            .await?
            .ok_or_else(|| worker::Error::RustError("operator GC query failed".into()))?;
        if count.count == 0 {
            bucket.delete(&key).await?;
        }
    }
    let next = if page.truncated() {
        page.cursor()
    } else {
        None
    };
    let value = next
        .as_deref()
        .map(s)
        .unwrap_or(wasm_bindgen::JsValue::NULL);
    db.prepare("UPDATE gc_cursor SET cursor=?1 WHERE id=1")
        .bind(&[value])?
        .run()
        .await?;
    Ok(())
}

/// Validate a signed Access app JWT and exact operator allowlist. / 验证 Access 应用 JWT 签名和精确操作者白名单。
async fn operator(req: &Request, env: &Env) -> Result<String> {
    configured(env)?;
    let team = env.var("TEAM_DOMAIN")?.to_string();
    let aud = env.var("ACCESS_AUD")?.to_string();
    let expected = env.secret("OPERATOR_EMAIL")?.to_string();
    let token = req
        .headers()
        .get("Cf-Access-Jwt-Assertion")?
        .ok_or_else(denied)?;
    if token.len() > 8192 {
        return Err(denied());
    }
    let header = decode_header(&token).map_err(|_| denied())?;
    if header.alg != Algorithm::RS256 {
        return Err(denied());
    }
    let kid = header.kid.ok_or_else(denied)?;
    let keys = access_keys(&team, false).await?;
    let mut key = keys.iter().find(|key| key.kid == kid && compatible(key));
    let fresh;
    if key.is_none() {
        fresh = access_keys(&team, true).await?;
        key = fresh.iter().find(|key| key.kid == kid && compatible(key));
    }
    let key = key.ok_or_else(denied)?;
    let decoding = DecodingKey::from_rsa_components(&key.n, &key.e).map_err(|_| denied())?;
    let mut validation = Validation::new(Algorithm::RS256);
    validation.set_issuer(&[&team]);
    validation.set_audience(&[&aud]);
    validation.required_spec_claims.insert("sub".into());
    let claims = decode::<AccessClaims>(&token, &decoding, &validation)
        .map_err(|_| denied())?
        .claims;
    if claims.iss != team
        || claims.sub.is_empty()
        || claims.token_type != "app"
        || !claims.email.eq_ignore_ascii_case(&expected)
    {
        return Err(denied());
    }
    Ok(claims.sub)
}

/// Refuse both SMTP intake and HTTP review until every critical operator realm
/// and alert binding is configured. This is stricter than a reachable health URL.
/// 在运营身份域和提醒绑定齐备前，同时拒绝 SMTP 收取与 HTTP 审查。
fn configured(env: &Env) -> Result<()> {
    let team = env.var("TEAM_DOMAIN")?.to_string();
    let aud = env.var("ACCESS_AUD")?.to_string();
    let origin = env.var("OPS_ORIGIN")?.to_string();
    let expected = env.secret("OPERATOR_EMAIL")?.to_string();
    let alert = env.secret("OPERATOR_ALERT_EMAIL")?.to_string();
    let team_url = Url::parse(&team)?;
    let expected_origin = if env.var("ROLE_DOMAIN")?.to_string() == "mail.moesegfault.dev" {
        "https://ops.moesegfault.dev"
    } else {
        "https://ops-staging.moesegfault.dev"
    };
    if team_url.scheme() != "https"
        || !team_url.host_str().is_some_and(|host| {
            host.ends_with(".cloudflareaccess.com") && !host.starts_with("replace")
        })
        || team_url.path() != "/"
        || team_url.query().is_some()
        || team_url.fragment().is_some()
        || aud.starts_with("REPLACE_")
        || aud.is_empty()
        || origin != expected_origin
        || !expected.contains('@')
        || !alert.contains('@')
        || alert
            .to_ascii_lowercase()
            .ends_with("@mail.moesegfault.dev")
        || alert
            .to_ascii_lowercase()
            .ends_with("@mail-staging.moesegfault.dev")
        || matches!(
            alert.to_ascii_lowercase().as_str(),
            "abuse@moesegfault.dev" | "postmaster@moesegfault.dev"
        )
    {
        return Err(denied());
    }
    let _: SendEmail = env.get_binding("OFFICIAL_EMAIL")?;
    Ok(())
}

/// Reject JWKs of another algorithm or usage. / 拒绝算法或用途不符的 JWK。
fn compatible(key: &Jwk) -> bool {
    key.kty == "RSA"
        && key.alg.as_deref().is_none_or(|alg| alg == "RS256")
        && key.usage.as_deref().is_none_or(|usage| usage == "sig")
}

/// Cache bounded public Access keys briefly; retry once on rotation. / 短时缓存有界 Access 公钥，轮换时再取一次。
async fn access_keys(team: &str, force: bool) -> Result<Vec<Jwk>> {
    let now = js_sys::Date::now();
    if !force {
        if let Some(keys) = ACCESS_KEYS.with(|cell| {
            cell.borrow()
                .as_ref()
                .filter(|(until, _)| *until > now)
                .map(|(_, keys)| keys.clone())
        }) {
            return Ok(keys);
        }
    }
    let url = Url::parse(&format!("{team}/cdn-cgi/access/certs"))?;
    let mut response = Fetch::Url(url).send().await?;
    if response.status_code() != 200 {
        return Err(denied());
    }
    let set: Jwks = response.json().await.map_err(|_| denied())?;
    if set.keys.is_empty() || set.keys.len() > 32 {
        return Err(denied());
    }
    ACCESS_KEYS.with(|cell| *cell.borrow_mut() = Some((now + ACCESS_CACHE_MS, set.keys.clone())));
    Ok(set.keys)
}

/// Block cross-origin browser form submissions. / 阻断跨源浏览器表单提交。
fn verify_origin(req: &Request, env: &Env) -> Result<()> {
    let origin = req.headers().get("Origin")?.ok_or_else(denied)?;
    if origin != env.var("OPS_ORIGIN")?.to_string() {
        return Err(denied());
    }
    Ok(())
}

/// Apply no-store and restrictive document headers to every response. / 为所有响应添加禁止缓存和严格文档头。
fn private_response(mut response: Response) -> Result<Response> {
    let headers = response.headers_mut();
    headers.set("Cache-Control", "no-store, private")?;
    headers.set("Referrer-Policy", "no-referrer")?;
    headers.set("X-Content-Type-Options", "nosniff")?;
    headers.set("X-Frame-Options", "DENY")?;
    headers.set("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")?;
    Ok(response)
}

/// Render a self-contained CSP-restricted operator page. / 渲染自包含且受 CSP 限制的运营页面。
fn page(body: String) -> Result<Response> {
    Response::from_html(format!("<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>moeSegFault Operator Mail</title><style>body{{font:16px system-ui;margin:3rem auto;max-width:65rem;padding:0 1rem;background:#111827;color:#e5e7eb}}a{{color:#93c5fd}}table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #374151;padding:.75rem;text-align:left}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#030712;padding:1rem;max-height:28rem;overflow:auto}}button{{padding:.6rem 1rem;background:#2563eb;color:white;border:0;border-radius:.4rem;cursor:pointer}}.actions{{display:flex;gap:.6rem}}dt{{font-weight:bold}}dd{{margin:0 0 .7rem}}</style><main>{body}</main></html>"))
}

/// Map only literal system addresses to a role. / 仅把精确系统地址映射成角色。
fn role(address: &str, domain: &str, allow_apex: bool) -> Option<&'static str> {
    let address = address.to_ascii_lowercase();
    let abuse = format!("abuse@{domain}");
    let postmaster = format!("postmaster@{domain}");
    match address.as_str() {
        value if value == abuse.as_str() || (allow_apex && value == "abuse@moesegfault.dev") => {
            Some("abuse")
        }
        value
            if value == postmaster.as_str()
                || (allow_apex && value == "postmaster@moesegfault.dev") =>
        {
            Some("postmaster")
        }
        _ => None,
    }
}

/// Pin apex permission to production only. / 只允许生产环境使用根域名角色。
fn valid_role_config(domain: &str, allow_apex: bool) -> bool {
    (domain == "mail.moesegfault.dev" && allow_apex)
        || (domain == "mail-staging.moesegfault.dev" && !allow_apex)
}

/// Keep URLs free of user data and SQL-shaped identifiers. / 确保 URL 只含不透明 UUID，不含用户数据。
fn valid_id(id: &str) -> bool {
    uuid::Uuid::parse_str(id).is_ok()
}

/// Escape untrusted MIME preview bytes before HTML insertion. / 原始 MIME 预览插入 HTML 前先转义。
fn escape(value: &str) -> String {
    value
        .chars()
        .map(|ch| match ch {
            '&' => "&amp;".to_string(),
            '<' => "&lt;".to_string(),
            '>' => "&gt;".to_string(),
            '"' => "&quot;".to_string(),
            '\'' => "&#39;".to_string(),
            _ => ch.to_string(),
        })
        .collect()
}

/// Return a content-free access failure. / 返回不泄露内容的访问失败。
fn denied() -> worker::Error {
    worker::Error::RustError("operator access denied".into())
}

/// Bind a D1 text parameter. / 绑定 D1 文本参数。
fn s(value: &str) -> wasm_bindgen::JsValue {
    wasm_bindgen::JsValue::from_str(value)
}

/// Bind a safe-range D1 numeric parameter. / 绑定安全范围内的 D1 数值参数。
fn n(value: i64) -> wasm_bindgen::JsValue {
    wasm_bindgen::JsValue::from_f64(value as f64)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Roles never become user mailbox aliases. / 角色地址绝不成为用户邮箱别名。
    #[test]
    fn accepts_only_system_roles() {
        assert!(valid_role_config("mail.moesegfault.dev", true));
        assert!(!valid_role_config("mail-staging.moesegfault.dev", true));
        assert_eq!(
            role(
                "POSTMASTER@mail.moesegfault.dev",
                "mail.moesegfault.dev",
                true
            ),
            Some("postmaster")
        );
        assert_eq!(
            role("abuse@moesegfault.dev", "mail.moesegfault.dev", true),
            Some("abuse")
        );
        assert_eq!(
            role(
                "abuse@mail-staging.moesegfault.dev",
                "mail-staging.moesegfault.dev",
                false
            ),
            Some("abuse")
        );
        assert_eq!(
            role(
                "abuse@moesegfault.dev",
                "mail-staging.moesegfault.dev",
                false
            ),
            None
        );
        assert_eq!(
            role("postmaster@other.dev", "mail.moesegfault.dev", true),
            None
        );
        assert_eq!(
            role(
                "abuse+tag@mail.moesegfault.dev",
                "mail.moesegfault.dev",
                true
            ),
            None
        );
    }

    /// Unsafe sender markup is never interpreted in preview. / 发件方标记在预览中永不执行。
    #[test]
    fn preview_is_escaped() {
        assert_eq!(
            escape("<script>x&y</script>"),
            "&lt;script&gt;x&amp;y&lt;/script&gt;"
        );
    }
}
