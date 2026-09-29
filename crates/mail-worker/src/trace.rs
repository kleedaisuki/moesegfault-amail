//! Allowlisted application trace events; no request-derived text enters retained logs.

use serde::Serialize;

/// Exact W3C version-00 context accepted only after a trusted boundary is crossed.
#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct Parent {
    trace_id: String,
    span_id: String,
    sampled: bool,
}

/// A fixed operation name, never copied from a URL or request body.
#[derive(Clone, Copy, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum Operation {
    Health,
    Inbound,
    AddressesList,
    AddressesAdd,
    AddressesDelete,
    MessagesList,
    MessagesSearch,
    SearchPoll,
    MessagesSend,
    MessagesGet,
    MessagesArchive,
    MessagesMark,
    MessagesDelete,
    TelemetryUpload,
    Unknown,
}

impl Operation {
    /// Map the historical CLI wire names into the same fixed operation vocabulary.
    pub(crate) fn from_cli(raw: &str) -> Option<Self> {
        Some(match raw {
            "addresses.list" => Self::AddressesList,
            "addresses.add" => Self::AddressesAdd,
            "addresses.delete" => Self::AddressesDelete,
            "messages.list" => Self::MessagesList,
            "messages.search" => Self::MessagesSearch,
            "messages.get" => Self::MessagesGet,
            "messages.archive" => Self::MessagesArchive,
            "messages.mark" => Self::MessagesMark,
            "messages.delete" => Self::MessagesDelete,
            "messages.send" => Self::MessagesSend,
            _ => return None,
        })
    }
}

/// An allowlisted outcome; arbitrary application or provider errors are excluded.
#[derive(Clone, Copy, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum Outcome {
    Success,
    ClientError,
    ServerError,
    PhaseFailure,
}

/// The only services permitted in retained application trace events.
#[derive(Clone, Copy, Serialize)]
#[serde(rename_all = "snake_case")]
enum Service {
    MailApi,
    MailCli,
}

/// A small, stable phase vocabulary rather than free-form span names.
#[derive(Clone, Copy, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum Phase {
    RequestExit,
    OperationExit,
    D1Read,
    D1Write,
    R2Write,
    ProviderSend,
    RoutingList,
    RoutingCreate,
}

/// Coarse failure reason; exception text and provider details are never retained.
#[derive(Clone, Copy, Serialize)]
#[serde(rename_all = "snake_case")]
enum ErrorCode {
    InvalidRequest,
    Unauthorized,
    Forbidden,
    NotFound,
    Conflict,
    RateLimited,
    ServiceUnavailable,
    OtherClient,
    OtherServer,
    DependencyFailure,
}

fn error_code(status: u16) -> Option<ErrorCode> {
    Some(match status {
        200..=399 => return None,
        400 => ErrorCode::InvalidRequest,
        401 => ErrorCode::Unauthorized,
        403 => ErrorCode::Forbidden,
        404 => ErrorCode::NotFound,
        409 => ErrorCode::Conflict,
        429 => ErrorCode::RateLimited,
        503 => ErrorCode::ServiceUnavailable,
        400..=499 => ErrorCode::OtherClient,
        _ => ErrorCode::OtherServer,
    })
}

/// Per-invocation span state, independent of the mail result.
pub(crate) struct Trace {
    trace_id: String,
    span_id: String,
    parent_span_id: Option<String>,
    sampled: bool,
    operation: Operation,
    request_bytes: Option<u64>,
}

/// The sole retained JSON schema. Adding a field requires a privacy review.
#[derive(Serialize)]
struct Event<'a> {
    schema_version: u8,
    service: Service,
    operation: Operation,
    phase: Phase,
    trace_id: &'a str,
    span_id: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    parent_span_id: Option<&'a str>,
    request_id: &'a str,
    outcome: Outcome,
    #[serde(skip_serializing_if = "Option::is_none")]
    error_code: Option<ErrorCode>,
    #[serde(skip_serializing_if = "Option::is_none")]
    http_status_class: Option<u16>,
    duration_ms_bucket: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    request_bytes_bucket: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    provider_http_status: Option<u16>,
    #[serde(skip_serializing_if = "Option::is_none")]
    provider_error_code: Option<u32>,
}

/// Client telemetry is a separate fixed schema; older rows may lack a span ID.
#[derive(Serialize)]
struct ClientEvent<'a> {
    schema_version: u8,
    service: Service,
    operation: Operation,
    phase: Phase,
    trace_id: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    span_id: Option<&'a str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    request_id: Option<&'a str>,
    outcome: Outcome,
    http_status_class: u16,
    duration_ms_bucket: u64,
    response_bytes_bucket: u64,
}

impl Trace {
    /// Create a fresh server span without inspecting any untrusted header.
    pub(crate) fn new() -> Self {
        Self {
            trace_id: uuid::Uuid::new_v4().simple().to_string(),
            span_id: random_span_id(),
            parent_span_id: None,
            sampled: true,
            operation: Operation::Unknown,
            request_bytes: None,
        }
    }

    /// Attach a strictly validated parent after authentication, never tracestate.
    pub(crate) fn accept_parent(&mut self, raw: Option<&str>) {
        let Some(parent) = raw.and_then(parse_parent) else {
            return;
        };
        self.trace_id = parent.trace_id;
        self.parent_span_id = Some(parent.span_id);
        self.sampled = parent.sampled;
    }

    /// Set an operation from a closed set rather than from a URL segment.
    pub(crate) fn operation(&mut self, operation: Operation) {
        self.operation = operation;
    }

    /// Record only a measured byte count, rounded to a power-of-two bucket.
    pub(crate) fn measured_request_bytes(&mut self, bytes: usize) {
        self.request_bytes = Some(bucket(bytes as u64));
    }

    /// Emit a best-effort bounded event, using a static fallback on serialization failure.
    pub(crate) fn exit(&self, request_id: &str, status: u16, duration_ms: u64) {
        let event = Event {
            schema_version: 1,
            service: Service::MailApi,
            operation: self.operation,
            phase: Phase::RequestExit,
            trace_id: &self.trace_id,
            span_id: &self.span_id,
            parent_span_id: self.parent_span_id.as_deref(),
            request_id,
            outcome: match status {
                200..=399 => Outcome::Success,
                400..=499 => Outcome::ClientError,
                _ => Outcome::ServerError,
            },
            error_code: error_code(status),
            http_status_class: Some(status / 100),
            duration_ms_bucket: bucket(duration_ms.min(3_600_000)),
            request_bytes_bucket: self.request_bytes,
            provider_http_status: None,
            provider_error_code: None,
        };
        emit(&event);
    }

    /// Emit one child phase span with only a fixed phase label and coarse outcome.
    pub(crate) fn phase(&self, request_id: &str, phase: Phase, success: bool, duration_ms: u64) {
        let span_id = random_span_id();
        emit(&self.phase_record(&span_id, request_id, phase, success, duration_ms));
    }

    /// Report only numeric Cloudflare Routing Rules POST facts, never its body.
    pub(crate) fn routing_create(
        &self,
        request_id: &str,
        success: bool,
        provider_http_status: Option<u16>,
        provider_error_code: Option<u32>,
        duration_ms: u64,
    ) {
        let span_id = random_span_id();
        emit(&self.routing_create_record(
            &span_id,
            request_id,
            success,
            provider_http_status,
            provider_error_code,
            duration_ms,
        ));
    }

    fn routing_create_record<'a>(
        &'a self,
        span_id: &'a str,
        request_id: &'a str,
        success: bool,
        provider_http_status: Option<u16>,
        provider_error_code: Option<u32>,
        duration_ms: u64,
    ) -> Event<'a> {
        let mut event = self.phase_record(
            span_id,
            request_id,
            Phase::RoutingCreate,
            success,
            duration_ms,
        );
        event.provider_http_status = provider_http_status;
        event.provider_error_code = provider_error_code;
        event
    }

    fn phase_record<'a>(
        &'a self,
        span_id: &'a str,
        request_id: &'a str,
        phase: Phase,
        success: bool,
        duration_ms: u64,
    ) -> Event<'a> {
        Event {
            schema_version: 1,
            service: Service::MailApi,
            operation: self.operation,
            phase,
            trace_id: &self.trace_id,
            span_id: &span_id,
            parent_span_id: Some(&self.span_id),
            request_id,
            outcome: if success {
                Outcome::Success
            } else {
                Outcome::PhaseFailure
            },
            error_code: if success {
                None
            } else {
                Some(ErrorCode::DependencyFailure)
            },
            http_status_class: None,
            duration_ms_bucket: bucket(duration_ms.min(3_600_000)),
            request_bytes_bucket: None,
            provider_http_status: None,
            provider_error_code: None,
        }
    }
}

/// Measure a bounded elapsed duration without treating wall-clock rollback as failure.
pub(crate) fn elapsed_ms(start: f64) -> u64 {
    (js_sys::Date::now() - start).max(0.0) as u64
}

fn emit(event: &Event<'_>) {
    match serde_json::to_string(event) {
        Ok(encoded) => worker::console_log!("{}", encoded),
        Err(_) => worker::console_warn!("amail trace event serialization failed"),
    }
}

/// Parse exact lower-case W3C v00 syntax with nonzero IDs and known flags.
pub(crate) fn parse_parent(raw: &str) -> Option<Parent> {
    let bytes = raw.as_bytes();
    if bytes.len() != 55
        || !bytes.is_ascii()
        || &bytes[..3] != b"00-"
        || bytes[35] != b'-'
        || bytes[52] != b'-'
    {
        return None;
    }
    let trace = &raw[3..35];
    let span = &raw[36..52];
    if !valid_hex_id(trace, 32) || !valid_hex_id(span, 16) || !matches!(&raw[53..], "00" | "01") {
        return None;
    }
    Some(Parent {
        trace_id: trace.to_owned(),
        span_id: span.to_owned(),
        sampled: &raw[53..] == "01",
    })
}

/// Validate only exact lower-case, nonzero correlation IDs.
pub(crate) fn valid_hex_id(id: &str, length: usize) -> bool {
    id.len() == length
        && id
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        && id.bytes().any(|byte| byte != b'0')
}

/// Emit a legacy-compatible CLI upload event without retaining caller text.
pub(crate) fn client_event(
    operation: Operation,
    trace_id: &str,
    span_id: Option<&str>,
    request_id: Option<&str>,
    status: u16,
    duration_ms: u64,
    response_bytes_bucket: u64,
) {
    let event = ClientEvent {
        schema_version: 1,
        service: Service::MailCli,
        operation,
        phase: Phase::OperationExit,
        trace_id,
        span_id,
        request_id: request_id.filter(|value| uuid::Uuid::parse_str(value).is_ok()),
        outcome: match status {
            200..=399 => Outcome::Success,
            400..=499 => Outcome::ClientError,
            _ => Outcome::ServerError,
        },
        http_status_class: status / 100,
        duration_ms_bucket: bucket(duration_ms.min(3_600_000)),
        response_bytes_bucket: bucket(response_bytes_bucket),
    };
    match serde_json::to_string(&event) {
        Ok(encoded) => worker::console_log!("{}", encoded),
        Err(_) => worker::console_warn!("amail client trace serialization failed"),
    }
}

fn random_span_id() -> String {
    let id = uuid::Uuid::new_v4().simple().to_string();
    id[..16].to_owned()
}

fn bucket(value: u64) -> u64 {
    if value == 0 {
        0
    } else {
        1u64 << (64 - (value - 1).leading_zeros()).min(32)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Valid context retains causal identity without copying arbitrary headers.
    #[test]
    fn strict_w3c_parent() {
        let raw = "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01";
        let parent = parse_parent(raw).unwrap();
        assert_eq!(parent.trace_id, "0123456789abcdef0123456789abcdef");
        assert_eq!(parent.span_id, "0123456789abcdef");
        assert!(parent.sampled);
        for bad in [
            "00-00000000000000000000000000000000-0123456789abcdef-01",
            "00-0123456789abcdef0123456789abcdef-0000000000000000-01",
            "00-0123456789ABCDEF0123456789abcdef-0123456789abcdef-01",
            "00-0123456789abcdef0123456789abcdef-0123456789abcdef-03",
            "00-0123456789abcdef0123456789abcdef-0123456789abcdé-01",
            "01-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
            "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01-extra",
        ] {
            assert!(parse_parent(bad).is_none(), "accepted invalid parent");
        }
    }

    /// Event serialization is a fixed schema with no user-controlled attributes.
    #[test]
    fn event_is_allowlisted() {
        let mut trace = Trace::new();
        trace.accept_parent(Some(
            "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
        ));
        trace.operation(Operation::MessagesSend);
        let event = Event {
            schema_version: 1,
            service: Service::MailApi,
            operation: trace.operation,
            phase: Phase::RequestExit,
            trace_id: &trace.trace_id,
            span_id: &trace.span_id,
            parent_span_id: trace.parent_span_id.as_deref(),
            request_id: "00000000-0000-4000-8000-000000000001",
            outcome: Outcome::Success,
            error_code: None,
            http_status_class: Some(2),
            duration_ms_bucket: 8,
            request_bytes_bucket: None,
            provider_http_status: None,
            provider_error_code: None,
        };
        let value = serde_json::to_value(event).unwrap();
        assert_eq!(value.as_object().unwrap().len(), 11);
        assert_eq!(value["parent_span_id"], "0123456789abcdef");
        assert!(value.get("url").is_none());
        assert!(value.get("tracestate").is_none());
    }

    /// A dependency phase has its own ID and points to the request span, not the CLI span.
    #[test]
    fn phase_span_has_server_parent() {
        let mut trace = Trace::new();
        trace.accept_parent(Some(
            "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
        ));
        trace.operation(Operation::Inbound);
        let span_id = "abcdef0123456789";
        let event = trace.phase_record(
            span_id,
            "00000000-0000-4000-8000-000000000001",
            Phase::R2Write,
            false,
            17,
        );
        let value = serde_json::to_value(event).unwrap();
        assert_eq!(value["span_id"], span_id);
        assert_eq!(value["parent_span_id"], trace.span_id);
        assert_ne!(value["parent_span_id"], "0123456789abcdef");
        assert_eq!(value["phase"], "r2_write");
        assert_eq!(value["error_code"], "dependency_failure");
        assert!(value.get("http_status_class").is_none());
    }

    /// Routing diagnostics expose numeric provider facts under the normal trace IDs only.
    #[test]
    fn routing_create_event_has_no_provider_text_slot() {
        let mut trace = Trace::new();
        trace.operation(Operation::AddressesAdd);
        let event = trace.routing_create_record(
            "abcdef0123456789",
            "00000000-0000-4000-8000-000000000001",
            false,
            Some(403),
            Some(10000),
            3,
        );
        let value = serde_json::to_value(event).unwrap();
        assert_eq!(value["phase"], "routing_create");
        assert_eq!(value["provider_http_status"], 403);
        assert_eq!(value["provider_error_code"], 10000);
        assert_eq!(value["parent_span_id"], trace.span_id);
        assert!(value.get("body").is_none());
        assert!(value.get("address").is_none());
        assert!(value.get("provider_message").is_none());
    }
}
