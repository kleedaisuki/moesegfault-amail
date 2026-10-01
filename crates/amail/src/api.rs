//! Mail Worker HTTP client and trace propagation / 邮件 Worker HTTP 客户端与追踪传播。

use crate::{auth, config::Runtime, telemetry};
use anyhow::{bail, Context, Result};
use reqwest::{
    blocking::{Client, RequestBuilder},
    header::{HeaderMap, CONTENT_TYPE},
    Method, StatusCode,
};
use serde_json::Value;
use std::{fmt, time::Duration};

/// Preserve the public CLI error text while retaining a typed retry discriminator.
#[derive(Debug)]
struct ApiFailure {
    status: StatusCode,
    code: String,
    message: String,
}

impl fmt::Display for ApiFailure {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message)
    }
}

impl std::error::Error for ApiFailure {}

/// Retry only a fresh, cursorless list rejected by the search generation guard.
/// One retry adds at most one 30-second HTTP timeout and a 100 ms pause.
fn cursorless_list<F, D>(cursor: Option<&str>, mut request: F, mut delay: D) -> Result<Value>
where
    F: FnMut() -> Result<Value>,
    D: FnMut(Duration),
{
    match request() {
        Err(error)
            if cursor.is_none()
                && error.downcast_ref::<ApiFailure>().is_some_and(|failure| {
                    failure.status == StatusCode::CONFLICT && failure.code == "search_job_stale"
                }) =>
        {
            delay(Duration::from_millis(100));
            request()
        }
        result => result,
    }
}

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

/// Accept only the staging add diagnostic's closed, canonical wire grammar.
/// Unknown server or intermediary headers must never enter CLI stderr.
fn address_diag(headers: &HeaderMap) -> Option<&str> {
    let mut values = headers.get_all("x-amail-address-diag").iter();
    let value = values.next()?.to_str().ok()?;
    if values.next().is_some() {
        return None;
    }
    let mut parts = value.split(':');
    if parts.next()? != "v1" {
        return None;
    }
    let phase = parts.next()?;
    if !matches!(
        phase,
        "input"
            | "d1_lookup"
            | "d1_allocate"
            | "d1_claim"
            | "routing_list"
            | "routing_create"
            | "d1_activate"
            | "d1_readback"
            | "response_encode"
            | "success"
    ) {
        return None;
    }
    let kind = parts.next()?;
    if !matches!(
        kind,
        "none" | "request" | "http" | "provider" | "decode" | "d1" | "state"
    ) {
        return None;
    }
    let status = parts.next()?;
    let code = parts.next()?;
    if parts.next().is_some()
        || !canonical_number(status, 100, 599)
        || !canonical_number(code, 1000, 999_999)
    {
        return None;
    }
    Some(value)
}

/// Only a single UUID may link a response to telemetry and stderr.
/// Do not use untrusted header bytes as a log or terminal string.
fn header_uuid(headers: &HeaderMap, name: &str) -> Option<String> {
    let mut values = headers.get_all(name).iter();
    let value = values.next()?.to_str().ok()?;
    if values.next().is_some() {
        return None;
    }
    let uuid = uuid::Uuid::parse_str(value).ok()?;
    if uuid.hyphenated().to_string() != value {
        return None;
    }
    Some(value.to_owned())
}

/// Prefer the Mail Worker's request ID; a malformed primary cannot be rescued by fallback.
pub(crate) fn response_correlation(headers: &HeaderMap) -> Option<String> {
    if headers.contains_key("x-amail-request-id") {
        header_uuid(headers, "x-amail-request-id")
    } else {
        header_uuid(headers, "x-moesegfault-correlation-id")
    }
}

/// A phase is causal evidence only when the same response has a canonical Worker ID.
fn address_response_diag(headers: &HeaderMap) -> Option<&str> {
    header_uuid(headers, "x-amail-request-id")?;
    address_diag(headers)
}

/// Classify Cloudflare-generated error pages without trusting header bytes as output.
/// Missing is distinct from any present, unrecognized or duplicated value.
fn cf_error_type(headers: &HeaderMap) -> &'static str {
    let mut values = headers.get_all("cf-error-type").iter();
    let Some(first) = values.next() else {
        return "absent";
    };
    if values.next().is_some() {
        return "other";
    }
    match first.as_bytes() {
        b"1101" => "1101",
        b"1102" => "1102",
        _ => "other",
    }
}

/// Zero denotes an unobserved provider result; all other numbers are canonical decimal.
fn canonical_number(value: &str, min: u32, max: u32) -> bool {
    value == "0"
        || (!value.starts_with('0')
            && value.bytes().all(|byte| byte.is_ascii_digit())
            && value
                .parse::<u32>()
                .is_ok_and(|number| (min..=max).contains(&number)))
}

/// Address-add codes are a closed API vocabulary, not arbitrary response text.
fn address_problem_code(problem: &Value) -> &'static str {
    let code = problem
        .get("code")
        .or_else(|| problem.get("error_code"))
        .and_then(Value::as_str);
    match code {
        Some("service_unavailable") => "service_unavailable",
        Some("not_found") => "not_found",
        Some("routing_unavailable") => "routing_unavailable",
        Some("unauthorized") => "unauthorized",
        Some("forbidden") => "forbidden",
        Some("address_provision_unknown") => "address_provision_unknown",
        Some("invalid_json") => "invalid_json",
        Some("address_deleting") => "address_deleting",
        Some("address_limit") => "address_limit",
        Some("address_retired") => "address_retired",
        Some("address_state_changed") => "address_state_changed",
        Some("address_unavailable") => "address_unavailable",
        Some("capacity_exhausted") => "capacity_exhausted",
        Some("reserved_or_invalid_name") => "reserved_or_invalid_name",
        _ => "http_error",
    }
}

/// Keep transport failure output fixed even when reqwest carries a sensitive URL.
pub(crate) fn transport_kind(error: &reqwest::Error) -> &'static str {
    if error.is_timeout() {
        "timeout"
    } else if error.is_connect() {
        "connect"
    } else if error.is_body() {
        "body"
    } else if error.is_decode() {
        "decode"
    } else if error.is_request() {
        "request"
    } else {
        "other"
    }
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
        let journal = telemetry::RequestSpan::new(self.cfg, operation);
        let token = match auth::access_token(self.cfg) {
            Ok(token) => token,
            Err(err) => {
                journal.finish(
                    0,
                    0,
                    None,
                    telemetry::Phase::Auth,
                    Some("credential_unavailable"),
                );
                return Err(err);
            }
        };
        let mut request: RequestBuilder = self
            .http
            .request(method, format!("{}{}", self.cfg.api_base, path))
            .bearer_auth(&token)
            .header("traceparent", journal.traceparent());
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
        self.execute_request(request, operation, journal)
    }

    /// Journal every HTTP completion boundary, including a truncated response.
    fn execute_request(
        &self,
        request: RequestBuilder,
        operation: &str,
        journal: telemetry::RequestSpan<'_>,
    ) -> Result<(StatusCode, Vec<u8>)> {
        let response = request.send();
        let response = match response {
            Ok(value) => value,
            Err(err) => {
                journal.finish(
                    0,
                    0,
                    None,
                    telemetry::Phase::Transport,
                    Some(transport_kind(&err)),
                );
                bail!(
                    "mail API {operation} transport failed: kind={}",
                    transport_kind(&err)
                );
            }
        };
        let status = response.status();
        let correlation = response_correlation(response.headers());
        let diagnostic = (operation == "addresses.add")
            .then(|| address_response_diag(response.headers()))
            .flatten()
            .map(str::to_owned);
        let cf_error = (operation == "addresses.add" && status.is_server_error())
            .then(|| cf_error_type(response.headers()));
        let body = response.bytes();
        let (phase, error_kind) = match &body {
            Ok(_) => (telemetry::Phase::Complete, None),
            Err(err) => (telemetry::Phase::ResponseBody, Some(transport_kind(err))),
        };
        journal.finish(
            status.as_u16(),
            body.as_ref().map_or(0, |bytes| bytes.len()),
            correlation.as_deref(),
            phase,
            error_kind,
        );
        let body = body
            .map_err(|err| {
                anyhow::anyhow!(
                    "mail API {operation} body read failed: kind={}",
                    transport_kind(&err)
                )
            })?
            .to_vec();
        if !status.is_success() {
            let problem: Value = serde_json::from_slice(&body).unwrap_or(Value::Null);
            let raw_code = problem
                .get("code")
                .or_else(|| problem.get("error_code"))
                .and_then(Value::as_str)
                .unwrap_or("http_error");
            let code = if operation == "addresses.add" {
                address_problem_code(&problem)
            } else {
                raw_code
            };
            let mut prefix = format!(
                "mail API {operation} failed: HTTP {status}, code={code}, correlation_id={}",
                correlation.as_deref().unwrap_or("none")
            );
            if let Some(diagnostic) = diagnostic {
                prefix.push_str(&format!(", diag={diagnostic}"));
            }
            if let Some(cf_error) = cf_error {
                prefix.push_str(&format!(", cf_error={cf_error}"));
            }
            return Err(ApiFailure {
                status,
                code: code.to_owned(),
                message: prefix,
            }
            .into());
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
        if operation == "addresses.add" {
            serde_json::from_slice(&bytes)
                .map_err(|_| anyhow::anyhow!("mail API addresses.add response invalid: kind=json"))
        } else {
            serde_json::from_slice(&bytes)
                .with_context(|| format!("invalid JSON response for {operation}"))
        }
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
        let path = format!(
            "{}{}",
            url.path(),
            url.query().map(|q| format!("?{q}")).unwrap_or_default()
        );
        cursorless_list(
            cursor,
            || self.json(Method::GET, &path, "messages.list", None),
            std::thread::sleep,
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
    use reqwest::header::{HeaderMap, HeaderValue};

    /// Exercise real HTTP reads, not a mock of the boundary that lost diagnostics.
    #[test]
    fn journals_complete_error_and_truncated_http_responses_once() {
        use rusqlite::Connection;
        use std::io::{Read, Write};
        use std::net::TcpListener;

        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.temp");
        std::fs::create_dir_all(&root).unwrap();
        let temp = tempfile::tempdir_in(root).unwrap();
        let cfg = telemetry::tests::config(temp.path());
        telemetry::init(&cfg).unwrap();
        let conn = Connection::open(cfg.home.join("telemetry.sqlite3")).unwrap();
        // Do not launch a detached uploader/credential lookup from unit tests.
        conn.execute(
            "INSERT INTO journal_state(key,value) VALUES('last_flush',?1)",
            [i64::MAX],
        )
        .unwrap();
        let api = Api::new(&cfg).unwrap();
        let correlation = "123e4567-e89b-42d3-a456-426614174000";
        for (status, body, declared, expected_phase) in [
            (200, "ok", 2, "complete"),
            (503, "{}", 2, "complete"),
            (200, "cut", 100, "response_body"),
        ] {
            let listener = TcpListener::bind("127.0.0.1:0").unwrap();
            let address = listener.local_addr().unwrap();
            let server = std::thread::spawn(move || {
                let (mut stream, _) = listener.accept().unwrap();
                stream
                    .set_read_timeout(Some(Duration::from_secs(5)))
                    .unwrap();
                let mut received = Vec::new();
                let mut buffer = [0u8; 1024];
                while !received.windows(4).any(|bytes| bytes == b"\r\n\r\n") {
                    let read = stream.read(&mut buffer).unwrap();
                    assert!(read > 0 && received.len() < 8192);
                    received.extend_from_slice(&buffer[..read]);
                }
                write!(stream, "HTTP/1.1 {status} Test\r\nContent-Length: {declared}\r\nX-Amail-Request-Id: {correlation}\r\nConnection: close\r\n\r\n{body}").unwrap();
            });
            let journal = telemetry::RequestSpan::new(&cfg, "messages.list");
            let traceparent = journal.traceparent();
            let result = api.execute_request(
                api.http
                    .get(format!(
                        "http://{address}/private-path?search=private-query"
                    ))
                    .header("traceparent", &traceparent),
                "messages.list",
                journal,
            );
            server.join().unwrap();
            assert_eq!(result.is_ok(), status == 200 && declared == body.len());
            let row: (u16, String, Option<String>, String, String, String, i64) = conn.query_row(
                "SELECT status,phase,error_kind,correlation_id,trace_id,span_id,started_at_ms FROM events ORDER BY id DESC LIMIT 1",
                [], |r| Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?,r.get(4)?,r.get(5)?,r.get(6)?))
            ).unwrap();
            assert_eq!(row.0, status);
            assert_eq!(row.1, expected_phase);
            assert_eq!(row.2.is_some(), expected_phase == "response_body");
            assert_eq!(row.3, correlation);
            assert_eq!(traceparent, format!("00-{}-{}-01", row.4, row.5));
            assert!(row.6 > 0);
            if let Err(error) = result {
                assert!(!error.to_string().contains("private-"));
            }
        }
        let count: i64 = conn
            .query_row("SELECT COUNT(*) FROM events", [], |r| r.get(0))
            .unwrap();
        assert_eq!(count, 3);
        // A request-construction failure is recorded without inventing HTTP status.
        let journal = telemetry::RequestSpan::new(&cfg, "messages.list");
        let result = api.execute_request(
            api.http
                .get("http://127.0.0.1/")
                .header("invalid", "bad\nprivate-value"),
            "messages.list",
            journal,
        );
        assert!(result.is_err());
        let row: (u16, String, Option<String>) = conn
            .query_row(
                "SELECT status,phase,error_kind FROM events ORDER BY id DESC LIMIT 1",
                [],
                |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
            )
            .unwrap();
        assert_eq!(row.0, 0);
        assert_eq!(row.1, "transport");
        assert!(row.2.is_some());
        let values: Vec<String> = conn
            .prepare(
                "SELECT operation || COALESCE(error_kind,'') || trace_id || span_id FROM events",
            )
            .unwrap()
            .query_map([], |r| r.get(0))
            .unwrap()
            .collect::<Result<_, _>>()
            .unwrap();
        assert!(values.iter().all(|value| !value.contains("private-")));
    }

    /// Auth acquisition failure belongs to the same attempted operation's journal.
    #[test]
    fn journals_auth_failure_before_any_request_is_sent() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.temp");
        std::fs::create_dir_all(&root).unwrap();
        let temp = tempfile::tempdir_in(root).unwrap();
        let mut cfg = telemetry::tests::config(temp.path());
        cfg.client_id.clear(); // Fails before keyring, token refresh or network use.
        telemetry::init(&cfg).unwrap();
        let conn = rusqlite::Connection::open(cfg.home.join("telemetry.sqlite3")).unwrap();
        conn.execute(
            "INSERT INTO journal_state(key,value) VALUES('last_flush',?1)",
            [i64::MAX],
        )
        .unwrap();
        assert!(Api::new(&cfg).unwrap().addresses().is_err());
        let row: (String, u16, String, String) = conn
            .query_row(
                "SELECT operation,status,phase,error_kind FROM events",
                [],
                |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?)),
            )
            .unwrap();
        assert_eq!(
            row,
            (
                "addresses.list".into(),
                0,
                "auth".into(),
                "credential_unavailable".into()
            )
        );
    }

    fn failure(status: StatusCode, code: &str) -> anyhow::Error {
        ApiFailure {
            status,
            code: code.to_owned(),
            message: format!(
                "mail API messages.list failed: HTTP {status}, code={code}, correlation_id=none"
            ),
        }
        .into()
    }

    #[test]
    fn cursorless_stale_list_retries_once_without_exposing_first_result() {
        let mut calls = 0;
        let mut delays = Vec::new();
        let page = cursorless_list(
            None,
            || {
                calls += 1;
                if calls == 1 {
                    Err(failure(StatusCode::CONFLICT, "search_job_stale"))
                } else {
                    Ok(serde_json::json!({"messages":[{"id":"m1"}],"next_cursor":null}))
                }
            },
            |duration| delays.push(duration),
        )
        .unwrap();
        assert_eq!(calls, 2);
        assert_eq!(delays, [Duration::from_millis(100)]);
        assert_eq!(page["messages"][0]["id"], "m1");
    }

    #[test]
    fn persistent_stale_list_fails_after_one_retry() {
        let mut calls = 0;
        let error = cursorless_list(
            None,
            || {
                calls += 1;
                Err(failure(StatusCode::CONFLICT, "search_job_stale"))
            },
            |_| {},
        )
        .unwrap_err();
        assert_eq!(calls, 2);
        assert!(error.to_string().contains("code=search_job_stale"));
    }

    #[test]
    fn list_retry_does_not_restart_cursor_or_other_failures() {
        for (cursor, status, code) in [
            (Some("opaque"), StatusCode::CONFLICT, "search_job_stale"),
            (None, StatusCode::CONFLICT, "search_cursor_stale"),
            (None, StatusCode::CONFLICT, "unrelated_conflict"),
            (None, StatusCode::SERVICE_UNAVAILABLE, "search_job_stale"),
        ] {
            let mut calls = 0;
            let mut delayed = false;
            let error = cursorless_list(
                cursor,
                || {
                    calls += 1;
                    Err(failure(status, code))
                },
                |_| delayed = true,
            )
            .unwrap_err();
            assert_eq!(calls, 1, "{cursor:?} {status} {code}");
            assert!(!delayed);
            assert!(error.to_string().contains(&format!("code={code}")));
        }
    }

    fn diagnostic_header(value: &str) -> HeaderMap {
        let mut headers = HeaderMap::new();
        headers.insert(
            "x-amail-address-diag",
            HeaderValue::from_str(value).unwrap(),
        );
        headers
    }

    #[test]
    fn address_diagnostic_accepts_only_closed_canonical_header() {
        let good = "v1:routing_create:provider:403:10000";
        assert_eq!(address_diag(&diagnostic_header(good)), Some(good));
        assert_eq!(
            address_diag(&diagnostic_header("v1:d1_claim:d1:0:0")),
            Some("v1:d1_claim:d1:0:0")
        );
        for bad in [
            "v1:other:provider:403:10000",
            "v1:routing_create:other:403:10000",
            "v1:routing_create:provider:0403:10000",
            "v1:routing_create:provider:200:01000",
            "v1:routing_create:provider:600:10000",
            "v1:routing_create:provider:200:1000000",
            "v1:routing_create:provider:200:10000:private",
            "v2:routing_create:provider:200:10000",
            "v1:routing_create:provider:200:-1",
        ] {
            assert_eq!(address_diag(&diagnostic_header(bad)), None, "{bad}");
        }
        let mut duplicate = diagnostic_header(good);
        duplicate.append("x-amail-address-diag", HeaderValue::from_static(good));
        assert_eq!(address_diag(&duplicate), None);
    }

    #[test]
    fn untrusted_problem_code_never_reaches_output() {
        assert_eq!(
            address_problem_code(&serde_json::json!({"code":"routing_unavailable"})),
            "routing_unavailable"
        );
        assert_eq!(
            address_problem_code(&serde_json::json!({"code":"private-address@example.org"})),
            "http_error"
        );
        assert_eq!(
            address_problem_code(&serde_json::json!({"message":"secret"})),
            "http_error"
        );
    }

    #[test]
    fn correlation_requires_one_canonical_uuid() {
        let id = "123e4567-e89b-42d3-a456-426614174000";
        let mut headers = HeaderMap::new();
        headers.insert("x-amail-request-id", HeaderValue::from_static(id));
        assert_eq!(response_correlation(&headers).as_deref(), Some(id));

        headers.append("x-amail-request-id", HeaderValue::from_static(id));
        assert_eq!(response_correlation(&headers), None);

        headers.clear();
        headers.insert(
            "x-amail-request-id",
            HeaderValue::from_static("private-address@example.org"),
        );
        headers.insert("x-moesegfault-correlation-id", HeaderValue::from_static(id));
        assert_eq!(response_correlation(&headers), None);

        headers.clear();
        headers.insert("x-moesegfault-correlation-id", HeaderValue::from_static(id));
        assert_eq!(response_correlation(&headers).as_deref(), Some(id));
        assert!(HeaderValue::from_bytes(b"secret\r\nX-Leak: yes").is_err());
    }

    #[test]
    fn address_phase_requires_canonical_primary_worker_id() {
        let id = HeaderValue::from_static("123e4567-e89b-42d3-a456-426614174000");
        let diag = "v1:routing_list:http:403:0";
        let mut headers = diagnostic_header(diag);
        assert_eq!(address_response_diag(&headers), None);

        headers.insert("x-moesegfault-correlation-id", id.clone());
        assert_eq!(address_response_diag(&headers), None);

        headers.insert(
            "x-amail-request-id",
            HeaderValue::from_static("private-address@example.org"),
        );
        assert_eq!(address_response_diag(&headers), None);

        headers.insert("x-amail-request-id", id.clone());
        assert_eq!(address_response_diag(&headers), Some(diag));

        headers.append("x-amail-request-id", id);
        assert_eq!(address_response_diag(&headers), None);
    }

    #[test]
    fn cloudflare_error_type_is_a_closed_response_category() {
        let mut headers = HeaderMap::new();
        assert_eq!(cf_error_type(&headers), "absent");
        headers.insert("cf-error-type", HeaderValue::from_static("1101"));
        assert_eq!(cf_error_type(&headers), "1101");
        headers.insert("cf-error-type", HeaderValue::from_static("1102"));
        assert_eq!(cf_error_type(&headers), "1102");
        headers.insert(
            "cf-error-type",
            HeaderValue::from_static("private@example.test"),
        );
        assert_eq!(cf_error_type(&headers), "other");
        headers.append("cf-error-type", HeaderValue::from_static("1101"));
        assert_eq!(cf_error_type(&headers), "other");
    }

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
