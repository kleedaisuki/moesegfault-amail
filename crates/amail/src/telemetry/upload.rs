//! One bounded detached upload; delivery receipts never recursively become events.

use super::{delivery, Event};
use crate::{api, auth, config::Runtime};
use anyhow::Result;
use delivery::{Attempt, Outcome};
use reqwest::blocking::{Client, Response};
use rusqlite::Connection;
use std::io::Read;
use std::time::Duration;

/// Legacy acknowledgements are tiny; read one overflow sentinel, never an arbitrary body.
const ACK_LIMIT: u64 = 4096;

/// Execute the legacy-compatible batch without holding a database transaction over I/O.
pub(super) fn run(cfg: &Runtime, scheduled_id: Option<&uuid::Uuid>) -> Result<()> {
    let conn = super::db(cfg)?;
    let http = Client::builder()
        .timeout(Duration::from_secs(5))
        .redirect(reqwest::redirect::Policy::none())
        .build();
    run_with(cfg, &conn, scheduled_id, || auth::access_token(cfg), http)
}

/// Credential/client injection is a test seam, not a production retry/provider abstraction.
fn run_with(
    cfg: &Runtime,
    conn: &Connection,
    scheduled_id: Option<&uuid::Uuid>,
    token: impl FnOnce() -> Result<String>,
    http: reqwest::Result<Client>,
) -> Result<()> {
    let Some(attempt) = delivery::begin(conn, scheduled_id, 0)? else {
        return Ok(());
    };
    let selected = match pending(conn) {
        Ok(selected) => selected,
        Err(_) => {
            return attempt.finish(
                conn,
                &[],
                Outcome::Failed,
                "journal",
                Some("journal_read"),
                None,
                None,
            )
        }
    };
    let ids: Vec<_> = selected.iter().map(|(id, _)| *id).collect();
    attempt.batch_count(conn, ids.len())?;
    if ids.is_empty() {
        return attempt.finish(conn, &[], Outcome::Empty, "complete", None, None, None);
    }
    attempt.phase(conn, "auth", None, None)?;
    let token = match token() {
        Ok(token) => token,
        Err(_) => {
            return attempt.finish(
                conn,
                &ids,
                Outcome::Failed,
                "auth",
                Some("credential_unavailable"),
                None,
                None,
            )
        }
    };
    let http = match http {
        Ok(http) => http,
        Err(_) => {
            return attempt.finish(
                conn,
                &ids,
                Outcome::Failed,
                "transport",
                Some("request"),
                None,
                None,
            )
        }
    };
    let events: Vec<_> = selected.into_iter().map(|(_, event)| event).collect();
    send(cfg, conn, attempt, &ids, &token, &http, &events)
}

/// Select at most twenty historical wire records; do not enrich the current producer.
fn pending(conn: &Connection) -> Result<Vec<(i64, Event)>> {
    let tx = delivery::transaction(conn)?;
    delivery::prune(&tx)?;
    let items = {
        let mut stmt = tx.prepare(
            "SELECT id,operation,status,duration_ms,bytes_bucket,trace_id,span_id,correlation_id
            FROM events WHERE uploaded=0 ORDER BY id LIMIT 20",
        )?;
        let rows = stmt.query_map([], |row| {
            Ok((
                row.get(0)?,
                Event {
                    operation: row.get(1)?,
                    status: row.get(2)?,
                    duration_ms: row.get(3)?,
                    bytes_bucket: row.get(4)?,
                    trace_id: row.get(5)?,
                    span_id: row.get(6)?,
                    correlation_id: row.get(7)?,
                },
            ))
        })?;
        rows.collect::<std::result::Result<Vec<_>, _>>()?
    };
    tx.commit()?;
    Ok(items)
}

/// Read a complete typed acknowledgement before marking rows locally accepted.
fn send(
    cfg: &Runtime,
    conn: &Connection,
    attempt: Attempt,
    ids: &[i64],
    token: &str,
    http: &Client,
    events: &[Event],
) -> Result<()> {
    attempt.phase(conn, "transport", None, None)?;
    let response = http
        .post(format!("{}/v1/telemetry", cfg.api_base))
        .bearer_auth(token)
        .json(&serde_json::json!({"events":events}))
        .send();
    let response = match response {
        Ok(response) => response,
        Err(error) => {
            let outcome = if error.is_builder() {
                Outcome::Failed
            } else {
                Outcome::Unknown
            };
            return attempt.finish(
                conn,
                ids,
                outcome,
                "transport",
                Some(if error.is_builder() {
                    "request"
                } else {
                    api::transport_kind(&error)
                }),
                None,
                None,
            );
        }
    };
    let status = response.status();
    let correlation = api::response_correlation(response.headers());
    if !status.is_success() {
        return attempt.finish(
            conn,
            ids,
            Outcome::Failed,
            "response_headers",
            None,
            Some(status.as_u16()),
            correlation.as_deref(),
        );
    }
    attempt.phase(
        conn,
        "response_body",
        Some(status.as_u16()),
        correlation.as_deref(),
    )?;
    let (outcome, phase, kind) = match acknowledgement(response, ids.len()) {
        Ok(()) => (Outcome::Accepted, "complete", None),
        Err((phase, kind)) => (Outcome::Unknown, phase, Some(kind)),
    };
    attempt.finish(
        conn,
        ids,
        outcome,
        phase,
        kind,
        Some(status.as_u16()),
        correlation.as_deref(),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use std::net::{TcpListener, TcpStream};

    /// Separate synthetic homes keep credentials and production state out of all tests.
    fn fixture() -> (tempfile::TempDir, Runtime, Connection) {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.temp");
        std::fs::create_dir_all(&root).unwrap();
        let home = tempfile::tempdir_in(root).unwrap();
        let cfg = super::super::tests::config(home.path());
        let conn = super::super::db(&cfg).unwrap();
        conn.execute(
            "INSERT INTO events(operation,status,duration_ms,bytes_bucket,trace_id)
            VALUES('messages.list',200,7,0,'0123456789abcdef0123456789abcdef')",
            [],
        )
        .unwrap();
        (home, cfg, conn)
    }

    /// Read the actual bounded legacy JSON request across arbitrary TCP fragmentation.
    fn request(stream: &mut TcpStream) -> serde_json::Value {
        stream
            .set_read_timeout(Some(Duration::from_secs(5)))
            .unwrap();
        let mut received = Vec::new();
        let mut buffer = [0; 1024];
        let header_end = loop {
            let n = stream.read(&mut buffer).unwrap();
            assert!(n > 0 && received.len() < 8192);
            received.extend_from_slice(&buffer[..n]);
            if let Some(end) = received.windows(4).position(|bytes| bytes == b"\r\n\r\n") {
                break end + 4;
            }
        };
        let headers = String::from_utf8_lossy(&received[..header_end]).to_ascii_lowercase();
        let length = headers
            .lines()
            .find_map(|line| line.strip_prefix("content-length:"))
            .unwrap()
            .trim()
            .parse::<usize>()
            .unwrap();
        while received.len() < header_end + length {
            let n = stream.read(&mut buffer).unwrap();
            assert!(n > 0 && received.len() < 8192);
            received.extend_from_slice(&buffer[..n]);
        }
        serde_json::from_slice(&received[header_end..header_end + length]).unwrap()
    }

    /// Extract only typed receipt fields, never HTTP or credential messages.
    fn receipt(
        conn: &Connection,
    ) -> (
        String,
        String,
        Option<String>,
        Option<u16>,
        Option<String>,
        i64,
        i64,
    ) {
        conn.query_row(
            "SELECT outcome,phase,error_kind,http_status,correlation_id,
            started_at_ms,elapsed_ms FROM journal_upload",
            [],
            |r| {
                Ok((
                    r.get(0)?,
                    r.get(1)?,
                    r.get(2)?,
                    r.get(3)?,
                    r.get(4)?,
                    r.get(5)?,
                    r.get(6)?,
                ))
            },
        )
        .unwrap()
    }

    /// Actual HTTP acceptance/refusal/truncation/poison/overflow cannot silently mark delivery.
    #[test]
    fn uploads_require_complete_bounded_acknowledgement_and_preserve_legacy_json() {
        let marker = "SYNTHETIC_PRIVATE_UPLOAD_MARKER";
        let correlation = "123e4567-e89b-42d3-a456-426614174000";
        for (status, body, declared, expected, kind) in [
            (
                202,
                format!("{{\"accepted\":1,\"private\":\"{marker}\"}}"),
                Some(0),
                "accepted",
                None,
            ),
            (202, "{\"accepted\":1}".into(), Some(0), "accepted", None),
            (503, marker.into(), Some(0), "failed", None),
            (202, "cut".into(), Some(100), "unknown", Some("body")),
            (
                202,
                "{\"accepted\":0}".into(),
                Some(0),
                "unknown",
                Some("ack_invalid"),
            ),
            (202, marker.into(), Some(0), "unknown", Some("ack_invalid")),
            (
                202,
                "x".repeat(4097),
                Some(0),
                "unknown",
                Some("ack_oversize"),
            ),
            (202, "x".repeat(4097), None, "unknown", Some("ack_oversize")),
        ] {
            let (_home, mut cfg, conn) = fixture();
            let listener = TcpListener::bind("127.0.0.1:0").unwrap();
            cfg.api_base = format!("http://{}", listener.local_addr().unwrap());
            let store_path = cfg.home.join("telemetry.sqlite3");
            let poisoned_header = body == "{\"accepted\":1}";
            let peer = std::thread::spawn(move || {
                let (mut stream, _) = listener.accept().unwrap();
                let sent = request(&mut stream);
                // Prove the uploader does not hold the shared database writer over HTTP I/O.
                let other = Connection::open(store_path).unwrap();
                other.busy_timeout(Duration::from_millis(250)).unwrap();
                other
                    .execute(
                        "INSERT INTO journal_state(key,value) VALUES('network_writer',1)",
                        [],
                    )
                    .unwrap();
                let correlation = if poisoned_header { marker } else { correlation };
                let response = match declared {
                    Some(n) => format!("HTTP/1.1 {status} Test\r\nContent-Length: {}\r\nX-Amail-Request-Id: {correlation}\r\nConnection: close\r\n\r\n{body}", if n == 0 { body.len() } else { n }),
                    None => format!("HTTP/1.1 {status} Test\r\nTransfer-Encoding: chunked\r\nX-Amail-Request-Id: {correlation}\r\nConnection: close\r\n\r\n{:x}\r\n{body}\r\n0\r\n\r\n", body.len()),
                };
                // An oversized/failed reply may correctly be dropped before the peer finishes writing.
                let _ = stream.write_all(response.as_bytes());
                sent
            });
            run_with(
                &cfg,
                &conn,
                None,
                || {
                    assert!(conn.is_autocommit());
                    Ok("SYNTHETIC_PRIVATE_TOKEN".into())
                },
                Client::builder().timeout(Duration::from_secs(5)).build(),
            )
            .unwrap();
            assert_eq!(
                peer.join().unwrap(),
                serde_json::json!({"events":[{
                "operation":"messages.list","status":200,"duration_ms":7,"bytes_bucket":0,
                "trace_id":"0123456789abcdef0123456789abcdef","correlation_id":null}]})
            );
            let row = receipt(&conn);
            assert_eq!(row.0, expected);
            assert_eq!(row.2.as_deref(), kind);
            assert_eq!(row.3, Some(status));
            assert_eq!(
                row.4.as_deref(),
                if poisoned_header {
                    None
                } else {
                    Some(correlation)
                }
            );
            assert!(row.5 > 0 && row.6 >= 0);
            let uploaded: i64 = conn
                .query_row("SELECT uploaded FROM events", [], |r| r.get(0))
                .unwrap();
            assert_eq!(uploaded, (expected == "accepted") as i64);
            let image = std::fs::read(cfg.home.join("telemetry.sqlite3")).unwrap();
            for protected in [marker.as_bytes(), b"SYNTHETIC_PRIVATE_TOKEN"] {
                assert!(!image
                    .windows(protected.len())
                    .any(|bytes| bytes == protected));
            }
        }
    }

    /// Deadlines before headers and after headers retain distinct safe receipt facts.
    #[test]
    fn upload_deadlines_remain_unknown_with_received_status_preserved() {
        for with_headers in [false, true] {
            let (_home, mut cfg, conn) = fixture();
            let listener = TcpListener::bind("127.0.0.1:0").unwrap();
            cfg.api_base = format!("http://{}", listener.local_addr().unwrap());
            let peer = std::thread::spawn(move || {
                let (mut stream, _) = listener.accept().unwrap();
                request(&mut stream);
                if with_headers {
                    stream.write_all(b"HTTP/1.1 202 Test\r\nContent-Length: 100\r\nConnection: close\r\n\r\n").unwrap();
                }
                // The client's actual deadline/drop releases the peer; no guessed delivery sleep.
                let _ = stream.read(&mut [0; 1]);
            });
            run_with(
                &cfg,
                &conn,
                None,
                || Ok("synthetic".into()),
                Client::builder()
                    .timeout(Duration::from_millis(500))
                    .build(),
            )
            .unwrap();
            peer.join().unwrap();
            let row = receipt(&conn);
            assert_eq!(row.0, "unknown");
            assert_eq!(
                row.1,
                if with_headers {
                    "response_body"
                } else {
                    "transport"
                }
            );
            assert_eq!(row.2.as_deref(), Some("timeout"));
            assert_eq!(row.3, with_headers.then_some(202));
            assert_eq!(
                conn.query_row("SELECT uploaded FROM events", [], |r| r.get::<_, i64>(0))
                    .unwrap(),
                0
            );
        }
    }

    /// Auth/request failures are safe local failures; an empty flush never consults credentials.
    #[test]
    fn upload_auth_builder_and_empty_boundaries_do_not_create_recursive_events() {
        let (_home, cfg, conn) = fixture();
        conn.execute("UPDATE events SET status=-1", []).unwrap();
        run_with(
            &cfg,
            &conn,
            None,
            || panic!("journal read failure must precede credentials"),
            Client::builder().build(),
        )
        .unwrap();
        let row = receipt(&conn);
        assert_eq!(
            (row.0.as_str(), row.1.as_str(), row.2.as_deref()),
            ("failed", "journal", Some("journal_read"))
        );
        conn.execute("UPDATE events SET status=200", []).unwrap();
        run_with(
            &cfg,
            &conn,
            None,
            || anyhow::bail!("SYNTHETIC_PRIVATE_CREDENTIAL"),
            Client::builder().build(),
        )
        .unwrap();
        let row = receipt(&conn);
        assert_eq!(
            (row.0.as_str(), row.1.as_str(), row.2.as_deref()),
            ("failed", "auth", Some("credential_unavailable"))
        );
        run_with(
            &cfg,
            &conn,
            None,
            || Ok("invalid\nSYNTHETIC_PRIVATE_TOKEN".into()),
            Client::builder().build(),
        )
        .unwrap();
        let row = receipt(&conn);
        assert_eq!(
            (row.0.as_str(), row.1.as_str(), row.2.as_deref()),
            ("failed", "transport", Some("request"))
        );
        assert_eq!(
            conn.query_row("SELECT COUNT(*) FROM events", [], |r| r.get::<_, i64>(0))
                .unwrap(),
            1
        );
        conn.execute("DELETE FROM events", []).unwrap();
        run_with(
            &cfg,
            &conn,
            None,
            || panic!("empty uploader must not access credentials"),
            Client::builder().build(),
        )
        .unwrap();
        assert_eq!(receipt(&conn).0, "empty");
    }
}

/// Ignore all provider/user text and bound acknowledgement memory before decoding.
fn acknowledgement(
    response: Response,
    count: usize,
) -> std::result::Result<(), (&'static str, &'static str)> {
    if response
        .content_length()
        .is_some_and(|length| length > ACK_LIMIT)
    {
        return Err(("acknowledgement", "ack_oversize"));
    }
    let mut body = Vec::new();
    response
        .take(ACK_LIMIT + 1)
        .read_to_end(&mut body)
        .map_err(|error| {
            (
                "response_body",
                if error.kind() == std::io::ErrorKind::TimedOut
                    || error
                        .get_ref()
                        .and_then(|source| source.downcast_ref::<reqwest::Error>())
                        .is_some_and(reqwest::Error::is_timeout)
                {
                    "timeout"
                } else {
                    "body"
                },
            )
        })?;
    if body.len() as u64 > ACK_LIMIT {
        return Err(("acknowledgement", "ack_oversize"));
    }
    let value: serde_json::Value =
        serde_json::from_slice(&body).map_err(|_| ("acknowledgement", "ack_invalid"))?;
    if value.get("accepted").and_then(serde_json::Value::as_u64) != Some(count as u64) {
        return Err(("acknowledgement", "ack_invalid"));
    }
    Ok(())
}
