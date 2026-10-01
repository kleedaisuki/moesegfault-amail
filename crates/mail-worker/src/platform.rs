//! Cloudflare and OpenRouter boundary clients. / Cloudflare 与 OpenRouter 平台边界客户端。

use futures_util::StreamExt;
use serde::Deserialize;
use std::collections::BTreeSet;
use wasm_bindgen::JsValue;
use worker::{Env, Fetch, Headers, Method, Request, RequestInit, Result};

use crate::archive::Draft;

#[derive(Deserialize)]
struct CfRuleResult {
    success: bool,
    result: Option<CfRule>,
}

/// A provider failure contains only fields safe to retain in a diagnostic event.
/// The response body and error message are deliberately never part of this type.
#[derive(Debug, Eq, PartialEq)]
pub(crate) enum RuleCreateFailure {
    /// The provider explicitly rejected the request; capacity is a compatibility hint.
    Provider {
        status: u16,
        code: Option<u32>,
        capacity: bool,
    },
    /// A success response could not confirm which rule was created.
    UnexpectedResponse { status: u16 },
    /// The request could not be constructed, sent, or read; it may still have arrived.
    Request,
}

impl RuleCreateFailure {
    /// Preserve the existing public capacity mapping without exposing provider text.
    pub(crate) fn is_capacity(&self) -> bool {
        matches!(self, Self::Provider { capacity: true, .. })
    }

    /// Return only numeric provider facts for private structured diagnostics.
    pub(crate) fn provider_status(&self) -> Option<u16> {
        match self {
            Self::Provider { status, .. } | Self::UnexpectedResponse { status } => Some(*status),
            Self::Request => None,
        }
    }

    /// The Cloudflare response code is not an HTTP status or human-readable error.
    pub(crate) fn provider_code(&self) -> Option<u32> {
        match self {
            Self::Provider { code, .. } => *code,
            _ => None,
        }
    }
}

#[derive(Deserialize)]
struct CfRuleFailureResponse {
    #[serde(default)]
    errors: Vec<CfRuleError>,
}

#[derive(Deserialize)]
struct CfRuleError {
    code: Option<u32>,
}
#[derive(Deserialize)]
struct CfRule {
    id: String,
    enabled: Option<bool>,
}

#[derive(Deserialize)]
struct CfRuleList {
    success: bool,
    result: Option<Vec<CfListedRule>>,
    result_info: Option<CfResultInfo>,
}
#[derive(Deserialize)]
struct CfResultInfo {
    total_pages: Option<usize>,
    page: Option<usize>,
    per_page: Option<usize>,
    count: Option<usize>,
    total_count: Option<usize>,
}
#[derive(Deserialize)]
struct CfListedRule {
    id: String,
    source: Option<String>,
    enabled: Option<bool>,
    name: Option<String>,
    actions: Vec<CfAction>,
    matchers: Vec<CfMatcher>,
}
#[derive(Deserialize)]
struct CfAction {
    r#type: String,
    value: Option<Vec<String>>,
}
#[derive(Deserialize)]
struct CfMatcher {
    r#type: String,
    field: Option<String>,
    value: Option<String>,
}

/// Exact rules remain owned even when disabled or their status is unknown.
/// Only `enabled == Some(true)` proves that a route may deliver mail.
#[derive(Debug, Eq, PartialEq)]
struct OwnedRule {
    id: String,
    enabled: Option<bool>,
}

/// One address's provider inventory; deleting and duplicate cleanup use all IDs.
#[derive(Debug, Default, Eq, PartialEq)]
pub(crate) struct OwnedRules(Vec<OwnedRule>);

impl OwnedRules {
    /// Whether an exact rule exists, regardless of current delivery status.
    pub(crate) fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    /// Number of exact owned rules for duplicate accounting.
    pub(crate) fn len(&self) -> usize {
        self.0.len()
    }

    /// The first deliverable exact rule, preserving the provider's ordering.
    pub(crate) fn first_enabled(&self) -> Option<&str> {
        self.0
            .iter()
            .find(|rule| rule.enabled == Some(true))
            .map(|rule| rule.id.as_str())
    }

    /// Whether the committed rule remains enabled at the provider.
    pub(crate) fn has_enabled(&self, id: &str) -> bool {
        self.0
            .iter()
            .any(|rule| rule.id == id && rule.enabled == Some(true))
    }

    /// All exact owned IDs, including disabled rules requiring state-aware cleanup.
    pub(crate) fn into_ids(self) -> Vec<String> {
        self.0.into_iter().map(|rule| rule.id).collect()
    }
}

/// Reject negative and over-cap envelopes without retaining provider text.
#[cfg(test)]
fn checked_rule_list(
    data: CfRuleList,
    status: u16,
) -> std::result::Result<(Vec<CfListedRule>, Option<usize>), RuleListFailure> {
    if !data.success {
        return Err(RuleListFailure::Provider { status });
    }
    let result = data.result.ok_or(RuleListFailure::Decode { status })?;
    let total_pages = data.result_info.and_then(|info| info.total_pages);
    if total_pages.is_some_and(|total| total > 10) {
        return Err(RuleListFailure::Decode { status });
    }
    Ok((result, total_pages))
}

/// Preserve only the first observable Rules GET failure boundary and numeric HTTP status.
#[derive(Debug, Eq, PartialEq)]
pub(crate) enum RuleListFailure {
    /// No HTTP response was observed; the request may nevertheless have reached Cloudflare.
    Request,
    /// Cloudflare returned a non-200 HTTP status.
    Http { status: u16 },
    /// A 200 envelope explicitly reported `success=false`.
    Provider { status: u16 },
    /// A 200 envelope was malformed, incomplete, or exceeded the page safety bound.
    Decode { status: u16 },
}

impl RuleListFailure {
    /// Return the status only when a provider response was actually observed.
    pub(crate) fn provider_status(&self) -> Option<u16> {
        match self {
            Self::Request => None,
            Self::Http { status } | Self::Provider { status } | Self::Decode { status } => {
                Some(*status)
            }
        }
    }
}

/// Shared address-phase egress allowance. Redirects are never followed.
/// Inventory, fresh absence checks, current-ID reads and DELETEs all debit it.
pub(crate) struct RoutingBudget {
    remaining: usize,
}

impl RoutingBudget {
    /// Reserve at most twenty external calls for one address invocation.
    pub(crate) fn new() -> Self {
        Self { remaining: 20 }
    }

    /// Admit a worst-case complete inventory before an absence recheck starts.
    pub(crate) fn can_inventory(&self) -> bool {
        self.remaining >= 10
    }

    /// Reserve GET plus DELETE before destructive work, avoiding partial admission.
    pub(crate) fn can_delete(&self) -> bool {
        self.remaining >= 2
    }

    /// Debit before submission, including failures whose remote effect is unknown.
    fn take(&mut self) -> Result<()> {
        if self.remaining == 0 {
            return Err(worker::Error::RustError("routing_budget_exhausted".into()));
        }
        self.remaining -= 1;
        Ok(())
    }
}

/// Only a fully validated, terminal paginated inventory can establish absence.
/// Provider rule data stays invocation-local and is never diagnostic material.
pub(crate) struct CompleteRuleInventory(Vec<CfListedRule>);

impl CfListedRule {
    /// Conjunctive destructive authority, under exclusive managed-namespace ownership.
    fn owns(&self, address: &str, ingress: &str) -> bool {
        self.source.as_deref() == Some("api")
            && self.name.as_deref() == Some(format!("amail {address}").as_str())
            && self.matchers.len() == 1
            && self.matchers[0].r#type == "literal"
            && self.matchers[0].field.as_deref() == Some("to")
            && self.matchers[0].value.as_deref() == Some(address)
            && self.actions.len() == 1
            && self.actions[0].r#type == "worker"
            && self.actions[0]
                .value
                .as_ref()
                .is_some_and(|values| values.len() == 1 && values[0] == ingress)
    }

    /// Near matches block settlement rather than licensing deletion of foreign IDs.
    fn touches(&self, address: &str) -> bool {
        self.name.as_deref() == Some(format!("amail {address}").as_str())
            || self.matchers.iter().any(|matcher| {
                matcher.field.as_deref() == Some("to") && matcher.value.as_deref() == Some(address)
            })
    }
}

impl CompleteRuleInventory {
    /// Preserve provider ordering; any near-match/saved-ID drift fails closed.
    pub(crate) fn for_address(
        &self,
        address: &str,
        ingress: &str,
        saved: Option<&str>,
    ) -> Result<OwnedRules> {
        let mut owned = Vec::new();
        for rule in &self.0 {
            if !rule.touches(address) && saved != Some(rule.id.as_str()) {
                continue;
            }
            if !rule.owns(address, ingress) {
                return Err(worker::Error::RustError("routing_scope_conflict".into()));
            }
            owned.push(OwnedRule {
                id: rule.id.clone(),
                enabled: rule.enabled,
            });
        }
        Ok(OwnedRules(owned))
    }

    /// Positive provider keys only: no all-tombstone scan or unknown-row deletion.
    pub(crate) fn retired_candidates(&self, domain: &str) -> Vec<String> {
        let suffix = format!("@{domain}");
        self.0
            .iter()
            .filter_map(|rule| {
                let address = rule.name.as_deref()?.strip_prefix("amail ")?;
                let part = address.strip_suffix(&suffix)?;
                if !crate::valid_address(address) || crate::RESERVED.contains(&part) {
                    return None;
                }
                Some(address.to_owned())
            })
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect()
    }
}

/// Read a bounded body incrementally: Content-Length is not trusted admission.
async fn rule_body(response: &mut worker::Response) -> Result<Vec<u8>> {
    const MAX_BYTES: usize = 256 * 1024;
    match response.body() {
        worker::ResponseBody::Empty => return Ok(Vec::new()),
        worker::ResponseBody::Body(bytes) if bytes.len() <= MAX_BYTES => return Ok(bytes.clone()),
        worker::ResponseBody::Body(_) => {
            return Err(worker::Error::RustError("routing_body_limit".into()))
        }
        worker::ResponseBody::Stream(_) => {}
    }
    let mut stream = response.stream()?;
    let mut bytes = Vec::new();
    while let Some(chunk) = stream.next().await {
        let chunk = chunk?;
        if chunk.len() > MAX_BYTES.saturating_sub(bytes.len()) {
            return Err(worker::Error::RustError("routing_body_limit".into()));
        }
        bytes.extend(chunk);
    }
    Ok(bytes)
}

/// One budget debit per nonredirecting provider exchange.
async fn routing_fetch(
    env: &Env,
    url: &str,
    method: Method,
    budget: &mut RoutingBudget,
) -> Result<worker::Response> {
    budget.take()?;
    let mut init = RequestInit::new();
    init.with_method(method)
        .with_headers(cf_headers(env)?)
        .with_redirect(worker::RequestRedirect::Manual);
    Fetch::Request(Request::new_with_init(url, &init)?)
        .send()
        .await
}

/// Bound the zone to ten pages / five hundred unique rules, requiring terminal proof.
pub(crate) async fn rule_inventory(
    env: &Env,
    budget: &mut RoutingBudget,
) -> std::result::Result<CompleteRuleInventory, RuleListFailure> {
    let zone = env
        .var("CF_ZONE_ID")
        .map_err(|_| RuleListFailure::Request)?
        .to_string();
    let mut rules = Vec::new();
    let mut ids = BTreeSet::new();
    let mut known_pages = None;
    let mut known_count = None;
    for page in 1..=10 {
        let url = format!("https://api.cloudflare.com/client/v4/zones/{zone}/email/routing/rules?per_page=50&page={page}");
        let mut response = routing_fetch(env, &url, Method::Get, budget)
            .await
            .map_err(|_| RuleListFailure::Request)?;
        let status = response.status_code();
        if status != 200 {
            return Err(RuleListFailure::Http { status });
        }
        let bytes = rule_body(&mut response)
            .await
            .map_err(|_| RuleListFailure::Decode { status })?;
        let data: CfRuleList =
            serde_json::from_slice(&bytes).map_err(|_| RuleListFailure::Decode { status })?;
        if !data.success {
            return Err(RuleListFailure::Provider { status });
        }
        let result = data.result.ok_or(RuleListFailure::Decode { status })?;
        let count = result.len();
        if count > 50 {
            return Err(RuleListFailure::Decode { status });
        }
        let mut terminal = count < 50;
        if let Some(info) = data.result_info {
            if info.page.is_some_and(|n| n != page)
                || info.per_page.is_some_and(|n| n != 50)
                || info.count.is_some_and(|n| n != count)
                || info.total_count.is_some_and(|n| n > 500)
            {
                return Err(RuleListFailure::Decode { status });
            }
            if let Some(total) = info.total_pages {
                if total > 10
                    || (total < page && !(total == 0 && page == 1 && count == 0))
                    || known_pages.is_some_and(|n| n != total)
                {
                    return Err(RuleListFailure::Decode { status });
                }
                known_pages = Some(total);
            }
            if let Some(total) = info.total_count {
                if known_count.is_some_and(|n| n != total) {
                    return Err(RuleListFailure::Decode { status });
                }
                known_count = Some(total);
            }
        }
        if let Some(total) = known_pages {
            terminal = page == total || (total == 0 && page == 1 && count == 0);
            if !terminal && count != 50 {
                return Err(RuleListFailure::Decode { status });
            }
        }
        for rule in result {
            if !valid_rule_id(&rule.id) || !ids.insert(rule.id.clone()) {
                return Err(RuleListFailure::Decode { status });
            }
            rules.push(rule);
        }
        if terminal {
            if known_count.is_some_and(|n| n != rules.len()) {
                return Err(RuleListFailure::Decode { status });
            }
            return Ok(CompleteRuleInventory(rules));
        }
    }
    Err(RuleListFailure::Decode { status: 200 })
}

/// IDs are path components, never arbitrary URLs or separator-bearing strings.
fn valid_rule_id(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= 128
        && id
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'-' | b'_'))
}

/// Request-path add uses the same complete and strict inventory contract.
pub(crate) async fn rules_for_address_typed(
    env: &Env,
    address: &str,
) -> std::result::Result<OwnedRules, RuleListFailure> {
    let ingress = env
        .var("EMAIL_INGRESS_WORKER_NAME")
        .map_err(|_| RuleListFailure::Request)?
        .to_string();
    rule_inventory(env, &mut RoutingBudget::new())
        .await?
        .for_address(address, &ingress, None)
        .map_err(|_| RuleListFailure::Decode { status: 200 })
}

/// Provision one literal subdomain routing rule; no catch-all exists.
/// An uncertain response remains in provisioning state for reconciliation.
pub async fn create_rule(
    env: &Env,
    address: &str,
) -> std::result::Result<String, RuleCreateFailure> {
    let zone = env
        .var("CF_ZONE_ID")
        .map_err(|_| RuleCreateFailure::Request)?
        .to_string();
    let worker_name = env
        .var("EMAIL_INGRESS_WORKER_NAME")
        .map_err(|_| RuleCreateFailure::Request)?
        .to_string();
    let url = format!("https://api.cloudflare.com/client/v4/zones/{zone}/email/routing/rules");
    let body = serde_json::json!({
        "name": format!("amail {address}"), "enabled": true, "source": "api",
        "actions": [{"type":"worker","value":[worker_name]}],
        "matchers": [{"type":"literal","field":"to","value":address}]
    });
    let mut response = fetch_json(env, &url, Method::Post, &body)
        .await
        .map_err(|_| RuleCreateFailure::Request)?;
    let status = response.status_code();
    let bytes = rule_body(&mut response)
        .await
        .map_err(|_| RuleCreateFailure::UnexpectedResponse { status })?;
    let body = std::str::from_utf8(&bytes)
        .map_err(|_| RuleCreateFailure::UnexpectedResponse { status })?;
    classify_create_response(status, body)
}

/// Decode the provider response without returning or recording arbitrary text.
/// The old capacity-text check is retained solely for public error compatibility.
fn classify_create_response(
    status: u16,
    body: &str,
) -> std::result::Result<String, RuleCreateFailure> {
    if matches!(status, 200 | 201) {
        let data: CfRuleResult = serde_json::from_str(body)
            .map_err(|_| RuleCreateFailure::UnexpectedResponse { status })?;
        if data.success {
            return data
                .result
                .filter(|rule| rule.enabled == Some(true) && valid_rule_id(&rule.id))
                .map(|rule| rule.id)
                .ok_or(RuleCreateFailure::UnexpectedResponse { status });
        }
    }
    let code = serde_json::from_str::<CfRuleFailureResponse>(body)
        .ok()
        .and_then(|data| {
            data.errors
                .into_iter()
                .filter_map(|error| error.code)
                .find(|code| *code >= 1000)
        });
    let lower = body.to_ascii_lowercase();
    let capacity = !matches!(status, 200 | 201)
        && ["limit", "maximum", "quota"]
            .iter()
            .any(|word| lower.contains(word));
    Err(RuleCreateFailure::Provider {
        status,
        code,
        capacity,
    })
}

/// Revalidate the full current provider rule before any state-aware DELETE.
/// A known-ID 404 is explicit absence; arbitrary failure envelopes are not.
pub(crate) async fn delete_owned_rule(
    env: &Env,
    address: &str,
    ingress: &str,
    rule_id: &str,
    budget: &mut RoutingBudget,
) -> Result<()> {
    if !valid_rule_id(rule_id) || !budget.can_delete() {
        return Err(worker::Error::RustError("routing_delete_unverified".into()));
    }
    let zone = env.var("CF_ZONE_ID")?.to_string();
    let url =
        format!("https://api.cloudflare.com/client/v4/zones/{zone}/email/routing/rules/{rule_id}");
    let mut current = routing_fetch(env, &url, Method::Get, budget).await?;
    if current.status_code() == 404 {
        return Ok(());
    }
    if current.status_code() != 200 {
        return Err(worker::Error::RustError("routing_read_failed".into()));
    }
    #[derive(Deserialize)]
    struct Current {
        success: bool,
        result: Option<CfListedRule>,
    }
    let current: Current = serde_json::from_slice(&rule_body(&mut current).await?)
        .map_err(|_| worker::Error::RustError("routing_read_failed".into()))?;
    let rule = current
        .result
        .filter(|rule| current.success && rule.id == rule_id && rule.owns(address, ingress))
        .ok_or_else(|| worker::Error::RustError("routing_scope_conflict".into()))?;
    // Read the permanent desired state after provider GET. Active duplicate
    // pruning can never delete whichever route is now committed by another actor.
    #[derive(Deserialize)]
    struct State {
        state: String,
        cf_rule_id: Option<String>,
    }
    let state = env
        .d1("MAIL_DB")?
        .prepare("SELECT state,cf_rule_id FROM addresses WHERE address=?1")
        .bind(&[JsValue::from_str(address)])?
        .first::<State>(None)
        .await?
        .ok_or_else(|| worker::Error::RustError("routing_state_unknown".into()))?;
    let allowed = matches!(state.state.as_str(), "deleting" | "retired")
        || (state.state == "active"
            && state
                .cf_rule_id
                .as_deref()
                .is_some_and(|saved| saved != rule.id));
    if !allowed {
        return Err(worker::Error::RustError("routing_state_changed".into()));
    }
    let mut response = routing_fetch(env, &url, Method::Delete, budget).await?;
    match response.status_code() {
        204 | 404 => Ok(()),
        200 => {
            #[derive(Deserialize)]
            struct Deleted {
                success: bool,
            }
            let deleted: Deleted = serde_json::from_slice(&rule_body(&mut response).await?)
                .map_err(|_| worker::Error::RustError("routing_delete_failed".into()))?;
            if deleted.success {
                Ok(())
            } else {
                Err(worker::Error::RustError("routing_delete_failed".into()))
            }
        }
        _ => Err(worker::Error::RustError("routing_delete_failed".into())),
    }
}

fn cf_headers(env: &Env) -> Result<Headers> {
    let headers = Headers::new();
    headers.set(
        "Authorization",
        &format!(
            "Bearer {}",
            env.secret("CF_EMAIL_ROUTING_TOKEN")?.to_string()
        ),
    )?;
    headers.set("Content-Type", "application/json")?;
    Ok(headers)
}

async fn fetch_json(
    env: &Env,
    url: &str,
    method: Method,
    body: &serde_json::Value,
) -> Result<worker::Response> {
    let mut init = RequestInit::new();
    init.with_method(method)
        .with_redirect(worker::RequestRedirect::Manual)
        .with_headers(cf_headers(env)?)
        .with_body(Some(JsValue::from_str(&body.to_string())));
    Fetch::Request(Request::new_with_init(url, &init)?)
        .send()
        .await
}

#[derive(Deserialize)]
struct EmbeddingResult {
    data: Vec<EmbeddingData>,
}
#[derive(Deserialize)]
struct EmbeddingData {
    embedding: Vec<f64>,
}

/// OpenRouter embedding input ceiling in UTF-8 bytes, shared with document projection.
pub const EMBEDDING_INPUT_MAX_BYTES: usize = 12_000;

/// Fixed, non-content-bearing failure classes for durable indexing decisions.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum EmbeddingFailure {
    InvalidInput,
    InvalidRequest,
    Dependency,
    RateLimited,
    Transient,
    Malformed,
}

impl EmbeddingFailure {
    /// A stable operator code; never include provider text or the embedding input.
    pub(crate) fn code(self) -> &'static str {
        match self {
            Self::InvalidInput => "invalid_input",
            Self::InvalidRequest => "invalid_request",
            Self::Dependency => "dependency_unavailable",
            Self::RateLimited => "provider_rate_limited",
            Self::Transient => "provider_transient",
            Self::Malformed => "provider_malformed",
        }
    }
}

/// Request exactly 256 dimensions and reject malformed/nonfinite vectors. / 请求恰好 256 维，并拒绝畸形或非有限向量。
pub async fn embed(env: &Env, input: &str, input_type: &str) -> Result<Vec<f32>> {
    embed_classified(env, input, input_type)
        .await
        .map_err(|error| worker::Error::RustError(error.code().into()))
}

/// Preserve only failure class for scheduler backoff; never propagate provider bodies.
pub(crate) async fn embed_classified(
    env: &Env,
    input: &str,
    input_type: &str,
) -> std::result::Result<Vec<f32>, EmbeddingFailure> {
    if input.is_empty() || input.len() > EMBEDDING_INPUT_MAX_BYTES {
        return Err(EmbeddingFailure::InvalidInput);
    }
    let headers = Headers::new();
    headers
        .set(
            "Authorization",
            &format!(
                "Bearer {}",
                env.secret("OPENROUTER_API_KEY")
                    .map_err(|_| EmbeddingFailure::Dependency)?
                    .to_string()
            ),
        )
        .map_err(|_| EmbeddingFailure::Dependency)?;
    headers
        .set("Content-Type", "application/json")
        .map_err(|_| EmbeddingFailure::Dependency)?;
    headers
        .set("HTTP-Referer", "https://amail.moesegfault.dev")
        .map_err(|_| EmbeddingFailure::Dependency)?;
    headers
        .set("X-Title", "amail")
        .map_err(|_| EmbeddingFailure::Dependency)?;
    headers
        .set("X-OpenRouter-Cache", "false")
        .map_err(|_| EmbeddingFailure::Dependency)?;
    let payload = serde_json::json!({
        "model": env.var("OPENROUTER_EMBEDDING_MODEL").map_err(|_| EmbeddingFailure::Dependency)?.to_string(),
        "dimensions": 256, "input": input, "input_type": input_type,
        "provider": {"zdr":true,"data_collection":"deny"}
    });
    let mut init = RequestInit::new();
    init.with_method(Method::Post)
        .with_headers(headers)
        .with_body(Some(JsValue::from_str(&payload.to_string())));
    let mut response = Fetch::Request(
        Request::new_with_init("https://openrouter.ai/api/v1/embeddings", &init)
            .map_err(|_| EmbeddingFailure::Transient)?,
    )
    .send()
    .await
    .map_err(|_| EmbeddingFailure::Transient)?;
    match response.status_code() {
        200 => {}
        400 | 413 | 422 => return Err(EmbeddingFailure::InvalidRequest),
        401 | 403 => return Err(EmbeddingFailure::Dependency),
        429 => return Err(EmbeddingFailure::RateLimited),
        _ => return Err(EmbeddingFailure::Transient),
    }
    let data: EmbeddingResult = response
        .json()
        .await
        .map_err(|_| EmbeddingFailure::Malformed)?;
    let values = data
        .data
        .into_iter()
        .next()
        .ok_or(EmbeddingFailure::Malformed)?
        .embedding;
    if values.len() != 256 || values.iter().any(|x| !x.is_finite()) {
        return Err(EmbeddingFailure::Malformed);
    }
    let norm = values.iter().map(|x| x * x).sum::<f64>().sqrt();
    if norm <= 1e-12 || !norm.is_finite() {
        return Err(EmbeddingFailure::Malformed);
    }
    Ok(values.into_iter().map(|x| (x / norm) as f32).collect())
}

/// Submit a validated draft through Cloudflare Email Service. / 经 Cloudflare Email Service 提交已校验草稿。
pub async fn send(env: &Env, draft: &Draft) -> Result<String> {
    use worker::{EmailAttachment, SendEmail, SendEmailBuilder};
    let binding: SendEmail = env.get_binding("EMAIL")?;
    let m = &draft.manifest;
    let builder = SendEmailBuilder::new_with_str_and_slice(&m.from, &m.to, &m.subject);
    if !m.cc.is_empty() {
        builder.set_cc_with_slice(&m.cc);
    }
    if !m.bcc.is_empty() {
        builder.set_bcc_with_slice(&m.bcc);
    }
    if let Some(reply_to) = &m.reply_to {
        builder.set_reply_to(reply_to);
    }
    if m.in_reply_to.is_some() || !m.references.is_empty() {
        let headers = js_sys::Object::<js_sys::JsString>::new_typed();
        if let Some(id) = &m.in_reply_to {
            js_sys::Reflect::set(
                &headers,
                &JsValue::from_str("In-Reply-To"),
                &JsValue::from_str(id),
            )?;
        }
        if !m.references.is_empty() {
            js_sys::Reflect::set(
                &headers,
                &JsValue::from_str("References"),
                &JsValue::from_str(&m.references.join(" ")),
            )?;
        }
        builder.set_headers(&headers);
    }
    builder.set_text(&draft.text);
    if let Some(html) = &draft.html {
        builder.set_html(html);
    }
    let mut attachments = Vec::new();
    for (meta, data) in &draft.assets {
        let filename = meta
            .filename
            .as_deref()
            .unwrap_or_else(|| meta.path.rsplit('/').next().unwrap_or("asset"));
        let view = js_sys::Uint8Array::from(data.as_slice());
        let item = if meta.disposition == "inline" {
            EmailAttachment::new_inline_with_typed_array(
                meta.cid.as_deref().unwrap_or(""),
                filename,
                &meta.content_type,
                &view,
            )
        } else {
            EmailAttachment::new_attachment_with_typed_array(filename, &meta.content_type, &view)
        };
        attachments.push(item);
    }
    if !attachments.is_empty() {
        builder.set_attachments(&attachments);
    }
    let result = binding.send_with_builder(&builder).await?;
    Ok(result.message_id())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// One shared allowance counts failure attempts and refuses excess work.
    #[test]
    fn routing_budget_is_hard_and_shared() {
        let mut budget = RoutingBudget::new();
        for _ in 0..10 {
            budget.take().unwrap();
        }
        assert!(budget.can_inventory());
        budget.take().unwrap();
        assert!(!budget.can_inventory());
        for _ in 0..8 {
            budget.take().unwrap();
        }
        assert!(!budget.can_delete());
        budget.take().unwrap();
        assert!(budget.take().is_err());
    }

    /// A saved ID or near match is never independent destructive authority.
    #[test]
    fn strict_inventory_rejects_scope_drift() {
        let address = "synthetic@mail.example.test";
        let raw = serde_json::json!({
            "id": "synthetic-rule", "enabled": false, "source": "api",
            "name": format!("amail {address}"),
            "matchers": [{"type":"literal","field":"to","value":address}],
            "actions": [{"type":"worker","value":["synthetic-ingress"]}]
        });
        let inventory = CompleteRuleInventory(vec![serde_json::from_value(raw.clone()).unwrap()]);
        let owned = inventory
            .for_address(address, "synthetic-ingress", None)
            .unwrap();
        assert_eq!(owned.len(), 1);
        assert_eq!(owned.first_enabled(), None);
        let mut drift = raw.clone();
        drift["actions"] = serde_json::json!([
            {"type":"worker","value":["synthetic-ingress"]}, {"type":"drop"}
        ]);
        let inventory = CompleteRuleInventory(vec![serde_json::from_value(drift).unwrap()]);
        assert!(inventory
            .for_address(address, "synthetic-ingress", None)
            .is_err());
        let inventory = CompleteRuleInventory(vec![serde_json::from_value(raw).unwrap()]);
        assert!(inventory
            .for_address(
                "foreign@mail.example.test",
                "synthetic-ingress",
                Some("synthetic-rule")
            )
            .is_err());
    }

    /// Negative, missing, and oversized list envelopes remain distinct fixed outcomes.
    #[test]
    fn routing_list_failure_classification() {
        let negative: CfRuleList = serde_json::from_str(
            r#"{"success":false,"errors":[{"message":"private-address@example.com"}]}"#,
        )
        .unwrap();
        assert!(matches!(
            checked_rule_list(negative, 200),
            Err(RuleListFailure::Provider { status: 200 })
        ));

        let missing: CfRuleList = serde_json::from_str(r#"{"success":true}"#).unwrap();
        assert!(matches!(
            checked_rule_list(missing, 200),
            Err(RuleListFailure::Decode { status: 200 })
        ));

        let huge: CfRuleList = serde_json::from_str(
            r#"{"success":true,"result":[],"result_info":{"total_pages":201}}"#,
        )
        .unwrap();
        assert!(matches!(
            checked_rule_list(huge, 200),
            Err(RuleListFailure::Decode { status: 200 })
        ));
        assert!(
            serde_json::from_str::<CfRuleList>(r#"{"success":true,"result":"secret"}"#).is_err()
        );

        assert_eq!(RuleListFailure::Request.provider_status(), None);
        assert_eq!(
            RuleListFailure::Http { status: 403 }.provider_status(),
            Some(403)
        );
    }

    /// A successful provider response returns only the rule identifier.
    #[test]
    fn create_rule_success() {
        let body = r#"{"success":true,"result":{"id":"rule-id","enabled":true}}"#;
        assert_eq!(classify_create_response(200, body), Ok("rule-id".into()));
        assert_eq!(classify_create_response(201, body), Ok("rule-id".into()));
    }

    /// A disabled or status-unknown route is owned but cannot establish delivery.
    #[test]
    fn listed_rule_enabled_selection_preserves_cleanup_inventory() {
        let rules: CfRuleList = serde_json::from_str(r#"{"success":true,"result":[{"id":"disabled","enabled":false,"actions":[],"matchers":[]},{"id":"unknown","actions":[],"matchers":[]},{"id":"enabled","enabled":true,"actions":[],"matchers":[]}]}"#).unwrap();
        let (listed, _) = checked_rule_list(rules, 200).unwrap();
        let owned = OwnedRules(
            listed
                .into_iter()
                .map(|rule| OwnedRule {
                    id: rule.id,
                    enabled: rule.enabled,
                })
                .collect(),
        );
        assert_eq!(owned.first_enabled(), Some("enabled"));
        assert!(!owned.has_enabled("disabled"));
        assert!(!owned.has_enabled("unknown"));
        assert!(owned.has_enabled("enabled"));
        assert_eq!(owned.into_ids(), vec!["disabled", "unknown", "enabled"]);
    }

    /// An unconfirmed create response may have created a route but cannot activate D1.
    #[test]
    fn create_rule_requires_confirmed_enabled_state() {
        for body in [
            r#"{"success":true,"result":{"id":"rule-id","enabled":false}}"#,
            r#"{"success":true,"result":{"id":"rule-id"}}"#,
        ] {
            assert_eq!(
                classify_create_response(200, body),
                Err(RuleCreateFailure::UnexpectedResponse { status: 200 })
            );
        }
    }

    /// HTTP and Cloudflare numeric codes survive, but body text never enters the error.
    #[test]
    fn create_rule_provider_rejection_is_typed_and_private() {
        let body = r#"{"success":false,"errors":[{"code":10000,"message":"private-alias@example.com private-token"}]}"#;
        let error = classify_create_response(403, body).unwrap_err();
        assert_eq!(
            error,
            RuleCreateFailure::Provider {
                status: 403,
                code: Some(10000),
                capacity: false,
            }
        );
        assert!(!format!("{error:?}").contains("private-alias"));
        assert!(!format!("{error:?}").contains("private-token"));
    }

    /// Preserve the existing public capacity mapping for provider quota text.
    #[test]
    fn create_rule_capacity_and_malformed_responses() {
        let capacity = classify_create_response(
            400,
            r#"{"success":false,"errors":[{"code":1000,"message":"Maximum routing rule limit reached"}]}"#,
        )
        .unwrap_err();
        assert!(capacity.is_capacity());
        assert_eq!(capacity.provider_status(), Some(400));
        assert_eq!(capacity.provider_code(), Some(1000));
        assert_eq!(
            classify_create_response(503, "upstream failed"),
            Err(RuleCreateFailure::Provider {
                status: 503,
                code: None,
                capacity: false,
            })
        );
        assert_eq!(
            classify_create_response(200, "not json"),
            Err(RuleCreateFailure::UnexpectedResponse { status: 200 })
        );
        assert_eq!(
            classify_create_response(200, r#"{"success":true}"#),
            Err(RuleCreateFailure::UnexpectedResponse { status: 200 })
        );
        assert_eq!(
            classify_create_response(200, r#"{"success":false,"errors":[{"code":1000}]}"#),
            Err(RuleCreateFailure::Provider {
                status: 200,
                code: Some(1000),
                capacity: false,
            })
        );
    }
}
