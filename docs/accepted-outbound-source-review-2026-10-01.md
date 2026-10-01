# Accepted outbound projection source review

Reviewed original source `289d1bf067211d16ecced5f38c3fc1caec5453f3` against parent `ea54512`, then corrective source `0fa2a9fa1d5c9c43640ed840279761367400925d`, and rebased followup source `f4bba05` on current main `f10af796`. Date: 2026-10-01. Independent static review only: no local build/test, provider operation, deployment, or source modification. Hosted acceptance tests were not yet integrated at review time.

## Verdict

**GO for exact nondeploying hosted CI on corrected followup source `f4bba05`; no unresolved substantive source defect found within this review scope.** Original `289d1bf` was NO-GO for complete integrity acceptance because of the derived-index defect below. That finding is now resolved in source, pending hosted regression evidence. This is not deployment admission or a claim that unexecuted tests passed.

## Resolved P1: Repaired body retained a vector for the old body

Location: `crates/mail-worker/src/accepted.rs`, `message_statement`, `ON CONFLICT(id) DO UPDATE SET body_text=excluded.body_text` (lines 158–159).

A legacy accepted partial message can already contain a compatible semantic vector: the old Cron exposed the message row before its journal reached `sent`, and automatic embedding ran independently. The new repair intentionally supports different compiler revisions and rewrites the retained ZIP's compiled body prefix. When the repaired prefix differs, the upsert changes `body_text` but leaves `embedding_json`, model, dimensions, input version, and any embedding work state untouched. The existing migration 0007 queue trigger runs only on INSERT; its finished trigger removes work after vector completion. Semantic search trusts model/256/input-version compatibility and has no text fingerprint. Once the final journal transition publishes the row, exact body search and semantic search refer to different documents indefinitely.

A pending/quarantined or previously leased legacy embedding-work row is another version of the same issue. Simply setting the vector to NULL is insufficient: it does not insert absent work, reset quarantined work, or revoke a token for an in-flight old-input provider response. `persist_embedding_success` checks the work token but not the actual input bytes.

Correction: within the final publication transaction, invalidate the derived vector and requeue owned work whenever its canonical embedding input changes, revoking any old work lease/token. An always-reset accepted legacy projection is a simpler conservative alternative if it preserves tombstones and owner guards; do not reset already-sent rows or reprocess tombstones. Migration triggers or an additional fenced publication statement may express this contract, but then update statement accounting and atomic-batch tests accordingly. Preserve user read/deletion state.

Hosted regression: seed (1) a compatible old vector with no work; (2) quarantined old work; and (3) a leased old work token. Repair a different body prefix from the exact committed ZIP. Require canonical byte-exact body, missing vector plus pending work, and a late success using the old token to change zero rows. Then build a new vector from the repaired input. No live third-party model request is needed.

Confidence: high; this is an executable source/trigger interaction, not a speculative model-quality objection.

### Corrective source review

`0fa2a9f` conservatively clears all five vector provenance fields in live accepted conflict publication. Migration 0010 adds a matching accepted-owner outbound body-update trigger: delete any previous work (and its lease/token), restore owner scheduling, and insert fresh default-pending work in the same publication transaction. Existing migration 0007's finished trigger sees `NEW.embedding_json IS NULL` and `NEW.deleted_at IS NULL`, so it does not remove the new work regardless of trigger order. Work deletion's owner-cleanup trigger may remove an empty owner schedule, which is immediately restored. A late old-input vector response cannot satisfy its revoked token. Fresh INSERT still uses the original insert trigger; tombstone conflict publication performs no UPDATE and creates no work. A failed final sent statement rolls all message/vector/work changes back together.

The amendment also gives all three final statements one clock snapshot, preventing distinct pre-submission times from making only an earlier statement pass the lease predicate.

Current code requires exactly-one changes only for journal claim, chunk writes, and final sent UPDATE. Those tables have no relevant update triggers in the inspected migrations; the message UPSERT checks success rather than exactly-one changes. Therefore additional message-trigger effects do not enter the sent proof. [D1 return-object documentation](https://developers.cloudflare.com/d1/worker-api/return-object/) does not explicitly distinguish trigger changes from direct changes; hosted native D1 tests should still verify exact claim/sent counts rather than assuming undocumented trigger accounting.

### Identical-chunk retry metadata acceptance

Earlier `stage` broke its loop when a successful chunk upsert did not report exactly one change. [SQLite UPDATE semantics](https://www.sqlite.org/lang_update.html) affect matched rows; [SQLite changes API](https://www.sqlite.org/c3ref/changes.html) counts direct UPDATE effects and excludes trigger side effects. The [SQLite project forum clarification](https://sqlite.org/forum/info/7f9cfd47e9b15549) explicitly says an equal-value update still increments the change count. There was thus no demonstrated SQLite equal-value defect, but the D1 return-object contract does not explicitly promise this detail. Followup `f4bba05` removes this unnecessary progress dependency: stage continues after every successful bounded upsert, and final fenced readiness alone decides publication. This is coherent even after a lost lease or intervening tombstone: subsequent statements become no-ops and cannot publish without authority. Hosted fault-on-chunk-three followed by exact-byte retry remains required evidence.

### Surviving legacy tombstone without retained ZIP

Old GC could remove R2 ZIP bytes and then fail before deleting the tombstone. Followup `f4bba05` recognizes only an owned outbound tombstone whose message ID, provider metadata and canonical R2 key agree with the accepted journal. Its stored byte count feeds the same exact reservation ownership guard. It claims the shared token lease, then uses a two-statement ledger/sent batch whose SQL rechecks journal identity, token, reservation and surviving deletion. No body/chunk INSERT is involved. Only the final changed journal or the exact already-sent proof authorizes success; archive absence alone does not.

This terminalization is correct whether the deleted archive still exists or was already removed: deletion intent means no reconstruction is needed. Existing accepted-aware GC keeps the tombstone until terminalization; normal GC subsequently releases chunks, bytes and reservation. The inspected legacy GC deletes R2 before the message and reservation, supporting this specific surviving-tombstone state. Missing reservations or foreign/live message collisions fail closed; an already physically removed tombstone is not manufactured from a missing archive.

Required hosted additions: surviving owned tombstone with no ZIP terminalizes without provider/body/embedding call; foreign-owner, mismatched provider/key/bytes, absent reservation and live-message/no-ZIP cases do not; two-statement terminalization rollback preserves accepted state; actual subsequent GC removes only the owned deleted delivery. No such runtime result was asserted by this review.

## Assessed and not raised as defects

- HTTP and Cron now share a token-fenced owner/hash/provider/storage publication path. Each staging and final statement checks journal authority inside SQL; an old token or terminal journal cannot resurrect chunks after sent/deletion/GC.
- The final three statements run in a D1 batch. Official D1 documentation guarantees ordered transactional execution and whole-sequence rollback on a statement failure; all-no-op completion is separately checked through the exact sent journal.
- Ready cardinality/range checks plus rewriting every expected index avoid missing/stale suffix chunks under exclusive token ownership. Empty text has a valid prefix; maximum service-valid four-million-byte drafts are not narrowed to a CLI-only cap.
- Accepted-aware tombstone GC and reservation preservation protect retained archives until terminalization. Delete by known owned ID still works for hidden legacy projections.
- Migration 0010 is additive. The documentation correctly requires applying migration first and draining old unfenced serving versions. Mixed old/new serving is **not safe**, because old code ignores the new token; this is an explicit rollout precondition, not a guarantee this commit implements.
- Current LIMIT 20 Cron statement-budget/fairness and maximum-draft runtime admission remain separately unresolved. The source document explicitly avoids claiming this repair fixes them.

## Primary references checked

- [Cloudflare D1Database batch API](https://developers.cloudflare.com/d1/worker-api/d1-database/): ordering, result positions, and transaction rollback.
- [Cloudflare Workers limits](https://developers.cloudflare.com/workers/platform/limits/): scheduled invocation duration assumptions; the lease is not a runtime/resource allowance.

## Limits and required next evidence

This is not a runtime proof. Real built Rust/Wasm hosted cases must cover chunk-write failure, final-transaction rollback, fresh/expired/stale lease, cross-path delayed HTTP after Cron/delete/GC, legacy partial visibility, foreign storage/message guards, exact maximum body, and the derived-index regression above. Record exact final source/test SHA and run URL. No privacy, live provider, production rollout, CPU/RSS, or full-Cron budget gate was verified here.
