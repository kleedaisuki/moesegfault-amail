//! Bounded, request-local diagnostics for authenticated staging address creation.

/// A closed stage vocabulary; no address, SQL, rule ID, or arbitrary error text is retained.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum Stage {
    Input,
    D1Lookup,
    D1Allocate,
    D1Claim,
    RoutingList,
    RoutingCreate,
    D1Activate,
    D1Readback,
    ResponseEncode,
    Success,
}

impl Stage {
    /// Map a stage to its stable ASCII header token.
    fn wire(self) -> &'static str {
        match self {
            Self::Input => "input",
            Self::D1Lookup => "d1_lookup",
            Self::D1Allocate => "d1_allocate",
            Self::D1Claim => "d1_claim",
            Self::RoutingList => "routing_list",
            Self::RoutingCreate => "routing_create",
            Self::D1Activate => "d1_activate",
            Self::D1Readback => "d1_readback",
            Self::ResponseEncode => "response_encode",
            Self::Success => "success",
        }
    }

    /// Classify an unannotated `?` by the boundary currently in progress.
    fn default_kind(self) -> Kind {
        match self {
            Self::Input => Kind::Request,
            Self::D1Lookup
            | Self::D1Allocate
            | Self::D1Claim
            | Self::D1Activate
            | Self::D1Readback => Kind::D1,
            Self::RoutingList | Self::RoutingCreate => Kind::Request,
            Self::ResponseEncode => Kind::Decode,
            Self::Success => Kind::None,
        }
    }
}

/// Closed failure-kind vocabulary; provider errors are not copied into the header.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum Kind {
    None,
    Request,
    Http,
    Provider,
    Decode,
    D1,
    State,
}

impl Kind {
    /// Map a failure kind to its stable ASCII header token.
    fn wire(self) -> &'static str {
        match self {
            Self::None => "none",
            Self::Request => "request",
            Self::Http => "http",
            Self::Provider => "provider",
            Self::Decode => "decode",
            Self::D1 => "d1",
            Self::State => "state",
        }
    }
}

/// One invocation's first relevant boundary, not a persistent trace or a retry signal.
pub(crate) struct AddressDiag {
    /// The last boundary entered before success or the first returned failure.
    stage: Stage,
    /// An optional precise classification containing only bounded numeric provider facts.
    failure: Option<(Kind, u16, u32)>,
}

impl AddressDiag {
    /// Start before parsing the authenticated request body.
    pub(crate) fn new() -> Self {
        Self {
            stage: Stage::Input,
            failure: None,
        }
    }

    /// Set the stage before an operation that can return an error.
    pub(crate) fn enter(&mut self, stage: Stage) {
        self.stage = stage;
        self.failure = None;
    }

    /// Record only observed provider numeric facts, rejecting out-of-contract values.
    pub(crate) fn fail(&mut self, kind: Kind, status: Option<u16>, code: Option<u32>) {
        let status = status
            .filter(|value| (100..=599).contains(value))
            .unwrap_or(0);
        let code = code
            .filter(|value| (1000..=999_999).contains(value))
            .unwrap_or(0);
        self.failure = Some((kind, status, code));
    }

    /// A successful response, including an idempotent 200 or pending 202, has no failure.
    pub(crate) fn success(&mut self) {
        self.enter(Stage::Success);
    }

    /// Emit one ASCII-only, fixed-grammar value; zero means the numeric fact was unavailable.
    pub(crate) fn header(&self, success: bool) -> String {
        let (stage, kind, status, code) = if success {
            (Stage::Success, Kind::None, 0, 0)
        } else {
            let (kind, status, code) = self.failure.unwrap_or((self.stage.default_kind(), 0, 0));
            (self.stage, kind, status, code)
        };
        format!("v1:{}:{}:{status}:{code}", stage.wire(), kind.wire())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The header cannot reflect arbitrary text and suppresses invalid numeric facts.
    #[test]
    fn grammar_and_bounds() {
        let mut diag = AddressDiag::new();
        assert_eq!(diag.header(false), "v1:input:request:0:0");
        diag.enter(Stage::RoutingCreate);
        diag.fail(Kind::Provider, Some(403), Some(10000));
        assert_eq!(diag.header(false), "v1:routing_create:provider:403:10000");
        diag.fail(Kind::Provider, Some(99), Some(u32::MAX));
        assert_eq!(diag.header(false), "v1:routing_create:provider:0:0");
        diag.success();
        assert_eq!(diag.header(true), "v1:success:none:0:0");
    }
}
