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
