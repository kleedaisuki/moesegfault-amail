//! Closed client attempt boundaries shared by upload and Queue readers.

use serde::{Deserialize, Serialize};

/// The observed end of one attempt, not JSON interpretation or a whole command.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ClientPhase {
    /// Credentials were unavailable before sending a request.
    Auth,
    /// No response headers arrived.
    Transport,
    /// Headers arrived but the complete response body did not.
    ResponseBody,
    /// The complete exchange arrived, including HTTP error responses.
    Complete,
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Legacy, complete-error and each failure boundary have distinct header semantics.
    #[test]
    fn boundaries_preserve_headers_without_inventing_success() {
        assert!(ClientAttempt::default().valid(0));
        for (phase, error_kind, status, failed) in [
            (
                ClientPhase::Auth,
                Some(ClientErrorKind::CredentialUnavailable),
                0,
                true,
            ),
            (
                ClientPhase::Transport,
                Some(ClientErrorKind::Connect),
                0,
                true,
            ),
            (
                ClientPhase::ResponseBody,
                Some(ClientErrorKind::Body),
                200,
                true,
            ),
            (
                ClientPhase::ResponseBody,
                Some(ClientErrorKind::Timeout),
                503,
                true,
            ),
            (ClientPhase::Complete, None, 200, false),
            (ClientPhase::Complete, None, 503, false),
        ] {
            let attempt = ClientAttempt {
                started_at_ms: Some(1_790_000_000_123),
                elapsed_ms: Some(121_007),
                phase: Some(phase),
                error_kind,
            };
            assert!(attempt.valid(status));
            assert_eq!(attempt.failed(), failed);
            // UTC acquisition may fail; do not fabricate a producer clock.
            assert!(ClientAttempt {
                started_at_ms: None,
                ..attempt
            }
            .valid(status));
            assert!(!ClientAttempt {
                elapsed_ms: None,
                ..attempt
            }
            .valid(status));
            assert!(!ClientAttempt {
                elapsed_ms: Some(crate::MAX_SAFE_INTEGER + 1),
                ..attempt
            }
            .valid(status));
            assert!(!ClientAttempt {
                started_at_ms: Some(crate::MAX_SAFE_INTEGER + 1),
                ..attempt
            }
            .valid(status));
        }
    }

    /// Partial fields and contradictory boundary/error pairs are not accepted.
    #[test]
    fn boundary_pairs_are_closed() {
        assert!(!ClientAttempt {
            elapsed_ms: Some(1),
            ..Default::default()
        }
        .valid(200));
        for (phase, error_kind, status) in [
            (ClientPhase::Auth, None, 0),
            (ClientPhase::Auth, Some(ClientErrorKind::Timeout), 0),
            (
                ClientPhase::Auth,
                Some(ClientErrorKind::CredentialUnavailable),
                200,
            ),
            (ClientPhase::Transport, Some(ClientErrorKind::Connect), 200),
            (ClientPhase::ResponseBody, Some(ClientErrorKind::Body), 0),
            (ClientPhase::Complete, Some(ClientErrorKind::Decode), 200),
            (ClientPhase::Complete, None, 0),
        ] {
            assert!(!ClientAttempt {
                elapsed_ms: Some(1),
                phase: Some(phase),
                error_kind,
                ..Default::default()
            }
            .valid(status));
        }
    }
}

/// Fixed library-level causes, never URLs, exception text or credential data.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ClientErrorKind {
    /// Credential acquisition did not complete.
    CredentialUnavailable,
    /// The client deadline expired.
    Timeout,
    /// Establishing the connection failed.
    Connect,
    /// Reading the response stream failed.
    Body,
    /// Response decoding failed.
    Decode,
    /// Constructing or issuing the request failed.
    Request,
    /// An uncategorized client library failure occurred.
    Other,
}

/// Optional additive reader metadata; entirely absent means a legacy attempt.
/// A missing UTC clock remains unknown, while an enriched attempt requires elapsed time.
#[derive(Clone, Copy, Debug, Default)]
pub struct ClientAttempt {
    /// Producer UTC start time in milliseconds, never upload/Queue receipt time.
    pub started_at_ms: Option<u64>,
    /// Exact monotonic milliseconds frozen before diagnostic persistence.
    pub elapsed_ms: Option<u64>,
    /// Observed completion or failure boundary.
    pub phase: Option<ClientPhase>,
    /// Safe failure cause; successful exchanges have no library error.
    pub error_kind: Option<ClientErrorKind>,
}

impl ClientAttempt {
    /// Whether any additive field is present; partial enrichments cannot masquerade as legacy.
    pub fn enriched(self) -> bool {
        self.started_at_ms.is_some()
            || self.elapsed_ms.is_some()
            || self.phase.is_some()
            || self.error_kind.is_some()
    }

    /// Validate numeric precision and whether response headers existed at the boundary.
    pub fn valid(self, status: u16) -> bool {
        if !self.enriched() {
            return true;
        }
        if self
            .started_at_ms
            .is_some_and(|n| n > crate::MAX_SAFE_INTEGER)
            || self.elapsed_ms.is_none_or(|n| n > crate::MAX_SAFE_INTEGER)
        {
            return false;
        }
        match (self.phase, self.error_kind) {
            (Some(ClientPhase::Auth), Some(ClientErrorKind::CredentialUnavailable)) => status == 0,
            (Some(ClientPhase::Transport), Some(kind)) => {
                status == 0 && kind != ClientErrorKind::CredentialUnavailable
            }
            (Some(ClientPhase::ResponseBody), Some(kind)) => {
                (100..=599).contains(&status) && kind != ClientErrorKind::CredentialUnavailable
            }
            (Some(ClientPhase::Complete), None) => (100..=599).contains(&status),
            _ => false,
        }
    }

    /// A received 2xx header does not make a truncated body a successful attempt.
    pub fn failed(self) -> bool {
        matches!(
            self.phase,
            Some(ClientPhase::Auth | ClientPhase::Transport | ClientPhase::ResponseBody)
        )
    }
}
