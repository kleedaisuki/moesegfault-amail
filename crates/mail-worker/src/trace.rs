//! Allowlisted application trace events; no request-derived text enters retained logs.

use amail_trace_schema::Event as QueuedEvent;
use amail_trace_schema::{ClientAttempt, ClientErrorKind, ClientPhase};
pub(crate) use amail_trace_schema::{DiagnosticCode, Operation, Phase};
use amail_trace_schema::{ErrorCode, Outcome, Service};
use serde::Serialize;
use std::cell::RefCell;

/// Exact W3C version-00 context accepted only after a trusted boundary is crossed.
#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct Parent {
    trace_id: String,
    span_id: String,
    sampled: bool,
}

/// Map historical CLI wire names into the fixed operation vocabulary.
pub(crate) fn operation_from_cli(raw: &str) -> Option<Operation> {
    Some(match raw {
        "addresses.list" => Operation::AddressesList,
        "addresses.add" => Operation::AddressesAdd,
        "addresses.delete" => Operation::AddressesDelete,
        "messages.list" => Operation::MessagesList,
        "messages.search" => Operation::MessagesSearch,
        "messages.search.poll" => Operation::SearchPoll,
        "messages.get" => Operation::MessagesGet,
        "messages.archive" => Operation::MessagesArchive,
        "messages.mark" => Operation::MessagesMark,
        "messages.delete" => Operation::MessagesDelete,
        "messages.send" => Operation::MessagesSend,
        "billing.status" => Operation::BillingStatus,
        "billing.session.create" => Operation::BillingSessionCreate,
        "billing.session.status" => Operation::BillingSessionStatus,
        _ => return None,
    })
}

fn error_code(status: u16) -> Option<ErrorCode> {
    Some(match status {
        100..=399 => return None,
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
    /// Invocation-owned safe records; no global request state.
    events: RefCell<Vec<QueuedEvent>>,
    /// Authentication boundary only; never serialized into retained diagnostic records.
    authenticated: bool,
    /// Start captured before authentication; IDs and clocks never contain request data.
    started_at_ms: u64,
}

/// One dependency's identity exists before transport and survives completion unchanged.
/// This prevents a propagated remote parent from referring to an unrecorded span.
pub(crate) struct DependencySpan<'a> {
    trace: &'a Trace,
    request_id: &'a str,
    phase: Phase,
    span_id: String,
    started_at_ms: u64,
}

impl DependencySpan<'_> {
    /// W3C remote parent is this client span, not its containing server span.
    pub(crate) fn traceparent(&self) -> String {
        format!(
            "00-{}-{}-{}",
            self.trace.trace_id,
            self.span_id,
            if self.trace.sampled { "01" } else { "00" }
        )
    }

    /// Finish a non-HTTP dependency exactly once; no exception prose is accepted.
    pub(crate) fn finish(self, success: bool) {
        self.finish_http(success, None);
    }

    /// Freeze clocks and retain only numeric HTTP facts for the approved dependency.
    pub(crate) fn finish_http(self, success: bool, status: Option<u16>) {
        let duration_ms = now_ms().saturating_sub(self.started_at_ms);
        let mut event = self.trace.phase_record(
            &self.span_id,
            self.request_id,
            self.phase,
            success,
            duration_ms,
        );
        event.occurred_at_ms = self.started_at_ms;
        if self.phase == Phase::BillingHttp {
            event.provider_http_status = status.filter(|value| (100..=599).contains(value));
        }
        self.trace.record(&event, false);
    }
}

/// The sole retained JSON schema. Adding a field requires a privacy review.
#[derive(Serialize)]
struct Event<'a> {
    schema_version: u8,
    event_id: String,
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
    /// Exact span start and duration allow a real causal timeline, not bucket guesses.
    occurred_at_ms: u64,
    duration_ms: u64,
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
    event_id: String,
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
    #[serde(skip_serializing_if = "Option::is_none")]
    occurred_at_ms: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    duration_ms: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    http_status: Option<u16>,
    #[serde(skip_serializing_if = "Option::is_none")]
    client_phase: Option<ClientPhase>,
    #[serde(skip_serializing_if = "Option::is_none")]
    client_error_kind: Option<ClientErrorKind>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error_code: Option<ErrorCode>,
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
            events: RefCell::new(Vec::new()),
            authenticated: false,
            started_at_ms: now_ms(),
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

    /// Announcements follow successful user authentication, not health/internal admission.
    pub(crate) fn authenticated(&mut self) {
        self.authenticated = true;
    }

    /// Binding presence permits parser announcement, never proves Queue consumer readiness.
    pub(crate) fn can_announce(&self, queue_bound: bool) -> bool {
        self.authenticated && queue_bound
    }

    /// Set an operation from a closed set rather than from a URL segment.
    pub(crate) fn operation(&mut self, operation: Operation) {
        self.operation = operation;
    }

    /// Record only a measured byte count, rounded to a power-of-two bucket.
    pub(crate) fn measured_request_bytes(&mut self, bytes: usize) {
        self.request_bytes = Some(bucket(bytes as u64));
    }

    /// Start before network work and propagate this handle's context to the remote server.
    pub(crate) fn dependency<'a>(
        &'a self,
        request_id: &'a str,
        phase: Phase,
    ) -> DependencySpan<'a> {
        DependencySpan {
            trace: self,
            request_id,
            phase,
            span_id: random_span_id(),
            started_at_ms: now_ms(),
        }
    }

    /// Finish the scheduled root without manufacturing HTTP status or request metadata.
    pub(crate) fn scheduled_exit(&self, request_id: &str, success: bool) {
        let duration_ms = now_ms().saturating_sub(self.started_at_ms);
        let mut event = self.phase_record(
            &self.span_id,
            request_id,
            Phase::ScheduledExit,
            success,
            duration_ms,
        );
        event.parent_span_id = None;
        event.occurred_at_ms = self.started_at_ms;
        self.record(&event, true);
    }

    /// Buffer a bounded request-exit event; never emit console fallback on failure.
    pub(crate) fn exit(&self, request_id: &str, status: u16, duration_ms: u64) {
        let event = Event {
            schema_version: 1,
            event_id: uuid::Uuid::new_v4().to_string(),
            service: Service::MailApi,
            operation: self.operation,
            phase: Phase::RequestExit,
            trace_id: &self.trace_id,
            span_id: &self.span_id,
            parent_span_id: self.parent_span_id.as_deref(),
            request_id,
            outcome: match status {
                100..=399 => Outcome::Success,
                400..=499 => Outcome::ClientError,
                _ => Outcome::ServerError,
            },
            error_code: error_code(status),
            http_status_class: Some(status / 100),
            duration_ms_bucket: bucket(duration_ms.min(3_600_000)),
            occurred_at_ms: self.started_at_ms,
            duration_ms,
            request_bytes_bucket: self.request_bytes,
            provider_http_status: None,
            provider_error_code: None,
        };
        self.record(&event, true);
    }

    /// Emit one child phase span with only a fixed phase label and coarse outcome.
    pub(crate) fn phase(&self, request_id: &str, phase: Phase, success: bool, duration_ms: u64) {
        let span_id = random_span_id();
        self.record(
            &self.phase_record(&span_id, request_id, phase, success, duration_ms),
            false,
        );
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
        self.record(
            &self.routing_create_record(
                &span_id,
                request_id,
                success,
                provider_http_status,
                provider_error_code,
                duration_ms,
            ),
            false,
        );
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
            event_id: uuid::Uuid::new_v4().to_string(),
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
            occurred_at_ms: now_ms().saturating_sub(duration_ms),
            duration_ms,
            request_bytes_bucket: None,
            provider_http_status: None,
            provider_error_code: None,
        }
    }

    /// Serialize only reviewed event schemas and reserve the last slot for request exit.
    fn record<T: Serialize>(&self, event: &T, exit: bool) {
        let Ok(value) = serde_json::to_value(event) else {
            return;
        };
        let Some(event) = QueuedEvent::from_value(value) else {
            return;
        };
        if serde_json::to_vec(&event).map_or(true, |bytes| bytes.len() > 1024) {
            return;
        }
        let mut events = self.events.borrow_mut();
        if events.len() < if exit { 128 } else { 127 } {
            events.push(event);
        }
    }

    /// Keep an operational warning causally attached to the request that encountered it.
    pub(crate) fn warning(&self, request_id: &str, code: DiagnosticCode) {
        let mut event = diagnostic_record(code);
        event.trace_id = self.trace_id.clone();
        event.parent_span_id = Some(self.span_id.clone());
        event.request_id = Some(request_id.to_owned());
        event.operation = self.operation;
        self.record(&event, false);
    }

    /// Detach the bounded records before an asynchronous handoff without retaining request state.
    pub(crate) fn take_events(&self) -> Vec<QueuedEvent> {
        std::mem::take(&mut *self.events.borrow_mut())
    }
}

/// Measure a bounded elapsed duration without treating wall-clock rollback as failure.
pub(crate) fn elapsed_ms(start: f64) -> u64 {
    (js_sys::Date::now() - start).max(0.0) as u64
}

/// Workers use UTC milliseconds; native contract tests use the system UTC clock.
/// Cross-service clock skew never changes parentage or invents negative durations.
fn now_ms() -> u64 {
    #[cfg(target_arch = "wasm32")]
    {
        js_sys::Date::now().max(0.0) as u64
    }
    #[cfg(not(target_arch = "wasm32"))]
    {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map_or(0, |value| value.as_millis().min(u64::MAX as u128) as u64)
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

/// Preserve legacy CLI events while enriching only validated reader metadata.
pub(crate) fn client_event(
    trace: &Trace,
    operation: Operation,
    trace_id: &str,
    span_id: Option<&str>,
    request_id: Option<&str>,
    status: u16,
    duration_ms: u64,
    response_bytes_bucket: u64,
    attempt: ClientAttempt,
) {
    if !attempt.valid(status) {
        return;
    }
    let event = ClientEvent {
        schema_version: 1,
        event_id: uuid::Uuid::new_v4().to_string(),
        service: Service::MailCli,
        operation,
        phase: Phase::OperationExit,
        trace_id,
        span_id,
        request_id: request_id.filter(|value| amail_trace_schema::canonical_uuid(value)),
        outcome: if attempt.failed() {
            Outcome::PhaseFailure
        } else {
            match status {
                100..=399 => Outcome::Success,
                400..=499 => Outcome::ClientError,
                _ => Outcome::ServerError,
            }
        },
        http_status_class: status / 100,
        duration_ms_bucket: bucket(duration_ms.min(3_600_000)),
        response_bytes_bucket: bucket(response_bytes_bucket),
        occurred_at_ms: attempt.started_at_ms,
        duration_ms: attempt.elapsed_ms,
        http_status: attempt.enriched().then_some(status),
        client_phase: attempt.phase,
        client_error_kind: attempt.error_kind,
        error_code: attempt.failed().then_some(ErrorCode::DependencyFailure),
    };
    trace.record(&event, false);
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

    /// Ordinary user authentication and the safe Queue boundary are both required to announce.
    #[test]
    fn capability_announcement_never_infers_authentication_or_queue_readiness() {
        let mut trace = Trace::new();
        assert!(!trace.can_announce(false));
        assert!(!trace.can_announce(true));
        trace.authenticated();
        assert!(!trace.can_announce(false));
        assert!(trace.can_announce(true));
    }

    /// A 2xx body failure stays a failure; complete HTTP errors stay complete exchanges.
    #[test]
    fn enriched_client_reader_maps_exact_measurements_and_boundary_outcomes() {
        for (phase, error_kind, status, outcome) in [
            (
                ClientPhase::Auth,
                Some(ClientErrorKind::CredentialUnavailable),
                0,
                Outcome::PhaseFailure,
            ),
            (
                ClientPhase::Transport,
                Some(ClientErrorKind::Connect),
                0,
                Outcome::PhaseFailure,
            ),
            (
                ClientPhase::ResponseBody,
                Some(ClientErrorKind::Decode),
                200,
                Outcome::PhaseFailure,
            ),
            (ClientPhase::Complete, None, 503, Outcome::ServerError),
            (ClientPhase::Complete, None, 201, Outcome::Success),
        ] {
            let trace = Trace::new();
            client_event(
                &trace,
                Operation::MessagesList,
                "0123456789abcdef0123456789abcdef",
                Some("0123456789abcdef"),
                Some("00000000-0000-4000-8000-000000000001"),
                status,
                120_000,
                0,
                ClientAttempt {
                    started_at_ms: Some(1_790_000_000_123),
                    elapsed_ms: Some(121_007),
                    phase: Some(phase),
                    error_kind,
                },
            );
            let events = trace.take_events();
            assert_eq!(events.len(), 1);
            let event = &events[0];
            assert!(event.valid());
            assert_eq!(event.occurred_at_ms, Some(1_790_000_000_123));
            assert_eq!(event.duration_ms, Some(121_007));
            assert_eq!(event.http_status, Some(status));
            assert_eq!(event.client_phase, Some(phase));
            assert_eq!(event.client_error_kind, error_kind);
            assert_eq!(event.outcome, outcome);
        }
    }

    /// Bound nine stage spans, three Billing calls, a root and fourteen conditions.
    #[test]
    fn maintenance_buffer_validates_whole_batch_before_any_binding() {
        let events = (0..27)
            .map(|_| diagnostic_record(DiagnosticCode::MaintenanceDeadlineDeferred))
            .collect::<Vec<_>>();
        let lengths = events
            .iter()
            .map(|event| serde_json::to_vec(event).unwrap().len())
            .collect::<Vec<_>>();
        assert!(lengths.iter().all(|length| *length <= 1024));
        assert_eq!(maintenance_charge(&events), batch_charge(&lengths));
        assert!(maintenance_charge(&events).unwrap() <= 45_596);
        let mut invalid = events.clone();
        invalid[12].error_code = Some(ErrorCode::DependencyFailure);
        assert!(maintenance_charge(&invalid).is_none());
        invalid[12] = diagnostic_record(DiagnosticCode::MaintenanceDeadlineDeferred);
        invalid.push(diagnostic_record(
            DiagnosticCode::MaintenanceDeadlineDeferred,
        ));
        assert!(maintenance_charge(&invalid).is_none());
    }

    /// Unreachable aggregate extremes belong in the pure charge helper only.
    #[test]
    fn maintenance_charge_checks_actual_bytes_cap_and_overflow() {
        assert_eq!(batch_charge(&[235_390]), Some(240_000));
        assert_eq!(batch_charge(&[235_391]), None);
        assert_eq!(batch_charge(&[usize::MAX]), None);
        assert_eq!(batch_charge(&[usize::MAX, 1]), None);
        assert_eq!(batch_charge(&[1024; 13]), Some(24_078));
    }

    /// Native TextEncoder fixture uses this independent literal standalone shape.
    #[test]
    fn maintenance_json_byte_contract_matches_native_literal_shape() {
        for code in [
            DiagnosticCode::RoutingReconciliationFailed,
            DiagnosticCode::OutboundReconciliationFailed,
            DiagnosticCode::SemanticIndexRetryFailed,
            DiagnosticCode::StorageLedgerReconciliationFailed,
            DiagnosticCode::DeletedMessageCleanupFailed,
            DiagnosticCode::OrphanObjectCleanupFailed,
            DiagnosticCode::SearchJobCleanupFailed,
            DiagnosticCode::AbuseDataCleanupFailed,
            DiagnosticCode::AddressReconciliationBatchFull,
            DiagnosticCode::NonEnabledCommittedRoutingRule,
            DiagnosticCode::NonEnabledProvisioningRoutingRule,
            DiagnosticCode::SemanticDocumentQuarantined,
            DiagnosticCode::SemanticProviderCooldown,
            DiagnosticCode::MaintenanceBudgetDeferred,
            DiagnosticCode::MaintenanceDeadlineDeferred,
        ] {
            let event = diagnostic_record(code);
            let expected = serde_json::json!({
                "schema_version": 1, "event_id": "00000000-0000-4000-8000-000000000001",
                "service": "mail_api", "operation": "maintenance", "phase": "maintenance",
                "trace_id": "0123456789abcdef0123456789abcdef", "span_id": "0123456789abcdef",
                "request_id": "00000000-0000-4000-8000-000000000001", "outcome": "phase_failure",
                "error_code": event.error_code, "duration_ms_bucket": 0, "diagnostic_code": code
            });
            assert_eq!(
                serde_json::to_vec(&event).unwrap().len(),
                serde_json::to_vec(&expected).unwrap().len()
            );
            assert_eq!(
                serde_json::to_value(&event)
                    .unwrap()
                    .as_object()
                    .unwrap()
                    .len(),
                12
            );
        }
    }

    /// Resource deferrals preserve distinct wire codes without becoming dependency failures.
    #[test]
    fn maintenance_deferrals_have_exact_diagnostic_pairs() {
        for (code, wire_code) in [
            (
                DiagnosticCode::MaintenanceBudgetDeferred,
                "maintenance_budget_deferred",
            ),
            (
                DiagnosticCode::MaintenanceDeadlineDeferred,
                "maintenance_deadline_deferred",
            ),
        ] {
            let event = diagnostic_record(code);
            assert!(event.valid());
            assert_eq!(event.error_code, Some(ErrorCode::ResourceDeferred));
            assert!(event.parent_span_id.is_none());
            let value = serde_json::to_value(event).unwrap();
            assert_eq!(value["diagnostic_code"], wire_code);
            assert_eq!(value["operation"], "maintenance");
        }
        let failure = diagnostic_record(DiagnosticCode::OutboundReconciliationFailed);
        assert!(failure.valid());
        assert_eq!(failure.error_code, Some(ErrorCode::DependencyFailure));
    }

    /// Resumable search polls cannot poison the entire legacy upload batch.
    #[test]
    fn cli_search_poll_is_a_reviewed_operation() {
        assert_eq!(
            operation_from_cli("messages.search.poll"),
            Some(Operation::SearchPoll)
        );
        assert!(operation_from_cli("messages.search.poll/private-input").is_none());
        assert!(operation_from_cli("messages.search.poll.extra").is_none());
    }

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
            event_id: uuid::Uuid::new_v4().to_string(),
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
            occurred_at_ms: 1_790_000_000_123,
            duration_ms: 7,
            request_bytes_bucket: None,
            provider_http_status: None,
            provider_error_code: None,
        };
        let value = serde_json::to_value(event).unwrap();
        assert_eq!(value.as_object().unwrap().len(), 14);
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

    /// The remote server must parent the client span actually retained at completion.
    #[test]
    fn billing_transport_preserves_propagated_identity_and_exact_clock() {
        let mut trace = Trace::new();
        trace.accept_parent(Some(
            "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
        ));
        trace.operation(Operation::BillingSessionCreate);
        let span = trace.dependency("00000000-0000-4000-8000-000000000001", Phase::BillingHttp);
        let parent = parse_parent(&span.traceparent()).unwrap();
        let started = span.started_at_ms;
        span.finish_http(false, Some(503));
        let events = trace.take_events();
        assert_eq!(events.len(), 1);
        let event = &events[0];
        assert_eq!(event.trace_id, parent.trace_id);
        assert_eq!(event.span_id.as_deref(), Some(parent.span_id.as_str()));
        assert_eq!(
            event.parent_span_id.as_deref(),
            Some(trace.span_id.as_str())
        );
        assert_eq!(event.occurred_at_ms, Some(started));
        assert!(event.duration_ms.is_some());
        assert_eq!(event.provider_http_status, Some(503));
        assert_eq!(event.outcome, Outcome::PhaseFailure);
        assert!(event.valid());
    }

    /// Successful no-op maintenance is visible, not indistinguishable from a dead Cron.
    #[test]
    fn scheduled_root_and_stage_share_trace_but_not_span_identity() {
        let mut trace = Trace::new();
        trace.operation(Operation::Maintenance);
        let request = "00000000-0000-4000-8000-000000000001";
        trace
            .dependency(request, Phase::MaintenanceStorage)
            .finish(true);
        trace
            .dependency(request, Phase::BillingHttp)
            .finish_http(true, Some(200));
        trace.scheduled_exit(request, true);
        let events = trace.take_events();
        assert_eq!(events.len(), 3);
        let stage = &events[0];
        let root = &events[2];
        assert!(events[1].valid());
        assert_eq!(events[1].parent_span_id, root.span_id);
        assert!(stage.valid() && root.valid());
        assert_eq!(stage.trace_id, root.trace_id);
        assert_eq!(stage.parent_span_id, root.span_id);
        assert_ne!(stage.span_id, root.span_id);
        assert_eq!(root.phase, Phase::ScheduledExit);
        assert!(root.parent_span_id.is_none());
        assert!(root.http_status_class.is_none());
    }

    /// One hundred legacy uploaded rows and a request exit require two ordered batches.
    #[test]
    fn full_telemetry_batch_keeps_exit_and_identity() {
        let trace = Trace::new();
        for _ in 0..100 {
            client_event(
                &trace,
                Operation::MessagesList,
                "0123456789abcdef0123456789abcdef",
                None,
                None,
                0,
                0,
                0,
                ClientAttempt::default(),
            );
        }
        trace.exit("00000000-0000-4000-8000-000000000001", 202, 0);
        let events = trace.take_events();
        assert_eq!(events.len(), 101);
        assert_eq!(
            events.last().unwrap().phase,
            amail_trace_schema::Phase::RequestExit
        );
        let ids: Vec<_> = events.iter().map(|event| event.event_id.clone()).collect();
        let batches = queue_batches(events);
        assert_eq!(
            batches.iter().map(Vec::len).collect::<Vec<_>>(),
            vec![100, 1]
        );
        let roundtrip: Vec<_> = batches
            .iter()
            .flatten()
            .map(|event| event.event_id.clone())
            .collect();
        assert_eq!(ids, roundtrip);
    }

    /// Burst telemetry cannot exhaust the request exit slot or exceed the memory bound.
    #[test]
    fn bounded_buffer_reserves_request_exit() {
        let trace = Trace::new();
        for _ in 0..200 {
            client_event(
                &trace,
                Operation::MessagesList,
                "0123456789abcdef0123456789abcdef",
                None,
                None,
                200,
                1,
                1,
                ClientAttempt::default(),
            );
        }
        trace.exit("00000000-0000-4000-8000-000000000001", 200, 1);
        let events = trace.take_events();
        assert_eq!(events.len(), 128);
        assert!(events.iter().all(QueuedEvent::valid));
        assert!(events
            .iter()
            .all(|event| serde_json::to_vec(event).unwrap().len() <= 1024));
        assert_eq!(
            events.last().unwrap().phase,
            amail_trace_schema::Phase::RequestExit
        );
        assert!(trace.take_events().is_empty());
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

/// Send typed safe records only; failures neither log request context nor change API outcomes.
/// Batches stay below Queue's 100-message limit and 256KB batch size limit.
pub(crate) async fn flush(env: &worker::Env, events: Vec<QueuedEvent>) {
    let Ok(queue) = env.queue("TRACE_EVENTS") else {
        return;
    };
    for events in queue_batches(events) {
        let batch = worker::BatchMessageBuilder::new().messages(events).build();
        if queue.send_batch(batch).await.is_err() {
            return;
        }
    }
}

/// Preserve order and event IDs while enforcing the Queue batch count and byte bounds.
fn queue_batches(mut events: Vec<QueuedEvent>) -> Vec<Vec<QueuedEvent>> {
    let mut batches = Vec::new();
    while !events.is_empty() {
        let tail = events.split_off(events.len().min(100));
        batches.push(events);
        events = tail;
    }
    batches
}

/// Consume Cron's fixed records at exit, without splitting, retry or console fallback.
///
/// Wait only until the immutable final-tail deadline. Dropping our waiter does
/// not cancel the native write: timeout is delivery-unknown, never safe to retry.
/// No waitUntil task, background continuation or timer rearming is introduced.
pub(crate) async fn flush_maintenance(
    env: &worker::Env,
    codes: Vec<DiagnosticCode>,
    mut events: Vec<QueuedEvent>,
    deadline: crate::maintenance::ExternalDeadline<'_>,
) {
    events.extend(codes.into_iter().map(diagnostic_record));
    if events.is_empty() || maintenance_charge(&events).is_none() {
        return;
    }
    if deadline.remaining().is_err() {
        return;
    }
    let Ok(queue) = env.queue("TRACE_EVENTS") else {
        return;
    };
    let batch = worker::BatchMessageBuilder::new().messages(events).build();
    let Ok(duration) = deadline.remaining() else {
        return;
    };
    let pending = Box::pin(queue.send_batch(batch));
    let timer = Box::pin(worker::Delay::from(duration));
    match futures_util::future::select(pending, timer).await {
        futures_util::future::Either::Left((_, timer)) => drop(timer),
        futures_util::future::Either::Right((_, pending)) => drop(pending),
    };
}

/// Validate the entire buffer and actual UTF-8 body bytes before binding access.
fn maintenance_charge(events: &[QueuedEvent]) -> Option<usize> {
    if events.len() > 27 || events.iter().any(|event| !event.valid()) {
        return None;
    }
    let lengths = events
        .iter()
        .map(|event| serde_json::to_vec(event).ok().map(|bytes| bytes.len()))
        .collect::<Option<Vec<_>>>()?;
    if lengths.iter().any(|length| *length > 1024) {
        return None;
    }
    batch_charge(&lengths)
}

/// Conservative application charge, not an exact provider serialization formula.
fn batch_charge(lengths: &[usize]) -> Option<usize> {
    let bodies = lengths
        .iter()
        .try_fold(0usize, |sum, len| sum.checked_add(*len))?;
    let overhead = 512usize.checked_mul(lengths.len())?.checked_add(4096)?;
    let charge = 2usize
        .checked_add(bodies)?
        .checked_add(lengths.len().saturating_sub(1))?
        .checked_add(overhead)?;
    (charge <= 240_000).then_some(charge)
}

/// Construct a standalone fixed maintenance condition without retaining source context.
fn diagnostic_record(code: DiagnosticCode) -> QueuedEvent {
    QueuedEvent {
        schema_version: 1,
        event_id: uuid::Uuid::new_v4().to_string(),
        service: amail_trace_schema::Service::MailApi,
        operation: amail_trace_schema::Operation::Maintenance,
        phase: amail_trace_schema::Phase::Maintenance,
        trace_id: uuid::Uuid::new_v4().simple().to_string(),
        span_id: Some(random_span_id()),
        parent_span_id: None,
        request_id: Some(uuid::Uuid::new_v4().to_string()),
        outcome: amail_trace_schema::Outcome::PhaseFailure,
        error_code: Some(
            if matches!(
                code,
                DiagnosticCode::MaintenanceBudgetDeferred
                    | DiagnosticCode::MaintenanceDeadlineDeferred
            ) {
                ErrorCode::ResourceDeferred
            } else {
                ErrorCode::DependencyFailure
            },
        ),
        http_status_class: None,
        duration_ms_bucket: 0,
        request_bytes_bucket: None,
        response_bytes_bucket: None,
        provider_http_status: None,
        provider_error_code: None,
        diagnostic_code: Some(code),
        occurred_at_ms: None,
        duration_ms: None,
        http_status: None,
        client_phase: None,
        client_error_kind: None,
    }
}
