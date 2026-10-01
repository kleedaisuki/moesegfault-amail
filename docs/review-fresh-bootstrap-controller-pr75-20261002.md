# Fresh bootstrap controller integration review

Date: 2026-10-02
Reviewer: bootstrap_review (independent; no production modifications or provider writes)
Source inspected: `.temp/fresh-mail-bootstrap`, controller commit `c2860de`, merged review head `e531e949a0600628071e93edfe16b6ceea61a187`.

## Scope and evidence limits

Static inspection of `infra/deploy/fresh_mail_bootstrap.py`, CI workflow integration, accepted fresh scope/readback/receipt modules, same-run artifact admission, deploy-result ambiguity boundary, and synthetic tests. No local tests/builds or provider operations were run. Hosted CI and actual protected provider execution are separate evidence, not supplied by this review.

## F1 — Recovery skips a remotely committed deployment when no version was captured (P2, high confidence)

Location: `Bootstrap.recover`, loop over `SCRIPTS`, conditional `if versions:`.

Trigger: Wrangler deployment times out, emits an oversized output, or exits without exactly one parseable version after a remote upload/deployment may have occurred. `run()` durably records role intent and failure but no version. `recover()` then does not read the known intended script deployment endpoint at all. Its result can omit a live partial graph and does not provide the promised observation for ambiguous submissions.

Correction: Observe each role with a recorded submit intent. Keep `captured_version=None` when unavailable, report independently observed serving coordinates with an explicit observed/unverified state, and never infer creation ownership, receipt success, replay or rollback authority from that read. Add a test from a no-version timeout journal, checking the exact GET and absence of writes/receipt.

Author acknowledged and is implementing.

## F2 — The operational recovery path is not yet executable (P2 before actual deployment, high confidence)

Location: controller `main()` and `.github/workflows/ci.yml` fresh bootstrap job/target.

The only current CLI entrypoint always constructs the current run's epoch and invokes `run()`. The workflow uploads prior journals but has no reviewed mode to admit/download those exact journals and invoke readonly recovery using the original source/run epoch. The method-level tests therefore do not establish an operator-accessible recovery path after a real ambiguous write. Starting the writer again would derive a different epoch, not observe the original operation.

Correction: Add a bounded recovery mode to an established hosted lane. Admit the prior repository/main/attempt-one producer and exact immutable recovery artifact, decode the owned original epoch/journals, then call readonly recovery. No creation, migration, queue mutation, deploy, receipt minting or automated retry. Alternatively do not dispatch the actual writer until this path exists; preserve source-only acceptance labeling meanwhile.

Author notified. This is a delivery integration gap, not a claim that the current controller retries writes.

## Positive source observations

- Exact main/first-attempt CI job identity and confirmation/freeze are required before provider credential/SDK setup.
- Admission reuses the fixed artifact ID, original manifest hash/compiler identity and all required completed source jobs, not a producer-only green result or ancestor artifact.
- Old retained Mail stores remain untouched; current held inventory is not relabelled historical drain.
- Fresh creation, migration, and each deploy are submitted once; failure stops rather than granting replay.
- New held/empty storage is verified before reader and producer deployment; sink readback occurs before either producer submit.
- Final v2 persistence receives the readback witness, has explicit paused/no-activation/no-old-work-end grants, and keeps source adoption outstanding.
- CI writer serialization is shared with established production writers and does not introduce a reentrant nested lock.

No broader production readiness or complete bootstrap approval is implied.

## Re-review update — controller/workflow corrections

Current author worktree inspected after the follow-up delegation (2026-10-02; changes not yet frozen into one acceptance SHA).

F1 is corrected in source: every recorded role submit intent gets one read-only serving observation, even without a captured Wrangler version. Read failures remain `UNVERIFIED`; no ownership/success/replay promotion is introduced. Dedicated synthetic tests cover the no-version timeout and failed-read cases. Hosted test execution is still required.

F2's executable routing is corrected in source by `.github/workflows/fresh-mail-bootstrap-recovery.yml` and protected `recover_main()`. The new read-only lane shares the non-canceling production writer lock, verifies main/first-attempt/workflow/job/confirmation context, runs source tests before exposing provider capabilities, and invokes no writer path. Full closure remains conditional on review and hosted validation of the pending exact prior-artifact loader (`fresh_bootstrap_recovery.py`).

Initial writer preflight records now preserve admission/refusal before artifact construction, and canonical recovery upload includes bounded queue creation records. These are diagnostics, not replacement creation or activation authority.

No additional substantive defect was identified in this bounded controller/workflow re-review. This does not validate the pending loader, provider readback behavior, or actual paused receipt production.

## Final source re-review — 5082af6

The integrated `infra/deploy/fresh_bootstrap_recovery.py` was inspected statically at author-reported `5082af6` (prior loader child `8e6d9c9`). It admits only the original terminal protected main/first-attempt creator and successful original source jobs; selects exact immutable bounded artifact IDs; validates the original epoch against run source; verifies the original full module manifest and bytes; rejects duplicate JSON keys, nonstandard constants, ZIP aliases/traversal/directory/symlink/encryption and oversized expansion; validates closed controller/scope/preflight/Queue evidence; and exclusively persists the admitted evidence under repository `.temp` before a read-only observation.

F1 and F2 are now resolved at the source-integration level. No additional substantive defect was found in the bounded loader review. Source tests include negative admission/archive contracts, but no local tests were executed. Current exact-head hosted checks and actual provider execution remain separate, outstanding acceptance evidence. Read failures deliberately remain unverified; recovery cannot grant replay, receipt success or activation.

Operational limit observed (not a new source blocker): cancelled creator runs and expired artifacts are not admitted by this recovery loader. Do not claim it provides universal recovery after every interruption or indefinite evidence retention. The current reviewed path covers admitted terminal success/failure/timeout creator runs with retained immutable evidence.

## Frozen-head delta review — 59c8b9904a11bbdbb08395d391b5ec0f231f30bf

Reviewed the diff from 5082af6 to the frozen PR 75 head. The loader now binds final scope creation timestamps to the earlier positive creation records, rejects duplicate Queue IDs in addition to duplicate names, enforces the scope replay flag as literal False rather than integer-zero equality, and validates string types before set membership. The maintained skill accurately describes first-held bootstrap, readonly recovery, unknown submit/read outcomes, and cancellation/expiration admission limits. No new substantive defect found in this bounded delta.

Source findings F1 and F2 remain resolved at this frozen head. Hosted final CI run 36898627288 was reported pending by the author; this static review does not assert its outcome. No local runtime tests/builds, provider operations, or production source changes were performed.
