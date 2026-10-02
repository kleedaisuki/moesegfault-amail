# Checked build artifacts

Build Worker trees once in the credential-free hosted producer. Deploy jobs depend
on full Worker acceptance and the same run's build. Restore its immutable artifact
before secrets, migration, resource or code mutation; never rebuild supposedly
identical Rust/Wasm during deployment.

The workflow selects the immutable artifact ID. Its manifest binds source SHA,
run/attempt, Rust compiler, worker-build version, generated trees and every file
hash. Use infra/ci/worker_artifact.py and
actual workflow outputs. A caller manifest, cache hit or partial native pass is not
admission. Mail/sink recheck before submit; changed/missing/extra bytes are refused.

Wrangler can bundle JavaScript after restoration; generated hashes do not alone
prove uploaded-byte identity. Preserve checked entry adapters/module resolution/
pinned packaging. Do not casually add --no-bundle or a packaging experiment.

## Submission and release

worker_deploy_result.submit makes one bounded Mail/sink submission. Timeout is
submit_timeout_ambiguous, not absence. UUID from failed submit is recovery metadata,
not success. Duplicate/missing UUID or oversized output supplies no target.
Serving/binding/privacy readback remains mandatory; version_captured cannot start
a dependent deploy. Lost logs/watch handles never authorize provider-write replay.

Release builds use rust-toolchain.toml, build/test five platform archives and
publish exact bytes plus skill bundle and SHA256SUMS. Check public bytes against
the original manifest. Never replace tag/assets to hide recovery or smoke failure.
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
