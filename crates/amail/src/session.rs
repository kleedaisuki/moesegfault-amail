//! Daemon-owned cloud capabilities, scoped to the current terminal operation.

use crate::{
    api, auth,
    config::Runtime,
    machine,
    profiles::{ActiveProfile, Store},
};
use anyhow::{ensure, Context, Result};
use reqwest::Method;
use serde_json::{json, Value};
use std::{cell::RefCell, sync::Mutex};

#[derive(Clone)]
struct ContextData {
    terminal: String,
    profile: ActiveProfile,
    cloud: Option<String>,
}

thread_local! {
    static CURRENT: RefCell<Option<ContextData>> = const { RefCell::new(None) };
    static ACCOUNT: RefCell<Option<String>> = const { RefCell::new(None) };
}
static ENROLLMENT: Mutex<()> = Mutex::new(());

pub fn install(terminal: &str, profile: ActiveProfile) {
    CURRENT.with(|current| {
        *current.borrow_mut() = Some(ContextData {
            terminal: terminal.to_owned(),
            profile,
            cloud: None,
        })
    });
}

pub fn clear() {
    CURRENT.with(|current| *current.borrow_mut() = None);
    ACCOUNT.with(|account| *account.borrow_mut() = None);
}

pub fn set_account(cfg: &Runtime, subject: Option<&str>) {
    use sha2::{Digest, Sha256};
    ACCOUNT.with(|account| {
        *account.borrow_mut() = subject.map(|subject| {
            let identity =
                serde_json::to_vec(&(&cfg.api_base, &cfg.issuer, &cfg.client_id, subject))
                    .expect("serializing string tuple cannot fail");
            Sha256::digest(&identity)
                .iter()
                .map(|byte| format!("{byte:02x}"))
                .collect()
        })
    });
}

pub fn account_scope() -> Option<String> {
    ACCOUNT.with(|account| account.borrow().clone())
}

pub fn local_profile_scope() -> Option<(String, String)> {
    CURRENT.with(|current| {
        current
            .borrow()
            .as_ref()
            .map(|current| (current.profile.id.clone(), current.profile.name.clone()))
    })
}

fn context() -> Result<ContextData> {
    CURRENT
        .with(|current| current.borrow().clone())
        .context("no active daemon profile")
}

fn now() -> i64 {
    chrono::Utc::now().timestamp()
}

fn cloud_request(cfg: &Runtime, path: &str, body: &Value, session: Option<&str>) -> Result<Value> {
    cloud_request_method(cfg, Method::POST, path, body, session)
}

fn cloud_request_method(
    cfg: &Runtime,
    method: Method,
    path: &str,
    body: &Value,
    session: Option<&str>,
) -> Result<Value> {
    let token = auth::access_token(cfg)?;
    let mut request = api::shared_http()?
        .request(method.clone(), format!("{}{path}", cfg.api_base))
        .bearer_auth(token)
        .header("x-amail-api-version", "2");
    if method != Method::GET {
        request = request.json(body);
    }
    if let Some(session) = session {
        request = request.header("x-amail-profile-session", session);
    }
    let response = request.send().map_err(|_| machine::Failure {
        code: "profile_transport_unknown",
        next_action: "inspect_state",
        data: json!({}),
        message: "cloud profile request outcome is unknown; inspect state before retrying".into(),
    })?;
    let status = response.status();
    let result: Value = response.json().context("invalid cloud profile response")?;
    if !status.is_success() {
        let code = result
            .get("code")
            .or_else(|| result.get("error"))
            .and_then(Value::as_str)
            .unwrap_or("profile_request_failed");
        let code = match code {
            "profile_not_registered" => "profile_not_registered",
            "profile_in_use" => "profile_in_use",
            "profile_session_expired" => "profile_session_expired",
            "profile_exists_or_limit" => "profile_exists_or_limit",
            "mailbox_in_use" => "mailbox_in_use",
            "mailbox_lease_expired" => "mailbox_lease_expired",
            _ => "profile_request_failed",
        };
        return Err(machine::Failure {
            code,
            next_action: "inspect_state",
            data: json!({"status":status.as_u16()}),
            message: format!("cloud request rejected: {code}"),
        }
        .into());
    }
    Ok(result)
}

fn token(cfg: &Runtime) -> Result<String> {
    let current = context()?;
    if let Some(token) = current.cloud {
        return Ok(token);
    }
    let _guard = ENROLLMENT
        .lock()
        .map_err(|_| anyhow::anyhow!("profile enrollment lock unavailable"))?;
    let mut store = Store::open(cfg)?;
    let cached = store.cloud_session(&current.profile.id)?;
    let token = if let Some(cached) = cached
        .as_ref()
        .filter(|cached| cached.expires_at > now() + 300)
    {
        cached.session_token.clone()
    } else {
        let result = cloud_request(
            cfg,
            "/v1/profiles/activate",
            &json!({
                "name":current.profile.name,"terminal_id":current.terminal,
                "session_token":cached.as_ref().map(|session| &session.session_token),
            }),
            None,
        )?;
        let profile_id = result
            .get("profile_id")
            .and_then(Value::as_str)
            .context("cloud activation missing profile identity")?;
        let token = result
            .get("session_token")
            .and_then(Value::as_str)
            .context("cloud activation missing session capability")?;
        let expires = result
            .get("expires_at")
            .and_then(Value::as_i64)
            .context("cloud activation missing expiry")?;
        ensure!(
            uuid::Uuid::parse_str(profile_id).is_ok() && uuid::Uuid::parse_str(token).is_ok(),
            "invalid cloud profile identity"
        );
        store.set_cloud_session(&current.profile.id, profile_id, token, expires)?;
        token.to_owned()
    };
    CURRENT.with(|context| {
        if let Some(current) = context.borrow_mut().as_mut() {
            current.cloud = Some(token.clone());
        }
    });
    Ok(token)
}

/// Tests and the legacy diagnostic worker have no mail-operation context.
pub fn request_session(
    cfg: &Runtime,
    _method: &Method,
    _path: &str,
    _json: Option<&Value>,
    _zip: Option<&[u8]>,
) -> Result<Option<String>> {
    if CURRENT.with(|current| current.borrow().is_none()) {
        return Ok(None);
    }
    let current = context()?;
    let active = Store::open(cfg)?.active(&current.terminal)?;
    ensure!(
        active
            .as_ref()
            .is_some_and(|profile| profile.id == current.profile.id),
        "profile_session_changed: the terminal no longer has this profile active"
    );
    token(cfg).map(Some)
}

pub fn create_cloud(cfg: &Runtime, name: &str, durable: bool) -> Result<()> {
    let token = token(cfg)?;
    cloud_request(
        cfg,
        "/v1/profiles",
        &json!({"name":name,"durable":durable}),
        Some(&token),
    )?;
    Ok(())
}

pub fn activate_cloud(cfg: &Runtime) -> Result<()> {
    token(cfg)?;
    Ok(())
}

pub struct Registration {
    pub durable: bool,
    pub profile_id: String,
    pub token: String,
    pub expires_at: i64,
}

/// Passwordless activation can discover an existing cloud profile on a new host.
pub fn discover(cfg: &Runtime, name: &str, terminal: &str) -> Result<Registration> {
    let reply = cloud_request(
        cfg,
        "/v1/profiles/activate",
        &json!({"name":name,"terminal_id":terminal}),
        None,
    )?;
    let token = reply
        .get("session_token")
        .and_then(Value::as_str)
        .context("cloud activation missing session capability")?;
    let list = cloud_request_method(cfg, Method::GET, "/v1/profiles", &json!({}), Some(token))?;
    let row = list
        .get("profiles")
        .and_then(Value::as_array)
        .and_then(|profiles| {
            profiles
                .iter()
                .find(|row| row.get("name").and_then(Value::as_str) == Some(name))
        })
        .context("activated cloud profile not listed")?;
    Ok(Registration {
        durable: row
            .get("durable")
            .and_then(Value::as_bool)
            .or_else(|| {
                row.get("durable")
                    .and_then(Value::as_i64)
                    .map(|number| number != 0)
            })
            .unwrap_or(false),
        profile_id: reply
            .get("profile_id")
            .and_then(Value::as_str)
            .context("cloud profile identity missing")?
            .to_owned(),
        token: token.to_owned(),
        expires_at: reply
            .get("expires_at")
            .and_then(Value::as_i64)
            .context("cloud profile expiry missing")?,
    })
}

pub fn list_cloud(cfg: &Runtime) -> Result<Value> {
    let token = token(cfg)?;
    cloud_request_method(cfg, Method::GET, "/v1/profiles", &json!({}), Some(&token))
}

/// Coalesce activity-driven renewal; idle daemons never keep profiles alive.
pub fn touch_existing_cloud(cfg: &Runtime) -> Result<()> {
    let current = context()?;
    let cached = Store::open(cfg)?.cloud_session(&current.profile.id)?;
    if cached.is_some_and(|cached| cached.expires_at <= now() + 300) {
        token(cfg)?;
    }
    Ok(())
}

pub fn release_cloud(cfg: &Runtime, profile: &ActiveProfile) -> Result<()> {
    let store = Store::open(cfg)?;
    if let Some(session) = store.cloud_session(&profile.id)? {
        if let Err(error) = cloud_request(
            cfg,
            "/v1/profiles/release",
            &json!({}),
            Some(&session.session_token),
        ) {
            if !error
                .downcast_ref::<machine::Failure>()
                .is_some_and(|failure| failure.code == "profile_session_expired")
            {
                return Err(error);
            }
        }
    }
    Ok(())
}

pub fn acquire(cfg: &Runtime, address: &str, mode: &str) -> Result<Value> {
    let current = context()?;
    let token = token(cfg)?;
    let result = cloud_request(
        cfg,
        "/v1/leases/acquire",
        &json!({"address":address,"mode":mode}),
        Some(&token),
    )?;
    let lease_token = result
        .get("lease_token")
        .and_then(Value::as_str)
        .context("cloud lease missing capability")?;
    let generation = result
        .get("generation")
        .and_then(Value::as_str)
        .context("cloud lease missing generation")?;
    let held_mode = result
        .get("mode")
        .and_then(Value::as_str)
        .context("cloud lease missing mode")?;
    Store::open(cfg)?.set_lease(
        &current.profile.id,
        address,
        lease_token,
        generation,
        held_mode,
    )?;
    let mut public = result;
    public
        .as_object_mut()
        .context("invalid cloud lease")?
        .remove("lease_token");
    Ok(public)
}

pub fn release_mailbox(cfg: &Runtime, address: &str) -> Result<Value> {
    let current = context()?;
    let mut store = Store::open(cfg)?;
    let lease = match store.lease(&current.profile.id, address)? {
        Some(lease) => lease,
        None => {
            acquire(cfg, address, "read")?;
            store
                .lease(&current.profile.id, address)?
                .context("cloud mailbox capability was not persisted")?
        }
    };
    let lease_token = lease
        .get("lease_token")
        .and_then(Value::as_str)
        .context("missing local lease capability")?;
    let token = token(cfg)?;
    let result = cloud_request(
        cfg,
        "/v1/leases/release",
        &json!({"address":address,"token":lease_token}),
        Some(&token),
    )?;
    store.remove_lease(&current.profile.id, address)?;
    Ok(result)
}
