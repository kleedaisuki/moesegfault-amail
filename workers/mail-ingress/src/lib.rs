//! Private SMTP-event transport for the Rust mail API. / Rust 邮件 API 的私有 SMTP 事件传输层。
//!
//! Only envelope-to and bounded RFC 822 bytes cross the service binding. Business policy,
//! mailbox ownership, parsing, and persistence remain in `amail-worker`.
//! 仅信封收件人和有界 RFC 822 字节经过服务绑定；业务策略、邮箱归属、解析与持久化留在 `amail-worker`。

use futures_util::StreamExt;
use worker::{event, Env, Error, ForwardableEmailMessage, Headers, Method, RequestInit, Result};

/// Maximum MIME size accepted by ingress and the mail API. / 入口与邮件 API 接受的最大 MIME 大小。
const MAX_MIME_BYTES: usize = 25 * 1024 * 1024;

/// Entry point for Cloudflare Email Routing. / Cloudflare Email Routing 事件入口。
///
/// A permanent SMTP rejection is issued only for invalid size or a 4xx API response.
/// A transport error or 5xx is surfaced to Cloudflare rather than silently accepted;
/// the provider's SMTP retry behavior must be verified with a live staging send.
/// 仅大小无效或 API 返回 4xx 时永久拒收；传输失败或 5xx 上报 Cloudflare，
/// 具体 SMTP 重试行为需在预发布环境实测。
#[event(email)]
pub async fn email(
    message: ForwardableEmailMessage,
    env: Env,
    _ctx: worker::Context,
) -> Result<()> {
    // Do not allow a downstream error's URL or envelope text into the event macro's error log.
    // 不允许下游错误中的 URL 或信封内容进入事件宏的错误日志。
    ingest(message, env)
        .await
        .map_err(|_| Error::RustError("amail ingress transport failed".into()))
}

/// Forward one bounded message through the private, environment-specific binding.
/// 通过环境隔离的私有绑定转发一封有界邮件。
async fn ingest(message: ForwardableEmailMessage, env: Env) -> Result<()> {
    if !valid_size(message.raw_size()) {
        message.set_reject("Message exceeds the amail 25 MiB limit");
        return Ok(());
    }

    let mut bytes = Vec::with_capacity((message.raw_size() as usize).min(MAX_MIME_BYTES));
    let mut stream = message.raw_byte_stream();
    while let Some(chunk) = stream.next().await {
        let chunk = chunk?;
        if chunk.len() > MAX_MIME_BYTES - bytes.len() {
            message.set_reject("Message exceeds the amail 25 MiB limit");
            return Ok(());
        }
        bytes.extend_from_slice(&chunk);
    }
    let origin = env.var("MAIL_API_ORIGIN")?.to_string();
    let secret = env.secret("INGRESS_SECRET")?.to_string();
    let mut headers = Headers::new();
    headers.set("content-type", "message/rfc822")?;
    headers.set("x-amail-ingress-secret", &secret)?;
    headers.set("x-amail-envelope-to", &message.to())?;
    headers.set("traceparent", &new_traceparent())?;

    let mut init = RequestInit::new();
    init.with_method(Method::Post)
        .with_headers(headers)
        .with_body(Some(js_sys::Uint8Array::from(bytes.as_slice()).into()));

    let response = env
        .service("MAIL_API")?
        .fetch(format!("{origin}/internal/inbound"), Some(init))
        .await?;
    match classify_status(response.status_code()) {
        Delivery::Accepted => Ok(()),
        Delivery::Reject => {
            message.set_reject("Recipient unavailable or message invalid");
            Ok(())
        }
        Delivery::Retry => Err(Error::RustError("mail API did not accept ingress".into())),
    }
}

/// An outcome tied to SMTP's permanent-versus-transient failure contract.
/// 与 SMTP 永久失败和临时失败语义对应的结果。
#[derive(Debug, Eq, PartialEq)]
enum Delivery {
    Accepted,
    Reject,
    Retry,
}

/// Classify API responses without leaking its body to Cloudflare logs.
/// 在不向 Cloudflare 日志泄露响应正文的前提下分类 API 响应。
fn classify_status(status: u16) -> Delivery {
    match status {
        200..=299 => Delivery::Accepted,
        400..=499 => Delivery::Reject,
        _ => Delivery::Retry,
    }
}

/// Reject non-finite provider metadata as well as oversized messages.
/// 拒绝非有限数值的提供商元数据及超大邮件。
fn valid_size(raw_size: f64) -> bool {
    raw_size.is_finite() && (0.0..=MAX_MIME_BYTES as f64).contains(&raw_size)
}

/// Generate a fresh W3C trace context with no address-derived identifiers.
/// 生成全新 W3C 追踪上下文，不使用从邮件地址派生的标识符。
fn new_traceparent() -> String {
    let trace = uuid::Uuid::new_v4().simple().to_string();
    let span = uuid::Uuid::new_v4().simple().to_string();
    format!("00-{trace}-{}-01", &span[..16])
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Preserve transient/permanent SMTP semantics. / 保持 SMTP 临时和永久失败语义。
    #[test]
    fn status_contract() {
        assert_eq!(classify_status(200), Delivery::Accepted);
        assert_eq!(classify_status(202), Delivery::Accepted);
        assert_eq!(classify_status(400), Delivery::Reject);
        assert_eq!(classify_status(429), Delivery::Reject);
        assert_eq!(classify_status(500), Delivery::Retry);
        assert_eq!(classify_status(599), Delivery::Retry);
    }

    /// Prevent body collection beyond the API cap. / 阻止收集超过 API 上限的正文。
    #[test]
    fn size_contract() {
        assert!(valid_size(MAX_MIME_BYTES as f64));
        assert!(!valid_size(MAX_MIME_BYTES as f64 + 1.0));
        assert!(!valid_size(-1.0));
        assert!(!valid_size(f64::NAN));
    }

    /// Trace IDs must be syntactically valid and change per event.
    /// 追踪 ID 必须格式正确，且每次事件均不同。
    #[test]
    fn trace_contract() {
        let first = new_traceparent();
        let parts: Vec<_> = first.split('-').collect();
        assert_eq!(parts.len(), 4);
        assert_eq!(parts[0], "00");
        assert_eq!(parts[1].len(), 32);
        assert_eq!(parts[2].len(), 16);
        assert_eq!(parts[3], "01");
        assert_ne!(first, new_traceparent());
    }
}
