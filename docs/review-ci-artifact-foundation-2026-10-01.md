# CI/artifact foundation independent audit — 2026-10-01

## Scope and verdict

Reviewed committed main `e9a56069898f74be7cda15ad4cc9ca42f41487c4` in isolated worktree `.temp/ci-artifact-audit`. Read maintainer skill and foundation/canary ledgers before targeted workflow/helper/test inspection. No production edits, local runtime tests/builds, provider operations, or credential reads were performed. External verification used official GitHub Actions documentation and maintained rust-cache documentation.

**No demonstrated blocking correctness defect was found in the reviewed build-once, native fan-out, stable aggregate, or bounded canary artifact admission.** This is not a declaration that the entire infrastructure foundation is complete. Normal deployment/release artifact wiring and actual native tracing/privacy acceptance remain outstanding. Run evidence below was supplied by the coordinating maintainer; this audit did not independently download provider receipts or rerun hosted checks.

## Checked invariants and evidence

| Boundary | Implementation evidence | Assessment |
| --- | --- | --- |
| Single producer | `ci.yml:1562–1700` builds seven trees, uploads one artifact, exports producer artifact ID | Native consumers do not rebuild Rust. |
| Same-run consumption | `ci.yml:1703–1756` downloads by producer ID; `worker_artifact.py:context/restore` compares source, run, attempt, pinned compiler policy, bundler policy and exact generated file hashes/set | Wrong-source/run/attempt/compiler/bundler and modified/missing/extra files are explicitly covered by hosted unit-test contracts. Compiler/bundler identity is the checked workflow policy plus manifest, not a independently signed runtime compiler attestation. Do not describe this as a cryptographic supply-chain attestation. |
| All native coverage | `native_suite.py:SUITES/command/counts`; `test_native_suite.py:test_every_native_file_is_owned_once` | Eight suites own every native test file exactly once; minimum 156 tests, no fail/cancel/skip/todo. Successful exit alone is insufficient. |
| Stable fail-closed gate | `ci.yml:1758–1783`, `always()`, both dependency results must equal `success` | Build failure or absent native success cannot pass the requested Worker aggregate. Hosted first implementation failure in foundation ledger is supporting execution evidence. |
| Cache correctness | `ci.yml:CLI/worker-build` and `cache_event.py` | Rust cache excludes workspace crates and installed binaries; bundler cache key includes OS/architecture/compiler fingerprint/version. Trusted push-only saves. Cache hits are acceleration, not tested-artifact evidence. Missing/partial lookup is not mislabeled cold. |
| Original-main admission | `validated_worker_build.py:identity` | Requires completed successful CI, exact main source, complete job/artifact inventories, named mandatory jobs and unique live artifact ID. Latest-attempt provenance must then match restored manifest. |
| Current/original separation | `validated_worker_build.py:unchanged_build/prepare/restore`, `native-tracing-canary.yml` | Current hosted infra tests precede provider access. Reuse requires original build ancestor and only enumerated experiment helpers/workflow/tests or Markdown changed. Rust, lockfile/toolchain/config/native fixtures/artifact helper/CI workflow changes are refused. Original build coordinates are retained separately from orchestration coordinates. |
| Bounded iteration | `native_fixture.py`, canary workflow | Diagnostic replay is explicitly weaker and cannot promote. Canary has no new-main full-CI dependency when the narrow proof passes. Bounded missing-history or incomplete API inventory fails closed rather than guessing success. |

## Necessary remaining foundation work (not a new regression)

**Tested-byte deployment is not yet generalized.** Ordinary deployment jobs still run `worker-build --release` after source checks, for example `ci.yml:1926–1927`, `1981–1982`, `2028–2029`, `2296–2297`, `2544–2546`, and `2619–2621`. Thus source success proves tested source/build output, not that every ordinary serving deployment consumes the verified native-tested module bytes. The foundation ledger already marks deployment/release wiring pending: preserve that status. No deployment was attempted by this audit.

Practical correction: extend the fixed producer artifact-ID and strict restore path to the specific admitted deployment graph; remove Rust custom build commands from deploy configuration; preserve existing external workflow/job contracts and writer serialization. Record the original artifact identity and resulting serving version. Add hosted admission tests for wrong artifact, source, attempt, modified bytes and hidden rebuild, then one explicitly admitted synthetic/isolated hosted deployment. Do not use this audit to resume Mail or release promotion.

## Latest actual canary: acceptable limited conclusions

Coordinator evidence: full CI `36870040420` passed for current main. Actual canary `36870838693` failed in 50 seconds (13:43:46–13:44:36 UTC), while consuming original fully checked main run `36867766344`, artifact `11164304271`, source `dcc4eed6b2dd27120940d79484ae7d9ddc0cb051`, under orchestration `e9a5606`. Artifact admission, serving-version, isolation, and capture readback passed. Probe flags were true; caller observability key was specifically **missing**, the observed canonical disabled shape. Public trigger returned HTTP 403. Owned resources were deleted and GET 404 verified; cleanup time 13:44:32.718360 UTC.

That supports bounded unchanged-input reuse and tested-artifact isolated lifecycle/cleanup, not native runtime span support, parentage, redaction, retained-record absence, or end-to-end tracing. Caller code's expected aggregate status is 200, so 403 alone does not identify a native Rust API failure. Do not infer that normalized disabled settings prove observed no capture: the planned complete pair-scoped retained-record check remains necessary. No reason was found to require another full Rust/native build merely for bounded trigger diagnostics when the existing narrow unchanged-input proof still passes.

## Limits and next evidence

* Full CI/API receipts were not independently fetched; supplied run IDs are coordinates, not fresh executions by this reviewer.
* Workflow-source tests are useful regression contracts, but string matching is not equivalent to executing every failure/cancellation path.
* Full hosted runs are uncontrolled timing observations, not causal cache/performance benchmarks or an SLA.
* The external reviewed practice is platform-owned dependency graphs, immutable artifacts and compiler/environment-aware caches. No research novelty or speculative orchestration is needed to repair these foundation gaps. Advanced diagnosis/sampling remains downstream of accurate runtime evidence.
* Next discriminating evidence is bounded synthetic trigger diagnostics and complete pair-scoped collection after an admitted successful trigger; then tested-artifact normal lifecycle wiring. Preserve business hold throughout.

## Primary references

* [GitHub Actions workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax) — dependency failure/skip behavior, `always()`, matrices and concurrency.
* [GitHub dependency caching reference](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching) — cache keys, scope and security; caches are not acceptance artifacts.
* [Swatinem rust-cache](https://github.com/Swatinem/rust-cache) — compiler/environment fingerprinting and workspace-crate exclusions.

## Follow-up: bounded trigger diagnostics diff

Independently inspected uncommitted `infra/deploy/native_tracing_experiment.py` and `infra/tests/test_native_tracing_experiment.py` in `.temp/native-trigger-diagnostics`, based on main e9a5606. No production modifications or tests performed by reviewer.

No demonstrated blocker found. HTTP errors record numeric status, body prefix length/class, header names, allowlisted media type/CF-Ray, and server/challenge booleans; no cookies, Location values, challenge body or arbitrary error prose enters this added receipt path. `NoRedirect` remains in use; trigger has one `open` call and no retry. The outer `finally` writes the end of the observation window on HTTP, JSON or native-verdict failure. Four source-owned reports are retained before native acceptance checks, so unsupported native API stages no longer disappear when verdict fails. All protections remain bounded to this credential-free synthetic source-owned endpoint; they are not a general policy allowing raw application/provider responses into artifacts.

Optional but valuable pre-dispatch verification: the added test currently covers the classifier only. Hosted mocked trigger tests should cover HTTP 403, malformed JSON, four unsupported safe reports and success; assert a single `open` call, from/to persistence on failure, reports saved before rejection, and no successful invocation event on rejection. No local runtime tests are required.

Primary-source investigation did not establish that fresh Worker deployment normally causes a transient 403 or that waiting/retrying is safe. The official [Challenge Page response detector](https://developers.cloudflare.com/cloudflare-challenges/challenge-types/challenge-pages/detect-response/) identifies `cf-mitigated: challenge` and `text/html`; this supports the chosen response classification, not attribution of the observed 403. Official [workers.dev routing documentation](https://developers.cloudflare.com/workers/configuration/routing/workers-dev/) says Access can cover one deployment URL or all Workers in an account, so `workers_dev` enabled alone does not prove unauthenticated reachability. Official [403 documentation](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/4xx-client-error/error-403/) also documents unstyled 403 before domain configuration is loaded (for example SNI mismatch); therefore bare Forbidden is not a reliable origin-versus-edge classifier. These are possible boundaries to discriminate, not diagnosed causes. No Access/provider settings were inspected or changed.
