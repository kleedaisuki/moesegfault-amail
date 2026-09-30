# Review: privacy trace Queue provisioning and rollout (`1664174`)

Date: 2026-09-30. Reviewer scope: independent static review of `1664174`, ADR
`ada53db`, containment `f3d389c`, surrounding serving-pin implementation and
current draft sink settings verifier. No local test/build, live API request,
provisioning, deployment or push was performed. Production code was not changed.
The producer/schema/sink and canary are concurrent draft work and are not
attested by this review.

## Decision

**GO for hosted non-deploying source CI on the integrated source; NO-GO for
live Queue provisioning / automatic rollout until the findings below are
resolved.** A branch push currently also deploys staging, so it is not a
non-deploying CI-only action. At `1664174` alone the trace crates and sink-mode
verifier are not yet committed; integrate those reviewed dependencies before
expecting CI to compile and the sink verification step to execute.

The intended architecture and order are sound: distinct realm names, private
sink prerequisite in both API jobs' `needs`, explicit one-day retention,
finite retries, no queue UPDATE/DELETE/purge or payload GET, ambiguous POST
failure stops, and a rollback contract that never restores logging-on API
versions. These are not substitutes for the missing live gates.

## Required corrections

### P1: staging containment gate does not establish the serving deployment

Locations: `.github/workflows/ci.yml` staging-trace-sink containment step and
staging-worker pre-deploy containment step; `check_observability.py::verify`.

Both new prerequisites call only `/settings` and `/script-settings`; neither
reads the active deployment and its traffic percentages. A separately uploaded
safe version or split deployment can satisfy the latest settings checks while
an older public API version still handles requests. Thus the prerequisite does
not enforce the ADR's **100%-serving containment-only version** before resource
creation / producer rollout. Confidence: high, established missing call path;
no claim that the live deployment is currently split.

Correction: bind the prerequisite to the known containment version, require
exactly one version at 100% from the active deployment, inspect its resources,
check both effective settings, then read the deployment again and reject a
change. Reuse/generalize `infra/deploy/pin_staging_mail.py` semantics rather than
using unversioned settings as a serving proof. Add hosted negative fixtures for
split traffic, wrong version and deployment change.

### P1: sink verification step does not check its private trigger/capability boundary

Locations: new production/staging sink jobs' `Verify sink retained telemetry
and private trigger boundary`; current draft `check_observability.py --mode sink`.

The committed checker at `1664174` has no `--mode` at all (an integration
prerequisite). The current draft adds mode but still reads only observability,
logpush and tail consumer settings. It never reads workers.dev / preview
exposure, routes/custom domains, schedules or version bindings. A stale route,
preview URL or additional binding can therefore survive and the step reports
`safe`. This contradicts the explicit no-HTTP/no-business-storage sink contract
and the CI step's claim. Confidence: high on missing verification; conditional
on actual provider drift.

Correction: use bounded provider readbacks for the exact sink's active version,
subdomain flags, complete routes/domain/schedule inventory, and exact allowed
binding set; reject exposure, storage/secrets/services or unknown shapes. Queue
consumer ownership alone does not cover HTTP triggers. Attest a stable serving
version around the readbacks. Add synthetic denial tests before live rollout.

### P2: ownership lists can be incomplete without being detected

Location: `infra/deploy/ensure_trace_queues.py:98-126`.

The official Queue response schema carries `consumers_total_count` and
`producers_total_count` in addition to arrays. The implementation checks only
array lengths. For a response with `producers=[]` but a nonzero total it accepts
an ostensibly unbound Queue; for a singleton reviewed producer/consumer array
with a larger total it claims exact ownership. Missing count attestation makes
an omitted/truncated ownership response look complete. Confidence: high for the
executable acceptance path, conditional on provider omission/truncation.

Correction: require integer nonnegative total counts matching the arrays, or
obtain separately bounded complete ownership inventory with an attested end.
Also require detail queue ID/name to equal the selected inventory identity.
Hosted fixtures should include mismatched totals, missing totals and wrong
resource identity, not merely removed consumers/producers.

### P2: same-name unbound resources are automatically adopted

Location: `ensure_trace_queues.py:84-109` and DLQ empty-list acceptance.

An existing reserved-name Queue with matching settings and empty attachment
arrays is accepted exactly like one created by this rollout. Empty attachments
are not a provenance or empty-backlog proof. Attaching the sink to an unrelated
or abandoned resource may deliver historical messages from outside the
reviewed producer boundary; no messages are read to establish their provenance.
This is a conditional resource-ownership risk, not evidence of a current
collision. Confidence: medium-high on the acceptance path.

Correction: pin resource IDs from reviewed creation evidence / explicit
reconciliation approval for existing unbound resources; fail unknown IDs rather
than automatically adopting them. A timed-out POST should leave an explicit
reconciliation path, not authorize name-only adoption. Do not fix this by
purging or inspecting arbitrary queue payloads.

## Tests and limits

The infrastructure CI job discovers the new Python tests. Current fixtures
cover retention drift, duplicate names, declared page traversal, no retry after
ambiguous POST, and missing owner arrays. They do not cover the above serving,
trigger, ownership-count or adoption gates. No test was executed locally.

A clean hosted source CI plus corrected settings/provisioning gates only permits
a bounded live rollout; it does not prove whole-record privacy. After rollout,
require the separately reviewed synthetic sink canary, both serving pins, API
non-retention, sink marker exclusion and retained causal trace evidence.

## External evidence (retrieved 2026-09-30)

- [Cloudflare Queue list schema](https://developers.cloudflare.com/api/resources/queues/methods/list/): page metadata, queue settings, producer/consumer arrays and total counts; worker consumer `script_name`, producer `script`.
- [Cloudflare active deployments](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/deployments/methods/list/): first deployment actively serves traffic; versions have individual percentages.
- [Queue configuration](https://developers.cloudflare.com/queues/configuration/configure-queues/).
- [Dead-letter queues](https://developers.cloudflare.com/queues/configuration/dead-letter-queues/).
- [Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/): native bindings and tracked asynchronous work support the architecture, not a complete privacy attestation.

The Queue Get documentation fetch failed repeatedly; no invented Get-specific
schema guarantee is asserted. Ownership totals are documented on Queue list,
and implementation must attest completeness using a supported provider shape.

## Narrow correction review (`71e6036`, `c9f698d`, `96a6181`)

Reviewed 2026-09-30 against the committed integrated tree at `96a6181`.
No local tests/builds, live calls, deployment or push. This addendum updates
rather than reopens the findings above.

| Finding | Current source status |
| --- | --- |
| P1 stable 100%-serving containment and successful deployment provenance | Open: prerequisite remains `check_observability.py` settings-only; no deployment/run/SHA/version pin. |
| P1 private sink trigger/capability attestation | Open: `96a6181` makes `--mode sink` executable, but still checks only settings/script-settings. |
| P2 owner-array completeness and detail identity | Resolved in source by `71e6036`: integer totals must equal arrays, queue ID/name must match detail. New fixtures deny mismatched ID/count. Hosted result remains unverified. |
| P2 no false resource adoption | Partially resolved: preexisting queue in `--phase queues` requires exact project-variable ID. Remaining identity/lifecycle issues below. |

### Remaining resource identity/lifecycle correction

`ensure_trace_queues.py::reconcile` discards the successful create result, then
freshly selects by name. It does not bind readback to the ID of the actual
created object. Also `--phase readback` does not check either reviewed ID.
Thus a name-preserving resource replacement can pass final ownership/settings
checks without the reviewed identity; this is conditional on replacement, not
an allegation of existing drift. Pin IDs obtained from successful creates
through that operation, and require reviewed IDs in subsequent readback.
Do not automatically save an unverified name-selected ID as creation evidence.

The first pass also creates an absent DLQ before inspecting a conflicting
preexisting main queue. Trigger: DLQ absent, main queue present but its reviewed
ID missing/wrong. A POST occurs before the predictable provenance denial.
Validate **all existing target resources before any POST**, then create only
missing resources. Add hosted fixtures for this mixed absent/conflicting case
and created-ID replacement. This is a P2 bounded mutation/recovery correction,
not a request for purge or a new general provisioning framework.

### Guarded canary wiring

`c9f698d` adds only the explicit manual `staging-trace-sink-canary` dispatch on
the exact development branch. The reusable job repeats the branch restriction,
checks a closed mode set and both UUID pins, requires exact confirmation for
synthetic canary mode, runs synthetic contracts before final secret-bearing
step, and provides login credentials only for canary mode. No new substantive
wiring issue found in this narrow review. The harness's correctness is delegated
to its independent review; this is not a live privacy approval.

However, the rollout jobs introduced in `1664174` still have the branch-push
condition. `c9f698d` does **not** disable automatic sink/API deployment on push.
A source CI push is therefore still a rollout attempt. Until the prerequisite
is a real immutable successful-run/SHA/version plus stable 100% serving check,
use a non-deploying hosted path or explicitly disable deployment. Merely writing
the provenance contract in documentation is not the gate.

### Updated decision

**GO for non-deploying hosted source CI on the integrated tree; NO-GO for live
Queue creation or automatic staging rollout.** Required live gates remain:
immutable successful containment deployment evidence, stable 100%-serving API
pin before mutation, complete private sink exposure/trigger/binding attestation,
and the remaining Queue provenance/lifecycle corrections. Production has no
prior API deployment, but still requires private sink verification and ordered
first safe API deployment. Whole-record synthetic acceptance is required after
rollout; settings green alone cannot establish privacy.

## Ordered rollout correction review (`53728e2`, `97b2c47`, `031cee7`)

Static follow-up, 2026-09-30; no tests/live calls/deployment/push.

Source-resolved:
- Staging API and sink rollout now requires manual staging dispatch on the exact
  branch and `RUN_STAGING_TRACE_SINK_ROLLOUT`; branch push no longer deploys these
  two services. Other pre-existing staging jobs are outside this narrow change.
- The prerequisite validates successful exact GitHub run, workflow/branch/SHA,
  successful unique API deploy job, one emitted version ID and historical safe
  config. `031cee7` rejects mutable rerun identity (`run_attempt != 1`). It then
  requires stable sole 100% serving version and both effective safe settings.
  Sink rechecks after deploy, and API rechecks before migration/deployment.
- Existing Queue IDs are checked before missing resources are created;
  successful POST identities are captured and pinned through fresh inventory
  and detail. Readback now checks reviewed IDs in all phases. Authorized
  operation IDs pass via step/job outputs to the dependent API job. No
  overwrite/delete/purge or raw payload read is added.

### Required hosted-test fixture correction

`infra/tests/test_require_trace_containment.py::ContainmentTests.responses`
claims its historical TOML is safe but omits `head_sampling_rate = 1.0` and
`redact_query_string = true`. The imported actual `safe_settings` rejects it.
Consequently `test_exact_evidence` deterministically raises
`source_privacy_unverified`. This is source-derived, not locally executed.
Fix the fixture to express the actual contract; do not loosen the production
privacy verifier to make the fixture pass. Infra implementer has been notified.

### Remaining gates / bounded refinements

Full private sink exposure/trigger/exact-bindings verifier remains open at the
reviewed committed source. Prior P1 remains until its independent source review.

The CI gate passes dispatch strings through raw `${{ inputs.* }}` interpolation
inside shell double quotes. Python's input validation happens after shell
expansion. Transport run/version values via step environment variables instead
so numeric/UUID contracts are enforced before any value can be interpreted as
shell syntax. This applies to the three new containment calls; no general
unrelated workflow rewrite is requested.

Identity validation precedes POST, but existing-resource owner arrays/counts
are still checked only after missing-peer creation. For complete pre-mutation
ownership attestation, read existing details first and validate them before
POST. A reviewed ID with attachment drift plus an absent peer otherwise causes
avoidable partial creation. Existing resource settings/ID and post-create
readback protection remain sound.

### Decision at this revision

**Fix the deterministic fixture before hosted source CI; no live provisioning
approval yet.** The previous automatic rollout/created-ID findings are closed
by actual source changes, not restated as blockers. Remaining live prerequisite
is full private sink attestation, hosted green integrated tests, successful
containment evidence accepted by the exact gate, and the bounded pre-mutation
ownership refinement. Queue schema/provider-shape failures must stop and be
classified; no blind rerun or adoption is authorized.

## Final infra-specific correction check (`282596e`, `0e50c35`, `c9fe9c9`, `f62b11b`)

Static review, 2026-09-30. No local test/build, live call, deployment or push.

The earlier infra-specific corrections now have coherent source implementations:
- Historical fixture includes the mandatory sampling/redaction fields.
- Run/version data are supplied in the intended staging job environments and
  referenced as quoted environment variables, not shell-expanded expressions.
- All preexisting resource attachment/count/identity details are validated with
  GET before creating any missing peer. The new foreign-consumer fixture asserts
  exactly a detail GET and no creation.
- Created IDs pass to both sink and API readback in that authorized workflow.
  Independent canary supplies separately reviewed project variables.
- First-attempt-only evidence check remains (`031cee7`).

### New P1 workflow syntax regression to correct before CI

`282596e` also accidentally inserted `AMAIL_TRACE_CONTAINMENT_RUN` and
`AMAIL_TRACE_CONTAINMENT_VERSION` at six-space indentation inside the
`detect-release` job's `steps` sequence, immediately after step `env.GH_TOKEN`
and before eight-space `shell`. These two mapping keys terminate/mix with the
sequence at the wrong level. The workflow cannot be parsed as valid YAML.
Remove those unrelated inserted lines; keep only the two intended staging job
`env` placements. This was established by direct source inspection, not a local
parser/test execution. Implementer and root were notified immediately.

No prior resolved Queue finding is reopened. **Hosted source CI is NO-GO only
until that deterministic syntax regression is fixed; afterward the reviewed
infra/provenance changes are GO for non-deploying hosted source CI.** Full sink
private exposure/trigger/bindings checker is still separately in progress, so
**live Queue creation/rollout remains unapproved** pending that source review,
actual hosted green result and accepted immutable containment evidence. Canary
wiring remains a guarded manual path, not an automatic privacy approval.

## Queue API and recovery review (`813869e`, `f56d244`, `2627983`)

Static review, 2026-09-30. Also accounted for `ae8fb14`, `da75085`, `701d8d9`
and the latest committed rollout wiring. No local tests/builds, live calls,
provisioning or push. Concurrent uncommitted strict-sink edits are outside this
infra verdict and remain with their independent reviewer.

### Source assessment

- `ae8fb14` removes the misplaced release-gate YAML keys; the deterministic
  workflow syntax finding is closed by inspection of the exact correction.
- The official Cloudflare Python SDK independently confirms bare Queue list is
  `SyncSinglePage`, create accepts `queue_name`/optional jurisdiction, and partial
  settings update is PATCH. `813869e` does not invent paging parameters;
  bounded response, unique identities and contradictory pagination/truncation
  guards retain fail-closed behavior.
- `f56d244` uses name-only POST then settings PATCH **only on the exact ID just
  returned by that POST**. Existing resources are read/attested but not updated.
  Both resource identities and ownership are validated before peer creation.
- `2627983` records only realm, fixed queue name and exact fresh Queue ID before
  PATCH, in a mode-0600 workspace `.temp` file. Always-upload uses an exact path
  and three-day retention; no credential, provider body or Queue payload is in
  the artifact. Actions artifacts inherit repository access rules: mode 0600
  does not make an uploaded artifact a secret store. These non-secret resource
  IDs are intentionally operator recovery evidence, not private mail data.
- The sink deploy helper captures provider output privately and propagates the
  sole generated version to `AMAIL_EXPECTED_TRACE_SINK_VERSION`; Queue step IDs
  enter the same checker call. Interface matches the strict checker names.
  Independent canary uses reviewed project Queue IDs. Staging API/sink remain
  manual-only; immutable first-attempt successful containment evidence and
  stable100 checks remain in place.

### P2: recover cannot inspect the exact failed-PATCH partial state

`ensure_trace_queues.py::reconcile` requires `bounded_queue(row)` before exact
ID/detail validation in **all** phases, including `recover`. If name-only POST
succeeds and PATCH fails/not-applied, the newly recorded queue keeps provider
default retention rather than 86400. Recovery rejects it at the initial
inventory with `queue_settings_drift`, never performs its exact-ID detail GET,
and cannot distinguish pending settings from identity/attachment drift. This
is the very interruption the new recovery artifact is intended to resolve.
The existing partial-recovery test models only already-correct retention.

Correction: for read-only recovery, validate exact reviewed identity first,
then GET its detail regardless of retention drift and classify it with fixed
non-ready categories. Do not return provisioning/readiness success for pending
settings, do not POST/PATCH/DELETE, and do not print raw settings or payloads.
Add a default-retention/failed-PATCH synthetic fixture asserting GET-only and
explicit non-ready classification. Normal queues/readback phases must retain
strict one-day gating. Implementer/root have been notified.

### Decision

**GO for non-deploying hosted source CI in this infra scope.** No known remaining
syntax or fixture failure is asserted; only actual hosted execution can prove
that. **NO-GO for live Queue creation at this revision** until failed-PATCH
recovery is usable, the strict-sink source review is GO, hosted integrated CI is
green and actual containment evidence passes the exact gate. Source agreement
with documented API shapes is not a live permission/provider-response proof.
No settings/ownership result alone grants whole-record privacy approval.

Additional official sources retrieved independently:
- [Cloudflare Queue SDK resource](https://github.com/cloudflare/cloudflare-python/blob/main/src/cloudflare/resources/queues/queues.py).
- [Create parameter schema](https://github.com/cloudflare/cloudflare-python/blob/main/src/cloudflare/types/queues/queue_create_params.py).
- [PATCH parameter schema](https://github.com/cloudflare/cloudflare-python/blob/main/src/cloudflare/types/queues/queue_edit_params.py).
