//! Allowlisted application trace events; no request-derived text enters retained logs.

use amail_trace_schema::Event as QueuedEvent;
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
        "messages.get" => Operation::MessagesGet,
        "messages.archive" => Operation::MessagesArchive,
        "messages.mark" => Operation::MessagesMark,
        "messages.delete" => Operation::MessagesDelete,
        "messages.send" => Operation::MessagesSend,
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
    trace: &Trace,
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
        event_id: uuid::Uuid::new_v4().to_string(),
        service: Service::MailCli,
        operation,
        phase: Phase::OperationExit,
        trace_id,
        span_id,
        request_id: request_id.filter(|value| amail_trace_schema::canonical_uuid(value)),
        outcome: match status {
            100..=399 => Outcome::Success,
            400..=499 => Outcome::ClientError,
            _ => Outcome::ServerError,
        },
        http_status_class: status / 100,
        duration_ms_bucket: bucket(duration_ms.min(3_600_000)),
        response_bytes_bucket: bucket(response_bytes_bucket),
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

    /// Validate real serialized bodies, including the exact thirteen-record case.
    #[test]
    fn maintenance_buffer_validates_whole_batch_before_any_binding() {
        let events = (0..13)
            .map(|_| diagnostic_record(DiagnosticCode::MaintenanceDeadlineDeferred))
            .collect::<Vec<_>>();
        let lengths = events
            .iter()
            .map(|event| serde_json::to_vec(event).unwrap().len())
            .collect::<Vec<_>>();
        assert!(lengths.iter().all(|length| *length <= 1024));
        assert_eq!(maintenance_charge(&events), batch_charge(&lengths));
        assert!(maintenance_charge(&events).unwrap() <= 24_078);
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
            request_bytes_bucket: None,
            provider_http_status: None,
            provider_error_code: None,
        };
        let value = serde_json::to_value(event).unwrap();
        assert_eq!(value.as_object().unwrap().len(), 12);
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
/// Queue has no cancellation contract. This one final await can exceed the soft
/// scheduling target, but cannot delay admission of another business phase.
pub(crate) async fn flush_maintenance(env: &worker::Env, codes: Vec<DiagnosticCode>) {
    let events = codes.into_iter().map(diagnostic_record).collect::<Vec<_>>();
    if events.is_empty() || maintenance_charge(&events).is_none() {
        return;
    }
    let Ok(queue) = env.queue("TRACE_EVENTS") else {
        return;
    };
    let batch = worker::BatchMessageBuilder::new().messages(events).build();
    let _ = queue.send_batch(batch).await;
}

/// Validate the entire buffer and actual UTF-8 body bytes before binding access.
fn maintenance_charge(events: &[QueuedEvent]) -> Option<usize> {
    if events.len() > 13 || events.iter().any(|event| !event.valid()) {
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
    }
}
