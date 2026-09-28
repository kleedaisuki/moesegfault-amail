//! Native OIDC login, protected credentials, and refresh / 原生 OIDC 登录、安全凭据与刷新。

use crate::config::Runtime;
use anyhow::{bail, ensure, Context, Result};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use chacha20poly1305::{
    aead::{Aead, KeyInit, Payload},
    ChaCha20Poly1305, Nonce,
};
use fs2::FileExt;
use jsonwebtoken::{decode, decode_header, jwk::Jwk, Algorithm, DecodingKey, Validation};
use rand::RngCore;
use reqwest::blocking::Client;
use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{
    io::{Read, Write},
    net::TcpListener,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

/// Pinned issuer discovery result / 固定签发者的发现结果。
#[derive(Debug, Deserialize)]
struct Discovery {
    issuer: String,
    authorization_endpoint: String,
    token_endpoint: String,
    jwks_uri: String,
    revocation_endpoint: Option<String>,
    #[serde(default)]
    authorization_response_iss_parameter_supported: bool,
    #[serde(default)]
    code_challenge_methods_supported: Vec<String>,
}

/// Stored tokens; never print or send to telemetry / 存储的令牌，不输出、不遥测。
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Tokens {
    /// Short-lived bearer for the mail API / 邮件 API 的短期 Bearer 令牌。
    pub access_token: String,
    /// Rotating refresh credential, never logged / 旋转刷新凭据，绝不记录日志。
    pub refresh_token: Option<String>,
    /// Validated ID token retained only for session context / 已校验、仅用于会话上下文的 ID 令牌。
    pub id_token: Option<String>,
    /// Unix expiration time / Unix 过期时间。
    pub expires_at: u64,
    /// Pairwise issuer subject, private to credential store / 签发者成对主体，仅保存在凭据存储中。
    pub subject: String,
}

#[derive(Debug, Deserialize)]
struct TokenReply {
    access_token: String,
    refresh_token: Option<String>,
    id_token: Option<String>,
    expires_in: u64,
    token_type: String,
}

#[derive(Debug, Deserialize)]
struct IdClaims {
    sub: String,
    nonce: String,
    token_use: String,
}

/// Fetch discovery and reject issuer drift or non-PKCE providers.
/// 获取发现文档并拒绝签发者漂移或不支持 PKCE 的提供者。
fn discover(cfg: &Runtime, http: &Client) -> Result<Discovery> {
    let uri = format!("{}/.well-known/openid-configuration", cfg.issuer);
    let d: Discovery = http
        .get(uri)
        .send()?
        .error_for_status()?
        .json()
        .context("Identity discovery must return JSON, not a login page")?;
    ensure!(d.issuer == cfg.issuer, "Identity issuer mismatch");
    ensure!(
        d.code_challenge_methods_supported
            .iter()
            .any(|x| x == "S256"),
        "Identity does not advertise S256 PKCE"
    );
    ensure!(
        d.authorization_response_iss_parameter_supported,
        "Identity must advertise authorization-response issuer"
    );
    for endpoint in [&d.authorization_endpoint, &d.token_endpoint, &d.jwks_uri] {
        ensure!(
            url::Url::parse(endpoint)?.scheme() == "https",
            "insecure Identity endpoint"
        );
    }
    Ok(d)
}

fn random_urlsafe(len: usize) -> String {
    let mut bytes = vec![0u8; len];
    rand::thread_rng().fill_bytes(&mut bytes);
    URL_SAFE_NO_PAD.encode(bytes)
}

fn now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

/// Validate RS256 ID token signature, issuer, audience, time, kind, and nonce.
/// 校验 RS256 ID 令牌的签名、签发者、受众、时间、种类和 nonce。
fn validate_id(
    token: &str,
    expected_nonce: &str,
    cfg: &Runtime,
    d: &Discovery,
    http: &Client,
) -> Result<String> {
    let header = decode_header(token)?;
    ensure!(
        header.alg == Algorithm::RS256,
        "unexpected ID token algorithm"
    );
    let kid = header.kid.context("ID token missing kid")?;
    let jwks: Value = http.get(&d.jwks_uri).send()?.error_for_status()?.json()?;
    let keys = jwks["keys"].as_array().context("JWKS missing keys")?;
    let item = keys
        .iter()
        .find(|key| key["kid"].as_str() == Some(kid.as_str()))
        .context("ID token signing key not found")?;
    ensure!(item["kty"] == "RSA", "ID token JWK must be RSA");
    ensure!(
        item["use"].is_null() || item["use"] == "sig",
        "ID token JWK is not for signing"
    );
    ensure!(
        item["alg"].is_null() || item["alg"] == "RS256",
        "ID token JWK algorithm mismatch"
    );
    if let Some(ops) = item["key_ops"].as_array() {
        ensure!(
            ops.iter().any(|op| op == "verify"),
            "ID token JWK cannot verify"
        );
    }
    let jwk: Jwk = serde_json::from_value(item.clone())?;
    let key = DecodingKey::from_jwk(&jwk)?;
    let mut validation = Validation::new(Algorithm::RS256);
    validation.set_issuer(&[cfg.issuer.as_str()]);
    validation.set_audience(&[cfg.client_id.as_str()]);
    validation.leeway = 30;
    let claims = decode::<IdClaims>(token, &key, &validation)?.claims;
    ensure!(
        claims.token_use == "id",
        "access token supplied where ID token expected"
    );
    ensure!(claims.nonce == expected_nonce, "OIDC nonce mismatch");
    ensure!(!claims.sub.is_empty(), "ID token missing subject");
    Ok(claims.sub)
}

fn credential(cfg: &Runtime) -> Result<keyring::Entry> {
    keyring::Entry::new(
        "moesegfault-amail",
        &format!("{}|{}", cfg.issuer, cfg.client_id),
    )
    .context("opening platform credential store")
}

/// Keyring holds only a 32-byte key; SQLite stores an authenticated token ciphertext.
/// 钥匙串仅保留 32 字节密钥；SQLite 存储经过认证的令牌密文。
const KEY_PREFIX: &str = "amail:v2:";

fn session_key(cfg: &Runtime) -> String {
    format!("{}|{}", cfg.issuer, cfg.client_id)
}

fn aad(cfg: &Runtime) -> Vec<u8> {
    format!("amail-auth-v2\0{}\0{}", cfg.issuer, cfg.client_id).into_bytes()
}

fn auth_db(cfg: &Runtime) -> Result<Connection> {
    let path = cfg.home.join("auth.sqlite3");
    let conn = Connection::open(&path)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600))?;
    }
    conn.busy_timeout(Duration::from_secs(30))?;
    conn.execute_batch(
        "CREATE TABLE IF NOT EXISTS sessions (
        session_key TEXT PRIMARY KEY, nonce BLOB NOT NULL, ciphertext BLOB NOT NULL
    )",
    )?;
    Ok(conn)
}

fn seal(tokens: &Tokens, key: &[u8; 32], cfg: &Runtime) -> Result<([u8; 12], Vec<u8>)> {
    let mut nonce = [0u8; 12];
    rand::thread_rng().fill_bytes(&mut nonce);
    let cipher = ChaCha20Poly1305::new_from_slice(key).expect("fixed 32-byte AEAD key");
    let plaintext = serde_json::to_vec(tokens)?;
    let ciphertext = cipher
        .encrypt(
            Nonce::from_slice(&nonce),
            Payload {
                msg: &plaintext,
                aad: &aad(cfg),
            },
        )
        .map_err(|_| anyhow::anyhow!("encrypting local OAuth session failed"))?;
    Ok((nonce, ciphertext))
}

fn open(nonce: &[u8], ciphertext: &[u8], key: &[u8; 32], cfg: &Runtime) -> Result<Tokens> {
    ensure!(nonce.len() == 12, "local OAuth session nonce is invalid");
    let cipher = ChaCha20Poly1305::new_from_slice(key).expect("fixed 32-byte AEAD key");
    let plaintext = cipher
        .decrypt(
            Nonce::from_slice(nonce),
            Payload {
                msg: ciphertext,
                aad: &aad(cfg),
            },
        )
        .map_err(|_| anyhow::anyhow!("local OAuth session authentication failed"))?;
    serde_json::from_slice(&plaintext).context("local OAuth session is invalid")
}

fn parse_key(value: &str) -> Result<Option<[u8; 32]>> {
    let Some(encoded) = value.strip_prefix(KEY_PREFIX) else {
        return Ok(None);
    };
    let raw = URL_SAFE_NO_PAD
        .decode(encoded)
        .context("local OAuth key is invalid")?;
    let key: [u8; 32] = raw
        .try_into()
        .map_err(|_| anyhow::anyhow!("local OAuth key length is invalid"))?;
    Ok(Some(key))
}

/// Commit ciphertext before replacing a legacy keyring value; after migration, update atomically.
/// 替换旧钥匙串值前先提交密文；迁移后使用原子事务更新。
fn save(cfg: &Runtime, tokens: &Tokens) -> Result<()> {
    let entry = credential(cfg)?;
    let stored = match entry.get_password() {
        Ok(value) => Some(value),
        Err(keyring::Error::NoEntry) => None,
        Err(err) => return Err(err).context("platform credential store unavailable"),
    };
    let existing_key = stored.as_deref().map(parse_key).transpose()?.flatten();
    let key = existing_key.unwrap_or_else(|| {
        let mut key = [0u8; 32];
        rand::thread_rng().fill_bytes(&mut key);
        key
    });
    let (nonce, ciphertext) = seal(tokens, &key, cfg)?;
    let mut conn = auth_db(cfg)?;
    let tx = conn.transaction()?;
    tx.execute(
        "INSERT INTO sessions(session_key,nonce,ciphertext) VALUES(?1,?2,?3)
        ON CONFLICT(session_key) DO UPDATE SET nonce=excluded.nonce,ciphertext=excluded.ciphertext",
        params![session_key(cfg), nonce.as_slice(), ciphertext],
    )?;
    tx.commit()?;
    if existing_key.is_none() {
        entry.set_password(&format!("{KEY_PREFIX}{}", URL_SAFE_NO_PAD.encode(key)))?;
    }
    Ok(())
}

fn clear(cfg: &Runtime) -> Result<()> {
    // Always attempt both halves: deleting either one makes the remaining half unusable.
    // 始终尝试清除两部分：删除任一部分都会使另一部分无法使用。
    let keyring_result = (|| -> Result<()> {
        match credential(cfg)?.delete_credential() {
            Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
            Err(err) => Err(err).context("clearing platform credential"),
        }
    })();
    let db_result = auth_db(cfg)?.execute(
        "DELETE FROM sessions WHERE session_key=?1",
        [session_key(cfg)],
    );
    db_result.context("clearing encrypted OAuth session")?;
    keyring_result?;
    Ok(())
}

/// Cross-process token mutation lock / 跨进程令牌变更锁。
fn token_lock(cfg: &Runtime) -> Result<std::fs::File> {
    let file = std::fs::OpenOptions::new()
        .create(true)
        .read(true)
        .write(true)
        .open(cfg.home.join("refresh.lock"))?;
    file.lock_exclusive()?;
    Ok(file)
}

/// Read the bounded HTTP request line across arbitrary TCP fragmentation.
/// 跨任意 TCP 分片读取有界的 HTTP 请求行。
fn request_line(reader: &mut impl Read) -> Result<String> {
    let mut buf = [0u8; 8192];
    let mut used = 0;
    loop {
        ensure!(used < buf.len(), "callback request line too long");
        let size = reader.read(&mut buf[used..])?;
        ensure!(size > 0, "callback request line incomplete");
        used += size;
        if let Some(end) = buf[..used].windows(2).position(|bytes| bytes == b"\r\n") {
            return Ok(String::from_utf8_lossy(&buf[..end]).into_owned());
        }
    }
}

/// Load tokens from OS-protected credential storage / 从操作系统凭据存储读取令牌。
pub fn load(cfg: &Runtime) -> Result<Tokens> {
    status(cfg)?.context("not logged in; run `amail login`")
}

/// Distinguish a missing login from an unavailable platform credential store.
/// 区分尚未登录与操作系统凭据存储不可用。
pub fn status(cfg: &Runtime) -> Result<Option<Tokens>> {
    cfg.require_oauth()?;
    let value = match credential(cfg)?.get_password() {
        Ok(value) => value,
        Err(keyring::Error::NoEntry) => return Ok(None),
        Err(err) => return Err(err).context("platform credential store unavailable"),
    };
    if let Some(key) = parse_key(&value)? {
        let row: Option<(Vec<u8>, Vec<u8>)> = auth_db(cfg)?
            .query_row(
                "SELECT nonce,ciphertext FROM sessions WHERE session_key=?1",
                [session_key(cfg)],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .optional()?;
        let (nonce, ciphertext) =
            row.context("encrypted OAuth session missing; run `amail login`")?;
        return open(&nonce, &ciphertext, &key, cfg).map(Some);
    }
    // Legacy v0.1 session: readable until the next successful refresh migrates it.
    // 旧版会话可读取，下一次成功刷新后迁移。
    serde_json::from_str(&value)
        .map(Some)
        .context("stored OAuth token set is invalid")
}

/// Perform single-use browser PKCE login on the exact registered loopback URI.
/// 在精确注册的回环 URI 上执行一次性浏览器 PKCE 登录。
pub fn login(cfg: &Runtime, no_browser: bool) -> Result<String> {
    cfg.require_oauth()?;
    let http = Client::builder().timeout(Duration::from_secs(20)).build()?;
    let d = discover(cfg, &http)?;
    let mut redirect = url::Url::parse(&cfg.redirect_uri)?;
    let addr = format!("127.0.0.1:{}", redirect.port().unwrap_or(0));
    let listener = TcpListener::bind(&addr)
        .with_context(|| format!("cannot listen on registered redirect {addr}"))?;
    redirect
        .set_port(Some(listener.local_addr()?.port()))
        .map_err(|_| anyhow::anyhow!("invalid loopback port"))?;
    let redirect_uri = redirect.to_string();
    listener.set_nonblocking(true)?;
    let state = random_urlsafe(32);
    let nonce = random_urlsafe(32);
    let verifier = random_urlsafe(32);
    let challenge = URL_SAFE_NO_PAD.encode(Sha256::digest(verifier.as_bytes()));
    let mut auth_url = url::Url::parse(&d.authorization_endpoint)?;
    auth_url
        .query_pairs_mut()
        .append_pair("response_type", "code")
        .append_pair("client_id", &cfg.client_id)
        .append_pair("redirect_uri", &redirect_uri)
        .append_pair("scope", "openid profile offline_access")
        .append_pair("state", &state)
        .append_pair("nonce", &nonce)
        .append_pair("code_challenge", &challenge)
        .append_pair("code_challenge_method", "S256");
    if no_browser {
        println!("{}", auth_url);
    } else {
        webbrowser::open(auth_url.as_str()).context("opening system browser")?;
    }
    let started = Instant::now();
    let (code, mut callback) = loop {
        ensure!(
            started.elapsed() < Duration::from_secs(300),
            "login timed out"
        );
        match listener.accept() {
            Ok((mut stream, _)) => {
                stream.set_read_timeout(Some(Duration::from_secs(5)))?;
                let line = request_line(&mut stream);
                let result = (|| -> Result<String> {
                    let line = line?;
                    let mut parts = line.split_whitespace();
                    ensure!(parts.next() == Some("GET"), "invalid callback method");
                    let target = parts.next().context("callback target missing")?;
                    ensure!(
                        target.starts_with('/') && !target.starts_with("//"),
                        "invalid callback target"
                    );
                    let url = redirect.join(target)?;
                    ensure!(
                        url.origin() == redirect.origin(),
                        "callback origin mismatch"
                    );
                    ensure!(url.path() == "/callback", "invalid callback path");
                    let mut pairs = std::collections::HashMap::new();
                    for (key, value) in url.query_pairs() {
                        ensure!(
                            pairs.insert(key.into_owned(), value.into_owned()).is_none(),
                            "duplicate callback parameter"
                        );
                    }
                    ensure!(pairs.get("state") == Some(&state), "OIDC state mismatch");
                    ensure!(
                        pairs.get("iss") == Some(&cfg.issuer),
                        "authorization response issuer mismatch"
                    );
                    if let Some(error) = pairs.get("error") {
                        bail!("Identity denied login: {error}");
                    }
                    pairs
                        .get("code")
                        .cloned()
                        .context("authorization code missing")
                })();
                match result {
                    Ok(code) => break (code, stream),
                    Err(err) => {
                        let _ = callback_page(&mut stream, false);
                        return Err(err);
                    }
                }
            }
            Err(err) if err.kind() == std::io::ErrorKind::WouldBlock => {
                std::thread::sleep(Duration::from_millis(100))
            }
            Err(err) => return Err(err.into()),
        }
    };
    let result = (|| -> Result<String> {
        let reply: TokenReply = http
            .post(&d.token_endpoint)
            .form(&[
                ("grant_type", "authorization_code"),
                ("client_id", cfg.client_id.as_str()),
                ("code", code.as_str()),
                ("redirect_uri", redirect_uri.as_str()),
                ("code_verifier", verifier.as_str()),
            ])
            .send()?
            .error_for_status()?
            .json()?;
        ensure!(
            reply.token_type.eq_ignore_ascii_case("Bearer"),
            "unexpected token type"
        );
        let id = reply
            .id_token
            .as_deref()
            .context("Identity did not return ID token")?;
        let subject = validate_id(id, &nonce, cfg, &d, &http)?;
        let tokens = Tokens {
            access_token: reply.access_token,
            refresh_token: reply.refresh_token,
            id_token: reply.id_token,
            expires_at: now().saturating_add(reply.expires_in),
            subject: subject.clone(),
        };
        let _lock = token_lock(cfg)?;
        let conn = Connection::open(cfg.home.join("telemetry.sqlite3"))?;
        conn.execute_batch("CREATE TABLE IF NOT EXISTS refresh_state (session_key TEXT PRIMARY KEY, in_progress INTEGER NOT NULL)")?;
        conn.execute("INSERT INTO refresh_state(session_key,in_progress) VALUES(?1,0) ON CONFLICT(session_key) DO UPDATE SET in_progress=0", [format!("{}|{}", cfg.issuer, cfg.client_id)])?;
        // Persistence is the final fallible step before browser success.
        // 持久化是浏览器显示成功前最后一个可能失败的步骤。
        save(cfg, &tokens)?;
        Ok(subject)
    })();
    let _ = callback_page(&mut callback, result.is_ok());
    result
}

/// Render only a static no-store localhost result after persistence succeeds or fails.
/// 仅在持久化完成或失败后渲染静态、不可缓存的本地结果页。
fn callback_page(stream: &mut std::net::TcpStream, success: bool) -> Result<()> {
    let body = if success {
        include_str!("oauth_success.html")
    } else {
        include_str!("oauth_failure.html")
    };
    let status = if success { "200 OK" } else { "400 Bad Request" };
    let response = format!("HTTP/1.1 {status}\r\nContent-Type: text/html; charset=utf-8\r\nCache-Control: no-store, max-age=0\r\nPragma: no-cache\r\nReferrer-Policy: no-referrer\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nContent-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'\r\nContent-Length: {}\r\nConnection: close\r\n\r\n", body.len());
    stream.write_all(response.as_bytes())?;
    stream.write_all(body.as_bytes())?;
    Ok(())
}

/// Refresh under an OS file lock plus durable crash marker to avoid replay.
/// 使用操作系统文件锁和持久崩溃标记刷新，避免重放。
pub fn access_token(cfg: &Runtime) -> Result<String> {
    cfg.require_oauth()?;
    let _lock = token_lock(cfg)?;
    let conn = Connection::open(cfg.home.join("telemetry.sqlite3"))?;
    conn.busy_timeout(Duration::from_secs(30))?;
    conn.execute_batch("CREATE TABLE IF NOT EXISTS refresh_state (session_key TEXT PRIMARY KEY, in_progress INTEGER NOT NULL)")?;
    let key = format!("{}|{}", cfg.issuer, cfg.client_id);
    conn.execute(
        "INSERT OR IGNORE INTO refresh_state(session_key,in_progress) VALUES(?1,0)",
        [&key],
    )?;
    let in_progress: i64 = conn.query_row(
        "SELECT in_progress FROM refresh_state WHERE session_key=?1",
        [&key],
        |row| row.get(0),
    )?;
    if in_progress != 0 {
        // A prior process may have consumed the predecessor before crashing.
        // 先前进程可能在崩溃前消耗旧令牌。
        clear(cfg)?;
        conn.execute(
            "UPDATE refresh_state SET in_progress=0 WHERE session_key=?1",
            [&key],
        )?;
        bail!("previous refresh outcome unknown; local session cleared to prevent token-family replay");
    }
    let old = load(cfg)?;
    if old.expires_at > now().saturating_add(60) {
        return Ok(old.access_token);
    }
    let refresh = old
        .refresh_token
        .as_deref()
        .context("session expired; run `amail login`")?;
    let http = Client::builder().timeout(Duration::from_secs(20)).build()?;
    let d = discover(cfg, &http)?;
    conn.execute(
        "UPDATE refresh_state SET in_progress=1 WHERE session_key=?1",
        [&key],
    )?;
    let reply = http
        .post(&d.token_endpoint)
        .form(&[
            ("grant_type", "refresh_token"),
            ("client_id", cfg.client_id.as_str()),
            ("refresh_token", refresh),
        ])
        .send()
        .and_then(|r| r.error_for_status())
        .and_then(|r| r.json::<TokenReply>());
    let reply = match reply {
        Ok(reply) => reply,
        Err(err) => {
            // Unknown refresh outcome is not retried: the predecessor might already be consumed.
            // 刷新结果不明时不重试：旧令牌可能已经被消耗。
            clear(cfg)?;
            conn.execute(
                "UPDATE refresh_state SET in_progress=0 WHERE session_key=?1",
                [&key],
            )?;
            bail!("refresh outcome unknown; local session cleared to prevent replay: {err}");
        }
    };
    ensure!(
        reply.token_type.eq_ignore_ascii_case("Bearer"),
        "unexpected refreshed token type"
    );
    let new = Tokens {
        access_token: reply.access_token,
        refresh_token: reply.refresh_token,
        // A refresh ID token has no original login nonce; keep the previously validated one.
        // 刷新得到的 ID 令牌没有原登录 nonce，因此保留此前已校验的令牌。
        id_token: old.id_token,
        expires_at: now().saturating_add(reply.expires_in),
        subject: old.subject,
    };
    save(cfg, &new)?;
    conn.execute(
        "UPDATE refresh_state SET in_progress=0 WHERE session_key=?1",
        [&key],
    )?;
    Ok(new.access_token)
}

/// Clear local tokens regardless of remote logout availability.
/// 无论远端登出是否可用，都清除本地令牌。
pub fn logout(cfg: &Runtime) -> Result<()> {
    cfg.require_oauth()?;
    let _lock = token_lock(cfg)?;
    // Revocation and local deletion are distinct; local safety wins if the network fails.
    // 撤销与本地删除相互独立；网络失败时仍优先保证本地安全。
    if let Ok(tokens) = load(cfg) {
        if let Some(refresh) = tokens.refresh_token {
            if let Ok(http) = Client::builder().timeout(Duration::from_secs(8)).build() {
                if let Ok(d) = discover(cfg, &http) {
                    if let Some(endpoint) = d.revocation_endpoint {
                        let _ = http
                            .post(endpoint)
                            .form(&[
                                ("token", refresh.as_str()),
                                ("token_type_hint", "refresh_token"),
                                ("client_id", cfg.client_id.as_str()),
                            ])
                            .send();
                    }
                }
            }
        }
    }
    clear(cfg)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn config(issuer: &str) -> Runtime {
        Runtime {
            api_base: "https://mail.example.test".into(),
            issuer: issuer.into(),
            client_id: "amail-cli-test".into(),
            redirect_uri: "http://127.0.0.1/callback".into(),
            home: std::path::PathBuf::new(),
        }
    }

    fn tokens() -> Tokens {
        Tokens {
            access_token: "a".repeat(7000),
            refresh_token: Some("r".repeat(7000)),
            id_token: Some("i".repeat(7000)),
            expires_at: 42,
            subject: "private-subject".into(),
        }
    }

    /// Full-size tokens exceed Windows Credential Manager's short string limit.
    /// 完整令牌超过 Windows 凭据管理器短字符串限制，钥匙串值始终固定长度。
    #[test]
    fn keyring_value_stays_bounded() {
        let key = [7u8; 32];
        let value = format!("{KEY_PREFIX}{}", URL_SAFE_NO_PAD.encode(key));
        assert!(value.encode_utf16().count() < 2560);
        assert_eq!(parse_key(&value).unwrap(), Some(key));
        assert!(
            serde_json::to_string(&tokens())
                .unwrap()
                .encode_utf16()
                .count()
                > 2560
        );
    }

    #[test]
    fn seal_round_trip_and_reject_tampering_or_wrong_context() {
        let cfg = config("https://identity.example.test");
        let key = [3u8; 32];
        let original = tokens();
        let (nonce, mut ciphertext) = seal(&original, &key, &cfg).unwrap();
        assert_eq!(
            open(&nonce, &ciphertext, &key, &cfg).unwrap().subject,
            original.subject
        );
        assert!(open(&nonce, &ciphertext, &[4u8; 32], &cfg).is_err());
        assert!(open(
            &nonce,
            &ciphertext,
            &key,
            &config("https://other.example.test")
        )
        .is_err());
        ciphertext[0] ^= 1;
        assert!(open(&nonce, &ciphertext, &key, &cfg).is_err());
    }

    #[test]
    fn callback_line_accepts_fragmentation_and_rejects_incomplete_or_oversize() {
        struct OneByte<'a>(&'a [u8]);
        impl Read for OneByte<'_> {
            fn read(&mut self, buf: &mut [u8]) -> std::io::Result<usize> {
                if self.0.is_empty() {
                    return Ok(0);
                }
                buf[0] = self.0[0];
                self.0 = &self.0[1..];
                Ok(1)
            }
        }
        let mut split = OneByte(b"GET /callback?code=x HTTP/1.1\r\nHost: 127.0.0.1\r\n");
        assert_eq!(
            request_line(&mut split).unwrap(),
            "GET /callback?code=x HTTP/1.1"
        );
        assert!(request_line(&mut OneByte(b"GET /callback")).is_err());
        assert!(request_line(&mut OneByte(&vec![b'a'; 8193])).is_err());
    }
}
