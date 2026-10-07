//! Human-authorized billing sessions; the CLI never approves payment or budget changes.
//!
//! Start with `amail billing status`. For a human-requested upgrade, preserve a UUID
//! and run `amail billing subscribe plus --idempotency-key UUID`. The command opens
//! the system browser and returns immediately; only its human user may authorize.
//! Use `--no-browser` for manual URL handoff, or resume `amail billing session UUID`
//! after interruption. Reuse the creation key after an uncertain create response;
//! never replace it merely because HTTP or polling timed out.
//!
//! A completed session proves authorization completion, not payment settlement.
//! Read authoritative effective resources and currency-labeled integer micros (current USD; historical CNY) from billing status.
use crate::{api::Api, emit, machine};
use anyhow::{ensure, Context, Result};
use clap::{Subcommand, ValueEnum};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::time::{Duration, Instant};

/// Subscription identifiers are closed and independent of display names.
#[derive(Clone, Copy, Debug, Serialize, ValueEnum)]
#[serde(rename_all = "lowercase")]
pub enum Plan {
    /// Community allowance with optional human-authorized overage.
    Free,
    /// Small prepaid resource bundle.
    Lite,
    /// Larger prepaid resource bundle.
    Plus,
}

/// Agent-facing operations; financial consent remains exclusively in the browser.
#[derive(Subcommand)]
pub enum Command {
    /// Read effective plan, usage, budget, and settlement state.
    Status,
    /// Request a plan change; only the human browser can authorize it.
    Subscribe {
        /// Suggested plan only; the human makes the final browser choice.
        plan: Plan,
        /// Reuse this UUID after any uncertain session-creation response.
        #[arg(long, value_parser = canonical_uuid)]
        idempotency_key: Option<uuid::Uuid>,
        /// Print the safe authorization URL instead of opening the system browser.
        #[arg(long)]
        no_browser: bool,
        /// Wait for human authorization, at most 900 seconds; default returns immediately.
        #[arg(long, default_value_t = 0, value_parser = clap::value_parser!(u64).range(0..=900))]
        wait_seconds: u64,
    },
    /// Open human-only billing management, including spending limits and cancellation.
    Manage {
        /// Reuse this UUID after an uncertain session-creation response.
        #[arg(long, value_parser = canonical_uuid)]
        idempotency_key: Option<uuid::Uuid>,
        #[arg(long)]
        no_browser: bool,
        #[arg(long, default_value_t = 0, value_parser = clap::value_parser!(u64).range(0..=900))]
        wait_seconds: u64,
    },
    /// Resume an existing session without creating another financial action.
    Session {
        /// Owner-scoped handle previously returned by the server.
        #[arg(value_parser = canonical_uuid)]
        id: uuid::Uuid,
        #[arg(long, default_value_t = 0, value_parser = clap::value_parser!(u64).range(0..=900))]
        wait_seconds: u64,
    },
}

/// Match the backend UUID v4 grammar without reflecting invalid caller input.
fn canonical_uuid(raw: &str) -> std::result::Result<uuid::Uuid, &'static str> {
    let id = uuid::Uuid::parse_str(raw).map_err(|_| "expected a canonical UUID v4")?;
    if id.get_version_num() != 4 || id.hyphenated().to_string() != raw {
        return Err("expected a canonical UUID v4");
    }
    Ok(id)
}

/// Closed server session states: completion is authorization, not proof of payment.
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "lowercase")]
enum State {
    /// Human consent has not completed; this is not a charge.
    Pending,
    /// Human authorization completed; inspect billing status for effective resources.
    Completed,
    /// The human declined or cancelled the authorization.
    Cancelled,
    /// The server authorization window elapsed.
    Expired,
    /// The server conclusively failed this authorization attempt.
    Failed,
}

/// Only safe, known browser-navigation metadata is decoded from session responses.
#[derive(Deserialize)]
struct Session {
    /// Owner-scoped continuation handle, never a credential.
    session_id: String,
    /// Server-owned financial authorization state.
    state: State,
    /// Optional only on create/pending replies; never accepted from untrusted mail.
    authorization_url: Option<String>,
    /// Server retry hint, bounded locally even if the response is faulty.
    retry_after_ms: Option<u64>,
}

/// Reject credentials, query strings, fragments, insecure schemes and cross-path tricks.
fn authorization_url(value: &str) -> Result<url::Url> {
    let url = url::Url::parse(value).context("invalid billing authorization URL")?;
    ensure!(
        url.scheme() == "https"
            && url.host_str().is_some()
            && url.username().is_empty()
            && url.password().is_none()
            && url.query().is_none()
            && url.fragment().is_none(),
        "billing authorization URL must be credential-free HTTPS without query or fragment"
    );
    Ok(url)
}

/// Parse without reflecting server content into errors or logs.
fn session(value: &Value, expected: Option<uuid::Uuid>) -> Result<Session> {
    let result: Session = serde_json::from_value(value.clone())
        .map_err(|_| anyhow::anyhow!("invalid billing session response"))?;
    let id = uuid::Uuid::parse_str(&result.session_id)
        .map_err(|_| anyhow::anyhow!("invalid billing session ID"))?;
    ensure!(
        id.hyphenated().to_string() == result.session_id,
        "noncanonical billing session ID"
    );
    ensure!(
        expected.is_none_or(|expected| expected == id),
        "billing session ID mismatch"
    );
    Ok(result)
}

/// Emit a closed session projection, not arbitrary server fields or payment claims.
fn output(value: &Session, url: Option<&url::Url>, human: bool) -> Result<()> {
    let mut body = json!({"session_id":value.session_id,"state":value.state,
        "next_action":if value.state == State::Pending {"human_authorize_or_resume_billing_session"} else {"query_billing_status"}});
    if let Some(url) = url {
        body["authorization_url"] = json!(url.as_str());
    }
    emit(&body, human)
}

/// Poll an owner-scoped handle only; timeout never means expired or failed.
fn poll(api: &Api<'_>, mut current: Session, wait_seconds: u64, human: bool) -> Result<()> {
    let deadline = Instant::now() + Duration::from_secs(wait_seconds);
    let id = uuid::Uuid::parse_str(&current.session_id)?;
    while current.state == State::Pending && Instant::now() < deadline {
        let delay = Duration::from_millis(current.retry_after_ms.unwrap_or(1000).clamp(500, 5000));
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining < delay {
            break;
        }
        std::thread::sleep(delay);
        current = session(&api.billing_session(&id)?, Some(id))?;
    }
    output(&current, None, human)
}

/// Print the stable creation key before the request so uncertain outcomes are recoverable.
fn create(
    api: &Api<'_>,
    plan: Option<Plan>,
    key: Option<uuid::Uuid>,
    no_browser: bool,
    wait_seconds: u64,
    human: bool,
) -> Result<()> {
    let key = key.unwrap_or_else(uuid::Uuid::new_v4);
    emit(
        &json!({"idempotency_key":key.to_string(),"next_action":"reuse_key_if_billing_session_creation_is_uncertain"}),
        human,
    )?;
    let mut body = json!({"action":if plan.is_some() {"subscribe"} else {"manage"}});
    if let Some(plan) = plan {
        body["plan"] = serde_json::to_value(plan)?;
    }
    let response = api.create_billing_session(&body, &key)?;
    let current = session(&response, None).map_err(|_| machine::Failure {
        code: "billing_session_response_invalid",
        next_action: "reuse_billing_session_key",
        data: json!({"idempotency_key":key.to_string()}),
        message: "Billing session response invalid; reuse the same creation key".to_owned(),
    })?;
    let url = current
        .authorization_url
        .as_deref()
        .map(authorization_url)
        .transpose()?;
    ensure!(
        current.state != State::Pending || url.is_some(),
        "pending billing session missing authorization URL"
    );
    output(&current, url.as_ref(), human)?;
    machine::event(
        "billing_session",
        json!({"session_id":current.session_id,"state":current.state,"next_action":"human_authorize_or_resume_billing_session"}),
    );
    if !no_browser && current.state == State::Pending {
        if webbrowser::open(url.as_ref().unwrap().as_str()).is_err() {
            machine::event(
                "billing_browser_unavailable",
                json!({"next_action":"open_authorization_url_manually"}),
            );
        }
    }
    if wait_seconds > 0 {
        poll(api, current, wait_seconds, human)?;
    }
    Ok(())
}

/// Run financial navigation without an agent-side approval endpoint.
pub fn run(api: &Api<'_>, command: Command, human: bool) -> Result<()> {
    match command {
        Command::Status => emit(&api.billing_status()?, human),
        Command::Subscribe {
            plan,
            idempotency_key,
            no_browser,
            wait_seconds,
        } => create(
            api,
            Some(plan),
            idempotency_key,
            no_browser,
            wait_seconds,
            human,
        ),
        Command::Manage {
            idempotency_key,
            no_browser,
            wait_seconds,
        } => create(api, None, idempotency_key, no_browser, wait_seconds, human),
        Command::Session { id, wait_seconds } => {
            let current = session(&api.billing_session(&id)?, Some(id))?;
            poll(api, current, wait_seconds, human)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn authorization_links_exclude_credentials_and_private_query_data() {
        assert!(authorization_url("https://billing.example/authorize/session-handle").is_ok());
        for value in [
            "http://billing.example/path",
            "https://secret@billing.example/path",
            "https://billing.example/path?code=private",
            "https://billing.example/#token",
            "javascript:alert(1)",
        ] {
            assert!(authorization_url(value).is_err());
        }
    }
    #[test]
    fn session_state_and_owner_handle_are_closed() {
        let id = uuid::Uuid::new_v4();
        let value = json!({"session_id":id.to_string(),"state":"pending","retry_after_ms":1});
        assert_eq!(session(&value, Some(id)).unwrap().state, State::Pending);
        assert!(session(&value, Some(uuid::Uuid::new_v4())).is_err());
        for state in ["paid", "approved", "unknown"] {
            assert!(session(&json!({"session_id":id.to_string(),"state":state}), None).is_err());
        }
        for state in ["completed", "cancelled", "expired", "failed"] {
            assert!(session(
                &json!({"session_id":id.to_string(),"state":state}),
                Some(id)
            )
            .is_ok());
        }
    }
}
