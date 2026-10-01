# Accepted outbound recovery: independent adversarial validation plan

Date: 2026-10-01. Source basis: origin/main `c6f93bf4cadbb58c69027ebc6208d594ca713c80`.
Status: **static derivation and runnable hosted reproductions only; not execution evidence**.

## Contract and isolation

Provider acceptance is a durable fact, not permission to send again. Local projection must converge exactly without charging storage twice, resurrecting user-deleted content, or monopolizing a bounded maintenance window. A service-valid ZIP/body must not be rejected or permanently retried merely because its searchable projection has many chunks. These expectations come from the product's send/delete/search behavior and durable accepted state, not from the current implementation's selected SQL.

`infra/tests/worker-boundary/outbound-recovery.test.mjs` runs the built Rust/Wasm scheduled handler in workerd with production D1 migrations, synthetic R2 archives, and a strict network interceptor. Only an empty synthetic route inventory is permitted; unexpected network requests throw. The semantic dependency is deliberately blocked for one day so no content leaves the fixture. ZIPs are independently encoded standard Stored entries with CRC32; no production archive packer is reused.

The new file is intentionally not added to the default pnpm test command. Known-contract failures remain ordinary assertions, not TODOs or assertions that endorse the current defect. An implementer should run this in a focused hosted CI lane before merging its corresponding repair. No provider call, deployment, project build, or project test was run locally.

## Cases and expected outcomes

| Case | Independent expected result | Static source assessment, not observed |
| --- | --- | --- |
| Decimal 4,000,000-byte text, valid Stored ZIP | Exact reassembled body, 66 extra chunks, sent state, replay keeps one message and unchanged storage charge | Expected to pass absent runtime budget failure |
| Chunk 3 fails, then fault is removed | Accepted state remains and no message is published; zero to two extra chunks may remain depending on rollback/cleanup; next invocation repairs all chunks exactly, without resend | Expected to pass; writes are replace-idempotent |
| Existing user tombstone | Recovery cannot make message searchable; GC may collect it | Expected to pass because INSERT OR IGNORE preserves existing deleted_at |
| Twenty missing archives, then valid accepted item (documented workload only) | Later item receives service within the explicitly chosen scheduler cap/cadence/backoff bound | Original LIMIT20 can repeatedly select the same unavailable records; no executable tick-count assertion is retained |
| Surviving exact-owned accepted tombstone with archive | Terminalizes without body chunk staging; remains invisible; subsequent GC removes all content and ledger | Original recovery re-stages text; repaired source short-circuits to deleted finalization |
| Twenty decimal4MB accepted archives | Extra chunk writes alone do not exceed the whole 1,000-query Paid allowance | Expected to fail if fixture runtime permits the full loop; 1,320 extra chunk writes alone |
| Delete after INSERT, before sent transition | Delete remains authoritative on subsequent maintenance | Expected to pass for this barrier; does not cover a separate in-flight HTTP writer |

The earlier pre-existing tombstone plus first-chunk GC trigger was not a valid cached-R2 concurrency test against the repair: deleted finalization short-circuits before any chunk insert, so the supposed barrier would never execute. It has been replaced with the narrow surviving-tombstone contract above and an explicit audit asserting **zero** new staging inserts. Concurrent GC after an active projector has cached its R2 bytes remains untested by this case. The separate HTTP/Cron/public-delete/real-GC fixtures cover their documented interleavings, not arbitrary mid-projection GC.

The budget test records inserted extra chunks, a rigorous lower bound, not a full D1 query counter. If workerd itself aborts at its query ceiling before 1,000 extra chunks, this particular assertion can pass without demonstrating budget-aware progress. That outcome requires examination of pending states/diagnostics; a pass is not Paid-safe acceptance. All combined Cron phases still need a real invocation counter and workload-specific bound.

## Exact arithmetic

Current `text_parts` uses <=60,000-byte values. For decimal4MB ASCII:

- `ceil(4,000,000 / 60,000) = 67` parts; the first is stored in messages, 66 extra chunk INSERTs.
- One recent accepted item performs metadata UPDATE +66 extra chunk INSERTs +message INSERT +storage ledger UPDATE +send-state UPDATE = **70 D1 statements**.
- Two shared outbound setup statements +20*70 = **1,402 outbound D1 statements**, excluding all other Cron phases.
- Binary4MiB would instead be 4,194,304 bytes, 70 parts and73 statements/item; it is not the fixture or the cited decimal4MB workload.

The fixture's Stored ZIP is less than5MiB and expanded content less than12MiB. It deliberately exercises service-valid content rather than a ZIP bomb or oversized request.

## Separate HTTP post-acceptance writer race: still unexercised

Required discriminating interleaving:

1. HTTP `/v1/send` receives a provider acceptance and durably records accepted state.
2. Hold its execution before local projection (including before extra chunks/message INSERT).
3. Dispatch Cron; allow it to finish projection and terminalize the accepted record.
4. Delete the message through the public owner-authorized API and run real GC to remove archive/message/chunks/ledger.
5. Resume the old HTTP invocation.
6. Assert no message/chunk/embedding work/reservation resurrection; no second provider send; the old HTTP result follows the established post-acceptance outcome contract.

This cannot currently be truthfully represented by the existing `outboundService` interceptor alone: provider send uses the newer Worker EmailService `binding.send_with_builder`, not an HTTP fetch. A synthetic EmailService binding and a precise execution barrier must be supported by the hosted harness (or a test-only generated shim wrapper reviewed for correct platform behavior). Do not claim the Cron-only SQLite trigger above verifies the HTTP race. No production test hook or alternate production send implementation has been added.

## Reproduction and evidence

Hosted runner, Node22, repository-locked Miniflare4.20260730.0, supported compatibilityDate2026-08-06, after the existing CI Wasm build/bundle:

```sh
cd infra/tests/worker-boundary
pnpm install --frozen-lockfile
node --test outbound-recovery.test.mjs
```

Local permitted static checks completed:

```sh
node --check infra/tests/worker-boundary/outbound-recovery.test.mjs
git diff --check
```

Both succeeded. No runtime verdict has been obtained. Source repairs should be tested with this file against both original and corrected built artifacts to demonstrate regression sensitivity, then followed by a real staged workflow only after release/privacy admission gates are satisfied.

## Additional publication-integrity regressions

Added before execution: a foreign storage reservation must refuse publication; a foreign existing message ID must retain exact original content and must not terminalize the unrelated accepted journal; failing the final sent transition must atomically roll back the new message and indexed storage state, leaving accepted recovery retryable. The final rollback fixture checks raw D1 publication absence rather than relying on a read API that might hide a still-present partial row. All three are normal contract assertions and statically expected to fail the original source. The late same-journal **HTTP** writer after sent/delete/GC remains assigned to the separate EmailService barrier harness; no direct invocation of internal production helpers is used as a substitute.

## Independent test-contract refinement

The partial-chunk fault assertion allows zero through two staged rows rather than requiring exactly two orphan rows. Retaining these rows is not a product contract: atomic rollback or safe cleanup may remove them. Accepted-state durability, absence of a visible message, and exact eventual retry remain mandatory; the chunk-three barrier still prevents more than two successful staging writes. This is a test-only correction, not a weakened publication or retry guarantee. The HTTP EmailService execution-barrier gap remains unchanged.

## Fairness workload: bound awaits scheduler contract

The original three-immediate-tick assertion was removed. It coupled fairness to the old LIMIT20 and would incorrectly reject a legitimate LIMIT5 scheduler with future retry deadlines. The workload remains twenty unavailable accepted archives followed by one valid accepted archive, with no new arrivals. For a chosen cap K and retry cadence/backoff, derive the finite service bound from those parameters and control the hosted clock; verify the unavailable records rotate and the valid one converges within that bound. For example, ignoring other priorities, scanning 21 initially due entries with K=5 needs up to five service turns, not three; immediate dispatches are not service turns if retry deadlines are still in the future. Neither a fixed number of rapid retries nor a passing short queue proves fairness. No runtime fairness verdict is claimed, and the present standalone executable file now has nine tests.

## Fixture authenticity

Accepted journal seeding now records the real SHA256 commitment of the independently encoded archive, matching the HTTP admission invariant rather than using a placeholder hash. Reservation bytes already equal actual ZIP bytes. Existing owned tombstones are obtained by completing real recovery before deletion, so their provider metadata is production-generated; the foreign-row fixture intentionally remains foreign and must be refused, not normalized into an owned projection.

## Deterministic HTTP fixture implementation (not yet executed)

A separate `accepted-http-cron-race.test.mjs` and test-only `accepted-race-entry.mjs` implement the documented after-acceptance barrier, plus an independent Stored ZIP helper. The test copies its adapter under the existing built module root on the hosted runner; production shim, Wasm, and Rust source are not edited. The adapter subclasses the actual default WorkerEntrypoint and proxies only the exact acceptance UPDATE's native `.run()` return. All native D1 operations complete normally before the barrier is signaled. EMAIL uses a synthetic `.send(builder)` returning a fixed messageId; real Rust builder conversion remains active.

Two tests distinguish (a) Cron projection followed by resumed HTTP plus replay and (b) Cron projection, public owner-authenticated DELETE, real GC, then resumed HTTP plus replay. Before Cron, both assert the acceptance row is committed, the original R2 archive exists, and no message or chunks have been projected. Afterwards they require exactly one provider invocation, stable message ID/202 outcome, and either exact single projection or complete absence of resurrected message/chunks/reservation/embedding work/storage charge.

This barrier occurs **before HTTP acquires a projection lease**, not while HTTP holds one. Therefore Cron winning first does not assume or demand that it steal an active lease. It covers a writer that has cached its ZIP but has not acquired publication ownership. A second future fixture must pause after successful HTTP projection-lease acquisition, verify immediate Cron defers, advance the test clock past the specified20-minute lease expiry, let Cron acquire a different token, then resume old token writes and prove they cannot publish. That active-lease expiry/stale-token path remains unexercised; no rapid repeated ticks substitute for elapsed time.

Static syntax checks passed for all three new modules. The generated subclass/native D1 Proxy combination still requires hosted contract smoke before either race test can be called executed or verified. Run separately after worker-build:

```sh
node --test accepted-http-cron-race.test.mjs
```

No test has been added to the default suite and no runtime execution has occurred locally. The original source is statically predicted to return `send_index_pending` after Cron already inserted its projection, and to republish a message after the delete/GC interleaving; these are predictions, not observed results.

## HTTP harness independent-review corrections

Both control and external-network handlers now count and reject unknown method+URL before an assertion can throw and be swallowed by production error handling. Native storage reservation and per-owner usage snapshots taken before HTTP resumes are compared after same-ID replay and one additional real Cron dispatch. This makes no-double-charge persistence an observed contract assertion rather than inferring it from a single message row. Static syntax/diff checks only; hosted execution remains pending.

## Lease, legacy projection, and surviving deletion-intent cases

The budget lower-bound reproduction is now isolated in `outbound-recovery-budget.test.mjs`; reusable synthetic setup is in `outbound-recovery-fixture.mjs`. Budget/fairness cases remain outside the default integrity suite and are not claimed fixed by publication repairs.

Three more integrity fixtures are added: (1) a fresh twenty-minute projection lease blocks Cron, then explicit stored deadline expiry allows repair and terminal cleanup; (2) a production-generated legacy projection changed back to accepted with a stale compatible256D vector, an old in-flight embedding lease, an obsolete text prefix/suffix, and unread state must repair exact text, retain unread, clear all vector metadata, regenerate clean work, and refuse an old-token SQL commit; (3) an exact-owned surviving tombstone with an already-deleted ZIP must terminalize without parsing/resending content, then GC completes cleanup. The tombstone case does not manufacture deletion intent when both ZIP and message are absent.

The embedding late-commit assertion directly exercises the durable old-token fence, not the whole delayed OpenRouter invocation. The lease fixture models expiry by changing the persisted deadline; it does not claim to test real clock waiting or an actually paused old projector. A dedicated HTTP barrier after real lease acquisition is still needed for that async stale-writer proof. New schema-specific cases require migration0010 and cannot be used unchanged against the historical nine-migration artifact.

## Actual stale HTTP projection token fixture

A third HTTP race now pauses after the native projection CAS claim commits (matching its fixed normalized SQL prefix). It asserts the original token and future deadline are present; immediate Cron must leave both unchanged and publish nothing. The fixture then expires only the persisted deadline, dispatches Cron, asserts a second successful claim, completes projection/public delete/real GC, and resumes the real old HTTP projector. Exact absence of resurrection, single provider send, accepted replay, and unchanged storage remain required. This replaces the previously planned async stale-projector gap with an **implemented but still unexecuted** hosted fixture; actual20-minute wall-clock expiry behavior is not tested. The first two acceptance-only race cases do not select migration0010 lease columns, allowing original nine-migration artifact reproduction by name selection. New lease/legacy tests do require the migration.

## Vacuous barrier correction

Removed the unreachable `gc_barrier` trigger and renamed the case truthfully to owned accepted tombstone with an existing archive. It now verifies sent state, invisibility, zero new body chunk staging via an actual trigger audit, and complete subsequent GC cleanup. The ZIP-less surviving-tombstone case remains separate. No claim is made that these cases exercise cached-R2 concurrent GC during active projection. Static syntax and full-branch diff checks only; runtime evidence remains pending.
