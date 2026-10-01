# Independent source review: Mail Cron complete-work admission

Date: 2026-10-01.
Candidate worktree: `.temp/cron-liveness-implementation`.
Base and worktree HEAD at inspection: `cb50b35e1672e33a503e423c125016235f81386c`.
Boundary: the uncommitted source candidate, including new untracked
`crates/mail-worker/src/maintenance.rs`; this is not a review of a committed PR
revision. Fixture authors were still editing tests during this review.

Post-commit association: source commits `d4199b5` and `dad8f48`, with fixtures
at PR #25 head `764dcbe42948e9f0ecc53dedfbcaec9156371767`. At that head, all six
production/raw-file SHA-256 fingerprints below were independently recomputed and
match the originally reviewed uncommitted snapshot exactly. This associates the
reviewed source content with the committed candidate without retroactively
claiming fixture review or runtime verification.

## Verdict and severity

**No substantive source defect found within the explicitly declared first-slice
scope. GO to nondeploying hosted source verification, not to deployment/release.**
There are no P0/P1/P2 correction requests from this review. Confidence is moderate
for source contracts, not runtime feasibility. No local project test or build
was performed; no provider mutation, deployment, commit or push was performed.
The reviewer changed only this review document.

## Scope and evidence

Read the implementation scope and policy notes first, reused the existing budget
ADR/review, and inspected the new admission module, all changed scheduled call
sites and their surrounding cleanup/outbound/embedding routines. Inspected the
unchanged statement adapter and the Rust trace-schema/Python mirror changes.
`git diff --check` completed without whitespace findings at the inspection point.
CI wiring and in-progress native fixtures are outside this source review.

| Contract | Independent source assessment |
| --- | --- |
| Invocation origin and clamp | `MaintenanceTurn::new` captures actual handler entry, not schedule time. `observe` uses maximum prior elapsed and nonnegative origin delta; backwards observations cannot restore eligibility. A nonfinite delta becomes infinity and remains sticky. |
| Threshold arithmetic | Outbound/addresses enter at elapsed <= 55,000 ms, i.e. 60,000 ms before 115,000 ms cutoff. Other phases enter strictly before 115,000 ms. Additional units require phase elapsed < 15,000 ms and the same phase-specific global headroom. Inclusivity is consistent with documented policy. |
| First entitlement | `enter` precedes database construction and setup at `lib.rs:196-197`. Each phase has one turn. The first `admit` consumes exactly one entry entitlement and cannot be denied solely because setup used the slice. This may start an already entitled item after cutoff; it is explicit policy, not hard cancellation. |
| Scheduled slot and grants | `phase_order` rotates identities with floor(schedule/300000) modulo eight; it neither reorders enum discriminants nor changes phase grant indexing. Existing configured Cron expressions are five-minute expressions. Duplicate/delayed scheduled slots have stable order. Arbitrary missed-slot fairness is explicitly not claimed. |
| Accepted boundary | `lib.rs:639-646` admits before the unchanged 75-statement allowance and exact due CAS. The noncloneable permit moves into `repair_accepted` once, before R2/archive/projector work. No time check was added inside accepted chunk writes, final publication, lease resolution or failure release. |
| Accepted integrity and accounting | `accepted.rs` is unchanged against base. `database.rs` changes only an explanatory enum comment; TOTAL=800 and GRANTS=[170,380,90,2,65,65,5,5] remain unchanged. The due/claim SQL and 75-statement reservation are unchanged. No foreground API changes were observed in the reviewed diff. |
| Deleted cleanup | `lib.rs:267-268` admits and checks all three SQL statements before the first R2 deletion. No admission check interrupts the row's complete existing delete sequence. |
| Orphan cleanup | `lib.rs:304-305` admits before protected-send SELECT, checks its SELECT plus two SQL deletes before destruction, and retains the existing submitting/unknown/accepted protection. No admission check interrupts the row's sequence. |
| Embedding claim | `lib.rs:842` admits before `claim_embedding`; existing active-row lease recheck, processing, persistence/retry and cooldown paths have no new elapsed rejection after claim. |
| Diagnostics | Deadline and statement denials use separate application-owned markers and distinct diagnostic codes, both paired only with ResourceDeferred. Rust validator/producer and Python allowlist/pair validation are synchronized. Maintenance diagnostics remain standalone; request-child deferrals remain invalid. |

Reference line numbers describe the inspected working-tree snapshot and may move
with subsequent formatting. These findings do not assert that authored tests pass.

## Material boundaries, disclosed rather than misclassified as defects

1. Addresses retain the entire existing finite claim/inventory/repair phase as
   one compound admitted unit. No per-row time gate or release allowance was
   introduced. The scope explicitly defers those together, avoiding a new
   partial-claim-release path in this slice.
2. Routing/inventory deadlines, Cron-specific embedding transport bounds and R2
   reader cleanup bounds are not implemented. Existing foreground transport
   behavior is not silently changed.
3. Immediate diagnostic Queue awaits can consume the admission window. Batched
   end-of-turn aggregation is expressly deferred. A phase failure followed by
   admission denial can still leave only the aggregate returned deferral visible;
   this is part of the separately declared diagnostic aggregation work, not a
   claim that this slice provides complete failure accounting.
4. Older closed-schema consumers can acknowledge/drop the new enum variant.
   Updating/verifying the sink before producer rollout is an explicit release
   prerequisite, even though the active source mirror is synchronized.
5. Complete-item entitlement removes an application-induced prefix cutoff, not
   platform lifetime, CPU, dependency latency, lease-feasibility or memory limits.
   All phases may still be denied after one long complete item. Rotation grants
   conditional recurring opportunity, not a completion SLA.

The next discriminating evidence is the nondeploying hosted native fixture:
maximum valid 66-chunk projection at 300 ms per chunk must reach terminal exact
content despite crossing the 15-second slice; the second due CAS/R2 attempt must
not occur, and later cleanup must still have an opportunity when global headroom
allows it. Slow setup must exercise first entitlement without clock-resetting.
No result for these experiments is supplied by this source review.

## Primary-source checks

Official documentation retrieved during review:

- [Workers performance and timers](https://developers.cloudflare.com/workers/runtime-apis/performance/): deployed Date/performance clocks advance with I/O, so observed deltas are not CPU measurement or synchronous preemption.
- [Scheduled handler](https://developers.cloudflare.com/workers/runtime-apis/handlers/scheduled/): scheduledTime is intended execution time in epoch milliseconds; returned handler promises are awaited subject to the platform's 15-minute lifetime.
- [Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/): invocation-local mutable state and awaited binding work are consistent with production guidance. No new floating I/O or module-global per-invocation state was introduced.

The initial docs.rs retrieval failed. In the post-commit follow-up, independently
read the locked local dependency source at
`C:/Users/STONE/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f/worker-0.8.7/src/schedule.rs`:
`ScheduledEvent::schedule(&self) -> f64` returns its `scheduled_time` field,
which is populated from the edge event field via the `scheduled_time()` accessor. The
production `event.schedule()` call therefore matches the locked source API.
This resolves the accessor-verification gap; full build/runtime compatibility
still remains hosted evidence, not a locally executed claim.
Existing repository architecture review already supplies the recurring
controller/liveness research context; no new formal-proof claim is made here.

## Snapshot fingerprints

SHA-256 of reviewed production files (raw working-tree bytes):

| File | SHA-256 |
| --- | --- |
| crates/mail-worker/src/maintenance.rs | FCE549BC6E11055308CDEFF7ACAB5C23858037EB143C5DC4E32BD37C3FA17D2E |
| crates/mail-worker/src/lib.rs | 676135669DAD7DBA055C4E1F04AFE38C1CE34C345D0889E8CEF11E8788A67741 |
| crates/mail-worker/src/trace.rs | 7E3C6BDBBD4CDC168C51B9E45A3D982668700B8F4EE46BCFE3280329A799105A |
| crates/mail-worker/src/database.rs | A02044113E1859F60FD108FE32DF17E53A86B46DD711DB87264363CD8B0DB7FC |
| crates/trace-schema/src/lib.rs | 13636443260AFE8712F0935F0C2A607A4B40F58CF195E10D9DD538696F86464D |
| infra/tests/staging_trace_sink_canary.py | E26A33BF61F2FEEAA0B8668BE73521D2E0619F11B89E94EE3E67FE1852BCDBDF |
