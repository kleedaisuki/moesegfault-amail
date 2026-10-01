# Enriched CLI telemetry capability

Status: bounded source implementation, awaiting hosted exact-head acceptance.
Baseline main bfb0276 has accepted optional attempt readers, local/auth command spans and detached receipt/
retention source. Source acceptance is not a Mail/sink deployment or production
privacy acceptance. This work introduces no provider operation or mail campaign.

## Minimal protocol

1. Ordinary **authenticated** Mail API responses announce exactly one header:
   `X-Amail-Telemetry: attempts-v1`. Public health/inbound and authentication
   failures do not announce. Missing required `TRACE_EVENTS` binding also prevents
   the announcement; binding presence is not proof of the consumer's version.
2. Existing clients ignore this additive response field. Current/new clients
   require the exact single token from the configured API origin. Missing,
   duplicated, malformed, future/unknown or cross-origin response metadata is not
   capability. No extra GET, user environment mode or manual opt-in is introduced.
3. Capability is a server/realm parser property, not account authorization or a
   JWT claim. Cache one bounded observation scoped to canonical API origin plus
   configured Identity issuer and client ID. Do not persist token, credential
   fingerprint, subject or account identity. Every upload still acquires current
   credentials and passes ordinary server authentication independently.
4. Learn the observation when complete HTTP headers arrive, including a response
   whose body subsequently fails. Persist it after the original attempt's clock
   is frozen, before detached scheduling. Header capability never changes command
   success: HTTP200 plus body failure remains the original `response_body`
   failure with received200 and safe cause.
5. Unknown/expired capability uses the unchanged legacy JSON at `/v1/telemetry`.
   Known capability sends validated optional `started_at_ms`, `elapsed_ms`,
   `phase` and `error_kind` at the explicit new POST route
   `/v1/telemetry/attempts`. Legacy/historical rows without valid complete attempt
   metadata remain legacy-shaped, even within a capable batch.

## Why an explicit upload route is necessary

A cached header/TTL alone cannot prevent a rollback between an ordinary response
and the detached upload. The old `/v1/telemetry` handler rejects unknown fields
with `deny_unknown_fields`. A version header or new Content-Type does not make
that older parser honor negotiation. A new path instead becomes an authenticated
404 **before** its legacy telemetry JSON parser runs. Thus enrichment never enters
the old strict route, even with stale announcements or mixed deployed versions.

On an enriched-route404, clear capability, keep pending rows and record the real
HTTP failure. Do not retry the POST in that uploader, invent acceptance, or issue
a capability probe. The existing next normal scheduling opportunity can submit
legacy. Latest ordinary response metadata likewise downgrades missing/unknown
announcements. A fixed five-minute freshness window limits dormant stale observations;
it is an optimization/freshness rule, not the rollback safety proof.

## Deployment/binding and account boundaries

The checked deployment graph already orders tested sink deployment/readback
before API promotion. Deploy the optional-field Queue reader before a capable
API version; prohibit independently rolling the consumer back below that reader
while any announcing API version remains active. The new API route/header promise
the parser contract, **not** completed Queue delivery. Existing `accepted` receipt
semantics remain API acknowledgement only.

The capability is uniform across authenticated users of the configured API/issuer/
client realm. Switching only the current user does not grant authority or change
schema support; current bearer authentication is still required. Switching API
origin, issuer or client ID must not reuse another realm's capability. This does
not redesign the pre-existing local journal's account/endpoint ownership policy;
no user subject is added to retained diagnostics.

Operational correction: the owner's existing account is in **production**, not
staging. Rejection against staging can be an issuer/data-realm mismatch and is not
evidence of an unresolved production login defect. All source tests use dedicated
synthetic staging/loopback fixtures; no user password, user keyring or actual
account/provider debugging is authorized here.

## Compatibility and honest coverage

* Legacy clients, upload route, body schema, ACK receipt, saved send keys and
  auth/refresh state are unchanged.
* Opt-out skips capability persistence/upload as well as existing collection.
* Historical rows never acquire fabricated clocks/phase from the uploader.
* Exact client metadata is validated against the shared reader contract before
  adding fields; unknown metadata falls back to the historical wire shape.
* Legacy remote readers cannot reconstruct a phase they were never sent. Their
  coarse status-derived view is not promoted into proof of a completed operation;
  the exact local failure journal remains authoritative until enrichment is used.
* Local/auth command spans belong to a separate bounded local table, not remote
  `events`, so ordinary local operation names cannot poison legacy upload batches.

## Hosted acceptance plan

Verify on GitHub Actions only:

* Ordinary real HTTP response headers: exact/missing/unknown/duplicate tokens,
  full and truncated bodies, same versus different origin, realm changes,
  freshness/clock rollback and telemetry opt-out.
* Actual uploader: unknown→legacy, announced→enriched, old/invalid rows→legacy,
  explicit versioned endpoint, rollback404 invalidation with pending rows kept,
  no probe or same-attempt retry, complete ACK acceptance unchanged.
* Shared exact attempt validation and Mail route/auth/binding announcement
  boundaries; existing native Queue reconstruction retains source clocks/status,
  and200-body-failure becomes `phase_failure` rather than success.
* No diagnostic persistence wait enters the original HTTP attempt duration,
  no business output/exit changes, and no raw metadata/body/credential retention.

Industry grounding: HTTP response extensibility and conservative POST retry
semantics in https://www.rfc-editor.org/rfc/rfc9110.html complement the existing
OpenTelemetry failure/duration distinctions. Causal monitoring and analysis-aware
sampling research cited in runtime-observability-foundation.md remain downstream
of this accurate baseline, not reasons to build a generic negotiation framework.
