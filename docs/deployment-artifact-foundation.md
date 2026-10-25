# Checked build artifacts

Build Worker trees once in the credential-free hosted producer. The default deploy
path requires full Worker acceptance and the same run's build. Restore its
immutable artifact before secrets, migration, resource or code mutation; never
rebuild supposedly identical Rust/Wasm during deployment. The explicitly reviewed
promotion path below reuses original checked bytes across runs without weakening
their identity or treating a failed writer as successful staging acceptance.

The workflow selects the immutable artifact ID. Its manifest binds source SHA,
run/attempt, Rust compiler, worker-build version, generated trees and every file
hash. Use infra/ci/worker_artifact.py and
actual workflow outputs. A caller manifest, cache hit or partial native pass is not
admission. Mail/sink recheck before submit; changed/missing/extra bytes are refused.

## Reviewed cross-run promotion

Successful source checks and successful deployed acceptance are different facts.
A deployment run that fails after its source jobs succeed can remain the valid
**producer** of its tested artifacts; the writer's failed conclusion remains
failed. Production promotion additionally requires a separate successful,
source-bound real-user **acceptance** run. Keep these coordinates separate:

| Identity | What it proves | What it does not prove |
| --- | --- | --- |
| Original source SHA, run/attempt and immutable artifact IDs | Required native, Worker/Wasm, provider and packaging jobs actually succeeded; original tested bytes exist | A successful deployment or real-user journey |
| Successful acceptance SHA/run and receipt artifact | The deployed exact runtime passed the bounded real semantic journey | A new build or permission to relabel the original artifact |
| Current orchestration SHA/run | Reviewed rollout/recovery tools and applicable authority | Runtime changes are covered by old evidence |

`infra/ci/accepted_staging_artifact.py` admits only its fixed repository, branch,
workflow, first-attempt provenance and named successful source jobs. Artifact
inventories must be complete, unique, unexpired and bound to the original SHA.
The original source must be an ancestor of the orchestration checkout and the
complete runtime/build/configuration closure must match: `Cargo.toml`, `Cargo.lock`,
`rust-toolchain.toml`, `.cargo`, `crates` and `workers`. The checked-out closure
must also be clean. A commit message, version equality, cache hit, matching binary
name or an arbitrary caller receipt is not equivalent admission.

The adapter records `accepted-staging-artifact/v1` with separate producer,
acceptance and orchestration identities. It restores the original artifact under
the original source/run/compiler identity, **never edits its manifest**, then
rechecks every file hash and exact file set against both the downloaded tree and
installed generated files. `tested_worker_artifact.require_artifact` repeats this
check before each mutation. Missing or changed runtime inputs require new relevant
checks/builds, not a promotion exception. Do not turn this into a general flag for
trusting any older run.

Production requires the successful named semantic-journey job plus its downloaded
`staging-semantic-acceptance/v1` receipt. That receipt binds the original producer,
acceptance checkout/run and exact API/maintenance/sink versions. Source-gate success
alone, or a receipt from another runtime closure, cannot satisfy it. Historical
same-run manifests and controllers retain their original fail-closed contract.

### Narrow recovery and incremental verification

For the one reviewed v0.3.1 partial transition, `staging_semantic_recovery.py`
admits original run `40188956353` and its exact owned API, paused maintenance,
sink, queues and original scheduled-cohort witness. Read-only schema diagnosis
comes first. A named continuation may activate only the remaining admitted work;
it must not redeploy the API/sink, reapply an already recorded migration, repeat
the completed 31-minute wait or call the failed overall run successful. Unknown
read/write outcomes still require exact owned reconciliation, never blind replay.

Choose incremental CI by changed inputs and accepted closure, not by a desire to
make every run green. A tooling-only correction should run its affected contracts;
an unchanged runtime reuses prior native/Wasm/provider evidence. Merge or promotion
must still verify the exact accepted runtime closure, while changed site/browser
inputs receive their relevant checks. This avoids repeating green runtime suites
without silently assuming unrelated orchestration changes are safe.

Wrangler can bundle JavaScript after restoration; generated hashes do not alone
prove uploaded-byte identity. Preserve checked entry adapters/module resolution/
pinned packaging. Do not casually add --no-bundle or a packaging experiment.

## Submission and release

worker_deploy_result.submit makes one bounded Mail/sink submission. Timeout is
submit_timeout_ambiguous, not absence. UUID from failed submit is recovery metadata,
not success. Duplicate/missing UUID or oversized output supplies no target.
Serving/binding/privacy readback remains mandatory; version_captured cannot start
a dependent deploy. Lost logs/watch handles never authorize provider-write replay.

Release gates cover all five native platforms and use rust-toolchain.toml. The
default path builds/tests all five; reviewed candidate promotion can reuse the
three already-tested native executables and build/test only the two missing
targets. `infra/release/promote_candidate.py` requires the checked-in
`infra/release/accepted-candidate.json` producer/acceptance chain and unchanged
runtime closure. It verifies the original complete candidate manifest, file set
and checksums before extracting executables. Newly packaged release archives keep
the executable bytes unchanged and include `BUILD-PROVENANCE.json`, separating
original native source/run/artifact identity from current packaging source/run.
They are not represented as newly compiled binaries. The release workflow attests
the actual new archive bytes, publishes the matching Skill and `SHA256SUMS`, then
checks every public asset against that trusted manifest. Never replace tag/assets
to hide recovery or smoke failure.
[Validation](validation.md) records delivered sources/outcomes.
Recovery uses immutable owned receipts plus current readback; elapsed time is not
drain proof. See [operations](operations.md) and [bootstrap](fresh-mail-bootstrap-workstream.md).

## Unpublished CLI candidates

`infra/ci/cli_candidate.py binary` packages the existing three native CI hosts
after release-mode tests/build. Each archive contains only the executable, README
and license; its producer metadata binds version, source SHA, run/attempt, target
and checksum. `assemble` requires all three same-run producer artifacts with exact
file sets and unchanged bytes before adding the agent skill ZIP, `candidate.json`
and `SHA256SUMS`. Review artifacts stay under `.temp/ci/cli-candidate` and use
explicit `candidate` filenames. They do not create a Git tag, GitHub Release or
public download, and are not a substitute for the five-platform release gate.
The reviewed promotion path above may consume this exact bundle as provenance;
it does not retroactively make the candidate a public release or skip the two
previously unbuilt platforms.

Hosted integration should upload each matrix producer separately, download those
same-run artifacts with merge enabled, assemble once, and retain the resulting
bundle for user acceptance. Never assemble by fetching historical public assets.

## Staging email and lifecycle adapters

`infra/deploy/deploy_staging_adapter.py --component ingress|events` selects only
the v0.1.2 candidate branch, explicit staging environment and `RUN_STAGING_V012`
confirmation. It rechecks the same-run artifact immediately before its single
Wrangler submission. Ingress secrets use a restricted temporary file under
`.temp`, removed on all exits; no provider output is printed. An observed UUID
on a failed submit is only recovery metadata, never automatic replay authority.

After both exact versions are captured, `check_staging_adapters.py` accepts
`--ingress-version` and `--events-version` (or their `AMAIL_EXPECTED_*_VERSION`
environment equivalents). It brackets exact single-version serving deployments
around immutable TOML-derived bindings, sole email/Queue handlers, capture-off,
empty schedules and private public surfaces. Lifecycle Queue inventory resolves
exact staging names; main Queue has exactly the staging events consumer, its
reviewed retry/batch settings and staging DLQ; neither queue accepts unexpected
worker producers/readers. A complete account subscription inventory must contain
exactly the reviewed domain-scoped lifecycle path to that Queue. A second graph
read must match the first. No message body, dequeue, sending or acknowledgment is
performed. This is adapter acceptance, not API readiness or drain evidence.

Queue provisioning in `ensure_email_events.py` creates only after the existing
bounded Cloudflare Queue catalog positively establishes exact-name absence.
Auth/network failures, malformed/truncated inventories and duplicate identities
stop without creating a resource. This also preserves normal production behavior
while replacing the unsafe assumption that every failed Wrangler info means absent.

The mapping uses Cloudflare's [Queue consumer schema](https://developers.cloudflare.com/api/resources/queues/subresources/consumers/)
(batch timeout milliseconds and DLQ name) and its [paginated subscription list](https://developers.cloudflare.com/api/resources/queues/subresources/subscriptions/methods/list/).
Focused source/mocked-provider contracts run with
`python -m unittest discover -s infra/tests -p test_staging_adapters.py`;
`python infra/deploy/check_staging_adapters.py --source-only` needs no credentials.
