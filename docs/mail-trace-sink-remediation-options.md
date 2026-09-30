# Conditional remediation: retained URL markers (2026-09-30)

Status: **conditional architecture, not an implementation or privacy attestation**.
This extends [the privacy decision](mail-trace-privacy-decision.md) and the
[historical discriminator](staging-trace-canary.md). No deployed setting, private
record, secret, live query, build, or test was accessed for this investigation.
The positive failure in hosted run `36703733769` establishes marker retention,
not the offending field or producer. The classifier result is still required.

## Classifier result -> next action

Treat mixed carriers as multiple defects; fixing one does not close the gate.
The classifier's fixed bins deliberately suppress raw records and field names.

| Fixed result | What it supports, not proves | Smallest appropriate action |
| --- | --- | --- |
| `metadata_url` or `workers_event_request`, `cf_worker_log`, `path_only` | A reviewed custom event is enriched with the triggering URL/path; invocation suppression may be working. | Review a sink-boundary change below. Do not add another application regex or assume query redaction removes paths. |
| URL/request enrichment with `query_only` or `both_same_suffix` | Effective query-redaction behavior is inconsistent with the intended URL non-retention boundary. | Pin the exact serving version; compare both script/version settings and export/tail destinations without dumping data. If intended settings match, prepare a minimal synthetic provider report and move retention away from the request-facing Worker. |
| `cf_worker_event` with a marker | Invocation-log suppression or the event-type/deployment boundary is inconsistent with expectation. | Reconcile the queried service and serving version/settings first. Correct an evidenced configuration/deployment defect before redesigning the sink. Do not infer application serialization leaked. |
| `source_or_message` | A marker exists in a payload/message carrier, but the coarse bin alone does not identify whether application code, generated Wasm shim, or platform wrapping emitted it. | Audit console/error/panic emission and generated wrapper at the exact deployed SHA. Correct the responsible emitter, retain typed enums, and prohibit free-form request/error text. A sink relocation would merely transport the leak if the payload itself is unsafe. |
| `metadata_other`, `other_or_multiple`, mixed types | The compact classifier is insufficient to select a single fix. | Inspect source ownership of the implicated fixed category; propose one additional fixed-enum, bounded discriminator only if necessary. Do not widen the historical window or export arbitrary fields. |
| `UNVERIFIED`, no surviving hit, malformed/truncated/expired records | No usable further attribution; the earlier positive failure remains. | Keep the privacy gate closed. Do not reinterpret absence as success, repeatedly query, or alter settings speculatively. |

Cloudflare documents custom logs and invocation logs as separate facilities, but
its [telemetry API schema](https://developers.cloudflare.com/api/resources/workers/subresources/observability/subresources/telemetry/methods/query/)
includes request URL and event enrichment. That schema is not a promise that
custom records exclude request context. This is why a whole-record retained-data
test is necessary. The [script settings API](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/settings/methods/get/)
defines query redaction; it does not specify arbitrary path redaction.

## Why routing is not the privacy boundary

The API already has `custom_domain=true`, `workers_dev=false`, and an explicit
staging hostname in `crates/mail-worker/wrangler.toml`. A
[Custom Domain matches the hostname without considering path or query](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/).
Moving from that domain to a Route, rejecting unknown paths earlier, or sanitizing
`Request.url` inside the handler does not establish that the original invocation
context was never retained. Nor can a Tail Worker erase an already persisted
source record. Keep the established API paths, authentication and response
contracts; do not force callers onto a new path just to make telemetry safer.

An unobserved gateway plus a private business Worker is a larger alternative. It
only helps if the business invocation receives genuinely sanitized context; raw
URL/request forwarding defeats it. It changes every mail call and failure path,
whereas the current defect may concern only the emission sink. Prefer moving
safe events, not moving the whole API.

## Options if platform enrichment is the confirmed carrier

Keep the existing typed `Event` and `ClientEvent` semantics and W3C parentage.
`trace.rs` currently emits JSON through `console_log!`; it has no dynamic
attribute map. A relocation must also cover warnings, panic/uncaught exception
paths and other console sites, not only `trace::emit()`.

| Candidate | Privacy hypothesis to test | Operating consequences | Judgment |
| --- | --- | --- | --- |
| Keep request-facing Workers Logs | A documented pre-persistence exclusion can remove all untrusted path/query context. | Least change, existing queries and retention. | Use only if an actual setting/provider fix is demonstrated; current readback has already failed to establish it. |
| Analytics Engine binding | Explicit datapoints contain only supplied safe fields, not the triggering URL. | Simple nonblocking writes and SQL queries, but adaptive sampling and three-month retention. | Good for aggregate health; not the sole store for exact individual causal traces. |
| Private fixed-URL service-binding logger | A new invocation contains a literal URL and reviewed event body, not the original request. | One extra Worker, lower machinery than a Queue, best-effort handoff; context propagation remains an unproven platform boundary. | Plausible cheaper candidate if its complete retained shape passes; never forward the incoming `Request` or arbitrary headers. |
| Queue -> queue-only logging Worker | The sink invocation has queue context and only the reviewed event body; no public fetch path exists. | Extra Queue/Worker, delayed visibility, retries/duplicates, bounded backlog and DLQ. Still Workers Logs sampling/retention. | Preferred candidate when preserving Cloudflare-native per-request diagnosis after confirmed enrichment, subject to a new retained-data test. |

[Analytics Engine](https://developers.cloudflare.com/analytics/analytics-engine/get-started/)
writes ordered explicit datapoints and returns immediately. Its
[limits](https://developers.cloudflare.com/analytics/analytics-engine/limits/)
include 250 points per invocation, 20 blobs, 20 doubles, one index, 16 KB total
blob data and three-month retention. Its
[adaptive sampling](https://developers.cloudflare.com/analytics/analytics-engine/sampling/)
means a successful write cannot promise every individual trace can be queried.
Using a trace ID as the index may improve grouping but is not an exact-retention
guarantee. Do not silently lengthen diagnostic retention from days to months.

Cloudflare's [HTTP service-binding example](https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/http/)
can forward a request. That is specifically **not** this design: a logger would
receive a newly constructed literal URL and allowlisted event only. Whether
retained enrichment includes caller context still requires deployment evidence.

For a Queue sink, [Workers Logs](https://developers.cloudflare.com/workers/observability/logs/workers-logs/)
documents queue invocation messages as queue names rather than HTTP URLs. This
supports the hypothesis, not a guarantee about every enriched field. Full-rate
Logs remain bounded: paid retention is seven days, free retention three days,
and an account daily cap can force sampling. Do not promise lossless tracing.

## Minimal Queue-sink contract and failure model

```text
CLI span C -> authenticated API span S (same trace T, parent C)
  -> typed event + server-generated event_id
  -> private Queue binding -> queue-only Worker -> retained safe application event
                                (no public routes, workers.dev or preview exposure)
```

1. Add a versioned bounded envelope containing a server-generated random
   `event_id` plus the existing safe application event. Keep request/span IDs
   unchanged; do not substitute the delivery handler's span for the original
   causal parent. No URL, mail data, raw exception, arbitrary header, owner ID,
   or free-form attribute enters the envelope. Validate the schema again at the
   consumer. Queue bindings are capability boundaries, not proof that future
   producers obey the schema.
2. Use a dedicated binding and isolated staging/production Queue. Disable
   retained Logs/native traces on the public API; check Logpush, destinations,
   tails and preview versions separately. Ingress/event Workers stay unobserved.
   The queue-only consumer enables reviewed custom Logs, invocation logs off,
   native traces off. Its queue name is fixed deployment configuration.
3. Enqueue a bounded few events without changing mail results. Await the send in
   `waitUntil` or another supported lifecycle mechanism, not an untracked future.
   Queue outages/quota/runtime death can lose diagnostics. Use safe platform
   [Queue metrics](https://developers.cloudflare.com/queues/observability/metrics/)
   for backlog and failed delivery; do not log the original request as fallback.
4. [At-least-once delivery](https://developers.cloudflare.com/queues/reference/delivery-guarantees/)
   permits duplicates and reordering. Reuse the same `event_id` on redelivery.
   Readers group identical payloads by ID and reject conflicting payloads;
   do not add a durable dedup database solely to avoid duplicate log rows.
   Never interpret enqueue time or consumer order as causal order.
5. Queue delivery/acknowledgment is **not a Workers Logs persistence acknowledgment**.
   `console_log!` has no end-to-end persistence receipt. Retrying cannot repair
   invisible platform loss; arbitrary repetition risks volume and duplicates.
   The trace remains best-effort. If exact durable per-event accounting becomes
   required, it needs a separately scoped durable store and retention contract.
6. Set a small finite retry policy, safe DLQ and retention budget explicitly.
   [Retry exhaustion](https://developers.cloudflare.com/queues/configuration/batching-retries/)
   otherwise deletes the message without a DLQ. Poison envelopes produce only a
   fixed diagnostic code, never the payload. Queue bodies and DLQ copies are
   retained data too. [Queue limits](https://developers.cloudflare.com/queues/platform/limits/)
   include 128 KB messages and plan-dependent retention; keep the application
   envelope well below the limit instead of relying on truncation.

## Evidence-gated migration, not another generic canary

After the classifier selects the enrichment branch, implement/review only the
new sink, typed handoff and readback guards. Hosted tests cover schema rejection,
client legacy compatibility, delivery duplicates, no raw-error fallbacks and
retained-record assessment of the new service. Deploy the sink first, then the
producer configuration atomically at a pinned staging version. Never dual-log
on the unsafe public Worker to compare results.

One bounded staging acceptance run should establish: source Worker retention
disabled; authenticated CLI -> API parentage present in sink events; unauthenticated
denial event present without trusted parent; path/query/body/header canaries
absent from **complete sink records and queued envelopes**; expected cleanup.
Include synthetic dependency failure and malformed-envelope paths. Account for
queue delay using a bounded polling deadline, not a wider historical query.
Identical delivery duplicates may be deduplicated by safe event ID, but missing,
conflicting or truncated events remain unverified. Keep production/public sending
closed until independent review and this exact deployed gate pass. Rollback must
not re-enable the previously unsafe public sink: roll back business changes with
retention still disabled, accepting reduced diagnostics rather than renewed leak.

The established production principle is separation of unsafe request context
from typed diagnostic data, using native bindings rather than REST credentials
([Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/)).
The empirical [USENIX Security 2023 logging study](https://www.usenix.org/conference/usenixsecurity23/presentation/lyons)
supports checking collectors and complete retained records rather than trusting
application formatting alone; it does not establish Cloudflare's producer here.
The actionable next step remains the reviewed one-shot historical classifier,
not a speculative configuration change or production rollout.
