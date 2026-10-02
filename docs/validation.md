# Product validation and release status

This is the single current acceptance ledger. Historical reviews/experiments are
in Git history, not competing current-state documents. Evidence recorded on
2026-10-02 is not a fresh inventory or permission to repeat production actions.

## Delivered v0.1.0

| Outcome | Actual evidence | Scope |
| --- | --- | --- |
| Production online graph | [36938451911](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36938451911) | API, maintenance, ingress, lifecycle consumer and private trace graph |
| Two-owned-account journey | [36942533661](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36942533661) | Receive/send/reply, TEXT/HTML/assets, filters/automatic semantic indexing, read state, ZIP export, deletion/isolation and delivered feedback for the same two sends |
| Operational contacts | [36954714726](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36954714726) | Verified destination, four real role receipts, normal health and opt-in schedule |
| Public sending allowed | [36954757295](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36954757295) | Explicit operator action; no invented human response commitment |
| Tagged builds | [36954856681](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36954856681) | Five platforms and skill bundle |
| Public bytes | [36957203738](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36957203738), job 110682831501 | Six archives against original manifest; seven published files including checksums |
| Published website | Later ordinary access to home/manual/changelog | HTTP 200, published Release links, no candidate copy/noindex; manual seven downloads/14 fragments, changelog two fragments |

[Release v0.1.0](https://github.com/kleedaisuki/moesegfault-amail/releases/tag/v0.1.0)
uses tag/artifact source `9ffb3284ddaec485a61b1efb93e4d26141b670cb`.
Recovery source was separately `6414b2038e45a56ac7a5cd710c2fef21266eb678`;
tag/assets/provenance were not replaced. Site version:
`1d89ad97-3046-456e-b008-97078a8db677`.

The continuation remains **FAILURE**: first site smoke ran 0.420 s after deploy
and did not confirm published-copy readiness. Later public access closes that
bounded site outcome, not a rewritten all-green run or another deployment.
Historical held/unreleased snapshots are not current production state.

## Useful bounded evidence and limits

### v0.1.2 work in progress (not published)

The owner authorized staging testing/deployment only, with public v0.1.0 unchanged.
Initial hosted [staging inspection 37046570528](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37046570528)
observed a mixed fetch/scheduled API with five-minute Cron, no maintenance Worker,
no trace sink or trace queues, and existing private ingress/lifecycle adapters.
API/ingress/lifecycle capture was positively read off. This establishes the legacy
predecessor requiring a cutover; it does not prove the v0.1.2 split graph is online.

Source `b2dbd66d786a5a790dc55486ee27ae578690f0ea` in staging run
[37053907751](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37053907751)
passed Linux/Windows/macOS CLI, native Worker, Wasm/workerd (112 boundary tests),
site, infrastructure and Worker performance gates. The overall run is **FAILURE**:
trace Queue provisioning and sink submission succeeded, but the sink verifier
incorrectly required the final two-producer graph during the legitimate
zero-producer preparation phase. API/maintenance/ingress/lifecycle/site deployment
jobs were skipped. This is partial infrastructure delivery, not an online v0.1.2
API, candidate site or completed native acceptance.

Fresh staging inspection
[37055035305](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37055035305)
confirmed the following non-content pins after that interruption:

| Resource | Observed immutable version / Queue identity | State |
| --- | --- | --- |
| API | `c3f6401a-1e84-4f51-91df-ae77d90683e9` | Original fetch + scheduled, five-minute Cron, Standard, capture off |
| Maintenance | Absent | No new scheduled writer activated |
| Ingress | `87002211-316c-4b75-8a27-993252e36488` | Original email adapter, capture off |
| Lifecycle | `8cfecf54-e0a5-44d1-b3b5-69cbbb8f9425` | Original Queue adapter, capture off |
| Trace sink | `be786239-402d-4e72-89c9-0acbe88b0b86` | Deployment `73892f24-1e84-406a-b025-3879580597e1`, Queue only, empty Cron |
| Trace Queue | `fcee510036af42c189e28c0b6ff9508e` | Bounded retention, zero producers |
| Trace DLQ | `f023f804b7bd4d8691fbfcb60416a001` | Bounded retention, zero producers |

The sink intentionally retains sanitized logs: provider capture is not disabled.
The old inspector's `capture_off=false` therefore must not be interpreted as either
privacy approval or proof of mail exposure. The corrected inspector keeps
`capture_off` separate from sink-only `privacy_safe`. Private-surface, immutable
capability, retention and exact Queue-consumer predicates must pass fresh before
owned continuation. The bounded resume controller preserves these existing
resources, pins the failed run's immutable ownership, requires identical runtime
bytes and reuses current full source gates. No continuation or v0.1.2 online
acceptance is claimed yet. No production resource, stable release or public site
was changed by this staging work.

Continuation [37056569732](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37056569732)
at source `6608d176897731851e8f01a85f47864b784e74af` passed the full source gates
but failed preflight before every provider-write step. Existing sink/Queues were
not replayed or replaced. Corrected inspection
[37057224593](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37057224593)
then confirmed all four sink privacy/capability/retention/Queue predicates, the
API-only preparation topology, `privacy_safe=true` separately from
`capture_off=false`, and the unchanged exact predecessor/Queue pins with zero
producers. Actual GitHub ownership recovery and tracked runtime comparison pass
locally, including the complete real job log and immutable artifacts. These facts
exclude graph drift and the tested provenance/dictionary shape as known causes;
the hosted preflight failure still requires diagnosis. The optional existing
inspection lane now checks that same admission with read-only confirmation before
another expensive full continuation. No online v0.1.2 delivery is claimed.

Read-admission run
[37057818125](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37057818125)
identified the remaining failure as `staging_resume_log_download_failed`: live
graph, runtime tree, origin metadata and immutable artifacts passed before the
hosted `gh api` job-log download failed. The same endpoint worked with the owner's
local CLI credentials; that does not establish why the hosted token/CLI failed.
The narrow repair separates the authenticated GitHub 302 request from its
allowlisted unauthenticated signed-blob download, retaining the exact typed sink
submit proof and read-only admission gate. Hosted success is still required before
another full continuation; no new permission or provider mutation is introduced.

Read-admission [37058454601](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37058454601)
at source `4732325020ffc7447242a1601d08ebfd8e47d6b2` passed. The same-source
continuation [37058617870](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37058617870)
passed all source/packaging gates, reused the owned sink/Queues, submitted
fetch-only API `01f14a8e-d5b1-41f9-9f8c-325c2e288ba7`, and completed the initial
scheduled-cohort cutover: 1,864.625790695 monotonic seconds, 30 pinned samples,
Standard old runtime, and both observed execution-lease counts zero and preserved.
Paused maintenance `bc616834-035f-4bb7-88d6-e29ce1ab5867` was replaced with active
scheduled-only `3d23d537-6379-4fcb-84c2-2c1b8a9f4857` and individually verified.

The run remains **FAILURE** at the subsequent complete split-graph check; remaining
ingress/lifecycle/site jobs were skipped. Fresh inspection
[37062907729](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37062907729)
confirmed those exact API/maintenance versions, API empty Cron, maintenance
five-minute Cron, both capture off, unchanged private sink, and the exact two
API + maintenance trace producers (DLQ has none). All sink predicates passed.
Diagnostic inspection
[37063591034](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37063591034)
confirmed the exact failure `split_role_absence_unverified`: the historical
staging contact Worker exists with email/scheduled handlers and five-minute Cron,
but has no Mail database, API/maintenance service, Mail body bucket or trace Queue
capability edge. The owner chose to retain it unchanged rather than deleting or
pausing unrelated contact operations to satisfy a name-only absence check.
The staging graph now brackets its immutable capability/serving/Cron snapshot
and rejects any Mail DB/R2/API/maintenance/sink service or trace main/DLQ edge.
Production still requires role absence. This proves the bounded Mail graph
separation, not population isolation or independent contact-monitor correctness.

An explicitly owned second continuation binds run `37058617870`, full source
gates, the API/paused/active typed submits and immutable 31-minute witness. It
reuses the existing API/maintenance/sink/Queues without schema/provider-policy
rewrites or another cutover wait; only the remaining adapters/site use current
same-run tested bytes. Fresh complete read admission must pass before proceeding.
No completed native/site acceptance or justification for replaying successful
API/maintenance submissions follows from these facts.

Continuation [37065145834](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37065145834)
at source `4f30e0274827c934feea57b75f8a29a9fbc9b597` passed every source gate,
owned API/maintenance/sink reuse and the complete active Mail graph. It submitted
ingress `09c34d0f-1147-467c-85f0-e7711d96d8fd` and lifecycle consumer
`63733c7c-6238-4522-be0f-befb5e8c4799`, and completed subscription reconciliation.
The subsequent complete adapter readback failed; site deployment was skipped.
These successful submits must not be blindly replayed. Current adapter diagnostic
reads preserve the exact version pins and project Queue consumer/settings/producer
shape and subscription predicates without message content or raw provider prose.
No predicate is relaxed before the actual failure shape is understood; the native
journey and candidate site acceptance remain incomplete.

Local lightweight source/mock checks cover staging context, immutable bounded
usage models, drift rejection, retained lease/backlog semantics, future split
replacement without the initial wait, exact adapter graph, candidate provenance
and site stale-copy rejection. No local Rust/Wasm/browser build, provider mutation,
mail send or deployment was performed for these checks. The independently reviewed
immutable usage-model member was corrected to `resources.script_runtime`; its
positive/negative fixtures are part of hosted admission. Actual hosted checks,
performance measurements, new graph readback, native journey and site/browser
acceptance must be added here only after their runs produce evidence.
The bounded native staging journey was extended to read new owner-visible
surfaces and correlate its existing second SMTP fixture to the first verified
DATA receipt. Its local mocked fixtures prove harness ordering/error contracts,
not actual provider delivery; no live outgoing feedback is claimed under the
staging global hold. A separately confirmed one-use owned self-send probe is now
prepared, including atomic live-grant refusal, first-output loss recovery, exact
same-key replay, actual outcomes/events and retained unknown intent ZIP. Its local
mock/SQLite tests prove harness and grant predicates, not delivery. Runtime outbound
feedback remains covered by hosted synthetic Wasm/D1 tests until that authorized
real canary is actually executed and its evidence recorded here.

Staging [36719116852](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36719116852),
source `17abe25`, passed one-principal native PKCE/two-message receive/search/ZIP/
cleanup and two `limit=1` exact-cosine pages:
`max_abs_error=0.00000000,count=2,order=true,origin_vector=true`; primary/cleanup
`none`. This is not a large-mailbox benchmark or proof of every tie/third-page/
tampered-cursor/ten-address case. Production isolation is real bounded evidence,
not exhaustive formal verification.

The owner's original account belongs to production Identity. Its historical
staging rejection was a realm mismatch, not a production password defect. The
synthetic production journey does not claim the owner's account was exercised.
Correlation is not a complete native Cloudflare trace waterfall. No measurement
establishes large-mailbox throughput or an indexing latency SLA.

## Verification proportional to value

The owner's preserved local audit records source-level repair candidates outside
this cleanup: orphan-object cleanup versus accepted-send projection race, allocation
atomicity, ZIP actual-byte cap, re-login marker ordering and no-op read-state
generation changes. They are not fixed by deleting infrastructure/tests/docs. The
untracked owner audit remains local and intact; triage these against product impact
before adding machinery or claiming resolution.

Use focused Rust business-contract tests, Worker/Wasm boundary checks, CLI
cross-platform checks and the site build in hosted CI. Local static syntax/link/
diff checks are fine; artifacts stay under root .temp/.cache. No per-patch audit
report, incident workflow or test of a test merely to inspect its spelling.
Repeat real mail only for a changed delivery boundary or new failure, using
authorized owned synthetic accounts and exact cleanup. Reuse successful evidence.

For this simplification, local static validation found no imports of deleted Python
modules; actionlint v1.7.11 accepted retained workflows (local shellcheck/pyflakes
disabled; normal hosted checks remain). The 52 focused infrastructure safety tests
and 22 Mail API privacy tests passed. A separate synthetic ZIP probe accepted
current six-tree and historical seven-tree bootstrap artifacts. Native JavaScript
syntax and local imports passed. This initial local verification did not execute
the hosted Rust/Wasm/runtime pipeline; premerge CI is a separate check. No provider
access/deployment or heavy local Rust/Wasm build occurred.

Premerge source `00d74df` passed [hosted checks 37035990692](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37035990692):
all three CLI platforms, Rust unit tests, Wasm builds, retained workerd boundaries,
infrastructure safety and both site states. Deployment/provider/mail jobs were
skipped. The retired Cargo target and test-only observer entry were corrected
before this pass; this is source acceptance, not production rollout evidence.

On 2026-10-03 the owner selected maintenance-only publication, preserving unchanged
live services. Source `c66dbba` passed [main CI 37038760121](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37038760121)
and [workflow guard 37038759966](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37038759966).
Application sources, production configs, migrations and site inputs are unchanged
from recorded production source `6414b203`; the lockfile only loses the retired
tracing experiment. No Worker/site deployment, policy change or provider write
was performed. Fresh exact-route GETs returned Mail health 200, anonymous address
list 401, and home/manual/changelog 200 with published v0.1.0 copy and Release links.
These public checks do not re-establish SMTP delivery or private graph inventory.
