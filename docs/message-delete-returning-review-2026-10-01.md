# Owner delete result authority review

Date: 2026-10-01. Hosted failure: [PR22 run 36804402543](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36804402543). Static source and hosted log review only; no local project test/build/provider operation.

## Demonstrated failure and mechanism

Two built Rust/Wasm HTTP-vs-Cron tests prove Cron reached exact `sent` journal plus one live message, then the owner's public DELETE returned 404. `delete_message` performs a successful owner-scoped conditional tombstone UPDATE but accepts only `meta.changes == 1`.

The exact pinned [Miniflare 4.20260730.0 D1 implementation](https://raw.githubusercontent.com/cloudflare/workers-sdk/miniflare@4.20260730.0/packages/miniflare/src/workers/d1/database.worker.ts) uses before/after SQLite `total_changes()` deltas (lines 114–154), not direct-statement `changes()`. Migration 0007's `messages_embedding_finished` deletes pending embedding work on tombstoning, and `embedding_work_owner_cleanup` may also delete its empty owner schedule. Hence one successfully deleted message can produce a count greater than one. The handler then emits false 404 **after committing deletion**. The test-only shim passes this SQL and metadata unchanged; no demonstrated route or ownership mismatch explains this failure.

The standalone recovery fixture's separate `send_held` failures occur during synthetic journal seeding and do not establish a production projection defect.

## Recommended correction

Use the same owner-scoped, not-already-deleted UPDATE with `RETURNING id`, then execute through D1 `.first()` and use returned-row presence as authority. This stays one statement and avoids a precheck race. First owned deletion returns established 204; foreign, missing and already-deleted IDs return established 404. Known owned hidden accepted partial rows remain deletable. Do not replace the guard with unconditional success or infer ownership from a post-update unscoped read.

[SQLite RETURNING](https://www.sqlite.org/lang_returning.html) reports rows affected by the outer statement, rather than counting trigger changes. [D1 prepared statement `first`](https://developers.cloudflare.com/d1/worker-api/prepared-statements/) executes the query without rewriting it and returns a row or null, without metadata. Hosted built-worker validation remains necessary for the combined API path.

## Acceptance requirements

- Owned live row with pending embedding work and last owner-schedule row: DELETE 204, work/schedule removed, one tombstone.
- Owned live row with no work: DELETE 204.
- Repeat deletion, missing ID and another owner: DELETE 404; no foreign state mutation.
- Hidden owned accepted partial row: DELETE 204, recovery never resurrects it.
- Existing two HTTP/Cron/delete/GC races pass through real public DELETE and real GC.

## Exact corrective source review

Reviewed commit `215ed3c5e4b39bfb431f8043bf156c2fd82a9925`. The source adopts the recommended one-statement owner/live UPDATE RETURNING and `.first<Value>` row-presence decision. It returns 204 only for its matched message, without restoring a racy precheck or exposing the hidden legacy partial row. Foreign, absent and already-deleted predicates remain false. No substantive source defect was found in this focused correction.

The hosted race tests now explicitly establish the target's exact owner and live state, pending embedding work, foreign-identity 404 without mutation, committed tombstone with 204, and repeated-delete 404 with unchanged timestamp. Additional variants exercise no embedding work and a hidden accepted journal projection. The hidden projection variant is coherent with current Cron ordering: outbound terminalization precedes GC, allowing actual deletion in the same scheduled turn. Tests retain the original delayed-HTTP/token races and real GC rather than weakening them to direct database deletion. A dedicated missing-ID assertion would be useful but is not a blocking gap given the unchanged exact predicate.

**Verdict: GO for nondeploying exact hosted CI after integrating reviewed fixture setup.** Original false-404 P1 is resolved in source; hosted combined acceptance is pending. No production deployment/privacy/provider/resource-budget gate is approved here.
