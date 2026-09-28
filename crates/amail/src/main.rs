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
};

/// Compact JSONL by default; `--human` opts into readable formatting.
/// 默认输出紧凑 JSONL；`--human` 才启用可读排版。
#[derive(Parser)]
#[command(name = "amail", version, about = "Agent-first mail for moeSegFault", long_about = None)]
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
    /// KEY=VALUE metadata predicate, repeatable.
    #[arg(long = "meta")]
    metadata: Vec<String>,
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
            for (label, key) in [
                ("ID", "id"),
                ("Mailbox", "mailbox"),
                ("From", "from"),
                ("To", "to"),
                ("Subject", "subject"),
                ("Received", "received_at"),
                ("Read", "read"),
                ("Size", "size_bytes"),
                ("Attachments", "has_attachments"),
            ] {
                if let Some(field) = value.get(key) {
                    let display = field
                        .as_str()
                        .map(str::to_owned)
                        .unwrap_or_else(|| field.to_string());
                    println!("{label:<12} {display}");
                }
            }
        } else {
            println!("{}", serde_json::to_string_pretty(value)?);
        }
    } else {
        println!("{}", serde_json::to_string(value)?);
    }
    Ok(())
}

fn emit_items(value: &Value, human: bool, keys: &[&str]) -> Result<()> {
    if human {
        if let Some(addresses) = value.get("addresses").and_then(Value::as_array) {
            let heading = format!("{:<40} {:<10} {}", "ADDRESS", "STATE", "CREATED");
            human_heading(&heading);
            for row in addresses {
                println!(
                    "{:<40} {:<10} {}",
                    field(row, "address"),
                    field(row, "state"),
                    field(row, "created_at")
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
                    clipped(field(row, "id"), 36),
                    clipped(field(row, "received_at"), 20),
                    read,
                    clipped(field(row, "from"), 28),
                    field(row, "subject")
                );
            }
            if let Some(cursor) = value.get("next_cursor").and_then(Value::as_str) {
                println!("Next cursor: {cursor}");
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
                Command::Search(args) => emit_items(
                    &api.search(&search_request(&args)?)?,
                    cli.human,
                    &["messages", "items"],
                )?,
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

    #[test]
    fn search_keeps_composed_predicates() {
        let args = SearchArgs {
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
    fn archive_write_never_overwrites() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("mail.zip");
        write_new(&path, b"first").unwrap();
        assert!(write_new(&path, b"second").is_err());
        assert_eq!(std::fs::read(path).unwrap(), b"first");
    }
}
