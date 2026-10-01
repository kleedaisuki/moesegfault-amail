# Infrastructure foundation

Status: implementation in progress. This document is the current infrastructure
plan and acceptance ledger, not a claim that production is deployed. On 2026-10-01
the owner explicitly prioritized infrastructure and debt repayment before further
mail debugging. Preserve the current send hold and do not resume production
inspection, mailbox campaigns or release promotion until this foundation passes.

## Current integrated state (2026-10-01)

This section supersedes dated implementation-status statements below. Product
scope and remaining release requirements are in the [Goal progress snapshot](goal-progress-snapshot.md).
Source baseline is main `bfb02765c622bced2ad2b8a10f6717cce79c6199`;
[exact-main CI 36888295197](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36888295197)
passed all three CLI platforms, Astro, infrastructure, Worker producer, eight
native suites and the stable aggregate. Historical receipts remain useful but
do not imply current deployment.

* PRs 52, 54 and 64 are merged: search-poll reader compatibility, enriched
  source-clock/error readers, and durable bounded CLI upload/loss accounting.
  PR 68 also merged local/auth command coverage (50 unit, five new command-process
  and four existing resilience tests per hosted CLI platform). The CLI still
  produces legacy remote events; capability negotiation and local-to-API causal
  connection remain separate ongoing source work.
* PRs 55 and 58 are merged: ordinary deploy jobs consume verified same-run module
  artifacts, and the standalone Identity inbox admits an original exact-main
  artifact. Their actual Mail/inbox deployment paths have not been executed by
  this foundation. Wrangler packaging still occurs; final packaged graph/bytes
  and runtime entry behavior are being tested in a credential-free hosted probe.
* PRs 59, 60 and 65 are merged: fixed diagnostic client identity, exact scoped
  diagnostic checks and per-case native-parentage admission. These do not prove
  that native spans have been retained by Cloudflare.
* PR 62 is merged: three fixed historical incident-read lanes are retired while
  source fixtures and receipts remain. The Queue permission workflow's automatic
  push trigger is the next bounded maintenance cleanup.
* PR 63 is merged: partial predecessor/receipt/readback contracts. There is not
  yet an executable production receipt producer or an accepted activation,
  drain or rollback. Fresh held production bootstrap is being implemented; old
  stores remain untouched, and empty inventory is not historical ownership proof.

Actual isolated canary [36884872446](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36884872446)
restored artifact `11172022967` from the exact-main run and passed deployment,
ownership, version and capture/isolation readback. Its one fixed-client POST
returned HTTP 404 / provider code 1042; no native-case receipts were produced,
and retained-record collection was skipped. Owned cleanup verified both scripts
absent at `2026-10-01T15:31:53.852080+00:00`. Artifact `11174410747` retains the
safe receipt. This is negative invocation evidence, not native-tracing/privacy
acceptance. Do not repeat the unchanged workers.dev experiment. The selected
next source design uses an absent-only, nonce-owned Worker Route and proxied DNS
record with existing Universal SSL, without borrowing public service hostnames
or creating an Advanced Certificate. It requires review before provider writes.

Five independent workstreams run in parallel: deployment/bootstrap, runtime
telemetry, native tracing, CI packaging/latency, and maintenance. Their leaders
may delegate bounded implementation/validation tasks. Root coordinates provider
writes under existing serialization; source review is not a global serial gate
for unrelated work. Tests and cross-platform execution remain hosted only.

The owner's original account belongs to production Identity, not staging.
Its rejected staging login is an environment/realm mismatch, not an established
production authentication bug. Its production native-client journey is
**UNEXECUTED**; do not repeat staging login, copy accounts or reset credentials
based on that historical rejection.

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
| CI dependency graph and caches | Build once; all native files assigned; parallel suites; stable fail-closed aggregate; dependency caches without credentials/workspace binaries; observed hosted durations and cache outcomes | Hosted source accepted; three CLI platforms and Worker observed exact warm dependency hits |
| Artifact and compiler provenance | Source/run/compiler/bundler/file hashes verified before consumption; wrong-source, modified/missing/extra file refused; promotion consumes tested artifacts rather than rebuilding silently | Ordinary same-run deployment and exact-main inbox source wiring merged; isolated canary consumption executed; final packaging and actual ordinary deployment remain unaccepted |
| CI and deployment diagnostics | Machine-readable timing/outcome summaries; source/run/stage/request correlation; useful safe provider failures; no repeated opaque probes | CI cache/native receipts and initial [control-plane integration](control-plane-observability.md) source accepted; lifecycle consumers pending |
| Runtime observability | Field-level schemas; CLI/API/maintenance/lifecycle coverage and diagnostics for loss; Cloudflare configuration and a synthetic correlation/privacy canary accepted | [Coverage repair and native-span validation plan](runtime-observability-foundation.md) |
| Deployment lifecycle | Explicit paused/active state; consistent source/toolchain/artifact; writer lock, readback, rollback and bounded recovery; project Secrets remain unchanged | Partial source contracts merged; fresh held bootstrap implementation ongoing; actual producer/activation/drain/rollback not accepted |
| Maintenance knowledge and cleanup | Current runbook and maintainer skill; legacy research probes isolated from normal product paths; canonical status ledger; no dangling test/active workflow | [Operational lane inventory and first historical retirement](maintenance-operational-lanes.md) hosted-source accepted on PR 62; supported recovery and active native-tracing preserved; remaining legacy debt explicitly inventoried |

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

## Accepted hosted build-once and native fan-out

Corrected PR 42 source b5a05835fc9276dc755e95df75138e91ad1f175a passed
run 36841123150, attempt 1. Checkout c2773645363605a2e089f260d8492088c1a79dbf
was the PR merge commit; its tree matched the reviewed head. One build packaged
30 generated files, and all eight native runners independently verified that
same source/run/file set before testing. Counts were 102 core, 7 entry, 6 liveness,
9 accepted, 7 routing, 6 embedding, 13 diagnostics and 1 historical budget:
**151 passed, zero failed/cancelled/skipped/todo**. All three CLI platforms,
infrastructure, Astro and workflow syntax also passed.

Observed times: build job 09:11:53–09:16:55 UTC (5m02s); native fan-out including
runner setup and artifact verification 09:16:58–09:20:02 (3m04s); stable Worker
aggregate succeeded at 09:20:08. Whole workflow ran 09:11:40–09:20:09 (8m29s).
The previous serial native phase was about 6m29s; these are uncontrolled observed
runs, not a whole-CI latency guarantee. New dependency-cache outputs reported
non_exact_or_miss; public bundler reported exact_hit. Do not infer cold versus
partial restoration from the former. Suite execution times are retained in
native-suite-* JSON artifacts and job summaries, separate from build artifacts.

Merged main 677fc1fdc92daca9c23f361ec99fb264b6f26882 has the accepted tree.
Its full run 36843081448 also completed successfully. No provider inspection,
mailbox mutation, deployment, sending grant or release accompanied these checks.
The remaining foundation work is still required before resuming business debug.

## Accepted CLI journal foundation

PR 44 source 46a6cbe9e7dc79242358521d73ab7273aa514095 passed scoped CI
36849720707 and syntax 36849720535. Linux/Windows/macOS each passed 33 unit
and 2 real CLI subprocess tests; all three dependency cache receipts were
exact_hit. Observed scoped workflow duration 2m01s includes platform jobs of
33s, 105s and 45s including setup. These are observed samples, not a performance
SLA. Main a0626aae5f79edab85755670902d1df358d91826 preserves the tested tree.

The compatible SQLite journal now records UTC start, exact monotonic duration,
auth/transport/body/completion phase and matching propagated IDs. Historical
rows retain NULL clocks. Durable send table/API ownership is separate without
moving the historical file or losing keys. Telemetry opt-out skips initialization;
diagnostic failure does not break successful commands or contaminate stdout.
Remote clock/error-phase enrichment is not yet rolled out. See the runtime ledger
for reader-first Queue schema, native sink tests and platform tracing acceptance.

## Accepted Queue reader and initial control-plane foundation

PR 46 source a68c743 passed scoped CI 36852119210 (27s), syntax 36852118204
and bootstrap synthetic contracts 36852117921. The actual provider-inspection job
was skipped. Main c75c24b accepted the structured status/CF-Ray, source/run/time,
process exit and schema-type diagnostics without any provider operation.

PR 45 source 42509113de044fc013a1c51a359286f9859c7812 passed full CI
36853948436 and syntax 36853947806. Actual checkout was merge commit
7770b4cb0acac48b9145d24813414d53de063eea, including accepted PR 46. Its tree
matches merged main cec8ac2451516e6be6228673176a4048f248976b. All three CLI
platforms, Astro, Rust/Wasm/unit checks and all eight native suites passed:
105 core plus 49 other tests = **154 passed, zero failed/cancelled/skipped/todo**.
One 30-file artifact was verified independently by all native runners.

The real compiled Rust Queue handler preserved old/enriched source clocks and
causal identity, acknowledged rejected poisoned/malformed records without replay,
and was observed through native console capture plus an actual post-Rust console
barrier. Prior failed fixture iterations are retained in the runtime ledger;
none were accepted as partial success. This is hosted runtime/source acceptance,
not deployed Cloudflare enrichment/native-span privacy acceptance. Producers are
still unchanged; reader deployment must precede enriched producer rollout.

Both Worker dependency and bundler receipts were exact_hit. Observed whole full
workflow was 5m02s (11:12:49–11:17:51 UTC), build 1m40s (11:13:01–11:14:41),
core job 2m58s including setup (11:14:45–11:17:43). The earlier observed full
workflow was 8m29s; these are uncontrolled samples, not an SLA or sole-cause
performance benchmark. A dedicated verified-artifact native fixture diagnostic
lane is hosted-accepted to avoid unrelated rebuild/tests during fixture repair;
it cannot substitute for current-source CI or promotion.

Next priorities: complete
reader-first remote application clocks/error semantics and the synthetic native
Cloudflare canary; then tested-artifact deployment/release wiring, lifecycle
readback/recovery and historical-lane cleanup. Business debug remains deferred.

## Accepted narrow native replay

PR 47 head 2ae5124d3002b2dd47cddb725c61bb1f2ce026a9 passed full source CI
36854745753 and syntax 36854745703, including all 154 native tests. Merged main
7242ad0d914978c97e8b0e87a0a52aafd5661b11 then executed actual diagnostic replay
36855666878 against completed source run 36853948436, artifact 11156458767.
The lane proved unchanged compilation inputs and verified the original 30-file
artifact with source 7770b4cb0acac48b9145d24813414d53de063eea, attempt 1,
Rust 1.98.1 and worker-build 0.8.5 before running current fixture source.

The three trace-sink native tests passed, zero failures/cancellations/skips/todo.
Observed whole replay duration was **24s** (11:29:15–11:29:39 UTC); runner job
19s (11:29:20–11:29:39), including metadata, download/verification and locked
runtime setup. This is a useful observed narrow-iteration fast path, not an SLA
or replacement for all-source CI. The receipt distinguishes original build and
current fixture source. No Rust compile, provider operation, mailbox action or
new deployment/release admission was involved. See native-fixture-replay.md.

## Accepted native tracing canary source and checked-artifact lifecycle

PR 49 head 8bf3f5097de0edafec8b9171c797e34f1a3023a0 / merge checkout
383052f832e2d7a9e02279c42f040f0ec0bae314 passed CI 36861601016 and syntax
36861600039. All 156 native tests passed (107 core plus 49 others), along with
three CLI platforms, Astro, Rust/Wasm/unit and infrastructure checks. The
build-once artifact now contains 35 files across seven module trees. Main
7b04df8425cf277c339042c06bea1faf42e43e39 preserves the accepted tree.

The new Rust infrastructure product uses native tracing imports directly; the
untraced caller generates four controlled requests to a private service-bound
probe without forwarding incoming data. Old-runtime tests accurately report
unsupported active getter and do not pretend to prove current platform support.
See native-cloudflare-tracing-canary.md for the comparison and evidence scope.

PR 50 head 5247463 passed full CI 36864805997 and syntax 36864805535; main
9d0a9599723a0887cc05a49376be54552252d64b retains the checked source. The isolated
experiment lane adds stronger artifact admission than diagnostic replay: complete
successful exact-main source CI, all required source jobs, fixed artifact ID and
original compiler/source/run/attempt/file hashes before provider access. Its
Wrangler configs omit Rust custom build commands, so deployment packages the
same checked bytes. Source-owned absent-script creation, version/endpoint/capture
readback and receipt-owned cleanup are implemented and synthetically tested.
Actual deployment/native-record observation/cleanup remains pending. This lane
has no Mail, account, store, routing or sending capability; it is not general
production/release admission. Full task/foundation completion is not claimed.

First infrastructure-only deployment run 36866726157 consumed the fully checked
main artifact from 36865492327. Both canary products deployed; a caller capture
readback guard refused progression before runtime invocation. Owned cleanup
completed and verified both scripts absent. This proves the tested-byte deploy
and failed-run cleanup paths, not native tracing or privacy acceptance. See
[native canary evidence](native-cloudflare-tracing-canary.md) for exact versions,
artifact and pending boundary repair. Mail deployment and business debug remain
deferred.

## Executed infrastructure artifact reuse and remaining acceptance

PR 53 source 3e00610ec5998759835d18b937628bfe1282c759 passed full CI
36870040420 and syntax 36870040082; merged main e9a56069898f74be7cda15ad4cc9ca42f41487c4.
Isolated experiment 36870838693 then proved current hosted infrastructure tests,
checked original artifact reuse (11164304271 / build run 36867766344 / compiled
source dcc4eed6), deployment and all pair ownership/version/isolation readbacks
without waiting for a redundant new full build. Total hosted run was 50 seconds.
Public trigger failed HTTP403 and no native runtime acceptance is claimed.
Failed-run owned cleanup verified both absent. Detailed evidence and missing
trigger HTTP facts are in native-cloudflare-tracing-canary.md.

Independent source audit at e9a5606 found no demonstrated blocker in the checked
artifact/fan-out/stable aggregate/narrow reuse contracts. The compiler/bundler
claim is checked workflow policy, not independent signed attestation. Ordinary
Mail/sink deployment still rebuilds and remains a required lifecycle repair;
the isolated experiment exception must not be generalized into release admission.
CLI search-poll telemetry batch blockage has a bounded reader-first fix accepted
on PR 52 (CI 36868331245), but is not yet integrated or deployed. Remote clock/
failure readers, complete command/phase/loss coverage and actual native tracing
remain outstanding. Infrastructure completion and business-debug resumption are
not admitted by these source/lifecycle milestones.

## Maintenance lanes and first reversible retirement

The [maintenance runbook](maintenance-operational-lanes.md) accounts for every
workflow file and CI job at main d593d1a. Ordinary source checks, supported
deployment/release and recovery are distinct from held acceptance/provider
research. The standalone Identity inbox is a supported native-login dependency;
the root native-tracing canary remains the active infrastructure experiment.

Remove only the completed fixed-September-30 marker-location, marker-discriminator
and Security Events dispatch targets/jobs. Their original run evidence, safe
classifiers and synthetic privacy/scope tests remain. A repository-wide source
regression prevents executable-lane resurrection and preserves supported job
identities. No provider query, remote disable, resource deletion, deployment or
mail action accompanies retirement. Old branch/run source is not retroactively
disabled; do not replay retired provider operations. PR 62 source 461183b passed
full hosted CI 36878849332 and syntax 36878848913; actual checkout b4fa3e6 has the
same tree. All 1,068 infrastructure discovery tests, three CLI platforms, Astro,
Worker build, eight native suites (156 passed, no failures/cancellations/skips/todo)
and stable aggregate passed. Every native runner verified the same 35-file build.
The first retirement is source accepted, not yet merged or a provider operation;
remaining historical debt is inventoried and no whole-foundation completion is
claimed. Exact evidence and old-ref replay boundaries are in the runbook.
