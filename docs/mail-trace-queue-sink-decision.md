# Decision: isolate mail trace retention behind a Queue (2026-09-30)

Status: **implementation contract and staging containment experiment; not a
deployed privacy or delivery attestation**. This refines
[the sink options](mail-trace-sink-remediation-options.md) and supersedes the
public-API custom-Logs sink in [the earlier decision](mail-trace-privacy-decision.md).
It changes neither mail/auth APIs nor the CLI SQLite/wire contract. No local
build/test, private-data query, deployment, or production change was performed
for this design.

## 1. Evidence and decision

The reviewed historical discriminator in hosted run
[36723490687](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36723490687)
at classifier source `d8b9631` returned:

```text
CLASSIFIED carrier=metadata_context+workers_event_request carriers=2_plus leaves=2_plus metadata_type=unrecognized wrapper_type=wrapper_absent trigger=fetch source_shape=allowlisted_application component=path_only records=1
```

This identifies two matched structural carrier categories in one record, not
two emitters. Its application payload passes the reviewed allowlist while path
markers survive elsewhere. `d8b9631` is the classifier revision, **not** an
attestation of the historical serving Worker. The event producer/type remains
unresolved. Nevertheless, adding another regex to an already safe application
payload cannot establish exclusion of request context before retention.

**Chosen boundary:** the public Mail API remains the business Worker, but has
all retained observability disabled. It serializes only bounded typed trace
events into a private Cloudflare Queue binding. A distinct queue-only Rust
Worker reconstructs and logs validated events to Cloudflare Workers Logs. It
has no HTTP, Email, Cron, Tail, RPC or business storage binding. Never forward
the incoming Request or its headers/context. Never retain an unsafe source log
to compare with the sink.

Cloudflare documents native resource bindings and async background processing
as production practices [1]. Its Logs documentation gives Queue invocations a
fixed queue-name message rather than a Fetch URL [2]. This supports the
containment hypothesis; **it is not a guarantee** that every retained Queue
event excludes original producer context or message bodies. Complete retained
records still need a live gate.

```text
CLI SQLite: trace T, client span C, response request R
        |
        | authenticated W3C traceparent only
        v
Mail API: server span S, parent C, request R       retained Logs/Traces OFF
        | phase D: parent S; phase P: parent S
        | owned, typed, bounded event envelopes only
        v
amail-trace-events[-staging]                      private Queue binding
        | bounded retries; duplicate/redelivery permitted
        v
amail-trace-sink[-staging]                        queue-only Rust handler
        | decode -> validate -> reconstruct -> safe console -> ack
        v
Workers Logs: original T/C/S/R, safe phase data   full-rate application Logs

exhausted valid delivery -> amail-trace-dlq[-staging]
                          no automatic replay/consumer; expires in 24 hours
```

## 2. State ownership and invariant-bearing data

| State | Owner/lifetime | Invariant |
| --- | --- | --- |
| Server trace T/S and request R | One API invocation | Fresh random IDs; trusted parent accepted only after existing authentication. |
| Phase span D/P | Original operation | Parent remains S; Queue delivery does not replace the business span or fabricate provider parentage. |
| Owned envelope/event ID E | Producer, then Queue/DLQ | Random server-generated E is stable on redelivery; no URL, envelope, principal, message ID or content. |
| Bounded event buffer | One invocation, not module/global state | At most 128 envelopes, each at most 1,024 serialized bytes; reserve an exit slot. |
| Queue backlog | Cloudflare, separate by realm | 24-hour message retention; finite consumer retries and concurrency; no recursive trace of transport. |
| Safe retained event | Sink / Cloudflare Logs retention | Schema revalidated; log rebuilt from typed fields; no raw queue/body/error fallback. |

Keep existing `trace.rs` operation/phase/outcome/error enums and W3C parentage.
Use an owned shared schema module for producer and consumer. A minimal envelope
is `TraceEnvelope { envelope_version: 1, event_id: CanonicalUuid,
event: TraceEvent }`, with a closed tagged event enum for API, legacy-compatible
CLI operation, and fixed system warning/maintenance events. Avoid flattening an
arbitrary map into this schema. Field addition is a privacy review, not a
general-purpose telemetry extension.

Both serialization boundaries validate IDs, enum membership, byte/time/status
ranges and field combinations; `serde(deny_unknown_fields)` rejects additions
instead of silently copying them. ID wrappers accept only canonical lower-case
nonzero 32/16-character W3C IDs and canonical server UUID format. Semantic
validation still matters after Deserialize. Client events retain optional span
and request IDs so historical uploads/SQLite rows remain valid. Legacy accepted
wire text that cannot enter the safe ID types is dropped from retained events,
not newly rejected at the public endpoint.

Buckets use the existing powers-of-two rule. Bound durations to one hour and
provider numeric fields to reviewed ranges; do not reinterpret arbitrary
integers as future codes. For HTTP client status zero, preserve its documented
unknown-status representation instead of demanding an ordinary 1..5 class.
No `tracestate`, URL/path/query, error/debug text, owner ID, address, subject,
body, archive filename, asset name, R2 key, SQL binding, vector, message ID,
provider exception, bearer token, dynamic attribute key or Request enters the
envelope. Queue and DLQ bodies are retained data, not an exemption from privacy.

Accepted authenticated trace IDs remain user-controllable correlation handles;
strict syntax cannot prove randomness or prohibit covert encoding. Preserve
the existing trust decision rather than claiming adversarial zero-leakage [3].

## 3. Producer and consumer implementation boundaries

The lockfile resolves `worker` **0.8.7**; the existing lifecycle Worker already
uses its `queue` feature. Add that feature for the Mail producer. The official
Rust implementation provides `Env::queue`, `Queue::send_batch`, raw/typed
MessageBatch iteration, and MessageExt acknowledgements [4]. `Context::wait_until`
accepts an owned `'static` future producing `()` [5]. Use the actual locked SDK,
not a pre-trained or unpinned method signature.

### Producer

1. Make events owned while IDs/phase timing are available; append to the
   invocation-local bounded buffer. A full buffer drops optional events and
   retains one fixed truncation/count indication if room, preserving the final
   request-exit event. Do not inspect the body merely to measure bytes.
2. Obtain the dedicated Queue binding before passing Env into dispatch (or
   preserve a safe binding handle). Finalize exit on success and controlled
   error paths without changing `x-amail-request-id`, status or mail behavior.
3. Hand off only the owned buffer and Queue handle in one tracked `wait_until`
   future. Send chunks of at most 100 envelopes and at most 102,400 serialized
   payload bytes. Existing `/v1/telemetry` allows 100 client records, so its
   server exit makes **101**: a single unchunked sendBatch is incorrect. Resolve
   Queue/binding/send failure privately; never console-log the request or raw
   SDK error, and never turn diagnostic failure into a mail failure.
4. No untracked spawned future and no console fallback. An ambiguous producer
   send need not be retried; diagnostics are best-effort. If retry is introduced,
   it must be bounded and reuse E for each original envelope. Do not add D1/R2
   diagnostic outboxes to business storage solely to emulate lossless tracing.
5. Convert all currently fixed API warnings into typed warning codes. Especially
   preserve Cron reconciliation, semantic quarantine/cooldown, and storage
   cleanup warnings: simply turning source Logs off would hide useful existing
   diagnostics. A scheduled run gets fresh opaque T/S/R and a fixed maintenance
   operation; it flushes through its supported lifecycle, or awaits the final
   bounded send. No scan row, owner or exception detail is included.

Uncaught runtime termination or panic before handoff can lose a final event.
Fully disabling source retention intentionally prevents raw exception capture;
do not invent a supposedly safe panic logger with arbitrary formatting. Use
provider aggregate errors/health and missing bounded-canary evidence to diagnose
this limit. Full safe event instrumentation is not lossless exception auditing.

### Consumer

Prefer a distinct small `workers/trace-sink` cdylib and shared schema module, or
an explicitly mutually exclusive queue-only build of the existing crate. **Do
not deploy the API bundle under a new name:** no-route config alone does not
prove the generated bundle lacks its fetch/cron exports. Hosted bundle checks
must establish the sink's queue handler and absence of other entry points;
the pinned worker-build can infer exported handlers [6]. Do not modify generated
JavaScript by hand or create a custom JS observability wrapper.

Decode individually via `batch.raw_iter()` and `Message<Value>::try_from(raw)`
before strict typed validation; this preserves the capability to acknowledge an
undecodable poison message. A single `batch.messages()` failure must not blindly
retry all raw bodies into the DLQ. For each message:

| Condition | Action | Retained output |
| --- | --- | --- |
| Valid schema/ranges/realm | Serialize a new typed event, console emit, ack that message. | E plus original safe business event; no raw message or Queue system ID. |
| Invalid/unknown/oversize envelope | Ack/drop that message; no retry or DLQ copy. | One fixed `trace_envelope_rejected` category/count, no body/field value/ID. |
| Controlled transient sink failure on a valid envelope | Retry that message under configured finite policy. | Fixed transport failure category only; no error text. |
| Uncaught process/runtime failure | Platform redelivery up to finite limit. | Native traces/invocation logs still off; no claim of complete safe custom event. |

The producer is the pre-retention privacy gate: consumer rejection cannot erase
an invalid body already placed on the Queue. Restrict capabilities to reviewed
producers and deployment operators. Test poison cases only with synthetic data;
never send real raw mail to demonstrate rejection. Because the sink handles
only reviewed typed messages, it should have no dependencies, storage or fetch
operations whose exception payloads could contain business data.

## 4. Concrete configuration and failure semantics

Explicitly declare both realms; do not rely on Wrangler inheritance. Production
names are `amail-trace-events`, `amail-trace-dlq`, `amail-trace-sink`; staging
adds `-staging`. API binding is `TRACE_EVENTS` in each realm.

```toml
# Public API, separately repeated under env.staging.
[[queues.producers]]
binding = "TRACE_EVENTS"
queue = "amail-trace-events"
[observability]
enabled = false
redact_query_string = true
[observability.logs]
enabled = false
invocation_logs = false
[observability.traces]
enabled = false
```

```toml
# Distinct private queue-only Worker, separately repeated under env.staging.
name = "amail-trace-sink"
main = "build/worker/shim.mjs"
compatibility_date = "2026-09-30"
workers_dev = false
preview_urls = false
[[queues.consumers]]
queue = "amail-trace-events"
max_batch_size = 10
max_batch_timeout = 1
max_retries = 3
retry_delay = 30
max_concurrency = 2
dead_letter_queue = "amail-trace-dlq"
[observability]
enabled = true
head_sampling_rate = 1.0
redact_query_string = true
[observability.logs]
enabled = true
invocation_logs = false
[observability.traces]
enabled = false
```

No routes/custom domains, services, outbound binding, database, bucket, Email,
Cron, Tail consumer, Logpush or external export destination on the sink.
Explicitly read back public URL/preview exposure independently of local intent.
Only Cloudflare's built-in Logs destination is allowed for the sink; the API
has no enabled retention/export destination or Tail consumer. Keep ingress and
lifecycle fully unobserved. Queue-level retention is not in the above producer
or consumer block: provision/read back **86,400 seconds on main and DLQ** using
the official Queue API/Wrangler setting [7]. Free-plan retention is already
fixed at 24 hours; paid plans must not inherit four-day defaults [8]. The DLQ
has no automatic consumer or return-to-main cycle. Manual replay requires a
separate reviewed bounded operator job that validates E/schema first.

Queues can redeliver/reorder [9]. E stays constant on redelivery; readers dedupe
identical E/payload pairs and fail on conflicting payloads. Do not add a database
to dedupe Logs. Clock/ingestion order does not establish parentage. Queue ack
means handler completion, **not** durable Workers Logs persistence receipt:
console has no receipt. Log sampling/account cap/retention can still hide
events despite `head_sampling_rate=1`. Missing or truncated evidence stays
UNVERIFIED, not repaired by indefinite polling/replay.

Platform Queue backlog/lag/retry/DLQ metrics support operations without raw
data [10]. They do not exhaustively count failed producer handoffs before
acceptance or prove every event persisted. Alert on increasing backlog,
oldest-message age approaching retention, sustained retries, any DLQ traffic,
missing synthetic trace heartbeat, and cost/volume. Thresholds are operational
defaults to tune from staging traffic; they must not be called lossless
accounting. Per-invocation bounds reduce memory/cost amplification but do not
bound unauthenticated request volume; preserve platform abuse/rate controls.

## 5. Migration, rollback and executable acceptance

1. **Source/hosted CI:** schema and producer tests, locked Rust native/Wasm build,
   generated bundle handler checks, Python config/readback tests and workerd
   Queue boundary tests. No local toolchain/build/test. Verify unknown keys,
   malformed/noncanonical IDs, legacy CLI uploads, invalid bytes/nesting,
   duplicate/conflicting E, 100-row upload+exit chunking, buffer saturation,
   fixed warnings and controlled enqueue failure preserving mail response.
2. **Provision staging only:** create/read back dedicated main+DLQ retention;
   deploy the sink first with no public route/preview and verify its generated
   handler/exposure/settings/consumer config. This is no permission to change
   existing lifecycle queues or provision production prematurely.
3. **Atomic producer switch:** deploy the reviewed API code+Queue binding+
   completely disabled source retention as one pinned version. Do not run the
   producer before its sink readback passes, and never dual-write old console
   traces. Verify both deployed settings endpoints and serving version. Disable
   unsafe retained source config even if the Queue cannot be made available;
   that is a diagnostic outage, not permission to restore a privacy failure.
4. **One guarded synthetic staging run:** establish authenticated CLI C -> API
   S parentage, child-phase parent S and opaque R/E in sink records; denial has
   a fresh server trace and no trusted caller parent. Inject distinctive path,
   query, body/subject/address/header markers, malformed traceparent, a controlled
   synthetic dependency failure and poison envelope. Inspect the **complete**
   cursor-complete bounded retained sink view and queued synthetic envelope
   schema without printing/exporting raw rows. Reject unknown/truncated views,
   missing required events, conflicting E or markers anywhere including
   platform metadata/enrichment. Apply the existing authorized query transport
   and fixed-summary discipline, changing the service to the sink and schema
   intentionally, not relabeling the old checker as a new gate.
5. **Source containment evidence:** independently inspect readback/no Tail or
   export destinations and a bounded corresponding public-Worker retained-event
   view, without assuming absence alone proves exclusion. Account for historical
   rows: disabling collection does not erase already retained records. Continue
   holding public sending and privacy acceptance until the new version's safe
   events are present and whole-record exclusion passes.
6. **Failure/recovery:** hosted synthetic boundary tests exercise producer send
   refusal (unchanged mail result), consumer interruption/redelivery, finite DLQ,
   poison drop, and same-E duplicates. A controlled live synthetic valid delivery
   failure may be added only with an explicit temporary staging consumer version,
   known restoration and no production mutation; don't cause a real incident
   merely to exercise DLQ. Poll delivery in a fixed deadline/window, not by
   expanding historical windows. Synthetic failures cannot prove every runtime
   exception safe.
7. **Production:** only after independent review and staging acceptance, provision
   separate resources and repeat sink-first/pinned producer switch/readback plus
   bounded production smoke. No CLI/API/SQLite migration and no message-storage
   backfill is required. Sink must support the envelope version for at least
   queued retention across a deployment; reject future versions safely.

Rollback preserves the privacy boundary: first stop/disable producer tracing or
restore the last **Queue-safe** API code/config with retention still off. Never
roll back to the previously enriched public-Logs version. Leave the sink draining
existing safe envelopes and DLQ expiring for their bounded lifetime. Restore a
compatible sink before re-enabling Queue emission. Do not purge unrelated mail
resources, replay an ambiguous delivery without E, or retry mail because traces
are absent. If queue sink enrichment still retains original URL markers, leave
the gate closed, disable sink retention, and retain only already approved local
CLI diagnostics/aggregate platform health while selecting a new scoped store.

## 6. Scope, alternatives and research connection

This is exact causal **application event tracing**, not native Cloudflare Traces
waterfall, automatic dependency traces, guaranteed distributed delivery, or
lossless security audit. External OpenRouter/provider context is not propagated
just because a Queue exists. It restores privacy-safe diagnosis at the same
mail API contracts, not a new mailbox UI or tracing product.

Compared with Analytics Engine, Queues preserve per-event identity and existing
Workers Logs queries without committing to adaptive aggregate sampling and
longer retention. A fixed-URL service binding is smaller but has a less clear
separation from caller invocation enrichment; moving every API request behind a
gateway is unnecessarily invasive. A learned log-redaction classifier cannot
be the confidentiality boundary for unobserved platform-added fields. Empirical
logging research demonstrates accidental disclosure through system/metadata
logging [11]; it motivates whole-pipeline retained-record tests, **not** a claim
about Cloudflare's producer or this design's success. Preserve meaningful fixed
dependency/status codes so safer logs do not lead operators to over-grant
permissions merely because errors became opaque [12].

**Adjacent unresolved scope:** `workers/role-monitor` still runs Email/Cron with
custom Logs on and invocation/native traces off. The Fetch finding is not proof
that role logs leak, but Email enrichment can be sensitive. Passing this API
Queue gate must not certify all role-monitor events. Apply a dedicated retained
Email-canary gate or separately migrate its typed events to the same realm-safe
schema; no raw complaint/envelope may enter this trace Queue. Ingress/lifecycle
observability remains off and their private mail processing remains unchanged.

For a role-monitor extension, use a distinct closed service/event variant with
fixed role (`abuse | postmaster`), fixed delivery/monitor phase and outcome,
bounded count/status/timing and a new random operational reference. A reference
must not be a hash of reporter/address/content or a provider/R2 identifier.
Create fresh role invocation trace IDs; do not invent a parent to an unrelated
user mail request. Acquire the same realm's private Queue capability and disable
retained role source observability in the same deployment before any marker
test. The role alert destination stays in its existing protected configuration,
never the trace schema. This is a compatible schema extension requiring source
review and its own Email whole-record acceptance; do not silently treat the
Fetch canary as its proof. Maintain the existing private role-mail storage and
lease/alert behavior unchanged while replacing only diagnostics emission.

**2026-10-01 source extension:** the reviewed role variant and a separate,
manually promoted exact-two-producer topology are now implemented in source.
Phase1 remains sole Mail API; phase2 is exactly Mail API plus role-monitor on
the same pinned Queue/DLQ and sole sink. It requires immutable phase1 provenance,
an actual prior API/sink whole-record privacy canary, and strict pre/post serving
readback; it does not deploy role automatically alongside the API. See the
[complete role transition and remaining independent Email/Cron gates](role-mail-monitoring.md#source-only-staged-shared-queue-rollout-contract-2026-10-01).
This update is not a live rollout or Email privacy acceptance.

## References (retrieved 2026-09-30)

1. [Cloudflare Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/).
2. [Cloudflare Workers Logs](https://developers.cloudflare.com/workers/observability/logs/workers-logs/).
3. [W3C Trace Context](https://www.w3.org/TR/trace-context/).
4. [Cloudflare workers-rs v0.8.7 Queue implementation](https://github.com/cloudflare/workers-rs/blob/v0.8.7/worker/src/queue.rs).
5. [Cloudflare Rust Context](https://docs.rs/worker/latest/worker/struct.Context.html).
6. [Cloudflare worker-build handler generation](https://github.com/cloudflare/workers-rs/blob/v0.8.7/worker-build/src/main.rs); deployment remains on the repository's reviewed pinned bundler, not automatically this newer source.
7. [Cloudflare Queue configuration](https://developers.cloudflare.com/queues/configuration/configure-queues/).
8. [Cloudflare Queue limits](https://developers.cloudflare.com/queues/platform/limits/).
9. [Cloudflare delivery guarantees](https://developers.cloudflare.com/queues/reference/delivery-guarantees/), [retries](https://developers.cloudflare.com/queues/configuration/batching-retries/) and [DLQ](https://developers.cloudflare.com/queues/configuration/dead-letter-queues/).
10. [Cloudflare Queue metrics](https://developers.cloudflare.com/queues/observability/metrics/).
11. [Lyons et al., USENIX Security 2023: sensitive information in Android system logging](https://www.usenix.org/conference/usenixsecurity23/presentation/lyons).
12. [Shen et al., USENIX Security 2023: improving logs to reduce permission over-granting](https://www.usenix.org/conference/usenixsecurity23/presentation/shen-bingyu-logging).
