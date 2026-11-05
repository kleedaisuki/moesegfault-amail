//! Service-authenticated Billing bridge. Financial consent is owned by Subscribe,
//! while mailbox ownership remains on the original Identity pairwise subject.

use futures_util::StreamExt;
use serde::Deserialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::cell::Cell;
use worker::{Env, Fetch, Headers, Method, Request, RequestInit, Response};

use crate::auth::Principal;
use crate::database::Database;
use crate::trace::{Phase, Trace};
use crate::{bind_num, bind_str, db, now, resource, AppError, AppResult};

/// Billing never receives a raw Identity subject or mutable email as owner key.
pub(crate) fn owner_id(user: &Principal) -> String {
    let mut hash = Sha256::new();
    hash.update(b"amail-owner-v020\0");
    hash.update((user.iss.len() as u64).to_be_bytes());
    hash.update(user.iss.as_bytes());
    hash.update((user.sub.len() as u64).to_be_bytes());
    hash.update(user.sub.as_bytes());
    format!("{:x}", hash.finalize())
}

/// Only known staging/production endpoints may receive the service credential.
struct Configuration {
    base: String,
    subscribe: String,
    return_url: String,
}

impl Configuration {
    fn load(env: &Env) -> AppResult<Self> {
        let issuer = env.var("IDENTITY_ISSUER")?.to_string();
        let expected = match issuer.as_str() {
            "https://identity-staging.moesegfault.dev" => (
                "https://billing-staging.moesegfault.dev",
                "https://subscribe-staging.moesegfault.dev",
                "https://amail-staging.moesegfault.dev/billing/return",
            ),
            "https://identity.moesegfault.dev" => (
                "https://billing.moesegfault.dev",
                "https://subscribe.moesegfault.dev",
                "https://amail.moesegfault.dev/billing/return",
            ),
            _ => return Err(unavailable()),
        };
        let result = Self {
            base: env.var("BILLING_BASE_URL")?.to_string(),
            subscribe: env.var("BILLING_SUBSCRIBE_ORIGIN")?.to_string(),
            return_url: env.var("BILLING_RETURN_URL")?.to_string(),
        };
        if (
            result.base.as_str(),
            result.subscribe.as_str(),
            result.return_url.as_str(),
        ) != expected
        {
            return Err(unavailable());
        }
        Ok(result)
    }

    /// The URL contains an opaque navigation handle, never tokens or grant codes.
    fn valid_authorization_url(&self, raw: &str) -> bool {
        let Ok(url) = url::Url::parse(raw) else {
            return false;
        };
        url.origin().ascii_serialization() == self.subscribe
            && url.username().is_empty()
            && url.password().is_none()
            && url.query().is_none()
            && url.fragment().is_none()
            && raw.len() <= 512
            && url.path().starts_with("/amail/authorize/")
    }
}

/// Decode a bounded successful response only; error bodies are never exposed.
async fn exchange(
    request: Request,
    signal: &worker::AbortSignal,
    status: &Cell<Option<u16>>,
) -> AppResult<Value> {
    let mut response = Fetch::Request(request).send_with_signal(signal).await?;
    status.set(Some(response.status_code()));
    if !(200..=299).contains(&response.status_code()) {
        return Err(unavailable());
    }
    let mut bytes = Vec::new();
    let mut stream = response.stream()?;
    while let Some(chunk) = stream.next().await {
        let chunk = chunk?;
        if bytes.len().saturating_add(chunk.len()) > 64 * 1024 {
            return Err(unavailable());
        }
        bytes.extend_from_slice(&chunk);
    }
    serde_json::from_slice(&bytes).map_err(|_| unavailable())
}

/// One native exchange is timed and parented; uncertain writes reuse their key.
async fn call(
    env: &Env,
    method: Method,
    path: &str,
    body: Option<Value>,
    key: Option<&str>,
    request_id: &str,
    trace: &Trace,
    origin_traceparent: Option<&str>,
) -> AppResult<Value> {
    let config = Configuration::load(env)?;
    let span = trace
        .dependency(request_id, Phase::BillingHttp)
        .continue_from(origin_traceparent);
    let headers = Headers::new();
    headers.set(
        "Authorization",
        &format!("Bearer {}", env.secret("BILLING_SERVICE_KEY")?.to_string()),
    )?;
    headers.set("Content-Type", "application/json")?;
    headers.set("traceparent", &span.traceparent())?;
    if let Some(key) = key {
        headers.set("Idempotency-Key", key)?;
    }
    let mut init = RequestInit::new();
    init.with_method(method)
        .with_headers(headers)
        .with_redirect(worker::RequestRedirect::Manual);
    if let Some(body) = body {
        init.with_body(Some(wasm_bindgen::JsValue::from_str(&body.to_string())));
    }
    let request = Request::new_with_init(&format!("{}{path}", config.base), &init)?;
    let controller = worker::AbortController::default();
    let signal = controller.signal();
    let status = Cell::new(None);
    let exchange = Box::pin(exchange(request, &signal, &status));
    let deadline = Box::pin(worker::Delay::from(std::time::Duration::from_secs(15)));
    let result = match futures_util::future::select(exchange, deadline).await {
        futures_util::future::Either::Left((result, _)) => result,
        futures_util::future::Either::Right((_, pending)) => {
            drop(pending);
            controller.abort();
            Err(unavailable())
        }
    };
    span.finish_http(result.is_ok(), status.get());
    result
}

/// Closed public creation request; the agent proposes, never approves, a plan.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Create {
    action: String,
    plan: Option<String>,
    #[serde(default)]
    device_code: bool,
}

/// Reject oversized financial navigation input before allocating an arbitrary body.
async fn create_body(req: &mut Request) -> AppResult<Create> {
    let mut stream = req.stream()?;
    let mut bytes = Vec::new();
    while let Some(chunk) = stream.next().await {
        let chunk = chunk?;
        if bytes.len().saturating_add(chunk.len()) > 2048 {
            return Err(AppError {
                status: 413,
                code: "request_too_large",
            });
        }
        bytes.extend_from_slice(&chunk);
    }
    serde_json::from_slice(&bytes).map_err(|_| AppError::bad("invalid_json"))
}

/// Durable owner-scoped session, saved before its first service submission.
#[derive(Deserialize)]
struct Session {
    id: String,
    action: String,
    requested_plan: String,
    remote_id: Option<String>,
    authorization_url: Option<String>,
    state: String,
    expires_at: i64,
    user_code: Option<String>,
}

/// Trusted receipt vocabulary is still validated before entitlement projection.
#[derive(Deserialize)]
struct Binding {
    owner_id: String,
    product_id: String,
    plan_id: String,
    overage_budget_micros: i64,
    currency: String,
    contract_version: String,
    valid_until: Option<i64>,
    updated_at: i64,
    authorization_id: String,
}

/// Historical CNY receipts may preserve plan access, never authorize new USD spending.
fn valid_binding_currency(currency: &str, contract: &str) -> bool {
    matches!(
        (currency, contract),
        ("USD", "amail-v0.2.0-usd-v1") | ("CNY", "amail-v0.2.0")
    )
}

fn unavailable() -> AppError {
    AppError {
        status: 503,
        code: "billing_unavailable",
    }
}

/// Reject ambiguous plan names rather than deriving privileges from display copy.
fn plan(raw: &str) -> AppResult<&'static str> {
    match raw {
        "free" | "amail-free" => Ok("free"),
        "lite" | "amail-lite" => Ok("lite"),
        "plus" | "amail-plus" => Ok("plus"),
        _ => Err(AppError::bad("invalid_billing_plan")),
    }
}

fn canonical_uuid(raw: &str) -> AppResult<String> {
    let uuid = uuid::Uuid::parse_str(raw).map_err(|_| AppError::bad("invalid_idempotency_key"))?;
    if uuid.get_version_num() != 4 || uuid.to_string() != raw {
        return Err(AppError::bad("invalid_idempotency_key"));
    }
    Ok(uuid.to_string())
}

/// Remote 192-bit navigation handles are opaque, not local UUIDs or URL paths.
fn valid_remote_id(raw: &str) -> bool {
    (32..=128).contains(&raw.len())
        && raw
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
}

async fn session(database: &Database, user: &Principal, id: &str) -> AppResult<Session> {
    database.prepare("SELECT id,action,requested_plan,remote_id,authorization_url,state,expires_at,user_code FROM billing_sessions WHERE owner_iss=?1 AND owner_sub=?2 AND id=?3")
        .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(id)])?
        .first::<Session>(None).await?.ok_or_else(AppError::not_found)
}

fn session_response(row: &Session, env: &Env) -> AppResult<Response> {
    let mut body = json!({"session_id":row.id,"state":row.state,
        "authorization_url":row.authorization_url,"expires_at":row.expires_at,"retry_after_ms":if row.user_code.is_some() {2000} else {1500}});
    if let Some(code) = &row.user_code {
        let uri = verification_uri(env)?;
        body["user_code"] = json!(code);
        body["verification_uri"] = json!(uri);
        body["verification_uri_complete"] = json!(format!("{uri}?user_code={code}"));
        body["expires_in"] = json!((row.expires_at - now() / 1000).max(0));
        body["interval"] = json!(2);
    }
    Ok(Response::from_json(&body)?)
}

const CODE_ALPHABET: &[u8; 32] = b"0123456789ABCDEFGHJKMNPQRSTVWXYZ";

fn new_user_code() -> String {
    let random = uuid::Uuid::new_v4();
    let bytes = random.as_bytes();
    let mut code = String::with_capacity(11);
    // These ten UUID bytes exclude version/variant bits; each contributes five
    // independent random bits. The code only locates a financial navigation page.
    for (index, byte) in [0, 1, 2, 3, 4, 5, 7, 9, 10, 11].iter().enumerate() {
        if index == 5 {
            code.push('-');
        }
        code.push(CODE_ALPHABET[(bytes[*byte] & 31) as usize] as char);
    }
    code
}

fn normalize_user_code(raw: &str) -> Option<String> {
    let plain: String = raw
        .chars()
        .filter(|ch| !ch.is_ascii_whitespace() && *ch != '-')
        .map(|ch| ch.to_ascii_uppercase())
        .collect();
    if plain.len() != 10 || !plain.bytes().all(|byte| CODE_ALPHABET.contains(&byte)) {
        return None;
    }
    Some(format!("{}-{}", &plain[..5], &plain[5..]))
}

fn verification_uri(env: &Env) -> AppResult<&'static str> {
    match env.var("IDENTITY_ISSUER")?.to_string().as_str() {
        "https://identity.moesegfault.dev" => Ok("https://mail.moesegfault.dev/billing/device"),
        "https://identity-staging.moesegfault.dev" => {
            Ok("https://mail-staging.moesegfault.dev/billing/device")
        }
        _ => Err(unavailable()),
    }
}

fn navigation_page(env: &Env, message: &str) -> AppResult<Response> {
    let subscribe = Configuration::load(env)?.subscribe;
    let mut response = Response::from_html(format!("<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content=\"width=device-width,initial-scale=1\"><title>amail billing</title><main><h1>Open your amail billing request</h1><p>Enter the code from your own amail terminal. Continue only if you requested this billing session. This step does not approve a subscription or spending limit; review and confirm those on Subscribe.</p><p>{message}</p><form method=post action=/billing/device><label>Code <input name=user_code autocomplete=off required maxlength=32></label><button type=submit>Continue to Subscribe</button></form></main></html>"))?;
    let headers = response.headers_mut();
    headers.set("Cache-Control", "no-store")?;
    headers.set("Referrer-Policy", "no-referrer")?;
    headers.set("X-Content-Type-Options", "nosniff")?;
    headers.set(
        "Content-Security-Policy",
        &format!("default-src 'none'; form-action 'self' {subscribe}; frame-ancestors 'none'; base-uri 'none'"),
    )?;
    Ok(response)
}

/// A public short code locates an existing navigation session; it never produces
/// a receipt, changes a plan, or replaces Subscribe's authenticated human consent.
pub(crate) async fn device_navigation(req: &mut Request, env: &Env) -> AppResult<Response> {
    let fields = if req.method() == Method::Get {
        req.url()?.query().unwrap_or_default().as_bytes().to_vec()
    } else {
        let mut stream = req.stream()?;
        let mut bytes = Vec::new();
        while let Some(chunk) = stream.next().await {
            let chunk = chunk?;
            if bytes.len() + chunk.len() > 256 {
                return Err(AppError::bad("invalid_billing_user_code"));
            }
            bytes.extend_from_slice(&chunk);
        }
        bytes
    };
    let fields: Vec<_> = url::form_urlencoded::parse(&fields).collect();
    if fields.is_empty() {
        return navigation_page(env, "");
    }
    let code = fields
        .iter()
        .find(|(key, _)| key == "user_code")
        .and_then(|(_, value)| normalize_user_code(value));
    let Some(code) = code else {
        return navigation_page(env, "Check the code shown by your terminal.");
    };
    #[derive(Deserialize)]
    struct Navigation {
        authorization_url: String,
    }
    let navigation = db(env)?.prepare("SELECT authorization_url FROM billing_sessions WHERE user_code=?1 AND state='pending' AND expires_at>?2 AND authorization_url IS NOT NULL")
        .bind(&[bind_str(&code),bind_num(now()/1000)])?
        .first::<Navigation>(None).await?;
    let Some(navigation) = navigation else {
        return navigation_page(
            env,
            "This code is unavailable or expired. Check the original terminal session.",
        );
    };
    if !Configuration::load(env)?.valid_authorization_url(&navigation.authorization_url) {
        return Err(unavailable());
    }
    let mut response = Response::empty()?.with_status(303);
    response
        .headers_mut()
        .set("Location", &navigation.authorization_url)?;
    response
        .headers_mut()
        .set("Referrer-Policy", "no-referrer")?;
    response.headers_mut().set("Cache-Control", "no-store")?;
    Ok(response)
}

/// Reserve an idempotent local intent before an external operation can succeed.
pub(crate) async fn create(
    req: &mut Request,
    env: &Env,
    user: &Principal,
    request_id: &str,
    trace: &Trace,
) -> AppResult<Response> {
    let key = canonical_uuid(
        &req.headers()
            .get("Idempotency-Key")?
            .ok_or_else(|| AppError::bad("idempotency_key_required"))?,
    )?;
    let body = create_body(req).await?;
    if !matches!(body.action.as_str(), "subscribe" | "manage")
        || (body.action == "manage" && body.plan.is_some())
    {
        return Err(AppError::bad("invalid_billing_action"));
    }
    let database = db(env)?;
    let account = resource::status(&database, user).await?;
    let requested_plan = if body.action == "subscribe" {
        plan(
            body.plan
                .as_deref()
                .ok_or_else(|| AppError::bad("invalid_billing_plan"))?,
        )?
    } else {
        plan(&account.plan)?
    };
    let timestamp = now() / 1000;
    let user_code = body.device_code.then(new_user_code);
    database.prepare("INSERT INTO billing_sessions(id,owner_iss,owner_sub,action,requested_plan,created_at,expires_at,origin_traceparent,user_code) VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9) ON CONFLICT(owner_iss,owner_sub,id) DO NOTHING")
        .bind(&[bind_str(&key),bind_str(&user.iss),bind_str(&user.sub),bind_str(&body.action),bind_str(requested_plan),bind_num(timestamp),bind_num(timestamp+1800),bind_str(&trace.traceparent()),user_code.as_deref().map(bind_str).unwrap_or(wasm_bindgen::JsValue::NULL)])?.run().await?;
    let row = session(&database, user, &key).await?;
    if row.user_code.is_some() != body.device_code
        || row.action != body.action
        || (body.action == "subscribe" && row.requested_plan != requested_plan)
    {
        return Err(AppError::conflict("idempotency_conflict"));
    }
    if row.state != "pending" || row.remote_id.is_some() {
        return session_response(&row, env);
    }
    if row.expires_at <= timestamp {
        return expire(env, &database, user, &key).await;
    }
    let requested_plan = row.requested_plan.as_str();
    let config = Configuration::load(env)?;
    let remote = call(
        env,
        Method::Post,
        "/v1/service/amail/authorizations",
        Some(json!({
            "owner_id":owner_id(user),"plan_id":format!("amail-{requested_plan}"),
            "overage_budget_micros":0,"currency":"USD","return_url":config.return_url
        })),
        Some(&key),
        request_id,
        trace,
        None,
    )
    .await?;
    let remote_id = remote
        .get("authorization_id")
        .and_then(Value::as_str)
        .ok_or_else(unavailable)?;
    if !valid_remote_id(remote_id) {
        return Err(unavailable());
    }
    let url = remote
        .get("authorization_url")
        .and_then(Value::as_str)
        .ok_or_else(unavailable)?;
    let expires_at = remote
        .get("expires_at")
        .and_then(Value::as_i64)
        .ok_or_else(unavailable)?;
    if !config.valid_authorization_url(url)
        || expires_at <= timestamp
        || expires_at > timestamp + 3600
    {
        return Err(unavailable());
    }
    database.prepare("UPDATE billing_sessions SET remote_id=?1,authorization_url=?2,expires_at=?3 WHERE owner_iss=?4 AND owner_sub=?5 AND id=?6 AND state='pending' AND remote_id IS NULL")
        .bind(&[bind_str(remote_id),bind_str(url),bind_num(expires_at),bind_str(&user.iss),bind_str(&user.sub),bind_str(&key)])?.run().await?;
    session_response(&session(&database, user, &key).await?, env)
}

async fn expire(env: &Env, database: &Database, user: &Principal, id: &str) -> AppResult<Response> {
    database.prepare("UPDATE billing_sessions SET state='expired' WHERE owner_iss=?1 AND owner_sub=?2 AND id=?3 AND state='pending'")
        .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(id)])?.run().await?;
    session_response(&session(database, user, id).await?, env)
}

/// Project only service-authenticated, product-scoped, unexpired consent receipts.
async fn apply(database: &Database, user: &Principal, value: &Value) -> AppResult<()> {
    let binding: Binding = serde_json::from_value(value.clone()).map_err(|_| unavailable())?;
    let timestamp = now() / 1000;
    let selected = plan(&binding.plan_id).map_err(|_| unavailable())?;
    if binding.owner_id != owner_id(user)
        || binding.product_id != "amail"
        || !valid_binding_currency(&binding.currency, &binding.contract_version)
        || binding.overage_budget_micros < 0
        || binding.overage_budget_micros > 1_000_000_000_000
        || binding.updated_at < 0
        || binding.updated_at > timestamp + 30
        || !valid_remote_id(&binding.authorization_id)
        || (selected != "free" && binding.valid_until.is_none())
    {
        return Err(unavailable());
    }
    let expired = binding.valid_until.is_some_and(|until| until <= timestamp);
    // Match the actual authority receipt, not whichever old session happened to be polled.
    // An out-of-band or legacy authority has no invented causal origin.
    #[derive(Deserialize)]
    struct Origin {
        origin_traceparent: Option<String>,
    }
    let origin = database.prepare("SELECT origin_traceparent FROM billing_sessions WHERE owner_iss=?1 AND owner_sub=?2 AND remote_id=?3 LIMIT 1")
        .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(&binding.authorization_id)])?
        .first::<Origin>(None).await?.and_then(|row| row.origin_traceparent);
    resource::apply_snapshot(
        database,
        user,
        &resource::Snapshot {
            plan: if expired {
                "free".into()
            } else {
                selected.into()
            },
            billing_owner_id: binding.owner_id,
            overage_budget_micros: if expired || binding.currency != "USD" {
                0
            } else {
                binding.overage_budget_micros
            },
            valid_until: if expired { None } else { binding.valid_until },
            authority_updated_at: binding.updated_at,
            authorization_id: binding.authorization_id,
            origin_traceparent: origin,
        },
    )
    .await
}

/// Polling cannot transfer another owner's receipt or grant privileges on redirect.
pub(crate) async fn poll(
    env: &Env,
    user: &Principal,
    id: &str,
    request_id: &str,
    trace: &Trace,
) -> AppResult<Response> {
    let id = canonical_uuid(id)?;
    let database = db(env)?;
    let row = session(&database, user, &id).await?;
    if row.state != "pending" {
        return session_response(&row, env);
    }
    let Some(remote_id) = row.remote_id.as_deref() else {
        if row.expires_at <= now() / 1000 {
            return expire(env, &database, user, &id).await;
        }
        return session_response(&row, env);
    };
    let receipt = call(
        env,
        Method::Get,
        &format!("/v1/service/amail/authorizations/{remote_id}"),
        None,
        None,
        request_id,
        trace,
        None,
    )
    .await?;
    let authorization = receipt.get("authorization").ok_or_else(unavailable)?;
    if authorization.get("id").and_then(Value::as_str) != Some(remote_id)
        || authorization.get("owner_id").and_then(Value::as_str) != Some(owner_id(user).as_str())
    {
        return Err(unavailable());
    }
    let remote_state = authorization
        .get("status")
        .and_then(Value::as_str)
        .ok_or_else(unavailable)?;
    let state = match remote_state {
        "approved" | "completed" => {
            if let Some(binding) = receipt.get("binding").filter(|value| !value.is_null()) {
                apply(&database, user, binding).await?;
            } else {
                // A newer authorization may already have superseded this receipt;
                // complete the old intent but project the current authority only.
                let current = call(
                    env,
                    Method::Get,
                    &format!("/v1/service/amail/accounts/{}", owner_id(user)),
                    None,
                    None,
                    request_id,
                    trace,
                    None,
                )
                .await?;
                apply(
                    &database,
                    user,
                    current
                        .get("binding")
                        .filter(|value| !value.is_null())
                        .ok_or_else(unavailable)?,
                )
                .await?;
            }
            "completed"
        }
        "pending" => "pending",
        "cancelled" | "denied" => "cancelled",
        "expired" => "expired",
        "failed" => "failed",
        _ => return Err(unavailable()),
    };
    database.prepare("UPDATE billing_sessions SET state=?1 WHERE owner_iss=?2 AND owner_sub=?3 AND id=?4 AND state='pending'")
        .bind(&[bind_str(state),bind_str(&user.iss),bind_str(&user.sub),bind_str(&id)])?.run().await?;
    session_response(&session(&database, user, &id).await?, env)
}

/// Refresh linked owners before mutations; unlinked community Free works offline.
pub(crate) async fn refresh(
    env: &Env,
    user: &Principal,
    request_id: &str,
    trace: &Trace,
) -> AppResult<()> {
    let database = db(env)?;
    let account = resource::status(&database, user).await?;
    if account.billing_owner_id.is_none() {
        return Ok(());
    }
    let receipt = call(
        env,
        Method::Get,
        &format!("/v1/service/amail/accounts/{}", owner_id(user)),
        None,
        None,
        request_id,
        trace,
        None,
    )
    .await?;
    if let Some(binding) = receipt.get("binding").filter(|value| !value.is_null()) {
        apply(&database, user, binding).await?;
    } else {
        return Err(unavailable());
    }
    Ok(())
}

/// Public status excludes service credentials, payer identities and mail contents.
pub(crate) async fn status(
    env: &Env,
    user: &Principal,
    request_id: &str,
    trace: &Trace,
) -> AppResult<Response> {
    refresh(env, user, request_id, trace).await?;
    let database = db(env)?;
    let current = resource::status(&database, user).await?;
    let temporary_limit = current.tmpaddr_limit();
    let mut account = serde_json::to_value(current).map_err(|_| unavailable())?;
    if let Some(object) = account.as_object_mut() {
        object.remove("billing_owner_id");
        object.remove("authorization_id");
        object.remove("origin_traceparent");
        object.insert("included_tmpaddr_addresses".into(), json!(temporary_limit));
    }
    Ok(Response::from_json(
        &json!({"api_version":"2","version":"0.2.0","account":account,
        "rates":{"currency":"USD","outbound_micros":1000,"storage_gb_month_micros":150_000,"address_month_micros":500_000},
        "settlement_state":"accrued_unsettled","payment_collection_available":false}),
    )?)
}

/// Minimal durable delivery metadata; neither message contents nor addresses are sent.
#[derive(Deserialize)]
struct Usage {
    /// Immutable denomination captured with the usage event.
    currency: String,
    event_id: String,
    billing_owner_id: String,
    period_start: i64,
    period_end: i64,
    meter: String,
    quantity: i64,
    amount_micros: i64,
    occurred_at: i64,
    authorization_id: String,
    authorized_at: i64,
    /// Opaque validated durable handoff, not a Billing payload field.
    origin_traceparent: Option<String>,
}

/// A successful transport is not settlement acknowledgement for another denomination.
fn usage_receipt_matches(receipt: &Value, event: &Usage) -> bool {
    let record = receipt.get("event").unwrap_or(receipt);
    record.get("event_id").and_then(Value::as_str) == Some(event.event_id.as_str())
        && record.get("currency").and_then(Value::as_str) == Some(event.currency.as_str())
        && record.get("amount_micros").and_then(Value::as_i64) == Some(event.amount_micros)
}

/// Fair bounded accounting and at-least-once outbox delivery share the scheduled
/// invocation's phase-scoped D1 handle and W3C trace. Remote ingestion is idempotent.
pub(crate) async fn maintain(
    env: &Env,
    database: &Database,
    trace: &Trace,
    request_id: &str,
) -> worker::Result<()> {
    #[derive(Deserialize)]
    struct Owner {
        owner_iss: String,
        owner_sub: String,
    }
    let owners=database.prepare("SELECT owner_iss,owner_sub FROM resource_accounts WHERE billing_owner_id IS NOT NULL ORDER BY accounting_tick,owner_iss,owner_sub LIMIT 2")
        .all().await?.results::<Owner>()?;
    for owner in owners {
        resource::accrue(
            database,
            &Principal {
                iss: owner.owner_iss,
                sub: owner.owner_sub,
                profile: None,
                enrollment_fence: false,
            },
        )
        .await
        .map_err(|_| worker::Error::RustError("billing_reconciliation_failed".into()))?;
    }
    let events=database.prepare("SELECT event_id,billing_owner_id,period_start,period_end,meter,quantity,amount_micros,occurred_at,authorization_id,authorized_at,origin_traceparent,currency FROM resource_outbox WHERE delivered_at IS NULL AND next_attempt_at<=unixepoch() ORDER BY next_attempt_at,occurred_at,event_id LIMIT 3")
        .all().await?.results::<Usage>()?;
    let mut failed = false;
    for event in events {
        database.ensure_remaining(1)?;
        let result=call(env,Method::Post,"/v1/service/amail/usage",Some(json!({
            "event_id":event.event_id,"owner_id":event.billing_owner_id,"currency":event.currency,
            "period_start":event.period_start,"period_end":event.period_end,"meter":event.meter,
                "quantity":event.quantity,"amount_micros":event.amount_micros,"occurred_at":event.occurred_at,
                "authorization_id":event.authorization_id,"authorized_at":event.authorized_at
        })),Some(&event.event_id),request_id,trace,event.origin_traceparent.as_deref()).await;
        let valid = result
            .as_ref()
            .is_ok_and(|receipt| usage_receipt_matches(receipt, &event));
        if valid {
            database.prepare("UPDATE resource_outbox SET delivered_at=unixepoch() WHERE event_id=?1 AND delivered_at IS NULL")
                .bind(&[bind_str(&event.event_id)])?.run().await?;
        } else {
            failed = true;
            database.prepare("UPDATE resource_outbox SET attempts=attempts+1,next_attempt_at=unixepoch()+MIN(86400,300*(1<<MIN(attempts,8))) WHERE event_id=?1 AND delivered_at IS NULL")
                .bind(&[bind_str(&event.event_id)])?.run().await?;
        }
    }
    if failed {
        return Err(worker::Error::RustError(
            "billing_reconciliation_failed".into(),
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn receipt_currency_and_contract_must_agree() {
        assert!(valid_binding_currency("USD", "amail-v0.2.0-usd-v1"));
        assert!(valid_binding_currency("CNY", "amail-v0.2.0"));
        assert!(!valid_binding_currency("CNY", "amail-v0.2.0-usd-v1"));
        assert!(!valid_binding_currency("USD", "amail-v0.2.0"));
        assert!(!valid_binding_currency("EUR", "amail-v0.2.0-usd-v1"));
    }

    #[test]
    fn acknowledgement_cannot_relabel_historical_money() {
        let event = Usage {
            event_id: "event".into(),
            billing_owner_id: "owner".into(),
            period_start: 1,
            period_end: 2,
            meter: "address_seconds".into(),
            quantity: 1,
            amount_micros: 22,
            occurred_at: 1,
            authorization_id: "receipt".into(),
            authorized_at: 1,
            origin_traceparent: None,
            currency: "CNY".into(),
        };
        assert!(usage_receipt_matches(
            &json!({"event_id":"event","currency":"CNY","amount_micros":22}),
            &event
        ));
        assert!(!usage_receipt_matches(
            &json!({"event_id":"event","currency":"USD","amount_micros":22}),
            &event
        ));
        assert!(!usage_receipt_matches(
            &json!({"event_id":"event","amount_micros":22}),
            &event
        ));
        assert!(!usage_receipt_matches(
            &json!({"event_id":"event","currency":"CNY","amount_micros":23}),
            &event
        ));
    }

    #[test]
    fn immutable_owner_keys_are_domain_separated_and_unambiguous() {
        let one = Principal {
            iss: "ab".into(),
            sub: "c".into(),
            profile: None,
            enrollment_fence: false,
        };
        let two = Principal {
            iss: "a".into(),
            sub: "bc".into(),
            profile: None,
            enrollment_fence: false,
        };
        assert_ne!(owner_id(&one), owner_id(&two));
        assert_eq!(owner_id(&one).len(), 64);
    }
    #[test]
    fn billing_codes_are_random_normalized_and_navigation_expires_without_consent() {
        let generated: std::collections::HashSet<_> = (0..1000).map(|_| new_user_code()).collect();
        assert_eq!(generated.len(), 1000);
        for code in &generated {
            assert_eq!(
                normalize_user_code(&code.to_ascii_lowercase()),
                Some(code.clone())
            );
            assert_eq!(
                normalize_user_code(&code.replace('-', " ")),
                Some(code.clone())
            );
        }
        assert!(normalize_user_code("not-a-code").is_none());
        let database = rusqlite::Connection::open_in_memory().unwrap();
        database
            .execute_batch(
                include_str!("../migrations/0014_billing_sessions.sql")
                    .split("-- Failed/ambiguous")
                    .next()
                    .unwrap(),
            )
            .unwrap();
        database
            .execute_batch(include_str!(
                "../migrations/0020_billing_device_navigation.sql"
            ))
            .unwrap();
        database.execute("INSERT INTO billing_sessions(id,owner_iss,owner_sub,action,requested_plan,created_at,expires_at,user_code,authorization_url) VALUES('session','issuer','subject','subscribe','plus',10,20,'ABCDE-FGHJK','https://subscribe.example/authorize/session')", []).unwrap();
        let lookup = |now: i64| {
            database.query_row("SELECT authorization_url FROM billing_sessions WHERE user_code=?1 AND state='pending' AND expires_at>?2 AND authorization_url IS NOT NULL", rusqlite::params!["ABCDE-FGHJK", now], |row| row.get::<_, String>(0))
        };
        assert!(lookup(19).is_ok());
        assert!(lookup(20).is_err());
        assert_eq!(
            database
                .query_row("SELECT state FROM billing_sessions", [], |row| row
                    .get::<_, String>(0))
                .unwrap(),
            "pending"
        );
        database
            .execute("UPDATE billing_sessions SET state='cancelled'", [])
            .unwrap();
        assert!(lookup(19).is_err());
    }

    #[test]
    fn authorization_links_have_exact_navigation_origin() {
        let config = Configuration {
            base: String::new(),
            subscribe: "https://subscribe-staging.moesegfault.dev".into(),
            return_url: String::new(),
        };
        assert!(config.valid_authorization_url(
            "https://subscribe-staging.moesegfault.dev/amail/authorize/opaque"
        ));
        assert!(!config.valid_authorization_url("https://evil.test/amail/authorize/opaque"));
        assert!(!config.valid_authorization_url(
            "https://subscribe-staging.moesegfault.dev/amail/authorize/opaque?code=secret"
        ));
    }
}
