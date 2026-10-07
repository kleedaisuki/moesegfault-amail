//! Opt-in structured stderr boundaries; private error prose never enters machine records.
use serde_json::{json, Value};
use std::sync::atomic::{AtomicBool, Ordering};
static ENABLED: AtomicBool = AtomicBool::new(false);

/// Configure once before parsing/runtime work so failures have the requested format.
pub fn enable(value: bool) {
    ENABLED.store(value, Ordering::Relaxed);
}
/// Recognize an explicitly requested flag, never a positional value after `--`.
pub fn requested(args: impl IntoIterator<Item = std::ffi::OsString>) -> bool {
    args.into_iter()
        .take_while(|arg| arg != "--")
        .any(|arg| arg == "--machine")
}
/// Whether structured stderr was explicitly requested.
pub fn enabled() -> bool {
    ENABLED.load(Ordering::Relaxed)
}
/// Emit one versioned record on stderr, preserving stdout's established contract.
pub fn event(kind: &str, data: Value) {
    if enabled() {
        eprintln!(
            "{}",
            json!({"schema":"amail.machine.v1","event":kind,"data":data})
        );
    }
}

/// A local/auth/continuation failure with a safe, actionable machine discriminator.
#[derive(Debug)]
pub struct Failure {
    /// Stable category independent of human error wording.
    pub code: &'static str,
    /// Required recovery action; not a generic retry boolean.
    pub next_action: &'static str,
    /// Safe continuation fields (never body, filters or credentials).
    pub data: Value,
    /// Preserved human-facing explanation.
    pub message: String,
}
impl std::fmt::Display for Failure {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.message)
    }
}
impl std::error::Error for Failure {}

/// Turn a locally detected contract violation into an actionable input failure.
pub fn invalid_input(message: &str) -> anyhow::Error {
    Failure {
        code: "invalid_input",
        next_action: "fix_input",
        data: json!({}),
        message: message.to_owned(),
    }
    .into()
}

/// Render typed failures and conservative unknown local errors without string guessing.
pub fn error_record(error: &anyhow::Error) -> Value {
    if let Some(failure) = error.downcast_ref::<Failure>() {
        return json!({"code":failure.code,"next_action":failure.next_action,"details":failure.data});
    }
    if let Some(failure) = error.downcast_ref::<crate::api::ApiFailure>() {
        let action = match failure.code.as_str() {
            "search_job_stale"
            | "search_job_expired"
            | "search_cursor_stale"
            | "search_cursor_expired"
            | "search_cursor_vector_changed" => "restart_search",
            "events_cursor_expired" => "restart_events",
            "required_client_version" => "upgrade_client",
            "invalid_billing_plan"
            | "invalid_billing_action"
            | "invalid_idempotency_key"
            | "idempotency_key_required" => "fix_input",
            "idempotency_conflict" | "billing_plan_invalid" | "billing_snapshot_invalid" => "stop",
            "outbound_quota_exhausted" | "resource_budget_exceeded" => "inspect_billing_status",
            "billing_unavailable" if failure.operation == "billing.session.create" => {
                "reuse_billing_session_key"
            }
            "billing_unavailable" if failure.operation == "billing.session.status" => {
                "resume_billing_session"
            }
            "billing_unavailable" => "retry_later",
            "send_held"
            | "recipient_suppressed"
            | "recipient_not_allowed"
            | "recipient_rejected"
            | "recipient_blocked"
            | "capacity_exhausted"
            | "not_found"
            | "forbidden" => "stop",
            "quota_exhausted" | "provider_rate_limited" | "provider_daily_limit" => "retry_later",
            "send_in_progress" | "send_outcome_unknown" | "send_unknown" | "send_index_pending" => {
                "query_send_status"
            }
            _ if failure.status.as_u16() == 426 => "upgrade_client",
            _ if failure.status.as_u16() == 401 => "login",
            _ if failure.operation == "billing.session.create"
                && failure.status.is_server_error() =>
            {
                "reuse_billing_session_key"
            }
            _ if failure.status.as_u16() == 429 => "retry_later",
            _ if failure.operation == "messages.send" && failure.status.is_server_error() => {
                "query_send_status"
            }
            _ if failure.status.is_client_error() => "fix_input",
            _ => "stop",
        };
        let code = if failure.code.len() <= 64
            && failure
                .code
                .bytes()
                .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_')
        {
            failure.code.as_str()
        } else {
            "http_error"
        };
        return json!({"code":code,"http_status":failure.status.as_u16(),"request_id":failure.request_id,"next_action":action});
    }
    json!({"code":"local_error","next_action":"inspect_local"})
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn machine_flag_is_not_a_positional_value() {
        let args = |values: &[&str]| {
            values
                .iter()
                .map(|value| std::ffi::OsString::from(*value))
                .collect::<Vec<_>>()
        };
        assert!(requested(args(&["amail", "--machine", "discover"])));
        assert!(requested(args(&["amail", "events", "--machine"])));
        assert!(!requested(args(&["amail", "get", "--", "--machine"])));
    }
    #[test]
    fn api_actions_and_codes_are_safe() {
        for (code, status, expected) in [
            ("search_cursor_vector_changed", 409, "restart_search"),
            ("events_cursor_expired", 410, "restart_events"),
            ("send_held", 503, "stop"),
            ("recipient_blocked", 403, "stop"),
            ("capacity_exhausted", 409, "stop"),
            ("quota_exhausted", 429, "retry_later"),
            ("send_outcome_unknown", 409, "query_send_status"),
            ("send_index_pending", 503, "query_send_status"),
            ("unauthorized", 401, "login"),
            ("client_upgrade_required", 426, "upgrade_client"),
            ("not_found", 404, "stop"),
            ("provider private\ntext", 500, "stop"),
        ] {
            let error: anyhow::Error = crate::api::ApiFailure {
                status: reqwest::StatusCode::from_u16(status).unwrap(),
                code: code.into(),
                request_id: None,
                operation: "messages.list".into(),
                message: "private prose".into(),
            }
            .into();
            let value = error_record(&error);
            assert_eq!(value["next_action"], expected);
            assert!(!value.to_string().contains("private"));
        }
    }
    #[test]
    fn send_server_failure_requires_reconciliation_not_resubmission() {
        let error: anyhow::Error = crate::api::ApiFailure {
            status: reqwest::StatusCode::INTERNAL_SERVER_ERROR,
            code: "internal_error".into(),
            request_id: None,
            operation: "messages.send".into(),
            message: "safe".into(),
        }
        .into();
        assert_eq!(error_record(&error)["next_action"], "query_send_status");
    }
    #[test]
    fn uncertain_billing_creation_reuses_original_key() {
        let error: anyhow::Error = crate::api::ApiFailure {
            status: reqwest::StatusCode::BAD_GATEWAY,
            code: "billing_unavailable".into(),
            request_id: None,
            operation: "billing.session.create".into(),
            message: "private provider prose".into(),
        }
        .into();
        assert_eq!(
            error_record(&error)["next_action"],
            "reuse_billing_session_key"
        );
        assert!(!error_record(&error).to_string().contains("private"));
    }
    #[test]
    fn billing_and_resource_failures_never_grant_financial_authority() {
        for (code, status, operation, action) in [
            (
                "invalid_billing_plan",
                400,
                "billing.session.create",
                "fix_input",
            ),
            (
                "invalid_billing_action",
                400,
                "billing.session.create",
                "fix_input",
            ),
            (
                "invalid_idempotency_key",
                400,
                "billing.session.create",
                "fix_input",
            ),
            (
                "idempotency_key_required",
                400,
                "billing.session.create",
                "fix_input",
            ),
            (
                "idempotency_conflict",
                409,
                "billing.session.create",
                "stop",
            ),
            (
                "billing_unavailable",
                503,
                "billing.session.create",
                "reuse_billing_session_key",
            ),
            (
                "billing_unavailable",
                503,
                "billing.session.status",
                "resume_billing_session",
            ),
            ("billing_unavailable", 503, "billing.status", "retry_later"),
            (
                "outbound_quota_exhausted",
                429,
                "messages.send",
                "inspect_billing_status",
            ),
            (
                "resource_budget_exceeded",
                429,
                "addresses.add",
                "inspect_billing_status",
            ),
            (
                "required_client_version",
                426,
                "billing.status",
                "upgrade_client",
            ),
            (
                "billing_snapshot_invalid",
                400,
                "billing.session.status",
                "stop",
            ),
        ] {
            let error: anyhow::Error = crate::api::ApiFailure {
                status: reqwest::StatusCode::from_u16(status).unwrap(),
                code: code.into(),
                request_id: None,
                operation: operation.into(),
                message: "private provider prose".into(),
            }
            .into();
            let record = error_record(&error);
            assert_eq!(record["next_action"], action, "{code} for {operation}");
            assert!(!record.to_string().contains("private"));
        }
    }
    #[test]
    fn continuation_and_auth_are_typed_without_private_error_prose() {
        let failure: anyhow::Error = Failure {
            code: "search_running",
            next_action: "resume_search",
            data: json!({"job_id":"safe-uuid"}),
            message: "private human text".into(),
        }
        .into();
        let value = error_record(&failure.context("additional private context"));
        assert_eq!(value["next_action"], "resume_search");
        assert_eq!(value["details"]["job_id"], "safe-uuid");
        assert!(!value.to_string().contains("private"));
        assert_eq!(
            error_record(&anyhow::anyhow!("private local path"))["code"],
            "local_error"
        );
    }
}
