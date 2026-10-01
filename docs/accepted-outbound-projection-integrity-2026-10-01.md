# Accepted outbound projection integrity

Date: 2026-10-01. Implementation base: Mail `origin/main` `ea54512f8ce798e097bc7645e5ee2f690030748c` (PR #18). Source-only correctness repair; no local project test/build, provider request, deployment, live subscription inspection or public-send change was performed. Validation below is an acceptance plan, not a claimed result.

## Problem and contract

The provider's accepted send is irreversible. `send_requests` owns the original owner-scoped idempotency key, ZIP SHA-256, delivery ID and provider ID. Recovery must never send or charge quota again. The immutable `messages/<id>.zip` and its owned storage reservation remain authoritative until the projection finishes.

The old HTTP and Cron paths independently wrote text chunks, a visible `messages` row, the storage ledger and `state='sent'`. A crash could expose an incomplete legacy projection. More seriously, a paused HTTP projector could resume after Cron had published, the user deleted, and GC physically removed the tombstone: the old unconditional INSERT could resurrect deleted mail. Fixing Cron alone cannot close that cross-path race.

## Implementation

`crates/mail-worker/src/accepted.rs` is the shared HTTP/Cron projection path. Additive migration `0010_accepted_projection.sql` adds an opaque UUID token, a lease expiry timestamp and a nonunique `(message_id,state)` journal index. Existing journal IDs and states are not replaced; no public CLI/API/ZIP schema is changed.

1. Cron reads the original ZIP only after native R2 metadata confirms the existing five-MiB service cap. It verifies the actual ZIP SHA-256 against the journal and applies the existing archive/draft validation. No narrower native-CLI size limit is imposed on the service.
2. HTTP and Cron use the same CAS to acquire a 20-minute projection lease on the exact accepted owner/subject/idempotency/message/provider/hash tuple. The lease must also find the same owner's reservation with the exact retained ZIP byte count and no conflicting existing message projection. A live lease is not stolen. A terminated isolate leaves durable intent; a later attempt can reclaim after expiry.
3. Every staging DELETE/INSERT and every final batch statement rechecks the exact accepted journal, opaque token, unexpired lease, owned reservation and compatible existing projection **inside its SQL statement**. A prior SELECT is not authority. D1 serializes a late write either before a new claim/terminal transition, or after it, when the stale token/state fails.
4. One fenced DELETE removes invalid/stale extra indices before rewriting deterministic UTF-8 chunks. This permits repair when an old compiler left more chunks than the current compiler generates. All expected positive indices are rewritten; the primary key and exact cardinality/range check prove no missing or extra indices at publication. There is no durable chunk cursor or deadline exit in this repair.
5. A three-statement D1 batch publishes/upserts the message body prefix, indexes the reservation and moves the exact journal to `sent` while clearing the token. Existing `is_read` and `deleted_at` are never assigned by the upsert. A repaired live legacy projection clears all old vector metadata; a migration trigger revokes/recreates its embedding work so an old in-flight embedding lease cannot commit stale text. New inserts retain migration 0007's original enqueue trigger. The trigger actions are in the same publication transaction, not extra submitted D1 statements. All three batch statements use one captured lease-clock snapshot. A tombstone can terminalize without restaging its deleted body. The final transition additionally requires the matching ledger to be indexed; an ignored/mismatched INSERT or UPDATE cannot authorize completion.
6. All three result objects must report success and the final conditional transition must change exactly one row. An all-no-op batch is not success. The only alternative success proof is an exact journal already at `sent`, which resolves a concurrent winner or an ambiguous completed publication even after GC has removed a deleted row. HTTP therefore truthfully returns the established `202 accepted` after Cron won; it does not reopen the mail.
7. Known projection errors best-effort release only this attempt's token, permitting immediate safe repair without waiting 20 minutes. If release fails or the isolate terminates, expiry is the fallback. Release is never a provider retry. A queued old staging statement after release sees a missing/replaced token and cannot write.

The [official D1 batch contract](https://developers.cloudflare.com/d1/worker-api/d1-database/) guarantees ordered transactional execution and rollback on a statement error. Batching improves atomicity and round trips, **not** the number of submitted SQL statements. [D1 limits](https://developers.cloudflare.com/d1/platform/limits/) include a whole-batch duration bound: a lease is not permission to run an unbounded transaction. Resolved [workers-rs 0.8.7 D1 bindings](https://github.com/cloudflare/workers-rs/blob/v0.8.7/worker/src/d1/mod.rs) expose batch result order, success and conditional change counts.

## Legacy states, readers and deletion

Existing live partial rows whose matching owner journal is still accepted are hidden from metadata fetch, archive fetch, search scanning, summary rehydration and embedding due/claim/content reads. They become visible only with the successful journal transition. A previously learned ID can still be deleted: the owner-scoped conditional tombstone update does not require the now-hidden row to pass the public read query. Unowned or already absent/deleted IDs retain their not-found response.

Deleted-message GC excludes any row with an accepted send journal. It cannot erase the tombstone or original ZIP before recovery terminalizes. The existing orphan collector already preserves accepted/submitting/unknown reservations. The shared token/state fences also stop a delayed foreground projector from inserting chunks after `sent` and subsequent physical GC.

Foreign message or reservation collisions are refused, not overwritten. Body/read/delete mutations cannot be inferred from the mere existence of a message ID. Restricted envelope repair is still owner/key/provider/hash scoped and respects the existing 90-day retention; no mail content, SQL, identity or provider error body is logged by this helper.

## Rollout and liveness assumptions

Apply migration before deploying code. Drain old **unfenced** Worker revisions and do not serve a mixed old/new rollout before relying on this invariant: a token cannot constrain code that never checks it. After all serving revisions use the token contract, different compiler revisions cannot mix chunk prefixes because only the current lease holder can stage or publish. A new holder rewrites all indices and the prefix before publication.

The platform clock supplies durable expiry. Forward clock movement can defer a running holder; backward movement can prolong recovery. The 20-minute value is a finite configured retry window under a progressing platform clock, not a formal wall-time guarantee under arbitrary clock changes. A new holder's UUID, rather than timestamp uniqueness, fences old work.

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

The outbound phase setup still submits two statements. A proposed five-item phase would therefore have normal upper bound `2+5*72=362`, giving the earlier loose full-Cron normal model **734**, not 729. An all-no-op late final batch can additionally require one exact-sent read and one failed-attempt lease release: conservative per-item submitted-call bound **`k+8<=74`**, five-item outbound **372**, corresponding combined loose bound **744**. Failed calls remain submitted statements; no refunds are assumed. Existing twenty-item source behavior remains unsafe under the documented 1,000-query invocation ceiling. These are source ceilings, not measured database/provider enforcement or CPU/RSS.

## Hosted acceptance evidence required

Use the real built Rust/Wasm entry, isolated native D1/R2, synthetic ZIPs and controlled synthetic I/O on GitHub-hosted runners only. No production test hook is added. Independent validator artifacts provide the initial stored-ZIP and post-accepted HTTP/Cron harnesses; their exact branch commits must be recorded with eventual run URLs.

| Interleaving/fault | Required observation |
|---|---|
| Exact 4,000,000-byte text plus replay | 67 exact pieces, one delivery, stable quota/IDs; provider never resubmitted |
| Fault on chunk 3, then repair | Accepted and invisible, at most two staged chunks; eventual byte-exact publication |
| Error in final sent transition | Entire three-statement publication rolls back; retained accepted ZIP/ledger repairs later |
| Legacy live partial row | No get/archive/search/embedding exposure while accepted; prefix/chunks repaired before sent |
| Existing or newly arriving user tombstone | Never cleared, never reappears; accepted-aware GC waits until terminalization |
| Foreign existing message/reservation | No foreign body/chunk change and no journal terminalization |
| Fresh live lease | Competing projector writes nothing; original holder remains authoritative |
| Expired lease and stale-token statement | New holder replaces token; every old staging/final statement becomes a no-op |
| Foreground accepted UPDATE paused before claim | Cron publishes; public delete plus real GC finishes; resumed HTTP returns same-ID 202 and writes nothing |
| Legacy vector and old leased embedding work | Vector metadata invalidated, work freshly queued; an old embedding lease cannot commit after repair |
| Older extra chunks / shorter new body | Stale suffix removed under lease; exact current compiled body and original mutable read/delete flags |

Only static Rust formatting/parsing and `git diff --check` were run locally. No runtime result is asserted here.
