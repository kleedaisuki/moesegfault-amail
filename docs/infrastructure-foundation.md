# Infrastructure foundation

Status: implementation in progress. This document is the current infrastructure
plan and acceptance ledger, not a claim that production is deployed. On 2026-10-01
the owner explicitly prioritized infrastructure and debt repayment before further
mail debugging. Preserve the current send hold and do not resume production
inspection, mailbox campaigns or release promotion until this foundation passes.

## Architecture and scope

Use platform mechanisms rather than a second home-grown control platform:

* GitHub Actions owns dependency ordering, parallel test matrices, immutable
  artifacts, job summaries, cancellation and deployment writer serialization.
* Cargo and a maintained Rust cache action own dependency fingerprinting. Cache
  contents are acceleration, never evidence that tests passed.
* One reviewed Worker build produces module trees once. Native suites consume the
  same source/run-bound artifact on independent hosted runners. The stable
  `Rust Worker (Wasm)` gate aggregates build and every native suite, preserving
  established promotion consumers and historical workflow/job identities.
* Cloudflare retains operational logs and spans. CLI SQLite retains the local
  journal. Correlation identifiers connect these records; mail contents and
  credentials do not belong in either diagnostic store.
* Existing project-managed GitHub Secrets remain project-managed. No second
  routing token, environment Secret migration, manual hash-Secret ceremony or new
  dashboard is introduced by this foundation.

The checked-in Rust compiler and bundler must be explicit. Build/test/deploy must
select the same compiler policy. Generated JavaScript is the official Rust/Wasm
runtime bridge, not a new business implementation. Preserve public CLI, HTTP,
ZIP, identity, storage and release contracts during internal refactoring.

## Information classification: privacy is field-level

| Class | Examples | Treatment |
| --- | --- | --- |
| Secret | Passwords, OAuth/API tokens, cookies, authorization headers, signed URLs | Never emit; keep only in authorized secret/credential storage |
| User content/personal metadata | Bodies, MIME, attachments, subjects, sender/recipient, search text, identity subject, private operational forwarding destination | Exclude from normal diagnostics; narrowly authorized content workflows remain separate |
| Operational coordinates | Service/operation, trace/span/request IDs, source SHA, Worker/deployment version, non-personal infrastructure IDs, public service domain, schema field names | Retain directly for correlation/debugging; do not classify every ID as a secret |
| Measurements | Exact timing, status/error codes, retries, attempts, queue lag, resource usage, schema expected/actual types and non-personal counts | Retain with units and scope; bucket only where a measurement materially exposes user content |
| Unknown provider/user text | Arbitrary response, exception string, request path/header/query/body | Do not dump wholesale; extract useful typed context at its boundary |

Each diagnostic event needs operation, phase, correlation, timing, outcome and
useful error context. `UNVERIFIED` may describe an acceptance verdict, but cannot
replace the diagnostic cause. A correlation ID is not proof of end-to-end
coverage: verify actual CLI, API, background and sink records, including missing
segments and diagnostic loss. Never promise a trace for an unrelated provider
control-plane call merely because the mail application has spans.

## Delivery sequence and exit conditions

| Work package | Exit condition | State |
| --- | --- | --- |
| CI dependency graph and caches | Build once; all native files assigned; parallel suites; stable fail-closed aggregate; dependency caches without credentials/workspace binaries; observed hosted durations and cache outcomes | Implementing |
| Artifact and compiler provenance | Source/run/compiler/bundler/file hashes verified before consumption; wrong-source, modified/missing/extra file refused; promotion consumes tested artifacts rather than rebuilding silently | Implementing for source checks; deploy/release wiring pending |
| CI and deployment diagnostics | Machine-readable timing/outcome summaries; source/run/stage/request correlation; useful safe provider failures; no repeated opaque probes | Pending |
| Runtime observability | Field-level schemas; CLI/API/maintenance/lifecycle coverage and diagnostics for loss; Cloudflare configuration and a synthetic correlation/privacy canary accepted | Pending |
| Deployment lifecycle | Explicit paused/active state; consistent source/toolchain/artifact; writer lock, readback, rollback and bounded recovery; project Secrets remain unchanged | Pending |
| Maintenance knowledge and cleanup | Current runbook and maintainer skill; legacy research probes isolated from normal product paths; canonical status ledger; no dangling test/active workflow | Pending |

Completion means all rows have executable evidence, not just a design review.
Runtime and cross-platform tests run in GitHub Actions only. Local work is source,
syntax and diff inspection; artifacts stay under repository `.temp`/`.cache`.
Infrastructure canaries must not create mail users/aliases, send user mail, grant
sending or change business data. Any required user action uses the question tool.

## Measured baseline

GitHub source run 36833685284, PR 40, Worker job 110275936022, took 11m34s
(08:00:42–08:12:16 UTC). Native testing occupied about 6m29s from 08:05:27
through 08:11:56, after bundling. The seven suites were serial. Main run
36832207613 took 8m33s for Worker, including 21s restoring the exact project
cache. Step success alone does not establish a cache hit; record the action's
cache result explicitly. These are observations, not controlled benchmarks or an
SLA. A Python-only scoped PR was observed at 24s, but coarse crate classification
still selected unrelated Worker compilation until PR 41's exact exemption.

The previous whole-tree/whole-job target-cache projection required a custom
200-line parser and invalidated compiled outputs for deployment-only Python and
test-only edits. Replace that dependency model with Cargo's standard dependency
cache and immutable built artifacts. Independent native suites should run on
separate runners: shared mutable build directories and timing-test CPU contention
must not be introduced merely to parallelize.

## Source references

* https://github.com/Swatinem/rust-cache — maintained dependency cache, default
  exclusion of workspace crates and compiler/environment-aware keys.
* https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching
  — cache scope/immutability, PR access and credential exclusion.
* https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/pass-job-outputs
  — fixed producer outputs and downstream dependency graph.
* https://developers.cloudflare.com/workers/languages/rust/ — supported Rust/Wasm
  build path. The pinned worker-build bridge is official generated infrastructure.
* https://opentelemetry.io/docs/concepts/signals/traces/ — propagated context and
  correlated spans are distinct from complete observed trace coverage.

No academic novelty is claimed for these foundations; mature platform mechanisms
are preferable to a speculative orchestration/telemetry framework. Evaluate
advanced sampling or automated incident diagnosis only after accurate baseline
events and an executable coverage check exist.

## First hosted implementation check

PR 42 run 36839757185 passed infrastructure, syntax, site and all three CLI
platforms. Worker build/unit checks and all six bundles completed, but artifact
assembly refused a regular generated file under a guessed extension allowlist.
No native suites ran and the stable aggregate correctly failed on build failure
plus skipped native coverage. This run is not a complete Worker pass.

Remove the guessed extension policy rather than adding another SDK special case.
Source maps/licenses are public generated outputs. Confidentiality comes from
the credential-free producer and exact generated directories, not extensions
(a .js/.json could contain a secret too). Preserve regular-file/symlink checks,
size bounds, source/run binding and full file-set/hash verification. A regression
allows a generated map while excluding config outside the selected trees.
