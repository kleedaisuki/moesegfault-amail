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
