# Accepted outbound projection integrity

Date: 2026-10-01. Implementation base: Mail `origin/main` `ea54512f8ce798e097bc7645e5ee2f690030748c` (PR #18). Source-only correctness repair; no local project test/build, provider request, deployment, live subscription inspection or public-send change was performed. Exact hosted source results are recorded below; deployment admission remains separate.

## Problem and contract

The provider's accepted send is irreversible. `send_requests` owns the original owner-scoped idempotency key, ZIP SHA-256, delivery ID and provider ID. Recovery must never send or charge quota again. The immutable `messages/<id>.zip` and its owned storage reservation remain authoritative until the projection finishes.

The old HTTP and Cron paths independently wrote text chunks, a visible `messages` row, the storage ledger and `state='sent'`. A crash could expose an incomplete legacy projection. More seriously, a paused HTTP projector could resume after Cron had published, the user deleted, and GC physically removed the tombstone: the old unconditional INSERT could resurrect deleted mail. Fixing Cron alone cannot close that cross-path race.

## Implementation

`crates/mail-worker/src/accepted.rs` is the shared HTTP/Cron projection path. Additive migration `0010_accepted_projection.sql` adds an opaque UUID token, a lease expiry timestamp and a nonunique `(message_id,state)` journal index. Existing journal IDs and states are not replaced; no public CLI/API/ZIP schema is changed.

1. Cron reads the original ZIP only after native R2 metadata confirms the existing five-MiB service cap. It verifies the actual ZIP SHA-256 against the journal and applies the existing archive/draft validation. No narrower native-CLI size limit is imposed on the service.
2. HTTP and Cron use the same CAS to acquire a 20-minute projection lease on the exact accepted owner/subject/idempotency/message/provider/hash tuple. The lease must also find the same owner's reservation with the exact retained ZIP byte count and no conflicting existing message projection. A live lease is not stolen. A terminated isolate leaves durable intent; a later attempt can reclaim after expiry.
3. Every staging DELETE/INSERT and every final batch statement rechecks the exact accepted journal, opaque token, unexpired lease, owned reservation and compatible existing projection **inside its SQL statement**. A prior SELECT is not authority. D1 serializes a late write either before a new claim/terminal transition, or after it, when the stale token/state fails.
4. One fenced DELETE removes invalid/stale extra indices before rewriting deterministic UTF-8 chunks. This permits repair when an old compiler left more chunks than the current compiler generates. All expected positive indices are rewritten; the primary key and exact cardinality/range check prove no missing or extra indices at publication. A successful equal-value chunk UPSERT is not stopped based on its change count: the bounded loop proceeds and final completeness decides. There is no durable chunk cursor or deadline exit in this repair.
5. A three-statement D1 batch publishes/upserts the message body prefix, indexes the reservation and moves the exact journal to `sent` while clearing the token. Existing `is_read` and `deleted_at` are never assigned by the upsert. A repaired live legacy projection clears all old vector metadata; a migration trigger revokes/recreates its embedding work so an old in-flight embedding lease cannot commit stale text. New inserts retain migration 0007's original enqueue trigger. The trigger actions are in the same publication transaction, not extra submitted D1 statements. All three batch statements use one captured lease-clock snapshot. A tombstone can terminalize without restaging its deleted body. The final transition additionally requires the matching ledger to be indexed; an ignored/mismatched INSERT or UPDATE cannot authorize completion.
6. All three result objects must report success and the final conditional transition must change exactly one row. An all-no-op batch is not success. The only alternative success proof is an exact journal already at `sent`, which resolves a concurrent winner or an ambiguous completed publication even after GC has removed a deleted row. HTTP therefore truthfully returns the established `202 accepted` after Cron won; it does not reopen the mail.
7. Known projection errors best-effort release only this attempt's token, permitting immediate safe repair without waiting 20 minutes. If release fails or the isolate terminates, expiry is the fallback. Release is never a provider retry. A queued old staging statement after release sees a missing/replaced token and cannot write.

The [official D1 batch contract](https://developers.cloudflare.com/d1/worker-api/d1-database/) guarantees ordered transactional execution and rollback on a statement error. Batching improves atomicity and round trips, **not** the number of submitted SQL statements. [D1 limits](https://developers.cloudflare.com/d1/platform/limits/) include a whole-batch duration bound: a lease is not permission to run an unbounded transaction. Resolved [workers-rs 0.8.7 D1 bindings](https://github.com/cloudflare/workers-rs/blob/v0.8.7/worker/src/d1/mod.rs) expose batch result order, success and conditional change counts.

## Legacy states, readers and deletion

Existing live partial rows whose matching owner journal is still accepted are hidden from metadata fetch, archive fetch, search scanning, summary rehydration and embedding due/claim/content reads. They become visible only with the successful journal transition. A previously learned ID can still be deleted: the owner-scoped conditional tombstone update does not require the now-hidden row to pass the public read query. Unowned or already absent/deleted IDs retain their not-found response.

Deleted-message GC excludes any row with an accepted send journal. It cannot erase the tombstone or original ZIP before recovery terminalizes. The existing orphan collector already preserves accepted/submitting/unknown reservations. A bounded narrow column in the existing accepted selection identifies an exact surviving owned/compatible tombstone. That branch acquires the same token-fenced lease and uses a two-statement ledger/sent batch without R2 read or content reconstruction, permitting GC to finish if old GC deleted the ZIP before failing its database cleanup. It never creates a message row or re-sends. If both ZIP and tombstone already disappeared, deletion intent is no longer distinguishable from missing/corrupt storage; this remains a legacy ambiguity requiring operator repair, not automatic successful terminalization. The shared token/state fences also stop a delayed foreground projector from inserting chunks after `sent` and subsequent physical GC.

Foreign message or reservation collisions are refused, not overwritten. Body/read/delete mutations cannot be inferred from the mere existence of a message ID. Restricted envelope repair is still owner/key/provider/hash scoped and respects the existing 90-day retention; no mail content, SQL, identity or provider error body is logged by this helper.

## Rollout and liveness assumptions

Apply migration before deploying code. Drain old **unfenced** Worker revisions and do not serve a mixed old/new rollout before relying on this invariant: a token cannot constrain code that never checks it. After all serving revisions use the token contract, different compiler revisions cannot mix chunk prefixes because only the current lease holder can stage or publish. A new holder rewrites all indices and the prefix before publication.

### Future staging cutover admission checklist

This is an executable ordering contract for the deployment owner, **not a deployment performed by this change**. The independent privacy/Issues gate must pass first. Do not use this checklist to bypass it. Production Mail is not presently deployed; staging can still have old scheduled invocations.

| Required action/evidence | Admission condition |
|---|---|
| Verify held public sending using the existing private hosted operator checker | `python infra/operator/check_send_hold.py --target staging` succeeds; no public unhold accompanies this cutover |
| Record an aggregate-only journal baseline | Count accepted/provider-positive journals and surviving owned tombstones; retain counts/state distributions and exact source/version, not owner keys, mail IDs, ZIPs or raw SQL results in public artifacts |
| Apply migration 0010 before any new code | Hosted staging D1 migration succeeds; verify the two lease columns, lookup index and semantic-work requeue trigger exist |
| Stop assigning work to old revisions | All effective HTTP/service routing and active Worker deployment percentages serve fenced revisions only; no old Cron trigger can start another old invocation |
| Establish HTTP/service admission stop | Verify old revisions cannot receive new HTTP/service work; record timestamped effective routing/deployment evidence, not source configuration alone |
| Drain old unfenced HTTP/service work | Independently verify completion or provider-confirmed termination of every old invocation that could still mutate these stores. No generic elapsed-time wait substitutes for this proof; a 100% new-version traffic pin cannot terminate old connected requests |
| Establish Cron admission stop | Disable old Cron starts and verify effective trigger state. Account explicitly for the documented up-to-15-minute propagation window; identify `T_last_cron`, the latest possible old Cron start, after propagation/readback uncertainty |
| Drain old unfenced Cron/Queue work | Observe every old invocation completed/terminated, or apply the corresponding documented 15-minute invocation window only after independently establishing its latest possible start and stopping retries/new admission. For Cron this means after `T_last_cron`, not merely 15 minutes after a source/config change |
| Recheck the effective deployment and journal aggregates after drain | No old version serves traffic or newly starts Cron; compare the accepted journal/status counts to the baseline and investigate unexpected divergence before resuming acceptance |
| Run narrowly scoped staged integrity acceptance on exact deployed revision | The post-accepted HTTP/Cron/delete/GC case and supported legacy-tombstone recovery pass, then existing Cron can resume under the fenced-only revision contract |

[Workers limits](https://developers.cloudflare.com/workers/platform/limits/) explicitly distinguish HTTP requests, which have no hard wall-duration limit while the client remains connected, from the 15-minute Cron/Queue window. [Cron trigger configuration](https://developers.cloudflare.com/workers/configuration/cron-triggers/) documents changes taking up to 15 minutes to propagate. Therefore a single 15-minute timer after disabling a trigger/configuration neither establishes the latest old Cron start nor drains old HTTP/service invocations.

If effective routing, trigger state, old invocation termination or timestamp provenance cannot be verified, keep the cutover admission false. Waiting while an old trigger is still able to start more work is **not** draining. Applying a migration is not proof that old source stopped serving. This checklist does not authorize a provider mutation, public send, production cutover or release by itself.

The platform clock supplies durable expiry. Forward clock movement can defer a running holder; backward movement can prolong recovery. The 20-minute value is a finite configured retry window under a progressing platform clock, not a formal wall-time guarantee under arbitrary clock changes and not an HTTP invocation lifetime cap. Token fencing, not assumed old-HTTP termination at 15 or 20 minutes, protects a new lease holder from still-running fenced source. A new holder's UUID, rather than timestamp uniqueness, fences old work.

This change deliberately does **not** add accepted-item fairness, LIMIT 5, a shared D1 budget, phase rotation, timeouts, deadline slices or a durable chunk cursor. A later phase deadline must prove that one maximum valid archive finishes within its admitted turn, or introduce continuation; repeatedly replaying a short prefix is not progress. Current twenty-row accepted recovery can still exceed Paid's documented D1 allowance. No deployment admission or Free-safety claim follows from this integrity repair.

## Source statement accounting

Let `k<=66` be the additional UTF-8 body chunks of any currently valid four-million-byte service draft. The normal success path per selected journal submits:

| Work | Statements |
|---|---:|
| Optional restricted envelope repair (count conservatively) | 1 |
| Projection lease claim | 1 |
| Fenced stale-extra-chunk cleanup | 1 |
| Additional body chunks | `k` |
| Atomic publication batch | 3 |
| **Normal accepted recovery** | **`k+6<=72`** |

The outbound phase setup still submits two statements. A proposed five-item phase would therefore have normal upper bound `2+5*72=362`, giving the earlier loose full-Cron normal model **734**, not 729. An all-no-op late final batch can additionally require one exact-sent read and one failed-attempt lease release: conservative per-item submitted-call bound **`k+8<=74`**, five-item outbound **372**, corresponding combined loose bound **744**. Failed calls remain submitted statements; no refunds are assumed. Existing twenty-item source behavior remains unsafe under the documented 1,000-query invocation ceiling. These are source ceilings, not measured database/provider enforcement or CPU/RSS. The exact surviving-tombstone branch uses one claim plus two batched statements (3 normal; at most 5 with no-op resolution/release), no ZIP read, chunk cleanup, body writes or envelope repair. Its scalar discovery is part of the same existing due SELECT, not an extra binding call. Each chunk's journal/reservation/legacy-row guard performs additional indexed database work up to 66 times per valid draft. Preserve correctness first; measure actual-account 4MB foreground latency and Cron CPU before claiming acceptable performance or replacing this with parameterized multi-row writes.

## Hosted acceptance evidence required

Use the real built Rust/Wasm entry, isolated native D1/R2, synthetic ZIPs and controlled synthetic I/O on GitHub-hosted runners only. No production test hook is added. Independent validator artifacts provide the initial stored-ZIP and post-accepted HTTP/Cron harnesses; their exact branch commits must be recorded with eventual run URLs.

| Interleaving/fault | Required observation |
|---|---|
| Exact 4,000,000-byte text plus replay | 67 exact pieces, one delivery, stable quota/IDs; provider never resubmitted |
| Fault on chunk 3, then repair | Accepted and invisible, at most two staged chunks; eventual byte-exact publication |
| Error in final sent transition | Entire three-statement publication rolls back; retained accepted ZIP/ledger repairs later |
| Legacy live partial row | No get/archive/search/embedding exposure while accepted; prefix/chunks repaired before sent |
| Old GC removed ZIP but surviving owned accepted tombstone remains | Two-statement terminalization, then real GC clears content/ledger; no reconstructed row or provider call |
| Existing or newly arriving user tombstone | Never cleared, never reappears; accepted-aware GC waits until terminalization |
| Foreign existing message/reservation | No foreign body/chunk change and no journal terminalization |
| Fresh live lease | Competing projector writes nothing; original holder remains authoritative |
| Expired lease and stale-token statement | New holder replaces token; every old staging/final statement becomes a no-op |
| Foreground accepted UPDATE paused before claim | Cron publishes; public delete plus real GC finishes; resumed HTTP returns same-ID 202 and writes nothing |
| Legacy vector and old leased embedding work | Vector metadata invalidated, work freshly queued; an old embedding lease cannot commit after repair |
| Older extra chunks / shorter new body | Stale suffix removed under lease; exact current compiled body and original mutable read/delete flags |

Only static Rust formatting/parsing and `git diff --check` were run locally. Runtime evidence comes exclusively from the exact hosted run recorded below, not local execution or a deployed-provider test.

### Integrated hosted test selection

The selected final validator files/reviews come from `570554ce395f1b7aac740c5828b2a7f330511dc0`; provider-free EmailService adapter research comes from `a723eb7`. They are integrated as scoped file snapshots, not a merge of the validator's older branch. Main's existing address, embedding HTTP and SQL-comment suites remain in the default package script.

The default hosted workerd suite adds **11 standalone accepted-integrity cases** in `outbound-recovery.test.mjs` and **5 deterministic HTTP/Cron and public-deletion cases** in `accepted-http-cron-race.test.mjs`. `outbound-recovery-budget.test.mjs` remains explicitly outside that default: twenty maximum valid archives are a known resource-bound counterexample awaiting the separate budget/fairness repair, not a skipped integrity assertion or a passing budget claim.

The corrected archive-present tombstone fixture observes zero new body-chunk staging, exact journal terminalization and real GC. It does **not** claim its removed, unreachable trigger exercised cached-R2 mid-projection GC. The HTTP expired-lease fixture resumes the stale HTTP holder after the new owner has already terminalized/deleted/collected; it proves that no resurrection occurs then, not separate runtime proof of stale-token isolation while a new owner is still publishing in accepted state. Token predicates also have independent source review. Hosted evidence is limited to the exact revision and selected cases recorded below.

Reproduce only on the hosted runner after its real Rust/Wasm build and shim preparation:

```sh
pnpm --dir infra/tests/worker-boundary install --frozen-lockfile
pnpm --dir infra/tests/worker-boundary test
```

Local checks of the integration were `node --check` for the six new JavaScript modules and `git diff --check`, not test execution.

### First hosted run and DELETE result correction

[Actions run 36804402543](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36804402543), PR head `25acdf1`, compiled the Rust/Wasm Worker but its default built workerd suite failed **13/87 cases**: eleven standalone fixtures were rejected by the production held-send INSERT guard before exercising recovery, and two real HTTP/Cron cases reported owner DELETE 404. These are failures, not completed acceptance. The isolated held-canary fixture correction is reviewed separately; do not disable the production guard to seed tests.

The DELETE implementation's exact-one `meta.changes` check was incorrect. The pinned Miniflare implementation derives that metadata from SQLite aggregate `total_changes()`; deleting a pending embedding work row and its owner schedule makes more than one database change although exactly one message was tombstoned. The official [D1 result contract](https://developers.cloudflare.com/d1/worker-api/return-object/) does not promise a direct-message-only count under triggers. The fix uses a single owner-scoped, still-live `UPDATE ... RETURNING id` and the returned row's presence. [SQLite RETURNING](https://www.sqlite.org/lang_returning.html) distinguishes directly modified rows from additional trigger changes. This preserves one submitted statement, first successful owner deletion `204`, foreign/already-deleted `404`, and deletion of a known hidden accepted legacy projection; it introduces neither a precheck race nor unconditional success.

The HTTP/Cron harness now checks exact owner/live-row preconditions, persisted deletion even when status is unexpected, foreign identity `404` without modification, first owner `204`, and repeated `404` without retombstoning. Two additional cases cover no pending embedding work and a known legacy projection hidden by accepted state. The ordinary cases explicitly require pending work so the cleanup triggers are actually exercised. These cases passed in the exact hosted rerun below; only static syntax/format/diff checks were performed locally.

### Corrective hosted evidence

Exact source revision `e75207531664d94adadb02d34ad7144d052d3992`:

- [Source run 36805785881](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36805785881) completed successfully: all six source jobs passed (CLI Linux, Windows and macOS; Astro site; Rust/Wasm Worker; infrastructure tests).
- Its real built Rust/Wasm workerd step reported **89 tests, 89 passed, 0 failed**, including the eleven accepted-recovery cases and five HTTP/Cron/public-deletion cases. The original `send_held` fixture setup and false owner-DELETE `404` failures were not weakened or ignored.
- [Workflow/syntax run 36805785689](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36805785689) passed on the same immutable revision.
- Provider/deployment/unhold jobs were skipped. No real send, deployed D1 enforcement, actual-account CPU/RSS, quiescent cutover, privacy approval or public release is established by these synthetic hosted passes.

The subsequent lease-comment/runbook correction separates HTTP lifetime from Cron/Queue bounds and integrates the [cutover admission contract](accepted-projection-cutover-contract-2026-10-01.md). It changes no lease duration, source predicate, migration SQL operation or test semantics; its exact final commit still needs the normal source checks before merge. Merging this source repair is not deployment approval.
