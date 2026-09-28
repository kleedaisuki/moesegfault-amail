//! Privacy-limited Cloudflare Email Sending lifecycle consumer.
//! Cloudflare Email Sending 生命周期事件的隐私受限消费者。

use chrono::DateTime;
use serde::Deserialize;
use serde_json::Value;
use wasm_bindgen::JsValue;
use worker::{console_log, console_warn, event, Env, MessageBatch, MessageExt, Result};

/// A typed subset of the provider schema; raw subject and SMTP detail are discarded.
/// 提供商模式的类型化子集；丢弃原始标题及 SMTP 详情。
#[derive(Debug, Deserialize)]
struct SendingEvent {
    #[serde(rename = "type")]
    event_type: String,
    source: Source,
    payload: Payload,
    metadata: Metadata,
}

/// Cloudflare's account-scoped event source identity. / Cloudflare 账户级事件来源身份。
#[derive(Debug, Deserialize)]
struct Source {
    #[serde(rename = "type")]
    source_type: String,
    #[serde(rename = "zoneId")]
    zone_id: String,
    domain: String,
}

/// Only the immutable provider ID and envelope fields needed for attribution.
/// 仅保留归因需要的不可变提供商 ID 与信封字段。
#[derive(Debug, Deserialize)]
struct Payload {
    #[serde(rename = "eventId")]
    event_id: String,
    #[serde(rename = "messageId")]
    message_id: String,
    sender: String,
    recipient: String,
}

/// Version and timestamp bound the interpretation of the provider payload.
/// 版本和时间戳限定提供商负载的解释方式。
#[derive(Debug, Deserialize)]
struct Metadata {
    #[serde(rename = "accountId")]
    account_id: String,
    #[serde(rename = "eventSchemaVersion")]
    schema_version: u32,
    #[serde(rename = "eventTimestamp")]
    timestamp: String,
}

/// A single provider ID resolves to one durable send even after archive deletion.
/// 单个提供商 ID 解析至一条持久发件记录，即使归档已删除亦然。
#[derive(Debug, Deserialize)]
struct Attribution {
    owner_iss: String,
    owner_sub: String,
    local_message_id: String,
    request_id: Option<String>,
    sender: String,
    envelope_json: String,
}

/// Queue entry point: acknowledge only committed events; retry failures into the DLQ.
/// 队列入口：仅确认已提交事件；失败事件重试后进入死信队列。
#[event(queue)]
pub async fn queue(batch: MessageBatch<Value>, env: Env, _ctx: worker::Context) -> Result<()> {
    let messages = match batch.messages() {
        Ok(messages) => messages,
        Err(_) => {
            console_warn!("amail lifecycle batch could not be decoded");
            batch.retry_all();
            return Ok(());
        }
    };
    for message in messages {
        match process(message.body(), &env).await {
            Ok(Some((kind, request_id))) => {
                // The API generated this opaque UUID; never log provider IDs or addresses.
                // 该不透明 UUID 由 API 生成；绝不记录提供商 ID 或地址。
                console_log!(
                    "amail lifecycle kind={} request_id={}",
                    kind,
                    request_id.unwrap_or_else(|| "legacy".into())
                );
                message.ack();
            }
            Ok(None) => message.ack(),
            Err(_) => {
                // Do not log queue bodies, subject, addresses, SMTP text, or D1 errors.
                // 不记录队列正文、标题、地址、SMTP 文本或 D1 错误。
                console_warn!("amail lifecycle event requires retry");
                message.retry();
            }
        }
    }
    Ok(())
}

/// Validate provider origin and attribute to the exact stored envelope recipient.
/// 验证提供商来源，并归因至所存信封中的精确收件人。
async fn process(body: &Value, env: &Env) -> Result<Option<(String, Option<String>)>> {
    let event: SendingEvent = serde_json::from_value(body.clone())?;
    let account = env.var("CF_ACCOUNT_ID")?.to_string();
    let zone = env.var("CF_ZONE_ID")?.to_string();
    let domain = env.var("MAIL_DOMAIN")?.to_string();
    let normalized = validate(&event, &account, &zone, &domain)
        .ok_or_else(|| worker::Error::RustError("lifecycle event invalid".into()))?;
    let db = env.d1("MAIL_DB")?;
    let rows = db
        .prepare("SELECT owner_iss,owner_sub,message_id AS local_message_id,request_id,sender,envelope_json FROM send_requests WHERE provider_id=?1 AND state IN ('accepted','sent') AND message_id IS NOT NULL AND sender IS NOT NULL AND envelope_json IS NOT NULL LIMIT 2")
        .bind(&[JsValue::from_str(&event.payload.message_id)])?
        .all()
        .await?
        .results::<Attribution>()?;
    let [row] = rows.as_slice() else {
        // A legacy send may need cron backfill; retry before DLQ review.
        // 旧版发件可能需要定时回填；先重试，随后由死信队列人工复核。
        return Err(worker::Error::RustError(
            "lifecycle attribution unavailable".into(),
        ));
    };
    let envelope: Vec<String> = serde_json::from_str(&row.envelope_json)?;
    if !matches_envelope(&row.sender, &envelope, &event.payload) {
        return Err(worker::Error::RustError(
            "lifecycle envelope mismatch".into(),
        ));
    }
    let received_at = (js_sys::Date::now() / 1000.0) as i64;
    let args = [
        JsValue::from_str(&event.payload.event_id),
        JsValue::from_str(&event.payload.message_id),
        JsValue::from_str(&row.local_message_id),
        JsValue::from_str(&row.owner_iss),
        JsValue::from_str(&row.owner_sub),
        JsValue::from_str(&normalized),
        JsValue::from_str(kind(&event.event_type).unwrap_or_default()),
        JsValue::from_f64(timestamp(&event.metadata.timestamp).unwrap_or_default() as f64),
        JsValue::from_f64(received_at as f64),
    ];
    let result = db.prepare("INSERT OR IGNORE INTO provider_events(event_id,provider_id,local_message_id,owner_iss,owner_sub,recipient,kind,occurred_at,received_at) VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9)")
        .bind(&args)?.run().await?;
    if result.meta()?.and_then(|meta| meta.changes).unwrap_or(0) == 0 {
        return Ok(None);
    }
    Ok(Some((
        kind(&event.event_type).unwrap_or_default().into(),
        row.request_id.clone(),
    )))
}

/// The provider event must name the original sender and one private envelope
/// recipient, including Cc/Bcc, not merely a To summary recipient.
/// 提供商事件必须匹配原发件人和私密信封中的收件人（含抄送与密送），不能仅匹配公开 To 摘要。
fn matches_envelope(sender: &str, envelope: &[String], payload: &Payload) -> bool {
    sender.eq_ignore_ascii_case(&payload.sender)
        && envelope
            .iter()
            .any(|r| r.eq_ignore_ascii_case(&payload.recipient))
}

/// Accept only known lifecycle events from this account, zone, domain and schema.
/// 仅接受所属账户、区域、域名及已知模式的生命周期事件。
fn validate(event: &SendingEvent, account: &str, zone: &str, domain: &str) -> Option<String> {
    if event.source.source_type != "email.sending"
        || event.source.zone_id != zone
        || event.source.domain != domain
        || event.metadata.account_id != account
        || event.metadata.schema_version != 1
        || kind(&event.event_type).is_none()
        || timestamp(&event.metadata.timestamp).is_none()
        || event.payload.event_id.len() > 128
        || event.payload.event_id.is_empty()
        || event.payload.message_id.len() > 256
        || event.payload.message_id.is_empty()
        || event.payload.sender.len() > 320
        || event.payload.recipient.len() > 320
        || !event.payload.sender.contains('@')
        || !event.payload.recipient.contains('@')
    {
        return None;
    }
    Some(event.payload.recipient.to_ascii_lowercase())
}

/// Map the fixed Cloudflare event vocabulary to durable risk states.
/// 将 Cloudflare 固定事件词汇映射至持久风险状态。
fn kind(value: &str) -> Option<&'static str> {
    match value {
        "cf.email.sending.message.deferred" => Some("deferred"),
        "cf.email.sending.message.delivered" => Some("delivered"),
        "cf.email.sending.message.bounced" => Some("bounced"),
        "cf.email.sending.message.failed" => Some("failed"),
        "cf.email.sending.message.rejected" => Some("rejected"),
        "cf.email.sending.message.complained" => Some("complained"),
        _ => None,
    }
}

/// Parse RFC 3339 milliseconds without relying on the local machine timezone.
/// 解析 RFC 3339 毫秒时间，不依赖本地时区。
fn timestamp(value: &str) -> Option<i64> {
    DateTime::parse_from_rfc3339(value)
        .ok()
        .map(|dt| dt.timestamp())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The direct-object shape follows Cloudflare's documented
    /// `message.complained` example; live Queue-body shape still needs a canary.
    /// 直接对象结构遵循 Cloudflare 文档中的 `message.complained` 示例；
    /// 实际队列正文形态仍需上线金丝雀验证。
    #[test]
    fn validates_source_and_vocabulary() {
        // https://developers.cloudflare.com/email-service/platform/event-subscriptions/
        let fixture = serde_json::json!({
            "type":"cf.email.sending.message.complained",
            "source":{"type":"email.sending","zoneId":"zone","domain":"mail.example.test"},
            "payload":{"eventId":"event-1","messageId":"provider-1","sender":"a@mail.example.test","recipient":"B@Example.test","terminal":true,"delivery":{"status":"complained"},"complaint":{"type":"abuse"}},
            "metadata":{"accountId":"account","eventSubscriptionId":"subscription-1","eventSchemaVersion":1,"eventTimestamp":"2026-09-28T01:02:03.132Z"}
        });
        let event: SendingEvent = serde_json::from_value(fixture.clone()).unwrap();
        assert_eq!(
            validate(&event, "account", "zone", "mail.example.test"),
            Some("b@example.test".into())
        );
        assert!(validate(&event, "account", "zone", "other.example.test").is_none());
        assert_eq!(timestamp(&event.metadata.timestamp), Some(1_790_557_323));
        let mut future = fixture;
        future["metadata"]["eventSchemaVersion"] = Value::from(2);
        let future: SendingEvent = serde_json::from_value(future).unwrap();
        assert!(validate(&future, "account", "zone", "mail.example.test").is_none());
    }

    /// Bcc feedback attributes to its owner, while another person's recipient fails.
    /// 密送反馈归因至其所有者，其他人的收件人不能通过。
    #[test]
    fn private_envelope_attribution_includes_bcc() {
        let envelope = vec!["to@example.net".into(), "bcc@example.net".into()];
        let payload = Payload {
            event_id: "e".into(),
            message_id: "p".into(),
            sender: "a@mail.example.test".into(),
            recipient: "BCC@EXAMPLE.NET".into(),
        };
        assert!(matches_envelope("a@mail.example.test", &envelope, &payload));
        let other = Payload {
            recipient: "stranger@example.net".into(),
            ..payload
        };
        assert!(!matches_envelope("a@mail.example.test", &envelope, &other));
    }
}
