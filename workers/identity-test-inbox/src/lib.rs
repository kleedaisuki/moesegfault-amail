//! Private staging Identity verification inbox. / 私有的预发布 Identity 验证收件箱。
//!
//! This is a single-purpose SMTP endpoint, not a public mailbox or HTTP API.
//! 这是专用 SMTP 测试入口，不是公共邮箱或 HTTP API。

use futures_util::StreamExt;
use worker::{event, Env, Error, ForwardableEmailMessage, Result};

/// Bound one verification message well below Cloudflare's inbound limit.
/// 将单封验证邮件限制在远低于 Cloudflare 入站上限的大小。
const MAX_MIME_BYTES: usize = 64 * 1024;
/// Isolate each delivery so a spoof or retry cannot overwrite another challenge.
/// 每次投递分别保存，防止伪造邮件或重试覆盖其他挑战。
const OBJECT_PREFIX: &str = "verification/";

/// Accept only explicitly configured apex test aliases; do not trust SMTP envelope sender.
/// 只接受明确配置的根域测试别名；不要信任 SMTP 信封发件人。
///
/// Cloudflare Sending may set the envelope sender to a bounce processor, so
/// sender filtering could reject the legitimate challenge without preventing spoofing.
/// Cloudflare Sending 可能将信封发件人改为退信处理地址；按其过滤会错拒合法挑战且无法防伪。
#[event(email)]
pub async fn email(
    message: ForwardableEmailMessage,
    env: Env,
    _ctx: worker::Context,
) -> Result<()> {
    accept(message, env)
        .await
        .map_err(|_| Error::RustError("identity test inbox unavailable".into()))
}

/// Store one bounded raw MIME message; never print its headers, body, or code.
/// 保存一封有界原始 MIME 邮件，绝不打印邮件头、正文或验证码。
async fn accept(message: ForwardableEmailMessage, env: Env) -> Result<()> {
    if !valid_recipient(&message.to(), &env.var("TEST_RECIPIENTS")?.to_string()) {
        message.set_reject("Recipient unavailable");
        return Ok(());
    }
    let size = message.raw_size();
    if !size.is_finite() || !(0.0..=MAX_MIME_BYTES as f64).contains(&size) {
        message.set_reject("Message exceeds test inbox limit");
        return Ok(());
    }
    let mut raw = Vec::with_capacity(size as usize);
    let mut stream = message.raw_byte_stream();
    while let Some(chunk) = stream.next().await {
        let chunk = chunk?;
        if chunk.len() > MAX_MIME_BYTES - raw.len() {
            message.set_reject("Message exceeds test inbox limit");
            return Ok(());
        }
        raw.extend_from_slice(&chunk);
    }
    env.bucket("PRIVATE_INBOX")?
        .put(&object_key(), raw)
        .execute()
        .await?;
    Ok(())
}

/// Generate a per-message key without mail content, sender, or a shared pointer.
/// 生成逐封独立的键，不包含邮件正文、发件人或共享指针。
fn object_key() -> String {
    format!("{OBJECT_PREFIX}{}.eml", uuid::Uuid::new_v4())
}

/// Exact deployed allowlist prevents reuse as a user mailbox or production inbox.
/// 部署时的精确白名单防止复用成用户邮箱或生产收件箱。
fn valid_recipient(to: &str, recipients: &str) -> bool {
    !to.is_empty()
        && recipients
            .split(',')
            .any(|recipient| !recipient.is_empty() && recipient.eq_ignore_ascii_case(to))
}

#[cfg(test)]
mod tests {
    use super::{object_key, valid_recipient, OBJECT_PREFIX};

    /// Reject accidental cross-realm reuse. / 拒绝意外跨身份域复用。
    #[test]
    fn accepts_only_dedicated_alias() {
        let allowlist = "amail-e2e@moesegfault.dev,amail-e2e-isolation@moesegfault.dev";
        assert!(valid_recipient("amail-e2e@moesegfault.dev", allowlist));
        assert!(valid_recipient(
            "amail-e2e-isolation@moesegfault.dev",
            allowlist
        ));
        assert!(!valid_recipient(
            "amail-e2e@mail.moesegfault.dev",
            allowlist
        ));
        assert!(!valid_recipient("other@moesegfault.dev", allowlist));
    }

    /// Every accepted delivery has a separate private object.
    /// 每次接受的投递都有独立私有对象。
    #[test]
    fn keys_are_unique_and_content_free() {
        let first = object_key();
        let second = object_key();
        assert_ne!(first, second);
        assert!(first.starts_with(OBJECT_PREFIX));
        assert!(first.ends_with(".eml"));
    }
}
