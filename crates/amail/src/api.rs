//! Mail Worker HTTP client and trace propagation / 邮件 Worker HTTP 客户端与追踪传播。

use crate::{auth, config::Runtime, telemetry};
use anyhow::{bail, Context, Result};
use rand::RngCore;
use reqwest::{
    blocking::{Client, RequestBuilder},
    header::CONTENT_TYPE,
    Method,
};
use serde_json::Value;
use std::time::{Duration, Instant};

/// Authenticated API client / 已认证的 API 客户端。
pub struct Api<'a> {
    cfg: &'a Runtime,
    http: Client,
}

fn hex_random(size: usize) -> String {
    let mut bytes = vec![0u8; size];
    rand::thread_rng().fill_bytes(&mut bytes);
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

fn segment(value: &str) -> String {
    url::form_urlencoded::byte_serialize(value.as_bytes()).collect()
}

/// Keep mailbox addresses in the request body, never in automatic URL traces.
/// 将邮箱地址放入请求体，绝不放入自动记录的 URL 追踪字段。
fn address_delete_parts(address: &str) -> (Method, &'static str, Value) {
    (
        Method::DELETE,
        "/v1/addresses",
        serde_json::json!({"address":address}),
    )
}

impl<'a> Api<'a> {
    /// Construct bounded-time client / 创建具有超时的客户端。
    pub fn new(cfg: &'a Runtime) -> Result<Self> {
        Ok(Self {
            cfg,
            http: Client::builder().timeout(Duration::from_secs(30)).build()?,
        })
    }

    fn execute(
        &self,
        method: Method,
        path: &str,
        operation: &str,
        json: Option<&Value>,
        zip: Option<&[u8]>,
        idempotency: Option<&str>,
    ) -> Result<Vec<u8>> {
        let token = auth::access_token(self.cfg)?;
        let trace_id = hex_random(16);
        let span_id = hex_random(8);
        let traceparent = format!("00-{trace_id}-{span_id}-01");
        let mut request: RequestBuilder = self
            .http
            .request(method, format!("{}{}", self.cfg.api_base, path))
            .bearer_auth(&token)
            .header("traceparent", traceparent);
        if let Some(value) = json {
            request = request.json(value);
        }
        if let Some(bytes) = zip {
            request = request
                .header(CONTENT_TYPE, "application/zip")
                .body(bytes.to_vec());
        }
        if let Some(key) = idempotency {
            request = request.header("Idempotency-Key", key);
        }
        let start = Instant::now();
        let response = request.send();
        let response = match response {
            Ok(value) => value,
            Err(err) => {
                telemetry::record(
                    self.cfg,
                    operation,
                    0,
                    start.elapsed().as_millis() as u64,
                    0,
                    &trace_id,
                    None,
                );
                return Err(err.into());
            }
        };
        let status = response.status();
        let correlation = response
            .headers()
            .get("x-moesegfault-correlation-id")
            .or_else(|| response.headers().get("x-amail-request-id"))
            .and_then(|v| v.to_str().ok())
            .map(str::to_owned);
        let body = response.bytes()?.to_vec();
        telemetry::record(
            self.cfg,
            operation,
            status.as_u16(),
            start.elapsed().as_millis() as u64,
            body.len(),
            &trace_id,
            correlation.as_deref(),
        );
        if !status.is_success() {
            let problem: Value = serde_json::from_slice(&body).unwrap_or(Value::Null);
            let code = problem
                .get("code")
                .or_else(|| problem.get("error_code"))
                .and_then(Value::as_str)
                .unwrap_or("http_error");
            bail!(
                "mail API {operation} failed: HTTP {status}, code={code}, correlation_id={}",
                correlation.as_deref().unwrap_or("none")
            );
        }
        Ok(body)
    }

    fn json(
        &self,
        method: Method,
        path: &str,
        operation: &str,
        body: Option<&Value>,
    ) -> Result<Value> {
        let bytes = self.execute(method, path, operation, body, None, None)?;
        if bytes.is_empty() {
            return Ok(serde_json::json!({"ok":true}));
        }
        serde_json::from_slice(&bytes)
            .with_context(|| format!("invalid JSON response for {operation}"))
    }

    /// List owned addresses / 列出拥有的地址。
    pub fn addresses(&self) -> Result<Value> {
        self.json(Method::GET, "/v1/addresses", "addresses.list", None)
    }

    /// Reserve an address / 预留地址。
    pub fn add_address(&self, local_part: &str) -> Result<Value> {
        self.json(
            Method::POST,
            "/v1/addresses",
            "addresses.add",
            Some(&serde_json::json!({"local_part":local_part})),
        )
    }

    /// Retire an address / 退役地址。
    pub fn delete_address(&self, address: &str) -> Result<Value> {
        let (method, path, body) = address_delete_parts(address);
        self.json(method, path, "addresses.delete", Some(&body))
    }

    /// List recent mail summaries / 列出近期邮件摘要。
    pub fn messages(&self, limit: u32, cursor: Option<&str>) -> Result<Value> {
        let mut url = url::Url::parse("https://example.invalid/v1/messages")?;
        url.query_pairs_mut()
            .append_pair("limit", &limit.to_string());
        if let Some(cursor) = cursor {
            url.query_pairs_mut().append_pair("cursor", cursor);
        }
        self.json(
            Method::GET,
            &format!(
                "{}{}",
                url.path(),
                url.query().map(|q| format!("?{q}")).unwrap_or_default()
            ),
            "messages.list",
            None,
        )
    }

    /// Search with server-side AND semantics / 按服务端 AND 语义检索。
    pub fn search(&self, request: &Value) -> Result<Value> {
        self.json(
            Method::POST,
            "/v1/messages/search",
            "messages.search",
            Some(request),
        )
    }

    /// Fetch metadata without changing read state / 获取元数据且不改变已读状态。
    pub fn message(&self, id: &str) -> Result<Value> {
        self.json(
            Method::GET,
            &format!("/v1/messages/{}", segment(id)),
            "messages.get",
            None,
        )
    }

    /// Fetch a ZIP without changing read state / 获取 ZIP 且不改变已读状态。
    pub fn archive(&self, id: &str) -> Result<Vec<u8>> {
        self.execute(
            Method::GET,
            &format!("/v1/messages/{}/archive", segment(id)),
            "messages.archive",
            None,
            None,
            None,
        )
    }

    /// Explicitly mark read or unread / 显式标记已读或未读。
    pub fn mark(&self, id: &str, read: bool) -> Result<Value> {
        self.json(
            Method::PATCH,
            &format!("/v1/messages/{}", segment(id)),
            "messages.mark",
            Some(&serde_json::json!({"read":read})),
        )
    }

    /// Delete the caller's delivery / 删除调用者拥有的投递副本。
    pub fn delete(&self, id: &str) -> Result<Value> {
        self.json(
            Method::DELETE,
            &format!("/v1/messages/{}", segment(id)),
            "messages.delete",
            None,
        )
    }

    /// Submit a validated ZIP with stable idempotency for unresolved attempts.
    /// 使用未决尝试的稳定幂等键提交校验后的 ZIP。
    pub fn send(&self, bytes: &[u8], key: &str) -> Result<Value> {
        let response = self.execute(
            Method::POST,
            "/v1/messages/send",
            "messages.send",
            None,
            Some(bytes),
            Some(key),
        )?;
        serde_json::from_slice(&response).context("invalid send response")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn address_deletion_keeps_personal_address_out_of_url() {
        let address = "alice@mail.moesegfault.dev";
        let (method, path, body) = address_delete_parts(address);
        assert_eq!(method, Method::DELETE);
        assert_eq!(path, "/v1/addresses");
        assert!(!path.contains(address));
        assert_eq!(body["address"], address);
    }
}
