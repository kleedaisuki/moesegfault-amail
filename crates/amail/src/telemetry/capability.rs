//! One origin/Identity-realm capability observation, never user/credential state.

use super::delivery;
use crate::config::Runtime;
use amail_trace_schema::{ATTEMPT_CAPABILITY, ATTEMPT_UPLOAD_PATH, CAPABILITY_HEADER};
use anyhow::Result;
use reqwest::header::HeaderMap;
use rusqlite::{params, Connection, OptionalExtension};

/// Freshness limits dormant observations; the explicit upload path provides rollback safety.
const FRESH_MS: i64 = 300_000;

/// Support is explicit, not inferred from status, a binding, or a generic version string.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) enum Capability {
    /// Absent/unknown/expired capability uses the old strict body and route.
    Legacy,
    /// The exact authenticated response contract was observed in this API realm.
    Attempts,
}

impl Capability {
    /// The old route never receives enriched fields, even after a server rollback.
    pub(super) fn path(self) -> &'static str {
        match self {
            Self::Legacy => "/v1/telemetry",
            Self::Attempts => ATTEMPT_UPLOAD_PATH,
        }
    }
}

/// Metadata learned from complete headers; body/command success is independent.
#[derive(Clone, Copy)]
pub(super) struct Observation {
    /// Only a single exact field from the configured response origin is supported.
    capability: Capability,
    /// UTC header arrival, not body completion or SQLite persistence time.
    observed_at_ms: Option<i64>,
}

/// Canonical configured origin excludes path/query/credentials by Runtime policy.
fn origin(cfg: &Runtime) -> Result<String> {
    Ok(url::Url::parse(&cfg.api_base)?
        .origin()
        .ascii_serialization())
}

impl Observation {
    /// Duplicate/unknown/cross-origin fields invalidate a prior observation.
    /// Unauthorized responses cannot establish an authenticated capability.
    pub(super) fn headers(
        cfg: &Runtime,
        headers: &HeaderMap,
        response_url: &url::Url,
        status: u16,
    ) -> Self {
        let mut values = headers.get_all(CAPABILITY_HEADER).iter();
        let exact = values.next().and_then(|value| value.to_str().ok()) == Some(ATTEMPT_CAPABILITY)
            && values.next().is_none();
        let same_origin = url::Url::parse(&cfg.api_base)
            .ok()
            .is_some_and(|configured| configured.origin() == response_url.origin());
        Self {
            capability: if exact && same_origin && status != 401 {
                Capability::Attempts
            } else {
                Capability::Legacy
            },
            observed_at_ms: delivery::utc_ms(),
        }
    }

    /// Replace the one bounded cache row; no token, credential fingerprint or user subject.
    pub(super) fn store(self, conn: &Connection, cfg: &Runtime) -> Result<()> {
        conn.execute("INSERT INTO journal_capability(id,api_origin,issuer,client_id,supported,observed_at_ms)
            VALUES(1,?1,?2,?3,?4,?5) ON CONFLICT(id) DO UPDATE SET api_origin=excluded.api_origin,
            issuer=excluded.issuer,client_id=excluded.client_id,supported=excluded.supported,
            observed_at_ms=excluded.observed_at_ms", params![origin(cfg)?, cfg.issuer, cfg.client_id,
                (self.capability == Capability::Attempts) as i64, self.observed_at_ms])?;
        Ok(())
    }
}

/// Diagnostic-only cache schema in the historical shared physical file.
pub(super) fn schema(conn: &Connection) -> Result<()> {
    conn.execute_batch(
        "CREATE TABLE IF NOT EXISTS journal_capability (
        id INTEGER PRIMARY KEY CHECK(id=1), api_origin TEXT NOT NULL, issuer TEXT NOT NULL,
        client_id TEXT NOT NULL, supported INTEGER NOT NULL, observed_at_ms INTEGER
    )",
    )?;
    Ok(())
}

/// Unknown observations/errors never become support; time rollback/future clocks are stale.
pub(super) fn load(conn: &Connection, cfg: &Runtime) -> Result<Capability> {
    let Some(now) = delivery::utc_ms() else {
        return Ok(Capability::Legacy);
    };
    load_at(conn, cfg, now)
}

/// Pure clock input permits deterministic freshness/rollback tests without changing system time.
fn load_at(conn: &Connection, cfg: &Runtime, now: i64) -> Result<Capability> {
    let supported = conn
        .query_row(
            "SELECT supported=1 AND observed_at_ms IS NOT NULL
        AND observed_at_ms<=?4 AND observed_at_ms>=?4-?5 FROM journal_capability
        WHERE id=1 AND api_origin=?1 AND issuer=?2 AND client_id=?3",
            params![origin(cfg)?, cfg.issuer, cfg.client_id, now, FRESH_MS],
            |row| row.get::<_, bool>(0),
        )
        .optional()?;
    Ok(if supported == Some(true) {
        Capability::Attempts
    } else {
        Capability::Legacy
    })
}

/// A404 on the explicit route is a rollback/unsupported route, never an invitation to retry now.
pub(super) fn unsupported(conn: &Connection, cfg: &Runtime) -> Result<()> {
    Observation {
        capability: Capability::Legacy,
        observed_at_ms: delivery::utc_ms(),
    }
    .store(conn, cfg)
}

#[cfg(test)]
mod tests {
    use super::*;
    use reqwest::header::HeaderValue;

    /// In-memory diagnostic state has no identity/keyring/provider dependency.
    fn fixture() -> (Connection, Runtime) {
        let conn = Connection::open_in_memory().unwrap();
        schema(&conn).unwrap();
        let cfg = super::super::tests::config(std::path::Path::new("synthetic-home"));
        (conn, cfg)
    }

    /// Only one exact same-origin authenticated announcement establishes support.
    #[test]
    fn exact_missing_duplicate_future_cross_origin_and_unauthorized_fields_are_distinct() {
        let (conn, cfg) = fixture();
        let url = url::Url::parse(&cfg.api_base).unwrap();
        for (values, response_url, status, expected) in [
            (
                vec![ATTEMPT_CAPABILITY],
                url.clone(),
                200,
                Capability::Attempts,
            ),
            (vec![], url.clone(), 200, Capability::Legacy),
            (vec!["attempts-v2"], url.clone(), 200, Capability::Legacy),
            (
                vec!["SYNTHETIC_PRIVATE_CAPABILITY"],
                url.clone(),
                200,
                Capability::Legacy,
            ),
            (
                vec![ATTEMPT_CAPABILITY, ATTEMPT_CAPABILITY],
                url.clone(),
                200,
                Capability::Legacy,
            ),
            (
                vec![ATTEMPT_CAPABILITY],
                url::Url::parse("https://other.example.test/").unwrap(),
                200,
                Capability::Legacy,
            ),
            (
                vec![ATTEMPT_CAPABILITY],
                url.clone(),
                401,
                Capability::Legacy,
            ),
            (
                vec![ATTEMPT_CAPABILITY],
                url.clone(),
                503,
                Capability::Attempts,
            ),
        ] {
            let mut headers = HeaderMap::new();
            for value in values {
                headers.append(CAPABILITY_HEADER, HeaderValue::from_str(value).unwrap());
            }
            let observation = Observation::headers(&cfg, &headers, &response_url, status);
            assert_eq!(observation.capability, expected);
            observation.store(&conn, &cfg).unwrap();
            assert_eq!(
                load_at(&conn, &cfg, observation.observed_at_ms.unwrap()).unwrap(),
                expected
            );
        }
        assert_eq!(
            conn.query_row("SELECT COUNT(*) FROM journal_capability", [], |r| r
                .get::<_, i64>(0))
                .unwrap(),
            1
        );
    }

    /// API origin/issuer/audience changes and unknown or future clocks cannot inherit support.
    #[test]
    fn cache_is_bounded_to_realm_freshness_and_actual_observation_time() {
        let (conn, cfg) = fixture();
        Observation {
            capability: Capability::Attempts,
            observed_at_ms: Some(1_790_000_000_123),
        }
        .store(&conn, &cfg)
        .unwrap();
        assert_eq!(
            load_at(&conn, &cfg, 1_790_000_000_123 + FRESH_MS).unwrap(),
            Capability::Attempts
        );
        for now in [1_790_000_000_122, 1_790_000_000_124 + FRESH_MS] {
            assert_eq!(load_at(&conn, &cfg, now).unwrap(), Capability::Legacy);
        }
        for changed in [
            Runtime {
                api_base: "https://other.example.test".into(),
                ..cfg.clone()
            },
            Runtime {
                issuer: "https://identity-staging.example.test".into(),
                ..cfg.clone()
            },
            Runtime {
                client_id: "other-client".into(),
                ..cfg.clone()
            },
        ] {
            assert_eq!(
                load_at(&conn, &changed, 1_790_000_000_123).unwrap(),
                Capability::Legacy
            );
        }
        Observation {
            capability: Capability::Attempts,
            observed_at_ms: None,
        }
        .store(&conn, &cfg)
        .unwrap();
        assert_eq!(
            load_at(&conn, &cfg, 1_790_000_000_123).unwrap(),
            Capability::Legacy
        );
        unsupported(&conn, &cfg).unwrap();
        assert_eq!(load(&conn, &cfg).unwrap(), Capability::Legacy);
    }
}
