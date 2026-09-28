//! Mail Worker HTTP client and trace propagation / 邮件 Worker HTTP 客户端与追踪传播。

use crate::{auth, config::Runtime, telemetry};
use anyhow::{bail, Context, Result};
use rand::RngCore;
use reqwest::{
    blocking::{Client, RequestBuilder},
    header::CONTENT_TYPE,
    Method, StatusCode,
};
use serde_json::Value;
use std::time::{Duration, Instant};

/// Authenticated API client / 已认证的 API 客户端。
pub struct Api<'a> {
    cfg: &'a Runtime,
    http: Client,
}

/// A search either has complete results or an owner-scoped continuation job.
/// 检索要么得到完整结果，要么得到限于本账户的续作任务。
pub enum SearchReply {
    /// Fully scored page / 已完整评分的结果页。
    Complete(Value),
    /// Incomplete work; no result is safe to display yet / 尚未完成，不得展示部分结果。
    Running {
        /// Opaque owner-scoped continuation identifier / 限于账户的不透明续作标识。
        job_id: String,
        /// Server-suggested bounded poll delay / 服务端建议的有界轮询间隔。
        retry_after: Duration,
    },
}

/// Parse HTTP 200 as final and HTTP 202 as continuation, never as a partial page.
/// 将 HTTP 200 解释为最终结果、202 解释为续作，绝不误作部分结果页。
fn parse_search_reply(status: StatusCode, bytes: &[u8]) -> Result<SearchReply> {
    let body: Value = serde_json::from_slice(bytes).context("invalid search response JSON")?;
    match status {
        StatusCode::OK => {
            if !body.get("messages").is_some_and(Value::is_array) {
                bail!("completed search response missing messages");
            }
            Ok(SearchReply::Complete(body))
        }
        StatusCode::ACCEPTED => {
            let id = body
                .get("job_id")
                .and_then(Value::as_str)
                .context("accepted search response missing job_id")?;
            if uuid::Uuid::parse_str(id).is_err()
                || body.get("state").and_then(Value::as_str) != Some("running")
            {
                bail!("invalid running search job response");
            }
            let delay = body
                .get("retry_after_ms")
                .and_then(Value::as_u64)
                .unwrap_or(500)
                .clamp(100, 5000);
            Ok(SearchReply::Running {
                job_id: id.to_owned(),
                retry_after: Duration::from_millis(delay),
            })
        }
        _ => bail!("unexpected successful search HTTP status {status}"),
    }
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

    /// Preserve status for asynchronous search while keeping shared telemetry/error handling.
    /// 为异步检索保留状态码，同时复用遥测与错误处理。
    fn execute_with_status(
        &self,
        method: Method,
        path: &str,
        operation: &str,
        json: Option<&Value>,
        zip: Option<&[u8]>,
        idempotency: Option<&str>,
    ) -> Result<(StatusCode, Vec<u8>)> {
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
        Ok((status, body))
    }

    /// Discard status only for endpoints without an asynchronous result contract.
    /// 仅对没有异步结果协议的端点丢弃状态码。
    fn execute(
        &self,
        method: Method,
        path: &str,
        operation: &str,
        json: Option<&Value>,
        zip: Option<&[u8]>,
        idempotency: Option<&str>,
    ) -> Result<Vec<u8>> {
        self.execute_with_status(method, path, operation, json, zip, idempotency)
            .map(|(_, body)| body)
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

    /// Search with server-side AND semantics; never expose partial results.
    /// 按服务端 AND 语义检索；绝不暴露部分结果。
    pub fn search(&self, request: &Value) -> Result<SearchReply> {
        let (status, body) = self.execute_with_status(
            Method::POST,
            "/v1/messages/search",
            "messages.search",
            Some(request),
            None,
            None,
        )?;
        parse_search_reply(status, &body)
    }

    /// Advance an authenticated resumable search job by one bounded step.
    /// 将已认证的可续作检索任务推进一个有界步骤。
    pub fn poll_search_job(&self, id: &str) -> Result<SearchReply> {
        if uuid::Uuid::parse_str(id).is_err() {
            bail!("search job id must be a UUID");
        }
        let (status, body) = self.execute_with_status(
            Method::GET,
            &format!("/v1/messages/search/jobs/{}", segment(id)),
            "messages.search.poll",
            None,
            None,
            None,
        )?;
        parse_search_reply(status, &body)
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

    #[test]
    fn accepted_search_is_not_mistaken_for_a_result_page() {
        let id = "123e4567-e89b-42d3-a456-426614174000";
        let body = serde_json::json!({"job_id":id,"state":"running","retry_after_ms":500});
        let reply = parse_search_reply(StatusCode::ACCEPTED, body.to_string().as_bytes()).unwrap();
        match reply {
            SearchReply::Running {
                job_id,
                retry_after,
            } => {
                assert_eq!(job_id, id);
                assert_eq!(retry_after, Duration::from_millis(500));
            }
            SearchReply::Complete(_) => panic!("202 cannot be final"),
        }
    }

    #[test]
    fn completed_search_requires_final_messages() {
        let complete = br#"{"messages":[],"next_cursor":null}"#;
        assert!(matches!(
            parse_search_reply(StatusCode::OK, complete).unwrap(),
            SearchReply::Complete(_)
        ));
        assert!(parse_search_reply(StatusCode::OK, br#"{"state":"running"}"#).is_err());
        assert!(parse_search_reply(StatusCode::ACCEPTED, br#"{"messages":[]}"#).is_err());
    }
}
