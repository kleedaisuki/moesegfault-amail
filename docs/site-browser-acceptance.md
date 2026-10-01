# Hosted candidate-site browser acceptance

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
of the current implementation. No browser pass is claimed by this document.

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
