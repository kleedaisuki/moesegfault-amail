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

## Diagnostic-only follow-up: `384c75e`

Exact delta reviewed: `3250ae9511e23cee69cb838cd00dfc91b8c128b0` to
`384c75e947d45bed8411ce605ae9c9adf3d018d7` (two files, 89 additions and
10 deletions). **GO for the diagnostic hosted rerun; no substantive finding.**
This was reported promptly to root before the rerun decision. It does not waive
the already-failed browser gate or approve any future CSS implementation.

- Focus still requires an outline style other than none and width >= 2 px.
  New return fields expose public element tag/id/class, focus-visible state
  and computed outline properties; both callers assert the same passes value.
  Keyboard continuation must still be inside main. Its new screenshot occurs
  before those assertions to preserve failure evidence, not to replace them.
- TOC still requires nonempty links, one exact local target, matching activated
  fragment, and `top >= header.bottom - 1 && top < innerHeight`. Geometry
  failures now append evidence and continue to later entries, then assert zero
  failures. No target tolerance or viewport width changes. Structural or click
  failures still fail the named check immediately, as before.
- Added scrolling-ancestor diagnostics contain CSS and geometry, not mail,
  page text, credentials, storage state, trace or request headers. Screenshot
  paths are generated solely from the existing fixed width/route/index values.
  The workflow, permission, upload scope and public/loopback target remain
  byte-unchanged. Current fixtures contain no authentication or private data.
- Inspected the already-downloaded hosted `report.json` under the implementer
  worktree without running a browser. Its source, timestamps, four-width TOC
  failure measurements, 12 focus failures and other named-check outcomes match
  the added first-run ledger. All 12 original skip-focus screenshots exist;
  their creation follows the first outline assertion, so identifying the
  second outline failure is justified. Separate CI success/run metadata and
  the individual screenshot visual interpretation were not re-observed here.

Performed source diff inspection, existing JSON/file evidence inspection and
`git diff --check` only. No local browser/build/test, hosted dispatch, dependency
installation, provider operation or implementer-worktree edit occurred.

## Bounded presentation settling: `681f09b`

Reviewed exact commit `681f09b2fcde8d7710286cd6a19e140e2fa0c90c`:
six harness lines and the corresponding diagnostic ledger. **GO for integration
with independently reviewed CSS `e7b5d1a` and copy `bd10e7c`, then a hosted
rerun.** This is approval to obtain new evidence, not a passing browser result.

The helper polls the original non-none/at-least-2px computed-outline predicate
using animation frames for at most 1000 ms, then independently recomputes the
same returned passes field used by the unchanged assertions. Timeout is caught
only to preserve final diagnostics; it does not set passes or waive the final
assertion. No focus operation, injected CSS, fixed sleep or weaker threshold
is added. This shared helper applies to both initial skip focus and main
continuation, not just the second Tab; that matches the recorded first-stage
320-changelog failure as well. At most 24 seconds of bounded polling is added
across the entire matrix when all checks time out, within the existing workflow
budget. The changes have no path conflict with CSS/copy and introduce no new
sensitive artifact category.

Inspected the existing downloaded diagnostic JSON for run `36809130233`: source
`f050fa33db2ac48f5c6d4d05296759631b646aaa`, ordinary-link continuation focus with
focus-visible true/solid outline/zero immediate width, first-stage 320-changelog
zero width, manual ancestor dimensions and both heading measurements match the
new ledger. The screenshot/style-timing explanation is a supported mechanism
hypothesis, not proof that every future focus state succeeds; the new bounded
wait and final assertion are the discriminating hosted observation.

[Playwright waitForFunction documentation](https://playwright.dev/docs/api/class-page#page-wait-for-function)
defines animation-frame polling and explicit timeout, matching the amendment.
No local browser/build/test/provider action was performed. Source inspection,
downloaded JSON inspection and diff-whitespace checking only; production and
implementer source were not modified.

## Initially visible mobile columns: `31f772b`

Reviewed exact test-only commit
`31f772b4fd9b2f7d48976a6c835dbfb529181653` (42 added lines, one harness file).
**GO for integration with separately reviewed forthcoming table CSS and hosted
rerun.** No substantive blocking issue found; this does not approve CSS not yet
reviewed or establish actual responsive acceptance.

The new check runs only for the manual at 320 and 390 px. It resets scrollLeft
on the table and every ancestor before collecting geometry, preventing the
existing right-edge reachability probe from manufacturing initially visible
columns. All headers plus the final cell of every row must have nonzero boxes,
visible CSS visibility and horizontal bounds within the viewport and each
overflow-clipping ancestor's client area. Current source tables have ordinary
Markdown headers and no spans; headers cover every column, and every final
body cell is additionally measured. There is no requirement that every row be
inside the vertical viewport simultaneously, so tall tables are not falsely
rejected merely because some rows require vertical scrolling.

The original minimum-font-size and horizontally-scrollable rightmost-cell
reachability implementation is unchanged and still called separately. New
failure collection preserves evidence across tables and ultimately asserts
zero failures. Screenshots and truncated cell text concern the current public
manual only; no request/session/storage/credential source is introduced.
This check measures cell-box geometry, not text comprehension, opacity/contrast
or screen-reader accessibility. Those existing visual-review boundaries remain.

Inspected current Markdown table structure and exact diff; performed
`git diff --check`. No local browser/build/test, hosted dispatch, dependency
installation, provider action or implementer-worktree modification occurred.
