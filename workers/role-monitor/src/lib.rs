//! Content-free monitoring for reserved system-role mail. / 系统角色邮箱的无正文监控。
//!
//! Only exact role envelopes are accepted. Raw MIME stays in Cloudflare transit and
//! the verified forwarding destination; the isolated D1 records opaque arrivals.
//! 仅接受精确角色信封。原始 MIME 只经过 Cloudflare 并抵达已验证转发地址；
//! 独立 D1 仅记录不透明的到达事件。

use js_sys::Date;
use serde::Deserialize;
use uuid::Uuid;
use wasm_bindgen::JsValue;
use worker::{
    console_log, console_warn, event, Env, Error, Fetch, ForwardableEmailMessage, Headers, Method,
    Request, RequestInit, Result, ScheduledEvent, SendEmailBuilder,
};

/// A lease spans several Cron periods but never substitutes for owner attention.
/// 租约覆盖多个 Cron 周期，但绝不代替所有者实际处理。
const LEASE_MS: i64 = 30 * 60 * 1000;
/// Stale notices invalidate the sender gate even if the Worker itself still runs.
/// 即使 Worker 仍运行，过期的未通知事件也会令发信闸门失效。
const MAX_UNALERTED_MS: i64 = 15 * 60 * 1000;
/// Role arrivals are a bounded operational audit, not a mailbox archive.
/// 角色到达记录是有期限的运维审计，而不是邮件归档。
const RETENTION_MS: i64 = 90 * 24 * 60 * 60 * 1000;
const ZONE_RULES_URL: &str = "https://api.cloudflare.com/client/v4/zones/";
const OFFICIAL_FROM: &str = "mail@moesegfault.dev";

/// One exact envelope and its internal, content-free label. / 单个精确信封及内部无正文标签。
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct Role {
    address: &'static str,
    label: &'static str,
}

/// The public production roles are separate from a single staging-only canary.
/// 公开生产角色与单个预发布金丝雀严格隔离。
const PRODUCTION_ROLES: [Role; 4] = [
    Role {
        address: "abuse@moesegfault.dev",
        label: "apex_abuse",
    },
    Role {
        address: "postmaster@moesegfault.dev",
        label: "apex_postmaster",
    },
    Role {
        address: "abuse@mail.moesegfault.dev",
        label: "mail_abuse",
    },
    Role {
        address: "postmaster@mail.moesegfault.dev",
        label: "mail_postmaster",
    },
];
const STAGING_ROLES: [Role; 1] = [Role {
    address: "amail-role-e2e@moesegfault.dev",
    label: "staging_probe",
}];

/// Read a fixed realm; do not let a deploy variable invent new public recipients.
/// 读取固定环境；部署变量不得自行创造公开收件人。
fn roles(realm: &str) -> Option<&'static [Role]> {
    match realm {
        "production" => Some(&PRODUCTION_ROLES),
        "staging" => Some(&STAGING_ROLES),
        _ => None,
    }
}

/// The Email handler intentionally has no HTTP companion or raw-body parser.
/// Email 处理器刻意不提供 HTTP 入口或原始正文解析器。
#[event(email)]
pub async fn email(
    message: ForwardableEmailMessage,
    env: Env,
    _ctx: worker::Context,
) -> Result<()> {
    handle_email(message, &env)
        .await
        .map_err(|_| Error::RustError("role mail handling unavailable".into()))
}

/// Persist a random arrival before a single forward; unknown outcomes remain visible.
/// 先持久化随机到达 ID，再调用一次转发；未知结果保持可见。
async fn handle_email(message: ForwardableEmailMessage, env: &Env) -> Result<()> {
    let realm = env.var("ROLE_REALM")?.to_string();
    let role = roles(&realm).and_then(|set| {
        set.iter()
            .find(|item| item.address.eq_ignore_ascii_case(&message.to()))
    });
    let Some(role) = role else {
        message.set_reject("Recipient unavailable");
        return Ok(());
    };
    let destination = env.secret("ROLE_FORWARD_DESTINATION")?.to_string();
    if !valid_destination(&destination) {
        return Err(Error::RustError("role destination invalid".into()));
    }
    let db = env.d1("ROLE_MONITOR")?;
    let id = Uuid::new_v4().to_string();
    let received_at = now();
    staging_fault(env, "before_insert")?;
    db.prepare("INSERT INTO role_arrivals(id,role,received_at) VALUES(?1,?2,?3)")
        .bind(&[
            JsValue::from_str(&id),
            JsValue::from_str(role.label),
            JsValue::from_f64(received_at as f64),
        ])?
        .run()
        .await?;

    staging_fault(env, "before_forward")?;
    // The only extra header is an opaque local reference; no message-derived field is logged.
    // 唯一附加头为不透明的本地引用；不记录邮件派生字段。
    let headers = Headers::new();
    headers.set("X-Amail-Role-Ref", &id)?;
    // The Email binding accepts web_sys::Headers, not the worker wrapper type.
    // Email 绑定接受 web_sys::Headers，而不是 worker 的封装类型。
    message
        .forward_with_headers(&destination, &headers.0)
        .await?;
    staging_fault(env, "after_forward")?;
    db.prepare("UPDATE role_arrivals SET forward_state='accepted',forward_updated_at=?2 WHERE id=?1 AND forward_state='unknown'")
        .bind(&[JsValue::from_str(&id), JsValue::from_f64(now() as f64)])?
        .run()
        .await?;
    console_log!("role arrival accepted role={} ref={}", role.label, id);
    Ok(())
}

/// A Cron failure leaves the old lease to expire; never renew from a partial run.
/// Cron 失败时让旧租约到期；部分成功绝不续租。
#[event(scheduled)]
pub async fn scheduled(_event: ScheduledEvent, env: Env, _ctx: worker::ScheduleContext) {
    if run_monitor(&env).await.is_err() {
        console_warn!("role monitor health check failed");
        // workers-rs 0.8.7's scheduled wrapper discards a returned Result.
        // A static panic is therefore required for Cron Past Events to record failure.
        // workers-rs 0.8.7 的 scheduled 包装层会丢弃返回的 Result；
        // 因此使用固定内容的 panic，使 Cron 历史事件明确记为失败。
        panic!("role monitor health check failed");
    }
}

/// Drain the notification outbox, audit all exact rules, then renew the send lease.
/// 清空通知发件箱、审计全部精确规则，然后续租发信闸门。
async fn run_monitor(env: &Env) -> Result<()> {
    let realm = env.var("ROLE_REALM")?.to_string();
    let expected = roles(&realm).ok_or_else(|| Error::RustError("role realm invalid".into()))?;
    let destination = env.secret("ROLE_FORWARD_DESTINATION")?.to_string();
    if !valid_destination(&destination) {
        return Err(Error::RustError("role destination invalid".into()));
    }
    let db = env.d1("ROLE_MONITOR")?;
    phase(
        "digest",
        flush_alerts(env, &db, expected, &destination).await,
    )?;
    phase("destination", audit_destination(env, &destination).await)?;
    phase("routes", audit_rules(env, expected).await)?;
    let pending = phase("lease", check_and_renew(&db).await)?;
    console_log!("role monitor healthy pending={}", pending);
    Ok(())
}

/// Log only a fixed phase name; provider/D1 error details may contain private data.
/// 只记录固定阶段名；供应商或 D1 错误详情可能包含隐私数据。
fn phase<T>(name: &'static str, result: Result<T>) -> Result<T> {
    if result.is_err() {
        console_warn!("role monitor phase={} failed", name);
    }
    result
}

/// Flush a sequence-bounded at-least-once digest without falsely alerting late inserts.
/// 清空序列快照约束的至少一次摘要，不误标延迟写入事件。
async fn flush_alerts(
    env: &Env,
    db: &worker::D1Database,
    expected: &[Role],
    destination: &str,
) -> Result<()> {
    let cutoff = now() - 1_000;
    // A sequence high-water mark freezes membership independently of handler
    // clock skew. A delayed insert may carry an old received_at but still has
    // a higher sequence and cannot be marked alerted by this digest.
    // 序列高水位冻结成员集合，不受处理器时钟偏差影响。延迟写入即便带旧
    // received_at，也会得到更高序列，绝不会被本次摘要误标为已通知。
    let snapshot = db
        .prepare("SELECT MAX(arrival_seq) AS max_seq FROM role_arrivals WHERE alerted_at IS NULL AND received_at<?1")
        .bind(&[JsValue::from_f64(cutoff as f64)])?
        .first::<AlertSnapshot>(None)
        .await?
        .ok_or_else(|| Error::RustError("role alert snapshot unavailable".into()))?;
    let max_seq = snapshot.max_seq.unwrap_or(0);
    let groups = db
        .prepare("SELECT role,forward_state,COUNT(*) AS count,MIN(received_at) AS oldest FROM role_arrivals WHERE alerted_at IS NULL AND received_at<?1 AND arrival_seq<=?2 GROUP BY role,forward_state")
        .bind(&[JsValue::from_f64(cutoff as f64), JsValue::from_f64(max_seq as f64)])?
        .all()
        .await?
        .results::<AlertGroup>()?;
    if !groups.is_empty() {
        let refs = db
            .prepare("SELECT id,role FROM role_arrivals WHERE alerted_at IS NULL AND received_at<?1 AND arrival_seq<=?2 ORDER BY received_at,id LIMIT 16")
            .bind(&[JsValue::from_f64(cutoff as f64), JsValue::from_f64(max_seq as f64)])?
            .all()
            .await?
            .results::<ArrivalRef>()?;
        let body = alert_body(&groups, &refs, expected, now())?;
        staging_fault(env, "before_alert")?;
        send_alert(env, &destination, &body).await?;
        staging_fault(env, "after_alert")?;
        db.prepare(
            "UPDATE role_arrivals SET alerted_at=?1 WHERE alerted_at IS NULL AND received_at<?2 AND arrival_seq<=?3",
        )
        .bind(&[
            JsValue::from_f64(now() as f64),
            JsValue::from_f64(cutoff as f64),
            JsValue::from_f64(max_seq as f64),
        ])?
        .run()
        .await?;
        console_log!("role alert digest accepted groups={}", groups.len());
    }
    Ok(())
}

/// Require no unresolved forwarding and a fresh outbox before renewing the lease.
/// 续租前要求无转发结果未知事件，且通知发件箱没有过期事件。
async fn check_and_renew(db: &worker::D1Database) -> Result<i64> {
    let state = db.prepare("SELECT COUNT(*) AS unknown, MIN(received_at) AS oldest FROM role_arrivals WHERE forward_state='unknown'")
        .first::<UnknownState>(None).await?
        .ok_or_else(|| Error::RustError("role state unavailable".into()))?;
    let pending = db.prepare("SELECT COUNT(*) AS pending, MIN(received_at) AS oldest FROM role_arrivals WHERE alerted_at IS NULL")
        .first::<PendingState>(None).await?
        .ok_or_else(|| Error::RustError("role outbox unavailable".into()))?;
    if state.unknown != 0
        || pending
            .oldest
            .is_some_and(|at| at < now() - MAX_UNALERTED_MS)
    {
        return Err(Error::RustError("role delivery or alert unresolved".into()));
    }
    // The DB no longer needs content-free, fully alerted accepted rows after 90 days.
    // 已转发且通知的无正文记录只保留 90 天。
    db.prepare("DELETE FROM role_arrivals WHERE forward_state='accepted' AND alerted_at IS NOT NULL AND received_at<?1")
        .bind(&[JsValue::from_f64((now() - RETENTION_MS) as f64)])?
        .run().await?;
    let checked_at = now();
    db.prepare("UPDATE role_monitor_health SET lease_until=?1,checked_at=?2 WHERE singleton=1")
        .bind(&[
            JsValue::from_f64((checked_at + LEASE_MS) as f64),
            JsValue::from_f64(checked_at as f64),
        ])?
        .run()
        .await?;
    // Readback avoids silently claiming a lease if an expected singleton row was absent.
    // 读回避免单例行丢失时错误声称已经续租。
    let lease = db
        .prepare("SELECT lease_until FROM role_monitor_health WHERE singleton=1")
        .first::<i64>(Some("lease_until"))
        .await?;
    if lease != Some(checked_at + LEASE_MS) {
        return Err(Error::RustError("role lease not renewed".into()));
    }
    Ok(pending.pending)
}

/// Grouped notice data contains no reporter-controlled content.
/// 分组通知数据不含举报者控制的内容。
#[derive(Deserialize)]
struct AlertGroup {
    role: String,
    forward_state: String,
    count: i64,
    oldest: i64,
}

/// One immutable upper bound for the current digest membership.
/// 当前摘要成员集合的不可变上界。
#[derive(Deserialize)]
struct AlertSnapshot {
    max_seq: Option<i64>,
}

/// A short random reference list helps locate originals without exposing content.
/// 简短随机引用列表帮助定位原信，同时不暴露内容。
#[derive(Deserialize)]
struct ArrivalRef {
    id: String,
    role: String,
}

/// Unknown forward outcomes cannot be dismissed by an accepted alert.
/// 即使通知已接受，也不能忽略转发结果未知的事件。
#[derive(Deserialize)]
struct UnknownState {
    unknown: i64,
    #[allow(dead_code)]
    oldest: Option<i64>,
}

/// Pending digest age bounds the monitoring lease. / 待发送摘要的年龄约束监控租约。
#[derive(Deserialize)]
struct PendingState {
    pending: i64,
    oldest: Option<i64>,
}

/// Render a compact safe digest from validated enum labels and aggregate counts.
/// 只用已验证的枚举标签与汇总计数构造安全、紧凑的摘要。
fn alert_body(
    groups: &[AlertGroup],
    refs: &[ArrivalRef],
    expected: &[Role],
    current_ms: i64,
) -> Result<String> {
    let mut body = String::from("Reserved-role mail arrived. Inspect the original in Inbox and Junk. Do not reply directly from this private mailbox; respond separately as mail@moesegfault.dev after review.\n\n");
    for group in groups {
        if !expected.iter().any(|role| role.label == group.role)
            || !matches!(group.forward_state.as_str(), "unknown" | "accepted")
            || group.count < 1
        {
            return Err(Error::RustError("role alert group invalid".into()));
        }
        let oldest_age_min = current_ms.saturating_sub(group.oldest).max(0) / 60_000;
        body.push_str(&format!(
            "{}: {} arrival(s), forward {}, oldest age {} min\n",
            group.role, group.count, group.forward_state, oldest_age_min
        ));
    }
    if !refs.is_empty() {
        body.push_str("\nFirst opaque references (search X-Amail-Role-Ref in the original):\n");
    }
    for reference in refs {
        if !expected.iter().any(|role| role.label == reference.role)
            || Uuid::parse_str(&reference.id).is_err()
        {
            return Err(Error::RustError("role alert reference invalid".into()));
        }
        body.push_str(&format!("{} {}\n", reference.role, reference.id));
    }
    if body.len() > 4_096 {
        return Err(Error::RustError("role alert too large".into()));
    }
    Ok(body)
}

/// Submit a content-free official-sender notice to the one secret destination.
/// 使用官方发件人向唯一机密目的地发送无正文通知。
async fn send_alert(env: &Env, destination: &str, body: &str) -> Result<()> {
    let builder = SendEmailBuilder::new_with_str_and_slice(
        OFFICIAL_FROM,
        &[destination.to_string()],
        "amail reserved-role mail notice",
    );
    builder.set_text(body);
    env.send_email("ROLE_ALERT")?
        .send_with_builder(&builder)
        .await?;
    Ok(())
}

/// A deliberately narrow destination syntax guard; provider verification is separate.
/// 此处仅狭义检查目的地语法；供应商验证是独立约束。
fn valid_destination(value: &str) -> bool {
    value.len() <= 254
        && value.bytes().filter(|byte| *byte == b'@').count() == 1
        && value.split_once('@').is_some_and(|(local, domain)| {
            !local.is_empty()
                && domain.contains('.')
                && !domain.starts_with('.')
                && !domain.ends_with('.')
                && value.is_ascii()
                && value
                    .bytes()
                    .all(|byte| byte.is_ascii_graphic() && byte != b'<' && byte != b'>')
        })
}

/// Synthetic failure hooks exist only in the isolated staging realm and never
/// read or synthesize reporter content. The production realm ignores them.
/// 合成故障钩子只在隔离的预发布环境生效，不读取或合成举报内容；生产环境忽略它们。
fn staging_fault(env: &Env, phase: &str) -> Result<()> {
    if env.var("ROLE_REALM")?.to_string() != "staging" {
        return Ok(());
    }
    let configured = env
        .secret("ROLE_TEST_FAULT")
        .map(|value| value.to_string())
        .unwrap_or_default();
    if configured == phase {
        return Err(Error::RustError("staging role fault injected".into()));
    }
    Ok(())
}

/// Provider response fields required for complete, duplicate-aware rule audits.
/// 完整、可识别重复规则的审计所需提供商响应字段。
#[derive(Deserialize)]
struct RulePage {
    success: bool,
    result: Vec<Rule>,
    result_info: PageInfo,
}
/// Provider-verified forwarding destinations are distinct from the route rules.
/// 提供商已验证的转发目的地与路由规则是不同的资源。
#[derive(Deserialize)]
struct AddressPage {
    success: bool,
    result: Vec<VerifiedAddress>,
    result_info: PageInfo,
}
#[derive(Deserialize)]
struct VerifiedAddress {
    email: String,
    verified: Option<String>,
}
#[derive(Deserialize)]
struct PageInfo {
    page: usize,
    per_page: usize,
    count: usize,
    total_count: usize,
    /// Email Routing may omit this field; total_count remains authoritative.
    total_pages: Option<usize>,
}

impl PageInfo {
    /// Derive the exhaustive page bound from the always-required total_count.
    fn pages(&self) -> usize {
        self.total_count.div_ceil(50).max(1)
    }
}
#[derive(Deserialize)]
struct Rule {
    enabled: bool,
    source: String,
    actions: Vec<Action>,
    matchers: Vec<Matcher>,
}
#[derive(Deserialize, PartialEq, Eq)]
struct Action {
    #[serde(rename = "type")]
    kind: String,
    value: Vec<String>,
}
#[derive(Deserialize, PartialEq, Eq)]
struct Matcher {
    #[serde(rename = "type")]
    kind: String,
    field: String,
    value: String,
}

/// Require one exact API-owned Worker rule per role, across every provider page.
/// 跨供应商所有分页，要求每个角色恰好一条精确 API 管理的 Worker 规则。
async fn audit_rules(env: &Env, expected: &[Role]) -> Result<()> {
    let zone = env.var("CF_ZONE_ID")?.to_string();
    if zone.len() != 32 || !zone.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err(Error::RustError("role zone invalid".into()));
    }
    let worker_name = match env.var("ROLE_REALM")?.to_string().as_str() {
        "production" => "amail-role-monitor",
        "staging" => "amail-role-monitor-staging",
        _ => return Err(Error::RustError("role realm invalid".into())),
    };
    let token = env.secret("CF_EMAIL_ROUTING_TOKEN")?.to_string();
    let mut found = vec![0usize; expected.len()];
    let mut expected_total = None;
    for page in 1..=100usize {
        let url = format!("{ZONE_RULES_URL}{zone}/email/routing/rules?per_page=50&page={page}");
        let mut response = provider_get(&url, &token).await?;
        if response.status_code() != 200 {
            return Err(Error::RustError("role rules unavailable".into()));
        }
        let data: RulePage = response.json().await?;
        let info = &data.result_info;
        if !valid_page(data.success, info, page, data.result.len(), expected_total) {
            return Err(Error::RustError("role rules pagination drift".into()));
        }
        expected_total = Some(info.total_count);
        for rule in data.result {
            for (index, role) in expected.iter().enumerate() {
                if rule.matchers.iter().any(|matcher| {
                    matcher.kind == "literal"
                        && matcher.field == "to"
                        && matcher.value.eq_ignore_ascii_case(role.address)
                }) {
                    found[index] += 1;
                    if !exact_worker_rule(&rule, role.address, worker_name) {
                        return Err(Error::RustError("role rule conflict".into()));
                    }
                }
            }
        }
        if page == info.pages() {
            break;
        }
    }
    if found.iter().any(|count| *count != 1) {
        return Err(Error::RustError("role rule missing or duplicate".into()));
    }
    Ok(())
}

/// A forwarding destination must still be explicitly verified by the provider.
/// 转发目的地必须持续处于供应商明确验证状态。
async fn audit_destination(env: &Env, destination: &str) -> Result<()> {
    let account = env.secret("CF_ACCOUNT_ID")?.to_string();
    if account.len() != 32 || !account.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err(Error::RustError("role account invalid".into()));
    }
    let token = env.secret("CF_EMAIL_ROUTING_TOKEN")?.to_string();
    let mut found = 0usize;
    let mut expected_total = None;
    for page in 1..=100usize {
        let url = format!("https://api.cloudflare.com/client/v4/accounts/{account}/email/routing/addresses?per_page=50&page={page}");
        let mut response = provider_get(&url, &token).await?;
        if response.status_code() != 200 {
            return Err(Error::RustError("role destinations unavailable".into()));
        }
        let data: AddressPage = response.json().await?;
        let info = &data.result_info;
        if !valid_page(data.success, info, page, data.result.len(), expected_total) {
            return Err(Error::RustError(
                "role destinations pagination drift".into(),
            ));
        }
        expected_total = Some(info.total_count);
        for address in data.result {
            if address.email.eq_ignore_ascii_case(destination) {
                found += 1;
                if address
                    .verified
                    .as_deref()
                    .filter(|v| !v.is_empty())
                    .is_none()
                {
                    return Err(Error::RustError("role destination unverified".into()));
                }
            }
        }
        if page == info.pages() {
            break;
        }
    }
    if found != 1 {
        return Err(Error::RustError(
            "role destination missing or duplicate".into(),
        ));
    }
    Ok(())
}

/// Bound every API inventory by reported pagination, not just a short last page.
/// 根据供应商报告的分页约束全部库存，不能仅依赖最后一页长度。
fn valid_page(
    success: bool,
    info: &PageInfo,
    page: usize,
    count: usize,
    prior: Option<usize>,
) -> bool {
    let pages = info.pages();
    success
        && info.page == page
        && info.per_page == 50
        && info.count == count
        && info
            .total_pages
            .is_none_or(|reported| reported == pages || (info.total_count == 0 && reported == 0))
        && pages <= 100
        && page <= pages
        && prior.is_none_or(|value| value == info.total_count)
        && count == (info.total_count.saturating_sub((page - 1) * 50)).min(50)
}

/// Issue an authenticated read without ever formatting token or response in logs.
/// 发出经认证的读取，绝不将令牌或响应格式化到日志。
async fn provider_get(url: &str, token: &str) -> Result<worker::Response> {
    let headers = Headers::new();
    headers.set("Authorization", &format!("Bearer {token}"))?;
    let mut init = RequestInit::new();
    init.with_method(Method::Get).with_headers(headers);
    Fetch::Request(Request::new_with_init(url, &init)?)
        .send()
        .await
}

/// Forbid extra matchers/actions that could silently redirect an address.
/// 禁止额外匹配器或操作，防止悄然重定向角色地址。
fn exact_worker_rule(rule: &Rule, address: &str, worker: &str) -> bool {
    rule.enabled
        && rule.source == "api"
        && rule.matchers
            == [Matcher {
                kind: "literal".into(),
                field: "to".into(),
                value: address.into(),
            }]
        && rule.actions
            == [Action {
                kind: "worker".into(),
                value: vec![worker.into()],
            }]
}

/// Cloudflare event time in Unix milliseconds. / Cloudflare 事件时间采用 Unix 毫秒。
fn now() -> i64 {
    Date::now() as i64
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Fixed roles prevent staging messages from entering production monitoring.
    /// 固定角色表防止预发布邮件流入生产监控。
    #[test]
    fn exact_realm_envelopes() {
        assert_eq!(roles("production").unwrap().len(), 4);
        assert_eq!(roles("staging").unwrap().len(), 1);
        assert!(roles("other").is_none());
        assert!(!roles("production")
            .unwrap()
            .iter()
            .any(|r| r.address == STAGING_ROLES[0].address));
    }

    /// Only a sole exact Worker action can keep the monitor lease healthy.
    /// 仅唯一的精确 Worker 操作才能保持监控租约健康。
    #[test]
    fn rule_audit_rejects_redirects() {
        let role = PRODUCTION_ROLES[0];
        let mut rule = Rule {
            enabled: true,
            source: "api".into(),
            matchers: vec![Matcher {
                kind: "literal".into(),
                field: "to".into(),
                value: role.address.into(),
            }],
            actions: vec![Action {
                kind: "worker".into(),
                value: vec!["amail-role-monitor".into()],
            }],
        };
        assert!(exact_worker_rule(&rule, role.address, "amail-role-monitor"));
        rule.actions.push(Action {
            kind: "forward".into(),
            value: vec!["elsewhere@example.test".into()],
        });
        assert!(!exact_worker_rule(
            &rule,
            role.address,
            "amail-role-monitor"
        ));
    }

    /// A database-injected role label cannot become alert text.
    /// 数据库中注入的角色标签不能变成通知正文。
    #[test]
    fn digest_accepts_only_enum_labels() {
        let mut group = AlertGroup {
            role: "apex_abuse".into(),
            forward_state: "accepted".into(),
            count: 2,
            oldest: 1,
        };
        let body = alert_body(&[group], &[], &PRODUCTION_ROLES, 1000).unwrap();
        assert!(body.contains("apex_abuse: 2"));
        group = AlertGroup {
            role: "unsafe\r\nBcc: attacker".into(),
            forward_state: "accepted".into(),
            count: 1,
            oldest: 1,
        };
        assert!(alert_body(&[group], &[], &PRODUCTION_ROLES, 1000).is_err());
    }

    /// Missing or drifting inventory pages must not renew the send lease.
    /// 缺页或漂移的库存页不得续租发信闸门。
    #[test]
    fn complete_pagination_is_required() {
        let info = PageInfo {
            page: 1,
            per_page: 50,
            count: 50,
            total_count: 51,
            total_pages: Some(2),
        };
        assert!(valid_page(true, &info, 1, 50, None));
        assert!(!valid_page(true, &info, 1, 49, None));
        assert!(!valid_page(true, &info, 1, 50, Some(52)));
        let omitted = PageInfo {
            total_pages: None,
            ..info
        };
        assert!(valid_page(true, &omitted, 1, 50, None));
        let bad = PageInfo {
            total_pages: Some(3),
            ..omitted
        };
        assert!(!valid_page(true, &bad, 1, 50, None));
    }

    /// Reject malformed or header-injectable private destinations before use.
    /// 使用前拒绝畸形或可注入邮件头的机密目的地。
    #[test]
    fn destination_is_plain_ascii_mailbox() {
        assert!(valid_destination("owner@example.test"));
        assert!(!valid_destination("owner@example.test\r\nBcc: attacker"));
        assert!(!valid_destination("owner@example.test\0"));
        assert!(!valid_destination("owner"));
    }
}
