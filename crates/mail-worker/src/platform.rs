//! Cloudflare and OpenRouter boundary clients. / Cloudflare 与 OpenRouter 平台边界客户端。

use serde::Deserialize;
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
}
#[derive(Deserialize)]
struct CfListedRule {
    id: String,
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

/// Reject negative or incomplete list envelopes without retaining provider text.
fn checked_rule_list(
    data: CfRuleList,
    status: u16,
) -> std::result::Result<(Vec<CfListedRule>, Option<usize>), RuleListFailure> {
    if !data.success {
        return Err(RuleListFailure::Provider { status });
    }
    let result = data.result.ok_or(RuleListFailure::Decode { status })?;
    let total_pages = data.result_info.and_then(|info| info.total_pages);
    if total_pages.is_some_and(|total| total > 200) {
        return Err(RuleListFailure::Decode { status });
    }
    Ok((result, total_pages))
}

/// Find all provider rules for one exact address, including orphan rules after partial failure. / 查找一个地址的全部供应商规则，包括局部失败留下的孤儿规则。
pub async fn rules_for_address(env: &Env, address: &str) -> Result<Vec<String>> {
    rules_for_address_typed(env, address)
        .await
        .map(OwnedRules::into_ids)
        .map_err(|_| worker::Error::RustError("routing_list_failed".into()))
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

/// Typed variant for the authenticated address-add diagnostic; other callers keep the old API.
pub(crate) async fn rules_for_address_typed(
    env: &Env,
    address: &str,
) -> std::result::Result<OwnedRules, RuleListFailure> {
    let zone = env
        .var("CF_ZONE_ID")
        .map_err(|_| RuleListFailure::Request)?
        .to_string();
    let ingress = env
        .var("EMAIL_INGRESS_WORKER_NAME")
        .map_err(|_| RuleListFailure::Request)?
        .to_string();
    let expected_name = format!("amail {address}");
    let mut rules = Vec::new();
    // The API permits at most 50 per page. A zone can include several mail domains.
    for page in 1..=200 {
        let url = format!("https://api.cloudflare.com/client/v4/zones/{zone}/email/routing/rules?per_page=50&page={page}");
        let mut init = RequestInit::new();
        init.with_method(Method::Get)
            .with_headers(cf_headers(env).map_err(|_| RuleListFailure::Request)?);
        let request = Request::new_with_init(&url, &init).map_err(|_| RuleListFailure::Request)?;
        let mut response = Fetch::Request(request)
            .send()
            .await
            .map_err(|_| RuleListFailure::Request)?;
        let status = response.status_code();
        if status != 200 {
            return Err(RuleListFailure::Http { status });
        }
        let data: CfRuleList = response
            .json()
            .await
            .map_err(|_| RuleListFailure::Decode { status })?;
        let (result, total_pages) = checked_rule_list(data, status)?;
        let count = result.len();
        for rule in result {
            if rule.name.as_deref() == Some(expected_name.as_str())
                && rule.actions.iter().any(|a| {
                    a.r#type == "worker"
                        && a.value
                            .as_ref()
                            .is_some_and(|values| values.iter().any(|v| v == &ingress))
                })
                && rule.matchers.iter().any(|m| {
                    m.r#type == "literal"
                        && m.field.as_deref() == Some("to")
                        && m.value.as_deref() == Some(address)
                })
            {
                rules.push(OwnedRule {
                    id: rule.id,
                    enabled: rule.enabled,
                });
            }
        }
        if count < 50 || total_pages.is_some_and(|total| page >= total) {
            break;
        }
        if page == 200 {
            return Err(RuleListFailure::Decode { status });
        }
    }
    Ok(OwnedRules(rules))
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
    let body = response
        .text()
        .await
        .map_err(|_| RuleCreateFailure::UnexpectedResponse { status })?;
    classify_create_response(status, &body)
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
                .filter(|rule| rule.enabled == Some(true))
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

/// Disable a literal routing rule before retiring an address. / 注销地址之前先禁用精确路由规则。
pub async fn delete_rule(env: &Env, rule_id: &str) -> Result<()> {
    let zone = env.var("CF_ZONE_ID")?.to_string();
    let url =
        format!("https://api.cloudflare.com/client/v4/zones/{zone}/email/routing/rules/{rule_id}");
    let headers = cf_headers(env)?;
    let mut init = RequestInit::new();
    init.with_method(Method::Delete).with_headers(headers);
    let req = Request::new_with_init(&url, &init)?;
    let response = Fetch::Request(req).send().await?;
    if !matches!(response.status_code(), 200 | 204 | 404) {
        return Err(worker::Error::RustError("routing_delete_failed".into()));
    }
    Ok(())
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
