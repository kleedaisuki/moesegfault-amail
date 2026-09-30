# Independent Worker project-cache v2 review

## Scope and decision

Reviewed `798f92817343f7a2ffe14600f44d4e458e32dcd5`, particularly `infra/ci/worker_cache_key.py`, its new contracts, and all three `.github/workflows/ci.yml` hunks. Read the original `99347db` review and measured iteration document first, then the Worker job, structural extractor, workspace manifest and boundary package scripts. No local builds, executable tests, dependency installation or live operations were performed.

**GO for hosted source checks of the current literal build recipe. One P2 correction is required before claiming that arbitrary runtime-dependent build layout fails closed.** No evidence establishes a stale output in the current recipe; this review is not a cache-hit measurement or production/privacy acceptance.

## P2: blanket step-condition removal accepts runtime-dependent build setup

Location: `infra/ci/worker_cache_key.py:79`, followed by expression validation at lines 80–85.

`workflow_contract()` removes every indented single-line `if:` before validating dynamic execution metadata. This intentionally accommodates the present cache/install/save guards, but also removes conditions on arbitrary compilation/setup steps. For example, inserting the following step into the synthetic fixture is accepted by inspection of the control flow:

```yaml
      - name: Select main-only linker setup
        if: ${{ github.ref == 'refs/heads/main' }}
        run: echo 'RUSTFLAGS=-C target-cpu=native' >> "$GITHUB_ENV"
```

The source-only key is identical across runs of that same revision on the two trusted push branches, even though the step executes only on one branch. The whole condition is hashed, but its resolved value is not. A bracket-form `inputs['flags']` step condition similarly evades the earlier dotted-input check and is then removed. This violates the stated rule that runtime-dependent build inputs disable reuse. Cargo can independently rebuild many changed-flag cases; this finding does **not** assert Cargo produces wrong code for the example. It identifies a concrete unsupported-layout acceptance path that the newly introduced guard promises to reject.

Remedy: isolate the job predicate separately, then validate step predicates instead of deleting them all. Permit only the exact present orchestration predicates attached to the pinned-bundler install and the two cache-save steps (or explicitly model those predicates); any other runtime-dependent build predicate must produce the unique unsaved miss. Add synthetic branch-dependent setup and bracket-input condition fixtures. Keep the whole raw Worker block hashed.

Confidence: high from direct regex/control-flow inspection. Impact is conditional on adding runtime-dependent setup; the current literal recipe remains usable for hosted source verification.

## Sound boundaries observed

* Unrelated dispatch choices and plain sibling jobs are excluded from the projection; the strict shared extractor bounds the Worker job at the actual sibling header. Duplicate/unsupported shallow layout fails closed.
* Entire Worker job source and inherited permissions are bound. Global env/defaults and unknown top-level settings reject reuse. Runner selection, checkout, toolchain setup, shell/defaults at job scope, command arguments, C/compiler fingerprint logic and cache/write policy are within the projection.
* Cargo manifests/lock, complete crates/workers trees, boundary-test tree and both helper/extractor implementations are bound by committed Git object identities. Optional root Cargo/toolchain settings are absence-bound. The current hosted checkout has no tracked-source-mutating setup step before fingerprinting; the boundary package has no install script. Git identities intentionally are not a guarantee for arbitrary dirty worktrees: the documented clean-checkout precondition matters.
* Unsupported reads/layouts return UUID-suffixed keys with `cacheable=false`; no shared fallback or exception/source output is emitted. The SHA-256 payload uses ordered JSON structure and validates complete identity membership; fixed hash/key lengths stay well below GitHub's 512-character limit. Its own saved keys cannot form longer prefix variants of another valid key.
* PR/manual runs still cannot save either cache. Explicit successful trusted-push cache saves remain after all Worker tests/checks/bundles; unsupported project inputs cannot save the target cache. Secret-free paths and independent branch cache scope preserve the existing trust model.
* The v2 target cache remains exclusively in the source-check job. Deploy jobs do not consume it. Actual Rust assertions, Wasm checks, bundling and workerd tests are not skipped on a project-cache hit. The existing pinned public bundler cache remains separate and unchanged.

## External contract

[GitHub dependency caching reference](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching) documents immutable cache entries, exact and prefix matching, the 512-character key maximum, and branch/base/default read scopes. It also warns that PR readers can retrieve cache content; only secret-free build outputs/tools belong in these paths. Static review does not establish actual cache restoration, latency or runtime-expression behavior on the hosted runner.

## Hosted follow-up

Run normal hosted source checks and the new helper fixtures. Correct the condition validation with focused hosted fixtures before presenting dynamic layout rejection as complete. Seed v2 once through a successful trusted source push, then use the next natural unrelated diagnostic/doc revision to observe exact target-cache reuse and retained assertions; do not introduce a deployment or live acceptance operation solely to measure cache timing.

## Correction follow-up: bb91d98

Reviewed `bb91d98d6ce8ab63c48132f3ff4c70eb086e4184` without executing local tests. Exact named-step guards and expected operations close the original named-step example. However P2 is **not yet resolved**: `execution_without_cache_guards()` detects only lines matching `^ +if:`. Standard GitHub step syntax can place the condition first:

```yaml
      - if: github.ref == 'refs/heads/main'
        run: echo 'RUSTFLAGS=-C target-cpu=native' >> "$GITHUB_ENV"
```

The first line is `- if:`, not `if:`. It therefore bypasses the condition detector; GitHub's implicit condition expression has no `${{ }}` for the later expression validator and no uppercase `GITHUB_*` token. The conditional build setup remains cacheable by the same direct control-flow reasoning. Reject step-first conditions (and any unsupported condition layout) before projection, retaining only the exact named-step orchestration forms. Add an implicit branch condition and bracket-input variant in that standard step-first layout. Hosted source checks are still permitted, but dynamic fail-closed contract GO remains withheld until corrected.
