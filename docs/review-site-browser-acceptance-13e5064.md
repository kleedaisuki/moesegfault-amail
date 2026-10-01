# Independent hosted site-browser acceptance review

Date: 2026-10-01. Exact implementation reviewed:
`13e5064326272304ff2d6435fb0ad161c6f21cc0`, relative to main
`73874d6a5d40ac542abefb0a9b88af99bbf28573`.
Reviewer worktree: `.temp/site-visual-hosted-review`.

## Verdict and authority

**GO for pushing this focused source and obtaining hosted evidence.**
No substantive blocking defect was found in the three-file change. This verdict
was communicated to root before any push; the reviewer performed no push.
It is not merge/deployment authorization, a browser execution result, closure
of the visual or accessibility gate, publication of v0.1.0, or Mail acceptance.

The diff adds only the independent browser workflow, its script and runbook:
408 inserted lines across three files. Existing source/deploy workflows, site
pages/styles, provider configuration and release gates are unchanged.

## Review basis

Read relevant release/candidate acceptance documents first, including
`site-release-acceptance-review.md`, `site-production-candidate-lane.md` and
`site-standalone-bootstrap-review.md`. Inspected the exact diff, shared layout,
manual/changelog layouts, release-state checker, CTA destinations and related
styles. Compared assertions with the actual user-facing contracts rather than
requiring that the present implementation necessarily pass.

| Boundary | Assessment and supporting source evidence |
| --- | --- |
| Events and permissions | Uses ordinary `pull_request`, not `pull_request_target`; default checkout and `github.sha` refer to the PR merge result. Only `contents: read` is requested and credentials are not persisted. No provider secret, environment, write permission, deployment command, reusable deploy call or Mail command is introduced. Manual inputs are passed via environment rather than interpolated into shell source. |
| Cost isolation | No push trigger and no existing CI change. Browser installation is confined to this workflow. PRs and manual source previews build the locked candidate site; live-candidate skips pnpm setup/install/build and validates the full lowercase deployed SHA before installing Chromium. |
| Browser/runner setup | Installs an exact Playwright package under repository `.temp`, suppresses npm install scripts, then explicitly installs Chromium with system dependencies and CJK fonts. The official Playwright CLI supports this single-browser hosted Linux path. Actual package downloads, apt availability, launch and runner duration remain hosted verification, not observed success. |
| Preview fidelity | Python serves the actual generated `site/dist`, bound to IPv4 loopback. Canonical trailing-slash paths correspond to generated index files. Shell strict mode, bounded readiness attempts plus final required curl, and an EXIT trap ensure failed readiness fails the step and the owned server is stopped on ordinary completion/failure. Provider headers are deliberately not simulated. |
| Live identity | Browser base is allowlisted to loopback or the fixed public site; no arbitrary URL input. Every initial route/width navigation requires 200 HTML, unchanged final URL, route-local candidate copy/service notice and absence of the published phrase. Live responses additionally require exact deployed revision and both noindex/nofollow tokens. Workflow-source SHA and deployed revision are separate report fields. |
| Four-width behavioral checks | Independently checks all three routes at 320/390/768/1440 CSS pixels. Document/body width checks permit intentional local scrollers. Skip behavior tests actual keyboard continuation into main, not an assumed tabindex implementation. Both CTA center hit testing and ancestor horizontal bounds supplement the page-wide overflow check. |
| TOC and tables | Actual clicks activate every generated manual/changelog fragment, demand exactly one target and test heading visibility below the measured sticky header. Manual cells must remain at least 14 CSS pixels, and the rightmost cell must be reachable through an overflowing ancestor. These are useful gross usability checks, not comprehension or screen-reader certification. |
| Failure semantics | Each named assertion catches and records its own error; later assertions/cases continue under ordinary assertion failures. The report is saved in finally after browser launch and failures yield exit code 1. Uncaught setup/context/cleanup errors also fail the process rather than print PASS. Setup failures before browser launch may produce no JSON; the runbook explicitly does not claim otherwise. Upload runs with always, and absent evidence only warns without turning prior failure into success. |
| Evidence/privacy | Upload allowlist contains screenshots, bounded assertion report and preview access log, not installed tools, dist, environment, tokens, HAR, storage state or browser trace. Browser contexts have no login/session fixture, and the script follows only page/TOC/manual fragment links, not external Release downloads. Current source and fixed live target are public candidate pages. Do not interpret fork-produced artifacts as trusted deployment input; no consumer is introduced here. |
| Compatibility | No existing command, workflow input, deployed route, release-mode output, source header or generated-header promotion contract changes. Browser script is Node ESM, and Bash/Python runner handling is intentionally Linux-specific; the runbook does not claim Windows/macOS browser/font acceptance. |

## Remaining evidence, not findings

1. Obtain a real hosted run for the integrated source identity, including actual
   harness installation, launch and all 12 cases. No local build/test/browser
   or provider operation was performed in this review.
2. A narrow-screen TOC failure may be real: existing heading scroll margins
   are fixed (manual 105 px, changelog 110 px), while the mobile header wraps.
   Source inspection cannot establish rendered height. Preserve the measured
   header assertion, inspect hosted evidence and fix source if necessary; do
   not weaken the test merely to accept current layout.
3. Independently review all screenshots and record run/attempt/source/revision
   identities. Automated success is not a human visual pass. Screen-reader,
   zoom, other browser engines and dark mode remain explicitly unverified.
4. Existing candidate publication/link/header checks remain authoritative for
   their wider contracts. This new browser check supplements them; it does not
   replace exact source CI, published-header isolation, live candidate smoke,
   Release-byte verification or operational authorization.

These are meaningful next observations, not speculative blockers. The task is
a bounded verification integration; an academic redesign would not resolve
the actual missing evidence more effectively than hosted behavioral checks
and independent human review.

## External contracts checked

- [GitHub workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows): ordinary PR checkout and merge-source identity.
- [GitHub workflow permissions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax): explicit permissions leave unspecified scopes disabled.
- [GitHub PR security](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target): ordinary PR isolation instead of privileged execution of untrusted source.
- [Playwright browser installation](https://playwright.dev/docs/browsers): explicit Chromium installation with Linux system dependencies.
- [Playwright CI](https://playwright.dev/docs/ci): hosted Linux dependency setup and browser execution.

Only Git source inspection, document reading, official documentation retrieval,
`git diff --check`, isolated worktree creation and this documentation commit
were performed. No production file was edited, implementer worktree changed,
local project tests/build/browser run, dependency installed, hosted workflow
dispatched, remote push made, or provider/SMTP/DNS/tag/Release mutated.
