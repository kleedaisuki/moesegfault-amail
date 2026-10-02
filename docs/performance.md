# Performance of the agent-first workflow

## Scope and useful trade-offs

The v0.1.2 performance work targets repeated short-lived script invocations,
the static installation/manual journey, and bounded long-tail exact search and
archive processing. Keep stdout contracts, read/mutation separation, credential
privacy, exact search ranking and old local databases intact. Performance work
does not authorize provider requests, real mailbox actions, or production release.

Do not infer an end-to-end latency improvement from a local CPU microbenchmark.
CLI elapsed process time includes process creation and filesystem work. Native
Worker timings exclude D1/R2/network and Wasm compilation. Static site reports
count render dependencies and built asset bytes; they do not measure LCP.

## Delivered mechanisms

| Area | Before | Change | Evidence and limit |
| --- | --- | --- | --- |
| CLI schema checks | Every diagnostics database open entered `BEGIN IMMEDIATE`, even when all additive columns existed | Modern journals read columns without reserving the single writer; a missing-column upgrade locks and rechecks before ALTER | Old-row and concurrent migration tests retained; reserved-writer regression test added. Hosted release benchmark compares the former transaction with the read path on the same file |
| Backend send | Copy the entire already-validated outbound ZIP before the R2 write; retain original bytes only to read its size later | Preserve length, transfer byte ownership into R2 | Removes one allocation/copy up to the 5 MiB accepted bound; no new buffering policy, changed request bytes, or replay behavior. Copy-cost microbenchmark is not R2 service latency |
| Backend idempotent marks | UPDATE fired the search-generation trigger even when read state already matched | SQL updates only a differing read state, preserving authorization lookup and full response | Ordinary native migration fixture checks repeat marking leaves generation unchanged, actual toggles increment it, and foreign ownership never mutates |
| Backend exact semantic scan | Revalidate and sum the same query's 256-coordinate norm for every eligible vector | A borrowed validated query computes norm once per scan batch, without normalizing stored values | Near-tie-sensitive f64 score-bit equivalence tested against the frozen original; same-process original/prepared microbench measures the candidate gain before staging acceptance |
| Backend feedback exploration | Ownership checks called the full-message loader, transferring unrelated body and metadata | Shared narrow `SELECT 1 AS visible` query for receipt links, outcomes and per-message events | Same owner/outbound/undeleted/pending visibility guard; native and Wasm synthetic large-body fixtures exercise the transfer boundary. Message `get` retains its full content contract; this is not a latency claim |
| Frontend manual/changelog | Shared layout included all vendor component CSS, though only homepage buttons use it | Explicit homepage opt-in, unchanged pinned vendor source and cascade | Each manual/changelog cold load omits 58,817 raw CSS bytes and one blocking stylesheet request. Shared vendor CSS is 8,807 instead of 67,624 bytes (86.98% reduction); final Astro CSS is measured separately |
| CLI discovery | Ordinary initialization would load config and diagnostics even for offline discovery | Product CLI executes offline discovery before application-state initialization | Benchmark alongside help/version/config; discovery must work without network, credentials or config writes |

No CSS selector pruning or asynchronous loading trick is needed. No SQLite WAL,
credential cache, disabled diagnostics, relaxed fsync, ANN index, or service
daemon is justified by these findings. See [exact search](perf-search.md) for
the all-candidate, stable-order and mutation-bound cursor contracts.

## Small hosted measurement suite

Run on GitHub Actions with pinned repository lockfiles, existing native/Worker/
site jobs and release binaries. Do not install or build heavy tooling locally.
All fixtures are synthetic and scratch/report files stay under `.temp`.

### CLI whole-process workloads

```sh
python scripts/performance.py --binary target/release/amail \
  --output .temp/performance/cli.json
# Optional: pair an older release binary on this exact runner.
python scripts/performance.py --binary target/release/amail \
  --baseline .temp/performance/baseline-amail \
  --output .temp/performance/cli-comparison.json
```

Cases: help, version, config, auth status with an empty synthetic session,
offline discovery, telemetry-enabled warm/first-use config, and 4 KiB/2 MiB
pack/unpack. Each process suppresses stdout/stderr and uses synthetic HTTPS
origins and its own application home; the script makes no authenticated API
calls. Auth status can still exercise the host keyring backend; record exit
codes and do not compare successful work with unavailable-backend errors.
Legacy binaries without discovery report their nonzero exit code, not a fake
speed comparison. First-use resets app state, not the OS page cache.

Three untimed warmup processes precede 25 startup/status samples, 15 ZIP samples
or nine first-use samples. Fixture preparation and cleanup are outside timing.
Reports retain raw milliseconds, median, nearest-rank p95, median absolute
deviation (MAD), binary size and OS/architecture/Python/commit context.

### CPU microbenchmarks

```sh
mkdir -p .temp/performance
cargo test -p amail --locked --release performance_microbench \
  -- --ignored --nocapture | tee .temp/performance/cli-microbench.log
cargo test -p amail-worker --locked --release performance_microbench \
  -- --ignored --nocapture | tee .temp/performance/worker-microbench.log
```

Ignored release tests reuse normal dependencies: no Criterion/nightly/test
framework. Each reports 15 repeat batches, per-operation nanoseconds, median,
nearest-rank p95 (the largest sample at this small sample size), MAD and raw
values. `black_box` surrounds inputs/results to discourage dead-code folding.
Fixtures are prepared outside timing. Bounds are intentional:

* 512 vectors of 256 dimensions: exact-score CPU constant, not approximate rank.
* 2,048 candidates with retained K=21/101: common/default and broad page sizes.
* Literal, regex and unsuccessful body filters over a fixed Unicode body.
* 4 KiB and 2 MiB archive assets: allocation/inflate behavior without a huge corpus.
* Removed archive-copy cost and former/current local schema checks.

The exact cosine comparison includes query preparation inside each batch,
not an artificially free precomputed input. Query/document sums retain the
original per-coordinate order; query norm reuse does not change normalization,
dimensions, precision or stable tie ordering. If the repeated batch measurement
does not justify the small helper, revert that production optimization while
retaining the useful workload baseline.

Compare equivalent workloads on one runner; retain repeats and investigate
effects that are larger than observed variation. Never gate CI on fixed
cross-runner milliseconds, and do not claim a reliable production p95 from 15
microbenchmark batches. CI gates semantic, resource and compatibility invariants;
measurements inform optimization decisions. A baseline from another runner is
historical context, not a causal before/after comparison.

### Frontend build/resource evidence

From `site/`, after each candidate/published build:

```sh
node --test scripts/measure-performance.test.mjs
node scripts/measure-performance.mjs > ../.temp/performance/site-candidate.json
```

The report reads actual built HTML/CSS, including inline Astro chunks, and counts
stylesheet requests, raw/gzip CSS, HTML and scripts. Gzip is an estimate with
documented defaults, not a claim about deployed content encoding. Existing
browser acceptance validates homepage styles and route-local CSS under desktop,
mobile and dark layouts; the static guide remains zero-client-script.

## Why these choices are grounded

* [SQLite transaction documentation](https://www.sqlite.org/lang_transaction.html)
  establishes that `BEGIN IMMEDIATE` reserves writing and can fail with BUSY.
  [PRAGMA table_info](https://www.sqlite.org/pragma.html#pragma_table_info) provides
  the read-only schema query. The slow-path lock/recheck preserves concurrent
  additive migration rather than replacing it with an unsafe once-only cache.
* [Cloudflare Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/)
  emphasize memory budgets and avoiding whole-body duplication; Workers have a
  [128 MB isolate memory limit](https://developers.cloudflare.com/workers/platform/limits/).
  ZIP validation genuinely needs bounded random-access bytes here, so eliminating
  the redundant copy is preferable to inventing a streaming archive protocol.
* [Astro's public-directory contract](https://docs.astro.build/en/basics/project-structure/)
  says public CSS bypasses bundling/optimization. [Google's rendering explanation](https://web.dev/articles/critical-rendering-path/render-blocking-css)
  explains why removing an unnecessary stylesheet dependency matters. Preserve
  required CSS rather than making all CSS asynchronous and risking a style flash.
* [Rust black_box](https://doc.rust-lang.org/std/hint/fn.black_box.html) is a
  best-effort optimizer barrier, not a timing or semantic correctness guarantee.
* [Taming Performance Variability, OSDI 2018](https://www.usenix.org/conference/osdi18/presentation/maricq)
  motivates repeated samples and environmental context. More recent
  [Towards Performance Robustness for Microservices, NSDI 2026](https://www.usenix.org/conference/nsdi26/presentation/saxena)
  reinforces dependency/resource assumptions rather than equating single-component
  mean speed with robust service performance. Its system machinery is not adopted
  for this small tool: the applicable insight is to distinguish local mechanisms,
  external service waits and workload-dependent limits.

## Results and next decisions

### Hosted built-site results

[Run 37048299485](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37048299485),
source `890f55a649a004cba7c44fcefb4f24bd8eef4ba4`, completed the site job including
Astro/TypeScript checks, candidate and published-state builds, release-copy checks
and payload reports. Artifact `performance-site-37048299485` contains both states.
Candidate measurements from the actual build:

| Route | HTML raw / gzip bytes | Stylesheet requests | External CSS raw / gzip bytes | Inline CSS bytes | Client script elements |
| --- | ---: | ---: | ---: | ---: | ---: |
| `/` | 8,295 / 3,433 | 5 | 82,218 / 17,082 | 0 | 0 |
| `/manual/` | 47,719 / 13,875 | 3 | 16,498 / 4,791 | 434 | 0 |
| `/changelog/` | 6,368 / 2,988 | 3 | 16,498 / 4,791 | 1,190 | 0 |

The omitted vendor stylesheet is exactly 58,817 raw / 10,338 estimated-gzip
bytes per manual/changelog cold load. This report includes real Astro chunks,
not just vendor-file arithmetic, and verifies zero client scripts. It does not
establish paint latency or visual correctness; browser/staging acceptance is a
separate check. The containing full workflow was still running when this site
artifact was inspected, so this is not a claim that all jobs passed.

Source-level eliminated allocation and lock acquisition above are concrete;
hosted native measurements are still required to quantify their elapsed-time
effect. Record exact run/commit and selected summaries when those jobs return.
Staging success is separate from native timing and site-byte evidence.
Escalate only the measured consequential bottleneck: e.g. repeated query-norm
work in broad exact search, redundant ZIP inflate, or synchronous store writes.
Do not adopt a heap, binary vector migration or persistent connection daemon
simply because a microbenchmark can be made faster.
