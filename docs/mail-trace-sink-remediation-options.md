# Conditional remediation: retained URL markers (2026-09-30)

Status: **second historical result justifies a reviewed staging Queue-sink
containment experiment; not an implementation or privacy attestation**.
This extends [the privacy decision](mail-trace-privacy-decision.md) and the
[historical discriminator](staging-trace-canary.md). No deployed setting, private
record, secret, live query, build, or test was accessed for this interpretation.
The positive failure in hosted run `36703733769` establishes marker retention,
not the offending field or producer. The second structural result below locates
the marker in known request-context carriers and supports sink separation,
without claiming definitive producer identity or a privacy pass.

## Containment deployment attempt: effective state still unverified

[Hosted CI run `36725878855`](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36725878855)
at containment source `9c0d5ab` passed the core hosted tests and uploaded the
staging Mail Worker version
`759906b4-bdb9-488a-a980-a4bada8ba83e`. Its subsequent effective-settings gate
returned only **`Mail observability staging: UNVERIFIED`**. The workflow was
therefore not a successful containment acceptance.

| Evidence | What it establishes | What remains unresolved |
| --- | --- | --- |
| Core hosted tests passed | The covered source/test contracts passed in Actions. | Effective provider settings, serving traffic, URL non-retention and Queue-sink privacy. |
| Version upload reported | The containment attempt produced the recorded version ID. | A single 100% serving version, effective Logs-off or a safe serving pin. |
| Aggregate `UNVERIFIED` readback | The checker could not establish its entire reviewed predicate. | Which endpoint/field failed, whether transport/permissions/shape or a policy mismatch caused it, and whether any retained capture is actually still enabled. |

At `9c0d5ab`, the verifier collapses both a false settings predicate and a
readback `ValueError` into the same fixed failure. Its predicate additionally
checks sampling/redaction, optional persistence/export shape and capture flags;
therefore this label **does not identify a particular mismatch**. In particular,
neither “Logs are still on” nor “Logs are safely off but the checker is too
strict” follows from it. Do not weaken the gate based on speculation.

**Operational state after that attempt:** effective Logs-off is **not proven**, and there
is **no safe serving pin for this uploaded version**. An older pin cannot be
carried forward across this upload. Keep the production privacy/public-send
gate closed and pause fresh traffic-based privacy, B registration and mutating
acceptance until the relevant deployment boundaries are reconciled. A targeted
read-only fixed-bin settings diagnostic is being implemented/reviewed to locate
the endpoint/shape/predicate branch without raw settings, identifiers from
requests, provider errors or secrets. This result does not authorize rerunning
the deployment, another generic canary or restoring the unsafe log sink.

The same run's private Identity inbox deployment job stopped separately at
`R2 custom-domain read failed: HTTP0`. In that checker's source, HTTP0 is the
transport-unavailable sentinel, not an HTTP provider status or a finding that
public/custom domains exist. It does not establish the specific transport cause
or effective bucket exposure. This live preflight occurs before that job's
Worker build/deploy, so this attempt did not upload the inbox replacement;
subsequent lifecycle/deployed-binding checks are not attested by this failed
check. Keep the current private-inbox/B gate unverified; see
[the operational record](staging-second-principal.md#latest-deployment-attempt-private-inbox-read-not-completed).

### Fixed-bin settings diagnostic: stable deployment, absent/non-object configuration

A later [core CI run `36728726698`](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36728726698)
uploaded staging Mail version `c3f6401a` (abbreviated version ID), but the
post-deploy observability check still failed. The targeted read-only diagnostic
[run `36730461386`](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36730461386)
at branch source `b536963` then returned `stable100` for that expected staging
version and the following fixed categories:

| Endpoint | Observability container | Observability child shapes/members | `logpush` | `tails` |
| --- | --- | --- | --- | --- |
| `/settings` | `observability_shape=missing` | All reported observability child shapes/members `missing` | `false` | `false` |
| `/script-settings` | `observability_shape=other` | All reported observability child shapes/members `missing` | `false` | `other` |

The reported child categories cover `logs_shape`, `traces_shape`, `enabled`,
`sampling`, `redact`, `logs`, `invocation`, `persist`, `logs_sampling`,
`logs_destinations`, `traces`, `traces_sampling`, and `traces_destinations`.
No raw container value, tail identity, binding, URL, account or provider error
was exported.

At `b536963`, `stable100` means both bounded settings GETs succeeded and were
bracketed by an identical single expected deployment/version at 100% traffic.
It is a **stable-serving control-plane observation for that interval**, not a
privacy-safe serving pin. It does not turn missing capture configuration into
disabled capture, establish data-plane non-retention, or carry across a later
deployment/settings change.

The exact classifier semantics matter:

- `/settings` `missing` means the `observability` key was absent in that returned
  settings object. The classifier cannot inspect its children and reports them
  as `missing`; those labels are not independent provider defaults.
- `/script-settings` `other` means `observability` was present but **not a
  dictionary**. The raw representation is deliberately undisclosed. Child
  `missing` here means no inspectable dictionary parent, not proof that each
  individual backend setting was omitted or false.
- `logpush=false` is the strict false Boolean category at both endpoints.
  `/settings` `tails=false` is an empty-list category. `/script-settings`
  `tails=other` is a non-list representation, not evidence of a populated Tail
  consumer or proof that exports are safely absent everywhere.

These shapes are sufficient to explain why the strict checker cannot pass:
`safe_observability()` requires a dictionary with explicit reviewed flags,
whereas neither returned observability container satisfies that prerequisite.
This locates a concrete representation/presence rejection rather than an
unexplained aggregate result; it **does not establish that it was the sole
failure branch in either earlier deployment job**. Do not reinterpret `missing`
or `other` as false, bypass one endpoint, or loosen the checker just to pass.

**Still unresolved:** effective Logs/Traces on versus off, Cloudflare's effective
default/normalization contract, and authoritative disabled-capture readback for
this version. Research into that contract is underway. The next action is to
resolve the authoritative effective-settings mechanism and independently review
any verifier change against it, not rerun the unchanged deployment, widen a
telemetry query or create new canary traffic. Production privacy/public sending
and the Queue-sink rollout containment prerequisite remain closed. This result
does not resolve the separate private-inbox/R2 transport gate.

## Second historical result: request-context retention located

[Read-only run `36723490687`](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36723490687),
classifier source `d8b9631`, queried the **same staging service and 2026-09-30
10:42:00–10:42:37 UTC window**, returning only:

```text
carrier=metadata_context+workers_event_request carriers=2_plus leaves=2_plus metadata_type=unrecognized wrapper_type=wrapper_absent trigger=fetch source_shape=allowlisted_application component=path_only records=1
```

`d8b9631` identifies the historical-query workflow source, not a new serving
version for the original 10:42 request. No new request or configuration mutation
was part of this classifier operation.

| Fixed finding | Bounded interpretation |
| --- | --- |
| `metadata_context+workers_event_request` | The recognized path marker appeared in at least one of the three exact indexed context fields (`trigger`, `spanName`, `transactionName`) and below `$workers.event.request`. The set contains exactly these two carrier categories, not source, message/error, URL, wrapper or unknown remainder. The exact leaf names and values remain private. |
| `leaves=2_plus`, `records=1` | At least two matching string leaves belonged to one matching returned record. This may be one request-derived value copied into two places; it is not evidence of two independent defects or two events. |
| `source_shape=allowlisted_application` | This matching record's source parsed and validated under the existing reviewed application-event schema. No inspected marker hit was in `source`. This does not attest every other record's payload or every exception/emitter path. |
| `metadata_type=unrecognized`, `wrapper_type=wrapper_absent` | Indexed type is present as a string but is not either recognized exact literal; the exact `$cloudflare` wrapper is absent. Invocation-versus-custom classification remains unknown. The earlier wrapper hypothesis is not supported for this matching record. |
| `trigger=fetch`, `component=path_only` | This matching record's reviewed top-level Worker eventType is `fetch`; the complete returned window contained recognized path-prefix hits but no query-prefix hits. Fetch eventType is not invocation-log type, and this does not establish global query-redaction correctness. |

**Inference:** request-context enrichment is now the strongest supported
mechanism: a validated application payload coexists with retained path text in
indexed context and the Worker request envelope. The official [telemetry event
schema](https://developers.cloudflare.com/api/resources/workers/subresources/observability/subresources/telemetry/methods/query/)
describes those metadata/Worker envelopes independently of `source`. This is
structural evidence consistent with platform enrichment, **not definitive
attribution to a particular platform logger or proof that invocation suppression
failed**. Original request-ID/suffix attribution and capture settings retain the
limitations recorded in the first-result section.

### Chosen next branch: Queue-only sink, staging first

The second result is sufficient to choose the containment experiment without
another broader historical query: move only the reviewed safe events over a
private Queue binding to a queue-only logging Worker, and disable retained
observability on the request-facing producer. This changes the sink invocation
context rather than trying to redact an original request after enrichment.
[Workers Logs](https://developers.cloudflare.com/workers/observability/logs/workers-logs/)
documents queue invocation messages as queue names, supporting the experiment;
it does not guarantee that every retained sink field is safe. Preserve the
existing API/CLI and causal trace IDs, and validate the envelope at both ends.

The Queue branch is justified by observed context retention despite a reviewed
source, even though the indexed row type is unrecognized. It does not require
declaring the platform producer conclusively known. A fixed-URL service logger
is a smaller alternative, but caller-context propagation remains an unproven
boundary; Queue delivery provides a distinct non-HTTP invocation to test.
Analytics Engine sampling/retention still makes it unsuitable as the only
per-event causal diagnostic store for this contract.

**No unsafe dual logging:** deploy/review the private sink first, then switch
the producer's typed handoff and retained-observability settings together at a
pinned staging version. Do not retain the old request-facing console path for
comparison or fallback. Check traces, invocation/custom capture, destinations,
tails and preview exposure, not only one flag. Queue outage must not restore
unsafe request logs or alter mail results. Rollback preserves source retention
off; temporary reduced diagnostics is safer than reinstating the evidenced
leak. Queue messages and any dead-letter copies are also retained data and need
the same payload allowlist and explicit retention bounds.

**Acceptance remains outstanding:** independently review the implementation,
run hosted tests, then establish complete retained sink records and queued
envelopes contain no synthetic path/query/mail/body/header markers, preserve
CLI-to-API parentage and denial isolation, and behave safely on dependency or
schema failures. [At-least-once delivery](https://developers.cloudflare.com/queues/reference/delivery-guarantees/)
requires stable event identity and duplicate-aware interpretation; Queue ACK is
not a Workers Logs persistence receipt. Keep the production privacy/public-send
gate closed until that exact deployed acceptance passes. See the migration and
failure-model sections below for the remaining contract, and the dedicated
[Queue-sink ADR](mail-trace-queue-sink-decision.md) for the concrete architecture.

## First historical result: exact interpretation

[Hosted read-only run `36713163067`](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36713163067)
returned the fixed line:

```text
carrier=other_or_multiple type=other_or_mixed component=path_only records=1
```

This used the already reviewed historical service/window classifier, not new
traffic or a fresh privacy canary. Interpret its bins through
`infra/tests/staging_trace_marker_location.py`, not their colloquial names:

| Observed bin | Supported conclusion | Not supported |
| --- | --- | --- |
| `records=1` | Exactly one returned record contained a recognized canary-prefix match. | Only one total event was returned; only one leaf in that record matched; exact attribution to the discarded original request ID. |
| `carrier=other_or_multiple` | Either a matched leaf was in the catch-all category, or two or more distinct carrier categories matched within this one record. | Multiple distinct records, emitters or defects; a leak specifically in `source`, `$metadata.url`, or `$workers.event.request`. |
| `type=other_or_mixed` with `records=1` | This single matching record's **top-level** `$metadata.type` was absent, non-string, or a string other than the two exact recognized literals. | Mixed event types across matching records; proof of invocation capture, a custom log, or native tracing. |
| `component=path_only` | The complete returned view contained a recognized path prefix and no recognized query prefix, with one consistent suffix. | Query redaction works for all requests; no query was stored outside this view; the path prefix necessarily appeared in a literal URL rather than a copied message. |

The transport required a completed, bounded, cursor-complete dry events query;
the classifier additionally required unique record IDs, exact staging service and
timestamps, supported `source`/`dataset` shape, and rejected explicit malformed or
true `$workers.truncated`. Those checks establish the scope of this finding, not
unconditional provider completeness or retention of every invocation. The
original random suffix was deliberately not persisted, so prefix attribution in
this short historical interval is strong bounded evidence, not an exact
request-ID proof. **The privacy gate remains closed.**

There is a concrete representation ambiguity worth discriminating once.
Cloudflare's [REST telemetry schema](https://developers.cloudflare.com/api/resources/workers/subresources/observability/subresources/telemetry/methods/query/)
places optional event type in `$metadata.type` and permits generic Worker event
enrichment. Its [Workers Logs guide](https://developers.cloudflare.com/workers/observability/logs/workers-logs/)
identifies invocation type at `$cloudflare.$metadata.type`. This documentation
difference makes a wrapper or type-location mismatch plausible; it does **not**
prove that the retained row used that shape, nor license searching arbitrary
nested `type` fields as authoritative classifications.

## Second-discriminator design (now exercised): preserve structure, never values

The useful question is now: **which predeclared structural carrier categories
matched, and where is the recognized event-type discriminator?** Do not repeat
the same lossy four-bin result, generate traffic, expand the interval, query by
marker value, export a row, or change deployed settings first.

Retain the exact historical window/service, dry transport, pagination and shape
guards. Replace the single carrier winner with independently reported fixed
presence bins (or a fixed ordered set of those labels), so simultaneous matches
are not collapsed. The minimum informative partition is:

1. Existing exact indexed URL and application payload/message categories.
2. Indexed request-context names (`trigger`, `spanName`, `transactionName`),
   separately from derived message/error text (`messageTemplate`, `error`,
   `errorTemplate`) and other indexed metadata.
3. Worker request enrichment, other Worker event enrichment, diagnostic-channel
   messages, and remaining Worker metadata, separately from application source.
4. The same exact predeclared URL/context/message/request categories under a
   literal `$cloudflare` wrapper, plus wrapper remainder. A wrapper is a
   structural observation, not proof that its text was emitted by the platform.
5. An explicit unmatched remainder for all other leaves, never their names.

For the matching record, report independent type-state bins at the exact
top-level `$metadata.type` and literal `$cloudflare.$metadata.type` locations:
`absent | malformed | unrecognized | cf_worker_event | cf_worker_log` (plus a
distinct absent-wrapper state and `mixed` only when multiple matching records
have different states). These are indexed/type-location observations, not a
claim to identify the telemetry producer. Do not echo the unknown
string, normalize it into a recognized type, or infer a type from a URL-bearing
message. If multiple matching records unexpectedly appear, report bounded
per-category presence/type-state sets, not an arbitrary first record or
lossy majority. Component and hit-count bins remain as before. A matched-carrier
count and matched-leaf count may use `1 | 2_plus`; count structural leaves, not
repeated appearances of the marker within one string.

Two fixed hints can help select the next source/settings check without exposing
values: allowlisted `$workers.eventType` (with explicit absent/unknown/mixed
states), and whether the inspected source parses as the already reviewed
application event schema (`allowlisted_application | unallowlisted_application |
not_application_schema | mixed`). These hints do not explain a hit in another
carrier: safe source plus an unknown error/wrapper hit is not an enrichment
attestation, and `eventType=fetch` is not proof of invocation-log type.

The implementation and synthetic tests must declare the exact labels/paths
before a second hosted read. Unknown structures stay unknown rather than
triggering recursive schema expansion. All visible fields remain scanned for
markers; a failure of shape/completeness, mismatched suffix or no surviving hit
is still **UNVERIFIED**. This is a deliberately limited diagnostic contract,
not a reusable arbitrary telemetry inspector or a privacy acceptance checker.

| Follow-up structure | Remediation decision |
| --- | --- |
| Only known request-context/enrichment carriers; recognized custom-log type; no application/message/error or remainder hit | Review the sink-boundary options below. An application regex cannot remove platform context before persistence. |
| Recognized invocation type at a reviewed exact type location | First reconcile the historical serving version and effective capture settings; type-location correction alone does not repair capture. |
| Application source or message/error text hit, including a wrapper's message representation | Audit the deployed emitter/generated shim/platform wrapping path. Do not relocate an unsafe payload and call that redaction. |
| Both context and payload carriers | Preserve both findings; they may be copies of one cause or separate causes. Determine the payload producer before selecting a combined fix. |
| Only known context, but no authoritative recognized type | Context retention is established structurally, while invocation-versus-custom remains unresolved. Review containment/sink separation without claiming invocation suppression failed. |
| Unknown remainder, conflicting type locations, incomplete/expired/no surviving hit | No single emitter-specific fix is justified. Keep the gate closed and use source/settings evidence to choose a separately reviewed containment experiment, not an indefinite sequence of broader historical queries. |

## Classifier result -> next action

Treat multiple carriers as multiple observations, not automatically multiple
defects: a single URL can be copied into several indexed fields. Every observed
unsafe carrier must be eliminated, but causation may be shared.
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

## Sink options after locating request-context carriers

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

The second classifier has justified the Queue-sink experiment, but has not
attested it. Implement/review only the new sink, typed handoff and readback
guards. Hosted tests cover schema rejection,
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
The actionable next step is the independently reviewed Queue-sink design and
implementation, followed by hosted tests and one pinned deployed privacy gate,
not another broader historical query or a speculative production rollout.
