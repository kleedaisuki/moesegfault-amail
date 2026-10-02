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
staging global hold. Runtime outbound feedback remains covered by hosted synthetic
Wasm/D1 tests unless a separately scoped owned canary is actually executed.

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
