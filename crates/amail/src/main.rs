//! amail agent-facing CLI / amail 面向 Agent 的命令行。

macro_rules! println {
    ($($arg:tt)*) => { crate::output::out(format_args!($($arg)*)) };
}
macro_rules! eprintln {
    ($($arg:tt)*) => { crate::output::err(format_args!($($arg)*)) };
}

mod api;
mod approval;
mod archive;
mod auth;
mod billing;
mod command_journal;
mod config;
mod daemon;
mod discovery;
mod export;
mod local_store;
mod machine;
mod output;
#[cfg(test)]
mod performance;
mod profiles;
mod send_state;
mod session;
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
    "--semantic also sends the search query. A multi-page semantic search keeps its query ",
    "text and exact query vector in owner-scoped server state for up to 24 hours; ",
    "later pages reuse that vector without another provider call. ",
    "AMAIL_TELEMETRY=off does not disable indexing or this server retention."
);

/// Compact JSONL by default; `--human` opts into readable formatting.
/// 默认输出紧凑 JSONL；`--human` 才启用可读排版。
#[derive(Parser)]
#[command(name = "amail", version, about = "Agent-first mail for moeSegFault", long_about = None, after_help = SEMANTIC_PRIVACY_NOTICE)]
struct Cli {
    /// Human-readable output, with terminal color when supported.
    #[arg(long, global = true)]
    human: bool,
    /// Versioned structured stderr; stdout keeps the established JSONL contract.
    #[arg(long, global = true, conflicts_with = "human")]
    machine: bool,
    #[command(subcommand)]
    command: Command,
}

/// All mail mutations are explicit; fetching never marks mail read.
/// 所有邮件状态变更均为显式操作；读取不会自动标记已读。
#[derive(Subcommand)]
enum Command {
    /// Manage terminal-exclusive profiles without passwords.
    Profile {
        #[command(subcommand)]
        command: ProfileCommand,
    },
    /// Manage the local background service.
    Daemon {
        #[command(subcommand)]
        command: DaemonCommand,
    },
    /// Acquire non-preemptible cloud mailbox ownership or export live history.
    Mailbox {
        #[command(subcommand)]
        command: MailboxCommand,
    },
    #[command(name = "_daemon", hide = true)]
    DaemonServe,
    /// Explore a concise offline capability index or one child topic.
    Discover { topic: Option<String> },
    /// Query an owner-scoped logical send intent, without resubmitting mail.
    SendStatus {
        id: String,
        /// Read an accepted local receipt only; this is not current delivery state.
        #[arg(long)]
        local: bool,
    },
    /// List recent accepted local intent receipts for lost-output recovery.
    SendReceipts {
        #[arg(long, default_value_t = 20)]
        limit: u32,
    },
    /// Query current owner-visible sending policy and quotas.
    SendingStatus,
    /// Inspect resources or request human browser authorization for subscriptions.
    Billing {
        #[command(subcommand)]
        command: billing::Command,
    },
    /// Query provider feedback for one owned outbound message.
    Outcomes { id: String },
    /// Explore owner-visible lifecycle event pages only when needed.
    Events {
        #[arg(long)]
        message: Option<String>,
        #[arg(long)]
        kind: Option<String>,
        #[arg(long)]
        since: Option<String>,
        #[arg(long, default_value_t = 20)]
        limit: u32,
        #[arg(long)]
        cursor: Option<String>,
    },
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
        #[arg(long, visible_alias = "intent")]
        idempotency_key: Option<String>,
    },
    /// Show non-secret configuration paths and values.
    Config,
    /// Detached internal telemetry worker / 独立遥测上传进程。
    #[command(name = "_telemetry-flush", hide = true)]
    TelemetryFlush {
        /// Carry only the generated diagnostic scheduling identity to the child.
        #[arg(long, hide = true)]
        attempt_id: Option<uuid::Uuid>,
    },
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
    Add {
        local_part: String,
        /// Allocate a temporary mailbox with at most six hours of retention.
        #[arg(long)]
        tmp: bool,
    },
    /// Retire one full address.
    Delete { address: String },
}

#[derive(Subcommand)]
enum ProfileCommand {
    List,
    Status,
    Create { name: String },
    Activate { name: String },
    Deactivate,
    Release { name: Option<String> },
}

#[derive(Subcommand)]
enum DaemonCommand {
    Status,
    Stop,
}

#[derive(Subcommand)]
enum MailboxCommand {
    Acquire {
        address: String,
        #[arg(long, default_value = "read", value_parser = ["read", "write"])]
        mode: String,
    },
    Release {
        address: String,
    },
    /// Download all currently retained messages before a temporary mailbox expires.
    Export {
        address: String,
        #[arg(long, short = 'o', visible_alias = "output")]
        out: PathBuf,
    },
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
    /// KEY=VALUE filter; discover search lists metadata keys. Distinct keys may repeat this flag.
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
        let (key, value) = item
            .split_once('=')
            .ok_or_else(|| machine::invalid_input("--meta requires KEY=VALUE"))?;
        if key.is_empty() {
            return Err(machine::invalid_input("metadata key cannot be empty"));
        }
        // The API represents metadata as a map, so another value for this key
        // cannot express conjunction and must never silently replace a filter.
        // Never echo caller-supplied metadata into stderr or Agent logs.
        if map.contains_key(key) {
            return Err(machine::invalid_input("duplicate --meta key"));
        }
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
                    if machine::enabled() {
                        machine::event(
                            "search_running",
                            json!({"job_id":job_id,"next_action":"resume_search"}),
                        );
                    } else {
                        eprintln!("amail: search job {job_id} running; polling (resume with `amail search --resume {job_id}`)");
                    }
                    active_id = Some(job_id.clone());
                }
                if started.elapsed() >= deadline {
                    return Err(machine::Failure {
                        code: "search_running", next_action: "resume_search",
                        data: json!({"job_id":job_id}),
                        message: format!("search job {job_id} still running; resume with `amail search --resume {job_id}`"),
                    }.into());
                }
                std::thread::sleep(retry_after.min(deadline.saturating_sub(started.elapsed())));
                reply = api
                    .poll_search_job(&job_id)
                    .with_context(|| format!("search job {job_id}"))?;
            }
        }
    }
}

fn run() -> Result<()> {
    let cli = match Cli::try_parse() {
        Ok(cli) => cli,
        Err(error)
            if matches!(
                error.kind(),
                clap::error::ErrorKind::DisplayHelp | clap::error::ErrorKind::DisplayVersion
            ) =>
        {
            error.exit()
        }
        Err(error) if machine::enabled() => {
            return Err(machine::Failure {
                code: "invalid_arguments",
                next_action: "fix_input",
                data: json!({}),
                message: error.to_string(),
            }
            .into())
        }
        Err(error) => error.exit(),
    };
    if let Command::Discover { topic } = &cli.command {
        return emit(&discovery::topic(topic.as_deref())?, cli.human);
    }
    let cfg = config::Runtime::load()?;
    match cli.command {
        Command::DaemonServe => daemon::serve(&cfg),
        Command::Daemon {
            command: DaemonCommand::Status,
        } => emit(&daemon::status(&cfg)?, cli.human),
        Command::Daemon {
            command: DaemonCommand::Stop,
        } => {
            daemon::stop(&cfg)?;
            emit(&json!({"stopped":true}), cli.human)
        }
        Command::TelemetryFlush { attempt_id } => {
            telemetry::flush_pending(&cfg, attempt_id.as_ref())
        }
        _ => {
            let code = daemon::forward(&cfg, std::env::args_os().collect())?;
            if code != 0 {
                std::process::exit(code);
            }
            Ok(())
        }
    }
}

pub(crate) fn daemon_tick(cfg: &config::Runtime) -> Result<()> {
    profiles::Store::open(cfg)?.sweep_all()?;
    Ok(())
}

fn absolute_paths(cli: &mut Cli, cwd: &std::path::Path) {
    let resolve = |path: &mut PathBuf| {
        if path.is_relative() {
            *path = cwd.join(&*path);
        }
    };
    match &mut cli.command {
        Command::Read { out, .. } => resolve(out),
        Command::Pack { directory, out } => {
            resolve(directory);
            resolve(out);
        }
        Command::Unpack { archive, out } => {
            resolve(archive);
            resolve(out);
        }
        Command::Send { archive, .. } => resolve(archive),
        Command::Sync {
            out_dir: Some(path),
            ..
        } => resolve(path),
        Command::Mailbox {
            command: MailboxCommand::Export { out, .. },
        } => resolve(out),
        _ => {}
    }
}

fn approval_summary(command: &Command) -> String {
    match command {
        Command::Profile { command } => match command {
            ProfileCommand::Create { name } => format!("Create profile: {name}"),
            ProfileCommand::Activate { name } => format!("Activate profile: {name}"),
            ProfileCommand::Release { name } => {
                format!("Release profile: {}", name.as_deref().unwrap_or("current"))
            }
            ProfileCommand::Deactivate => {
                "Deactivate this terminal; retain the profile reservation".into()
            }
            ProfileCommand::List => "List profiles".into(),
            ProfileCommand::Status => "Show this terminal's profile".into(),
        },
        Command::Send { archive, .. } => format!("Send mail from archive: {}", archive.display()),
        Command::Delete { id } => format!("Delete message: {id}"),
        Command::Read { id, out, .. } => format!("Download message {id} to {}", out.display()),
        Command::Get { id } => format!("Get message metadata: {id}"),
        Command::Mark { id, read, .. } => format!(
            "Mark message {id} {}",
            if *read { "read" } else { "unread" }
        ),
        Command::Address { command } => match command {
            AddressCommand::Add { local_part, tmp } => format!(
                "Register {}@{}",
                local_part,
                if *tmp {
                    "tmpaddr.moesegfault.dev"
                } else {
                    "mail.moesegfault.dev"
                }
            ),
            AddressCommand::Delete { address } => format!("Retire address: {address}"),
            AddressCommand::List => "List owned addresses".into(),
        },
        Command::Mailbox { command } => match command {
            MailboxCommand::Acquire { address, mode } => {
                format!("Acquire {mode} ownership: {address}")
            }
            MailboxCommand::Release { address } => format!("Release mailbox ownership: {address}"),
            MailboxCommand::Export { address, out } => {
                format!("Export live history for {address} to {}", out.display())
            }
        },
        Command::Login { .. }
        | Command::Auth {
            command: AuthCommand::Login { .. },
        } => "Authenticate owner account in browser".into(),
        Command::Logout
        | Command::Auth {
            command: AuthCommand::Logout,
        } => "Remove the owner's local account credentials".into(),
        Command::Auth {
            command: AuthCommand::Status,
        } => "Read owner authentication status".into(),
        Command::Pack { directory, out } => {
            format!("Pack {} to {}", directory.display(), out.display())
        }
        Command::Unpack { archive, out } => {
            format!("Extract {} to {}", archive.display(), out.display())
        }
        Command::Search(_) => "Search messages within the profile's acquired mailboxes".into(),
        Command::Sync { .. } => {
            "Synchronize messages within the profile's acquired mailboxes".into()
        }
        Command::Billing { .. } => "Inspect or open human-authorized billing".into(),
        Command::SendStatus { .. } => "Inspect logical send status".into(),
        Command::SendReceipts { .. } => "Read local accepted-send receipts".into(),
        Command::SendingStatus => "Inspect sending policy and resource quotas".into(),
        Command::Events { .. } | Command::Outcomes { .. } => {
            "Read owned mail delivery feedback".into()
        }
        Command::Config => "Read non-secret configuration".into(),
        _ => "Run amail operation".into(),
    }
}

pub(crate) fn run_daemon(request: daemon::Request) -> Result<()> {
    machine::enable(machine::requested(request.args.clone()));
    session::clear();
    let mut cli = Cli::try_parse_from(request.args)
        .map_err(|error| machine::invalid_input(&error.to_string()))?;
    absolute_paths(&mut cli, &request.cwd);
    let cfg = request.cfg;
    let terminal = request.terminal;
    if cfg.home.join("auth.sqlite3").exists() {
        let credentials = auth::status(&cfg)?;
        session::set_account(
            &cfg,
            credentials.as_ref().map(|tokens| tokens.subject.as_str()),
        );
        send_state::bind_account(&cfg)?;
    }
    let mut store = profiles::Store::open(&cfg)?;
    let mut active = store.peek_active(&terminal)?;
    let profile_control = matches!(&cli.command, Command::Profile { .. });
    let activation = matches!(
        &cli.command,
        Command::Profile {
            command: ProfileCommand::Activate { .. }
        }
    );
    let mut implicit_activation = false;
    if active.is_none() && !activation && !store.terminal_initialized(&terminal)? {
        if !cfg.yolo {
            approval::authorize_request(
                "profile.activate",
                &format!(
                    "Activate the initial user profile; {}",
                    approval_summary(&cli.command)
                ),
            )?;
        }
        active = Some(store.activate(&terminal, "user")?);
        implicit_activation = true;
    } else if !cfg.yolo {
        let requested_user = matches!(&cli.command, Command::Profile { command: ProfileCommand::Activate { name } } if name == "user")
            || matches!(&cli.command, Command::Profile { command: ProfileCommand::Release { name:Some(name) } } if name == "user");
        if active
            .as_ref()
            .is_some_and(|profile| profile.name == "user")
            || requested_user
        {
            approval::authorize_request("operation", &approval_summary(&cli.command))?;
        }
    }
    if let Some(profile) = active.as_ref() {
        session::install(&terminal, profile.clone());
        store.active(&terminal)?;
        if implicit_activation
            && session::account_scope().is_some()
            && !matches!(
                &cli.command,
                Command::Auth {
                    command: AuthCommand::Login { .. } | AuthCommand::Logout
                } | Command::Login { .. }
                    | Command::Logout
            )
        {
            if let Err(error) = session::activate_cloud(&cfg) {
                store.deactivate(&terminal)?;
                return Err(error);
            }
        }
        if !matches!(
            &cli.command,
            Command::Profile {
                command: ProfileCommand::Release { .. }
            }
        ) {
            session::touch_existing_cloud(&cfg)?;
        }
    } else {
        ensure!(
            profile_control,
            "profile_inactive: activate a profile for this terminal"
        );
    }
    if matches!(
        &cli.command,
        Command::Auth { .. } | Command::Login { .. } | Command::Logout
    ) {
        ensure!(
            active.as_ref().is_some_and(|p| p.name == "user"),
            "user_profile_required: account authentication belongs to user"
        );
    }
    if let Command::Profile { command } = cli.command {
        return run_profile(command, &cfg, &terminal, &mut store, active, cli.human);
    }
    if let Command::Mailbox { command } = cli.command {
        return match command {
            MailboxCommand::Acquire { address, mode } => {
                emit(&session::acquire(&cfg, &address, &mode)?, cli.human)
            }
            MailboxCommand::Release { address } => {
                emit(&session::release_mailbox(&cfg, &address)?, cli.human)
            }
            MailboxCommand::Export { address, out } => {
                session::acquire(&cfg, &address, "read")?;
                export::run(&api::Api::new(&cfg)?, &address, &out, cli.human)
            }
        };
    }
    if let Err(error) = telemetry::init(&cfg) {
        telemetry::report_loss("initialize", &error);
    }
    command_journal::run_with_context(&cfg, command_kind(&cli.command), |command_id| {
        execute(cli, &cfg, command_id)
    })
}

fn run_profile(
    command: ProfileCommand,
    cfg: &config::Runtime,
    terminal: &str,
    store: &mut profiles::Store,
    active: Option<profiles::ActiveProfile>,
    human: bool,
) -> Result<()> {
    match command {
        ProfileCommand::List => {
            if active.is_some()
                && cfg.home.join("auth.sqlite3").exists()
                && auth::status(cfg)?.is_some()
            {
                let cloud = session::list_cloud(cfg)?;
                for profile in cloud
                    .get("profiles")
                    .and_then(Value::as_array)
                    .into_iter()
                    .flatten()
                {
                    if let Some(name) = profile.get("name").and_then(Value::as_str) {
                        let durable = profile
                            .get("durable")
                            .and_then(Value::as_bool)
                            .or_else(|| {
                                profile
                                    .get("durable")
                                    .and_then(Value::as_i64)
                                    .map(|number| number != 0)
                            })
                            .unwrap_or(false);
                        store.import_cloud_profile(name, durable)?;
                    }
                }
            }
            emit(&json!({"profiles":store.list(terminal)?}), human)
        }
        ProfileCommand::Status => emit(&json!({"profile":active}), human),
        ProfileCommand::Activate { name } => {
            ensure!(
                active.as_ref().is_none_or(|profile| profile.name == name),
                "profile_active: deactivate the current profile before activating another"
            );
            let authenticated =
                cfg.home.join("auth.sqlite3").exists() && auth::status(cfg)?.is_some();
            let local_exists = store
                .list(terminal)?
                .iter()
                .any(|profile| profile.name == name);
            if !local_exists && authenticated {
                let registration = session::discover(cfg, &name, terminal)?;
                store.import_cloud_profile(&name, registration.durable)?;
                let profile = store.activate(terminal, &name)?;
                store.set_cloud_session(
                    &profile.id,
                    &registration.profile_id,
                    &registration.token,
                    registration.expires_at,
                )?;
                session::install(terminal, profile.clone());
                return emit(&json!({"profile":profile}), human);
            }
            let profile = store.activate(terminal, &name)?;
            session::install(terminal, profile.clone());
            if authenticated {
                if let Err(error) = session::activate_cloud(cfg) {
                    store.deactivate(terminal)?;
                    return Err(error);
                }
            }
            emit(&json!({"profile":profile}), human)
        }
        ProfileCommand::Deactivate => emit(
            &json!({"deactivated":true,"profile":store.deactivate(terminal)?}),
            human,
        ),
        ProfileCommand::Create { name } => {
            let existing = store
                .list(terminal)?
                .into_iter()
                .find(|profile| profile.name == name);
            let profile = if let Some(profile) = existing {
                profile
            } else {
                store.create(terminal, &name)?
            };
            if cfg.home.join("auth.sqlite3").exists() && auth::status(cfg)?.is_some() {
                session::create_cloud(cfg, &profile.name, profile.durable)?;
            }
            emit(&json!({"profile":profile}), human)
        }
        ProfileCommand::Release { name } => {
            let name = name
                .or_else(|| active.map(|p| p.name))
                .context("profile_inactive: specify the reserved profile name")?;
            let profile = store
                .list(terminal)?
                .into_iter()
                .find(|p| p.name == name)
                .context("profile_not_found")?;
            ensure!(
                profile.owned,
                "profile_not_owned: this terminal does not own the profile"
            );
            let profile = profiles::ActiveProfile {
                id: profile.id,
                name: profile.name,
            };
            session::release_cloud(cfg, &profile)?;
            let released = store.release(terminal, &name)?;
            emit(&json!({"released":true,"profile":released}), human)
        }
    }
}
/// Canonical diagnostic names never include arguments or alias spellings.
fn command_kind(command: &Command) -> Option<command_journal::CommandKind> {
    use command_journal::CommandKind as K;
    Some(match command {
        Command::TelemetryFlush { .. }
        | Command::Profile { .. }
        | Command::Mailbox { .. }
        | Command::Daemon { .. }
        | Command::DaemonServe
        | Command::Discover { .. }
        | Command::SendStatus { .. }
        | Command::SendReceipts { .. }
        | Command::SendingStatus
        | Command::Outcomes { .. }
        | Command::Events { .. } => return None,
        Command::Billing { command } => match command {
            billing::Command::Status => K::BillingStatus,
            billing::Command::Subscribe { .. } => K::BillingSubscribe,
            billing::Command::Manage { .. } => K::BillingManage,
            billing::Command::Session { .. } => K::BillingSession,
        },
        Command::Config => K::Config,
        Command::Pack { .. } => K::Pack,
        Command::Unpack { .. } => K::Unpack,
        Command::Auth {
            command: AuthCommand::Login { .. },
        }
        | Command::Login { .. } => K::AuthLogin,
        Command::Auth {
            command: AuthCommand::Status,
        } => K::AuthStatus,
        Command::Auth {
            command: AuthCommand::Logout,
        }
        | Command::Logout => K::AuthLogout,
        Command::Address {
            command: AddressCommand::List,
        } => K::AddressList,
        Command::Address {
            command: AddressCommand::Add { .. },
        } => K::AddressAdd,
        Command::Address {
            command: AddressCommand::Delete { .. },
        } => K::AddressDelete,
        Command::Sync { .. } => K::Sync,
        Command::Search(_) => K::Search,
        Command::Get { .. } => K::Get,
        Command::Read { .. } => K::Read,
        Command::Mark { .. } => K::Mark,
        Command::Delete { .. } => K::Delete,
        Command::Send { .. } => K::Send,
    })
}

/// Execute the unchanged public behavior inside a best-effort completion boundary.
fn execute(cli: Cli, cfg: &config::Runtime, command_id: Option<uuid::Uuid>) -> Result<()> {
    match cli.command {
        Command::Discover { topic } => emit(&discovery::topic(topic.as_deref())?, cli.human)?,
        Command::SendReceipts { limit } => {
            emit_items(&send_state::receipts(cfg, limit)?, cli.human, &["receipts"])?
        }
        Command::SendStatus { id, local: true } => {
            emit(&send_state::receipt(cfg, &id)?, cli.human)?
        }
        Command::Config => emit(
            &json!({"api_base":cfg.api_base,"issuer":cfg.issuer,"client_id":cfg.client_id,
            "redirect_uri":cfg.redirect_uri,"home":cfg.home,"yolo":cfg.yolo,"daemon":cfg.daemon,"telemetry_enabled":std::env::var("AMAIL_TELEMETRY").ok().as_deref()!=Some("off")}),
            cli.human,
        )?,
        Command::TelemetryFlush { attempt_id } => {
            telemetry::flush_pending(&cfg, attempt_id.as_ref())?;
        }
        Command::Auth { command } => match command {
            AuthCommand::Login { no_browser } => {
                auth::login(&cfg, no_browser).map_err(|error| machine::Failure {
                    code: "authentication_failed",
                    next_action: "login",
                    data: json!({}),
                    message: error.to_string(),
                })?;
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
            auth::login(&cfg, no_browser).map_err(|error| machine::Failure {
                code: "authentication_failed",
                next_action: "login",
                data: json!({}),
                message: error.to_string(),
            })?;
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
            let bytes = archive::outbound_bytes(&path).map_err(|error| machine::Failure {
                code: "invalid_draft",
                next_action: "fix_input",
                data: json!({}),
                message: error.to_string(),
            })?;
            let digest = Sha256::digest(&bytes);
            let hash: String = digest.iter().map(|b| format!("{b:02x}")).collect();
            let key = if let Some(key) = idempotency_key {
                if uuid::Uuid::parse_str(&key).is_err() {
                    return Err(machine::invalid_input("idempotency key must be a UUID"));
                }
                key
            } else {
                let random = uuid::Uuid::new_v4().to_string();
                send_state::send_key(&cfg, &hash, &random)?
            };
            machine::event(
                "send_intent",
                json!({"idempotency_key":key,"next_action":"query_send_status"}),
            );
            let result = api::Api::for_command(&cfg, command_id)?.send_owned(bytes, &key)?;
            // Persist acceptance before stdout; release only this matching unresolved intent.
            send_state::record_accepted(&cfg, &hash, &key, &result).map_err(|error| {
                machine::Failure {
                    code: "accepted_receipt_unavailable",
                    next_action: "query_send_status",
                    data: json!({"idempotency_key":key}),
                    message: format!("send accepted but local receipt unavailable: {error}"),
                }
            })?;
            emit(&result, cli.human)?;
        }
        command => {
            let api = api::Api::for_command(&cfg, command_id)?;
            match command {
                Command::SendStatus { id, local: false } => {
                    emit(&api.send_status(&id)?, cli.human)?
                }
                Command::SendingStatus => emit(&api.sending_status()?, cli.human)?,
                Command::Billing { command } => billing::run(&api, command, cli.human)?,
                Command::Outcomes { id } => emit(&api.outcomes(&id)?, cli.human)?,
                Command::Events {
                    message,
                    kind,
                    since,
                    limit,
                    cursor,
                } => emit_items(
                    &api.events(
                        message.as_deref(),
                        kind.as_deref(),
                        since.as_deref(),
                        limit,
                        cursor.as_deref(),
                    )?,
                    cli.human,
                    &["events"],
                )?,
                Command::Address { command } => match command {
                    AddressCommand::List => {
                        emit_items(&api.addresses()?, cli.human, &["addresses", "items"])?
                    }
                    AddressCommand::Add { local_part, tmp } => emit(
                        &api.add_address_kind(&local_part, if tmp { "tmpaddr" } else { "mail" })?,
                        cli.human,
                    )?,
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
    machine::enable(machine::requested(std::env::args_os()));
    if let Err(error) = run() {
        // Debug chains can contain HTTP URLs or provider payloads; print only the top-level error.
        // 调试错误链可能包含 URL 或提供者载荷，因此只打印顶层错误。
        if machine::enabled() {
            machine::event("error", machine::error_record(&error));
        } else {
            eprintln!("amail: {error}");
        }
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
            let help = match Cli::try_parse_from(args.clone()) {
                Ok(_) => panic!("help unexpectedly parsed as a command: {args:?}"),
                Err(help) => help,
            };
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
                "up to 24 hours",
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
    fn progressive_commands_and_machine_flag_parse() {
        let cli = Cli::try_parse_from([
            "amail",
            "--machine",
            "events",
            "--message",
            "m1",
            "--kind",
            "delivered",
            "--limit",
            "3",
        ])
        .unwrap();
        assert!(cli.machine);
        assert!(matches!(cli.command, Command::Events { limit: 3, .. }));
        assert!(Cli::try_parse_from(["amail", "--machine", "--human", "discover"]).is_err());
        let cli = Cli::try_parse_from([
            "amail",
            "send",
            "draft.zip",
            "--intent",
            "123e4567-e89b-42d3-a456-426614174000",
        ])
        .unwrap();
        assert!(matches!(
            cli.command,
            Command::Send {
                idempotency_key: Some(_),
                ..
            }
        ));
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
