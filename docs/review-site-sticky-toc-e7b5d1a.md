# Independent sticky-header scroll source review

Date: 2026-10-01. Reviewed source: `e7b5d1a9a39b1e437f961c7ce32b739736300acf`
against `73874d6a5d40ac542abefb0a9b88af99bbf28573`.
Reviewer worktree: `.temp/site-sticky-toc-source-review`.

## Decision

**GO for integrating this focused source into a diagnostic hosted preview;
NO-GO for declaring the browser gate closed or authorizing deployment on static
reasoning alone.** No substantive blocking defect was found in the reviewed
CSS diff. The nested-overflow mechanism is a supported explanation, not yet an
observed ancestor trace. Keep the diagnostic amendment and unchanged visibility
assertion; run them against the exact integrated source identity.

This is not publication, merge/deployment authorization, Mail acceptance, a
skip-focus waiver, or proof of every browser/device configuration.

## Evidence and scope

Read the implementation note, candidate-lane contract and independent hosted
browser review before inspecting layouts, foundation CSS and site styles.
Inspected the exact three-file delta, shared header/viewport, manual article,
changelog release heading, existing fragment links and reduced-motion rule.
The production delta consists only of `global.css` and `changelog.css`; no
layout, heading ID, release-state branch, provider header, workflow or download
contract changes.

Inspected the already-downloaded original hosted `report.json` in
`.temp/site-visual-hosted-acceptance/.temp/hosted-browser-run-36808670970/`.
It identifies source `d996547c92f1e2ecffcad986fb5e6c12466054da`, target
`source-preview`, no deployed revision, and start
`2026-10-01T03:03:28.570Z`. Its recorded first-heading failures agree with the
source note. Run [36808670970, attempt 1](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36808670970)
is failed browser evidence for the old source, not a result for this fix.

| Width | Observed header bottom | New header-height expression | New viewport top exclusion |
| --- | --- | --- | --- |
| 320 / 390 | 125.1875 px | 125.2 px | 149.2 px |
| 768 | 128.890625 px | 128.9 px | 152.9 px |
| 1440 | 77 px | 77 px | 101 px |

Numbers in the expression columns are arithmetic predictions, not a rendered
measurement of the revised source. Subpixel rounding explains the small
difference from the old-source observed geometry.

## Static assessment

1. **Correct ownership of the obstruction.** `global.css:html` puts the
   exclusion on the viewport, where the shared sticky header obscures content.
   Root scroll padding is not inherited into the article. The manual retains
   `overflow-x:auto`; CSS cross-axis computation makes its vertical overflow
   `auto`. Its unconstrained content height does not itself prove a usable
   vertical scroll range. Root padding removes dependence on a heading margin
   surviving inner scroll-range clamping, including the first heading at the
   article's beginning. No first-heading exception or overflow removal is
   introduced. Actual ancestry and scroll behavior still require the rerun.
2. **Responsive geometry preserves appearance.** Desktop inner min-height is
   still 76 px and the border still 1 px. The explicit header line-height 1.7
   equals the existing inherited foundation body value. CTA sizes/padding retain
   their values at both breakpoints. Wrapped height accounts for 30 px outer
   padding, the larger of brand/CTA first-row heights, 14 px row gap, 14 px nav
   text at line-height 1.7, 16 px nav padding and 1 px border. Current Chinese
   nav items remain single-line horizontal scrollers. Desktop TOC top remains
   108 px; mobile TOC is static, so the changed top expression is inactive there.
3. **Avoid double offset.** Removing the 105/110 px heading margins is coherent:
   keeping them alongside root padding would compound the exclusion. Desktop
   destination gaps change slightly (manual 105 to 101 px; changelog 110 to
   101 px), while still leaving the intended 24 px below the 77 px header.
   Normal layout spacing is unchanged; scroll padding does not create document
   padding or move unfragmented page content.
4. **Existing fragments and minimal content.** TOC, installation CTA, inline
   privacy links and direct hash URLs keep the same targets and now share the
   viewport exclusion. Root padding cannot create negative scroll positions or
   extra content at a short document's end: an unreachable alignment is bounded
   by available scroll range. A near-start target therefore need not have the
   full 24 px gap, but must still be visible. The existing `#main` starts after
   the in-flow header; this diff does not change focusability or keyboard focus
   continuation. It also does not promise that an end-of-page target reaches an
   exact pixel offset.
5. **Mobile safe area and compatibility.** No `viewport-fit=cover`, safe-area
   padding, fixed header inset or viewport metadata is changed. The formula
   follows current CSS header geometry, not a new notch-specific layout. Real
   mobile visual-viewport/browser-chrome behavior, platform scrollbars, zoom,
   larger user fonts and other engines were not established by the original
   desktop Chromium run. Do not silently extend that acceptance claim. The
   formula must evolve with future header geometry changes; the source note
   correctly identifies its dependent nav/row/padding values.
6. **Release-candidate boundary.** Candidate copy, future installation wording,
   noindex/source headers, download destinations and promotion fixtures are
   byte-unchanged. The fix has no path to provider, release or Mail mutation.

## Required next discriminator

Run the reviewed diagnostic harness on the exact source that includes this fix.
Record run/attempt, checked-out merge/source SHA and deployed revision separately.
For manual first and later headings, capture computed overflow, scroll padding,
scroll margin, client/scroll dimensions and scroll positions for all ancestors,
plus target/header rectangles. Confirm whether the article is the inferred
nested scroll container and whether its range limits the old margin behavior.
If the measured mechanism differs, revise the explanation rather than weaken
the unchanged heading visibility assertion.

All generated TOC entries at 320/390/768/1440 must retain exact target activation
and satisfy the existing measured-header visibility rule; additionally check
direct initial hash loading, the cross-route installation CTA, inline privacy
hashes, first-heading return after a later heading, and table right-edge
reachability. Compare header/nav and top-of-page screenshots for no visual
regression. Boundary widths around 580/850 are useful follow-up geometry checks,
not evidence already obtained. Treat skip-link focus continuation as a separate
unchanged failing gate pending its active-element diagnostics.

## External rationale and execution boundary

- [CSS Scroll Snap, scroll-padding](https://www.w3.org/TR/css-scroll-snap-1/#scroll-padding):
  viewport-owned exclusion and scroll-into-view use without requiring snapping.
- [CSS Overflow, overflow properties](https://www.w3.org/TR/css-overflow-3/#overflow-properties):
  cross-axis overflow computation supporting the manual ancestry hypothesis.

The most useful external discriminator here is standards-aligned browser
evidence, not an unrelated research redesign. Only Git/source/document/hosted
JSON inspection, official specification retrieval, `git diff --check`, isolated
worktree creation and this atomic documentation commit were performed. No local
project test, build, browser, dependency installation, hosted dispatch, push,
deployment or provider operation occurred. The primary and implementer worktrees
were not edited.
