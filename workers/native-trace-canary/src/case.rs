//! Source-owned synthetic requests, never a forwarding interface for user input.

use serde::Serialize;

/// A comparison case preserves the same operational behavior with two URL policies.
#[derive(Clone, Copy, Debug, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Mode {
    /// Positive control: automatic native attributes may contain synthetic markers.
    Baseline,
    /// Test root-attribute replacement, without assuming it affects other records.
    Redacted,
}

impl Mode {
    /// Stable source-owned route label.
    pub fn label(self) -> &'static str {
        match self {
            Self::Baseline => "baseline",
            Self::Redacted => "redacted",
        }
    }
}

/// No arbitrary failure messages or payloads can enter the native exception test.
#[derive(Clone, Copy, Debug, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Kind {
    /// Successful HTTP and custom-span completion.
    Success,
    /// Deliberate fixed exception and HTTP 500, not a Rust panic or user error.
    Failure,
}

impl Kind {
    /// Stable source-owned route label.
    pub fn label(self) -> &'static str {
        match self {
            Self::Success => "success",
            Self::Failure => "failure",
        }
    }
    /// Expected observed status, independent of marker content.
    pub fn status(self) -> u16 {
        if self == Self::Success {
            200
        } else {
            500
        }
    }
}

/// One immutable case; the run ID is a public synthetic coordinate, not a credential.
#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub struct Case {
    /// Reviewed comparison mode.
    pub mode: Mode,
    /// Reviewed result class.
    pub kind: Kind,
    /// Lowercase 128-bit run coordinate, bounded before URL/header construction.
    pub run: String,
}

impl Case {
    /// Generate exactly four cases without accepting incoming request values.
    pub fn all(run: &str) -> Option<Vec<Self>> {
        if !valid_run(run) {
            return None;
        }
        Some(
            [Mode::Baseline, Mode::Redacted]
                .into_iter()
                .flat_map(|mode| {
                    [Kind::Success, Kind::Failure]
                        .into_iter()
                        .map(move |kind| Self {
                            mode,
                            kind,
                            run: run.into(),
                        })
                })
                .collect(),
        )
    }

    /// Parse only the controlled private probe path; unknown paths have no trace operation.
    pub fn from_path(path: &str) -> Option<Self> {
        let parts: Vec<_> = path.split('/').collect();
        if parts.len() != 4 || parts[0] != "" {
            return None;
        }
        let mode = match parts[1] {
            "baseline" => Mode::Baseline,
            "redacted" => Mode::Redacted,
            _ => return None,
        };
        let kind = match parts[2] {
            "success" => Kind::Success,
            "failure" => Kind::Failure,
            _ => return None,
        };
        let run = parts[3].strip_prefix("amail_native_path_")?;
        valid_run(run).then(|| Self {
            mode,
            kind,
            run: run.into(),
        })
    }

    /// Synthetic URL marker stands in for personal path/query metadata.
    pub fn url(&self) -> String {
        format!(
            "https://synthetic.invalid/{}/{}/amail_native_path_{}?query=amail_native_query_{}",
            self.mode.label(),
            self.kind.label(),
            self.run,
            self.run
        )
    }

    /// Distinct marker for a header normally reflected in automatic root attributes.
    pub fn header(&self) -> String {
        format!("amail_native_header_{}", self.run)
    }

    /// Distinct protected-content marker; no actual mail is sent or processed.
    pub fn body(&self) -> String {
        format!("amail_native_body_{}", self.run)
    }
}

/// Reject unbounded or personal-looking run coordinates before constructing requests.
fn valid_run(run: &str) -> bool {
    run.len() == 32
        && run.bytes().any(|b| b != b'0')
        && run
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

#[cfg(test)]
mod tests {
    use super::*;
    const RUN: &str = "0123456789abcdef0123456789abcdef";

    /// All comparisons differ only by reviewed mode/result, not caller input.
    #[test]
    fn four_roundtrippable_cases_have_distinct_content_origins() {
        let cases = Case::all(RUN).unwrap();
        assert_eq!(cases.len(), 4);
        for case in cases {
            let path = case
                .url()
                .split('?')
                .next()
                .unwrap()
                .strip_prefix("https://synthetic.invalid")
                .unwrap()
                .to_owned();
            assert_eq!(Case::from_path(&path), Some(case.clone()));
            assert!(case.body().starts_with("amail_native_body_"));
            assert_ne!(case.body(), case.header());
        }
    }

    /// A future public caller cannot smuggle its query/body/identity into the probe factory.
    #[test]
    fn invalid_modes_paths_and_personal_run_ids_are_rejected() {
        for run in [
            "",
            "user@example.test",
            "0123456789ABCDEF0123456789abcdef",
            &"a".repeat(33),
        ] {
            assert!(Case::all(run).is_none());
        }
        for path in [
            "/unknown/success/amail_native_path_0123456789abcdef0123456789abcdef",
            "/baseline/panic/amail_native_path_0123456789abcdef0123456789abcdef",
            "/baseline/success/amail_native_path_user@example.test",
            "/extra/baseline/success/a",
        ] {
            assert!(Case::from_path(path).is_none());
        }
    }
}
