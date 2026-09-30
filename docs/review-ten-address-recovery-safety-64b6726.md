# Independent review: cross-run quota recovery safety

Date: 2026-10-01. Reviewed safety commit: `64b6726de67da617739ab0e7379477c197598b70`.
Reviewed composition/workflow integration: `4c6dde35faa36f6dc36d22bbbcf1b33ffe6fff35`
and its unchanged `staging_ten_address_acceptance.py` caller.

## Decision

**GO for hosted source-only checks after the independently reviewed `85d3cd1`
correction below. Live quota/recovery dispatch remains NO-GO.** This is permission
to obtain hosted evidence, not a claim that tests already passed. The controller
safety correction itself has no substantive defect
identified in the inspected paths. It conservatively removes cross-run DELETE
replay without inventing an attempt history from the immutable manifest.

No local tests, builds, executable harness runs, provider/CLI operations,
artifact downloads, authentication, SMTP, or deployment were performed. The
fixture failure is a source-derived executable path, not a reported test run.
Only this review artifact was written; concurrent worktree changes are outside
scope and were not staged.

## Resolved finding: P1 stale composition recovery contract

Location: `infra/tests/test_staging_ten_address_acceptance.py:124-133`, with
fixture construction at lines 80-81.

`PhaseTests.execute("recover")` creates an active candidate. The recovery test
then requires a success label and exactly one DELETE. The new public
`hosted.recover` instead passes `may_delete=False`, and manifest reconciliation
raises `recovery_manual_intervention_required` for that live candidate before
calling DELETE. Therefore the existing composition fixture necessarily raises
instead of returning its asserted success tuple. Confidence: high.

Impact: both normal source test discovery and the new standalone workflow's
pre-Secrets `test_staging_ten_address*.py` discovery include this fixture. This
blocks green hosted evidence and preparation/campaign/recovery entry in the
standalone workflow. The safe implementation must not be weakened to satisfy
the obsolete fixture.

Remedy: split the composition coverage into (1) an active/pretransition
independent recovery that requires the fixed manual-intervention outcome and
asserts both CLI add and delete were not called, and (2) an already settled or
synthetically Cron-settling retirement that succeeds without local prepared
ciphertext and with zero DELETEs. Retain original run/artifact coordinates,
owner authentication, post-success privacy checks and native scratch teardown
assertions. Prefer supplying a forbidden delete capability in recovery as
defense in depth, although the currently reviewed public controller never
invokes the passed callable.

## Safety boundary assessment

| Boundary | Source-derived result |
| --- | --- |
| Pretransition process death | Active/pending/provisioning resource rows remain ambiguous. Public recovery calls `_cleanup(..., may_delete=False)` and cannot send a DELETE; eligible live rows require the fixed manual-intervention code. Unsafe ownership/rules can fail earlier with their own fixed contract code. |
| Posttransition process death | Existing `deleting` or `retired + needs_reconcile=1` rows receive only bounded read polling. Settlement verifies exact owner, issuer, local part, allocation time, clean retired tombstone and route absence. Cron timeout is failure, not renewed send authority. |
| Same-invocation cleanup | Only campaign's private `finally` passes `may_delete=True`. Manifest reconciliation scopes candidates, audits full matching provider rules and saved IDs, rechecks each candidate before one supported DELETE, and stops after ambiguous send or settlement failure. No batch/retry path was introduced. |
| Campaign re-entry | `_observe(..., prefix=0)` moved outside the mutating `try/finally`. A partial campaign fails admission without accidentally acquiring cleanup permission. Exact residual tombstones also violate the empty-prefix observation. |
| Final result | `manifest.reconcile` still requires no eligible live rows, exact baseline R2 inventory, full baseline provider rules, unchanged unrelated rows and global live count. Controller additionally requires empty owner API, candidate storage/message absence and original serving pin. Read-only mode does not bypass this final invariant. |
| Wrapper/workflow | `execute` explicitly calls public `hosted.recover`, not `_cleanup` or campaign. Workflow recover selects the `recover` mode with exact prior-run/artifact coordinates. There is no mutation override argument, journal flag or fallback to campaign. Passing an available `cli.delete` callable is unnecessary but not exercised by the current read-only controller. |

## Coverage and operational limits

New controller fixtures cover active/pending/provisioning pretransition ambiguity,
posttransition deleting settlement without replay, partial pending-retired/live
cleanup, read-only manifest reconciliation and rejected campaign re-entry.
Existing campaign fixtures preserve exact same-invocation deletion, asynchronous
202 settlement, first-ambiguity stop, eleven-alias regression cleanup and
cooperative interruption coverage. They were inspected, not executed. The
wrapper-level obsolete recovery fixture was corrected by `85d3cd1` as reviewed
below.

Read polling is not a deployment lock or global transaction. Full baseline
verification occurs before success; unrelated drift cannot pass merely because
a candidate eventually retires. Authentication/logout may still mutate Identity
session state; “read-only recovery” here means no address/routing/storage mutation
by the recovery controller, not zero network requests of every kind.

The design deliberately sacrifices automatic progress for ambiguous live rows.
The encrypted manifest records intent and exact scope, not a durable attempt
journal. A fixed manual-intervention result authorizes neither a fresh campaign
nor calling private cleanup nor a manual DELETE procedure. Production guidance
likewise treats missing responses as ambiguous and requires explicit, durably
enforced request identity to make retries safe; see [AWS Builders' Library:
Making retries safe with idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/).
This reference supports the ambiguity distinction, not a claim that this service
already implements that contract.

After fixture correction, GO is limited to obtaining hosted synthetic/real-cipher
source evidence for the exact containing SHA. Live dispatch still needs the
independent workflow review, retained original encrypted artifact/key generation,
current source admission, complete live readbacks, original service pins,
effective capture-off, held policy and concurrency/operational authorization.
No reviewed path proves recovery after a killed process whose DELETE never
became an observable transition.

## Narrow follow-up review: `85d3cd1`

Reviewed commit: `85d3cd10b9acf62877d5d0d79293259e2c4369f9`.
The original P1 finding is resolved. No further substantive finding was
identified in this correction; no local tests/builds/live calls were run.

- The wrapper now supplies `forbidden` for **both** add and delete unless mode
  is campaign. External recovery therefore lacks CLI address mutation even if
  an accidental future controller invocation tries to use its adapter DELETE.
  The existing explicit call remains public `hosted.recover`.
- Default independent recovery uses an empty, authenticated baseline and
  requires success with zero DELETEs, exact original artifact coordinates, no
  local prepared file and two effective-privacy checks. This is an adequate
  success case, not a substitute for the controller's synthetic Cron fixtures.
- A separate `active_recovery=True` fixture creates the ambiguous live row and
  requires `recovery_manual_intervention_required`. The helper's `finally`
  asserts neither native CLI add nor delete was called on recovery, including
  that failure path.
- `main` exposes exactly the source-owned fixed manual-intervention failure
  marker with exit code 1. Other contract failures retain the generic fixed
  failure marker; observed exception content is not printed. The new entry
  fixture checks that failure marker and exit status, not success.

The active-failure helper exits before its post-call scratch-directory assertion;
production teardown remains in `execute`'s outer `finally`, and the successful
recovery helper still asserts scratch teardown. Extending the failure fixture's
teardown assertion would be optional coverage improvement, not a release-blocking
defect established by this review.

**Updated decision: GO for hosted source-only checks of an exact containing SHA;
live dispatch remains NO-GO until the independent operational/workflow gates are
satisfied.** Do not infer hosted pass evidence or authorize manual deletion from
this source assessment.
