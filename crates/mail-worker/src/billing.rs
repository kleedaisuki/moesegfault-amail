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
    database.prepare("SELECT id,action,requested_plan,remote_id,authorization_url,state,expires_at FROM billing_sessions WHERE owner_iss=?1 AND owner_sub=?2 AND id=?3")
        .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(id)])?
        .first::<Session>(None).await?.ok_or_else(AppError::not_found)
}

fn session_response(row: &Session) -> AppResult<Response> {
    Ok(Response::from_json(
        &json!({"session_id":row.id,"state":row.state,
        "authorization_url":row.authorization_url,"expires_at":row.expires_at,"retry_after_ms":1500}),
    )?)
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
    database.prepare("INSERT OR IGNORE INTO billing_sessions(id,owner_iss,owner_sub,action,requested_plan,created_at,expires_at,origin_traceparent) VALUES(?1,?2,?3,?4,?5,?6,?7,?8)")
        .bind(&[bind_str(&key),bind_str(&user.iss),bind_str(&user.sub),bind_str(&body.action),bind_str(requested_plan),bind_num(timestamp),bind_num(timestamp+1800),bind_str(&trace.traceparent())])?.run().await?;
    let row = session(&database, user, &key).await?;
    if row.action != body.action
        || (body.action == "subscribe" && row.requested_plan != requested_plan)
    {
        return Err(AppError::conflict("idempotency_conflict"));
    }
    if row.state != "pending" || row.remote_id.is_some() {
        return session_response(&row);
    }
    if row.expires_at <= timestamp {
        return expire(&database, user, &key).await;
    }
    let requested_plan = row.requested_plan.as_str();
    let config = Configuration::load(env)?;
    let remote = call(
        env,
        Method::Post,
        "/v1/service/amail/authorizations",
        Some(json!({
            "owner_id":owner_id(user),"plan_id":format!("amail-{requested_plan}"),
            "overage_budget_micros":0,"return_url":config.return_url
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
    session_response(&session(&database, user, &key).await?)
}

async fn expire(database: &Database, user: &Principal, id: &str) -> AppResult<Response> {
    database.prepare("UPDATE billing_sessions SET state='expired' WHERE owner_iss=?1 AND owner_sub=?2 AND id=?3 AND state='pending'")
        .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(id)])?.run().await?;
    session_response(&session(database, user, id).await?)
}

/// Project only service-authenticated, product-scoped, unexpired consent receipts.
async fn apply(database: &Database, user: &Principal, value: &Value) -> AppResult<()> {
    let binding: Binding = serde_json::from_value(value.clone()).map_err(|_| unavailable())?;
    let timestamp = now() / 1000;
    let selected = plan(&binding.plan_id).map_err(|_| unavailable())?;
    if binding.owner_id != owner_id(user)
        || binding.product_id != "amail"
        || binding.currency != "CNY"
        || binding.contract_version != "amail-v0.2.0"
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
            overage_budget_micros: if expired {
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
        return session_response(&row);
    }
    let Some(remote_id) = row.remote_id.as_deref() else {
        if row.expires_at <= now() / 1000 {
            return expire(&database, user, &id).await;
        }
        return session_response(&row);
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
    session_response(&session(&database, user, &id).await?)
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
    let mut account = serde_json::to_value(resource::status(&database, user).await?)
        .map_err(|_| unavailable())?;
    if let Some(object) = account.as_object_mut() {
        object.remove("billing_owner_id");
        object.remove("authorization_id");
        object.remove("origin_traceparent");
    }
    Ok(Response::from_json(
        &json!({"api_version":"2","version":"0.2.0","account":account,
        "rates":{"currency":"CNY","outbound_micros":5000,"storage_gb_month_micros":1_000_000,"address_month_micros":3_000_000},
        "settlement_state":"accrued_unsettled","payment_collection_available":false}),
    )?)
}

/// Minimal durable delivery metadata; neither message contents nor addresses are sent.
#[derive(Deserialize)]
struct Usage {
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
            },
        )
        .await
        .map_err(|_| worker::Error::RustError("billing_reconciliation_failed".into()))?;
    }
    let events=database.prepare("SELECT event_id,billing_owner_id,period_start,period_end,meter,quantity,amount_micros,occurred_at,authorization_id,authorized_at,origin_traceparent FROM resource_outbox WHERE delivered_at IS NULL AND next_attempt_at<=unixepoch() ORDER BY next_attempt_at,occurred_at,event_id LIMIT 3")
        .all().await?.results::<Usage>()?;
    let mut failed = false;
    for event in events {
        database.ensure_remaining(1)?;
        let result=call(env,Method::Post,"/v1/service/amail/usage",Some(json!({
            "event_id":event.event_id,"owner_id":event.billing_owner_id,
            "period_start":event.period_start,"period_end":event.period_end,"meter":event.meter,
                "quantity":event.quantity,"amount_micros":event.amount_micros,"occurred_at":event.occurred_at,
                "authorization_id":event.authorization_id,"authorized_at":event.authorized_at
        })),Some(&event.event_id),request_id,trace,event.origin_traceparent.as_deref()).await;
        let valid = result.as_ref().is_ok_and(|receipt| {
            receipt.get("event_id").and_then(Value::as_str) == Some(event.event_id.as_str())
                || receipt
                    .get("event")
                    .and_then(|value| value.get("event_id"))
                    .and_then(Value::as_str)
                    == Some(event.event_id.as_str())
        });
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
    fn immutable_owner_keys_are_domain_separated_and_unambiguous() {
        let one = Principal {
            iss: "ab".into(),
            sub: "c".into(),
        };
        let two = Principal {
            iss: "a".into(),
            sub: "bc".into(),
        };
        assert_ne!(owner_id(&one), owner_id(&two));
        assert_eq!(owner_id(&one).len(), 64);
    }
    #[test]
    fn closed_plan_and_key_contracts() {
        assert_eq!(plan("amail-plus").unwrap(), "plus");
        assert!(plan("enterprise").is_err());
        assert!(canonical_uuid("not-a-key").is_err());
        assert!(canonical_uuid(&uuid::Uuid::nil().to_string()).is_err());
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
