# Native Cloudflare tracing canary

Status: source implementation under hosted validation, not deployed/native trace
acceptance. The owner prioritizes infrastructure/debt before mailbox debugging.

## Concrete experiment

One infrastructure-only Rust/Wasm product has two deployments: a private probe
with native traces and safe console events, and an untraced caller that constructs
four fixed synthetic requests. Caller input URL/query/header/body is never read
or forwarded. Probe has no workers.dev/preview/custom route and only the caller
has its service binding. No Mail DB/R2/Queue, account/SMTP/send capability or
runtime secret exists in the pair. Deployment overrides a public random run ID.

Cases are baseline/redacted crossed with success/fixed-failure. Distinct source
markers stand in for protected path, query, user-agent and body. Rust imports the
platform tracing namespace directly through wasm-bindgen, exercises getActiveSpan,
setAttributes, startSpan, fixed recordException and explicit child end. It checks
active context again across a real asynchronous delay. Redacted cases replace
url.full/path/query and user_agent.original on the root, without assuming that
this changes other automatic request/log records or survives finalization.

A fixed safe console receipt tests enrichment outside spans too. The source
receipt does not echo original URL/headers/body or JS exception prose. Native
failure reports a specific API/lifecycle stage; missing API/sampling/context is
not accepted as successful tracing. Baseline must establish the relevant markers
and actual native child/error records. Collect the complete pair-scoped window,
compare both policies, verify actual native parentage and inspect all retained
marker locations. Public operational IDs/schema keys are evidence, not privacy
violations. No raw real-mail record is involved or permitted.

The untraced caller's incoming request has no retained logs/traces and its data
never reaches the probe; it does not provide a general forwarding/mail endpoint.
This narrow public trigger is only infrastructure experiment control and must be
removed after collection. It is not an authentication mechanism or product UI.

## Source versus deployed acceptance

Miniflare 4.20260730.0 predates the active-root getter update. Hosted tests prove
that actual compiled Rust service dispatch generates four controlled requests
without caller data and truthfully reports unsupported new API on that runtime.
They **do not prove** current Cloudflare runtime support or redaction. Normal CI
builds the product once, includes its module tree in the verified artifact, and
assigns both native files to core (107 core / 156 total minimum). Actual controlled
deployment/readback, trace collection and cleanup are still required.

Use tested original artifact bytes for the pair, no hidden Rust rebuild on deploy.
Do not change Mail/maintenance capture settings, service graph or send hold to
run this experiment. Capture source/run/Worker versions and readback; ambiguous
writes require existing-state inspection rather than automatic resubmission.
If root replacement leaves private markers in other fields, retain the safe
application event boundary and use native tracing on suitable platform surfaces.

## Primary references

* https://developers.cloudflare.com/workers/observability/traces/custom-spans/
  — getActiveSpan is request-context-dependent; undefined attribute values are
  no-ops, manual spans must end, recordException can expose error message/stack.
* https://developers.cloudflare.com/workers/observability/traces/spans-and-attributes/
  — automatic URL/user-agent/Email/D1/R2 fields have distinct privacy origins.
* https://developers.cloudflare.com/workers/best-practices/workers-best-practices/
  — service bindings and invocation-owned state instead of public forwarding.
* https://wasm-bindgen.github.io/wasm-bindgen/reference/attributes/on-js-imports/module.html
  and js_namespace — bind native module functions without a hand-written JS mail
  implementation or guessed exported Span constructor.
