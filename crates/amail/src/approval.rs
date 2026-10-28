//! One browser decision for one daemon operation; viewing a page grants nothing.

use anyhow::{ensure, Context, Result};
use axum::{
    body::{to_bytes, Body},
    extract::State,
    http::{Request as HttpRequest, StatusCode},
    response::{IntoResponse, Response},
    Router,
};
use serde_json::json;
use std::{
    sync::{Arc, Mutex},
    time::Duration,
};
use tokio::{net::TcpListener, sync::oneshot};

const AUTHORIZATION_TIMEOUT: Duration = Duration::from_secs(120);
const MAX_HEADERS: usize = 8192;
const MAX_BODY: usize = 1024;
static AUTHORIZATION: Mutex<()> = Mutex::new(());

struct Challenge {
    host: String,
    path: String,
    action: String,
    operation: &'static str,
    summary: String,
}

struct Pending {
    challenge: Challenge,
    decision: Mutex<Option<oneshot::Sender<bool>>>,
}

struct Request {
    method: String,
    path: String,
    host: String,
    origin: Option<String>,
    content_type: Option<String>,
    body: Vec<u8>,
}

#[derive(Debug, PartialEq, Eq)]
enum Action {
    View,
    Approve,
    Deny,
    Reject,
}

fn operation_label(operation: &str) -> &'static str {
    match operation {
        "profile" | "profile.create" | "profile activate" | "profile.activate" => {
            "Manage an amail profile"
        }
        "login" | "auth.login" => "Sign in to amail",
        "logout" | "auth.logout" => "Sign out of amail",
        "send" | "messages.send" => "Send an email",
        "delete" | "messages.delete" => "Delete email",
        "address" | "address.add" | "address.delete" => "Manage an email address",
        "read" | "messages.archive" => "Download email",
        "pack" | "unpack" => "Process a mail archive",
        "billing" => "Open amail billing",
        "semantic.change" => "Change account-wide semantic search consent",
        _ => "Run the requested amail operation",
    }
}

fn failure(code: &'static str, message: &str) -> anyhow::Error {
    crate::machine::Failure {
        code,
        next_action: "stop",
        data: json!({}),
        message: message.to_owned(),
    }
    .into()
}

/// Display the exact non-content request identity before accepting a decision.
pub fn authorize_request(operation: &str, summary: &str) -> Result<()> {
    let _serial = AUTHORIZATION
        .lock()
        .unwrap_or_else(|error| error.into_inner());
    runtime()?.block_on(async {
        let listener = TcpListener::bind(("127.0.0.1", 0))
            .await
            .context("cannot open the local amail authorization page")?;
        let challenge = Challenge {
            host: listener.local_addr()?.to_string(),
            path: format!("/authorize/{}", uuid::Uuid::new_v4()),
            action: uuid::Uuid::new_v4().to_string(),
            operation: operation_label(operation),
            summary: bounded_summary(summary),
        };
        let url = format!("http://{}{}", challenge.host, challenge.path);
        crate::output::err(format_args!(
            "amail: authorize this operation in your browser: {url}\n"
        ));
        // A headless session can open this private URL manually. Browser launch
        // failure never implicitly approves the operation.
        let _ = webbrowser::open(&url);
        wait_for_decision(listener, challenge, AUTHORIZATION_TIMEOUT).await
    })
}

fn runtime() -> Result<tokio::runtime::Runtime> {
    Ok(tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()?)
}

async fn wait_for_decision(
    listener: TcpListener,
    challenge: Challenge,
    timeout: Duration,
) -> Result<()> {
    let (sender, receiver) = oneshot::channel();
    let pending = Arc::new(Pending {
        challenge,
        decision: Mutex::new(Some(sender)),
    });
    // Axum/Hyper bounds HTTP/1 parsing (100 headers, ~400 KiB connection
    // buffer); the application narrows accepted headers to 8 KiB and bodies
    // to 1 KiB with a two-second body deadline.
    let router = Router::new().fallback(handle).with_state(pending);
    let (shutdown, stopping) = oneshot::channel::<()>();
    let mut server = tokio::spawn(async move {
        axum::serve(listener, router)
            .with_graceful_shutdown(async {
                let _ = stopping.await;
            })
            .await
    });
    let decision = tokio::time::timeout(timeout, receiver).await;
    let _ = shutdown.send(());
    if tokio::time::timeout(Duration::from_secs(2), &mut server)
        .await
        .is_err()
    {
        server.abort();
    }
    match decision {
        Ok(Ok(true)) => Ok(()),
        Ok(Ok(false)) => Err(failure(
            "authorization_denied",
            "the amail operation was denied",
        )),
        _ => Err(failure(
            "authorization_timeout",
            "amail authorization timed out; no operation was performed",
        )),
    }
}

async fn handle(State(pending): State<Arc<Pending>>, request: HttpRequest<Body>) -> Response {
    let action = read_request(request)
        .await
        .map(|request| evaluate(&request, &pending.challenge))
        .unwrap_or(Action::Reject);
    match action {
        Action::View => respond(StatusCode::OK, page(&pending.challenge)),
        Action::Approve | Action::Deny => {
            let approved = action == Action::Approve;
            let sender = pending
                .decision
                .lock()
                .unwrap_or_else(|error| error.into_inner())
                .take();
            if let Some(sender) = sender {
                if sender.send(approved).is_ok() {
                    respond(StatusCode::OK, result_page(approved))
                } else {
                    respond(
                        StatusCode::CONFLICT,
                        "This authorization expired.".to_owned(),
                    )
                }
            } else {
                respond(
                    StatusCode::CONFLICT,
                    "This authorization was already decided.".to_owned(),
                )
            }
        }
        Action::Reject => respond(
            StatusCode::BAD_REQUEST,
            "Invalid authorization request.".to_owned(),
        ),
    }
}

async fn read_request(request: HttpRequest<Body>) -> Result<Request> {
    let method = request.method().as_str().to_owned();
    let path = request.uri().to_string();
    let mut host = None;
    let mut origin = None;
    let mut content_type = None;
    let mut length = None;
    let mut total_headers = 0;
    for (name, value) in request.headers() {
        let name = name.as_str();
        let value = value.to_str()?.trim().to_owned();
        total_headers += name.len() + value.len() + 4;
        ensure!(
            total_headers <= MAX_HEADERS,
            "authorization headers too large"
        );
        match name.to_ascii_lowercase().as_str() {
            "host" => set_once(&mut host, value)?,
            "origin" => set_once(&mut origin, value)?,
            "content-type" => set_once(&mut content_type, value)?,
            "content-length" => set_once(&mut length, value)?,
            "transfer-encoding" | "expect" | "upgrade" => {
                anyhow::bail!("unsupported authorization request framing")
            }
            "connection" if value.to_ascii_lowercase().contains("upgrade") => {
                anyhow::bail!("unsupported authorization connection upgrade")
            }
            _ => {}
        }
    }
    let size = length.as_deref().unwrap_or("0").parse::<usize>()?;
    ensure!(size <= MAX_BODY, "authorization body too large");
    let body = tokio::time::timeout(
        Duration::from_secs(2),
        to_bytes(request.into_body(), MAX_BODY),
    )
    .await
    .context("authorization body timed out")??
    .to_vec();
    ensure!(body.len() == size, "inconsistent authorization body length");
    Ok(Request {
        method,
        path,
        host: host.context("authorization host is missing")?,
        origin,
        content_type,
        body,
    })
}

fn set_once(slot: &mut Option<String>, value: String) -> Result<()> {
    ensure!(slot.is_none(), "duplicate authorization header");
    *slot = Some(value);
    Ok(())
}

fn evaluate(request: &Request, challenge: &Challenge) -> Action {
    if request.host != challenge.host || request.path != challenge.path {
        return Action::Reject;
    }
    let origin = format!("http://{}", challenge.host);
    if request
        .origin
        .as_ref()
        .is_some_and(|value| value != &origin)
    {
        return Action::Reject;
    }
    if request.method == "GET" && request.body.is_empty() {
        return Action::View;
    }
    if request.method != "POST"
        || request.content_type.as_deref() != Some("application/x-www-form-urlencoded")
    {
        return Action::Reject;
    }
    let fields: Vec<_> = url::form_urlencoded::parse(&request.body).collect();
    if fields.len() != 2
        || fields
            .iter()
            .filter(|(key, value)| key == "nonce" && value.as_ref() == challenge.action)
            .count()
            != 1
    {
        return Action::Reject;
    }
    match fields
        .iter()
        .find(|(key, _)| key == "decision")
        .map(|(_, value)| value.as_ref())
    {
        Some("approve") => Action::Approve,
        Some("deny") => Action::Deny,
        _ => Action::Reject,
    }
}

fn page(challenge: &Challenge) -> String {
    format!(
        "<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content=\"width=device-width,initial-scale=1\"><title>Authorize amail</title><body><main><h1>Authorize this amail operation?</h1><p>{}</p><pre>{}</pre><p>This decision applies only to this one operation. Approval does not authorize future operations.</p><form method=post action=\"{}\"><input type=hidden name=nonce value=\"{}\"><button type=submit name=decision value=approve>Approve</button> <button type=submit name=decision value=deny>Deny</button></form></main></body></html>",
        challenge.operation, escape_html(&challenge.summary), challenge.path, challenge.action
    )
}

fn bounded_summary(summary: &str) -> String {
    let mut end = summary.len().min(2048);
    while !summary.is_char_boundary(end) {
        end -= 1;
    }
    summary[..end].to_owned()
}

fn escape_html(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
}

fn result_page(approved: bool) -> String {
    let result = if approved { "Approved" } else { "Denied" };
    format!("<!doctype html><html lang=en><meta charset=utf-8><title>amail authorization</title><body><h1>{result}</h1><p>You may close this tab. Check the terminal for the operation result.</p></body></html>")
}

fn respond(status: StatusCode, body: String) -> Response {
    (
        status,
        [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Cache-Control", "no-store"),
            ("Pragma", "no-cache"),
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"),
            // Native form POSTs under no-referrer send Origin: null, which
            // contradicts the exact-origin check. Still suppress cross-origin referrers.
            ("Referrer-Policy", "same-origin"),
            (
                "Content-Security-Policy",
                "default-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
            ),
        ],
        body,
    )
        .into_response()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        io::{Read, Write},
        net::TcpStream,
        thread,
    };

    fn challenge() -> Challenge {
        Challenge {
            host: "127.0.0.1:43210".to_owned(),
            path: "/authorize/view-nonce".to_owned(),
            action: "action-nonce".to_owned(),
            operation: "Send an email",
            summary: "user profile: send mail.zip".to_owned(),
        }
    }

    fn request(method: &str, body: &str) -> Request {
        Request {
            method: method.to_owned(),
            path: challenge().path,
            host: challenge().host,
            origin: Some("http://127.0.0.1:43210".to_owned()),
            content_type: Some("application/x-www-form-urlencoded".to_owned()),
            body: body.as_bytes().to_vec(),
        }
    }

    #[test]
    fn get_never_approves_and_page_uses_a_separate_action_nonce() {
        assert_eq!(evaluate(&request("GET", ""), &challenge()), Action::View);
        assert_eq!(
            evaluate(
                &request("GET", "nonce=action-nonce&decision=approve"),
                &challenge()
            ),
            Action::Reject
        );
        let html = page(&challenge());
        assert!(html.contains("method=post"));
        assert!(html.contains("value=\"action-nonce\""));
        assert!(!html.contains("<script"));
    }

    #[test]
    fn summary_is_escaped_and_bounded_on_a_utf8_boundary() {
        let mut challenge = challenge();
        challenge.summary = "user <script>\"'& target".to_owned();
        let html = page(&challenge);
        assert!(html.contains("user &lt;script&gt;&quot;&#39;&amp; target"));
        assert!(!html.contains("<script>"));
        let summary = bounded_summary(&"界".repeat(1000));
        assert!(summary.len() <= 2048);
        assert_eq!(summary.chars().count(), 682);
    }

    #[test]
    fn only_exact_action_nonce_and_same_origin_allow_a_decision() {
        let mut req = request("POST", "nonce=action-nonce&decision=approve");
        assert_eq!(evaluate(&req, &challenge()), Action::Approve);
        req.origin = Some("null".to_owned());
        assert_eq!(evaluate(&req, &challenge()), Action::Reject);
        req.origin = Some("http://127.0.0.1:43210.attacker.example".to_owned());
        assert_eq!(evaluate(&req, &challenge()), Action::Reject);
        req.origin = None;
        req.host = "attacker.example".to_owned();
        assert_eq!(evaluate(&req, &challenge()), Action::Reject);
        assert_eq!(
            evaluate(
                &request("POST", "nonce=view-nonce&decision=approve"),
                &challenge()
            ),
            Action::Reject
        );
        assert_eq!(
            evaluate(
                &request("POST", "nonce=action-nonce&nonce=action-nonce"),
                &challenge()
            ),
            Action::Reject
        );
    }

    #[test]
    fn deny_is_an_explicit_terminal_decision() {
        assert_eq!(
            evaluate(
                &request("POST", "nonce=action-nonce&decision=deny"),
                &challenge()
            ),
            Action::Deny
        );
    }

    #[test]
    fn mature_http_requests_keep_body_and_header_bounds() {
        let body = "nonce=action-nonce&decision=deny";
        let valid = || {
            HttpRequest::builder()
                .method("POST")
                .uri("/authorize/view-nonce")
                .header("Host", "127.0.0.1:43210")
                .header("Content-Type", "application/x-www-form-urlencoded")
                .header("Content-Length", body.len())
        };
        runtime().unwrap().block_on(async {
            let req = read_request(valid().body(Body::from(body)).unwrap())
                .await
                .unwrap();
            assert_eq!(evaluate(&req, &challenge()), Action::Deny);
            assert!(read_request(
                valid()
                    .header("Host", "duplicate")
                    .body(Body::from(body))
                    .unwrap()
            )
            .await
            .is_err());
            assert!(read_request(
                HttpRequest::builder()
                    .header("Host", "a")
                    .header("Content-Length", "1025")
                    .body(Body::empty())
                    .unwrap()
            )
            .await
            .is_err());
            for name in ["Transfer-Encoding", "Expect", "Upgrade"] {
                assert!(read_request(
                    valid()
                        .header(name, "unsupported")
                        .body(Body::from(body))
                        .unwrap()
                )
                .await
                .is_err());
            }
        });
    }

    #[test]
    fn timeout_is_typed_and_does_not_approve() {
        let error = runtime().unwrap().block_on(async {
            let listener = TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
            wait_for_decision(listener, challenge(), Duration::ZERO)
                .await
                .unwrap_err()
        });
        assert_eq!(
            error
                .downcast_ref::<crate::machine::Failure>()
                .unwrap()
                .code,
            "authorization_timeout"
        );
    }

    #[test]
    fn http_journey_views_then_denies_without_running_the_operation() {
        let listener = std::net::TcpListener::bind(("127.0.0.1", 0)).unwrap();
        listener.set_nonblocking(true).unwrap();
        let address = listener.local_addr().unwrap();
        let mut challenge = challenge();
        challenge.host = address.to_string();
        let (sender, receiver) = std::sync::mpsc::channel();
        let waiter = thread::spawn(move || {
            let result = runtime().unwrap().block_on(async {
                let listener = TcpListener::from_std(listener).unwrap();
                wait_for_decision(listener, challenge, Duration::from_secs(3)).await
            });
            sender
                .send(result.map_err(|error| error.to_string()))
                .unwrap();
        });
        let exchange = |request: &str| {
            let mut socket = TcpStream::connect(address).unwrap();
            socket
                .set_read_timeout(Some(Duration::from_secs(2)))
                .unwrap();
            socket.write_all(request.as_bytes()).unwrap();
            let mut response = String::new();
            socket.read_to_string(&mut response).unwrap();
            response
        };
        let response = exchange(&format!(
            "GET /authorize/view-nonce HTTP/1.1\r\nHost: {address}\r\nConnection: close\r\n\r\n"
        ));
        assert!(response.starts_with("HTTP/1.1 200 OK"));
        assert!(response.contains("name=nonce value=\"action-nonce\""));
        assert!(response
            .to_ascii_lowercase()
            .contains("cache-control: no-store"));
        assert!(response
            .to_ascii_lowercase()
            .contains("referrer-policy: same-origin"));
        assert!(receiver.try_recv().is_err());
        let body = "nonce=action-nonce&decision=deny";
        let response = exchange(&format!(
            "POST /authorize/view-nonce HTTP/1.1\r\nHost: {address}\r\nOrigin: http://{address}\r\nConnection: close\r\nContent-Type: application/x-www-form-urlencoded\r\nContent-Length: {}\r\n\r\n{body}", body.len()
        ));
        assert!(response.contains("<h1>Denied</h1>"));
        assert_eq!(
            receiver.recv_timeout(Duration::from_secs(2)).unwrap(),
            Err("the amail operation was denied".to_owned())
        );
        waiter.join().unwrap();
    }
}
