//! amail agent-facing CLI / amail 面向 Agent 的命令行。

mod api;
mod archive;
mod auth;
mod config;
mod telemetry;

use anyhow::{bail, ensure, Context, Result};
use clap::{Args, Parser, Subcommand};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs::OpenOptions,
    io::{IsTerminal, Write},
    path::PathBuf,
    time::{Duration, Instant},
};

/// Privacy disclosure for exploratory help, never compact command output.
const SEMANTIC_PRIVACY_NOTICE: &str = concat!(
    "Privacy: Active received and sent mail subjects plus bounded body-text excerpts ",
    "(combined first 12,000 UTF-8 bytes) are sent to OpenRouter and its model provider ",
    "for background semantic indexing, even if --semantic is never used. ",
    "--semantic also sends the search query. AMAIL_TELEMETRY=off does not disable indexing."
);

/// Compact JSONL by default; `--human` opts into readable formatting.
/// 默认输出紧凑 JSONL；`--human` 才启用可读排版。
#[derive(Parser)]
#[command(name = "amail", version, about = "Agent-first mail for moeSegFault", long_about = None, after_help = SEMANTIC_PRIVACY_NOTICE)]
struct Cli {
    /// Human-readable output, with terminal color when supported.
    #[arg(long, global = true)]
    human: bool,
    #[command(subcommand)]
    command: Command,
}

/// All mail mutations are explicit; fetching never marks mail read.
/// 所有邮件状态变更均为显式操作；读取不会自动标记已读。
#[derive(Subcommand)]
enum Command {
    /// Authenticate through the system browser.
    Auth {
        #[command(subcommand)]
        command: AuthCommand,
    },
    /// Short alias for `auth login`.
    #[command(after_help = SEMANTIC_PRIVACY_NOTICE)]
    Login {
        #[arg(long)]
        no_browser: bool,
    },
    /// Short alias for `auth logout`.
    Logout,
    /// Manage addresses under mail.moesegfault.dev.
    Address {
        #[command(subcommand)]
        command: AddressCommand,
    },
    /// Pull recent message summaries; optionally export their ZIP archives.
    Sync {
        #[arg(long, default_value_t = 20)]
        limit: u32,
        #[arg(long)]
        cursor: Option<String>,
        #[arg(long)]
        all: bool,
        #[arg(long)]
        out_dir: Option<PathBuf>,
    },
    /// Search message metadata, text, or semantic meaning with AND predicates.
    #[command(after_help = SEMANTIC_PRIVACY_NOTICE)]
    Search(SearchArgs),
    /// Fetch metadata only, without changing read state.
    Get { id: String },
    /// Download one ZIP archive, optionally extracting into a new directory.
    Read {
        id: String,
        #[arg(short, long)]
        out: PathBuf,
        #[arg(long)]
        unpack: bool,
    },
    /// Explicitly mark a message read or unread.
    Mark {
        id: String,
        #[arg(long, conflicts_with = "unread")]
        read: bool,
        #[arg(long)]
        unread: bool,
    },
    /// Delete the caller's copy of a message.
    Delete { id: String },
    /// Native ZIP packaging of a draft directory.
    Pack {
        directory: PathBuf,
        #[arg(short, long)]
        out: PathBuf,
    },
    /// Native safe extraction of a received ZIP.
    Unpack {
        archive: PathBuf,
        #[arg(short, long)]
        out: PathBuf,
    },
    /// Validate and submit a ZIP; unresolved retries reuse the idempotency key.
    Send {
        archive: PathBuf,
        /// Stable UUID to reuse when retrying an uncertain send.
        #[arg(long)]
        idempotency_key: Option<String>,
    },
    /// Show non-secret configuration paths and values.
    Config,
    /// Detached internal telemetry worker / 独立遥测上传进程。
    #[command(name = "_telemetry-flush", hide = true)]
    TelemetryFlush,
}

/// Native OIDC session commands / 原生 OIDC 会话命令。
#[derive(Subcommand)]
enum AuthCommand {
    /// Open system browser for authorization (or print URL for manual browser use).
    #[command(after_help = SEMANTIC_PRIVACY_NOTICE)]
    Login {
        #[arg(long)]
        no_browser: bool,
    },
    /// Show only non-secret session state.
    Status,
    /// Revoke refresh token best-effort and always remove local credentials.
    Logout,
}

/// Address lifecycle commands / 地址生命周期命令。
#[derive(Subcommand)]
enum AddressCommand {
    /// List owned addresses and provisioning state.
    List,
    /// Register an available local part (maximum ten per account).
    Add { local_part: String },
    /// Retire one full address.
    Delete { address: String },
}

/// Search predicates, all combined by AND on the server.
/// 检索谓词由服务端按 AND 组合。
#[derive(Args)]
struct SearchArgs {
    /// Resume an accepted server search job without resubmitting private filters.
    /// 续作已接受的任务，不重新提交私密检索条件。
    #[arg(long)]
    resume: Option<String>,
    /// Maximum time to wait before returning a resumable job ID.
    /// 本次调用等待的最长秒数，超时后可凭任务 ID 续作。
    #[arg(long, default_value_t = 900)]
    wait_seconds: u64,
    #[arg(long)]
    mailbox: Option<String>,
    #[arg(long)]
    after: Option<String>,
    #[arg(long)]
    before: Option<String>,
    #[arg(long)]
    title: Option<String>,
    #[arg(long = "from")]
    sender: Option<String>,
    #[arg(long)]
    to: Option<String>,
    #[arg(long)]
    body: Option<String>,
    /// KEY=VALUE filter (message_id, in_reply_to, content_type, attachment_name); distinct keys may repeat this flag.
    #[arg(long = "meta")]
    metadata: Vec<String>,
    /// Send this query to OpenRouter for semantic search; background mail indexing happens even without this option.
    #[arg(long)]
    semantic: Option<String>,
    #[arg(long)]
    regex: bool,
    #[arg(long)]
    case_sensitive: bool,
    #[arg(long, conflicts_with = "unread")]
    read: bool,
    #[arg(long)]
    unread: bool,
    #[arg(long, default_value_t = 20)]
    limit: u32,
    #[arg(long)]
    cursor: Option<String>,
}

fn emit(value: &Value, human: bool) -> Result<()> {
    if human {
        if value.get("id").is_some() && value.get("subject").is_some() {
            println!("{}", human_detail(value));
        } else {
            println!("{}", serde_json::to_string_pretty(value)?);
        }
    } else {
        println!("{}", serde_json::to_string(value)?);
    }
    Ok(())
}

/// Escape untrusted control characters before terminal presentation.
/// 在终端展示前转义不可信控制字符，避免邮件内容注入终端指令。
fn safe_human(value: &str) -> String {
    let mut escaped = String::new();
    for ch in value.chars() {
        if ch.is_control() {
            escaped.push_str(&format!("\\u{:04x}", ch as u32));
        } else {
            escaped.push(ch);
        }
    }
    escaped
}

/// Render familiar metadata first, then every remaining server field without omission.
/// 先展示常用元数据，再完整保留服务端返回的其余字段。
fn human_detail(value: &Value) -> String {
    let ordered = [
        ("ID", "id"),
        ("Mailbox", "mailbox"),
        ("From", "from"),
        ("To", "to"),
        ("Subject", "subject"),
        ("Received", "received_at"),
        ("Read", "read"),
        ("Size", "size_bytes"),
        ("Attachments", "has_attachments"),
    ];
    let mut lines = Vec::new();
    let mut push = |label: &str, field: &Value| {
        let text = field
            .as_str()
            .map(safe_human)
            .unwrap_or_else(|| field.to_string());
        lines.push(format!("{label:<16} {text}"));
    };
    for &(label, key) in &ordered {
        if let Some(field) = value.get(key) {
            push(label, field);
        }
    }
    if let Some(fields) = value.as_object() {
        for (key, field) in fields {
            if !ordered.iter().any(|(_, known)| key.as_str() == *known) {
                push(key, field);
            }
        }
    }
    lines.join("\n")
}

fn emit_items(value: &Value, human: bool, keys: &[&str]) -> Result<()> {
    if human {
        if let Some(addresses) = value.get("addresses").and_then(Value::as_array) {
            let heading = format!("{:<40} {:<10} {}", "ADDRESS", "STATE", "CREATED");
            human_heading(&heading);
            for row in addresses {
                println!(
                    "{:<40} {:<10} {}",
                    safe_human(field(row, "address")),
                    safe_human(field(row, "state")),
                    safe_human(field(row, "created_at"))
                );
            }
            println!("{} address(es)", addresses.len());
            return Ok(());
        }
        if let Some(messages) = value
            .get("messages")
            .or_else(|| value.get("items"))
            .and_then(Value::as_array)
        {
            let heading = format!(
                "{:<36} {:<20} {:<6} {:<28} {}",
                "ID", "RECEIVED", "READ", "FROM", "SUBJECT"
            );
            human_heading(&heading);
            for row in messages {
                let read = match row.get("read").and_then(Value::as_bool) {
                    Some(true) => "yes",
                    Some(false) => "no",
                    None => "—",
                };
                println!(
                    "{:<36} {:<20} {:<6} {:<28} {}",
                    clipped(&safe_human(field(row, "id")), 36),
                    clipped(&safe_human(field(row, "received_at")), 20),
                    read,
                    clipped(&safe_human(field(row, "from")), 28),
                    safe_human(field(row, "subject"))
                );
            }
            if let Some(cursor) = value.get("next_cursor").and_then(Value::as_str) {
                println!("Next cursor: {}", safe_human(cursor));
            }
            println!("{} message(s)", messages.len());
            return Ok(());
        }
        return emit(value, true);
    }
    if let Some(items) = keys
        .iter()
        .find_map(|key| value.get(*key).and_then(Value::as_array))
    {
        for item in items {
            emit(item, false)?;
        }
        if let Some(cursor) = value.get("next_cursor").filter(|c| !c.is_null()) {
            emit(&json!({"next_cursor":cursor}), false)?;
        }
    } else {
        emit(value, false)?;
    }
    Ok(())
}

fn field<'a>(value: &'a Value, key: &str) -> &'a str {
    value.get(key).and_then(Value::as_str).unwrap_or("—")
}

fn clipped(value: &str, max: usize) -> String {
    let mut chars = value.chars();
    let clipped: String = chars.by_ref().take(max).collect();
    if chars.next().is_some() {
        format!(
            "{}…",
            clipped
                .chars()
                .take(max.saturating_sub(1))
                .collect::<String>()
        )
    } else {
        clipped
    }
}

fn human_heading(value: &str) {
    if std::io::stdout().is_terminal() && std::env::var_os("NO_COLOR").is_none() {
        println!("\x1b[1;36m{value}\x1b[0m");
    } else {
        println!("{value}");
    }
}

fn metadata(args: &SearchArgs) -> Result<BTreeMap<String, String>> {
    let mut map = BTreeMap::new();
    for item in &args.metadata {
        let (key, value) = item.split_once('=').context("--meta requires KEY=VALUE")?;
        ensure!(!key.is_empty(), "metadata key cannot be empty");
        // The API represents metadata as a map, so another value for this key
        // cannot express conjunction and must never silently replace a filter.
        // Never echo caller-supplied metadata into stderr or Agent logs.
        ensure!(!map.contains_key(key), "duplicate --meta key");
        map.insert(key.to_owned(), value.to_owned());
    }
    Ok(map)
}

fn write_new(path: &PathBuf, data: &[u8]) -> Result<()> {
    ensure!(!path.exists(), "refusing to overwrite {}", path.display());
    let temp = path.with_extension(format!("amail-{}.tmp", uuid::Uuid::new_v4()));
    let result = (|| -> Result<()> {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temp)?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            file.set_permissions(std::fs::Permissions::from_mode(0o600))?;
        }
        file.write_all(data)?;
        file.sync_all()?;
        ensure!(!path.exists(), "refusing to overwrite {}", path.display());
        std::fs::rename(&temp, path)?;
        #[cfg(unix)]
        {
            let parent = path
                .parent()
                .filter(|p| !p.as_os_str().is_empty())
                .unwrap_or_else(|| std::path::Path::new("."));
            std::fs::File::open(parent)?.sync_all()?;
        }
        Ok(())
    })();
    if result.is_err() {
        let _ = std::fs::remove_file(&temp);
    }
    result
}

fn summary_id(item: &Value) -> Result<&str> {
    let id = item
        .get("id")
        .and_then(Value::as_str)
        .context("message missing id")?;
    ensure!(
        id.chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_'),
        "unsafe message id"
    );
    Ok(id)
}

fn sync(
    api: &api::Api<'_>,
    limit: u32,
    mut cursor: Option<String>,
    all: bool,
    out_dir: Option<PathBuf>,
    human: bool,
) -> Result<()> {
    ensure!((1..=100).contains(&limit), "limit must be 1..100");
    if let Some(dir) = &out_dir {
        std::fs::create_dir_all(dir)?;
    }
    loop {
        let value = api.messages(limit, cursor.as_deref())?;
        if let Some(dir) = &out_dir {
            if let Some(items) = value
                .get("messages")
                .or_else(|| value.get("items"))
                .and_then(Value::as_array)
            {
                for item in items {
                    let id = summary_id(item)?;
                    let path = dir.join(format!("{id}.zip"));
                    let bytes = api.archive(id)?;
                    if path.exists() {
                        ensure!(
                            std::fs::read(&path)?.as_slice() == bytes.as_slice(),
                            "existing archive differs: {}",
                            path.display()
                        );
                    } else {
                        write_new(&path, &bytes)?;
                    }
                }
            }
        }
        emit_items(&value, human, &["messages", "items"])?;
        let next_cursor = value
            .get("next_cursor")
            .and_then(Value::as_str)
            .map(str::to_owned);
        ensure!(
            next_cursor.is_none() || next_cursor != cursor,
            "mail API repeated a pagination cursor"
        );
        cursor = next_cursor;
        if !all || cursor.is_none() {
            break;
        }
    }
    Ok(())
}

fn search_request(args: &SearchArgs) -> Result<Value> {
    ensure!((1..=100).contains(&args.limit), "limit must be 1..100");
    let mut value =
        json!({"limit":args.limit,"regex":args.regex,"case_sensitive":args.case_sensitive});
    for (key, field) in [
        ("mailbox", &args.mailbox),
        ("after", &args.after),
        ("before", &args.before),
        ("title", &args.title),
        ("from", &args.sender),
        ("to", &args.to),
        ("body", &args.body),
        ("semantic", &args.semantic),
        ("cursor", &args.cursor),
    ] {
        if let Some(text) = field {
            value[key] = json!(text);
        }
    }
    let meta = metadata(args)?;
    if !meta.is_empty() {
        value["metadata"] = json!(meta);
    }
    if args.read {
        value["read"] = json!(true);
    }
    if args.unread {
        value["read"] = json!(false);
    }
    Ok(value)
}

/// Hide intermediate 202 responses from stdout and return only complete results.
/// 不将中间 202 响应写入标准输出，只返回完整结果。
fn run_search(api: &api::Api<'_>, args: &SearchArgs, human: bool) -> Result<()> {
    ensure!(
        (1..=86_400).contains(&args.wait_seconds),
        "wait-seconds must be 1..86400"
    );
    let started = Instant::now();
    let deadline = Duration::from_secs(args.wait_seconds);
    let mut reply = if let Some(id) = &args.resume {
        let has_filters = [
            &args.mailbox,
            &args.after,
            &args.before,
            &args.title,
            &args.sender,
            &args.to,
            &args.body,
            &args.semantic,
            &args.cursor,
        ]
        .iter()
        .any(|value| value.is_some())
            || !args.metadata.is_empty()
            || args.regex
            || args.case_sensitive
            || args.read
            || args.unread
            || args.limit != 20;
        ensure!(
            !has_filters,
            "--resume cannot be combined with search filters"
        );
        api.poll_search_job(id)?
    } else {
        api.search(&search_request(args)?)?
    };
    let mut active_id: Option<String> = None;
    loop {
        match reply {
            api::SearchReply::Complete(results) => {
                return emit_items(&results, human, &["messages", "items"]);
            }
            api::SearchReply::Running {
                job_id,
                retry_after,
            } => {
                if let Some(existing) = &active_id {
                    ensure!(existing == &job_id, "search job id changed during polling");
                } else {
                    eprintln!("amail: search job {job_id} running; polling (resume with `amail search --resume {job_id}`)");
                    active_id = Some(job_id.clone());
                }
                if started.elapsed() >= deadline {
                    bail!("search job {job_id} still running; resume with `amail search --resume {job_id}`");
                }
                std::thread::sleep(retry_after.min(deadline.saturating_sub(started.elapsed())));
                reply = api
                    .poll_search_job(&job_id)
                    .map_err(|err| anyhow::anyhow!("search job {job_id}: {err}"))?;
            }
        }
    }
}

fn run() -> Result<()> {
    let cli = Cli::parse();
    let cfg = config::Runtime::load()?;
    telemetry::init(&cfg)?;
    match cli.command {
        Command::Config => emit(
            &json!({"api_base":cfg.api_base,"issuer":cfg.issuer,"client_id":cfg.client_id,
            "redirect_uri":cfg.redirect_uri,"home":cfg.home,"telemetry_enabled":std::env::var("AMAIL_TELEMETRY").ok().as_deref()!=Some("off")}),
            cli.human,
        )?,
        Command::TelemetryFlush => {
            telemetry::flush_pending(&cfg)?;
        }
        Command::Auth { command } => match command {
            AuthCommand::Login { no_browser } => {
                auth::login(&cfg, no_browser)?;
                emit(&json!({"authenticated":true}), cli.human)?;
            }
            AuthCommand::Status => {
                let tokens = auth::status(&cfg)?;
                emit(
                    &json!({"authenticated":tokens.is_some(), "expires_at":tokens.map(|t| t.expires_at)}),
                    cli.human,
                )?;
            }
            AuthCommand::Logout => {
                auth::logout(&cfg)?;
                emit(&json!({"authenticated":false}), cli.human)?;
            }
        },
        Command::Login { no_browser } => {
            auth::login(&cfg, no_browser)?;
            emit(&json!({"authenticated":true}), cli.human)?;
        }
        Command::Logout => {
            auth::logout(&cfg)?;
            emit(&json!({"authenticated":false}), cli.human)?;
        }
        Command::Pack { directory, out } => {
            archive::pack(&directory, &out)?;
            emit(&json!({"packed":true,"path":out}), cli.human)?;
        }
        Command::Unpack { archive: path, out } => {
            archive::unpack(&std::fs::read(path)?, &out)?;
            emit(&json!({"unpacked":true,"path":out}), cli.human)?;
        }
        Command::Send {
            archive: path,
            idempotency_key,
        } => {
            let bytes = archive::outbound_bytes(&path)?;
            let digest = Sha256::digest(&bytes);
            let hash: String = digest.iter().map(|b| format!("{b:02x}")).collect();
            let key = if let Some(key) = idempotency_key {
                ensure!(
                    uuid::Uuid::parse_str(&key).is_ok(),
                    "idempotency key must be a UUID"
                );
                key
            } else {
                let random = uuid::Uuid::new_v4().to_string();
                telemetry::send_key(&cfg, &hash, &random)?
            };
            let result = api::Api::new(&cfg)?.send(&bytes, &key)?;
            telemetry::accepted(&cfg, &hash)?;
            emit(&result, cli.human)?;
        }
        command => {
            let api = api::Api::new(&cfg)?;
            match command {
                Command::Address { command } => match command {
                    AddressCommand::List => {
                        emit_items(&api.addresses()?, cli.human, &["addresses", "items"])?
                    }
                    AddressCommand::Add { local_part } => {
                        emit(&api.add_address(&local_part)?, cli.human)?
                    }
                    AddressCommand::Delete { address } => {
                        emit(&api.delete_address(&address)?, cli.human)?
                    }
                },
                Command::Sync {
                    limit,
                    cursor,
                    all,
                    out_dir,
                } => sync(&api, limit, cursor, all, out_dir, cli.human)?,
                Command::Search(args) => run_search(&api, &args, cli.human)?,
                Command::Get { id } => emit(&api.message(&id)?, cli.human)?,
                Command::Read { id, out, unpack } => {
                    let bytes = api.archive(&id)?;
                    if unpack {
                        archive::unpack(&bytes, &out)?;
                    } else {
                        write_new(&out, &bytes)?;
                    }
                    emit(&json!({"id":id,"path":out,"unpacked":unpack}), cli.human)?;
                }
                Command::Mark { id, read, unread } => {
                    ensure!(read || unread, "choose --read or --unread");
                    emit(&api.mark(&id, read)?, cli.human)?;
                }
                Command::Delete { id } => emit(&api.delete(&id)?, cli.human)?,
                _ => bail!("unreachable command"),
            }
        }
    }
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        // Debug chains can contain HTTP URLs or provider payloads; print only the top-level error.
        // 调试错误链可能包含 URL 或提供者载荷，因此只打印顶层错误。
        eprintln!("amail: {error}");
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Keep the third-party processing disclosure visible at first-use discovery points.
    #[test]
    fn help_discloses_automatic_semantic_indexing() {
        for args in [
            vec!["amail", "--help"],
            vec!["amail", "login", "--help"],
            vec!["amail", "auth", "login", "--help"],
            vec!["amail", "search", "--help"],
        ] {
            let help = Cli::try_parse_from(args.clone()).unwrap_err();
            assert_eq!(help.kind(), clap::error::ErrorKind::DisplayHelp);
            let output = help
                .to_string()
                .split_whitespace()
                .collect::<Vec<_>>()
                .join(" ");
            for phrase in [
                "background semantic indexing",
                "even if --semantic is never used",
                "--semantic also sends the search query",
                "AMAIL_TELEMETRY=off does not disable indexing",
            ] {
                assert!(output.contains(phrase), "missing {phrase} from {args:?}");
            }
        }
    }

    #[test]
    fn search_keeps_composed_predicates() {
        let args = SearchArgs {
            resume: None,
            wait_seconds: 900,
            mailbox: None,
            after: Some("2026-01-01T00:00:00Z".into()),
            before: None,
            title: Some("release".into()),
            sender: None,
            to: None,
            body: None,
            metadata: vec!["message_id=abc".into()],
            semantic: Some("rollout risk".into()),
            regex: true,
            case_sensitive: true,
            read: false,
            unread: true,
            limit: 7,
            cursor: None,
        };
        let query = search_request(&args).unwrap();
        assert_eq!(query["title"], "release");
        assert_eq!(query["metadata"]["message_id"], "abc");
        assert_eq!(query["semantic"], "rollout risk");
        assert_eq!(query["read"], false);
        assert_eq!(query["regex"], true);
        assert_eq!(query["limit"], 7);
    }

    #[test]
    fn search_rejects_repeated_metadata_key_before_request() {
        let cli = Cli::try_parse_from([
            "amail",
            "search",
            "--meta",
            "attachment_name=report.pdf",
            "--meta",
            "attachment_name=chart.png",
        ])
        .unwrap();
        let Command::Search(args) = cli.command else {
            panic!("expected search command");
        };
        let error = search_request(&args).unwrap_err().to_string();
        assert_eq!(error, "duplicate --meta key");
    }

    #[test]
    fn duplicate_metadata_error_does_not_echo_key() {
        let cli = Cli::try_parse_from([
            "amail",
            "search",
            "--meta",
            "private-address@example.org=x",
            "--meta",
            "private-address@example.org=y",
        ])
        .unwrap();
        let Command::Search(args) = cli.command else {
            panic!("expected search command");
        };
        assert_eq!(
            search_request(&args).unwrap_err().to_string(),
            "duplicate --meta key"
        );
    }

    #[test]
    fn search_preserves_distinct_metadata_keys() {
        let cli = Cli::try_parse_from([
            "amail",
            "search",
            "--meta",
            "message_id=x",
            "--meta",
            "content_type=text/plain",
        ])
        .unwrap();
        let Command::Search(args) = cli.command else {
            panic!("expected search command");
        };
        let query = search_request(&args).unwrap();
        assert_eq!(query["metadata"]["message_id"], "x");
        assert_eq!(query["metadata"]["content_type"], "text/plain");
        assert_eq!(query["metadata"].as_object().unwrap().len(), 2);
    }

    #[test]
    fn archive_write_never_overwrites() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("mail.zip");
        write_new(&path, b"first").unwrap();
        assert!(write_new(&path, b"second").is_err());
        assert_eq!(std::fs::read(path).unwrap(), b"first");
    }

    #[test]
    fn human_detail_preserves_extended_metadata_without_terminal_controls() {
        let value = json!({
            "id":"m1", "subject":"hello\u{001b}[31m", "direction":"inbound",
            "has_html":true, "request_id":"r1", "metadata":{"message_id":"x"},
            "attachments":[{"filename":"report.pdf"}],
        });
        let output = human_detail(&value);
        for name in [
            "direction",
            "has_html",
            "request_id",
            "metadata",
            "attachments",
            "report.pdf",
        ] {
            assert!(output.contains(name), "missing {name}");
        }
        assert!(!output.contains('\u{001b}'));
        assert!(output.contains("\\u001b"));
    }

    #[test]
    fn resumable_search_flags_parse_without_filters() {
        let id = "123e4567-e89b-42d3-a456-426614174000";
        let cli = Cli::try_parse_from(["amail", "search", "--resume", id, "--wait-seconds", "30"])
            .unwrap();
        match cli.command {
            Command::Search(args) => {
                assert_eq!(args.resume.as_deref(), Some(id));
                assert_eq!(args.wait_seconds, 30);
                assert!(args.semantic.is_none());
            }
            _ => panic!("expected search command"),
        }
    }
}
