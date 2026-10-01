# Independent review: bounded Paid-first Mail maintenance

Date: 2026-10-01. Reviewed architecture commit: `34e909d1df431ae3c07e4828c199108f4e2b91b1`. Source reference: Mail main `c6f93bf4cadbb58c69027ebc6208d594ca713c80`. Separately inspected embedding transport candidate worktree head `0c9e1f1dd12ed761de7cb393711f10eec1fa2eff` to distinguish its 30-second default from the proposed Cron policy. This is independent source/document review, not execution evidence. No local project tests/build, provider operations, remote plan inspection or deployment was performed.

## Verdict

**GO for bounded source implementation after the accompanying ADR corrections. NO-GO for implementation exactly as originally scoped, or for deployment/release.** The first statement-budget slice is independently implementable. The projection/lifetime slice must cover both existing HTTP and Cron publishers; a Cron-only fence would leave a concrete resurrection race. Paid/effective limits, privacy admission and maximum-valid workload evidence remain rollout prerequisites. The source model is not an actual CPU/memory/latency profile.

## Findings and corrections

### 1. Material: HTTP is also a projection writer

The original ADR describes fenced Cron staging and excludes HTTP paths from the resource-wrapper refactor, but does not require existing HTTP post-acceptance writes to obey the fence. Current `send_message` persists accepted state, invokes unfenced `store_text`, inserts `messages`, updates the ledger and then sets sent separately (`crates/mail-worker/src/lib.rs`, approximately lines 2471–2492). These writes can overlap the new Cron projector and deleted-message collector.

Concrete counterexample, without provider resend or a stale Cron fence:

1. HTTP successfully submits EMAIL, stores accepted state, then suspends before its unfenced chunk or message INSERT.
2. Cron claims the same accepted journal, stages all chunks and atomically publishes message/ledger/sent.
3. User deletes the now-visible message; its tombstone hides it. GC sees sent rather than accepted, deletes R2, chunks, message and reservation.
4. The paused HTTP writer resumes. Unfenced `store_text` can recreate orphan chunks; its plain message INSERT now succeeds because GC removed the tombstone. The message is visible again, possibly with a missing archive and missing quota reservation.

An accepted-aware GC SELECT fixes the *legacy accepted partial-row* case but not this *sent then old HTTP writer* case. A paused HTTP writer is a current supported workflow, not a theoretical old-schema corner.

**Minimal compatible remedy:** share one post-acceptance projection helper between HTTP and Cron. It never submits EMAIL or charges quotas; it acquires a conditional claim on the exact owner-scoped send journal and guards envelope/chunk/finalization writes using that identity, accepted state and a unique fence. HTTP keeps its normal parsing/admission/provider path and its existing 202 accepted response contract; if another projector owns the item, leave durable recovery intact rather than publishing unguarded. Cron retains its private accounting wrapper. Use a unique token or prove that the due timestamp changes on every successful takeover. Both paths use the same three-statement terminal batch and distinguish `LostClaim` from actual publication.

The terminal two statements must additionally prove the surviving message belongs to the expected owner/archive/direction. `INSERT OR IGNORE` due to an unrelated collision is not permission to release the journal. D1 batch rollback applies on SQL error; successful conditional no-ops do not automatically roll back or prove progress. Use the terminal UPDATE result's changes count, with no extra success-path read required. These predicates and fence bindings do not increase the modeled Cron statement count.

Hosted discriminator: pause the real HTTP boundary immediately after accepted and at an intermediate chunk; let Cron finish, delete, run GC, then release HTTP. Assert no message/chunk resurrection, no second provider send, no new quota charge and no cross-owner row mutation. Include stale HTTP and stale Cron claim transfers and a preexisting tombstoned accepted row.

### 2. Material liveness condition: a 15-second slice can repeatedly replay one prefix

The Paid choice deliberately has no durable chunk cursor. A deferred item reparses the ZIP and rewrites chunks starting at the first extra index. Finite due times and phase rotation provide service opportunities but do not imply terminal progress if the full valid item's successful work never fits its slice.

For example, a valid text item with 66 extra chunks and consistently successful 300-ms D1 writes needs over 19 seconds for chunks alone. A 15-second phase admission slice writes the same first approximately 49 chunks on every attempt, defers, and never reaches finalization. This does not require an indefinitely failed dependency or a CPU-limit violation. Repeating successful calls is not sufficient for liveness.

**Correction:** make completion of a maximum-valid item under the actual admission policy a rollout discriminator. If that path is not feasible, increase a reserved per-item completion allowance based on measurements, or add durable committed-chunk continuation; do not claim phase rotation resolves it. Initial 15/120-second policies may be useful probe settings, but are not established service guarantees. The accompanying ADR now states this explicitly.

### 3. Documentation correction: an entire D1 batch has a published duration limit

The original ADR says an entire 30-second batch bound is not justified from the individual-query limit. The official [D1 limits page](https://developers.cloudflare.com/d1/platform/limits/), footnote 4, explicitly applies 30 seconds to the entire batch call. The stronger bound is therefore documented, although timeout does not establish remote cancellation or whether a commit occurred. Keep the journal-based ambiguous-result recovery. This correction does not justify a 15-second phase deadline or a smaller CPU bound.

### 4. Policy reconciliation: embedding's candidate 30 seconds is not Cron's 10 seconds

The separately developed embedding transport has a 30-second header/body abort bound. The ADR proposes 10 seconds inside a 15-second Cron slice. Neither constant overrides the other automatically. Globally replacing the candidate's 30 seconds with 10 would affect foreground semantic requests without having established the need.

**Compatible integration:** retain the foreground default; add an internal duration/deadline-aware transport entry point. Cron passes the minimum of 10 seconds and remaining phase/global admission time. Check time before acquiring an embedding claim or starting transfer. No time left is a budget/deadline deferral, not a provider attempt; a submitted exchange that actually times out remains transient under existing retry policy. The 10-second threshold still requires latency/backlog evidence: it can otherwise turn a usable but consistently slower provider into a permanent nonprogress condition. Manual redirects, incremental response cap and native abort semantics remain required in both modes.

## Pre-merge accounting correction and reallocation

The first revision of this review incorrectly endorsed `170+360+90+2+65+65+5+5+8 = 800`; its actual sum is **770**. This arithmetic mistake was caught before PR #21 merge and is explicitly corrected rather than silently preserving the old endorsement. Independently re-summing the phase allocations gives the revised choice `170+380+90+2+65+65+5+5+18 = 800`. It preserves the established address/semantic/GC reservations, increases outbound to 380 for its new cleanup plus failure-resolution headroom, and makes the remaining 18 control tokens explicit. Each grant meets its listed healthy-path ceiling; phase borrowing is still prohibited.

The in-progress accepted integrity implementation additionally submits one fenced stale-index chunk cleanup DELETE per item. Its normal maximum is therefore `2+5*(1 claim+1 cleanup+1 envelope+66 chunks+3 finalization) = 362`; the combined normal-path model is `160+362+83+1+61+61+3+3 = 734`. The previous 357/729 model was valid only before this new cleanup, not for the integrity implementation. This follow-up inspected the current `accepted.rs` candidate statically and makes no execution claim.

That candidate also has a failure-only conditional lease-release UPDATE and a journal resolution read for failed claims/all-no-op finalization. These are **additional executed statements**, so 734 must not be advertised as an unconditional all-outcome ceiling. Debit and admit each through the common wrapper, including compensation; if a permit cannot be obtained, retain the journal/lease for later recovery. The revised outbound grant's 18-token normal-path headroom does not authorize unbounded retries. The shared runtime 800 ceiling remains the hard source guarantee to test, independently of normal-path arithmetic.

## Reviewed parts of the corrected design

| Property | Independent result |
| --- | --- |
| Phase reservations | Corrected allocation `170+380+90+2+65+65+5+5+18 = 800`. No borrowing keeps deletion/indexing opportunity independent of address/outbound load. The earlier allocation was 770, not 800. |
| Source loose normal-path ceilings | `160+362+83+1+61+61+3+3 = 734`, including five claims and five stale-index cleanup submissions. Failure/no-op resolution and retries require separate debits. |
| Maximum service text chunks | At most 4,000,000 compiled text bytes; each nonlast UTF-8 slice is at least 59,997 bytes, hence at most 67 parts / 66 extra INSERTs. Empty text still uses one first part. |
| Outbound phase | Two setup statements plus five times `(one claim + one stale-index cleanup + one possible envelope UPDATE + 66 chunk INSERTs + three finalization statements) = 362`. Reserve 72 per healthy maximum-valid item before claim/I/O; additionally admit actual resolution/release work. |
| D1 submission accounting | Counting each submitted prepared statement, including N batch members, no-ops, errors and retries, is a conservative application contract. prepare/bind are not executions. No claim that batching erases platform query limits. |
| R2 / diagnostic model | Five GETs plus forty DELETEs per two GC phases gives 85; one final diagnostic batch plus 800 SQL tokens gives 886 modeled internal operations. Exact billing/subrequest internals remain distinct. |
| Terminal publication | A three-statement D1 batch can atomically publish message/ledger/sent; order, same-claim predicates, same-owner message proof and conditional result handling are mandatory. |
| GC legacy case | Keeping accepted-linked tombstones until terminalization prevents old partial-row recovery from resurrecting user-deleted content; both publishing paths must then honor the fence. |
| Eight-phase rotation | `floor(scheduledTime/300000) % 8` is coherent for the current single five-minute Cron schedule and needs no isolate-global state. It is conditional opportunity fairness, not a cleanup SLA. |
| Free alternative | Parameterized multi-row chunk INSERTs can reduce 66 writes to three within the stated bound-parameter limit. They do not prove the combined handler fits Free query/CPU limits. |
| Clock interpretation | [Workers timers](https://developers.cloudflare.com/workers/runtime-apis/performance/) advance after I/O, so admission checks cannot certify synchronous CPU work or preempt ZIP/DOM parsing. |

Current official [Workers limits](https://developers.cloudflare.com/workers/platform/limits/) support the distinction between 30 seconds CPU for a five-minute Paid Cron, fifteen minutes wall time and 128-MB per-isolate memory. The actual account tier/effective settings are still unknown to this review. The ADR appropriately uses the stricter published D1-specific query bound and avoids claiming profiling from statement arithmetic.

## Concrete implementation slices

1. **GO now, source only:** private `MaintenanceDb`/single-use statement permits; phase reservations; instrument every scheduled execution and batch; tests prove exhausted admission never calls a binding and no nested helper bypasses accounting. No deployment inference.
2. **GO after corrected contract is agreed:** additive due/claim schema plus shared post-acceptance HTTP/Cron projector, conditional staging, owner-safe terminal batch, accepted-aware GC and five-item fair Cron selection. Keep provider submission/quota/idempotency semantics unchanged. Test adversarial interleavings before claiming lifetime closure. Drain/avoid mixed old unfenced HTTP writers at rollout.
3. **GO after integration with transport candidate:** deadline-aware embedding entry point, routing aborts, phase rotation and admission; accumulate fixed diagnostics then flush once. Include the complete-item latency discriminator, not just per-phase first-opportunity tests.
4. **NO-GO until evidence:** deployment/release awaits verified Paid/effective limits, existing privacy gates, actual-account batch behavior and synthetic maximum-valid compilation/projection CPU/memory/wall completion. The Cron gate is independent of the second-principal, quota campaign and public-outbound release gates.

The reviewer updated only the ADR and this English review artifact. No production implementation was changed, no tests were represented as executed and no provider-facing action was taken.
