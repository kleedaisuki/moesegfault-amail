//! Invocation-local typed diagnostics. This module never accepts Email messages or raw errors.

use amail_trace_schema::{RoleCode, RoleEvent, RoleKind};
use uuid::Uuid;

/// A monitor has four phases and at most one digest; reserve one final outcome slot.
const MAX_EVENTS: usize = 8;

/// One fresh causal root per Email/Cron invocation; never reuse reporter headers or D1 report IDs.
pub(crate) struct Diagnostics {
    trace_id: String,
    root_span: String,
    events: Vec<RoleEvent>,
}

impl Diagnostics {
    /// Generate correlation state before any dependency work can fail.
    pub(crate) fn new() -> Self {
        Self {
            trace_id: Uuid::new_v4().simple().to_string(),
            root_span: random_span(),
            events: Vec::new(),
        }
    }

    /// Append a fixed child outcome without consuming the final invocation slot.
    pub(crate) fn phase(&mut self, code: RoleCode, count: Option<u64>) {
        if !code.is_phase() || self.events.len() >= MAX_EVENTS - 1 {
            return;
        }
        let mut span = random_span();
        while span == self.root_span {
            span = random_span();
        }
        let event = self.event(code, span, Some(self.root_span.clone()), None, count);
        if event.valid() {
            self.events.push(event);
        }
    }

    /// Finalize one root outcome, preserving child correlation and owned safe data only.
    pub(crate) fn finish(
        mut self,
        code: RoleCode,
        role: Option<RoleKind>,
        count: Option<u64>,
    ) -> Vec<RoleEvent> {
        if !code.is_phase() {
            let event = self.event(code, self.root_span.clone(), None, role, count);
            if event.valid() {
                self.events.push(event);
            }
        }
        self.events
    }

    /// Construct only the shared closed contract; do not add dynamic attributes.
    fn event(
        &self,
        code: RoleCode,
        span: String,
        parent: Option<String>,
        role: Option<RoleKind>,
        count: Option<u64>,
    ) -> RoleEvent {
        RoleEvent::new(
            Uuid::new_v4().to_string(),
            self.trace_id.clone(),
            span,
            parent,
            code,
            role,
            count.map(bucket),
        )
    }
}

/// The UUID variant nibble in this half makes an all-zero span impossible.
fn random_span() -> String {
    Uuid::new_v4().simple().to_string()[16..].to_string()
}

/// Fixed power-of-two aggregates bound precision and cannot overflow.
fn bucket(value: u64) -> u64 {
    if value == 0 {
        0
    } else {
        value.min(1 << 32).next_power_of_two()
    }
}

/// Best-effort bounded handoff; diagnostic failure never changes forwarding or health semantics.
/// No Env, message, destination, error object or console fallback crosses this boundary.
pub(crate) async fn flush(queue: worker::Queue, events: Vec<RoleEvent>) {
    if events.is_empty()
        || events.len() > MAX_EVENTS
        || events.iter().any(|event| {
            !event.valid() || serde_json::to_vec(event).map_or(true, |encoded| encoded.len() > 1024)
        })
    {
        return;
    }
    let batch = worker::BatchMessageBuilder::new().messages(events).build();
    let _ = queue.send_batch(batch).await;
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A full optional buffer cannot drop the original root failure or change its parentage.
    #[test]
    fn bounded_buffer_preserves_root() {
        let mut diagnostics = Diagnostics::new();
        for _ in 0..20 {
            diagnostics.phase(RoleCode::DestinationFailed, None);
        }
        let events = diagnostics.finish(RoleCode::MonitorFailed, None, None);
        assert_eq!(events.len(), MAX_EVENTS);
        assert!(events.iter().all(RoleEvent::valid));
        let root = events.last().unwrap();
        assert_eq!(root.code, RoleCode::MonitorFailed);
        assert!(root.parent_span_id.is_none());
        for event in &events[..MAX_EVENTS - 1] {
            assert_eq!(event.trace_id, root.trace_id);
            assert_eq!(event.parent_span_id.as_deref(), Some(root.span_id.as_str()));
            assert!(serde_json::to_vec(event).unwrap().len() <= 1024);
        }
    }

    /// Only accepted roles and reviewed aggregate fields can appear in final outcomes.
    #[test]
    fn typed_email_and_cron_outcomes() {
        let events =
            Diagnostics::new().finish(RoleCode::EmailAccepted, Some(RoleKind::StagingProbe), None);
        assert_eq!(events.len(), 1);
        assert!(events[0].valid());
        let mut diagnostics = Diagnostics::new();
        diagnostics.phase(RoleCode::DigestAccepted, Some(5));
        let events = diagnostics.finish(RoleCode::MonitorHealthy, None, Some(u64::MAX));
        assert_eq!(events[0].count_bucket, Some(8));
        assert_eq!(events[1].count_bucket, Some(1 << 32));
        assert!(events.iter().all(RoleEvent::valid));
        assert_eq!(bucket(0), 0);
    }
}
