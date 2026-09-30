# Independent CI iteration review

## Scope and conclusion

Reviewed commit `99347db6cb8712c6f80696334c32c92ca88ff34f` against its parent: `.github/workflows/ci.yml`, `infra/tests/test_ci_iteration_contract.py`, and `docs/hosted-iteration-critical-path-2026-09-30.md`. Inspected surrounding check, dispatch, staging, production, and reusable-workflow call predicates, cache inputs, and workspace layout. No local builds or tests were run.

**No substantive defect found in this change. GO for hosted source CI and the documented cold/warm timing experiment; not evidence of achieved latency, successful cache restoration, privacy acceptance, or production readiness.**

## Evidence and reasoning

* All four original source suites retain their push predicates and existing PR predicates; manual `checks` adds the same suites without reaching deployment jobs. The existing project-branch PR skip is unchanged: its push supplies the heavy checks. Other PR heads retain all source checks. CLI remains a three-OS matrix; Worker assertions and workerd execution are not conditional on a cache hit.
* Only non-mutating source/check dispatches enter the new `ci-checks-${ref}` cancelable group. State-changing/manual diagnostic dispatches retain `ci-${ref}` with cancellation disabled. Existing job-level external-state locks are untouched. The ref-wide group is not a global all-branches deployment lock; this limitation predates the change and component locks still apply.
* All changed staging deployment predicates now require `workflow_dispatch` with `target=staging`. Mail API and trace sink retain their exact rollout confirmation. Production-main predicates, dependency gates, serving-pin checks, secret delivery, route/account safeguards, and release readiness logic are unchanged.
* The live synthetic embedding probe is removed only from source pushes; manual staging/production still runs it and deployment dependencies still require it. Ordinary source checks neither receive its credential nor call the provider.
* Build-cache inputs cover current Cargo root manifests/lock, complete `crates`/`workers` Git trees, workflow recipe, OS/architecture, and compiler/linker/libc version fingerprint. No root Cargo configuration, root build script, or toolchain file currently exists outside those inputs. Future additions must extend the input key as documented.
* Cache restores and saves are separated. Saves default to successful preceding steps and additionally require a trusted main/project-branch push and cache miss. PR/manual runs do not save. Worker check steps contain no secrets; paths do not include Cargo home or live fixtures. Deployment jobs do not restore these caches, so a cached check executable is not promoted as a release artifact.
* Dedicated tool installation and PATH setup are coherent: misses install pinned `worker-build` under the cached root; both hit/miss paths prepend its `bin` directory before bundling. Cargo tests execute even when compiled objects are restored.
* The new contract test is a source-level guard, not a YAML expression evaluator or hosted execution oracle. Its static assertions are useful for intended separation/cache restrictions, but hosted execution must establish actual trigger selection, cache behavior, and elapsed time.

## External contracts checked

[GitHub concurrency documentation](https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency) supports separate expression-derived concurrency groups and cancellation policy. Cancellation is limited here to checks, rather than shared-state mutations. GitHub concurrency does not guarantee FIFO delivery of pending work; the change does not claim otherwise.

[GitHub dependency caching reference](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching) documents branch/default/base cache scope and that caches are accessible to PR readers. Cached paths therefore must remain secret-free. There are no fallback keys in this change. GitHub can still consider a primary-key prefix match: generated keys have fixed-length hash suffixes and this workflow saves exactly those keys, so its own valid entries cannot be a longer primary-key-prefix variant. Treat the caches as build acceleration, never test success or trusted release provenance.

## Required hosted follow-up

Run push checks for this immutable source revision; confirm all source suites execute and all staging/provider-live jobs skip. Run a manual `checks` dispatch after successful cache saves on the same revision; record cache-hit labels, test execution, job/step times, and total elapsed time. Compiler updates, checkout timestamps, runner scheduling, cache transfer cost, or Cargo fingerprints can reduce reuse; do not turn projected 4–6 minute feedback into a claimed measurement. No new mail/Identity/route mutation is necessary for this experiment.
