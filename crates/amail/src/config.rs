//! CLI configuration and paths / CLI 配置与路径。

use anyhow::{bail, Context, Result};
use directories::{ProjectDirs, UserDirs};
use fs2::FileExt;
use serde::{Deserialize, Serialize};
use std::{
    fs::OpenOptions,
    io::Write,
    path::{Path, PathBuf},
    time::Duration,
};

/// Non-secret configuration. OAuth credentials deliberately never belong here.
/// 非敏感配置；OAuth 凭据绝不写入此处。
#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct Config {
    /// Mail Worker HTTPS origin / 邮件 Worker 的 HTTPS 源。
    pub api_base: Option<String>,
    /// Pinned Identity issuer / 固定的 Identity 签发者。
    pub issuer: Option<String>,
    /// Public native OAuth client ID / 公开的原生 OAuth 客户端 ID。
    pub client_id: Option<String>,
    /// Registered native loopback redirect template / 已注册的原生回环重定向模板。
    pub redirect_uri: Option<String>,
    /// Explicitly bypass human approval for operations in the user profile.
    #[serde(default)]
    pub yolo: bool,
    #[serde(default)]
    pub daemon: DaemonConfig,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(default)]
pub struct DaemonConfig {
    pub max_concurrency: usize,
    pub start_timeout_seconds: u64,
}

impl Default for DaemonConfig {
    fn default() -> Self {
        Self {
            max_concurrency: 4,
            start_timeout_seconds: 15,
        }
    }
}

impl DaemonConfig {
    fn validate(&self) -> Result<()> {
        if !(1..=32).contains(&self.max_concurrency) {
            bail!("daemon.max_concurrency must be 1..32");
        }
        if !(1..=120).contains(&self.start_timeout_seconds) {
            bail!("daemon.start_timeout_seconds must be 1..120");
        }
        Ok(())
    }
}

/// Resolved runtime configuration / 解析后的运行配置。
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Runtime {
    /// Mail Worker HTTPS origin / 邮件 Worker 的 HTTPS 源。
    pub api_base: String,
    /// Pinned Identity issuer / 固定的 Identity 签发者。
    pub issuer: String,
    /// Exact accepted OAuth audience / 精确接受的 OAuth 受众。
    pub client_id: String,
    /// Loopback redirect template, optionally with fixed port / 可选固定端口的回环重定向模板。
    pub redirect_uri: String,
    /// Local non-secret state directory / 本地非敏感状态目录。
    pub home: PathBuf,
    pub yolo: bool,
    pub daemon: DaemonConfig,
}

impl Runtime {
    /// Load convention defaults, then TOML, then environment overrides.
    /// 依次应用约定默认值、TOML 和环境变量覆盖。
    pub fn load() -> Result<Self> {
        let explicit_home = std::env::var_os("AMAIL_HOME");
        let home = if let Some(value) = &explicit_home {
            PathBuf::from(value)
        } else {
            UserDirs::new()
                .context("cannot determine the user home directory")?
                .home_dir()
                .join(".amail")
        };
        let home = if home.is_absolute() {
            home
        } else {
            std::env::current_dir()?.join(home)
        };
        std::fs::create_dir_all(&home).with_context(|| format!("creating {}", home.display()))?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&home, std::fs::Permissions::from_mode(0o700))?;
        }
        if explicit_home.is_none() {
            if let Some(legacy) = ProjectDirs::from("dev", "moesegfault", "amail") {
                migrate_legacy(legacy.data_local_dir(), &home)?;
            }
        }
        std::fs::create_dir_all(home.join("bin"))?;
        let path = home.join("config.toml");
        let config: Config = if path.exists() {
            toml::from_str(&std::fs::read_to_string(&path)?)
                .with_context(|| format!("parsing {}", path.display()))?
        } else {
            Config::default()
        };
        config.daemon.validate()?;
        let value = |key: &str, file: Option<String>, fallback: &str| {
            std::env::var(key)
                .ok()
                .or(file)
                .unwrap_or_else(|| fallback.to_owned())
        };
        let api_base = value(
            "AMAIL_API_BASE",
            config.api_base,
            "https://mail.moesegfault.dev",
        );
        let issuer = value(
            "AMAIL_ISSUER",
            config.issuer,
            "https://identity.moesegfault.dev",
        );
        let client_id = value("AMAIL_CLIENT_ID", config.client_id, "amail-cli");
        let redirect_uri = value(
            "AMAIL_REDIRECT_URI",
            config.redirect_uri,
            "http://127.0.0.1/callback",
        );
        for (name, url) in [("api_base", &api_base), ("issuer", &issuer)] {
            let parsed = url::Url::parse(url).with_context(|| format!("invalid {name}"))?;
            if parsed.scheme() != "https"
                || parsed.host_str().is_none()
                || parsed.path() != "/"
                || parsed.query().is_some()
                || parsed.fragment().is_some()
                || !parsed.username().is_empty()
                || parsed.password().is_some()
            {
                bail!("{name} must be an HTTPS origin");
            }
        }
        Ok(Self {
            api_base: api_base.trim_end_matches('/').to_owned(),
            issuer: issuer.trim_end_matches('/').to_owned(),
            client_id,
            redirect_uri,
            home,
            yolo: config.yolo,
            daemon: config.daemon,
        })
    }

    /// Require reviewed native-client registration for OAuth use.
    /// OAuth 使用前必须具备经审核的原生客户端注册信息。
    pub fn require_oauth(&self) -> Result<()> {
        if self.client_id.is_empty() || self.redirect_uri.is_empty() {
            bail!("Identity native client registration missing: set AMAIL_CLIENT_ID and AMAIL_REDIRECT_URI (or config.toml)");
        }
        let uri = url::Url::parse(&self.redirect_uri).context("invalid redirect_uri")?;
        if uri.scheme() != "http"
            || uri.host_str() != Some("127.0.0.1")
            || uri.path() != "/callback"
            || uri.query().is_some()
            || uri.fragment().is_some()
        {
            bail!("redirect_uri must be a registered http://127.0.0.1[:port]/callback");
        }
        Ok(())
    }
}

/// Copy a consistent upgrade snapshot without dropping unresolved send journals.
/// Old binaries must be closed before upgrading; their mutable stores are retained
/// as recovery input, not silently merged with a separately initialized new home.
fn migrate_legacy(legacy: &Path, home: &Path) -> Result<()> {
    if legacy == home || !legacy.is_dir() {
        return Ok(());
    }
    let complete = home.join(".legacy-migration-complete");
    if complete.exists() {
        return Ok(());
    }
    let lock = OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(home.join("migration.lock"))?;
    lock.lock_exclusive()?;
    if complete.exists() {
        return Ok(());
    }
    let pending = home.join(".legacy-migration-pending");
    let databases = ["auth.sqlite3", "telemetry.sqlite3"];
    if !pending.exists() && databases.iter().any(|name| home.join(name).exists()) {
        bail!("legacy amail state and initialized ~/.amail both exist; retain both and set AMAIL_HOME explicitly before migrating");
    }
    let refresh = OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(legacy.join("refresh.lock"))?;
    refresh
        .try_lock_exclusive()
        .context("close older amail processes before migrating local state")?;
    if !pending.exists() {
        write_marker(&pending)?;
    }
    for name in databases {
        let source = legacy.join(name);
        if !source.exists() {
            continue;
        }
        let staged = home.join(format!(".migration-{name}"));
        if staged.exists() {
            std::fs::remove_file(&staged)?;
        }
        let db = rusqlite::Connection::open_with_flags(
            &source,
            rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY,
        )?;
        db.busy_timeout(Duration::from_secs(5))?;
        db.execute(
            "VACUUM INTO ?1",
            [staged
                .to_str()
                .context("legacy migration path must be Unicode")?],
        )?;
        protect_file(&staged)?;
        OpenOptions::new().write(true).open(&staged)?.sync_all()?;
        let destination = home.join(name);
        if destination.exists() {
            // Only an interrupted, never-admitted migration can own this file.
            std::fs::remove_file(&destination)?;
        }
        std::fs::rename(&staged, &destination)?;
    }
    let old_config = legacy.join("config.toml");
    let new_config = home.join("config.toml");
    if old_config.exists() && !new_config.exists() {
        let mut target = OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&new_config)?;
        protect_file(&new_config)?;
        std::io::copy(&mut std::fs::File::open(old_config)?, &mut target)?;
        target.sync_all()?;
    }
    write_marker(&complete)?;
    std::fs::remove_file(pending)?;
    Ok(())
}

fn write_marker(path: &Path) -> Result<()> {
    let mut marker = OpenOptions::new().create_new(true).write(true).open(path)?;
    protect_file(path)?;
    marker.write_all(b"amail local-state migration v1\n")?;
    marker.sync_all()?;
    Ok(())
}

fn protect_file(path: &Path) -> Result<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600))?;
    }
    #[cfg(not(unix))]
    let _ = path;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> tempfile::TempDir {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.temp");
        std::fs::create_dir_all(&root).unwrap();
        tempfile::tempdir_in(root).unwrap()
    }

    #[test]
    fn convention_defaults_are_safe_and_partial_toml_overrides_them() {
        let defaults: Config = toml::from_str("").unwrap();
        assert!(!defaults.yolo);
        assert_eq!(defaults.daemon.max_concurrency, 4);
        let configured: Config =
            toml::from_str("yolo = true\n[daemon]\nmax_concurrency = 2\n").unwrap();
        assert!(configured.yolo);
        assert_eq!(configured.daemon.max_concurrency, 2);
        assert_eq!(configured.daemon.start_timeout_seconds, 15);
        assert!(toml::from_str::<Config>("[daemon]\nmax_concurrency = 0")
            .unwrap()
            .daemon
            .validate()
            .is_err());
    }

    #[test]
    fn migration_preserves_wal_state_and_never_reimports_after_admission() {
        let root = fixture();
        let old = root.path().join("old");
        let new = root.path().join("new");
        std::fs::create_dir_all(&old).unwrap();
        std::fs::create_dir_all(&new).unwrap();
        let db = rusqlite::Connection::open(old.join("telemetry.sqlite3")).unwrap();
        db.execute_batch("PRAGMA journal_mode=WAL; CREATE TABLE intents (key TEXT); INSERT INTO intents VALUES ('unresolved');").unwrap();
        migrate_legacy(&old, &new).unwrap();
        let copied = rusqlite::Connection::open(new.join("telemetry.sqlite3")).unwrap();
        let key: String = copied
            .query_row("SELECT key FROM intents", [], |row| row.get(0))
            .unwrap();
        assert_eq!(key, "unresolved");
        copied
            .execute("UPDATE intents SET key='accepted'", [])
            .unwrap();
        migrate_legacy(&old, &new).unwrap();
        let key: String = copied
            .query_row("SELECT key FROM intents", [], |row| row.get(0))
            .unwrap();
        assert_eq!(key, "accepted");
    }

    #[test]
    fn migration_refuses_to_overwrite_an_independent_new_store() {
        let root = fixture();
        let old = root.path().join("old");
        let new = root.path().join("new");
        std::fs::create_dir_all(&old).unwrap();
        std::fs::create_dir_all(&new).unwrap();
        std::fs::write(new.join("auth.sqlite3"), b"keep").unwrap();
        assert!(migrate_legacy(&old, &new).is_err());
        assert_eq!(std::fs::read(new.join("auth.sqlite3")).unwrap(), b"keep");
    }
}
