# amail Goal progress snapshot

Date: 2026-10-01. Source baseline: main
`6f63e1f559bc2d0a5c9d27c40294349fcf77dde1`.
This is a product-wide checklist, not release permission. The
[infrastructure foundation](infrastructure-foundation.md) is the current work
priority. All required production and publication outcomes remain in scope.

## Status vocabulary

* **Implemented / source accepted:** reviewed code and applicable hosted checks
  exist. This is not proof of current serving code or real delivery.
* **Bounded actual acceptance:** a named real journey passed only its stated
  cases, environment and source. Do not extrapolate to production or every edge.
* **Incomplete / unexecuted:** implementation, current-state evidence or an
  actual required journey is missing. It is not necessarily a known defect.

## Product requirements

| Requirement | Implemented or observed | Remaining required outcome |
| --- | --- | --- |
| Rust agent CLI, short commands, compact pipe output, opt-in human formatting, no web mailbox or `view` | Source implemented; hosted Linux/Windows/macOS checks exist. | Publish and verify actual v0.1.0 downloads/install/first-run behavior. |
| Native ZIP pack/unpack, metadata and optional TOML, HTML/TEXT/assets and HTML-to-MIME compilation | Source implemented; bounded hosted native receive journey checked archive contents/assets. | Production receive and actual outbound recipient/rendering acceptance; complete release artifacts. |
| Generic Identity mechanism and browser-only authorization | Platform changes deployed; dedicated staging principal completed native PKCE. | Original account's production journey is UNEXECUTED. Its account is in production, not staging; the historical staging rejection is a realm mismatch, not an established production-auth bug. |
| CLI alias registration, ten-address maximum, reserved service names, ownership and deletion | Source implemented; one owned literal routing/retirement journey passed. | Real dual-principal isolation, quota/reserved boundaries and production lifecycle acceptance. |
| Composable time/title/metadata/body/regex/case-sensitive/read-state search | Source implemented; bounded receive/search/read/delete passed. | Remaining multi-principal, pagination/tamper/boundary cases and production acceptance. |
| Automatic Qwen 8B / 256-dimensional OpenRouter indexing and server exact cosine | Source implemented; two protected origin-vector results across two limit=1 pages had zero measured absolute error and correct order. Automatic third-party content processing is owner-approved and disclosed. | Tie/third-page/tamper cases, current production index/recovery and end-to-end acceptance. |
| Public user mail domain and private root-domain system identity/DNS | Literal routes and four standard-role forwards exist; owner confirmed role test delivery. Official system From remains mail@moesegfault.dev. | Current production Mail graph/DNS/TLS/ingress and real outbound feedback. Forwarding destination is private and must not be recorded here. |
| SQLite diagnostics, distributed tracing, privacy and loss visibility | Local request and local/auth command journals, enriched readers, search-poll compatibility and durable upload/loss accounting merged. | Producer capability rollout, local-to-API causal connection, full remote segments and actual retained native trace/error/privacy proof. Correlation alone is not end-to-end coverage. |
| GitHub Actions builds/tests/deploys with efficient iteration | Build once, verified artifacts, eight native fan-out suites, warm dependency cache observations and narrow diagnostic lanes accepted. Same-run ordinary deploy/inbox admission merged. | Actual final packaging/module evidence, held Mail deployment, bootstrap/activation/drain/rollback/recovery acceptance. No local project builds/tests. |
| Branded TypeScript/Astro/pnpm site: home/manual/changelog and TOCs | Candidate site live; run36812450154 passed 78 assertions across 12 page/viewport cases. | Release-backed download state and formal published-site acceptance; candidate status is not a public release. |
| Maintained progressive-disclosure user/Identity/maintainer skills | Source skills and supporting runbooks exist. | Verify published skill bundle against final CLI/contracts/assets. |
| GitHub Release v0.1.0 | Release pipeline and candidate artifacts exist. | Tag, actual published release, verified binaries/checksums/skills and protected release gates. No release is claimed. |

The bounded actual mail journey is
[36719116852](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36719116852),
source `17abe25`: one principal, native PKCE, literal route, two SMTP fixtures,
ZIP/content/assets, search/read/delete, exact route retirement, and two exact
cosine pages. Measured `max_abs_error=0.00000000`, `count=2`, `order=true`,
`origin_vector=true`. Do not rerun this merely because source changed; execute
the missing discriminating outcomes after infrastructure readiness.

## Parallel work and next convergence

| Owner stream | Current bounded delivery | Acceptance boundary |
| --- | --- | --- |
| Deployment leader and children | Fresh, positively owned held storage/bootstrap and receipt producer; preserve existing stores. | Actual paused graph first; activation/drain/rollback still separate. |
| Runtime leader and children | Local/auth command spans accepted in PR 68; rollback-safe enriched producer negotiation underway. | Preserve old wire and CLI behavior; hosted source success does not prove remote sink delivery or local-to-API causal connection. |
| Native tracing leader and children | Route plus new proxied DNS transport; per-case native/error/async/privacy evidence. | Latest workers.dev run36884872446 failed before cases; both scripts cleaned. New source transport requires review before root writes. |
| CI/performance stream and validator | Credential-free real Wrangler packaging and packaged-module runtime probe. | Source artifact hashes and packaged runtime evidence are distinct from uploaded production byte identity. |
| Maintenance leader and curator | Remove unsolicited push provider reads; maintain operational lanes and correct authentication status. | Manual supported recovery/diagnostic contracts preserved; no user-account workaround. |
| Independent reviewers | Source contracts and hosted evidence for each bounded slice. | Review records bind exact heads; changing source requires renewed relevant checks. |

Leaders may spawn child agents as explicitly requested. Root serializes only
conflicting provider writes and integrates reviewed work; it must not serialize
all independent analysis, implementation and validation. All worktrees and
experiment artifacts stay under repository `.temp`/`.cache`.

Public sending remains held. Foundation completion, business-debug resumption,
production deployment and formal release are separate outcomes; none is inferred
from green source checks, a candidate website or design documents.
