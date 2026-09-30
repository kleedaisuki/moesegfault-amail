# Queue-only trace sink implementation (2026-09-30)

Status: source implementation, **not deployed privacy acceptance**. This follows
[the sink ADR](mail-trace-queue-sink-decision.md). The independent live classifier
run `36723490687` found the synthetic path marker in request enrichment, not the
allowlisted application source. Retaining custom logs in a public fetch invocation
therefore does not establish the required boundary.

## Boundary and wire contract

- `crates/mail-worker` has all retained observability disabled in both realms.
  It never invokes console logging. Existing routes, auth, status/error payloads,
  request correlation response headers and search behavior remain unchanged.
- `crates/trace-schema` contains one owned, flat, `deny_unknown_fields` Event.
  The original API/client event fields remain version 1 with added producer UUIDv4
  `event_id`. Enums, canonical IDs, power-of-two buckets and service/phase field
  combinations are checked both before enqueue and before sink serialization.
- Each fetch invocation owns a `RefCell<Vec<Event>>`: at most 128 safe records,
  with the last slot reserved for its final request exit. Each encoded event is
  at most 1,024 bytes. Queue batches have at most 100 entries; 100 uploaded CLI
  rows plus one API exit are two ordered batches, not an oversized provider call.
- The fetch handler detaches safe events and uses `Context::wait_until` for Queue
  handoff. Neither binding nor enqueue failure changes a successful mail operation
  or prints a fallback log. The failure does **not** imply guaranteed diagnostics:
  provider Queue metrics do not cover every failed producer handoff.
- `workers/trace-sink` has only `#[event(queue)]`. It has no fetch, scheduled,
  email, routes, service bindings, Workers.dev or preview URLs. It reserializes
  only the validated Event into retained Workers Logs. CLI/server/phase IDs are
  not replaced by queue-consumer IDs.
- Raw per-message decoding failures and invalid events are acknowledged/dropped
  without logging the payload, exception or a fallback message, and without
  retrying poison into the DLQ. A serialization failure for an already valid
  event retries that individual message. Bounded retries/DLQ are configured.
- At-least-once delivery can duplicate a retained event. `event_id` remains stable
  for that redelivery; readers deduplicate by this ID. A console call followed by
  Queue acknowledgement is not proof that Cloudflare retained that record.

## Operational diagnostics

All fourteen prior fixed API warning labels now have a closed `DiagnosticCode`
in the shared schema. The two request-path storage-ledger warnings are buffered
as maintenance child events with the original trace ID/request ID and server-span
parent. Cron/nested reconciliation diagnostics have standalone opaque maintenance
IDs and are best-effort awaited Queue handoffs; they do not claim a single common
Cron-run trace. There is no raw error, account, address, R2 key or SQL diagnostic.

The queue names are `amail-trace-events` / `amail-trace-events-staging`, DLQs
`amail-trace-dlq` / `amail-trace-dlq-staging`, private Workers `amail-trace-sink` /
`amail-trace-sink-staging`. Main and DLQ retention must independently read back as
86,400 seconds. Consumers: batch 10, timeout 1 second, retries 3, retry delay
30 seconds, maximum concurrency 2. Queues are isolated by realm.

## Verification contract

`crates/mail-worker/check_observability.py --realm staging|production` checks
public API retention entirely off; `--mode sink` checks safe custom Logs on/full,
invocation/native traces off, both settings APIs and no unreviewed exports.
Sink mode now additionally requires `AMAIL_EXPECTED_TRACE_SINK_VERSION` and the
reviewed Queue/DLQ IDs. It pins the same sole 100%-serving deployment before and
after its checks, reads the exact version's compiled handler set (`queue` only,
no named entrypoints) and empty binding set, and requires Workers.dev/preview and
Cron to be absent. It inspects complete bounded account-domain/account-zone
inventories, every returned zone's unpaginated Worker routes, and account Queue
subscriptions to reject any other sink subscription. Permission-denied, missing,
unknown, duplicate, inconsistent, oversized or incomplete readback fails closed;
local Wrangler intent is not substituted for deployed evidence. The Domain API is the documented unfiltered SinglePage endpoint, with no invented
page/per_page parameters: optional generic metadata is accepted only if it does
not contradict the complete result array. Bounds are 20
zone inventory pages, 1,000 domain/zone rows, at most 20 zones and 100 Queues for this
project's acceptance check. The account inventory is necessarily limited to the
credentials' actual visibility; use an account-wide reviewed deploy capability,
not a token that silently excludes zones. The compiled no-fetch handler check is
an independent safeguard even if another operator later alters route publication.
These checks do not establish absence of retained markers; the canary covers that.

Hosted tests must run the pure schema denial/roundtrip cases and existing Worker
trace cases, including full 100-row telemetry and reserved-exit/batch bounds, then
build both Wasm bundles. No local builds or tests were run for this implementation;
only formatting/source checks. Before source rollout, first deploy/pin the
containment-only commit with public retention off. After Queue/source rollout,
read back both serving versions, Queue retention/consumer ownership and settings,
then run a fresh bounded retained-data canary across **both** API and sink services.
Only that complete record inspection can attest absence of path/query/address/body
markers while retaining the original causal application IDs. Production public
sending and release remain held pending the independent acceptance gates.

## Platform evidence

The pinned workers-rs 0.8.7 source exposes Queue `send_batch`, raw message
acknowledgement and Context `wait_until`; no speculative binding is needed:
[Queue source](https://github.com/cloudflare/workers-rs/blob/v0.8.7/worker/src/queue.rs),
[Context source](https://github.com/cloudflare/workers-rs/blob/v0.8.7/worker/src/context.rs).
Cloudflare documents [per-message acknowledgements and retry bounds](https://developers.cloudflare.com/queues/configuration/batching-retries/)
and [DLQ delivery](https://developers.cloudflare.com/queues/configuration/dead-letter-queues/).
Queue-only invocation context is a containment hypothesis verified by the hosted
retained-data test, not a provider guarantee that safe source alone proves privacy.


Readback endpoint contracts follow Cloudflare's [version resource API](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/get/)
(handler/binding resources), [account Worker domain inventory](https://developers.cloudflare.com/api/resources/workers/subresources/domains/methods/list/)
and [zone Worker route inventory](https://developers.cloudflare.com/api/resources/workers/subresources/routes/methods/list/).
The sink uses the existing reviewed `pin_staging_mail.serving_deployment` parser
and `ensure_trace_queues` ownership/detail validators without calling provisioning.


Domain endpoint shape correction: Cloudflare's [official generated SDK](https://github.com/cloudflare/cloudflare-python/blob/main/src/cloudflare/resources/workers/domains.py)
uses `SyncSinglePage` with no page/per_page request arguments. The generic REST
example's pagination metadata is not a license to invent pagination for this
endpoint. Denial tests require optional metadata to agree with the unfiltered
array, and reject explicit missing rows, later pages, cursors or duplicate IDs.

The Queue subscription proof reuses the strengthened complete inventory helper:
integer page/per_page/count/total_count/total_pages, requested page size, exact
per-page cardinality, coherent/stable totals, unique Queue IDs/names and complete
accumulated count. An integration denial test calls that actual helper through
`queue_trigger_exact`; a response omitting a third Queue while claiming more
results fails before any consumer-detail read can falsely attest exclusivity.
