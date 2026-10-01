//! Closed privacy-safe trace wire contract shared by producer and isolated sink.
//! Unknown fields, noncanonical identifiers and incompatible field combinations fail closed.

use serde::{Deserialize, Serialize};

mod role;
pub use role::{RoleCode, RoleEvent, RoleKind};
mod client;
pub use client::{ClientAttempt, ClientErrorKind, ClientPhase};

/// Closed union of reviewed producers; existing Mail events retain their wire shape.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(untagged)]
pub enum Record {
    /// Existing Mail API/CLI correlation contract, unchanged on the wire.
    Mail(Event),
    /// Content-free Email/Cron monitor diagnostics without HTTP field semantics.
    Role(RoleEvent),
}

impl Record {
    /// Reject malformed, oversized or semantically invalid payloads before reconstruction.
    pub fn from_value(value: serde_json::Value) -> Option<Self> {
        if serde_json::to_vec(&value).ok()?.len() > 1024 {
            return None;
        }
        let record: Self = serde_json::from_value(value).ok()?;
        let valid = match &record {
            Self::Mail(event) => event.valid(),
            Self::Role(event) => event.valid(),
        };
        valid.then_some(record)
    }
}

/// Closed operation vocabulary; never deserialize arbitrary labels.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Operation {
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
    /// Scheduled or bounded operational diagnostics, never request-derived labels.
    Maintenance,
}

/// Closed outcome vocabulary; never deserialize arbitrary labels.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Outcome {
    Success,
    ClientError,
    ServerError,
    PhaseFailure,
}

/// Closed service vocabulary; never deserialize arbitrary labels.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Service {
    MailApi,
    MailCli,
}

/// Closed phase vocabulary; never deserialize arbitrary labels.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Phase {
    RequestExit,
    OperationExit,
    D1Read,
    D1Write,
    R2Write,
    ProviderSend,
    RoutingList,
    RoutingCreate,
    /// Scheduled or bounded operational diagnostics, never request-derived labels.
    Maintenance,
}

/// Closed errorcode vocabulary; never deserialize arbitrary labels.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ErrorCode {
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
    /// Deliberate maintenance admission deferral, never a provider failure.
    ResourceDeferred,
}

/// Fixed operational conditions; no mail, aliases, provider errors or request context.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DiagnosticCode {
    /// Address repair did not complete.
    RoutingReconciliationFailed,
    /// Outbound repair did not complete.
    OutboundReconciliationFailed,
    /// Background embedding retry failed.
    SemanticIndexRetryFailed,
    /// Storage ledger reconciliation failed.
    StorageLedgerReconciliationFailed,
    /// Deleted-message cleanup failed.
    DeletedMessageCleanupFailed,
    /// Orphan-object cleanup failed.
    OrphanObjectCleanupFailed,
    /// Search state cleanup failed.
    SearchJobCleanupFailed,
    /// Abuse envelope expiration failed.
    AbuseDataCleanupFailed,
    /// Address sweep reached its fixed bound.
    AddressReconciliationBatchFull,
    /// A committed route was disabled.
    NonEnabledCommittedRoutingRule,
    /// A provisioning route was disabled.
    NonEnabledProvisioningRoutingRule,
    /// An embedding document entered quarantine.
    SemanticDocumentQuarantined,
    /// The embedding provider entered cooldown.
    SemanticProviderCooldown,
    /// A storage reservation update must be reconciled.
    StorageLedgerStateDeferred,
    /// A maintenance phase retained its journal when its SQL grant ran out.
    MaintenanceBudgetDeferred,
    /// Maintenance retained its journal when its admission deadline elapsed.
    MaintenanceDeadlineDeferred,
}

/// Flat allowlisted JSON. Validation additionally enforces service-specific field sets.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Event {
    /// Wire contract version; only version one is accepted.
    pub schema_version: u8,
    /// Producer-generated canonical UUIDv4, stable across Queue redelivery.
    pub event_id: String,
    /// Reviewed originating service, independent of sink invocation.
    pub service: Service,
    /// Reviewed logical operation rather than URL or CLI input.
    pub operation: Operation,
    /// Reviewed causal phase label.
    pub phase: Phase,
    /// Strict lower-case nonzero W3C 128-bit trace ID.
    pub trace_id: String,
    /// Strict W3C span ID; absent only for legacy CLI rows.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub span_id: Option<String>,
    /// Strict causal parent ID, never replaced by Queue span IDs.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub parent_span_id: Option<String>,
    /// Canonical UUID request correlation; optional for legacy CLI rows.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub request_id: Option<String>,
    /// Fixed coarse outcome classification.
    pub outcome: Outcome,
    /// Fixed coarse error classification; no exception text.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error_code: Option<ErrorCode>,
    /// HTTP status hundred class; zero only for historical CLI failures.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub http_status_class: Option<u16>,
    /// Producer UTC event time, not sink receipt time; absent for legacy records.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub occurred_at_ms: Option<u64>,
    /// Exact operational elapsed milliseconds, independent of content-size buckets.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub duration_ms: Option<u64>,
    /// Exact observed HTTP status; zero is reserved for CLI attempts with no headers.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub http_status: Option<u16>,
    /// Optional enriched CLI boundary; absent for legacy clients and all API events.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub client_phase: Option<ClientPhase>,
    /// Closed client failure cause, never arbitrary exception text.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub client_error_kind: Option<ClientErrorKind>,
    /// Power-of-two elapsed bucket bounded to one hour rounded upward.
    pub duration_ms_bucket: u64,
    /// Measured request byte bucket, never content or a path.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub request_bytes_bucket: Option<u64>,
    /// Measured CLI response byte bucket.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub response_bytes_bucket: Option<u64>,
    /// Numeric Routing Rules response status, without response body.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub provider_http_status: Option<u16>,
    /// Numeric Routing Rules API error, without exception text.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub provider_error_code: Option<u32>,
    /// Fixed maintenance condition replacing static API console warnings.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub diagnostic_code: Option<DiagnosticCode>,
}

impl Event {
    /// Decode without retaining untrusted error text, then enforce every invariant.
    pub fn from_value(value: serde_json::Value) -> Option<Self> {
        let event: Self = serde_json::from_value(value).ok()?;
        event.valid().then_some(event)
    }

    /// Enforce canonical IDs, bounded numeric buckets and exact causal field combinations.
    pub fn valid(&self) -> bool {
        if self.schema_version != 1
            || !canonical_uuid(&self.event_id)
            || !valid_hex_id(&self.trace_id, 32)
            || self
                .span_id
                .as_deref()
                .is_some_and(|id| !valid_hex_id(id, 16))
            || self
                .parent_span_id
                .as_deref()
                .is_some_and(|id| !valid_hex_id(id, 16))
            || self
                .request_id
                .as_deref()
                .is_some_and(|id| !canonical_uuid(id))
            || self.occurred_at_ms.is_some_and(|n| n > MAX_SAFE_INTEGER)
            || self.duration_ms.is_some_and(|n| n > MAX_SAFE_INTEGER)
            || (self.service != Service::MailCli
                && (self.client_phase.is_some() || self.client_error_kind.is_some()))
            || self.http_status.is_some_and(|n| {
                (!(100..=599).contains(&n) && !(n == 0 && self.service == Service::MailCli))
                    || self.http_status_class != Some(n / 100)
            })
            || !valid_bucket(self.duration_ms_bucket, 1 << 22)
            || self
                .request_bytes_bucket
                .is_some_and(|n| !valid_bucket(n, 1 << 32))
            || self
                .response_bytes_bucket
                .is_some_and(|n| !valid_bucket(n, 1 << 32))
            || self.http_status_class.is_some_and(|n| n > 5)
            || self
                .provider_http_status
                .is_some_and(|n| !(100..=599).contains(&n))
        {
            return false;
        }
        match (self.service, self.phase) {
            (Service::MailCli, Phase::OperationExit) => self.valid_client(),
            (Service::MailApi, Phase::Maintenance) => self.valid_diagnostic(),
            (Service::MailApi, Phase::RequestExit) => self.valid_request(),
            (Service::MailApi, Phase::OperationExit) => false,
            (Service::MailApi, _) => self.valid_phase(),
            _ => false,
        }
    }

    fn no_provider(&self) -> bool {
        self.provider_http_status.is_none() && self.provider_error_code.is_none()
    }

    fn valid_client(&self) -> bool {
        let attempt = ClientAttempt {
            started_at_ms: self.occurred_at_ms,
            elapsed_ms: self.duration_ms,
            phase: self.client_phase,
            error_kind: self.client_error_kind,
        };
        // Previously accepted exact measurements without phase remain valid reader records.
        let enriched_boundary = self.client_phase.is_some() || self.client_error_kind.is_some();
        let valid_outcome = if enriched_boundary {
            self.http_status.is_some_and(|status| attempt.valid(status))
                && if attempt.failed() {
                    self.outcome == Outcome::PhaseFailure
                        && self.error_code == Some(ErrorCode::DependencyFailure)
                } else {
                    self.error_code.is_none() && self.valid_status_outcome(true)
                }
        } else {
            self.error_code.is_none() && self.valid_status_outcome(true)
        };
        matches!(
            self.operation,
            Operation::AddressesList
                | Operation::AddressesAdd
                | Operation::AddressesDelete
                | Operation::MessagesList
                | Operation::MessagesSearch
                | Operation::SearchPoll
                | Operation::MessagesSend
                | Operation::MessagesGet
                | Operation::MessagesArchive
                | Operation::MessagesMark
                | Operation::MessagesDelete
        ) && self.parent_span_id.is_none()
            && valid_outcome
            && self.request_bytes_bucket.is_none()
            && self.response_bytes_bucket.is_some()
            && self.diagnostic_code.is_none()
            && self.no_provider()
    }

    fn valid_diagnostic(&self) -> bool {
        ((self.operation == Operation::Maintenance && self.parent_span_id.is_none())
            || (self.operation != Operation::Maintenance && self.parent_span_id.is_some()))
            && self.span_id.is_some()
            && self.request_id.is_some()
            && self.outcome == Outcome::PhaseFailure
            && match self.diagnostic_code {
                Some(
                    DiagnosticCode::MaintenanceBudgetDeferred
                    | DiagnosticCode::MaintenanceDeadlineDeferred,
                ) => {
                    self.operation == Operation::Maintenance
                        && self.error_code == Some(ErrorCode::ResourceDeferred)
                }
                Some(_) => self.error_code == Some(ErrorCode::DependencyFailure),
                None => false,
            }
            && self.http_status_class.is_none()
            && self.request_bytes_bucket.is_none()
            && self.response_bytes_bucket.is_none()
            && self.no_provider()
    }

    fn valid_request(&self) -> bool {
        self.operation != Operation::Maintenance
            && self.span_id.is_some()
            && self.request_id.is_some()
            && self.response_bytes_bucket.is_none()
            && self.diagnostic_code.is_none()
            && self.no_provider()
            && self.valid_status_outcome(false)
            && match self.outcome {
                Outcome::Success => self.error_code.is_none(),
                Outcome::ClientError => matches!(
                    self.error_code,
                    Some(
                        ErrorCode::InvalidRequest
                            | ErrorCode::Unauthorized
                            | ErrorCode::Forbidden
                            | ErrorCode::NotFound
                            | ErrorCode::Conflict
                            | ErrorCode::RateLimited
                            | ErrorCode::OtherClient
                    )
                ),
                Outcome::ServerError => matches!(
                    self.error_code,
                    Some(ErrorCode::ServiceUnavailable | ErrorCode::OtherServer)
                ),
                _ => false,
            }
    }

    fn valid_phase(&self) -> bool {
        self.operation != Operation::Maintenance
            && self.span_id.is_some()
            && self.parent_span_id.is_some()
            && self.request_id.is_some()
            && self.http_status_class.is_none()
            && self.request_bytes_bucket.is_none()
            && self.response_bytes_bucket.is_none()
            && self.diagnostic_code.is_none()
            && (self.phase == Phase::RoutingCreate || self.no_provider())
            && matches!(
                (self.outcome, self.error_code),
                (Outcome::Success, None)
                    | (Outcome::PhaseFailure, Some(ErrorCode::DependencyFailure))
            )
    }

    fn valid_status_outcome(&self, legacy: bool) -> bool {
        matches!(
            (self.http_status_class, self.outcome),
            (Some(1..=3), Outcome::Success)
                | (Some(4), Outcome::ClientError)
                | (Some(5), Outcome::ServerError)
        ) || (legacy && self.http_status_class == Some(0) && self.outcome == Outcome::ServerError)
    }
}

/// JSON integers crossing JavaScript must not silently lose precision.
const MAX_SAFE_INTEGER: u64 = (1 << 53) - 1;

/// Exact lowercase nonzero W3C correlation identifier, never arbitrary text.
pub fn valid_hex_id(id: &str, length: usize) -> bool {
    id.len() == length
        && id
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        && id.bytes().any(|b| b != b'0')
}

/// Canonical lower-case UUIDv4 correlation generated by the producer.
pub fn canonical_uuid(raw: &str) -> bool {
    uuid::Uuid::parse_str(raw).is_ok_and(|id| {
        id.get_version_num() == 4
            && id.get_variant() == uuid::Variant::RFC4122
            && id.hyphenated().to_string() == raw
    })
}

fn valid_bucket(value: u64, maximum: u64) -> bool {
    value <= maximum && (value == 0 || value.is_power_of_two())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    /// Produce a complete safe event without calling platform APIs.
    fn fixture() -> serde_json::Value {
        json!({"schema_version":1,"event_id":"00000000-0000-4000-8000-000000000002",
            "service":"mail_api","operation":"messages_list","phase":"request_exit",
            "trace_id":"0123456789abcdef0123456789abcdef","span_id":"abcdef0123456789",
            "parent_span_id":"0123456789abcdef","request_id":"00000000-0000-4000-8000-000000000001",
            "outcome":"success","http_status_class":2,"duration_ms_bucket":8})
    }

    /// Sink reconstruction preserves causal and producer identities exactly across retries.
    #[test]
    fn roundtrip_preserves_identity() {
        let record = Record::from_value(fixture()).unwrap();
        assert_eq!(serde_json::to_value(record).unwrap(), fixture());
        let first = Event::from_value(fixture()).unwrap();
        let encoded = serde_json::to_value(&first).unwrap();
        assert_eq!(encoded, fixture());
        let second = Event::from_value(encoded).unwrap();
        assert_eq!(first.event_id, second.event_id);
        assert_eq!(first.trace_id, second.trace_id);
        assert_eq!(first.parent_span_id, second.parent_span_id);
        assert!(serde_json::to_string(&second).unwrap().len() < 1024);
    }

    /// A reader upgrade preserves legacy shape and exact operational measurements.
    #[test]
    fn enriched_measurements_roundtrip_without_adding_fields_to_legacy_rows() {
        let old = fixture();
        assert_eq!(
            serde_json::to_value(Record::from_value(old.clone()).unwrap()).unwrap(),
            old
        );
        let mut enriched = fixture();
        enriched["occurred_at_ms"] = json!(1_790_000_000_123u64);
        enriched["duration_ms"] = json!(7);
        enriched["http_status"] = json!(201);
        assert_eq!(
            serde_json::to_value(Record::from_value(enriched.clone()).unwrap()).unwrap(),
            enriched
        );
    }

    /// Typed useful measurements do not open a channel for arbitrary personal text.
    #[test]
    fn enriched_fields_reject_wrong_types_precision_loss_and_inconsistent_status() {
        for (field, bad) in [
            ("occurred_at_ms", json!(-1)),
            ("occurred_at_ms", json!("private-time")),
            ("occurred_at_ms", json!(MAX_SAFE_INTEGER + 1)),
            ("duration_ms", json!(-1)),
            ("duration_ms", json!(0.5)),
            ("duration_ms", json!(MAX_SAFE_INTEGER + 1)),
            ("http_status", json!("private-status")),
            ("http_status", json!(0)),
            ("http_status", json!(600)),
            ("http_status", json!(503)),
        ] {
            let mut value = fixture();
            value[field] = bad;
            assert!(Record::from_value(value).is_none(), "accepted {field}");
        }
    }

    /// Poison fields, arbitrary enums and malformed identifiers never enter retained source.
    #[test]
    fn unsafe_fields_and_values_are_rejected() {
        for (field, value) in [
            ("url", json!("https://private.invalid/body")),
            ("operation", json!("private-title")),
            ("event_id", json!("00000000-0000-0000-0000-000000000002")),
            ("trace_id", json!("0123456789ABCDEF0123456789abcdef")),
            ("span_id", json!("0000000000000000")),
            ("request_id", json!("private-address")),
            ("schema_version", json!(2)),
            ("duration_ms_bucket", json!(7)),
            ("provider_http_status", json!(403)),
            ("http_status_class", json!(6)),
            ("response_bytes_bucket", json!(8)),
            ("diagnostic_code", json!("semantic_provider_cooldown")),
            ("error_code", json!("dependency_failure")),
        ] {
            let mut value_fixture = fixture();
            value_fixture[field] = value;
            assert!(
                Event::from_value(value_fixture).is_none(),
                "accepted unsafe field {field}"
            );
        }
        for field in ["span_id", "request_id", "http_status_class"] {
            let mut value = fixture();
            value.as_object_mut().unwrap().remove(field);
            assert!(Event::from_value(value).is_none());
        }
    }

    /// Legacy client rows have no span/request ID and may report an unknown network status.
    #[test]
    fn legacy_cli_unknown_status_remains_safe() {
        let value = json!({"schema_version":1,"event_id":"00000000-0000-4000-8000-000000000002",
            "service":"mail_cli","operation":"messages_list","phase":"operation_exit",
            "trace_id":"0123456789abcdef0123456789abcdef","outcome":"server_error",
            "http_status_class":0,"duration_ms_bucket":0,"response_bytes_bucket":0});
        assert!(Event::from_value(value).is_some());
    }

    /// Only the fixed standalone maintenance pairs may report resource deferral.
    #[test]
    fn resource_deferral_is_not_a_dependency_failure_or_request_event() {
        let mut value = fixture();
        value.as_object_mut().unwrap().remove("http_status_class");
        value.as_object_mut().unwrap().remove("parent_span_id");
        value["operation"] = json!("maintenance");
        value["phase"] = json!("maintenance");
        value["outcome"] = json!("phase_failure");
        value["error_code"] = json!("resource_deferred");
        for code in [
            "maintenance_budget_deferred",
            "maintenance_deadline_deferred",
        ] {
            value["diagnostic_code"] = json!(code);
            assert!(Event::from_value(value.clone()).is_some());
            for (field, bad) in [
                ("error_code", json!("dependency_failure")),
                ("diagnostic_code", json!("outbound_reconciliation_failed")),
                ("operation", json!("messages_send")),
                ("parent_span_id", json!("abcdef0123456789")),
                ("phase", json!("request_exit")),
                ("outcome", json!("success")),
            ] {
                let mut bad_value = value.clone();
                bad_value[field] = bad;
                assert!(Event::from_value(bad_value).is_none());
            }
            let mut request_child = value.clone();
            request_child["operation"] = json!("messages_send");
            request_child["parent_span_id"] = json!("abcdef0123456789");
            assert!(Event::from_value(request_child).is_none());
        }
    }

    /// Numeric dependency status is restricted to a routing-create child phase.
    #[test]
    fn phase_fields_have_exact_contract() {
        let mut value = fixture();
        value["phase"] = json!("routing_create");
        value.as_object_mut().unwrap().remove("http_status_class");
        value["outcome"] = json!("phase_failure");
        value["error_code"] = json!("dependency_failure");
        value["provider_http_status"] = json!(403);
        value["provider_error_code"] = json!(10000);
        assert!(Event::from_value(value.clone()).is_some());
        value["phase"] = json!("d1_read");
        assert!(Event::from_value(value).is_none());
    }
}
