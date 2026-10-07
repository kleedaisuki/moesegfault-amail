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

### Real retained-reader client identification failure and repair

The Free browser journey in run
[37619464034](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37619464034)
completed cancellation, approval, return-page navigation and the authoritative CLI
receipt. Its terminal failure was the retained reader's fixed diagnostic
`billing_retained_trace_unverified_billing_read_retained_trace_service_forbidden`.
The safe journey coordinates are retained in
`.temp/v020-free-37619464034/staging-billing-evidence.json`.

A bounded follow-up compared the same machine, fixed Billing/Subscribe staging
`POST /v1/service/amail/trace-query`, identical valid service credential and the
same trace ID from that evidence. The credential stayed in process memory. Only
status, media type, known response keys and validated span counts were printed;
error response bodies, headers, reason strings and raw provider prose were not
read or persisted.

| Client | Billing result | Subscribe result |
| --- | --- | --- |
| Python urllib default client identifier | 403, `text/plain` | 403, `text/plain` |
| Same Python request with `User-Agent: amail-staging-witness/0.2.0` | 200, `application/json`, `{schema_version, spans}` | 200, `application/json`, `{schema_version, spans}` |
| Node fetch default client | 200, `application/json`, same schema | 200, `application/json`, same schema |

This controlled comparison establishes a client-identifier-dependent response
difference and rules out an invalid service key as the explanation for these
specific 403 responses. It does **not** identify a particular WAF rule, bot score,
network intermediary or policy implementation. No security settings, permissions,
credentials, authentication flow or deployed production code were changed.

The witness now identifies itself honestly with that fixed product/version user
agent, without impersonating a browser. Focused tests assert this header on both
fixed readers while preserving all scope, redirect, authentication and byte limits.
All ten reader/diagnostic tests passed with `ResourceWarning` treated as errors;
syntax and scoped diff checks passed.

Using the repaired reader against only the six evidence trace IDs subsequently
validated 11 Billing spans and eight Subscribe spans. The approval creation trace
contained four validated spans from each service, including the closed approval
operation. A second bounded read of those same six IDs confirmed one actual
Subscribe approval server → Subscribe dependency client → Billing authorization
server parent chain on the approval trace. `connected_authorization` also returned
true using the recorded creation-context ancestor set, without inventing any
Mail or CLI span. This confirms the service read and safe-envelope path after the fix;
it does not substitute for the final hosted Mail-sink/CLI/Billing/Subscribe retained
ancestor-chain witness, subsequently completed against the admitted helper artifact
as recorded below.

### Optional real-meter evidence scope

The explicitly confirmed synthetic Lite address-meter path keeps actual
`resource_outbox.origin_traceparent` trace IDs and adds them to the normal
subscription/Manage/restore CLI journal IDs before the parent's final telemetry
flush. It deduplicates the union and rejects more than 16 trace IDs or an elapsed
Billing journey of 810 seconds. Restore approval traces therefore remain available
to the retained-reader witness; observing an outbox trace never replaces browser
authorization-chain evidence.

Only safe aggregate facts are returned: positive address-seconds, explicitly
denominated integer micros (USD for new usage, CNY only for separate history),
delivered-event count, four created/retired addresses, zero restored
budget, `pending_settlement`, and validated random trace IDs. Raw owner IDs,
addresses, event IDs, authorization URLs, activation codes, credentials and
provider response bodies remain in memory and are not evidence fields. The three
fixed D1 SELECTs and Billing usage GET use the existing honest
`amail-staging-witness/0.2.0` client identifier, bounded bodies and rejected
redirects. Their success proves actual ledger acknowledgement, not payment
collection or native vendor tracing.

The current polling admission leaves 135 seconds inside the 810-second envelope for
three 25-second reads and the parent's 60-second final flush. Together with the
existing 90-second retained-query reserve, this avoids admitting a last read whose
bounded completion alone would push the journey outside the 15-minute scope.

### Optional charged-outbox asynchronous retained witness

When `metering` evidence exists, ordinary authorization acceptance alone no
longer completes the retained witness. Every explicit `metering.trace_ids` entry
must independently pass the existing CLI / Mail / Billing / human-approval
ancestry verifier. A successful Mail `maintenance` / `billing_http` span must
have that exact creation Mail server as its parent and a successful real Billing
`billing_usage_record` request server as its child. Its validated link IDs then
select one separate bounded staging-sink read, using the exact linked span ID as
the query needle and projecting only the matching `scheduled_exit` record.
That record must be a parentless maintenance root on the linked trace. Unrelated
maintenance diagnostics are not retained or treated as acceptance evidence.

The verifier returns only trace/span IDs and counts for the asynchronous proof.
It compares causal IDs, not cross-host wall-clock order. A scheduler root may
report an unrelated phase failure while its usage dependency and remote usage
request succeeded. Reads retain the existing 128-event / 15-minute bounds,
20-second network timeout and shared 90-second retry deadline; the additional
read never starts after that deadline. No action is replayed, no provider writes
are introduced, and non-meter acceptance keeps its existing return shape.

Focused offline tests cover the complete asynchronous and hosted join, absent
links, wrong origin/usage/scheduler parentage, wrong usage operation, failed usage
dependency, missing CLI ancestry, unsafe scheduler fields, content-free async
errors, and rejection of absent or unrelated explicit meter trace IDs.

### Actual hosted asynchronous proof (2026-10-07)

[37630962022](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37630962022),
exact candidate source `d1291b80923d7d463e596bcd702a6e251039797f`, completed
successfully. Safe artifact `11486684051` records ordinary human/CLI acceptance
with 14 spans and the separate charged-origin proof with 20 spans plus one
separately retained scheduled root. The observed meter was seven address-seconds
and seven CNY micros, not a simulated or seeded outbox event.

| Causal boundary | Actual retained identity |
| --- | --- |
| Charged origin trace | `e365ea01443bb50609dd67ef3bebcbab` |
| Creation Mail server | `17f91fcc6ea94275` |
| Successful maintenance usage client | `2e37d9232c144bd4` |
| Successful Billing usage server | `62f56f328ead0db6` |
| Linked actual scheduled trace | `8dcef501e1ba4ab894d29141fc029b01` |
| Exact parentless scheduled root | `d3b2d315667d419a` |

Parent equality proved creation-server → usage-client → usage-server. The usage
client's link selected the exact separately retained scheduled root; wall-clock
proximity was not substituted for causality. Zero current budget and six delivered
period events matched the real pending-settlement ledger. The same run repeated
SMTP/archive/search and controlled self-send recovery/delivery acceptance.


### Actual fixed USD asynchronous proof (2026-10-07)

The monetary/retained-trace portion of
[37644087065](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37644087065)
passed on deployed Mail `27c5818` and Billing/Subscribe `86bb06e`. Safe artifact
`11494520444` records 14 ordinary human/CLI spans, 18 charged-origin spans and
one separately retained scheduled root. Normal allocation/retirement generated
14 excess address-seconds and 2 USD micros in two delivered events. The original
6 CNY events / 22 CNY micros remain independently readable and unchanged.

| Causal boundary | Actual USD retained identity |
| --- | --- |
| Charged origin trace | `1b9162ed6e2993a35b1fca190b80a25d` |
| Creation Mail server | `17fa27721f094203` |
| Successful maintenance usage client | `ddadf7d9a09845f8` |
| Successful Billing usage server | `718b4f69f9975bb6` |
| Linked actual scheduled trace | `82999ef829c749359d95bbcd5bfb82ce` |
| Exact parentless scheduled root | `361d2df4052e4289` |

This proves real asynchronous causal linkage, not inferred wall-clock proximity.
The same run's later mail-sending status assertion incorrectly required CNY;
therefore the overall run was not green. Ordinary mail acceptance subsequently passed with the helper corrected in
`37646418030`, without the real-meter flag or another charged test.
Existing liability and original trace evidence are preserved, not reset or
synthesized to make a rerun look clean.


The final ordinary USD authorization witness `11495350924` from successful
`37646418030` contains 14 spans on trace `de83c4b044739aa3e6bd57a0d5f3a48e`, Mail
server `b60ff4a8669c4399`, Billing client `09bd813f1bc5481a` and Billing server
`0429ae184716e127`. Both CLI and human-authorization ancestry are validated. This
is separate from the charged-origin/scheduled proof above, not its replacement.
Final fixed readback `37646496526` found all eight actual retained usage servers
successful (two USD and six historical CNY), unchanged separate totals and no
undelivered outbox liability. See `usd-cutover.md` for the complete accepted run
and candidate/artifact coordinates.
