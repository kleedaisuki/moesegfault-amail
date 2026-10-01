# D1 trigger-inclusive change-count audit

Date: 2026-10-01. Independent static review of Mail main `d3e99c090288ef5953d38d0ad82eeac4846e68b3` and PR #22 candidate `25acdf1a160a3a57656e8e7bf43ce1007d3f9e9c`. Scope: Rust Worker decisions based on `D1Result.meta.changes`, and matching triggers/foreign-key actions in migrations 0001–0010. No production edits, local project build/tests, provider operation, deployment, or push. Line numbers below refer to PR #22 candidate unless noted.

## Verdict and necessary correction

**One P1 defect found: PR #22 acknowledges successful message deletion as 404.** No second trigger-count defect was found among the other 16 inspected metadata-count decision sites. They should not be mechanically rewritten on the strength of this finding.

### P1: Successful tombstone is rejected as not found

Location: `crates/mail-worker/src/lib.rs:1872–1878`, `delete_message`.

The exact statement updates an owned, previously live `messages` row's `deleted_at`, then requires `meta.changes == 1` before returning 204. Migration `0005_search_jobs.sql:16–19` has an unconditional `AFTER UPDATE ON messages` trigger that inserts/updates one owner `search_generations` row. Thus the direct update plus search invalidation already modifies two rows when metadata is measured by a per-statement `total_changes()` delta. Migration `0007_embedding_work.sql:63–76` can additionally remove the message's embedding work and its now-empty owner schedule: the normal count is 2, 3, or 4, not 1. This applies even to a fully indexed message with no remaining work, not only accepted recovery or legacy rows.

Impact: the tombstone commits and hides mail, but the owner receives 404; a retry cannot succeed because the row is already deleted. This violates the CLI/API acknowledgement contract and breaks the hosted deletion/race acceptance path. Main's prior implementation did not inspect deletion metadata, so this is introduced by PR #22, not an existing main regression.

Evidence: [hosted run 36804402543](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36804402543) used this exact candidate and pinned `miniflare` `4.20260730.0`; both late-HTTP projection tests fail with `owner delete failed: 404`. The parent investigation established trigger-inclusive pinned Miniflare accounting; this review independently maps the source path and unavoidable generation trigger. This review does not claim a live remote D1 reproduction or that other failing cases in the run share this cause.

Preferred correction: keep the atomic owned/live conditional UPDATE and append `RETURNING id`; use a successful native D1 result's returned direct-row presence/cardinality as the proof. Keep the owner predicates and `deleted_at IS NULL`; absent/already-deleted/foreign IDs should still yield 404. A bounded `.all()` result and exactly one returned ID avoids relying on trigger metadata. Do not remove generation invalidation or embedding cleanup, pre-read then unconditionally acknowledge, subtract guessed trigger counts, or accept unrelated trigger-only changes. For this exact statement alone, a positive metadata count would currently distinguish a direct match, but RETURNING expresses the intended direct-row contract and is safer against future schema changes.

Hosted regression should cover: (1) indexed message without work; (2) pending work shared with another owner-work row; (3) last pending work for its owner; (4) hidden owned accepted tombstone admission; (5) foreign/missing IDs and repeated delete; and retain the actual HTTP→Cron→delete→GC race assertions. Require first owned delete 204 plus tombstone/queue cleanup, while zero direct matches remain 404. No live third-party request is required.

Confidence: high; source proof plus hosted failure. Release correction required before accepting PR #22.

## Exhaustive metadata decision inventory

| Location | Exact target/operation | Applicable write trigger | Assessment |
|---|---|---|---|
| `lib.rs:324–326` | `addresses` due-time conditional UPDATE | None | Safe current-schema one-row claim. |
| `lib.rs:476–478` | `addresses` provisioning→active UPDATE; checks zero | None | Safe zero-match classification. |
| `lib.rs:754–771` | `embedding_work` lease UPDATE | None; owner cleanup applies to DELETE only | Safe one-row lease claim. |
| `lib.rs:1208–1210` | `daily_usage` conditional INSERT/UPSERT | None | Safe one-row quota admission. |
| `lib.rs:1555–1557` | `addresses` pending→provisioning UPDATE | None | Safe one-row provider-operation claim. |
| `lib.rs:1633–1636` | `addresses` provisioning→active UPDATE; checks zero | None | Safe zero-match classification; exact row readback separately confirms activation. |
| `lib.rs:1873–1875` | `messages` live→tombstone UPDATE | Search generation, embedding finished, nested owner cleanup | **P1 above.** |
| `lib.rs:2343–2345` | `send_requests` preparing→reserving UPDATE | None; request admission guards apply to INSERT only | Safe one-row quota reservation claim. |
| `lib.rs:2485–2487` | `send_requests` preparing→submitting UPDATE | None | Safe one-row provider-call claim. |
| `search_jobs.rs:475–484` | `search_jobs` bounded conditional INSERT | None | Safe quota/generation admission. |
| `search_jobs.rs:533–536` | `search_jobs` preparing→running UPDATE | None | Safe state transition. |
| `search_jobs.rs:633–638` | `search_jobs` running→advancing version CAS | None | Safe one-row lease claim. |
| `search_jobs.rs:790–815` | `search_jobs` advancing→done UPDATE (both cursor variants) | None | Safe one-row checkpoint proof. |
| `search_jobs.rs:827–831` | `search_jobs` advancing→running version CAS | None | Safe one-row checkpoint proof. |
| `accepted.rs:204–216` | Exact `send_requests` accepted projection lease UPDATE | None | Safe one-row claim. |
| `accepted.rs:274–287` | Final batch's `send_requests` accepted→sent UPDATE for tombstone | None | Safe current-schema journal proof; preceding ledger UPDATE has no UPDATE trigger. |
| `accepted.rs:322–334` | Final batch's `send_requests` accepted→sent UPDATE after message publication | None | Safe current-schema journal proof. Message UPSERT trigger effects belong to that statement; its metadata is not used as direct-row proof. |

There are 17 decision sites (including two zero-count classifications); 13 existed on main, and PR #22 adds deletion plus three accepted-helper sites. No foreign-key cascading action is defined for these targets. `messages` references addresses without an ON DELETE/UPDATE cascade; addressing uses persistent retirement rather than changing/deleting the key. SELECT subqueries inside CAS predicates do not run table write triggers.

## Trigger-heavy paths deliberately not findings

- `mark_message` updates `messages.is_read`, triggering search invalidation, but does not interpret its count; it returns an owned fresh read.
- `persist_embedding_success` conditionally updates `messages.embedding_json`, triggering search invalidation and work cleanup, but does not require one metadata change. Lease claim is an UPDATE of `embedding_work`, not its trigger-bearing DELETE.
- Message INSERT/upsert, accepted projection body repair, storage-reservation INSERT/DELETE, and GC message DELETE can change several trigger rows. Their metadata is not used as one-row success proof in these paths.
- New send-request INSERT can consume a held canary and audit release gates via migration 0006; `send_message` checks admission error, not `changes == 1`. Existing send-request UPDATE claims do not fire those INSERT guards.
- Provider-event INSERT can update outcomes/holds/blocks and audit policy, but no Rust Worker count decision was found on that operation.
- Role-contact policy/health and release-gate triggers are substantial, but their operator scripts are outside this Rust Worker audit; no assertion about script accounting is made here.
- PR #22 message publication deliberately uses result success, not its trigger-heavy upsert count. Final sent proof remains on trigger-free `send_requests`. No evidence supports calling preceding message trigger effects a cumulative batch-counter defect.

## References and limits

- [SQLite total changes](https://www.sqlite.org/c3ref/total_changes.html): includes changes inside trigger programs and foreign-key actions. A raw connection total is cumulative; the pinned harness observation concerns a per-statement delta, not unbounded cross-statement totals.
- [SQLite RETURNING](https://www.sqlite.org/lang_returning.html): emits direct modified rows, not trigger/foreign-key auxiliary writes. Return only the bounded ID, not mail content.
- [D1 return object](https://developers.cloudflare.com/d1/worker-api/return-object/): remote metadata must not be assumed to be a stable direct-row identity oracle. This audit does not generalize the hosted Miniflare observation into an independently measured remote behavior.

The audit is specific to current migrations and the candidate SHA. Future triggers on current no-trigger claim tables require revisiting their metadata proof. It is not full correctness, concurrency, budget, privacy, schema-rollout, or live-deployment certification. No academic literature is needed to adjudicate this concrete SQLite/API contract defect; primary implementation semantics and executed boundary evidence are the relevant authority.
