//! CLI configuration and paths / CLI 配置与路径。

use anyhow::{bail, Context, Result};
use directories::ProjectDirs;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

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
}

/// Resolved runtime configuration / 解析后的运行配置。
#[derive(Clone, Debug)]
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
}

impl Runtime {
    /// Load convention defaults, then TOML, then environment overrides.
    /// 依次应用约定默认值、TOML 和环境变量覆盖。
    pub fn load() -> Result<Self> {
        let home = if let Ok(value) = std::env::var("AMAIL_HOME") {
            PathBuf::from(value)
        } else {
            ProjectDirs::from("dev", "moesegfault", "amail")
                .context("cannot determine the application data directory")?
                .data_local_dir()
                .to_path_buf()
        };
        std::fs::create_dir_all(&home).with_context(|| format!("creating {}", home.display()))?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&home, std::fs::Permissions::from_mode(0o700))?;
        }
        let path = home.join("config.toml");
        let config: Config = if path.exists() {
            toml::from_str(&std::fs::read_to_string(&path)?)
                .with_context(|| format!("parsing {}", path.display()))?
        } else {
            Config::default()
        };
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
