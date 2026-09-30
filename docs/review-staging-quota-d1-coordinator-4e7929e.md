# Independent review: dormant concrete escrow recovery coordinator

Date: 2026-10-01. Reviewed commit: `4e7929ee9668f11336d92ff94d9f6adc605a8136`.
Baseline: independently corrected terminal source `63f9d11`, correction review
`35a87d7`, and original quota composition/read-only recovery contracts.

## Decision and execution limits

**After correction `9890d48`: GO for the bounded dormant coordinator and hosted
source-only validation; live remains NO-GO.** The initial `4e7929e` assessment
was NO-GO pending the P2 below; the independent follow-up at the end resolves
it without removing its failure mechanism. This is a functional recovery-path
defect, not a request for
live execution or additional alias mutation. No local tests/builds, executable
harness invocation, provider requests, migration, key access, artifact download,
workflow dispatch, or production-source changes were performed. Inspected
fixtures are source evidence, not executed results. Unrelated worktree changes
are excluded from this review and its commit.

Reused internal design and prior reviews by filename, inspected the complete
three-file diff and surrounding acceptance, hosted, manifest, readback, native,
escrow and synthetic fixture implementations, and searched all coordinator and
terminal-helper callers. Public research was limited to primary engineering
and academic sources.

## P2: the post-teardown oracle rejects normal retired campaign tombstones

**Location:** `infra/tests/staging_ten_address_acceptance.py:240`, the call to
`manifest.assert_prefix(plan, reader.read(), 0, ...)`. **Confidence: high,
source-derived deterministic failure path; not executed locally.**

The new final check uses the pre-campaign zero-prefix oracle. At
`staging_ten_address_manifest.py:342-345`, that oracle requires the set of every
row absent from the baseline to equal the empty prefix. This includes retired
rows, not only live allocations. By contrast, supported campaign deletion
leaves retired owner-bound tombstones, and the actual readback deliberately
includes all candidate rows, including retired rows:
`staging_ten_address_readback.py:197-207` selects `state!='retired' OR address
IN (...)`. These rows are journal state and are not physically deleted by this
recovery path.

The established cleanup oracle explicitly accepts such rows only when owner,
creation time and local part match, retirement is settled, no provider rule
remains, `cf_rule_id` is null and `needs_reconcile` is zero
(`manifest.recovery_actions`, lines 303-330). `manifest.reconcile` then compares
the complete unrelated-row, rule, object and global-count baseline. This is
the oracle already used by `hosted.recover`.

| Step | Valid supported state | Current coordinator behavior |
| --- | --- | --- |
| Prepare | Original baseline has no candidate allocations | Authenticated original artifact is retained |
| Campaign | Ten supported adds, then supported DELETEs settle | Ten candidate rows remain retired; provider rules are absent |
| Recovery | Fresh native owner inventory is empty; baseline count/storage/rules are restored | `hosted.recover` correctly succeeds without add/delete |
| Teardown | Native logout/home teardown and binary removal return normally | Required local ordering succeeds |
| Final remote check | Same ten settled tombstones remain | Zero-prefix assertion raises `global_or_owner_drift` before receipt SQL |

Thus the coordinator can finalize a never-mutated empty fixture but cannot
finalize a normal successfully cleaned quota campaign, or a recovery in which
Cron has settled earlier DELETEs. Ciphertext is conservatively retained, so
this is not an unsafe purge; it is an operationally blocking false rejection
on the main intended use case, preventing terminal settlement and subsequent
admission progress.

**Coherent remedy:** use the existing read-only cleanup/baseline relation after
teardown rather than the pre-campaign prefix relation. For example, re-run
`manifest.reconcile` with `delete=None` and the previously freshly authenticated
owner, then independently recheck storage and service/privacy pins. Preserve
the exact unrelated-row/rule/R2 inventory comparisons and owner-bound settled
tombstone validation. Do not filter retired rows away, weaken ownership checks,
physically delete tombstones, or grant recovery a DELETE capability.

Add a deterministic composition fixture starting with candidate allocations
that were created and retired through `World` (which already preserves
tombstones), then perform the real dormant recovery/teardown/SQLite sequence.
It must emit the receipt/purge only after teardown and leave the tombstones
unchanged. Also reject unsettled/foreign retired rows and post-teardown
owner/rule/storage drift without terminal SQL. The current success fixture
starts with `World()` empty and therefore misses precisely this contract
difference. Keep its existing active-row and teardown failure cases.

## Other assessed boundaries

| Boundary | Static assessment |
| --- | --- |
| Dormancy and capabilities | `main` still calls ordinary `execute`; neither parser nor workflows reference `finalize_recovery`. Terminal mode is recover-only before environment consumption. Both adapter add and delete are forbidden in recover mode. Python private functions are trusted source conventions, not an access-control boundary. |
| Current/source/original admission | Reuses hosted attempt-1 environment admission, exact checkout SHA, observed current manual-run record, successful exact source-run checks, original manual-run/artifact run/SHA metadata and authenticated original manifest checkout. No caller-provided pass flag or outcome label replaces these checks. |
| Binary and session | Reuses exact current-source immutable Windows binary admission and a fresh native A session with verified Identity owner binding. Owner and username must equal the original manifest. No local executable/session fallback was introduced. |
| Escrow binding | Before recovery, schema/header relation and exact artifact ID are checked. Nonterminal escrow must provide complete matching authenticated ciphertext. Existing terminal metadata does not bypass fresh external recovery. |
| Hold/service/privacy | The real readback sending-state callback is passed to `Services`; initial three-service immutable pins/bindings and independent effective capture-off remain required. Post-teardown service/hold, complete inventory, storage and effective privacy checks are present, though the inventory oracle has the P2 above. |
| Independent cleanup | `hosted.recover` validates owner/baseline/provider/storage, observes native owned inventory, and performs read-only settlement. Active allocations require manual intervention, not address DELETE replay. |
| Teardown ordering | Terminal SQL is textually after normal return from the native context and successful owned binary `rmtree`, outside the `finally`. Exceptions/cancellation do not fall through. Native teardown proves local removal, not guaranteed remote refresh-token revocation. |
| Receipt ambiguity | `_finalize` remains the reviewed exact lifecycle conditional write. A lost/zero-change receipt response propagates and does not reach purge. Existing terminal metadata can permit separately invoked purge only after all fresh coordinator checks; it does not rewrite the receipt. |
| Purge ambiguity | `_purge` requires exact authenticated original bytes and matching immutable receipt. A lost DELETE response stops, retaining all not-yet-deleted chunks; already committed deletions are not undone. A later separate invocation may skip absent chunks only after fresh recovery. |
| Compatibility | No tenant/runtime/API/migration-stream change or CLI/workflow contract expansion is introduced. The dormant staging schema remains unapplied. No real D1 SQL/parameter/latency claim follows from injected SQLite. |

The receipt/purge query callback assertions in the new tests directly check
native context exit and binary directory absence, rather than accepting a
generic passed boolean. Native/scratch failure, active row, final privacy
failure and post-teardown active-row drift cases assert no terminal SQL. This
ordering coverage is useful. It does not currently exercise successful settled
tombstones, coordinator resumption from an existing terminal receipt/partial
purge, or source/artifact/header failure through the terminal entry specifically.
Earlier primitive tests cover many of those components, but are not evidence
that the complete coordinator has executed them. Those remain bounded hosted
coverage opportunities after the necessary correction, not extra demonstrated
defects.

## Engineering and research interpretation

The no-replay boundary remains consistent with AWS's production discussion of
[safe retries and request identity](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/).
The peer-reviewed SOSP 2015 paper
[Implementing Linearizability at Large Scale and Low Latency](https://web.eecs.umich.edu/~manosk/assets/papers/rifl.pdf)
connects completion records to operation identity and safe reclamation in its
own system model. Neither source establishes exactly-once provider cleanup
here or turns a public receipt digest into external attestation. The useful
design implication is to preserve the tombstone/operation history and reuse
the existing recovery-state oracle; adding retries or removing journal rows to
make an empty-prefix assertion pass would attack the wrong problem. No new
distributed framework is necessary for this correction.

## Unchanged live gates and explicit limitations

The design accurately states that the immutable original 30-day artifact is
still mandatory. Expired-artifact full-ciphertext fallback is not implemented.
After partial purge, remaining D1 chunks cannot reconstruct the original full
manifest; if the artifact expires, stop and require a separately reviewed
storage-settlement/expiry path. Logical D1 deletion is not erasure of retained
artifacts or provider backups. An incomplete writing escrow without the full
authenticated envelope must not be fabricated into terminal success.

Correcting this source defect and obtaining hosted synthetic evidence do not
authorize live use. Exact applied staging schema/permissions and D1 integer/
nullable parameter behavior, provider latency/shared-mail impact, wrapper and
expiry integration, metadata watchdog/real Agent intake, 24-hour accountable
acknowledgement/freshness, current source/binary/native/provider/storage/hold/
service/capture-off admission and separately authorized recovery all remain
live gates. No migration, campaign, key retirement, acknowledgement-based
purge, schema drop, replay or live workflow dispatch is authorized by this review.

## Independent correction review: `9890d48`

Inspected the complete three-file correction and the reused `reconcile`,
`recovery_actions`, row/rule builders and full composition fixture. **P2
resolved. GO for hosted dormant source validation; no additional substantive
defect found in this bounded correction. Live remains NO-GO.** No local
tests/builds, provider requests, migration, key access or dispatch occurred.
Fixtures were inspected, not executed; hosted results are still required.

The post-teardown call now passes `reader.read`, literal `None` for deletion,
and the owner obtained from the already completed fresh native authentication
to the established `manifest.reconcile`. That oracle accepts only exact
owner/time/name-bound settled tombstones, and retains the complete baseline
checks for unrelated rows, provider rules, R2 objects and global count. The
separate storage and effective privacy checks remain after it; service/hold
checking remains before it. No rows are hidden or deleted to force equality,
and no mutation callback or broader recovery capability was introduced.

The new success fixture constructs ten manifest-eligible owner-bound retired
rows with null provider IDs, no rule, zero pending reconciliation and an old
`next_reconcile_at`. This accurately represents the persistent journal relation
that the original prefix assertion rejected. It traverses the real coordinator
and existing isolated SQLite escrow, while the shared query callback requires
native exit and binary scratch absence before receipt/purge. It asserts all
ten tombstones remain and native add/delete are never called. This is a
structural source regression fixture, not evidence that a live campaign ran.

Four adversarial fixtures first supply valid recovery state, then mutate only
after native context exit: an unrelated baseline row owner, an unrelated rule
raw digest, a candidate tombstone owner, or its pending-reconciliation flag.
They require failure after observed teardown with the parent still sealed and
no receipt/purge SQL. The shared harness inserts authenticated nonterminal
ciphertext before invocation, so no terminal query means that ciphertext is
retained. Existing active-row, native/scratch failure and final capture-off
cases remain. Coordinator partial-purge resumption, expired artifacts and
real-provider semantics are still outside this narrow correction's evidence.

The documentation now describes the same cleanup-state oracle and labels the
new fixtures as awaiting hosted execution. All live gates and artifact-expiry/
partial-purge limitations above remain unchanged.
