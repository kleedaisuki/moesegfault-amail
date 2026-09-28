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
#[derive(Deserialize)]
struct CfRule {
    id: String,
}

#[derive(Deserialize)]
struct CfRuleList {
    success: bool,
    result: Vec<CfListedRule>,
    result_info: Option<CfResultInfo>,
}
#[derive(Deserialize)]
struct CfResultInfo {
    total_pages: Option<usize>,
}
#[derive(Deserialize)]
struct CfListedRule {
    id: String,
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

/// Find all provider rules for one exact address, including orphan rules after partial failure. / 查找一个地址的全部供应商规则，包括局部失败留下的孤儿规则。
pub async fn rules_for_address(env: &Env, address: &str) -> Result<Vec<String>> {
    let zone = env.var("CF_ZONE_ID")?.to_string();
    let ingress = env.var("EMAIL_INGRESS_WORKER_NAME")?.to_string();
    let expected_name = format!("amail {address}");
    let mut ids = Vec::new();
    // The API permits at most 50 per page. A zone can include several mail domains.
    for page in 1..=200 {
        let url = format!("https://api.cloudflare.com/client/v4/zones/{zone}/email/routing/rules?per_page=50&page={page}");
        let mut init = RequestInit::new();
        init.with_method(Method::Get).with_headers(cf_headers(env)?);
        let mut response = Fetch::Request(Request::new_with_init(&url, &init)?)
            .send()
            .await?;
        if response.status_code() != 200 {
            return Err(worker::Error::RustError("routing_list_failed".into()));
        }
        let data: CfRuleList = response.json().await?;
        if !data.success {
            return Err(worker::Error::RustError("routing_list_failed".into()));
        }
        let count = data.result.len();
        let total_pages = data.result_info.as_ref().and_then(|info| info.total_pages);
        if total_pages.is_some_and(|total| total > 200) {
            return Err(worker::Error::RustError("routing_list_limit".into()));
        }
        for rule in data.result {
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
                ids.push(rule.id);
            }
        }
        if count < 50 || total_pages.is_some_and(|total| page >= total) {
            break;
        }
        if page == 200 {
            return Err(worker::Error::RustError("routing_list_limit".into()));
        }
    }
    Ok(ids)
}

/// Provision one literal subdomain routing rule; no catch-all exists. / 创建单个子域名精确路由规则；不存在全收规则。
pub async fn create_rule(env: &Env, address: &str) -> Result<String> {
    let zone = env.var("CF_ZONE_ID")?.to_string();
    let worker_name = env.var("EMAIL_INGRESS_WORKER_NAME")?.to_string();
    let url = format!("https://api.cloudflare.com/client/v4/zones/{zone}/email/routing/rules");
    let body = serde_json::json!({
        "name": format!("amail {address}"), "enabled": true, "source": "api",
        "actions": [{"type":"worker","value":[worker_name]}],
        "matchers": [{"type":"literal","field":"to","value":address}]
    });
    let mut response = fetch_json(env, &url, Method::Post, &body).await?;
    if response.status_code() != 200 && response.status_code() != 201 {
        let body = response
            .text()
            .await
            .unwrap_or_default()
            .to_ascii_lowercase();
        if body.contains("limit") || body.contains("maximum") || body.contains("quota") {
            return Err(worker::Error::RustError(
                "routing_capacity_exhausted".into(),
            ));
        }
        return Err(worker::Error::RustError("routing_create_failed".into()));
    }
    let result: CfRuleResult = response.json().await?;
    if !result.success {
        return Err(worker::Error::RustError("routing_create_failed".into()));
    }
    result
        .result
        .map(|rule| rule.id)
        .ok_or_else(|| worker::Error::RustError("routing_create_failed".into()))
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

/// Request exactly 256 dimensions and reject malformed/nonfinite vectors. / 请求恰好 256 维，并拒绝畸形或非有限向量。
pub async fn embed(env: &Env, input: &str, input_type: &str) -> Result<Vec<f32>> {
    if input.is_empty() || input.len() > 12_000 {
        return Err(worker::Error::RustError("embedding_input_size".into()));
    }
    let headers = Headers::new();
    headers.set(
        "Authorization",
        &format!("Bearer {}", env.secret("OPENROUTER_API_KEY")?.to_string()),
    )?;
    headers.set("Content-Type", "application/json")?;
    headers.set("HTTP-Referer", "https://amail.moesegfault.dev")?;
    headers.set("X-Title", "amail")?;
    headers.set("X-OpenRouter-Cache", "false")?;
    let payload = serde_json::json!({
        "model": env.var("OPENROUTER_EMBEDDING_MODEL")?.to_string(),
        "dimensions": 256, "input": input, "input_type": input_type,
        "provider": {"zdr":true,"data_collection":"deny"}
    });
    let mut init = RequestInit::new();
    init.with_method(Method::Post)
        .with_headers(headers)
        .with_body(Some(JsValue::from_str(&payload.to_string())));
    let mut response = Fetch::Request(Request::new_with_init(
        "https://openrouter.ai/api/v1/embeddings",
        &init,
    )?)
    .send()
    .await?;
    if response.status_code() != 200 {
        return Err(worker::Error::RustError("embedding_unavailable".into()));
    }
    let data: EmbeddingResult = response.json().await?;
    let values = data
        .data
        .into_iter()
        .next()
        .ok_or_else(|| worker::Error::RustError("embedding_shape".into()))?
        .embedding;
    if values.len() != 256 || values.iter().any(|x| !x.is_finite()) {
        return Err(worker::Error::RustError("embedding_shape".into()));
    }
    let norm = values.iter().map(|x| x * x).sum::<f64>().sqrt();
    if norm <= 1e-12 || !norm.is_finite() {
        return Err(worker::Error::RustError("embedding_norm".into()));
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
    let result = binding
        .send_with_builder(&builder)
        .await
        .map_err(|_| worker::Error::RustError("send_provider_failed".into()))?;
    Ok(result.message_id())
}
