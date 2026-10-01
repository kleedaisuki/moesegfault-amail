//! Infrastructure-only native tracing canary: no mail, account, DB, R2 or send capability.
//!
//! Two deployments share this Rust/Wasm product. The untraced caller constructs
//! fixed synthetic requests for a private service-bound probe; it never forwards
//! incoming request data. This is not an authentication or mail implementation.

mod case;
mod native;

use case::{Case, Kind, Mode};
use serde::Serialize;
use wasm_bindgen::JsValue;
use worker::{event, Env, Headers, Method, Request, RequestInit, Response, Result};

/// Public operational receipt; no original URL, header, body or exception enters it.
#[derive(Serialize)]
struct Report {
    /// Source-owned synthetic comparison case.
    case: Case,
    /// The platform getter and all native operations succeeded.
    available: bool,
    /// Root span actually reported itself sampled.
    sampled: bool,
    /// Actual failing boundary or completed operation.
    stage: &'static str,
}

/// Dispatch only the two configured infrastructure roles; no arbitrary forwarding target.
#[event(fetch)]
pub async fn fetch(request: Request, env: Env, _ctx: worker::Context) -> Result<Response> {
    match env.var("CANARY_ROLE")?.to_string().as_str() {
        "caller" => call_probe(&env).await,
        "probe" => probe(request).await,
        _ => Response::error("Unknown infrastructure role", 503),
    }
}

/// Incoming caller URL/body/headers are deliberately not consumed or forwarded.
async fn call_probe(env: &Env) -> Result<Response> {
    let Some(cases) = Case::all(&env.var("PROBE_ID")?.to_string()) else {
        return Response::error("Invalid public probe coordinate", 503);
    };
    let service = env.service("PROBE")?;
    let mut receipts = Vec::new();
    for case in cases {
        let mut init = RequestInit::new();
        init.with_method(Method::Post)
            .with_body(Some(JsValue::from_str(&case.body())));
        let headers = Headers::new();
        headers.set("user-agent", &case.header())?;
        headers.set("content-type", "text/plain")?;
        // Non-secret W3C input tests real platform propagation, not overwritten trace IDs.
        headers.set(
            "traceparent",
            &format!("00-{}-0123456789abcdef-01", case.run),
        )?;
        init.with_headers(headers);
        let mut response = service
            .fetch_request(Request::new_with_init(&case.url(), &init)?)
            .await?;
        let status = response.status_code();
        let body: serde_json::Value = response.json().await?;
        receipts.push(serde_json::json!({"status":status,"report":body}));
    }
    Response::from_json(&serde_json::json!({"receipts":receipts}))
}

/// Source parsing and tracing errors do not echo the original request or JS exception.
async fn probe(request: Request) -> Result<Response> {
    let Some(case) = Case::from_path(&request.path()) else {
        return Response::error("Unknown synthetic case", 404);
    };
    let result = exercise(&case).await;
    let (available, sampled, stage) = match result {
        Ok(sampled) => (true, sampled, "complete"),
        Err(stage) => (false, false, stage.label()),
    };
    let status = if available { case.kind.status() } else { 503 };
    let report = Report {
        case,
        available,
        sampled,
        stage,
    };
    // This safe event deliberately tests automatic retained-log enrichment too.
    worker::console_log!("{}", serde_json::to_string(&report)?);
    Ok(Response::from_json(&report)?.with_status(status))
}

/// Compare raw/root-replaced attributes and real async context on the actual runtime.
async fn exercise(case: &Case) -> std::result::Result<bool, native::Stage> {
    let root = native::Span::active()?;
    root.attributes(&[
        ("amail.canary.run", JsValue::from_str(&case.run)),
        ("amail.canary.mode", JsValue::from_str(case.mode.label())),
        ("amail.canary.kind", JsValue::from_str(case.kind.label())),
    ])?;
    if case.mode == Mode::Redacted {
        root.attributes(&[
            (
                "url.full",
                JsValue::from_str("https://synthetic.invalid/probe"),
            ),
            ("url.path", JsValue::from_str("/probe")),
            ("url.query", JsValue::from_str("")),
            (
                "user_agent.original",
                JsValue::from_str("amail-native-canary"),
            ),
        ])?;
    }
    let child = native::Span::child()?;
    let result = async {
        worker::Delay::from(std::time::Duration::from_millis(1)).await;
        native::Span::active()?.attributes(&[("amail.canary.after_await", JsValue::TRUE)])?;
        child.attributes(&[("amail.canary.kind", JsValue::from_str(case.kind.label()))])?;
        if case.kind == Kind::Failure {
            child.fixed_exception()?;
        }
        Ok(root.sampled())
    }
    .await;
    let ended = child.end();
    result.and_then(|sampled| ended.map(|_| sampled))
}
