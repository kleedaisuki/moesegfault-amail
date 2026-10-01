# Independent accepted-stage integrated candidate review

Date: 2026-10-01. Candidate: `502651be429618896b9bd2f5bb555e44976b8a63`.
Merged PR29/31 base: `8ca1815307ae515aa5cacc6a25bb161779bb7be7`.
Review worktree: `.temp/accepted-stage-integration-review`.
Prior independent source review: `251c4694be0818ddfb47c318895e1b91965d940d`,
covering source/harness candidate `2c67564bf6cdddca3c63261c0dd082d0e7b90cb6`.

## Decision and limits

**GO for exact-head non-deploying hosted CI. No substantive integration defect
found. This is not executed-test acceptance, merge approval based on green CI,
or authorization to deploy, release sending, mutate provider state, or resume Cron.**

Reviewed committed source and workflow selection; inspected relevant prior review
and implementation knowledge first. Ran only Git/source inspection and scoped
`git diff --check` (successful), plus retrieval of public Cloudflare documentation.
No local project tests, build, installation, provider requests, hosted dispatch,
push, deployment, or implementation-worktree modifications occurred. The new
isolated worktree contains only this review artifact as an additional commit.

## Evidence

| Integration contract | Evidence and assessment |
| --- | --- |
| Exact earlier-reviewed implementation | `accepted.rs` has identical Git blob `2377453a731d47ab810175febcb5d386d7cfafb7` in the integrated and earlier candidates. New test and observer are also byte-identical: respectively `7a10363be9b719ee866485f76e9cc53871550da2` and `7169887937c7a6ecd06efaae45c2400c15aa8824`. No fence/index/result-validation behavior was silently changed by rebase. |
| PR29/31 retained | Merged base is an ancestor. Against that base, no diff in `lib.rs`, `platform.rs`, `archive_read.rs`, `maintenance.rs`, `trace.rs`, embedding-deadline suite/observer, final-diagnostics suite/observer, routing suite, R2/archive tests, HTTP/race tests, or default suite membership. Changes are limited to staging source/harness, additive docs/registration, and reviewed liveness/budget adaptations. |
| Unique new selection | Package has exactly one `test:accepted-stage`, selecting exactly `node --test accepted-stage-batch.test.mjs`; Worker job has exactly one unconditional step invoking it, after bundling and liveness. Six direct test declarations plus one test declaration instantiated by a three-value ambiguity loop yield nine actual cases. No skip, name filter or stub-only selection. |
| Exact built production code | Worker job checks out its own head, installs frozen dependencies, compiles Wasm, then runs `worker-build --release` in `crates/mail-worker` before boundary suites. Observer imports `../../../crates/mail-worker/build/worker/shim.mjs`; fixture root resolves to repository root. Existing module rules recognize ESM `.mjs`/`.js` and compiled `.wasm`. No new test-only implementation substitutes for Rust handlers. |
| Native execution path | Test imports locked Miniflare `4.20260730.0`, sets `cf:false`, creates local native D1/R2, applies actual migrations, invokes inherited compiled scheduled/HTTP handlers. Observer unwraps native bound statements and invokes one `target.batch`, never a loop of `run` calls. Faults operate after native transaction completion except the real SQLite abort trigger. |
| Existing coverage retained | Default script retains all seven exact file selections. Focused liveness (now six cases), Routing, embedding and final-diagnostics steps remain selected. Historical 102-case coverage is not reduced: all existing declarations/selections remain, with one additive liveness case and nine staging cases. 102 is historical baseline evidence, not a fresh observed count. |
| Statement oracle | Budget test still requires exactly 379 statements and zero unsupported operations. Five maximum items require 45 staging batches (330 members) plus five final batches (15 members): 50 batches, 345 members, 34 individual calls; `34+345=379`. Statement admission wrapper remains unchanged. |
| Liveness preservation | Existing slow-member, cutoff, slow-setup, insufficient-headroom and eight-slot rotation cases remain. Successful-group observer counts members; chunk-40 cutoff requires exactly 26 continuation chunk members. Added nine-call/two-second delay case demands genuine elapsed >=18 seconds and exact publication/cleanup; it is not a production benchmark. Liveness/budget files are unchanged from earlier reviewed `2c67564`. |
| No provider mutation | New suite routes network through explicit synthetic `outboundService`; only local OIDC GETs and synthetic Routing-list GET are accepted. Unexpected destinations/methods fail. Native fixture mutations affect only ephemeral local D1/R2. No sending provider invocation, secret injection, deployment action or live binding added. |
| Build-cache provenance | `worker_cache_key.py` includes committed `crates`, `workers`, all boundary-test inputs and full Worker workflow contract, with no fallback cache keys. New source/harness/registration cannot silently reuse an unrelated project's compilation. Bundler cache contains only pinned public tool. |

Nine cases cover maximum ASCII/replay, boundary counts, maximum mixed-width UTF-8,
real whole-group rollback, three ambiguous committed result forms, expired-token
concurrency while the successor remains accepted, and real public owner DELETE
with later GC. Prior detailed source review explains the discriminators and
unchanged safety/recovery contracts; this integration review does not duplicate it.

## External calibration

Retrieved on review date: [D1 database API](https://developers.cloudflare.com/d1/worker-api/d1-database/)
supports sequential ordered batch results and whole-sequence rollback;
[Miniflare](https://developers.cloudflare.com/workers/testing/miniflare/) identifies
its workerd-backed simulation;
[Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/)
support native bindings and awaited operations. Academic reconciliation-liveness
context and alternative architecture tradeoffs remain in the prior review/ADR;
no new research claim is introduced by this registration-only integration step.

## Required next evidence

Run hosted CI on this immutable integrated head and retain actual test selection,
case counts, all assertions and outcomes. Expected new suite: nine passing cases;
expected additive focused liveness case: one; old selections must still run.
Resolve failures without weakening the 379/N-token, rollback, exact content,
lease/token, no-resend, tombstone, HTTP/race, R2/deadline or diagnostic contracts.
Native harness success still does not establish paid-account CPU/memory/whole-Cron
latency or authorize live rollout; those remain separately gated measurements.
