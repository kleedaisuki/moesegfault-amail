# Independent review: held API-only CI integration, f734dca

Date: 2026-10-01. Exact reviewed change:
`f734dca353ad25107c74f7fdfdf3732b359cee85` against its first parent.

## Decision and scope

**GO for pushing the coherent source revision to GitHub-hosted source checks.**
No substantive new defect was identified in this ten-file integration delta.
This is not approval to dispatch a deployment, run quota acceptance, mutate
provider state, adopt contacts, attest human operations, or allow public sends.
Hosted full source CI and the independent workflow syntax lane must pass at the
containing immutable revision before any separately authorized held rollout.

Reviewed the exact workflow/test/documentation diff, its source callers, and
the prior direct-only graph (`f62a1d9`), realm-safe deployment (`d3f8eba`),
direct-contact gate/hold (`a93fe58`/`212cfe0`), and quota workflow (`4c6dde3`)
contracts. Existing review documents were located by filename and consulted
first. All conclusions below are static source assessment; no local project
tests, builds, migrations, provider calls, deployment, sending, secret change,
or mailbox access occurred. Public GitHub documentation was retrieved to check
the concurrency contract. Concurrent uncommitted operator/workflow changes
observed in the shared worktree are outside this verdict.

## Assessed integration

| Boundary | Source evidence and judgment |
| --- | --- |
| Dormant role deployment | The production role rollout workflow is deleted; CI removes the staging role deployment job and dispatch choice. Current workflow sources do not invoke the role deploy/migration helpers or select `api-role` topology. Historical SMTP and read-only research remain explicit, separate jobs, not a production admission dependency. Source deletion neither retires remote research storage nor cancels already running historical revisions. |
| Dispatch surface | CI declares 24 distinct dispatch input names, below the inclusive 25 limit. The removed sink-canary-run input belonged only to removed role rollout. All retained inputs and ordinary check/staging targets remain. |
| Production preparation | Sink preparation explicitly selects `bootstrap` or `api-only-maintenance`, with the existing protected production environment, main-branch guard, phase confirmation and external graph-writer freeze. Bootstrap requires held policy, complete API/role absence and four exact verified direct forwards. Maintenance requires the strict existing API-only graph. |
| Production Queue lifecycle | Only bootstrap provisions queues. Maintenance performs `readback --topology api-only`, preserving configured Queue/DLQ IDs and publishing those exact identities. No maintenance recover/recreate branch or role migration is introduced. |
| Production replacement | Both sink and Mail jobs select literal `api-only`; role-version/routed-count inputs are removed. Maintenance checks old/new sink and old/new Mail through the same strict graph checker. Mail receives the same-run sink/Queue outputs. Post-Mail acceptance overrides the API pin with `steps.api.outputs.version`; the existing graph marker is emitted only after successful full graph readback. |
| Held and four-forward protection | The reused direct graph/preparation guard enforces held/unattested global policy and exact unchanged forwarding snapshots, plus role absence, immutable serving pins, Queue ownership, independent API/sink privacy. The workflow does not write contact adoption, health, attestation, send allow, or operational forwarding rules. Bootstrap remains a separately frozen multi-job rollout, not an atomic transaction. |
| Staging preconditions | Existing release-branch, exact confirmation, containment evidence and staging environment remain. Global hold is checked before Queue/sink mutation, before provider/schema changes, immediately before Mail replacement, and after readback. Existing privacy configuration and independent containment checks are not bypassed. |
| Exact staging deployment | Mail uses the redacted realm-safe wrapper with explicit staging target/topology/confirmation and `INGRESS_SECRET_STAGING`. Queue ownership is API-only; immutable `queue-api` binding acceptance uses the newly captured API UUID and same-run Queue ID. Independent API and exact sink privacy checks precede final held readback. No raw Wrangler output or new secret key is introduced. |
| Standalone staging pin | Explicit `queue-api` and reviewed staging Queue ID replace the historical default pre-Queue contract. This intentionally rejects an old topology instead of weakening immutable binding acceptance. |
| Source-only execution | Existing push/PR/check job selection remains source-only. All changed provider/deployment jobs still require manual dispatch; provider-live is also manual. No new secret reference or deployment-on-push/PR path is added by the delta. |

## Concurrency and operational limits

The same-repository quota accept/recover job and active staging Mail, sink,
ingress, events, private inbox, and capture/settings correction jobs use the
exact `staging-native-mail-acceptance` group with `cancel-in-progress: false`.
The standalone inbox workflow uses that same group at workflow level only.
CI owns it at job level only, avoiding parent/dependent-job self-blocking.
The promotion mutator DAG is sink -> Mail -> ingress -> events -> private
inbox. In particular, events now depends on ingress, and inbox depends on
events; no parallel same-run mutator siblings compete for a pending slot.
Unrelated site work and source checks remain independent.

[Current GitHub concurrency documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
confirms repository-scoped groups, default one-pending replacement, and an
optional `queue: max` for multiple pending members. Therefore non-canceling
running work does not guarantee every pending dispatch executes. The documented
external freeze and no-dispatch-order guarantee are accurate; the serial DAG
solves same-run sibling replacement, not arbitrary concurrent manual dispatch
replacement. Cross-repository Identity/Login writers, dashboard operations,
out-of-band tools, and historical running workflows still require independently
enforced freeze. A lock is not a provider/D1 transaction or crash rollback.

The production workflow retains its separate non-canceling workflow-level
`amail-production-graph-writer` group. Its job-level groups are different, so
the staging shared-group change does not create a production reentrant wait.
Existing separately scoped forwarding operations must also respect the explicit
production graph-writer freeze; this review does not claim that one concurrency
string coordinates every possible writer in the repository or account.

## Legacy contracts and compatibility

The infrastructure discovery command remains the full suite. Updated contracts
do not merely delete obsolete assertions: they replace role-deployment ordering
with active-path absence, exact API-only lifecycle/Queue/pin checks, no role
migration or forwarding rewrite, preserved production lock and dispatch bound,
and staging hold/privacy ordering. The missing-`fi` historical Bash regression
still has a parseable synthetic fixture and malformed negative fixture; it no
longer pretends a removed deployment gate remains active. Role provenance tests
retain independent sink/canary oracle-before-marker checks and historical SMTP
pin wiring. The production retained-record evidence guard is still tested to
reject missing actual privacy harness evidence.

These source-shape tests are useful regression guards, not live evidence or
proof of their mocked provider guards. The count assertion alone does not
validate duplicate YAML keys; independent hosted workflow syntax validation
remains necessary. Actual test success has not been inferred from inspection.

The workflow maintenance target/confirmation change and removal of rollout-only
inputs are deliberate retirement of an unaccepted internal alternate topology,
not a user-facing Mail CLI/wire change. Old operational dispatch recipes must
use the documented direct-only target and confirmation; preserving an alias to
the obsolete role graph would undermine fail-closed migration. Existing user
mail D1/R2 identities, HTTP routes, ingress secret realm selection, and four
Cloudflare-managed forwards remain preserved by the consumed source contracts.

## Remaining acceptance boundary

No mandatory correction is requested for this delta. Live readiness still
requires green containing hosted checks, actual protected environment/default-
branch registration, no old or external writers, exact live pins/readback,
separately authorized held migration/deployment, and independent release/privacy
evidence. Continuing direct-contact observation and truthful owner Inbox/Junk
and response adoption/attestation remain public-release prerequisites; successful
configuration/deployment cannot satisfy them automatically.

This distinction is consistent with the established
[Gray Failure research connection](https://www.microsoft.com/en-us/research/publication/gray-failure-achilles-heel-cloud-scale-systems/):
component/configuration success does not establish the human operational outcome
that the release gate protects. No new research-driven machinery is recommended.

Internal basis: [deployment contract](direct-forward-api-deployment.md),
[production graph review](review-production-api-only-graph-f62a1d9.md),
[realm-safe deployment review](review-staging-exact-deploy-wrapper-d3f8eba.md),
[direct gate review](review-direct-forward-contact-gate-a93fe58.md), and
[quota workflow review](review-ten-address-workflow-4c6dde3.md).

## Hosted correction: omitted worker-suite delimiter dependency

Hosted source run `36773432805` subsequently reported an Infrastructure failure
in `workers/identity-test-inbox/test_deploy_workflow.py`. Source inspection
confirms that its job slice ends with
`ci.index("\n  staging-role-monitor:", start)`, although this integration
deliberately removed that job. The resulting `ValueError` prevents the existing
all-alias interlock and deployed-binding assertions from executing. This is a
demonstrated test integration defect, not a live deployment/privacy failure.

**F1 (source acceptance blocker): update the private-inbox workflow test to
extract the exact named inbox job independently of an unrelated following
job.** Preserve both workflow paths and every pre/post all-alias and deployed-
binding assertion; do not restore the retired deployment job or relax the
interlock. Use the existing reviewed source extractor where practical.

This was a review miss: the earlier legacy-reference search covered
`infra/tests` but omitted the separately discovered worker suite. The initial
statement that no substantive delta defect was found is superseded for this
specific test-integration boundary. Pushing a corrective source revision for
hosted checks remains appropriate, but `f734dca` alone has not passed its source
acceptance gate. No local test/build/live action was performed to investigate.
Remaining jobs in that hosted run were still running when the failure was
reported; this artifact does not infer their eventual results.

### Narrow correction review: cddf427

Independently inspected exact commit
`cddf427fdf2613175826d262d8516ab1293a428e`, including its two-file diff and
the existing `workflow_source.py` extractor. **F1 is closed at source level;
GO for a containing corrective source push and fresh hosted checks.** No
production behavior or deployment workflow was changed by this correction.

The inbox suite now imports the existing strict extractor through the explicit
repository `infra/tests` path and selects `staging-identity-test-inbox` in CI
and `deploy` in the standalone workflow. This removes the nonexistent-successor
dependency and narrows both assertions to the actual target job. The extracted
assertion helper preserves all original counts and pre/post deployment ordering
for both all-alias interlocks and immutable deployed-binding readback.

New synthetic fixtures exercise the deleted successor, unrelated neighboring
credential/body isolation, CRLF normalization, and rejection when postdeploy
guards are moved into another job. The negative fixture currently trips the
all-alias count first; the real contract also retains the deployed-binding count
and ordering assertion, so this fixture detail is not a weakening or blocker.
The reused extractor rejects missing/duplicate job keys and unsupported shallow
layout rather than broadening the slice to neighboring jobs.

The documentation accurately records the hosted failure without inventing a
production incident or claiming local test success. No local tests/builds/live
actions were run during this correction review. Actual suite success and other
jobs' outcomes must be established by fresh hosted evidence at a containing
immutable revision; source closure alone is not a green-run claim.
