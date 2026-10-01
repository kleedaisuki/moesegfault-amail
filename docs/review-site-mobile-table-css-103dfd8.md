# Source review: mobile manual table wrapping 103dfd8

Date: 2026-10-01. Independent reviewer: `/root/site_mobile_table_css_review`.

## Exact scope and decision

**GO for a hosted source-preview browser rerun of the integration containing
CSS commit `103dfd8747d07a4a5dd40e4c5c4a1413069d8db2` and test-only commit
`31f772b4fd9b2f7d48976a6c835dbfb529181653`. No substantive source defect found.**
This is not rendered acceptance, deployment authorization, or release/Mail
readiness. Record the actual integrated source SHA in the hosted report; neither
individual commit identifies the combined tree.

Reviewed CSS against PR24 base `e627a6064c61011743adde84cbe3ae1ac80bd525`.
Recovered prior screenshot evidence through `2c50418:docs/review-site-visual-artifact-36809632215.md`
because that document is not present in the CSS branch. That independent review
records hidden second-column information at 320/390 in hosted source-preview run
36809632215, attempt 1, source `4a76064a9db414033c0eb336474a29cf516261b4`.
This review read that evidence document, not the original image pixels, and does
not reassert its visual observations as a fresh screenshot inspection.

## Source reasoning

| Contract | Assessment and evidence |
| --- | --- |
| Preserve actual tables | Only CSS changes in production. `manual.md` retains all three two-column Markdown tables; no DOM, display-role, heading, filename, quota, or copy transformation is introduced. Table/header semantics are preserved at source level, not independently screen-reader-certified. |
| Both columns initially visible at 320/390 | `global.css` supplies `width: 100%` and 14px table font. The mobile wrap is viewport minus 32px, and the reading grid is one column with a `min-width: 0` article. Fixed layout on current two-column tables without explicit column widths divides the expected 288/358px table into approximately 144/179px columns. The 24px horizontal cell padding leaves approximately 120/155px for text. These are source-derived estimates, not measured browser geometry. |
| Filename wrapping rather than clipping | The manual-specific cell selector overrides `.prose` cell `white-space: nowrap` by higher specificity. Normal whitespace and inherited `overflow-wrap: anywhere` also apply to the inline code filenames. Existing inline-code styling adds padding/border but no nowrap, fixed height, or truncation. There is no new hidden overflow, ellipsis, line clamp, inserted hyphen, or string mutation. Wrapped code background/border appearance and copying still deserve human inspection. |
| Quota readability | Existing 14px cell text is unchanged. Current numeric tokens, including `10,000`, are short compared with estimated available width. Longer scope/limit descriptions can increase row height instead of hiding the numeric column. No fixed row height is present. |
| Desktop and unrelated routes | All new declarations are scoped to `.manual-prose` and `max-width: 580px`; 768/1440 layouts and nonmanual routes receive no new declarations. No shared grid, overflow, code-block scrolling, header, TOC target, or scroll-padding setting changes. |
| TOC and overflow recovery | More mobile table height moves later headings naturally. Existing actual-click TOC and document/body overflow checks must still pass on the integrated tree; preserved declarations alone do not prove browser behavior. The article overflow fallback remains intact. |

This is a simple representation-level correction of the observed dominant case,
not additional scroll controls or special-case JavaScript. Future wider table
schemas are outside this assessment and require their own narrow-screen review.

The mechanism is consistent with primary platform specifications:
[W3C CSS fixed table layout](https://www.w3.org/TR/CSS2/tables.html#fixed-table-layout)
allocates unspecified columns from remaining table width; [W3C CSS Text wrapping](https://www.w3.org/TR/css-text-3/#overflow-wrap-property)
defines overflow wrapping for otherwise unbreakable strings. No research-heavy
alternative is needed to justify this bounded CSS repair.

## Interaction with test-only 31f772b

The added mobile assertion measures both headers and every last-column cell at
horizontal position zero, including viewport and scrolling-ancestor boundaries.
It runs at 320/390 before the existing font-size/right-edge-reachability check.
These operations complement the fix without replacing the existing checks or
weakening desktop, page overflow, focus, or TOC checks. Existing tables have exactly
two columns, so headers plus last cells appropriately cover the missing-column
failure. Captures are separately named `*-table-*-initial-columns.png`.

**Important evidence limit:** whole-cell rectangles being visible do not prove
glyph content is untruncated, filenames are comfortable to read, or row
associations are visually clear. The new assertion deliberately does not replace
human review. Independently inspect all three 320/390 table captures at practical
reading scale: both headings and all filenames/limits must be legible without a
swipe, especially `10,000`, 50/20 daily limits, and the Windows/macOS archive
suffixes. Compare 768/1440 captures with prior desktop evidence, and retain all
existing overflow, focus, and actual-click TOC assertions. A screenshot pass must
refer to the combined hosted source, not the historical run.

## Work boundary

Inspected exact diff, layouts, global/manual CSS, applicable vendored style
selectors, all current manual tables, browser harness, and existing acceptance
contracts; `git diff --check e627a606 103dfd8` completed without errors.
No local project tests, build, browser, dependency installation, provider request,
push, deployment, or implementer-worktree modification was performed. This
review artifact is an isolated documentation-only commit in
`.temp/site-mobile-table-css-review`.
