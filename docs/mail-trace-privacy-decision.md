# Decision: privacy-safe distributed correlation for mail Workers (2026-09-29)

Status: original source design followed by **2026-09-30 evidence-driven sink
revision**; not a deployed privacy claim. This complements
`review-mail-observability-privacy.md`. No raw private telemetry, mail, secret,
or deployed setting is reproduced here.

## Superseding sink decision after retained-context evidence (2026-09-30)

The original recommendation to retain allowlisted custom events directly on
the request-facing Mail Worker is **not sufficient for the required privacy
boundary**. The live marker failure in `36703733769` was followed by a bounded
structural historical read, [run `36723490687`](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36723490687)
at classifier source `d8b9631`, for the same 10:42:00–10:42:37 UTC staging
window. Its fixed output locates a path marker in `metadata_context` and
`workers_event_request`, across at least two leaves in one matching record,
with `source_shape=allowlisted_application`, `metadata_type=unrecognized`,
`wrapper_type=wrapper_absent`, `trigger=fetch`, and `component=path_only`.

This supports request-context enrichment coexisting with a reviewed safe source.
It does not conclusively identify the producer, prove invocation capture stayed
enabled, or attest every payload/exception path. The [precise evidence and
limitations](mail-trace-sink-remediation-options.md#second-historical-result-request-context-retention-located)
are the operative rationale; no further broad historical read is needed to
choose the next containment experiment.

**Revised decision:** preserve typed application events, existing W3C causal
IDs, local CLI telemetry privacy and all mail APIs, but move the safe events
through a private Cloudflare Queue binding to a queue-only logging Worker.
Disable retained observability on the public request-facing producer. The sink
receives only the reviewed bounded envelope, not the triggering Request, URL,
headers, mail data or arbitrary exceptions; validate at both boundaries.
The consumer's non-HTTP invocation is a different enrichment boundary to test,
not an assumed privacy guarantee. Stable event IDs, bounded retry/retention and
duplicate-aware reading address Queue at-least-once delivery; diagnostics remain
best-effort and cannot change business success/failure.

Deploy the reviewed sink first, then atomically switch the producer's handoff
and retention settings at a pinned staging version. **No unsafe dual logging or
raw-error fallback**: do not keep the old request-facing retained logs to compare
results, including on rollback or Queue failure. Audit capture/export/tail and
preview settings independently. The earlier direct-source settings recipe below
is historical implementation context, **not the new rollout recipe**. Do not
apply it to re-enable the unsafe source.

The production privacy/public-send gate remains closed until independent review,
hosted tests and exact deployed retained-data/failure canaries establish marker
absence and preserved parentage through the new sink. The [Queue-sink contract
and migration conditions](mail-trace-sink-remediation-options.md#minimal-queue-sink-contract-and-failure-model)
remain required. This revision selects the next evidence-producing design;
it does not claim implementation, deployment or acceptance is complete. The
concrete target architecture is recorded separately in
[the Queue-sink ADR](mail-trace-queue-sink-decision.md).

### First containment upload is not an effective-settings pass

[CI `36725878855`](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36725878855)
at `9c0d5ab` passed core hosted tests and uploaded staging Mail version
`759906b4-bdb9-488a-a980-a4bada8ba83e`, then returned
`Mail observability staging: UNVERIFIED` at the effective readback. **Logs-off
has not been proven and no safe serving pin follows from the upload.** The
aggregate checker result cannot identify the failing setting or distinguish
policy mismatch from unavailable/malformed readback. The [containment-attempt
record](mail-trace-sink-remediation-options.md#containment-deployment-attempt-effective-state-still-unverified)
preserves the exact evidence and separate private-inbox HTTP0 failure. A
reviewed targeted fixed-bin readback diagnostic, not blind redeployment or a
fresh privacy canary, is the next discriminator. No production/public-send or
new mutation gate is opened by successful source tests alone.

### Readback representation located; effective capture remains unknown

[Read-only diagnostic `36730461386`](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36730461386)
at branch source `b536963` observed `stable100` around expected staging version
`c3f6401a` (abbreviated ID). [Core CI `36728726698`](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36728726698)
had uploaded that version but failed the post-deploy observability checker.
The diagnostic's `/settings` observation was `observability_shape=missing`,
all observability child shapes/members `missing`, `logpush=false`, `tails=false`.
Its `/script-settings` observation was `observability_shape=other`, all such
children `missing`, `logpush=false`, `tails=other`.

This explains an explicit prerequisite rejection in the strict checker:
neither observability representation is the required dictionary. It does **not**
prove capture is on, off, or governed by a safe Cloudflare default. Missing
children under a non-dictionary parent are classifier categories, not individual
effective false flags; `tails=other` is not evidence of enabled consumers.
`stable100` establishes a bracketed serving-version observation, **not a safe
containment pin or retained-data privacy pass**. The [full fixed-bin record and
limitations](mail-trace-sink-remediation-options.md#fixed-bin-settings-diagnostic-stable-deployment-absentnon-object-configuration)
are authoritative for this result. Resolve the authoritative effective readback
contract before changing the verifier or attempting Queue rollout; do not
repeat the same deployment or infer permission to send new canary traffic.

## Original decision in one sentence (direct-source sink superseded)

Retain reviewed, allowlisted **application trace events** in Cloudflare Workers Logs, linked by W3C trace/span IDs across CLI and the mail API; disable Cloudflare's automatic invocation logs and native traces for the mail API in both realms until Cloudflare can exclude sensitive automatic fields *before persistence*. This is a real causal distributed trace graph over structured events, but **not** the Cloudflare native Traces waterfall or automatic D1/R2/fetch spans.

## Why native tracing cannot be the privacy-safe default

The following background and original implementation recipe preserve the
2026-09-29 investigation snapshot, not current serving-setting evidence. The
superseding decision above governs sink rollout; consult the later live-result
documents for observed state instead of treating historical "current" wording
as a new readback.

| Boundary | Current code / platform capture | Consequence |
|---|---|---|
| Public `#[event(fetch)]` API | The API currently enables native traces and logs at 100%; staging has no explicit override. Cloudflare's Fetch Handler root span includes `url.full` and `url.path`; invocation log includes method and URL. The deployed staging readback was reported as `redact_query_string=false`. | Any caller can send a URL with an address, search text, or token in the **query or arbitrary path**, even if the router rejects it. Application redaction runs too late. |
| Outbound fetch / storage | Native spans include outbound `url.full`/`url.query`, D1 `db.query.text`, and R2 keys plus HTTP/custom metadata and error messages. The reviewed implementation normally uses bound SQL, fixed provider URLs, and random R2 keys. | Those practices reduce ordinary leakage, but native capture is still an independently evolving source. Query redaction cannot sanitize path, SQL literals, R2 metadata, or exception text. Do not claim that bodies or Authorization headers are automatically captured; the listed fields do not establish that. |
| Email ingress / event consumer | Ingress/event observability is already off; Email root spans include `cloudflare.email.from` and `.to`. | Keep it off. A lower sampling rate changes probability, not confidentiality. |
| Custom native spans | Cloudflare's JS `tracing.enterSpan()` requires `observability.traces.enabled=true`, nests with automatic spans, lacks manual parent wiring and `spanContext()` IDs. The current Rust worker-build shim is generated, not a maintained JS tracing layer. | Adding custom native spans cannot isolate the safe fields from automatic spans or reliably produce a CLI-to-native trace ID. Do not wrap Rust business logic in a JS shim just to gain a span UI. |

Cloudflare's current API schema says `redact_query_string` removes query strings from request URLs in logs **and** traces. Its Wrangler location is the **top-level observability object**, `[observability] redact_query_string = true`, not `[observability.logs]`. Wrangler 4.128.0 added this field; CI already pins 4.142.0. Correct the older location recommendation in `review-mail-observability-privacy.md` when implementing. Even correctly applied, it is defense in depth, not a justification for retaining native API traces: full arbitrary path survives.

## Minimal state and contract

The correlation state is one `TraceContext { trace_id: 16 random bytes, span_id: 8 random bytes, sampled }` per operation, plus an opaque server-generated `request_id` per API invocation. A server span uses the incoming CLI span ID as `parent_span_id` only after successful authentication; a private ingress span can use its generated W3C parent only after the shared secret has been checked. Empty/malformed/untrusted contexts start a fresh server trace. `tracestate` is never copied into retained data or forwarded to third parties. The existing `x-amail-request-id` response header and response JSON are unchanged.

The retained event schema is an **allowlist**, not arbitrary key-value attributes:

```text
schema_version, service enum, operation enum, phase enum,
trace_id (32 lowercase hex), span_id (16 lowercase hex),
parent_span_id (16 lowercase hex or absent), request_id (server UUID),
outcome/error_code enum, http_status_class, duration_ms bucket,
optional measured request_bytes/response_bytes buckets, retry_count bucket
```

Never serialize request/response, `Error`/`Debug`, URL, path, query, header, `tracestate`, email envelope, address, subject, body, attachment, archive path, provider error text, token, SQL bindings, vector, R2 key or message ID into this event. Use typed enums for names and phases, not caller-provided strings. A single Rust serializer emits a bounded JSON event, with a fixed static fallback on serialization failure; do not consume request bodies merely to measure bytes. Cloudflare recommends JSON logs for indexed fields, but verify whether the Rust `console_log!` string is parsed/indexed as expected in staging; if not, send the same typed event as a JS object through a tiny Rust/Wasm console bridge rather than changing the data model. One exit event per authenticated API request plus a few meaningful operation/phase events (routing, D1, R2, embedding) is enough; do not log every internal function. Keep existing fixed warning strings. A trace record is best-effort and must never change mail results.

Representative flow:

```text
CLI command span (trace T, span C)
  -- traceparent: 00-T-C-01 --> authenticated API request span (T, span S, parent C)
      -- local phase --> D1 operation event (T, span D, parent S)
      -- local phase --> provider call event (T, span P, parent S)
  <-- x-amail-request-id: R --
CLI journal/upload: operation, T, C, R, safe timing/status only
```

This is causal parent-child linkage, not merely matching a request ID. The current CLI already generates a W3C `traceparent` and journals the trace ID; the API currently reads/logs `traceparent` only on `/internal/inbound`, and the CLI telemetry upload lacks the span ID. Thus **today's CLI→API trace is not yet joined in retained data**. Server-first telemetry schema evolution should make CLI `span_id` optional, then add it to the local SQLite journal/upload without invalidating old records. Preserve the user-facing API and `AMAIL_TELEMETRY=off`; a disabled client upload still leaves the safe server span, not a fabricated client span.

W3C trace IDs are correlation handles, not secrets. Public clients can syntactically forge IDs or encode 16 bytes of data in one; validating syntax is necessary but cannot prove randomness. For authenticated clients, accept only exact version-00 lowercase hex layout, nonzero IDs, valid flags, no extra bytes; ignore malformed values without logging them, rate-limit event volume, and never use client events as authoritative server metrics. If the requirement becomes adversarial zero-leakage even against a user deliberately encoding secrets in IDs, public client-chosen trace IDs cannot meet it: issue server-chosen IDs and link the CLI by returned `request_id` instead, explicitly sacrificing a single W3C trace tree on the first request. This trust-boundary choice must be recorded, not hidden behind a regex.

Do **not** claim external OpenRouter traces join automatically. Cloudflare documents that external trace propagation is not yet automatic; the native API's `propagation_policy` is feature-gated and not a substitute for application verification. The current internal ingress→API service binding passes a fresh opaque `traceparent`; its API parent relation can be recorded safely, while ingress's automatic observability remains off. Queue/provider callbacks remain joined by the existing opaque request ID only until an independently reviewed safe event path exists.

## Required implementation and rollout order

1. **Immediate containment, staging then production:** Explicitly configure the API in both realms as below; leave ingress and event-consumer observability off and role-monitor's reviewed application logs only. Do not change routes, request/response bodies, binaries, or mail storage. Deploy via existing gated workflows. Sampling is **not** a redaction strategy.

   ```toml
   [observability]
   enabled = true
   head_sampling_rate = 1.0
   redact_query_string = true
   [observability.logs]
   enabled = true
   invocation_logs = false
   [observability.traces]
   enabled = false

   [env.staging.observability]
   enabled = true
   head_sampling_rate = 1.0
   redact_query_string = true
   [env.staging.observability.logs]
   enabled = true
   invocation_logs = false
   [env.staging.observability.traces]
   enabled = false
   ```

   In tests and post-deploy readback, require `observability.redact_query_string is true`, `logs.enabled is true`, `logs.invocation_logs is false`, `traces.enabled is false` independently for both scripts/versions. Check no unintended export destinations or Tail Worker consumers; Cloudflare account retention and access remain operational controls. Fail closed if the deployed values differ. The existing role-monitor verifier is a pattern for a no-mutation API settings verifier.

2. **Safe trace events, server first:** Add the typed Rust trace context/event module, strict parser and tests. Emit request-exit events after auth; generate a server trace on auth failure without reading/logging attacker `traceparent`. Preserve existing `request_id`. Add a safe internal ingress event after shared-secret validation. Do not make event emission part of mail success/failure control flow. Only after server records exist, extend CLI journal/upload to include an optional `span_id` and parent relation, retaining old SQLite rows and old `/v1/telemetry` payload compatibility.

3. **Canary and failure validation:** In staging, inject distinctive synthetic address/subject/body/query/token-like canaries in one normal request and one rejected URL with a canary in both query and path. Inspect **retained** API log/event fields with authorized restricted access, without copying raw records into CI or docs. Assert canaries absent; assert trace T, CLI C, API S, parent C, request R and safe status/phase present. Exercise bad `traceparent`, unauthenticated request, D1/R2/provider failures, and panic/uncaught exception paths with synthetic input. A config readback alone cannot prove exception/log behavior. Verify mail behavior and response contracts before production rollout.

4. **Future native trace reconsideration only with a new gate:** Require platform-level pre-persistence exclusion or proven sufficient sanitization of root URL **path**, email envelope, R2 metadata/error fields, and arbitrary exception text; confirm actual span attributes under canaries, propagation semantics, retention, export recipients, and cost. Do not switch on `tracing.enterSpan()` and assume it replaces automatic spans. If Cloudflare provides a safer native mode later, migrate event identity/trace IDs without changing external mail contracts.

## Rejected shortcuts

* `redact_query_string=true` plus native traces: protects query only, not arbitrary path or dependency metadata.
* Native custom spans with a sanitized attribute allowlist: auto-spans still coexist; IDs and manual parent control are unavailable today.
* A Tail Worker filtering native spans after emission: it cannot guarantee that Cloudflare never retained the original sensitive fields.
* Setting native trace sampling to zero or a small fraction: does not provide useful comprehensive tracing or a privacy guarantee.
* Disabling observability everywhere without a replacement: sacrifices safe,
  actionable diagnostics. Disabling retained observability on the unsafe public
  producer while adding the reviewed Queue sink is the revised decision, not
  this rejected shortcut.

## Sources

* [Cloudflare Workers Logs](https://developers.cloudflare.com/workers/observability/logs/workers-logs/) — invocation message and disabling invocation logs while keeping custom logs.
* [Cloudflare automatic spans and attributes](https://developers.cloudflare.com/workers/observability/traces/spans-and-attributes/) — Fetch root/runtime URL attributes, Email envelope, D1 SQL, R2 metadata.
* [Cloudflare custom spans](https://developers.cloudflare.com/workers/observability/traces/custom-spans/) and [known limitations](https://developers.cloudflare.com/workers/observability/traces/known-limitations/) — automatic-span coexistence, missing span context/manual parents, external propagation.
* [Cloudflare Workers API observability schema](https://developers.cloudflare.com/api/resources/workers/) and [Wrangler 4.128.0 release](https://github.com/cloudflare/workers-sdk/releases/tag/wrangler@4.128.0) — query redaction location and effective settings.
* [W3C Trace Context](https://www.w3.org/TR/trace-context/) and [OpenTelemetry tracing API](https://opentelemetry.io/docs/specs/otel/trace/api/) — trace/span ID and remote-parent semantics, privacy and trust boundary.
