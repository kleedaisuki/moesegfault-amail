# CI source scope and observed waiting latency

Status: real hosted scoped path accepted; selector source still requires its
full PR checks. This is not deployment, release or native Cloudflare runtime
acceptance.

## Workload and decision

The infrastructure foundation prioritizes short synthetic orchestration repair
loops without rebuilding unchanged Rust or executing unrelated native suites.
The existing PR selector already skips builds for ordinary infrastructure Python
changes. Its blanket workflow/`infra/ci/` classification still made isolated
canary/fixture orchestration changes select CLI, Worker and Astro unnecessarily.

Keep the existing GitHub Actions dependency graph and exact artifact contracts;
add only three reviewed non-build paths to `pr_scope.INFRASTRUCTURE_ONLY`:

| Path | Actual consumer and mandatory validation |
| --- | --- |
| `.github/workflows/native-tracing-canary.yml` | Isolated manual experiment/readonly diagnosis; hosted `test_native_tracing_experiment.py` and independent workflow syntax guard |
| `.github/workflows/native-fixture.yml` | Manual diagnostic replay; hosted `test_native_fixture.py` and independent workflow syntax guard |
| `infra/ci/native_fixture.py` | Replay orchestration and bounded GitHub metadata reader; hosted replay/admission contract tests |

This is a consumer distinction, not a glob exemption for workflows/Python. The
selector itself, `ci.yml`, release/standalone deployment workflows,
`validated_worker_build.py`, `worker_artifact.py`, `native_suite.py`, cache policy,
and unknown/shared/compiler inputs remain full. Worker/native fixture/package/
lockfile edits still select the Worker build and **all** native suites. Mixed
changes retain the union of their actual consumers. Additions and deletions are
handled by the same complete committed-path rule; there is no trusted cache hit
or test-history prediction involved.

The unconditional infrastructure job and independent workflow syntax guard still
run on every eligible PR. Push/main and manual checks/deployment remain full;
main source artifact admission still requires complete successful exact-source
jobs. No producer, stable `Rust Worker (Wasm)` aggregate, artifact restoration,
ancestor exception, provider capability, release acceptance or deployment byte
contract changes. The selector policy change itself selects full checks.

## Observed baseline, 2026-10-01 UTC

PR 57 head `91f4679e8a4569c6801ff02b86b0419ecd2e7248`, source run
[36876190933](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36876190933),
changed exactly canary workflow, experiment helper, its tests and canary docs.
It passed, but selected every compilation consumer. Existing PR 56 head
`57719776c70314c3bd277d6d0135269be6f7d72f`, run
[36873611752](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36873611752),
changed infrastructure Python/docs without a workflow and already used scoped CI.

| Observed interval | Full PR 57 | Existing scoped PR 56 |
| --- | ---: | ---: |
| Workflow created to updated completion | 322 s (14:25:17–14:30:39) | 29 s (14:05:25–14:05:54) |
| Scope selection job | 6 s | 5 s |
| Mandatory infrastructure job including setup | 27 s | 22 s |
| Worker producer including setup | 112 s | Not selected |
| Core native job including setup | 180 s | Not selected |
| Actual complete core native execution step | 167 s | Not selected |
| Stable Worker aggregate job | 2 s | Not selected |

PR 57 critical path: 7 s initial queue; scope job 6 s; 5 s producer scheduling;
112 s producer; 4 s native scheduling; 180 s core; 4 s aggregate scheduling;
2 s aggregate; 2 s workflow finalization. Whole-run timestamps include scheduling
and lifecycle overhead and are not sums of concurrent jobs.

The core native job spent about 13 s outside its real 167 s test execution;
producer dependency restoration was 11 s, Wasm target setup 9 s, and main Mail
bundling 36 s. Setup/cache tuning cannot remove the dominant core execution wait.
Skipping that job is justified **only** for changes with no native consumer;
actual native source/test changes continue executing it. Do not shorten timing
tests, fake timers or infer passing behavior from the original artifact/cache.

These are uncontrolled GitHub-hosted observations (one sample per baseline), not
paired benchmarks, confidence intervals or a latency SLA. Workloads, source,
runner allocation and cache state differ. The useful causal evidence is the job
graph and actual step durations, not a claim of a universal 11x speedup.

## Reproduction and source boundaries

Use GitHub metadata without launching provider operations:

```powershell
gh pr view 57 --json files,headRefOid
gh api repos/kleedaisuki/moesegfault-amail/actions/runs/36876190933
gh api 'repos/kleedaisuki/moesegfault-amail/actions/runs/36876190933/jobs?per_page=100'
gh api repos/kleedaisuki/moesegfault-amail/actions/runs/36873611752
gh api 'repos/kleedaisuki/moesegfault-amail/actions/runs/36873611752/jobs?per_page=100'
```

Job/step duration is `completed_at - started_at`; workflow wall time here is
`updated_at - created_at` for completed runs. Raw metadata is stored in this
task's repository-local `.cache/ci-latency/`. No local runtime/project tests,
builds or toolchain installs are part of this investigation.

Hosted selector contracts reproduce PR 57's exact changed-path shape, verify
each exact exemption, and reject nearby unknown, source/admission, compiler,
package/lockfile and mixed-consumer changes. Existing malformed/truncated/
unreadable Git diff/event and non-PR fallback tests remain required. A source-only
stacked probe may vary only a canary workflow comment to exercise the real hosted
PR event; it supplies no main/release acceptance and is closed without merge.

## Actual scoped-path probe

Measurement-only [PR 61](https://github.com/kleedaisuki/moesegfault-amail/pull/61)
used base selector source `0778bc90ad15248ab9f25d02fb5a1d34e5d8f0ec` and head
`524cf36cb2d3e96d2a06a392467838ed8ada97d4`. Its entire PR diff was one comment
in `native-tracing-canary.yml`; no code, runtime/provider behavior or compiler
input changed. Actual hosted CI
[36878536461](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36878536461)
passed in **33 s** (14:43:05–14:43:38 UTC), including a 5 s scope job and
25 s mandatory infrastructure job. Independent syntax
[36878536119](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36878536119)
passed in 13 s (14:43:05–14:43:18). CLI, producer, all native suites and Astro
were actually skipped; provider/deploy jobs were also skipped. Hosted
infrastructure executed the real encrypted recovery and synthetic Python/
source/admission/privacy contracts, not an empty replacement check.

The probe was closed without merge after collecting run/job metadata. Its branch
is retained for reproducibility. It is not trusted-main source CI, full native
acceptance or deployment/release artifact admission. Compared with the historical
322 s workflow-shaped orchestration baseline, this confirms removal of the
unrelated 112 s producer + 180 s core critical path. The 289 s wall-time
difference is an observed workload-specific contrast, **not** an equivalent
paired benchmark or performance promise. A single sample cannot estimate tail
latency or variance. Selector negative/mixed guards and final full source checks
remain the correctness evidence; speed alone cannot justify skipping tests.

## External rationale

GitHub's production mechanisms already provide job conditions, immutable
artifacts, matrix concurrency and cancellation. Keep scope as a small reviewed
consumer list rather than replacing them with another orchestration/cache layer.
The [workflow syntax reference](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
explains failed/skipped `needs` propagation and the `always()` guard; the stable
aggregate must continue failing on missing required native coverage when selected.
The [required-check guidance](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)
distinguishes skipped workflows (pending) from conditionally skipped jobs. Do not
replace mandatory PR infrastructure/syntax checks with whole-workflow path skips.

The peer-reviewed [build-system-aware multi-language regression test selection
study (ICSE-SEIP 2022)](https://doi.org/10.1145/3510457.3513078) identifies build
dependencies as the relevant cross-language selection boundary. Recent
[Targeted Test Selection research (2025 preprint)](https://arxiv.org/abs/2509.10279)
explores learned changed-file selection without coverage maps; its reported
failure detection is not complete. Such prediction is not appropriate release
proof here. Exact small consumer boundaries plus full trusted-main gates offer
the useful waiting reduction without learning/instrumentation complexity or
weakening artifact admission. No academic novelty is claimed.
