# Independent review: retained R2 GET local-wait deadline

Date: 2026-10-01.

## Decision and exact scope

**GO for exact-head, non-deploying hosted CI. No substantive defect found in the
focused follow-up.** This is not runtime acceptance, merge/release approval,
deployment permission, or a hard invocation-duration guarantee.

Candidate: `508c68d3e7b1d75248648be647ac1f3a7327fd2c`.
Comparison baseline: `4c27631ec77e7ad804cd32ddfb1bcde6bbe4e910`.
Review artifact lives in independent detached worktree
`.temp/cron-r2-get-508c68d-review`; no production implementation was edited,
and no PR branch was changed or pushed.

Reused the prior independent review and implementation deadline note before
examining the five-file delta. Traced archive GET/body, accepted due admission/CAS,
projection claim/publication, maintenance deferral and subsequent phases, observer
and fixture isolation, ordinary test selection, and unchanged foreground embedding.
Inspected cached lockfile-matched worker 0.8.7 and js-sys 0.3.106 source.
No local project test, build, install, provider request, deployment, secret read,
or sending-unhold action was performed. Git diff whitespace inspection passed.
All runtime/test statements below concern authored discriminators, not execution.

## Contract assessment

| Contract | Evidence and conclusion |
| --- | --- |
| Bound an indefinitely pending local GET wait | archive_read.rs:19-51 selects pinned worker-rs GET execute against Delay from the immutable deadline remaining duration. Timer win drops the losing Rust future and immediately returns the closed maintenance deferral marker. No subsequent await of GET or retry exists. |
| A successful ready GET cannot restart time | select polls GET first. The post-select remaining check catches logical/real expiry even when GET and timer are both ready, cancels only an already-returned stream, and declines body/hash/ZIP work. Missing/error results also cannot evade the expiry check. |
| No projection lease exists to release at this boundary | reconcile_outbound performs admission, statement-budget check and due CAS before repair_accepted. The CAS changes only index_next_attempt_at. accepted::publish creates the opaque token and calls claim only after GET/body/hash/ZIP validation. Existing expired lease fields may exist on a due row, but this read path has acquired no active lease. |
| Five-minute due delay survives timeout | advance_accepted_due sets the exact observed row's due slot to scan_at + 300000 with immutable journal predicates and RETURNING. Neither GET helper nor the maintenance-deferral branch rolls it back. This is retry scheduling, not projection authority. |
| No partial publication or quota mutation on GET timeout | GET timeout returns through ? before body and before the metadata UPDATE / publish call. There is no accepted/quota/storage mutation in get; the durable accepted row, quota reservation and immutable archive remain authoritative. |
| Following item and later cleanup | reconcile_outbound immediately propagates the typed deferral instead of admitting the next row. scheduled continues its phase loop after diagnostic handling; it does not terminate the whole invocation because this phase deferred. |
| Foreground behavior unchanged | The entire follow-up diff touches no embedding helper/caller or foreground timeout code. archive_read::get has exactly the retained accepted-repair caller. Successful existing projector and native body paths are not interrupted by new checks within publication. |
| Cancellation statement remains truthful | Comments and note explicitly distinguish local waiter drop from native/remote cancellation, forbid abandonment of mutation authority, and describe returned-body cancellation separately. R2 get options provide no AbortSignal contract. |

## Authored native discriminators

The two new cases intercept the native-interface bucket.get called by the real
built Rust/Wasm scheduled entry. The never case returns an unresolved Promise;
the delayed case waits on a real workerd 35000 ms timer before forwarding the
original binding GET. These are synthetic native-interface timing faults, not
measurements of a real remote R2 outage.

Host Date.now measures only tick runtime. Required duration is at least 29000 ms
and below 34500 ms, so the old unconditional await fails the delayed case and
cannot finish the never case. The 45000 ms test bound limits failed runs.
No artificial clock offset is introduced in these new modes. Existing late-get
mode still advances worker Date.now by 35000 ms to discriminate the post-result
immutable-cutoff recheck with zero first body reads and one stream cancellation.

Both new cases require zero reads, zero arrayBuffer calls, one GET, no cancel
claim, no indexed text, accepted journal retention, untouched following due slot,
retained source object, and deletion of an old provider event demonstrating later
privacy cleanup. External fixture bucket.get bypasses the observer for source
retention inspection. Fresh Miniflare realm and finally dispose confine the pending
synthetic work. The ordinary pnpm test command selects r2-archive-read.test.mjs;
CI still selects this plus complete-item, routing and embedding deadline suites.

### Non-blocking verification improvements

The new query selects projection token/lease but asserts only state. It does not
directly assert the first row's five-minute due advancement, null/zero lease,
quota_reserved or reserved storage state, nor absence of every staging content row.
Those invariants are supported by the traced write order and helper source, not
fully established by these test assertions. Useful inexpensive hosted assertions:
compare the timed-out row's due against the scan clock within a tight allowance,
assert initial token/lease unchanged, and assert quota/storage reservation unchanged.
Absence of these extra assertions is not a source defect in this narrow patch.

The delayed fixture disposes its realm soon after the 30-second local return, so
it does not verify the abandoned Promise's eventual 35-second settlement.
It does verify the required bounded wait and safe zero-consumption at timeout.

## Native ownership limits

Locked worker 0.8.7 GetOptionsBuilder::execute consumes its builder, submits one
binding get Promise, awaits JsFuture, then converts the returned object.
Locked js-sys 0.3.106 JsFuture installs self-contained resolve/reject callbacks;
its source explicitly states that dropping JsFuture does not detach/free those
callbacks. Settlement remains safe after Rust waiter drop and rejection is handled,
but an unresolved Promise can retain SDK bookkeeping until settlement/runtime
reclamation. Therefore this change bounds application waiting; it neither proves
remote GET cancellation nor immediate reclamation of all native/SDK resources.
No added bespoke background task or late-object callback is needed for correctness.

GET has no durable write side effect and the due attempt was already recorded.
This makes dropping this waiter materially different from abandoning a submitted
D1 mutation, R2 put/delete, or already-owned publication. Native remote work,
D1 latency, CPU parsing and an admitted full successful projector still prevent a
hard 120-second completion claim.

## External grounding

Primary references retrieved during this review:

- [Cloudflare R2 Workers API](https://developers.cloudflare.com/r2/api/workers/workers-api-reference/):
  get returns metadata plus a readable stream; listed get options do not establish
  AbortSignal cancellation. Stream cancellation and GET completion are distinct.
- [Cloudflare Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/):
  use native bindings and bounded streaming; the local race preserves those choices.
- [Beldi, OSDI 2020](https://www.usenix.org/conference/osdi20/presentation/zhang-haoran):
  durable transactional serverless workflows are a structural alternative when
  whole-unit feasibility fails, not evidence that an existing R2 GET is cancelable.
- Lockfile-matched implementation:
  worker-0.8.7/src/r2/builder.rs:40-63 and
  js-sys-0.3.106/src/futures/mod.rs:181-252 in the existing Cargo source cache.

## Required next gate

Run exact candidate hosted, non-deploying CI and retain exact checkout/head SHA,
suite counts and timings for both new cases. The prior green 4c27631 run is evidence
only for the older body-only wait policy, not validation of this follow-up.

