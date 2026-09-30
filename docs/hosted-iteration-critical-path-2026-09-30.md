# Hosted iteration critical path and bounded improvement

## Question and workload

The goal is to shorten **source-change feedback** on GitHub-hosted runners without moving tests onto the developer workstation, weakening release/live-mail/privacy gates, or silently replacing a serving Worker during an acceptance run. This is distinct from shortening one-shot SMTP/Identity/provider observation: those operate on shared external state and remain serial where required.

Evidence was read from the GitHub Actions run and job APIs on 2026-09-30. No local tests, builds, dependency installs, sends, or deployments were performed for this investigation. All times below are UTC. `run_started_at` is not a usable queue measure here: it equals run creation even when no job starts for minutes. The operational wait is creation to the first **non-skipped** job start. Job times include setup/post steps.

## Observed baseline

| Push run | Created | First active job | Workflow updated | Observed wait | Worker job | Dependent deployment tail | Total |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [36728726698](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36728726698), `b536963` | 14:23:18 | 14:23:22 | 14:34:56 | 0:04 | 7:19 | 4:13 failed API deploy | 11:38 |
| [36732054850](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36732054850), `3ae8ed5` | 14:49:47 | 14:49:50 | 14:59:23 | 0:03 | 5:51 | 3:41 role monitor | 9:36 |
| [36734170513](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36734170513), `34db41a` | 15:06:16 | 15:11:18 | 15:22:08 | 5:02 | 7:15 | 3:34 private inbox | 15:52 |

The tail includes scheduling gaps from Worker completion to dependent job start. These are three different revisions and runner allocations, **not a controlled repeated benchmark**; report ranges rather than statistical confidence intervals. Worker time ranges 5:51–7:19, median 7:15. The latest run's critical path is approximately:

```text
5:02 wait -> 7:15 Worker checks/bundles -> 0:04 scheduling -> 3:29 inbox deploy
```

The latest Worker job spent 2:09 installing `worker-build` (15:13:58–15:16:07), 0:38 bundling the privacy sink, and 1:17 bundling the API. Its actual workerd assertions took 0:09. The downstream inbox job then spent **another 2:24** installing Rust bundler/Wrangler and 0:32 compiling a Worker that the upstream job had already bundled. Role monitor tool installation took 2:02. Site checks took 0:23, infra 0:19, and the Windows CLI job 2:08: none explains the long critical path.

There was also a distinct [duplicate push run 36732055983](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36732055983), with the same SHA/event/workflow ID as 36732054850. It started active jobs at 14:59:27, after the first run completed at 14:59:23, and completed at 15:11:15. The new revision's first jobs started three seconds later. This directly accounts for the new run's five-minute wait behind obsolete work. The API does **not** prove what client action caused the duplicate trigger; do not attribute it to a specific actor/tool bug without further evidence. PR counterpart runs lasted approximately three seconds and skipped the test suites, so they were not duplicate heavy compilations.

### Reproduction

```powershell
gh api repos/kleedaisuki/moesegfault-amail/actions/runs/36734170513
gh api 'repos/kleedaisuki/moesegfault-amail/actions/runs/36734170513/jobs?per_page=100'
```

Use only `id`, `event`, `head_sha`, `created_at`, `updated_at`, job names/start/end/conclusion, and step names/start/end. No retained Worker logs, user content, credentials, or mailbox data are needed. Repeat for the run IDs in the table and duplicate run above. Compute durations by subtracting ISO timestamps, not parsing formatted display strings.

## Causal explanation

1. **Unnecessary shared lane:** all push checks and manual mutations used `ci-${ref}`, with push cancellation disabled. An obsolete/duplicate source run queued behind and blocked newer feedback and diagnostic dispatches.
2. **Unrelated staging mutations per push:** API deployment had already been manually gated for privacy containment, but source pushes still replaced site, role-monitor, and private Identity inbox Workers. Their deployment tail was unrelated to source-test feedback, could invalidate serving-version evidence, and consumed the same lane.
3. **Repeated cold tools:** `cargo install worker-build --locked` compiled the public tool in each fresh runner. This is measured wasted setup, not an assertion that the mail algorithm itself is slow.
4. **A deliberately broad source suite:** all Rust/Wasm packages and all supported CLI OSes still run. That coverage is currently valuable; the first improvement does not attempt uncertain change-impact selection.

Personal root-agent review can add orchestration delay, but the measured sixteen-minute hosted run is machine queue/build/deployment time, not sixteen minutes of root-agent inspection. Contract-derived tests and specialist review should supply evidence directly; root integration should not re-run completed checks without a failure that implicates them.

## Implemented source design

* Push/PR become **non-deploying source checks**; explicit `target=checks` offers the same manual non-deploying path. Full original CLI/Worker/site/infra contracts still execute. OpenRouter synthetic live contract runs on explicit staging/production promotion, not on ordinary pushes.
* Check runs use a separate `ci-checks-${ref}` concurrency group and cancel obsolete checks. Manual state operations retain the existing `ci-${ref}` group and do not cancel in-progress work. Their job-level locks, exact confirmations, serving pins, route absence checks, account gates, privacy boundaries, and production-main guards are unchanged.
* The secret-free Worker **check job only** restores two exact caches: compiled `target` keyed by OS/architecture/full Rust/C compiler/libc fingerprint and Git trees/blobs for workspace source inputs and workflow build commands, and a pinned 0.8.5 `worker-build` dedicated install root keyed by OS/architecture/toolchain. There are no partial/fallback keys. Tests always execute, even on cache hits; Wasm bundles and workerd assertions are not skipped.
* Cache writes are explicit and limited to successful trusted `main`/project-branch push checks after all Worker contracts and bundles. PR/manual check/promotion runs cannot save these caches. No Cargo home, credentials, `.temp`, live diagnostics, or user data is cached. All deployment jobs still build independently and do not consume cached project bundles: a check cache is not a release artifact.
* `infra/tests/test_ci_iteration_contract.py` makes the separation and cache write restrictions inspectable and regression-tested on hosted CI. New external build inputs (for example root `.cargo/config.toml` or generated inputs outside `crates/` and `workers/`) require extending the exact source key before adopting them.

This preserves manual promotion's source validation and full privacy rollout gate. It deliberately does **not** solve artifact promotion or granular component deployment in the same change; those would need separate provenance and acceptance design.

## Target and validation plan

**Not a measured after-result yet.** With the latest timings, removing the unrelated deployment tail and duplicate-run queue takes source feedback from 15:52 to approximately 7:15 plus runner setup/scheduling. A hit on the public bundler cache removes a measured 2:09 install, suggesting **4–6 minutes warm full-source feedback**, and **7–8 minutes cold** when no obsolete-run queue exists. An exact workspace cache hit can shorten unchanged-Rust/infra-only revisions further, but that gain is not assumed for actual Rust code edits. Infra/site results remain independently available in roughly 20–30 seconds plus runner scheduling. Runner congestion/cache transfer overhead can invalidate these estimates; record it rather than claiming success from source inspection.

After source review, run hosted push checks once cold and an equivalent manual `checks` run warm on the same immutable SHA, then compare job and step times, cache-hit state, test counts, and conclusions. A manual check cannot write caches. Keep mutation/deployment dispatches out of this timing experiment. Do not accept a cache-hit job that skips actual assertions. Verify source push invokes **no** staging deployment/provider-live jobs. These runs validate the design; later ordinary Rust edits measure whether the warm bundler benefit persists with a project build-cache miss.

### Hosted cold/warm source-check observations (2026-09-30)

The first non-deploying push [36738776043](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36738776043), `1e378e5`, was **not a green workflow**: Infrastructure had one historical TOML fixture error (`test_require_trace_containment.test_exact_evidence`, `source_privacy_unverified`, because the synthetic source omitted the now-required disabled Issues section). The Worker job itself passed every Rust/Wasm, bundle, and workerd assertion, and its trusted project-branch cache-save steps completed. The follow-up push [36739829040](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36739829040), `5f6778a`, changed only that infra fixture/docs while leaving the exact Worker source key and pinned bundler inputs unchanged; **all six active source jobs passed**. These are not strictly same-SHA repeated runs, but the second job reported exact hits for both cache keys created by the first.

| Source push | Created → first active job | Workflow elapsed | Worker job | Infra | Windows CLI | Cache evidence |
| --- | --- | --- | --- | --- | --- | --- |
| [36738776043](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36738776043), cold | 15:42:25 → 15:42:29 (0:04) | 7:24, **workflow failed only on infra fixture** | 7:19, passed | 0:14, failed (1/525) | 4:31, passed | exact Worker build and pinned bundler **missed**, then both saved after passing Worker contracts |
| [36739829040](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36739829040), warm | 15:50:52 → 15:50:57 (0:05) | 2:09, passed | 1:47, passed | 0:16, passed | 2:03, passed | exact Worker build and pinned bundler **hit/restored**; install and save steps skipped |
| [36742065920](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36742065920), Rust source edit | 16:08:52 → 16:08:57 (0:05) | 5:59, passed | 5:52, passed | 0:14, passed | 2:25, passed | exact Worker build **missed/saved**; pinned bundler **hit/restored**, install skipped |

All three runs executed CLI tests on Ubuntu/macOS/Windows, the full Rust Worker unit/build suite, Wasm bundles, workerd address-boundary assertions, Astro checks, and infra probes. OpenRouter live contract and **every** staging/provider mutation or deployment job were skipped on all three pushes; no serving Worker was replaced. The cold Worker still saved its cache because that job's own complete contracts passed, even though the unrelated infra job made the workflow red. This is job-scoped cache policy, not a claim that the first workflow passed.

Selected Worker step durations (cold → warm): bundled tool install **2:07 → skipped**; exact project-cache restore **0:01 → 0:13**; Rust Worker unit tests **0:48 → 0:03**; API bundle **1:15 → 0:32**; privacy-sink bundle **0:37 → 0:08**; workerd address assertions **0:09 → 0:09**. The Worker job fell by **5:32** (7:19 → 1:47), while the complete source-feedback path fell by **5:15** (7:24 → 2:09). The cold/warm comparison includes normal runner and cache-transfer variance, and the revisions differ in an infra fixture; it is evidence for the exact-key warm path, not a general speedup estimate for Rust source changes. A third manual same-SHA `checks` run is not needed to establish that these keys restore or that tests still execute. The next informative measurement is an ordinary Rust edit that misses the project build cache but hits the pinned bundler cache.

That next probe is now observed: `a30cd5d` changed Rust trace-schema and role-monitor sources, so the exact project cache correctly **missed**, while the unchanged pinned bundler cache **hit**. Its tool-install step was skipped; Worker unit tests took 1:01, privacy-sink/API bundles 0:40/1:20, and workerd assertions remained 0:09. The Worker job was 5:52 and the full non-deploying source run 5:59, both green. Relative to the cold run, total elapsed was 1:25 lower, but this is not a controlled speedup estimate: the revisions, compilation graph, hosted runner, and initial workflow conclusion differ. The useful mechanism-level result is narrower: a real Rust edit invalidated the project build cache without invalidating the independently keyed bundler cache, and all assertions still executed. It also bounds the cost of that particular source edit between the exact-cache warm case and the cold case, not all future edits.

Reproduction: read only each run's `created_at`/`updated_at`, the six non-skipped job `started_at`/`completed_at` fields and Worker step timings from GitHub Actions; the Worker logs contain fixed cache-miss/save or hit/restore labels. No mail, secrets, or provider payloads are required.

What remains serialized: reviewed staged rollout, shared alias/account/route creation and cleanup, one-use SMTP sends, serving-pin-sensitive acceptance, production promotion, and observational provider waits. Cancellation is not safe for those operations; a timeout can leave ambiguous external state. Avoid replacing safety serialism with parallel retries.

## External grounding

* [GitHub concurrency documentation](https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency) supports explicit groups and cancellation of obsolete non-mutating runs. Queue delay and retained run state must be observed rather than inferred from a timeout.
* [GitHub dependency cache reference](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching) describes exact-key matching, branch access restrictions, cache exposure, and storage costs. Cached files are not a secret store or a passing test result.
* [Cloudflare workers-rs issue #1021](https://github.com/cloudflare/workers-rs/issues/1021) independently reports cold `worker-build` installation as a substantial hosted-CI cost and recommends a pinned locked pre-step with caching. Our own job timings, not that report, justify this optimization here.
* [Google's 2025 Speculative Testing with Transition Prediction](https://research.google/pubs/speculative-testing-at-google-with-transition-prediction/) explores scheduling tests by predicted outcome transitions under large-scale CI demand. That frontier matters when assertions themselves dominate; applying learned test omission now would add uncertainty without addressing our measured tool-install/deployment bottleneck. Full coverage is retained.

## Status

Source implementation and hosted cold/warm validation are complete for the exact unchanged-Worker-input path above; one changed-Rust-source/project-cache-miss, bundler-hit run is also measured. Broader workload performance remains uncertain. No public sending or privacy gate is relaxed by this change.

## Structural workflow contracts (2026-10-01)

Two later hosted feedback failures were test-fixture coupling, not regressions in provider behavior: a hardcoded dispatch-input count and a job slice ending at a particular later job. Adding a safe manual diagnostic changed those unrelated assumptions. The demonstrated named-successor and staging-substring job-source contracts now share `infra/tests/workflow_source.py`: extraction is bounded by actual two-space sibling job headers inside the single top-level `jobs` block, rather than an expected successor name. Duplicate/missing jobs, quoted or otherwise unsupported sibling keys, shallow odd indentation and inline job mappings fail closed rather than being absorbed into the preceding job. This intentionally follows the repository's block-style workflow layout; it is not a general YAML parser. Raw job source remains available for exact manual-event, confirmation, branch, environment, secret-scope and execution-order assertions.

The synthetic adjacent-job fixture includes a credential-bearing unrelated job, an underscore identifier, a nested shell step, a final job and a following top-level mapping. It asserts that inserting the unrelated job cannot satisfy or contaminate the preceding job's safety assertions. Existing assertions were retained, with only their source extraction replaced. The independently owned Worker R2 creation/delivery-history tests are excluded from this change. Local verification is limited to Python AST parsing and diff inspection; executable tests remain on GitHub-hosted runners.

## Repeated project-cache misses on unrelated workflow edits (2026-10-01)

Later source pushes show the pinned bundler cache working, but an overly broad
project-source key repeatedly invalidating compilation. This is separate from
the seconds-long Infra feedback boundary described in
[the fast-feedback design](hosted-infra-fast-feedback-design.md).

| Source / push run | Worker job | Project cache | Bundler cache | Whole workflow |
| --- | --- | --- | --- | --- |
| `0c18c78`, [36763904226](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36763904226) | 5:25 | miss, saved | exact hit; install skipped | 5:31, green |
| `2d08556`, [36765951110](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36765951110) | 3:38 | miss, saved | exact hit; install skipped | 3:44, red on Infra |
| `3542a5f`, [36766439483](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36766439483) | 1:41 | exact hit from `2d08556` | exact hit; install skipped | 2:36, green; Windows CLI dominates |
| `a36d11c`, [36767492647](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36767492647) | 5:46 | miss, saved | exact hit; install skipped | 5:53, green |

All four revisions have identical committed root/workspace identities:

```text
Cargo.toml 025c0cad61835a21ace1cf74db8022eebfd489a7
Cargo.lock e2ca7b6b06aca4b16a1e0522e74c9c354afc98d6
crates     5b160679e7c971e8d55a997ee703b3def6c3ae60
workers    3b4e5847afee5d6af3d3e217cab75630afeceb75
```

The compiler/C/libc fingerprint was also identical (`b85b12…`) in the inspected
cache labels. The old key hashes the **entire `ci.yml` blob**, not merely the
Worker build contract. Its workflow blob differs for `0c`, `2d/354`, and `a36`.
`2d` extends the Worker job's manual predicate as part of production graph work;
`354` only changes an unrelated test/doc and restores the preceding exact key.
`a36` changes only a dispatch choice and adds an unrelated encrypted-diagnostic
job to `ci.yml`; its complete Worker block is byte-identical to `2d/354` after
LF normalization. Therefore a new sibling diagnostic invalidates all compiled
Worker outputs despite unchanged Worker source/commands. This is key scope,
not cache corruption, tool reinstallation, or an unproven Cargo-freshness bug.

Mechanism-level timings: `354` restores `target` in 15 seconds, executes Rust
Worker tests in 4 seconds, bundles the sink/API in 7/32 seconds, and still runs
workerd assertions for 9 seconds. In `a36`, the miss makes schema/sink tests,
sink Wasm check, and Mail unit tests consume 33/32/53 seconds before later
compilation/bundling. Different runners make these observational comparisons,
not controlled repeated speedup measurements.

### Minimal v2 source design

The project cache advances to `worker-check-v2`; the independently effective
`worker-build-check-v1` tool cache remains unchanged. The stdlib-only
`infra/ci/worker_cache_key.py` projects **the entire Worker job block** through
the existing strict sibling extractor, plus inherited permissions. It hashes
that projection together with exact committed identities for Cargo manifest,
lock, complete `crates`/`workers` trees, boundary-test tree, the fingerprint
helper itself, and its structural extractor. Optional `.cargo` and Rust
toolchain files are absence-bound, so introducing them changes the key.

Unknown top-level fields, inherited global env/defaults, YAML indirection,
unsupported layout, or dynamic build inputs produce a unique uncacheable miss
and disable project-cache writes. They do not skip source tests. Global
env/defaults are deliberately unsupported until a future explicit runtime-
value contract is designed; raw expressions alone cannot fingerprint their
resolved build effects. Every current Worker command, step, local env, action,
runner setting, predicate and cache policy is within the hashed job body.
Unrelated dispatch choices and sibling jobs are outside it. Trusted push-only
writes and full assertion execution remain unchanged; deployment never consumes
this check cache and still builds independently.

This creates one expected v2 cold seed. The next naturally occurring unrelated
manual-job or Python/doc edit should hit the same project key and keep Worker
feedback near the observed 1:41 warm path, rather than the observed 3:38–5:46
miss paths. **That is a target, not a measured v2 result.** Full-source feedback
may then be dominated by Windows CLI rather than Worker, as happened in `354`.
Measure all job timings, exact hit labels and retained assertions at the first
natural warm revision; do not run extra deployments or fabricate a production
cache artifact. Static AST/diff inspection is local; executable tests remain
hosted. Focused synthetic contracts cover sibling invariance, Worker/global
permission invalidation, each declared object/config absence, unknown layouts,
unique unsaved fallbacks and the current workflow's cacheability.

Independent review identified a conditional-build omission in the initial v2
implementation: removing every indented `if:` from runtime-expression validation
would accept a compiler setup gated by a runtime variable. The correction
removes only the three exact existing bundler-install/cache-save conditions,
bound to their named steps and existing install/save operations. Any other conditional setup, including folded/plain
runtime-variable expressions or a known cache condition on a different step,
now disables project-cache reuse. The full guard text remains in the hashed
contract. Synthetic regression fixtures cover rejection and supported guards;
hosted tests and re-review are still required before claiming acceptance.
The follow-up review also identified standard step-first `- if:` conditions,
whose GitHub expressions do not require `${{ }}`. These and quoted/spaced
conditional keys now fail closed; only the current name/uses-first step layout
is supported. Branch/input implicit-expression fixtures preserve that boundary.

Reproduce via run/job APIs and filter the **secret-free Worker job logs only**
for `Cache restored from key`, `Cache not found for input keys`, and `Cache saved
with key`. Compare committed inputs with `git rev-parse <sha>:Cargo.toml
<sha>:Cargo.lock <sha>:crates <sha>:workers <sha>:.github/workflows/ci.yml`.
No private provider/job logs or mail data are needed. GitHub's
[cache reference](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
explains exact-key identity and immutable entries; the
[Cargo build-cache reference](https://doc.rust-lang.org/cargo/reference/build-cache.html)
explains cached compilation outputs. This change narrows cache identity to the
actual build contract, not test selection or acceptance coverage.

### Exact Worker cache-v2 first push (2026-09-30)

At `b3587bf`, [push source run 36774241992](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36774241992) was green across all six active jobs. It was created at 20:40:13 UTC, first active jobs started at 20:40:17 (0:04 wait), and the workflow completed at 20:45:25 (5:12 total). The previous [run 36773432805](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36773432805), `c5b2fd1`, had failed **only** in a stale private-inbox workflow test: it searched for the removed `staging-role-monitor:` job boundary and raised `ValueError`. That Infra failure surfaced in 0:19; the corrected `b3587bf` Infra suite passed in 0:18. The comparison demonstrates fast failure/repair feedback for this fixture, not a measured speedup for the full suite.

| `b3587bf` active job | Start → end UTC | Duration | Result |
| --- | --- | --- | --- |
| Infrastructure probe unit tests | 20:40:17 → 20:40:35 | 0:18 | Passed |
| CLI Ubuntu | 20:40:18 → 20:41:35 | 1:17 | Passed |
| CLI macOS | 20:40:23 → 20:41:55 | 1:32 | Passed |
| CLI Windows | 20:40:18 → 20:43:04 | 2:46 | Passed |
| Astro release site | 20:40:18 → 20:40:41 | 0:23 | Passed |
| Rust Worker/Wasm | 20:40:18 → 20:45:24 | 5:06 | Passed |

The independent [workflow syntax guard 36774241515](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36774241515) passed in 0:08. The PR-triggered [private-provider synthetic crypto 36774249823](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36774249823) passed on Ubuntu and Windows (0:21 each); [candidate-site source/isolation checks 36774249765](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36774249765) passed in 0:27. A separate direct-contact workflow was not triggered by this push; its syntax was covered by the workflow guard. All 51 non-source jobs in the main push run were skipped, so no provider state or serving Mail Worker was changed.

The Worker log reported an exact **`worker-check-v2` cache miss**, a hit/restoration for the independently pinned **`worker-build-check-v1` bundler cache**, and a successful `worker-check-v2` save after checks. The 5:06 Worker job therefore establishes the new key's cold-write path, **not** a v2 cache-hit improvement. A future source-unchanged hosted run that actually reports a v2 hit is required before measuring or claiming that gain; no duplicate run was dispatched merely to manufacture this comparison.

### Natural v2 warm-cache observation (2026-09-30)

The next ordinary docs-only push, `7719d67`, produced [source run 36775433360](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36775433360): **all six source jobs passed**. It was created at 20:50:29 UTC, first active jobs started at 20:50:33 (0:04 wait), and completed at 20:52:53 (2:24 total). Comparing the two exact revisions with `git diff --name-only b3587bf 7719d67` shows only files under `docs/` changed; the Worker code, build inputs and Worker-job workflow source were unchanged. The completed Worker log explicitly reported **exact `worker-check-v2` hit and restoration** for the key saved by `b3587bf`, plus the same independently pinned **`worker-build-check-v1` hit/restoration**. All Worker/Wasm checks ran and passed; no cache result was substituted for an assertion.

| `7719d67` active job | Start → end UTC | Duration | Result |
| --- | --- | --- | --- |
| Infrastructure probe unit tests | 20:50:33 → 20:50:50 | 0:17 | Passed |
| CLI Ubuntu | 20:50:33 → 20:51:45 | 1:12 | Passed |
| CLI macOS | 20:50:39 → 20:51:42 | 1:03 | Passed |
| CLI Windows | 20:50:34 → 20:52:52 | 2:18 | Passed |
| Astro release site | 20:50:35 → 20:50:59 | 0:24 | Passed |
| Rust Worker/Wasm | 20:50:33 → 20:52:21 | 1:48 | Passed |

The independent [workflow syntax guard 36775433047](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36775433047), PR-triggered [private-provider synthetic crypto 36775438131](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36775438131) on Ubuntu and Windows, and [candidate-site source/isolation checks 36775437909](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36775437909) also passed. The main push run skipped all 51 non-source jobs, including every deployment/provider mutation; no serving Worker changed.

For this unchanged Worker-source/cache-identity pair, the Worker job fell from **5:06 cold-write to 1:48 exact-hit** (3:18 less), while whole source feedback fell from **5:12 to 2:24** (2:48 less); the second run's longest job was Windows CLI. These are two naturally occurring hosted runs, not a controlled benchmark: runner conditions and independent CLI scheduling may differ. The defensible result is that the v2 key survives unrelated documentation changes, restores the compiled Worker cache, retains complete checks, and shortens this observed feedback path. It does **not** predict performance for Rust edits, new build inputs, or a deployment/release path.
