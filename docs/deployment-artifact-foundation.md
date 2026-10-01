# Ordinary deployment artifact foundation

Status: source implementation awaiting hosted acceptance. This is a bounded
foundation slice, not deployment authorization or a completed lifecycle rollout.
No provider writes, accounts, user mail, secret changes or deployments were made.
The current send hold and infrastructure-first admission remain unchanged.

## Executable delivery contract

The nine ordinary Worker deployment jobs in `ci.yml` depend directly on both
`worker` (the stable full native aggregate) and `worker-build`. Each selects only
`needs.worker-build.outputs.artifact_id`, downloads into `.temp/ci/worker-built`
on its own fresh runner, and runs `worker_artifact.py restore` before any resource,
privacy, schema or code mutation. The existing producer remains credential-free.
No deploy job installs worker-build, compiles Rust or regenerates the bridge.

The original same-run manifest continues to bind exact checkout SHA, run/attempt,
Rust compiler, worker-build version, all seven public generated module trees and
every file hash. Source maps/licenses remain generated public output; guessed
extension allowlists are not reinstated. The fixed producer ID and complete
Worker gate establish admission; a self-authored manifest does not prove tests.

Mail API and trace-sink helpers additionally call `tested_worker_artifact` directly
before creating temporary secrets or submitting Wrangler. That check compares
the retained artifact and installed trees, rejecting post-restore rebuilds,
changed/missing/extra files or changed source/run/compiler identities. Other
ordinary consumers restore before their existing single deployment submission.
The isolated `validated_worker_build` ancestry exemption is not imported or used
by any ordinary deployment. A new checkout/run requires its own complete CI.

`release.yml` now selects `rust-toolchain.toml` rather than mutating floating
stable. Its existing five-platform release build/test, fixed archive consumption,
assembly checksums and published-byte comparison remain unchanged. This is not
cross-run CLI binary reuse: release platforms still produce and test their own
exact-compiler archives, which assembly/publishing never rebuilds.

## One-attempt diagnostics and recovery boundary

`worker_deploy_result.submit` owns one bounded 600-second Mail/sink submission.
It emits source/run-correlated control-plane records with the observed exit code,
version count, exact valid version and source-owned failure reason. Timeout is
explicitly `submit_timeout_ambiguous`; process creation failure and output bounds
are distinct. It does not invent an HTTP status for opaque Wrangler output.
Provider output, command arguments containing secret paths, exception text,
credentials and arbitrary response strings never enter diagnostic events.

A unique UUID printed with a failing exit is captured as recovery metadata for
both Mail and sink. The operation still fails. A duplicate/missing UUID or output
beyond the bound supplies no target. Neither submission, failed readback nor
diagnostic-stream failure retries a provider write. Existing downstream serving,
immutable capability/privacy and held-send readbacks remain authoritative;
`version_captured` alone is not readiness. A failed sink step cannot start its
dependent Mail step merely because it emitted recovery metadata.

## Lifecycle boundaries that are still open

| Concern | This slice | Required next evidence |
| --- | --- | --- |
| Same checked generated inputs | Same-run producer, full gate, verified restore; Mail/sink recheck immediately before submit | Hosted source/native acceptance, then an explicitly authorized provider lifecycle exercise |
| Writer exclusion | Existing production workflow-level graph writer lock and staging lane locks preserved; no nested same-lock deadlock | Audit every future lifecycle writer and keep dependent shared-lock jobs serialized |
| Paused/active | Existing API empty-Cron invariant and pure `mail_split_transition` state model preserved | Independently admitted predecessor record and protected transition runner with actual trigger/graph readback |
| Drain | No age-based or environment-only admission added | Old-work end evidence; uncertain drain must remain paused, not infer completion from elapsed time |
| Rollback | No blind automatic rollback or submit replay introduced | Exact prior serving deployment + compatible resources/schema + unchanged schedule, readback, bounded recovery |
| Packaging bytes | Original generated trees preserved and rechecked; existing pinned Wrangler packaging unchanged | Credential-free hosted dry-run/package comparison before claiming uploaded module byte identity |

Wrangler's final packaging remains an explicit limitation: it is not Rust/Wasm
recompilation, but it can bundle JavaScript. Cloudflare documents `--no-bundle`
for preprocessed code; changing to it also changes module discovery/base directory
and must be validated against the composed Mail entry adapter and generated Wasm
imports. Do not silently add that flag or claim provider-uploaded byte equivalence
from hashes of pre-packaging generated files. The next source step should compare
credential-free pinned-Wrangler dry-run output with the tested generated module
set and exercise the exact packaged tree in hosted native fixtures.

The preserved unfinished worktree
`.temp/scheduled-only-product-split-impl` contains an early split record/release
prototype. Its single-Wasm digest, release extension allowlist and prepare-run
authority are narrower/different than today's accepted seven-tree full-CI artifact
contract. They are useful findings, not an ordinary release admission. No dirty
changes there were overwritten, cherry-picked or treated as acceptance.

## Validation plan and evidence ledger

All execution belongs to GitHub Actions. Local checks are syntax and diff only.
Hosted contracts cover exact/wrong source/run/attempt/compiler/bundler; intact
original versus changed/missing/extra installed modules; rejection before secret
material and Wrangler; one-attempt failure/timeout; useful exit/version facts with
poison output excluded; every ordinary job's gate/artifact/order/no-rebuild; and
release compiler plus unchanged checksum/published-byte verification.

The PR checks cannot exercise protected deployment jobs, and a full native pass
cannot prove actual readback/drain/rollback or uploaded module byte identity. Keep
those rows open even when source CI turns green. Hosted run/source coordinates
will be recorded after the first accepted source run.

## Primary references

* https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-what-your-workflow-does/storing-and-sharing-data-from-a-workflow — immutable artifacts and dependent producer/consumer jobs.
* https://github.com/actions/download-artifact — select immutable artifact IDs, not arbitrary latest artifact names.
* https://developers.cloudflare.com/workers/wrangler/bundling/ — final bundling versus explicit no-bundle for preprocessed artifacts.
* https://developers.cloudflare.com/workers/wrangler/configuration/ — module discovery, rules and base-directory semantics.
* https://developers.cloudflare.com/workers/versions-and-deployments/rollbacks/ — rollback is not schema/data/resource rollback; compatibility must be established separately.
