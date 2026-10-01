# Independent review: accepted outbound recovery adversarial tests

Date: 2026-10-01. Reviewed candidate commits `411302c8174d3029a55273a99b9cb0154a1e63eb` and `78afe187418c23433cd1562d06c1d7dfc0215bed`, based on Mail main `c6f93bf4cadbb58c69027ebc6208d594ca713c80`.

## Verdict

**GO for hosted integration with the corresponding production integrity repair** after independent follow-up review of `beb7c28d9ea4513f25ffb9f5df7648eef0cdf600` and `b6dc85e1447ccc6f6153f68974dd73704bb9f56a`: both assertion-coupling findings below are resolved. Hosted execution remains necessary before treating the suite as passing evidence. This is not a verdict that the original implementation passes, nor permission for provider operations/deployment. The candidate deliberately stays out of the default test script while known original-source contract failures exist.

## Findings

### Resolved P2: partial-chunk fault freezes a noncontractual persistence strategy

Location: `infra/tests/worker-boundary/outbound-recovery.test.mjs`, test `partial chunk failure remains durable and repairs on a later tick`, assertion requiring exactly two rows in `message_text_chunks` immediately after the injected chunk-3 failure.

The actual observable contract is accepted journal retention, no visible partial message, no second provider send, and exact retry convergence. Atomic chunk writes may roll the earlier two chunks back; that is a sound implementation and would falsely fail this assertion. The retry already verifies exact text and the final 66-row projection. Require no visible message and accepted state, and allow zero or the correct incomplete prefix. If leftover chunks are intentionally part of a separate internal continuation contract, document that contract explicitly rather than deriving it from current sequential INSERT behavior. Confidence: high, statically demonstrated.

### Resolved P2: three-tick starvation bound freezes the current maintenance batch size

Location: same file, test `twenty unavailable archives cannot starve a later valid accepted message`, fixed three-iteration loop.

No product/service contract establishes completion of the twenty-first item within three immediately dispatched maintenance turns. A fair scheduler with a safe batch limit of five requires up to five turns at the same clock value, while still fixing the original permanent starvation. The planned invocation-budget work may deliberately choose such a smaller batch. Derive the test bound from a documented scheduling contract/cap, or use a conservative finite bound that detects perpetual reselection while permitting smaller safe batches. If retries use deadlines, control/advance the scheduled clock deterministically instead of assuming wall-clock sleeps. Confidence: high; impact is false CI rejection of a correct budget/fairness repair, not an original production defect.

## Positive assessment and limits

- The fixture executes the actual built Rust scheduled handler in workerd, production migrations, and real isolated Miniflare D1/R2 bindings. It does not duplicate production recovery SQL as its oracle.
- Independently generated standard Stored ZIP local/central headers, offsets, CRC32, lengths, and EOCD are consistent. ASCII `4_000_000` bytes produces 67 slices at 60,000 bytes, 66 additional chunk writes, and a ZIP safely below the 5MiB archive / 12MiB expanded caps.
- Original-source arithmetic is correct: 70 D1 statements per recent accepted item, two shared setup statements, 1,402 outbound statements for twenty items, before other Cron phases. This uses decimal 4MB, not 4MiB.
- Ownership tests correctly use exact indexed text, including extra chunks, so foreign-message chunk contamination is not hidden by only reading the first row. Final-transition failure checks raw projection absence and ledger state, not merely an API visibility filter.
- The egress interceptor accepts only one exact synthetic empty route-inventory GET and increments an unexpected-request sentinel before throwing for every other fetch. The sentinel is asserted after scheduled completion, so errors swallowed by the handler are still failures. Embedding is deliberately blocked; no real secrets, principal, destination, SMTP/OIDC/OpenRouter operation, deployment, or provider request appears in the fixtures.
- Budget audit counts extra chunk inserts only. A passing assertion does not establish the full Cron query budget, global progress, or a Paid/Free account admission. The candidate documents this limitation honestly; do not promote it into a full budget acceptance gate.
- Historical-source assessment only, superseded by the vacuity correction below: the former GC trigger was intended to capture a D1 interleaving after cached archive read. It is unreachable through repaired source's surviving-tombstone shortcut and must not be treated as that interleaving's evidence.
- Fault injection uses real SQLite triggers. Hosted execution must verify that triggers fire and recovery progresses against original and repaired built artifacts; static inspection cannot establish timing, actual runtime limits, or target-platform parity.

## Method and references

Reviewed the two commit diffs, complete fixture and accompanying plan, existing boundary harness conventions, production scheduled phase order, recovery/chunk/storage/delete implementation, archive caps, and production migrations. No local project build/test, provider operation, deployment, or push was performed. `git diff --check HEAD~2 HEAD` was clean; this is only static formatting evidence.

Primary platform references consulted:

- https://developers.cloudflare.com/d1/platform/limits/ — per-invocation 1,000 Paid / 50 Free queries; batch statements retain individual query limits.
- https://developers.cloudflare.com/workers/testing/miniflare/core/scheduled/ — direct scheduled event dispatch in the runtime harness.

No academic novelty is being evaluated: this is a bounded regression-test review of concrete service contracts and platform behavior.

## Follow-up resolution

Exact follow-up diffs were reviewed statically. `beb7c28` now permits zero through two staged chunks while preserving accepted state, raw message absence, final exact reassembly, and final 66-chunk checks. Atomic rollback no longer produces a false failure. `b6dc85e` removes the unsupported three-tick executable bound; the plan explicitly retains the missing-archive workload as **unexecuted**, requiring a scheduler cap/cadence/backoff contract and controlled clock. This resolves the test-coupling defect by narrowing the suite to nine tests; it does **not** supply a fairness regression or establish that production starvation is fixed. The scheduler/budget implementation must bring its own discriminating fairness test before fairness acceptance. No new substantive issue was found in those exact changes. No local runtime tests/build or push was performed.

## Follow-up: lease and legacy semantic integrity (`f19d62d`)

Reviewed exact candidate `f19d62d1c5b2e5d7d6910775c73a6582d146ee10` against `accepted.rs`, `lib.rs` integration, migration `0010_accepted_projection.sql`, and embedding triggers in the integrity worktree at `4f37db5000afc9e7406fc6ed5be0ac791e6bcdb0`. **GO for hosted integrity integration; no new substantive findings.** The tests require migration0010 and the matching built artifact; they are not directly runnable against the historical nine-migration source.

- Splitting the twenty-archive budget lower-bound test into a separately selected file is sound scope control. It does not remove or establish the separate full-Cron budget/fairness obligation.
- Shared fixture extraction preserves independent standard ZIP encoding, SHA-256 commitment, real isolated runtime/storage, blocked embedding dependency, and unexpected-egress sentinel. No provider operation or private data is introduced.
- Active lease case correctly verifies no projection/chunks or token theft while a twenty-minute stored deadline remains live. Setting the persisted deadline to zero tests expiry recovery without wall-clock sleeps; terminal token/deadline cleanup is checked. It does not by itself test an old running projector.
- Legacy case starts from a real production-generated matching projection, preserves owner/archive/provider commitment, then injects stale text/vector/suffix/unread state. Migration0007's vector-update trigger deletes prior work; the inserted synthetic old work subsequently exercises migration0010's publication requeue. Exact reconstructed content catches stale chunk99, all vector metadata must clear, mutable unread must remain, and work must be fresh/unleased. Direct late-token SQL is a deliberately narrower fence assertion than the production embedding commit (which additionally checks live deadline and other conditions), not a substitute for actual delayed provider execution; the plan labels this accurately.
- ZIP-less case preserves exact matching owned tombstone and storage reservation before removing the archive. This is actual deletion intent recognized by `finish_deleted`, unlike a missing ZIP alone. Terminal accepted-to-sent transition and subsequent message/chunk/storage/work cleanup are checked through real Cron.

Static `git diff --check f19d62d^ f19d62d` reports newly added blank EOF lines in the extracted fixture and budget files. This is minor formatting hygiene, not a substantive correctness issue. No local runtime test/build, provider operation, deploy or push was performed. Hosted behavior and the separate stale HTTP writer barrier still require their execution evidence.

## Review correction: extracted fixture bindings (`cc4a4c0`)

The lead identified a substantive defect missed by the preceding `f19d62d` review: the foreign-message collision test continued to use `sender` and `issuer` after those constants moved into the fixture module, but neither was imported/exported. The test would fail with `ReferenceError` at its `.bind(sender, issuer, Date.now())` call. Syntax-only checking cannot discover this lexical binding omission. The preceding unconditional source GO for `f19d62d` is withdrawn; responsibility for missing the extraction dependency belongs to this review, not to hosted execution.

Exact correction `cc4a4c0` exports the two synthetic constants from `outbound-recovery-fixture.mjs` and imports them in `outbound-recovery.test.mjs`, with no change to their values or service assertions. Reviewed the full extracted module and both consumers for free identifiers: fixture dependencies are imported `assert`, `createHash`, `path`, `fileURLToPath`, `Miniflare`, `applyMigrations`, `workerModuleRules`, locally declared constants/functions, and standard runtime globals `Buffer`, `Date`, `Response`, `Error`; integrity-test dependencies are imported `assert`, `test`, `fixture`, `accepted`, `indexedText`, `text`, `sender`, `issuer`, callback locals, and standard `Date`, `Array`, `JSON` globals; budget-test dependencies are imported `assert`, `test`, `fixture`, `accepted` and callback locals. No further undeclared extraction dependency was found by this complete manual inventory. EOF whitespace was separately normalized in `ba5f63a`.

**Final conditional GO for hosted integration at `cc4a4c0`** with migration0010 and the matching integrity implementation. This is a corrected static assessment, not evidence of test execution or effective platform budgets. No local project test/build, provider operation or push was performed. The independent budget/fairness and delayed-provider proof limits above remain unchanged.

## Review correction: unreachable GC race barrier (`afdfaa5`)

The lead identified another misleading-coverage defect missed by this review. The prior `physical tombstone collection during recovery cannot resurrect deleted mail` test pre-set the exact owned tombstone before scheduled recovery. Repaired `lib.rs` computes `deleted_bytes` from that tombstone and calls `finish_deleted`, then continues before the R2 read and chunk staging. Its `gc_barrier BEFORE INSERT ON message_text_chunks` therefore never fires. A passing visibility assertion would be vacuous evidence of the advertised cached-R2 concurrent-GC race. My prior historical-source assessment did not re-check barrier reachability against the repaired source; that was a review miss, not proof that such a production race exists.

Reviewed exact correction `afdfaa59dba411f7885a368d7bce7e2a178aac6e`. It removes the unreachable mutation barrier and truthfully renames the case `owned accepted tombstone with archive terminalizes without chunk staging`. The archive is explicitly present before repair; an actual per-ID chunk-insert trigger audit starts at zero; real Cron must terminalize the journal, retain invisibility and leave the staging audit at zero; subsequent real Cron must leave no message/chunk/reservation/embedding work or archive. Original recovery would attempt extra chunk inserts, so this audit discriminates the new no-restaging contract without pretending to introduce a race. The plan explicitly marks cached-R2 mid-projection concurrent GC as untested and distinguishes the separate ZIP-less tombstone and HTTP/Cron/delete/GC cases.

**Conditional GO for hosted integration at `afdfaa5`; no remaining substantive test-review finding in the corrected scope.** This supersedes the preceding verdict for the misleading race case; it does not close arbitrary cached-R2 GC interleavings, scheduler fairness or full-Cron budgets. Source and runtime revision-drain safeguards need their separate acceptance evidence. No local project test/build, provider operation, deployment or push was performed.
