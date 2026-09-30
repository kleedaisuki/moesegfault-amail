# Queue-only trace sink retained-data canary

Status: source harness prepared; not executed locally or live. Public sending and
production privacy acceptance remain closed pending independent review, hosted
synthetic tests and one explicitly guarded deployed run.

## Contract and scope

`infra/tests/staging_hosted_trace_sink_canary.py` owns the fresh hosted Windows
native-PKCE home and delegates to `staging_trace_sink_canary.py`. Modes are
`--mode preflight` and `--mode canary`; only full mode requires exact
`--confirm RUN_STAGING_TRACE_SINK_CANARY`. Both require `--source-version UUID`
and `--sink-version UUID` from independently observed deployment outputs. These
are public deployment pins, not credentials. Repository credentials remain
in environment variables: `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`,
`CF_OBSERVABILITY_TOKEN`, and the existing synthetic account secrets. No raw
records, marker, correlation IDs or response bodies reach stdout or artifacts.

Preflight requires the source API's retained Logs/native tracing disabled, the
Queue-only sink's explicit typed custom Logs enabled with invocation/native
tracing disabled, no unreviewed tail/log export, a supported exact-service query
key, and 100% traffic on each supplied serving version. Repeat those settings
and both pins after readback; missing/split/changed versions fail closed.

One authenticated `amail address list` yields local SQLite `(T, C, R)` only in
memory. One anonymous reqwest POST carries four markers in URL path, URL query,
body and a dedicated header. The feature-gated Rust helper accepts only the
existing exact synthetic staging URL and derives body/header values itself;
`--sink-private-id` also supplies an adversarial syntactically valid traceparent.
Its UUID-only stdout is captured privately. The unchanged old `--private-id`
behavior remains a GET. Both require exactly HTTP 401 and one canonical Worker
request ID without redirect; neither displays the request or response content.

The sink query begins two seconds before probes and ends two seconds plus 120
seconds after them. Wait 125 seconds before first read so the entire fixed window
is historical. One additional read after 60 seconds is permitted only for missing
root/denial evidence; it does not send new traffic or widen the original window.
Count/cursor-complete dry queries cap 1,600 events and require exact service echo.
The second view must retain all first-view indexed IDs. This is a bounded
consumer/indexing allowance, not a Queue delivery latency guarantee.

The checker scans **the entire retained JSON record** (keys, custom payload,
platform metadata and enrichment) for all four exact synthetic markers, rejects
truncation/unknown payload, validates typed event fields and stable UUIDv4 event
IDs, and deduplicates identical at-least-once Queue copies. Reused event IDs with
different payloads fail. Exactly one distinct API `addresses_list/request_exit`
event must match `(T, S, R)`, parent `C`, `S != C`, and successful HTTP class.
Exactly one distinct anonymous denial event must have no parent and a trace ID
different from the authenticated trace and the adversarial traceparent. The
source API's same bounded window must contain zero retained records.

Success output is only `staging_trace_sink_hosted:
bounded_retained_canary_verified`. It proves this bounded source/sink retained
window and two causal roots. It **does not** prove lossless tracing for all traffic,
future absence, Queue/DLQ retention privacy or all operational failure branches.
There is no non-destructive queued-envelope readback endpoint: only the strict
Rust producer/consumer schema and hosted tests attest queued envelope construction,
not an independent live peek. Queue at-least-once delivery and Workers Logs
retention/sampling remain explicit limitations. Do not consume DLQ messages or
introduce a public sink endpoint merely to manufacture that stronger claim.

## Validation and coordination

The existing service-filter query helpers gained an optional keyword-only service
parameter, defaulting to the unchanged API service. The new sink service changes
both query construction and the strict echoed service check; no mutable global
service override is used. Synthetic contract tests cover whole-record marker
carriers, truncation, event-ID conflicts/identical redelivery, invalid parentage,
anonymous trace isolation, schema rejection, service echo and confirmation order.
Run these only in hosted CI, alongside old trace/helper contracts and Rust helper
tests. The source/settings checker and CI deploy integration are separately owned.
An independent review must gate dispatch; actual settings/readback evidence must
be recorded here without raw private records when available.

See [prior retained-path incident](staging-trace-canary.md) and
[remediation alternatives](mail-trace-sink-remediation-options.md). Cloudflare's
[Queue delivery guarantees](https://developers.cloudflare.com/queues/reference/delivery-guarantees/)
require at-least-once-aware deduplication, and its
[Workers Logs documentation](https://developers.cloudflare.com/workers/observability/logs/workers-logs/)
distinguishes invocation records from custom Logs. Those platform descriptions
motivate this design but do not replace a complete retained-data canary.
