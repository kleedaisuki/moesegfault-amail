# Hosted candidate-site browser acceptance

## Current fixed hosted live-candidate pass (2026-10-01)

**PASS for the bounded automated browser contract at deployed source
`47d391615e671722c7f01bb7cf8963987f6150f9`; not full visual/accessibility or
Mail/release acceptance.** [Live run 36812450154](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36812450154),
attempt 1, main, workflow_dispatch, completed success. Its report records:

| Identity / measurement | Observed value |
| --- | --- |
| Target / base | `live-candidate` / `https://amail.moesegfault.dev` |
| Workflow source / deployedRevision | Both `47d391615e671722c7f01bb7cf8963987f6150f9` |
| Capture interval (UTC) | 2026-10-01 03:52:23.131–03:52:52.938 |
| Matrix | `/`, `/manual/`, `/changelog/` at 320, 390, 768 and 1440 CSS pixels: 12 cases |
| Named check totals | 78 passed, 0 failed; includes screenshot capture, which is not human visual approval |
| Artifact | `site-browser-36812450154-1`, ID `11140635520`; report and 66 PNG screenshots |

The downloaded report was inspected at repository-relative
`.temp/live-site-browser-36812450154/site-browser-36812450154-1/site-browser-evidence/report.json`.
Counts were recomputed from `cases[].checks[].passed`; screenshots were counted,
not independently visually reviewed. The hosted report/artifact remains the
primary evidence; this local retrieval path is not a permanent published asset.
Retrieve it while retained via `gh run download 36812450154 --name
site-browser-36812450154-1 --dir .temp/live-site-browser-36812450154`.

Exact route/candidate identity, no page-wide overflow, skip-link/continuation
focus, CTA/local installation/privacy destinations, all local TOC target
clearances, rendered privacy emphasis, manual cell readability/reachability
thresholds and mobile table column visibility without horizontal scrolling
passed where applicable. Table checks
measure their declared thresholds, not human comprehension. This run performs
browser GET/navigation only; it does not build/deploy the live site.

[Main source-preview run 36811172838](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36811172838)
also completed success at the same workflow source before deployment. It is
separate source-preview evidence, not the reason the live site passes. The
[deployment ledger](site-production-candidate-lane.md#current-fixed-candidate-update-and-live-browser-outcome-2026-10-01)
connects the corrected deployment, fixed Worker version and same-run live smoke.
Earlier failed hosted runs below retain their real failure observations and
fix rationale; they are historical, not current failures.

No new human screenshot judgment, screen-reader announcement/reading-order
check, contrast/zoom certification, cross-browser/OS/font guarantee, clean
archive install, provider/DNS health or Identity/Mail/send readiness follows.
The [earlier human visual review](review-site-visual-artifact-36809632215.md)
is scoped to its own source-preview artifact; do not relabel it as review of
this live artifact. No local tests, browser execution or mutation occurred in
this documentation curation.

## Purpose and evidence boundary

The candidate deployment ledger in `site-production-candidate-lane.md` proves
bounded HTTP/header/copy/TOC acceptance, not visual or keyboard usability. This
independent workflow fills that gap without adding browser installation to
every Mail source iteration or changing the deployment gate.

Source inspected: `origin/main` at
`73874d6a5d40ac542abefb0a9b88af99bbf28573`. Relevant contracts are the shared
skip link and main navigation in `BaseLayout.astro`, generated local TOCs in
`ManualLayout.astro` and `changelog.astro`, native installation/privacy links,
and the page-local candidate state/service boundary in `candidate_site.py`.
Expected results below derive from these user-facing contracts, not screenshots
of the current implementation. This original implementation section claimed no
browser pass; later run-specific outcomes are recorded separately above and below.

## Invocation and target identity

Workflow: `.github/workflows/site-browser-acceptance.yml`, **Site browser
acceptance**. It receives only read-only repository permission, no provider
secrets, and never calls Wrangler or a deployment/release/Mail workflow.

- Relevant pull requests run `source-preview`: hosted locked site install,
  candidate build/state check, then a Python static server bound to runner
  loopback. This checks the checked-out PR merge source, not the live domain.
- Manual `source-preview` checks the selected workflow source the same way.
- Manual `live-candidate` performs browser GET/navigation only against the fixed
  `https://amail.moesegfault.dev` host; **no site dependency install or build**.
  Supply `candidate_revision` as the full lowercase 40-character SHA actually
  deployed, not the newer workflow-source SHA. Every initial route response
  must identify that exact revision and `noindex, nofollow`. Historical deployed
  source `de2f1508005ff84841bc197b7181c5177f145857` is recorded in the existing
  deployment ledger; recheck current live identity before using it.

For example, after independently reviewed integration to the default branch:

```sh
# A read-only live-site browser run, not a deployment authorization.
gh workflow run site-browser-acceptance.yml --ref main \
  -f target=live-candidate -f candidate_revision=<full-current-deployed-sha>
```

There is no push trigger, reusable deployment hook, provider environment, or
arbitrary URL input. Workflow cancellation affects only this acceptance lane.
Default-branch registration and a separate root decision to push/dispatch are
still required; this implementation does not perform either operation.

## Focused acceptance matrix

All three routes (`/`, `/manual/`, `/changelog/`) run at 320, 390, 768 and
1440 CSS-pixel widths, with 900-pixel height, Chinese locale, light color scheme,
and reduced motion in pinned Chromium via `playwright@1.51.1`.
The hosted runner installs Noto CJK fonts so Chinese screenshot review is not
invalidated by missing glyphs; this is not a Windows/macOS font-fidelity claim.

| Claim | Reproducible check / evidence |
| --- | --- |
| Route and candidate truth | Exact final URL, HTTP 200 HTML, single main landmark, route-local candidate status and service disclaimer; live revision/robots headers |
| No page-wide horizontal overflow | Document/body scroll width no more than viewport + 1 CSS pixel; intentional local code/table scroll remains permitted |
| Skip link and focus | First keyboard Tab lands on visible skip link with outline; Enter reaches `#main`; next Tab is inside main rather than header; focus outline remains present |
| CTA clipping | Every header/action/release CTA is visible, inside horizontal viewport and unclipped by horizontal overflow ancestors after scrolling into view; no download is followed |
| Install/privacy destination integrity | Existing `/manual/#...` destinations resolve to actual IDs by navigation, including cross-route homepage disclosure links |
| TOC usability | Every manual/changelog entry has exactly one local target; actual click sets expected fragment; target heading begins below sticky header and inside viewport |
| Manual table reachability | Tables exist; every cell is at least 14 CSS pixels; overflowing table's scroll container permits reaching its rightmost cell |
| Human visual evidence | Viewport/full-page screenshots per route/width, focused skip-link screenshot, manual table screenshots, timestamped JSON assertions |

Artifact `site-browser-<run-id>-<attempt>` is retained for 14 days, including
failure evidence. Assertions are independently recorded per case instead of
allowing one failure to suppress all subsequent route checks. Keep useful
review findings in the repository before artifact expiry; do not retain routine
runner chatter as release evidence.

### Required human review before closing the visual gate

Review all 12 viewport/full-page pairs, not just desktop. Inspect readable text
and tables, CTA wrapping, header/menu layout, content ordering, privacy warning
placement before actions, focus visibility, and whether locally scrolling wide
tables are discoverable and comfortable on a narrow screen. Screenshots are
review artifacts, **not** pixel-diff baselines or an automated aesthetic pass.
Full-page captures can be tall; viewport/table captures provide practical
zoomed evidence. Record run URL, attempt, workflow-source SHA, live revision if
applicable, artifact review outcome and reviewer identity.

## Known limits and consequential next checks

- This is Chromium-only, light-mode and 100% zoom. It does not establish
  Firefox/WebKit compatibility, dark-mode readability, touch gestures, 200%
  text/zoom reflow, contrast compliance or accessibility certification.
- Playwright keyboard checks cannot prove screen-reader announcements,
  landmark/heading navigation or usable table reading. A real screen reader
  (for example NVDA with an actual supported browser) remains an independent
  manual check. Native skip continuation is checked behaviorally, not by
  demanding a `tabindex` that the public contract never specified.
- Table font-size/reachability checks catch gross shrink/clipping, not actual
  comprehension. Horizontal scrolling is allowed; human judgment must assess
  discoverability and layout, especially because the current prose container
  itself permits horizontal overflow.
- Headings hidden behind the sticky header are real navigation failures; do
  not weaken the assertion merely because current fixed offsets differ from
  the mobile header height. Likewise an unclipped page can still contain a
  clipped CTA, which is why both checks exist.
- Source preview deliberately does not emulate provider headers/redirects/DNS.
  Live checks establish only the fixed observed deployed source, not changes in
  a newer source-preview run. Both evidence identities are recorded separately.
- There are no release-asset downloads, CLI installs, Identity sign-in, SMTP,
  provider mutation, send-hold changes, or Mail readiness assertions.

## Implementation verification performed locally

All added files are isolated in repository-relative worktree
`.temp/site-visual-hosted-acceptance`; the shared primary worktree is unchanged.
Only source inspection and static checks were permitted:

```powershell
node --check site/scripts/browser-acceptance.mjs
git diff --check
python -c "import yaml; from pathlib import Path; yaml.load(Path('.github/workflows/site-browser-acceptance.yml').read_text(), Loader=yaml.BaseLoader)"
```

No local project test, build, dependency installation or browser run occurred.
The first hosted run must establish harness/browser setup correctness; a
dependency/network/runner failure is not automatically a site defect. Hosted
workflow lint, successful execution, independent code review and manual
screenshot/screen-reader review are pending, not silently assumed.

## First actual hosted run: failures preserved

PR [#24](https://github.com/kleedaisuki/moesegfault-amail/pull/24), head
`3250ae9511e23cee69cb838cd00dfc91b8c128b0`, triggered browser run
[36808670970, attempt 1](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36808670970).
The actual checked-out PR merge source recorded in the report is
`d996547c92f1e2ecffcad986fb5e6c12466054da`, not the PR head. Browser checks ran
2026-10-01 03:03:28–03:03:51 UTC. Hosted candidate build/state checks, pinned
browser install, CJK fonts and browser launch succeeded; behavioral checks
**failed**. Artifact `site-browser-36808670970-1`, ID `11139275320`, contains
the original screenshots/report and preview server log.

| Width | Manual first heading top / header bottom | Changelog heading top / header bottom |
| --- | --- | --- |
| 320 | 0.703 / 125.188 | 110.203 / 125.188 |
| 390 | 0.344 / 125.188 | 110.203 / 125.188 |
| 768 | 0.547 / 128.891 | 110.672 / 128.891 |
| 1440 | 0.844 / 77.000 | Passed; original harness did not retain passing geometry |

The manual first target is `先认识-amail`; changelog target is `v0.1.0`.
These measured headings begin behind the sticky header. Original TOC checking
stopped at the first failure in each route/width; later manual targets are not
verified by that run. The assertion remains unchanged. Added diagnostics now
record computed heading margins and scrolling ancestors, capture each failed
TOC target, and continue through all entries before failing the named check.

All 12 skip/focus checks failed specifically at the **second** focus-outline
assertion, after Enter and Tab into main. This stage identification is supported
by all 12 saved `*-skip-focus.png` images: those captures occur after the first
outline assertion. Direct inspection of `320-manual-skip-focus.png` shows the
visible skip link and clear outline. The original error expression did not
distinguish stages or include the active element/style. This is not evidence
that the skip link itself lacked a focus ring. The next diagnostic reports tag,
class, `:focus-visible`, computed outline style/width/color at both stages and
saves `*-main-continuation-focus.png` before asserting. It does **not** weaken
the existing minimum-outline or keyboard-continuation contract. Whether the
second-stage failure is a product issue or an over-specific outline assumption
requires that actual browser evidence, not guesswork from CSS alone.

Route/candidate identity, page overflow and CTA/destination checks passed in
all 12 cases; table font-size/right-edge checks passed at all four widths.
Screenshot capture passed, but this is not a complete human visual review.
Independent hosted runs also succeeded:
[syntax 36808670944](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36808670944),
[candidate source CI 36808670923](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36808670923),
and [main CI 36808671216](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36808671216).
No deployment/provider jobs ran; these successes do not cancel the browser
failure or establish live-source/screen-reader acceptance.

Artifacts were retrieved solely with `gh run download 36808670970 --dir
.temp/hosted-browser-run-36808670970` inside the isolated worktree. Screenshot
viewing is inspection of hosted output, not local browser execution. No
production source was changed by the validator. A separately owned source fix
and diagnostic-only harness amendment require independent review before the
next hosted run; no blind rerun or failure waiver is justified.

### Diagnostic run: separate style timing from real anchor defects

After independent approval of diagnostic-only `384c75e`, run
[36809130233, attempt 1](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36809130233)
ran the unchanged site with actual PR merge source
`f050fa33db2ac48f5c6d4d05296759631b646aaa`. Build/install/launch again passed;
behavioral checks failed. Active continuation elements were ordinary links,
not automatically focusable prose containers. Diagnostics reported
`:focus-visible=true`, `outlineStyle=solid` but `outlineWidth=0px` at immediate
sampling. Yet the subsequent hosted `320-home-main-continuation-focus.png`
visibly draws a clear outline around the focused privacy link. At 320 changelog,
the same zero-width sample occurred even at the first skip-focus stage.

This is evidence of a keyboard-event/style-resolution sampling gap in the
harness: the screenshot is captured after the immediate diagnostic evaluation,
and the site stylesheet specifies the existing 3-pixel focus outline. The
focused element and contract must be checked after bounded browser presentation
settling, not only immediately after keyboard dispatch. The amendment waits
up to one second with animation-frame polling for the **same** non-none,
at-least-2-pixel computed outline, then records and asserts it. A timeout does
not become success; final computation still must satisfy the original predicate.
It introduces no fixed sleep, manufactured focus, injected styles or weakened
outline requirement. Actual success remains a hosted observation pending review.

TOC measurements independently confirm a real source issue. Manual headings
compute a 105-pixel margin, but their prose article has `overflowY=auto`,
`scrollTop=0` and equal client/scroll heights (12977/11548/8429/7912 pixels for
320/390/768/1440 respectively). The first heading still lands at root top ~0;
subsequent installation headings land at ~105, below an insufficient margin
on narrow screens. Changelog has no scrolling ancestor and its 110-pixel margin
lands near 110; actual header bottom is 125.188 or 128.891 on narrow screens,
versus 77 on desktop. Its desktop heading top was 110.344 and passed. These
measurements are preserved in report `tocGeometry`; per-target failure images
now include `320-manual-toc-0-failure.png` and
`1440-manual-toc-0-failure.png`. The source owner must fix actual viewport anchor
clearance rather than hiding this difference in the assertion.
