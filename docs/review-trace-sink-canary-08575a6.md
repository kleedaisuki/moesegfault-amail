# Independent source review: Queue-sink retained privacy canary

Reviewed: `08575a6` and `c37c25d`; integration comparison against the current
shared Rust trace schema (source commit `96a6181`). Review date: 2026-09-30.

## Decision

**GO for hosted synthetic CI. NO-GO for a guarded deployed acceptance run until
finding R1 is corrected and hosted tests pass.** This is not live privacy
acceptance. No local tests/builds, live traffic, private logs, secrets, or deployment
were accessed. CI YAML/reusable workflow is separately owned and excluded.

## R1 — P2: retained schema checker does not mirror the current wire contract

Location: `infra/tests/staging_trace_sink_canary.py:133-143` (`safe_event`).
Confidence: high, source-traced; synthetic reproductions below are not executed.

Non-maintenance events are delegated to the old `legacy.allowlisted_event`.
That helper checks vocabulary and broad numeric syntax, but does not enforce
Rust `Event::valid_request`, `valid_client`, or `valid_phase` field combinations.
For example, adding `provider_http_status=403` or
`error_code="dependency_failure"` to the valid successful `addresses_list`
request-root fixture passes `safe_event` and the root checks in `assess`, while
Rust `Event::valid_request` rejects it. A regression retaining incompatible
fields can therefore still earn the advertised typed-schema attestation.
This is an acceptance-oracle defect, not evidence of current private-data leakage.

The reverse drift also exists: the maintenance branch requires
`operation="maintenance"` and no parent. Current Rust `valid_diagnostic`
intentionally also permits operation-scoped diagnostic events with a parent,
and `Trace::warning` constructs them (trace.rs:275-281). An otherwise safe
concurrent request diagnostic in the bounded sink window would fail the entire
canary. Byte buckets above 1 GiB and at most 4 GiB are accepted by the Rust
contract but rejected by the legacy helper's extra 1 GiB cap.

Correction: keep the new canonical-ID/bucket guards, replace legacy schema
validation with the current explicit service/phase field-combination contract,
and include hosted synthetic fixtures for valid request-scoped diagnostics,
valid boundary byte buckets, and invalid provider/error/service/phase/root
combinations. Do not weaken or change the old checker used by prior canaries.

## Positive assessment

- All four literal markers are scanned across the entire serialized retained
  record, including keys, platform enrichment, and custom payload; stdout has
  only fixed categories. Helper stdin avoids marker-bearing process arguments.
- Cursor/count completeness, stable record IDs, maximum page/window/response
  limits, completed dry-query status and exact service/timeframe/filter echoes
  are inherited without mutable global service changes. Record truncation and
  ambiguous/unknown application payload fail closed.
- Identical Queue redelivery is deduplicated by event ID; conflicting event-ID
  reuse fails. Authenticated CLI journal parentage and anonymous trace isolation
  are checked independently of sink invocation context.
- Both service versions and effective privacy settings are checked before
  traffic and after retained readback. Missing/split/changed versions fail.
- A late-read allowance repeats only the same fixed read window, never traffic;
  first-read record IDs cannot disappear from the second read. Source retained
  rows invalidate acceptance. Documentation accurately limits this to a bounded
  indexed window, not pending Queue/DLQ envelope or globally lossless tracing.
- Old no-flag and `--private-id` Rust helper requests remain GET; only the new
  exact flag adds synthetic POST body/header/untrusted traceparent carriers.

## External basis and limits

Cloudflare's [Workers Logs documentation](https://developers.cloudflare.com/workers/observability/logs/workers-logs/)
distinguishes invocation logs and application logs; its
[Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/)
recommend structured observability and asynchronous platform bindings. These
support the architectural boundary, but do not establish actual retained
privacy. The inherited pagination contract and settings readback require hosted
and live evidence; review alone cannot prove provider indexing completeness or
future absence. Queue/schema implementation and CI wiring have separate reviews.

## Narrow recheck — R1 resolved (`4781278`, Rust `728f2c3`)

Decision: **GO for hosted synthetic CI and source-level use as the bounded live
acceptance oracle.** Actual live acceptance still requires green hosted tests,
reviewed deployment/wiring, effective settings and version pins, and a successful
guarded run. This supersedes the earlier R1 dispatch restriction, not the stated
privacy scope/limitations.

Source comparison confirms `safe_event` no longer delegates to the legacy schema
checker. Its exact service/phase branches now match Rust's request, dependency,
CLI, and diagnostic combinations, including the current ten CLI operations.
Prior impossible successful-root provider/error fields are rejected; mandatory
API span/request IDs are enforced; status/outcome/error combinations agree.
Standalone and parented operation-scoped maintenance events are accepted only in
the respective Rust-defined forms. Power-of-two request/response byte buckets
through 2^32 are accepted without the former secondary 1 GiB cap. UUID checks
also require the RFC4122 variant. Optional field omission/null semantics agree
with serde Option deserialization.

Added hosted synthetic tests cover the prior bad success status/error/provider
cases, valid status/error combinations, standalone/parented maintenance positive
and negative cases, 4 GiB boundaries, routing-create-only provider fields, exact
CLI operations and legacy optional CLI IDs. The fix changes only the new canary,
its synthetic tests and documentation; old helper and legacy checker behavior
are untouched. No substantive remaining defect found in this narrow recheck.
No tests/builds/live traffic were run locally, and CI wiring remains excluded.
