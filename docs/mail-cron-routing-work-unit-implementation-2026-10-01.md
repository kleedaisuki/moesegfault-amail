# Cron complete routing inventory and useful first repair

Date: 2026-10-01. Initial source base: merged PR #25 main `4370d2d`.
Status: exact source/fixture hosted acceptance below passed; not deployed.
This is the next independently reviewable slice, not embedding/R2/Queue work.

## Reused model and integration

Reuse PR #25's `MaintenanceTurn` and pre-setup first entitlement. The address
caller now preserves that entitlement until **after complete inventory/discovery**
and spends it on its first actual address repair. It does not spend the only
permit on inventory, or recheck the expired 15-second slice before the first row.
Later rows require fresh admission. The external policy borrows the same clamped
clock independently of the mutable phase handle; see
[transport policy](mail-cron-routing-deadline-policy-2026-10-01.md).

The complete inventory deadline is one original 30-second child cutoff, clipped
by phase-entry+60 seconds and invocation 115 seconds. Each complete native
connection/header/body exchange has at most ten seconds of positive remaining
allowance. No rolling page deadline is introduced. Only a terminal, consistent,
<=10-page/500-unique-rule inventory can support discovery, adoption, absence or
destruction. Healthy ten-page inventories at 3.2 seconds/page remain infeasible
under this policy; do not weaken completeness to hide that latency envelope.

## Counted exact-slot deferral

Existing claims still select/advance at most thirty rows before external I/O;
no per-row claim SELECT or durable scheduler is added. Time-denied rows whose
repair has not been attempted get the existing exact-slot priority UPDATE from
scan+300000 to scan-1, under the exact observed address/state/slot and intent
predicate. This write is charged through the unchanged maintenance adapter.
If compensation cannot be paid/submitted, finite original slots recover by expiry.
No uncounted compensation, timer in the database adapter, or binding cancellation.

Before each row, reserve its worst-case complete repair **plus one release token
for every still-unattempted row**. One validated initial inventory spends at least
one of twenty external submissions, leaving <=19. At most nine complete current
GET/DELETE pairs remain, each with one fresh desired-state SELECT. That plus one
terminal UPDATE is <=10 SQL; provisioning adoption uses <=3 conditional UPDATEs.
`ADDRESS_REPAIR_SQL_MAX=10` is conservative per row, not ten extra submissions.
The fixed address grant remains 170 and the invocation ceiling remains 800.

After pre-submission denial inside a repair, compare actual shared native
submission counts. No request submitted for this row means it can receive exact
priority deferral. Any already submitted request means the current row retains
its finite attempted slot; only untouched following rows are priority-deferred.
The complete permit never blocks successful fenced state persistence on elapsed
time alone. Real submitted timeout stays a dependency failure, not success or
proof that a provider mutation did not occur.

An initial inventory pre-denial or timer timeout priority-defers all already
claimed but unrepaired rows. Ordinary HTTP, malformed-body and scope/provider
failure retain the established finite retry-slot policy. Partial inventory never
licenses state settlement. Fresh absence inventory uses the same complete-policy
wrapper and preserves distinct pre-denial/timeout classification.

## Native lifecycle and compatibility

One failed complete exchange invokes exactly one native controller abort site.
The losing read future is dropped before native reader cleanup. Rejected/unused
bodies cancel their reader without first erroring the stream through abort; normal
EOF just releases its lock. Native cancel is initiated synchronously and its
Promise settlement is observed by a capture-free one-shot callback, not awaited
past expiry, not a detached Rust read/cleanup task. No private input, reader or
controller is retained by that callback. Cancellation itself is not assumed
instantaneous, and an unresolved native cancellation Promise is not a hard
end-to-end completion guarantee.

Foreground routing keeps `RoutingBudget::new()` without these new timers, with
the established status/error/404/204 mappings. Foreground embedding, accepted
projectors/fences/archives, R2 behavior, public APIs/CLI and migrations are not
changed. Redirect refusal, exact current-rule ownership plus fresh D1 desired
state before DELETE, body cap, and external submission accounting remain.
After an ambiguous DELETE, keep the journal and settle using later complete
inventory; never blindly retry inside the same turn or call abort rollback.

## Evidence gates

Local verification is static only. The focused hosted native suite has seven
discriminators; see [fixture notes](mail-cron-routing-deadline-fixture-notes-2026-10-01.md).
It must establish complete 20-second inventory **and first real promotion**,
counted priority deferral plus fast next-turn progress, native whole-exchange
abort/reader cleanup, a real 30-second nonrolling inventory cutoff, and ambiguous
DELETE recovery without a second DELETE. Existing 96 default workerd cases,
PR #25's five slow-item/rotation cases, schema/contracts and all platform source
checks remain required. A malformed Content-Length case is not claimed by the
Node bridge fixture; actual native byte crossing and stop/cancel are the oracle.

No deployment, provider mutation, Cron activation, unhold, effective Paid/CPU
proof, production CPU/RSS measurement or hard 120-second bound is authorized.
Cron embedding/R2 reader deadlines and a final byte-guarded deep-diagnostic Queue
collector remain separate small source slices. Old-writer drain, privacy and
release gates remain hard prerequisites after all source checks pass.

Production and research context: [controller reconciliation](https://kubernetes.io/docs/concepts/architecture/controller/),
[Anvil, OSDI 2024](https://www.usenix.org/conference/osdi24/presentation/sun-xudong),
[native Streams cancellation](https://streams.spec.whatwg.org/#default-reader-cancel),
[Workers production practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/).
The useful-first-turn test distinguishes recurring successful inventory retrieval
from actual journal progress; neither safety nor a successful GET alone proves
reconciliation liveness. No formal verification claim is made.

## First hosted compile failure and exhaustive caller correction

Exact candidate `fe024e3f75dd9f2bf326bade0d28d507a25fb2fa`,
[CI 36814716325](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36814716325),
failed before built-workerd execution at Rust unit compilation: `add_address`'s
foreground diagnostic match omitted the two new closed RuleListFailure variants.
The source review did not catch that remaining call site; no runtime pass or
deadline/cancellation conclusion follows from this failed compile.

The correction introduces a small exhaustive typed diagnostic classifier with
pure tests. Foreground `RoutingBudget::new()` cannot currently produce the
Cron-only Deferred variant, but explicitly mapping it to existing `State` means
admission denial rather than invented provider evidence, without expanding the
established staging header grammar or breaking strict CLI/sanitizer parsers.
Timeout maps to existing `Request`, retaining transient transport classification
with no observed provider HTTP status. Existing Request/Http/Provider/Decode
mappings are unchanged. Cron's separate `routing_list_error` still produces the
standalone maintenance deadline/resource-deferred pair for pre-denial and an
ordinary dependency failure for submitted timeout. No wildcard/todo conceals
future enum additions. Narrow independent review precedes the exact-head rerun.

## Corrected exact hosted acceptance

PR #27 remote head `2325828b1402e40e61580091a2765a5c87c7f702`:
[full CI 36815435803](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36815435803),
attempt 1, **success**, 2026-10-01 04:30:27 to 04:37:42 UTC;
[workflow syntax 36815435371](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36815435371),
**success**. All seven source checks passed: three native CLI platforms,
infrastructure, site, Rust Worker/Wasm, and workflow syntax.

Actions checked out PR merge revision
`1320fb746a21e494578107ec8d7e8b4294cf9bc2`, distinct from both branch heads.
Worker units **65/65**, existing default built-workerd **96/96**, prior focused
liveness **5/5**, and new native routing **7/7** passed, with zero failures.

| Passing discriminator | TAP case duration, including fixture setup/teardown |
| --- | ---: |
| Complete 20-second inventory, first real promotion, deferred next row and fast next turn | 20,973.933290 ms |
| Hanging headers, one complete exchange deadline | 10,768.013378 ms |
| Seven-second headers then pending body, same complete deadline | 10,767.675759 ms |
| Ten 3.2-second pages, original inventory deadline and no partial settlement | 30,912.484897 ms |
| Remotely accepted DELETE then body stall, finite journal and later absence convergence | 10,848.422172 ms |
| Native byte cap, stop/cancel/release | 740.242563 ms |
| Foreign redirect refusal | 652.990905 ms |

These are whole synthetic test case durations, not separately measured handler
duration, actual provider latency, CPU/RSS, or a production SLO. Assertions
established the exact addressed SQL counts described in fixture notes, priority
release slots, first useful repair, no second DELETE, native signal abort and
reader cancellation/release. They did not rely on Node source cancel callbacks
or claim that actual remote computation stopped.

The first E0004 failed candidate remains separate historical evidence. Committed
source and fixture review records preserve that compiler omission/correction,
the initial header/body timing discriminator gap, its seven-second correction,
and exact source hashes. Root final review and merge remain separate decisions.
Raw successful Worker logs are retained at worktree
`.temp/ci-36815435803-worker.log`, separate from the failed predecessor.

This evidence update is a local documentation-only follow-up, initially not
pushed into the exact validated PR head. No project runtime tests/builds were
run locally, no provider/deployment/Cron/unhold mutation occurred. All deferred
embedding/R2/Queue, privacy, plan/CPU/RSS and old-writer drain gates above remain.
