//! Separate closed diagnostics for Email/Cron; no envelope, MIME, destination or error text.

use serde::{Deserialize, Serialize};

/// Fixed reviewed producer; cannot be substituted with a caller-provided service name.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
enum RoleService {
    RoleMonitor,
}

/// Public role categories, not mailbox strings or reporter-controlled recipients.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RoleKind {
    /// Apex abuse role.
    ApexAbuse,
    /// Apex postal-administration role.
    ApexPostmaster,
    /// Public receiving-domain abuse role.
    MailAbuse,
    /// Public receiving-domain postal-administration role.
    MailPostmaster,
    /// Isolated synthetic staging role.
    StagingProbe,
}

/// Fixed outcomes and failure phases; never copy a provider error or dynamic phase name.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RoleCode {
    /// An unsupported recipient was rejected without inspecting its body.
    EmailRejected,
    /// Forwarding and its durable state update both completed.
    EmailAccepted,
    /// The handler failed; forwarding may be unknown in its existing D1 row.
    EmailFailed,
    /// The scheduled monitor failed without renewing an invalid lease.
    MonitorFailed,
    /// The full monitor completed and renewed its lease.
    MonitorHealthy,
    /// A content-free digest was accepted and its snapshot marked alerted.
    DigestAccepted,
    /// Digest handling failed.
    DigestFailed,
    /// Verified-destination audit failed.
    DestinationFailed,
    /// Exact-role routing audit failed.
    RoutesFailed,
    /// Outbox/forward-state/lease check failed.
    LeaseFailed,
}

impl RoleCode {
    /// Phase events are children of the invocation root, never Queue-consumer spans.
    pub fn is_phase(self) -> bool {
        matches!(
            self,
            Self::DigestAccepted
                | Self::DigestFailed
                | Self::DestinationFailed
                | Self::RoutesFailed
                | Self::LeaseFailed
        )
    }
}

/// Flat strict role schema; no local report UUID is needed for retained diagnostics.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RoleEvent {
    /// Only schema version one is accepted.
    pub schema_version: u8,
    /// Fixed producer identity; private to prevent unchecked construction.
    service: RoleService,
    /// Fresh producer-generated UUIDv4, stable if the Queue redelivers this event.
    pub event_id: String,
    /// Fresh invocation correlation ID; no incoming Email header is accepted as a parent.
    pub trace_id: String,
    /// Producer span identity, not the sink's Queue span.
    pub span_id: String,
    /// Invocation root span for phase events only.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub parent_span_id: Option<String>,
    /// Fixed diagnostic category.
    pub code: RoleCode,
    /// Present only for an accepted exact role.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub role: Option<RoleKind>,
    /// Power-of-two pending count or digest group count, capped at 2^32.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub count_bucket: Option<u64>,
}

impl RoleEvent {
    /// Construct an owned diagnostic without accepting arbitrary payload attributes.
    pub fn new(
        event_id: String,
        trace_id: String,
        span_id: String,
        parent_span_id: Option<String>,
        code: RoleCode,
        role: Option<RoleKind>,
        count_bucket: Option<u64>,
    ) -> Self {
        Self {
            schema_version: 1,
            service: RoleService::RoleMonitor,
            event_id,
            trace_id,
            span_id,
            parent_span_id,
            code,
            role,
            count_bucket,
        }
    }

    /// Enforce exact field combinations and bounded canonical correlation identifiers.
    pub fn valid(&self) -> bool {
        if self.schema_version != 1
            || !super::canonical_uuid(&self.event_id)
            || !super::valid_hex_id(&self.trace_id, 32)
            || !super::valid_hex_id(&self.span_id, 16)
            || self
                .parent_span_id
                .as_deref()
                .is_some_and(|id| !super::valid_hex_id(id, 16) || id == self.span_id)
            || self.code.is_phase() != self.parent_span_id.is_some()
            || self
                .count_bucket
                .is_some_and(|count| count > 1 << 32 || (count != 0 && !count.is_power_of_two()))
        {
            return false;
        }
        match self.code {
            RoleCode::EmailAccepted => self.role.is_some() && self.count_bucket.is_none(),
            RoleCode::MonitorHealthy => self.role.is_none() && self.count_bucket.is_some(),
            RoleCode::DigestAccepted => {
                self.role.is_none() && self.count_bucket.is_some_and(|n| (1..=8).contains(&n))
            }
            _ => self.role.is_none() && self.count_bucket.is_none(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    /// Use synthetic identifiers only; no live role metadata enters test fixtures.
    fn fixture() -> serde_json::Value {
        json!({"schema_version":1,"service":"role_monitor",
            "event_id":"00000000-0000-4000-8000-000000000002",
            "trace_id":"0123456789abcdef0123456789abcdef",
            "span_id":"abcdef0123456789","code":"email_accepted","role":"staging_probe"})
    }

    /// Role fields cannot widen the preexisting Mail event contract.
    #[test]
    fn distinct_roundtrip_without_wire_wrapper() {
        let record = crate::Record::from_value(fixture()).unwrap();
        assert_eq!(serde_json::to_value(record).unwrap(), fixture());
        assert!(crate::Event::from_value(fixture()).is_none());
    }

    /// Unknown fields, arbitrary labels and incompatible phase/aggregate fields fail closed.
    #[test]
    fn reject_unsafe_payloads() {
        for (key, value) in [
            ("sender", json!("synthetic@example.test")),
            ("destination", json!("synthetic@example.test")),
            ("subject", json!("synthetic")),
            ("body", json!("synthetic")),
            ("role", json!("synthetic@example.test")),
            ("code", json!("private-provider-error")),
            ("service", json!("mail_api")),
            ("event_id", json!("00000000-0000-0000-0000-000000000002")),
            ("trace_id", json!("0123456789ABCDEF0123456789abcdef")),
            ("span_id", json!("0000000000000000")),
            ("schema_version", json!(2)),
            ("count_bucket", json!(8)),
            ("parent_span_id", json!("0123456789abcdef")),
        ] {
            let mut value_fixture = fixture();
            value_fixture[key] = value;
            assert!(
                crate::Record::from_value(value_fixture).is_none(),
                "accepted {key}"
            );
        }
        let mut oversized = fixture();
        oversized["body"] = json!("x".repeat(1025));
        assert!(crate::Record::from_value(oversized).is_none());
    }

    /// Counts belong to two success codes only; failed phases require a distinct root parent.
    #[test]
    fn combinations_are_closed() {
        let mut healthy = fixture();
        healthy.as_object_mut().unwrap().remove("role");
        healthy["code"] = json!("monitor_healthy");
        healthy["count_bucket"] = json!(0);
        assert!(crate::Record::from_value(healthy.clone()).is_some());
        for n in [7, (1_u64 << 32) + 1] {
            healthy["count_bucket"] = json!(n);
            assert!(crate::Record::from_value(healthy.clone()).is_none());
        }
        healthy.as_object_mut().unwrap().remove("count_bucket");
        healthy["code"] = json!("destination_failed");
        assert!(crate::Record::from_value(healthy.clone()).is_none());
        healthy["parent_span_id"] = json!("0123456789abcdef");
        assert!(crate::Record::from_value(healthy.clone()).is_some());
        healthy["parent_span_id"] = healthy["span_id"].clone();
        assert!(crate::Record::from_value(healthy).is_none());
    }
}
