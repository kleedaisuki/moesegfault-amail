# Mobile manual table readability

## Observed problem and scope

Base: PR24 source `e627a6064c61011743adde84cbe3ae1ac80bd525`, not
`main`. Hosted source-preview screenshots from run `36809632215`, attempt 1,
showed the installation table with only its device column at 320 CSS pixels;
at 390 pixels only a clipped sliver of the archive column appeared. Existing
automated right-edge reachability can pass while a reader has no visible cue
that the installation filenames require horizontal scrolling.

Reviewed evidence: `320-manual-table-1.png` and `390-manual-table-1.png` in
artifact `site-browser-36809632215-1` (reported source
`4a76064a9db414033c0eb336474a29cf516261b4`, not a deployed revision).
The independent visual review is recorded in commit `2c50418`, document
`review-site-visual-artifact-36809632215.md`. Relevant shared contracts are in
`site-browser-acceptance.md` and `site-release-acceptance-review.md`.

## Design and compatibility

The manual currently has three two-column tables: human/agent responsibilities,
platform/archive mapping, and sending limits. At the existing 580-pixel mobile
breakpoint, `manual.css` now uses fixed table layout and permits normal cell
wrapping, with `overflow-wrap: anywhere` for uninterrupted archive filenames.
The inherited full table width gives both columns space without requiring a
hidden swipe. Fixed layout prevents long filenames from allocating almost all
available space to one column. Text wraps visually; filename bytes, copying,
links, Markdown content, table/header semantics and the existing 14-pixel cell
font remain unchanged.

The override is manual-specific and mobile-only. Desktop/tablet styles above
580 pixels, code-block scrolling, the shared article overflow fallback and
other routes are unchanged. No JavaScript, cards, extra scrolling controls or
browser-harness changes are introduced. All current tables have two columns;
future wider tables need a deliberate narrow-screen design review rather than
assuming that this layout guarantees readability for arbitrary schemas.

## Verification boundary and next acceptance

Performed source inspection of all three Markdown tables, stylesheet cascade,
the cited hosted screenshots, and a whitespace/error check with `git diff
--check`. No local project tests, build or browser were run, as requested.
This is a source fix, not a new rendered visual pass.

Independent review and hosted source-preview acceptance must verify both
headers and both columns at initial horizontal scroll position, especially
320/390 pixels, retain the existing cell-font and reachability assertions,
and review the three table screenshots for readable wrapping. The 768/1440
screenshots should remain unaffected. Root owns PR24 integration and any
push/dispatch; this work does not authorize deployment or release.
