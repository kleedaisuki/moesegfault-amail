# v0.2.0 privacy-safe distributed tracing

## Outcome and implementation boundary

The subscription flow must be diagnosable as real causal spans, not merely logs
that happen to share a UUID. Mail keeps its private typed Queue/sink boundary;
automatic HTTP/invocation capture remains disabled because checkout credentials,
mail addresses, paths, query strings and provider errors can contain private data.

The release must preserve these distinctions:

* A CLI command journal ID is local recovery state, not a remote span ID.
* An HTTP attempt has a random W3C trace/span ID; API authentication precedes
  adopting its incoming `traceparent`.
* A Mail server span has a different span ID and the CLI attempt as its parent.
* Each Billing HTTP client span is created **before** transport. Its propagated
  `traceparent` contains exactly the same span ID retained at completion.
* Billing's server span adopts that client span as its remote parent after
  authenticating the service caller. Hosted authorization retains safe creation
  context in server-owned session state; credentials never become trace fields.
* Queue transport preserves producer event/span IDs. Sink receipt time and Queue
  invocation IDs must not replace application timing or causal context.
* Durable send reservations preserve the originating Mail server `traceparent`.
  Acceptance copies that context into the immutable usage outbox. Later delivery
  continues the original trace/parent and separately links the actual scheduler
  root with the closed `linked_trace_id`/`linked_span_id` pair. The span sent to
  Billing is still exactly the client span retained at completion.

The shape is:

```text
CLI HTTP attempt
  └─ Mail request
       ├─ D1 / R2 / provider dependency
       └─ Billing HTTP client
            └─ Billing service request
                 └─ later human approval (persisted safe context)

scheduled maintenance root
  ├─ addresses
  ├─ outbound
  ├─ embeddings
  ├─ storage
  ├─ deleted
  ├─ orphans
  ├─ search
  ├─ abuse
  └─ billing usage outbox
       └─ links to Billing HTTP clients in originating send/consent traces
          (at most three per sweep; original parentage is not overwritten)
```

## Changes from v0.1.2

The existing CLI already propagates W3C context and retains exact attempt start,
elapsed time and closed failure boundaries. Mail already emitted parented
dependency IDs, but only retained duration buckets, so a faithful timing waterfall
could not be reconstructed. Scheduled maintenance emitted only failure conditions,
not a successful run/root or timed stages. There was no Billing operation grammar.

The v0.2.0 implementation adds exact UTC start and elapsed milliseconds to Mail
request/dependency spans; a consuming dependency handle propagates and completes
the same child ID; fixed Billing operation names; and an independent scheduled
root with nine timed child phases. The scheduler retains its immutable final-tail
deadline and performs one bounded Queue submission without replay on timeout.
The maximum batch is 27 records: nine stage spans, one root, at most three Billing
HTTP spans and fourteen fixed diagnostic conditions. Diagnostics are standalone conditions; stage
failure spans are the causal run view.

The typed sink accepts only validated fixed vocabularies and numeric facts. New
producer vocabularies require deploying its same-source reader first. No raw
URLs, paths, query strings, SQL, mailbox aliases, subjects, bodies, attachments,
account identifiers, auth codes, credentials or arbitrary dictionaries are added.
No customer ID is needed to reconstruct a trace.

## Integration contract

Mail call sites use:

```rust
let span = trace.dependency(request_id, Phase::BillingHttp);
headers.set("traceparent", &span.traceparent())?;
let result = /* authenticated Billing transport */;
span.finish_http(result.is_ok(), observed_http_status);
```

The result must represent the actual dependency outcome, not an unrelated later
parse result. When HTTP headers exist, preserve their numeric status even if
reading or validating the body fails. Transport failure has no invented status.
Never retry a potentially committed Billing mutation merely because telemetry
failed. The handle consumes itself on finish to prevent duplicate completion.

CLI telemetry operation labels are exactly `billing.status`,
`billing.session.create` and `billing.session.status`. These are mapped to closed
snake-case wire operation values. Subscription polls have their own HTTP traces;
the hosted session's durable creation context joins the subsequent human action,
not a guessed context from a browser URL.

Billing and Subscribe retain their closed spans directly in their own D1 stores,
indexed by trace ID and expiring after seven days. Their HTTP Workers keep Logs,
native Traces and Issues off. Safe JSON inside an HTTP console log is insufficient:
the platform's enclosing event may still contain the original path/query. The
typed D1 store avoids retaining that raw envelope entirely. Telemetry insertion
is best effort and cannot replace an already committed authorization response.

The hosted BFF persists the validated Billing creation/GET context in server-owned
D1 state against a capability hash, expiring after thirty minutes. Subsequent
approval/cancellation adopts it **before** creating the BFF server/client spans.
Billing honors an authenticated same-creation-trace incoming BFF client parent;
only the initial browser GET needs restoration from the durable creation context.
No tracing capability is placed in a URL or supplied by browser input.

Mail `billing_sessions.origin_traceparent` is captured before the first external
creation call and never overwritten by polls/retries. Applying a receipt resolves
that receipt's actual authorization ID to its saved source context; a superseded
session or a routine refresh cannot become a new financial-consent origin. Stock
usage keeps this source; send usage keeps its individual provider-attempt source.
Unknown and accepted sends preserve the same reservation context across recovery.

## Acceptance evidence required

1. Real CLI request emits a W3C parent and an exact locally journaled attempt.
2. Mail adopts that trace only after authentication, creates a distinct server ID,
   and retains both exact timing and outcome.
3. Billing transport receives the retained Mail child ID as its parent; Billing
   server output has a distinct span ID and matching trace ID.
4. Hosted approval joins durable creation context, and agent polling observes the
   approved subscription without agent-only authorization.
5. Synthetic provider failure leaves safe status/outcome records without changing
   idempotent write/recovery semantics.
6. A scheduled no-op still emits a timed root and each attempted phase. Root
   outcome reflects failures/deferred phases. Queue deadline/size bounds hold.
7. Private retained sink output (not upload HTTP acceptance alone) proves delivery.
   Repeated event IDs after Queue redelivery are deduplicated by consumers.
8. Witness output is content-free. Any trace validation failure names a fixed
   boundary, never prints offending raw records.

Unit contracts cover the closed grammar, stable dependency propagation/completion
identity, exact clocks, scheduling grammar and forbidden-field rejection. Hosted
simulation and staging evidence must be recorded here when actually observed;
this design note is not itself deployment or retained-delivery evidence.

## Standards and trade-offs

W3C [Trace Context](https://www.w3.org/TR/trace-context/) defines remote parent
propagation. OpenTelemetry's [Tracing API](https://opentelemetry.io/docs/specs/otel/trace/api/)
and [trace model](https://opentelemetry.io/docs/concepts/signals/traces/) distinguish
timed spans, events and links. The implementation uses that causal model without
an auto-instrumentation SDK that would accidentally retain request content.
UTC clocks can skew across hosts; parentage is authoritative and durations must
never be inferred by subtracting timestamps from different hosts. A custom typed
transport is not native Cloudflare tracing or an OTLP collector, and a partial
retained trace must never be described as a complete captured waterfall.

## Retained staging witness

`infra/tests/staging_trace_witness.py` reads the existing Mail sink's typed logs via
Cloudflare's [Observability query API](https://developers.cloudflare.com/api/resources/workers/subresources/observability/subresources/telemetry/methods/query/).
It is not a capture service. The API currently requires `Workers Observability
Write` permission even for a dry query; a missing scope is an explicit unavailable
retention witness, not permission to broaden credentials or enable native capture.

The Mail reader accepts only the fixed staging sink script name;
each query includes an exact opaque trace ID, a maximum fifteen-minute window,
128-event maximum and a two-megabyte HTTP-response limit. It does not paginate,
discover fields, search across an account or retain provider envelopes. Only
validated closed records are projected into memory. Unknown fields, private text,
bad identifiers, missing clocks, truncation and malformed responses fail with
fixed content-free error labels. Repeated event IDs must have identical payloads.

Billing and Subscribe are read through their fixed staging origins with
`POST /v1/service/amail/trace-query`, exactly `{"trace_id": "..."}` in the body and
the shared stage service key in the `Authorization` header. The response is
exactly `{"schema_version":1,"spans":[...]}`. The same 128-record/two-megabyte
bounds apply and expired records are excluded by the service. The key stays in
memory: never pass it in a command-line argument, URL or diagnostic. No provider
HTTP console query is used for these services.

Hosted acceptance can call:

```python
from infra.tests.staging_trace_witness import SCRIPTS, read_records, read_service_records, witness

records = read_records(account, token, SCRIPTS["mail_api"], trace_id, start_ms, end_ms)
for service in ("billing", "subscribe"):
    records += read_service_records(service, shared_stage_key, trace_id)
summary = witness(records, trace_id, require_cli=True, require_authorization=True)
```

The trace ID and timestamps come from the actual native CLI's diagnostic request
row; they are not derived from mail, addresses, tokens or a checkout URL. The
result proves retained CLI→Mail server→Billing HTTP client→Billing server ancestry.
With authorization required it additionally requires a successful authorization
span whose actual remote parent is a retained Subscribe client span beneath the
retained approval server span, all connected to creation context. This is supplementary to browser acceptance,
not proof by itself that a human approved or money was collected. No raw console
or provider response may be uploaded as an artifact.

2026-10-07 local evidence: the seven focused Python reader/witness tests and three
real SQLite migration-preservation tests passed;
targeted `rustfmt` parsing and `node --check` for the expanded compiled sink test
passed; scoped `git diff --check` passed. Rust/native sink execution and live
retained delivery remain hosted/staging acceptance requirements, not inferred
from these static and mocked checks.
