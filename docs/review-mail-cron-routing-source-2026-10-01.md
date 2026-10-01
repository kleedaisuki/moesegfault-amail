# Independent source review: Cron routing deadlines and first repair

Date: 2026-10-01.
Worktree: `.temp/cron-liveness-implementation`, branch `codex/cron-routing-deadlines`.
Review base: `13b2c284bae38e196a0d63c721675d007a3f790a`.
Production source commit: `f4a1dcd7a9e83ce1de1dc57a7a08247c6af30a1b`.
Inspected HEAD: `4fe000b0f6e42d43d304cba4060f4c8b3714ca08`.
Production diff from the source commit to inspected HEAD is empty. This review
covers the three production source files changed against base and their callers;
fixture correctness and hosted runtime results are separately owned.

## Verdict

**No substantive source defect found. GO for nondeploying hosted verification,
not deployment or release.** No P0/P1/P2 correction request. Confidence is moderate:
static contract and dependency-source review is not native-runtime evidence.

Read the routing deadline policy and routing work-unit implementation notes
first, reused the previous independent complete-work admission review, inspected
full affected functions and current foreground call sites, and checked locked
worker 0.8.7 APIs. No local project test or build was performed. No provider
operation, deployment, commit, push or production source modification was made.
The reviewer wrote only this review artifact. `git diff --check 13b2c284` passed.

## Deadline and transport assessment

| Property | Independent assessment and location |
| --- | --- |
| Same clock, not independent timer origin | `maintenance.rs:116-190`: ExternalDeadline borrows the invocation, and all current observations call the existing sticky nondecreasing `observe`. It does not borrow the mutable phase handle. Copies retain the cutoff. |
| Compound and inventory arithmetic | Compound cutoff is min(phase-entry+60000,115000); one inventory child is min(parent,inventory-start+30000), created outside pagination. Each exchange gets min(10000,positive remaining). Invalid/infinite elapsed fails closed; no page resets its inventory allowance. |
| Prefetch admission and accounting | `platform.rs:355-376`: request construction and positive deadline check occur before `take`; debit occurs before native fetch is polled. Submitted failures/timeouts are charged, admission denial is not. The shared hard cap remains twenty and all list/current-GET/DELETE calls use it. |
| Complete exchange race | One timer races connection, headers and capped body reading together. Timer win explicitly drops the losing exchange before touching its reader. Exchange success explicitly drops the losing timer. No header-only timeout or detached body task was introduced. |
| Reader ownership | `platform.rs:372,409-467`: acquired native reader is saved in the outer owner before polling read. Thus the reader remains available after dropping a pending read future, rather than disappearing inside the loser. Native chunk size is checked before Wasm copy; total remains <=256 KiB without trusting Content-Length. |
| Cleanup order | `platform.rs:394-404,474-492`: only an outer exchange error invokes controller.abort, once. Timeout then initiates reader cancel and releases lock. Body-cap/read errors and unused non-200 bodies cancel/release without first aborting their stream. Normal EOF only releases. |
| Cancellation settlement | Cancellation is synchronously initiated but its untrusted promise is not awaited past expiry. A capture-free one-shot callback handles either settlement; it retains no request, reader, controller or private input. No Rust background cleanup future or eval is introduced. An indefinitely pending native cancel promise is not claimed to have completed. |
| Status compatibility | RoutingResponse preserves observed status even when body acquisition/consumption fails. List non-200 remains Http(status); known current-rule 404 and DELETE 204/404 remain success without requiring bodies; 200 decode failures remain errors. Foreground RoutingBudget::new has no new duration and foreground POST keeps rule_body. |

The source race is cooperative: neither CPU-bound work nor native D1 calls are
preempted. A final page that completes at the timer boundary may win the select
race; no hard millisecond completion guarantee is implied. The implemented
absolute deadline prevents rolling per-page allowances while preserving full
inventory validation rather than authorizing decisions from partial pages.

## State ownership and SQL allowance proof

`lib.rs:430-483` leaves the first-unit entitlement unconsumed during claims,
complete inventory and discovery. The first row then calls `admit` exactly once;
slow successful inventory cannot lose that entitlement solely to the 15-second
additional-unit slice. Later rows use the same turn and recheck admission.

No destructive authority was relaxed: `platform.rs:701-741` retains current owned
rule GET, exact rule/managed namespace validation, a fresh D1 desired-state read,
then separately admitted DELETE. If DELETE was submitted and times out, the row
is not settled as deleted and no immediate blind DELETE retry is introduced.
Its finite journal slot survives for fresh subsequent reconciliation. Aborting a
request is never treated as remote rollback.

Independent allowance derivation:

1. Complete initial inventory necessarily spends at least one shared egress token.
2. At most nineteen remain; therefore at most nine full GET/DELETE pairs can
   execute for one repair. Each pair needs at most one D1 desired-state SELECT.
   Current-rule 404 spends a GET but no D1 SELECT; it cannot increase this bound.
3. Active/deleting/retired repair adds at most one terminal UPDATE: <=10 SQL.
   Provisioning adoption uses <=3 UPDATEs; fresh absence inventory adds no D1
   SELECT per page and at most one terminal UPDATE. The other state-only branches
   use <=1 UPDATE. Hence ADDRESS_REPAIR_SQL_MAX=10 is conservative.
4. Before each row, `ensure_remaining(pending_rows+10)` retains one charged
   exact-slot release token per still-unattempted row even after that row's full
   worst case. Neither serial execution nor nested calls can borrow another
   phase's grant. Existing address grant 170 and invocation 800 remain unchanged.

`defer_address_repairs` at `lib.rs:495-506` first checks the entire remaining
release set and debits every actual UPDATE through the existing adapter. The
UPDATE conditions exact address, observed state, scan+300000 slot and continued
repair intent; it moves only matching slots to scan-1. An inability to pay or a
binding failure leaves remaining claims at finite expiry, not an uncounted write
or permanently locked state.

Initial incomplete inventory timeout/pre-denial releases all claimed but
unrepaired rows. Within a repair, elapsed pre-denial uses the submitted-count
delta to exclude the current row if any exchange was submitted, while releasing
untouched following rows. A genuine submitted timeout remains a dependency
error. Existing egress-budget Deferred handling is retained and every later
attempt still requires fresh ownership/current-state observations.

## Locked dependency and external evidence

Independently read these installed worker 0.8.7 sources beneath
`C:/Users/STONE/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f/worker-0.8.7/src/`:

- `global.rs`: send_with_signal supplies the exact AbortSignal through native
  RequestInit and awaits native fetch with JsFuture.
- `abort.rs`: abort consumes the controller and invokes the native abort method.
- `response.rs`: native response conversion preserves its ReadableStream rather
  than buffering it before the caller can cap the body.
- `delay.rs`: dropping a pending Delay clears its native timeout handle; the
  successful exchange's losing timer does not remain armed.

Primary references retrieved during the focused review:
[Cloudflare Fetch](https://developers.cloudflare.com/workers/runtime-apis/fetch/),
[WHATWG reader cancellation](https://streams.spec.whatwg.org/#generic-reader-cancel),
and [reader releaseLock](https://streams.spec.whatwg.org/#default-reader-release-lock).
The Streams contract permits cancellation through the active reader and rejects
pending reads when the lock is released. Earlier retrieved
[Workers production guidance](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/)
and [timer semantics](https://developers.cloudflare.com/workers/runtime-apis/performance/)
remain the production context: timers are not CPU accounting or proof of remote
cancellation. The implementation notes reuse
[Anvil, OSDI 2024](https://www.usenix.org/conference/osdi24/presentation/sun-xudong)
for the distinction between repeated observation and reconciliation progress;
this review does not assert a formal liveness proof.

## Limits and next gate

Existing accepted, embedding, R2, database adapter and trace schema source files
have no diff against base. No new foreground timeout was introduced. The thirty
second inventory policy can still make a consistently successful ten-page
inventory at 3.2 seconds/page infeasible; the implementation notes explicitly
state this limitation and do not hide it by weakening completeness. Queue waits,
D1 duration, CPU/RSS/effective plan limits, Cron embedding/R2 deadlines and final
deep diagnostic aggregation remain separate gates/slices.

Before source acceptance, hosted native evidence must establish hanging-header
and hanging-body timeout, one native abort with reader cleanup, actual oversize
chunk rejection/cancel, complete 20-second inventory followed by first promotion,
nonrolling 30-second pagination cutoff, counted priority release and later turn
progress, and ambiguous DELETE recovery without duplicate blind DELETE.
This source review supplies no passing result for those tests.

## Raw working-tree SHA-256 snapshot

| File | SHA-256 |
| --- | --- |
| crates/mail-worker/src/maintenance.rs | CA047833F3FAFAEC1D0CB09CE6ACEFF1E4577A5878DAE2F3A57C25383FCA94E3 |
| crates/mail-worker/src/platform.rs | FAA177E0B71F19D2D924C3F49C8AEE71E9BC63C8C595D6A5F7207A3811A2244D |
| crates/mail-worker/src/lib.rs | 9B437CCFBFC47850CEB1AFE5EE895CD56C67EE1BC342F6C6741C0BA42BC1C625 |
