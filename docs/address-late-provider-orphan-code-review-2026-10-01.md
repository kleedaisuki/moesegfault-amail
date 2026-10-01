# Independent code review: late-provider orphan convergence

Date: 2026-10-01. Reviewed commit: `e06d2bab75657594a0bdb8e36e5ed652ed2cfadc`, compared with main `d3e2f7d`. Reviewed the provider-first design and independent design review in the sibling isolated worktrees, production Rust callers, boundary fixture additions, Cargo dependency/lock changes, and implementation/budget notes.

## Decision

**One substantive P2 correction is required before merge acceptance: budget-skipped rows do not receive fair external-work turns under persistent failures of earlier rows.** GO to implement the correction and run exact-head hosted verification; not GO for deployment/provider mutation. No demonstrated foreign-deletion or public-contract break was found in inspected paths. This is static review, not a successful compile or executable verification.

## F1 — P2: rotate attempted work, not budget-skipped rows identically

Locations: `crates/mail-worker/src/lib.rs:322-326` (every claimed row receives the identical `scan_at + 5 minutes`), `391-407` (all selected rows are claimed before inventory and the fixed-order loop), and `platform.rs:522-524` (cannot admit GET+DELETE with fewer than two remaining calls).

Trigger: ten or more due retired/deleting lifetimes, each with a strict owned route, fit in one inventory page. The first nine by existing `created_at,address` order have current GETs that succeed and DELETEs that return a persistent fixed failure, such as HTTP 200 `success=false`; the later lifetime has a healthy removable route. Every row remains flagged, with stable created/name ordering.

Executable-path derivation, not an executed local test:

1. All ten rows are selected and assigned exactly the same next due timestamp.
2. Inventory costs one of twenty calls.
3. Each of the first nine failing routes consumes its admitted GET+DELETE pair: eighteen more calls. Failure retains their repair intent.
4. One call remains, so the healthy later row fails pair admission without even receiving its ID GET.
5. At the next due tick all ten again have the same due timestamp, unchanged birth/name tie-break order, and unchanged routes. The identical first nine consume the same nineteen calls indefinitely.

Impact: one bounded batch of permanently failing provider objects prevents unrelated healthy deletions from converging. The new preclaim policy removes starvation between batches when there are more than thirty rows, but not within a batch. The comment claiming every selected row owns a fair retry slot is insufficient: receiving a scheduler selection is not receiving an admitted external-work attempt. Safety is preserved, but the intended fair bounded-repair contract and failure isolation are not.

The new forty-row fairness fixture (`infra/tests/worker-boundary/address-add.test.mjs:560-579`) uses only successful deletions. It eventually empties the provider store because early successful rows leave the queue, and therefore cannot distinguish this defect.

Correction guidance: preserve the pre-inventory rotation that handles whole-inventory failures, but after successful inventory distinguish attempted/finished rows from rows denied admission solely by budget. Make deferred rows precede already-attempted rows at a subsequent tick using durable conditional scheduling, or use an equivalent explicit fair cursor. Do not rearm every discovery or unconditionally reset all flagged rows to -1. Keep state-only repair progress, current-state guards, existing 30-row and 20-call caps, and repair intent on unknown outcomes. Add a hosted fixture with <=30 due lifetimes, nine permanently failing DELETE acknowledgments, and one or more later healthy routes; assert that the healthy route is removed in a bounded number of successive admitted ticks while failed markers remain. Also retain the >30 and failed-inventory fairness checks.

Confidence: high in the static failure path; no local project tests/builds were run.

## Positively inspected contracts

- Every scheduled tick reaches one complete bounded provider inventory even with zero due rows. A provider failure rotates preclaimed rows; it does not license cleanup from a partial prefix.
- Complete inventory is a private tuple type only returned after terminal proof. At most ten pages, fifty objects/page, five hundred unique validated IDs, coherent optional counts/pages, no redirects, and bounded streamed response bytes are checked. Ten full pages without terminal metadata do not establish completeness.
- Retired discovery derives at most five hundred provider-positive keys, uses fifty-key D1 point-query batches, excludes other domains/reserved candidates, never scans all historical tombstones, and conditionally rearms marker=0 without altering owner/state/name/slot/birth.
- All provider DELETE callers now pass through current full ID GET, strict exact single matcher/action/ingress/source/name predicate, and current D1 desired-state check. Active committed ID protection is re-evaluated after provider GET. Saved ID alone is not authority; a foreign ID found in complete inventory blocks settlement. An absent saved ID is not blindly appended/deleted.
- GET 200 `success=false`, mismatched ID, malformed/foreign rule, and DELETE 200 `success=false` cannot confirm removal. Known-ID 404 and DELETE 204/404 remain explicit documented missing-resource assumptions, not generalized error recovery.
- Provisioning-to-pending obtains a fresh complete absence recheck from the same twenty-call budget rather than treating the older shared snapshot as new proof. Budget cannot cover its worst case: leave provisioning and retain scheduling.
- Request DELETE retains the existing accepted `202` vocabulary and leaves partial work deleting. No API shape, address state/schema, ownership lifetime, or CLI change was found.
- New `futures-util` is already present in Cargo.lock with macro support. `worker` v0.8.3 exposes `ResponseBody`, `Response::body`, `Response::stream`, and a byte Stream in official source; the inspected usage is consistent. No concrete hidden compile error was identified, but only hosted exact-head Rust/Wasm compilation can establish it.
- New public(crate) structs/functions and important ownership/budget implementations have semantics-oriented Rust documentation. English implementation notes explicitly preserve held/privacy/version/management-exclusivity/recovery gates and do not claim deployment or real campaign success.

## Retained limits, not new findings

The provider API does not give a verified atomic inventory snapshot or content-fenced DELETE. Scope safety still requires exclusive management of exact managed IDs/names. Known-ID missing-resource handling and immutable ID lifetimes require the existing provider assumptions. The retired-only drift goal does not solve clean-pending late creates or prove historical producers are quiescent.

The twenty-call address allowance is not a whole-Cron D1/account-plan admission guarantee. The implementation explicitly documents that outstanding gate; source review and an address-only egress assertion cannot establish deployment readiness. Privacy/Issues, serving provenance/bindings, public-send hold and retained-escrow/recovery ownership remain separate release gates.

## Evidence and scope

Inspected full production Rust diff, all route DELETE call sites, relevant add/delete state transitions, new persistent synthetic provider harness, adversarial/fairness fixtures, Cargo.lock/package manifest, and docs. `git diff --check d3e2f7d e06d2ba` returned clean. No production source edits, local project tests/builds, provider/account calls, push, or deployment were performed.

Public official references retrieved on 2026-10-01: [Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/), [workers-rs v0.8.3 response source](https://raw.githubusercontent.com/cloudflare/workers-rs/v0.8.3/worker/src/response.rs), and [workers-rs v0.8.3 streams source](https://raw.githubusercontent.com/cloudflare/workers-rs/v0.8.3/worker/src/streams.rs). Industry/research controller rationale is already documented in the reviewed design; this review does not rediscover it or claim formal verification.
