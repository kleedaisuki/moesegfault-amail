# Cron routing exchange deadlines

Date: 2026-10-01. Scope: routing transport in `platform.rs` and the borrowed
`ExternalDeadline` policy in `maintenance.rs`. Status: source implementation,
formatting and static review only; no local project build/runtime test,
provider action, deployment, commit, or push performed by this assignment.

## Reused knowledge and boundary

Read the admission policy notes and the root design at
`.temp/cron-liveness-deadline-design/docs/mail-cron-liveness-deadline-design-2026-10-01.md`
before editing. Unit admission is still separate from statement accounting and
durable ownership. No accepted projection, embedding transport, R2 transport,
Queue diagnostic, API schema, or foreground timeout policy is changed here.
Caller integration and hosted fixture execution are separate owners.

## Clock, lifetime, and formula

`ExternalDeadline<'a>` contains only `&'a MaintenanceTurn` and immutable elapsed
cutoff milliseconds. `PhaseTurn<'a>::routing_deadline(&self)` returns the
invocation lifetime, not the temporary borrow of the phase; callers can still
call mutable `admit()` while the routing budget exists. There is no Rc, global
state, environment override, or independent clock. All observations use the same
nondecreasing invocation clock; invalid deltas fail closed.

For phase-entry elapsed E, complete-inventory start I, and current clamped elapsed T:

| Boundary | Absolute cutoff / exchange duration |
| --- | --- |
| Compound routing phase | C = min(E + 60000 ms, 115000 ms) |
| One complete inventory | P = min(C, I + 30000 ms) |
| Native exchange | min(10000 ms, applicable cutoff - T), requiring positive time |

Inventory creates its child deadline once, outside pagination. Pages never
restart thirty seconds. GET-current and DELETE use the compound cutoff, with
fresh admission before each submission. D1 between those operations is not raced
or canceled. The ten-page / fifty-rules-per-page / five-hundred-unique-rules /
256 KiB actual-body constraints and terminal completeness proofs remain intact.
A partial inventory cannot establish absence or authorize a repair.

`RoutingBudget::new()` keeps foreground routing without the new time policy.
`RoutingBudget::cron(turn.routing_deadline())` explicitly installs Cron policy.
The twenty-submission allowance remains shared by setup, fresh inventories,
current-rule GET, and DELETE. Request construction and deadline admission precede
`take()`. A denied prefetch spends zero; a submitted native failure or timeout
spends one. `submitted()` lets the caller compare before/after counts for a row.

## Native exchange ownership and cleanup

One Rust timer races the complete connection/header/bounded-body future. Its
exact AbortSignal is passed to native fetch. Manual redirects remain mandatory.
The body stream's native reader is stored outside the raced future before any
read is polled. A timed-out losing exchange is dropped before cleanup touches
that reader. Timeout aborts the exact controller, synchronously initiates native
reader cancellation, then releases its lock. There is one controller abort site
for a failed complete exchange, not a second abort in the timer branch.
Oversize/read failure cancels/releases its acquired reader without first aborting
and erroring the stream; non-200 unread bodies use the same reader cleanup.
EOF releases the lock without cancellation. Success
explicitly drops the losing timer. No detached task or Promise.race performs
cleanup; only native Promise settlement bookkeeping absorbs cancel rejection.
That bookkeeping uses a one-shot callback on both fulfillment and rejection,
not eval or a Rust background task. Cancellation itself is not awaited, since
an untrusted underlying cancel promise must not extend the expired deadline.
The read future's JS rejection is already handled by JsFuture.

Chunk length is inspected as a native Uint8Array before `to_vec()`. Content-Length
is not trusted. Non-200 bodies are canceled unread. A structured status plus body
Result preserves foreground non-200/known-ID-404/DELETE-204 mappings even if body
acquisition or consumption fails. Foreground POST retains its existing rule_body
implementation, and foreground embedding is untouched.

## Failure and destructive semantics

Pre-submission time rejection is exactly `maintenance::deferred()`.
Inventory maps it to `RuleListFailure::Deferred`; native submitted timeout maps
to `RuleListFailure::Timeout`. Both have no provider status, unlike an observed
HTTP failure. The caller must not turn an unattempted time-deferred row into an
ordinary attempted failure or claim that timeout proves no remote effect.

Deletion retains current owned-rule GET, fresh desired-state D1 read, and DELETE
in that order. A timeout after submitted DELETE remains unknown: the provider
may have applied deletion. It is never success, never proof of no effect, and
never an immediate blind retry. A later scheduled fresh observation resolves
ambiguity through the established ownership and desired-state protocol.

## Evidence and next verification

Authored deterministic policy tests cover invocation-only borrowing with later
mutable phase admission, compound/global cutoff equality, backward clamping,
one absolute inventory child cutoff, clipping to the parent, and invalid-clock
failure. Existing budget tests now check submission count zero/twenty; failure
classification tests check absent provider statuses for deferred/timeout.
These tests are authored, not locally executed. Direct rustfmt and git diff
--check passed. Hosted integration must exercise hanging connection, hanging
body, oversized native chunk, cancellation/release, complete pagination crossing
the soft unit slice, deadline denial before the next native call, and ambiguous
DELETE followed by a fresh observation.

Production references retrieved on 2026-10-01:

- [Cloudflare Fetch](https://developers.cloudflare.com/workers/runtime-apis/fetch/).
- [Cloudflare Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/).
- [WHATWG Streams Standard](https://streams.spec.whatwg.org/#default-reader-cancel),
  including reader cancellation and release semantics.

This bounded source slice follows established platform cancellation/streaming
mechanisms rather than introducing an experimental transport abstraction. It
makes no hard wall-clock completion guarantee for D1 or CPU-bound work.
