# Mail maintenance statement admission implementation

Date: 2026-10-01. Source-only candidate, based on accepted-projection candidate
`25acdf1`; **not hosted-validated, deployed, Paid-verified or release-approved**.

## First atomic slice: accounting only

The private `database::{Database,Statement}` adapter is the only MAIL_DB binding
owner in the Mail Worker. Foreground construction has no maintenance admission
state and forwards the existing prepare/bind/first/all/run/batch behavior. It does
not change API data, limits, error bodies, journal authority or provider sends.
Scheduled construction supplies one invocation-owned shared budget and a fixed
phase identity. Each of the established eight phases receives its ADR grant:
170/380/90/2/65/65/5/5. Their sum is 782; the remaining 18 control tokens are not
borrowable. Each `first/all/run` debits immediately before the binding operation;
`batch(N)` debits N atomically before submitting. Failure, rollback and no-op do
not refund. Prepare/bind/result inspection are not submissions. There is no raw
handle, Deref, exec, dump, session or statement-inner escape hatch.

Every Cron nested database call uses the phase adapter: route discovery/claims,
fresh desired-state read before provider DELETE, accepted projection/release and
terminal-resolution batches, embedding lease/retry/cooldown, storage ledger,
deleted/orphan GC, search-job cleanup and abuse retention. HTTP address deletion
passes its foreground adapter into the same provider verification helper.
The established phase order remains unchanged in this accounting commit. Before
accepted R2/parse work, a serial item checks that its maximum 74-statement
projection fits the remaining grant (current projector before due-rotation).
Denial retains accepted state/ZIP/journals and services subsequent phases.

## Deferral schema and rollout skew

`MaintenanceBudgetDeferred` / `ResourceDeferred` is one new closed diagnostic
pair, allowed only for standalone maintenance. It adds no fields, SQL, address,
owner, provider body or resource key. A caught denial emits at most one such event
for that phase, not a provider-failure event. Existing diagnostic pairs retain
their validation. The Rust trace schema and active Python safe sink-canary mirror
must be deployed/validated together.

An **old** Queue sink deserializes unknown enum variants as invalid; its handler
acknowledges and drops invalid records. Therefore an older sink would silently
lose this new deferral evidence, not automatically accept it. The CLI does not
consume server maintenance records, and its operation telemetry contract is
unchanged. No exhaustive Rust enum match requires a broad API revision. Rollout
must deploy/verify the updated private sink **before** enabling new producers;
an undeployed Queue/sink is not evidence of compatibility. No public wire-schema
version bump is implied by this private additive vocabulary.

## Evidence and remaining release blockers

Native tests exercise grant denial without mutation, per-statement batch counts,
phase independence, invocation/phase batch scope and exact deferral validation.
A provider-free built-workerd fixture seeds twenty accepted maximum-valid 4MB
text archives and verifies five complete projections / fifteen retained accepted
rows, 330 chunk writes, and later privacy-retention cleanup. SQL trigger counts
are **lower-bound** submission evidence; they do not emulate remote D1 quotas or
measure actual CPU/RSS. Tests run on GitHub-hosted runners only. Local evidence is
limited to rustfmt, Python AST parsing, Node syntax and `git diff --check`.

The first slice does **not** establish fair due selection, phase rotation,
finite per-phase/invocation admission, 10-second Cron provider timeouts, capped
incremental R2 reads, single final Queue flush, or maximum-valid archive CPU/RSS
completion. These remain separate source/evidence work. Workers Paid and effective
short-interval Cron CPU admission must be independently verified before deploy;
`usage_model=standard` and an omitted `cpu_ms` do not establish either. Published
D1 remains 1,000 Paid / 50 Free statements per invocation; <=800 is not Free-safe.

References: [ADR](mail-cron-budget-architecture-decision-2026-10-01.md),
[whole-Cron review](mail-cron-budget-review-2026-10-01.md),
[D1 limits](https://developers.cloudflare.com/d1/platform/limits/),
[D1 batch](https://developers.cloudflare.com/d1/worker-api/d1-database/),
[workers-rs locked D1 v0.8.7](https://github.com/cloudflare/workers-rs/blob/v0.8.7/worker/src/d1/mod.rs),
[Workers production practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/).

## Second atomic slice: accepted due fairness

Migration `0011_accepted_projection_due.sql` adds one journal-owned finite retry
slot, with existing rows due immediately. Cron selects only exact accepted,
provider-positive rows with due slot and projection lease expired, ordered by due
time / original created time / stable message ID, LIMIT 5. Before R2 or parsing,
one conditional UPDATE advances the exact observed due slot to scan time +5min.
It rechecks owner/idempotency/archive/provider/state and expired lease; returned
row presence, not trigger-expanded D1 change counts, proves admission. The due
claim **does not replace** the opaque projection lease shared by HTTP and Cron.
HTTP post-acceptance projector behavior remains unchanged. A concurrent HTTP
projector may win that lease; Cron cannot overwrite a sent/deleted projection.

Missing ZIPs, hash mismatch, malformed archives and foreign reservation/projection
identities still consume a retry turn and move behind untouched work. Catching a
per-item projection error continues other selected rows. Budget denial stops only
the outbound phase, without unmetered release/recovery statements or provider
resend. Five still-active foreground leases do not use the five-row selection.

The extra pre-R2 due UPDATE is **in addition to** PR22's existing projection lease
claim. Correct source arithmetic is healthy `734+5=739` combined / outbound367;
conservative late path `744+5=749` combined / outbound377. The item's whole-allowance
check becomes 75, i.e. `2+5*(66+9)=377`, under the 380 fixed grant. Three remaining
tokens are not a license to add uncounted compensation. All submissions still go
through the adapter and fail closed, regardless of the arithmetic model.

Added provider-free built-workerd contracts model three poison batches followed
by healthy work, skip five live foreground leases, and continue a good item after
a preceding projection fault. Existing fault-recovery tests explicitly reset
the durable due slot to model its expiry rather than assume immediate retry or
sleep on wall time. Eventual recovery assumes recurring scheduled service and
eventually successful admitted D1/R2 operations; a permanent database failure is
not repaired by retry ordering. This slice has no new local/runtime test claim.

## Third atomic slice: incremental native R2 archive cap

`archive_read::read` preserves the 5-MiB compressed service ZIP limit and existing
archive hash/parse validation. It uses the object returned by the original GET,
not an extra HEAD/read/retry. Oversized object metadata cancels the returned native
body stream without requesting a chunk. Admitted metadata is not trusted as the
only allocation bound: a native reader inspects each Uint8Array length **before**
copying it into Wasm, stops at the first single/cumulative over-limit chunk,
awaits read-stream cancellation and releases the reader lock. EOF must also match
the object size. Missing/oversized/inconsistent retained content remains accepted
and retains its ZIP/reservation; read transport faults return one fixed safe code.

The helper does not call `arrayBuffer()` or workers-rs `ByteStream` (which copies
the chunk into Rust before its caller can inspect length). Application retained
byte length is <=5MiB; Vec allocator capacity, native stream buffers and concurrent
Wasm invocations still mean this is **not a 128-MB RSS guarantee**. Canceling an
object's read stream does not claim cancellation of a binding write. Read/cancel
latency has no new deadline guarantee in this slice.

A test-only WorkerEntrypoint subclass imports the production built shim unchanged
and wraps only explicit synthetic R2 object names. It forges oversized metadata,
one oversized native chunk, and cumulative chunks crossing the cap, with a
zero-high-water-mark producer. Hosted contracts require zero/one/two producer
reads respectively, exactly one cancellation, zero whole-body arrayBuffer calls,
retained accepted state/ZIP, and progress of a following healthy accepted item.
The fresh local-only D1 fixture remains globally held and rejects all unexpected
egress; this is no production hook, flag, service or route. No local runtime test
or hosted result is claimed here.

Additional primary references:
[R2 Worker API](https://developers.cloudflare.com/r2/api/workers/workers-api-reference/),
[workers-rs locked R2 object body](https://github.com/cloudflare/workers-rs/blob/v0.8.7/worker/src/r2/mod.rs).

The Cargo manifest's `0.8.3` requirement is a semver range, not the resolved SDK
version: Cargo.lock resolves worker 0.8.7. Both adapter method signatures and the
native R2 read interface were rechecked against that exact locked source; the
accounting wrapper intentionally exposes only the executor methods used here,
not SDK IntoFuture/raw/session escape hatches.

The independent R2 source review's nonblocking acquisition-error note is resolved:
workers-rs response-body acquisition is also mapped to the fixed
`accepted_archive_read_failed` code, not propagated as arbitrary SDK text.

## Fourth atomic slice: independent actual D1 submission observation

A separately scoped test-only subclass wraps native local D1, preserving real
workerd/Miniflare SQL execution. It counts actual calls to first/all/run and each
member of native batch, not application permits or SQL-trigger internal work.
Prepare/bind spend zero; proxied prepared statements are unwrapped before native
batch so transactional behavior is unchanged. Unsupported binding methods fail
closed. Only fixed numeric counters are exposed on a synthetic test-only endpoint;
no SQL, bound values, owner identities or production API hook is introduced.
Fixture setup/readback uses Miniflare's unwrapped native binding and must leave
the observer counters exactly zero before scheduled execution.

For the twenty maximum-valid text / embedding-cooldown workload, the source
**hypothesis**, to be checked on hosted CI, is 379 submitted SQL statements:
address2 +outbound367 +embedding1 +storage1 +deleted1 +orphan1 +search3 +abuse3.
There are five native batches containing fifteen statements, and 364 individual
executors. The exact count would detect treating batch(N) as one, skipped/bypassed
binding calls, or accidental retries. It remains a synthetic path count, not a
proof of every error branch, actual plan enforcement, CPU usage or peak RSS.
