# Independent human-style site screenshot review

Date: 2026-10-01. Reviewer: delegated product/visual reviewer
`/root/site_visual_human_review`. Scope: public candidate pages only.

## Evidence identity and verdict

- Hosted run: <https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36809632215>,
  attempt 1; artifact `site-browser-36809632215-1`.
- `report.json` records source `4a76064a9db414033c0eb336474a29cf516261b4`,
  target **source-preview**, base `http://127.0.0.1:4321`, and no deployed revision.
  Recorded capture interval: 2026-10-01 03:15:49.646–03:16:15.993 UTC.
- The downloaded report records 76 successful named checks across 12 cases.
  This reviewer did not independently query workflow completion metadata or
  rerun those checks; automated success is not the human visual verdict.
- **No P0/P1 visual defect found. One P2 mobile table-discoverability issue
  remains.** The principal candidate-page journey is visually coherent, but
  do not describe narrow-screen manual comprehension as unqualified acceptance.
  A small affordance/readability follow-up is preferable to a site redesign.

This is hosted **preview artifact** review, not inspection of the live domain,
deployment acceptance, screen-reader certification, release publication,
native installation, provider-request verification or Mail readiness.

## Material actionable finding

**P2 — narrow manual tables conceal consequential second-column information
without a visible scrolling cue.** In `320-manual-table-1.png`, only the device
column is visible: neither the package-column heading nor any archive name
appears. In `320-manual-table-2.png`, only quota scopes appear; the limit-column
heading and every numeric limit are offscreen. These tables look complete at
their right edge, with no visible scrollbar, direction cue or explanatory
text. A reader must already know to try horizontal scrolling to discover the
information required to choose an archive or understand sending limits.
`390-manual-table-1.png` and `390-manual-table-2.png` expose small clipped parts
of the second column, providing some evidence of continuation but still not a
complete filename or several complete limits. `320-manual-table-0.png` and
`390-manual-table-0.png` similarly truncate Agent responsibilities.

The report's table-reachability assertions pass. Therefore this is **not** a
claim of irretrievable data or page-wide horizontal overflow; it is a human
discoverability problem left outside those automated assertions. Screenshots
cannot prove actual touch/keyboard scrolling comfort.

Smallest complete product requirement: at 320 and 390 px, a first-time reader
must either see each device-to-package and scope-to-limit association through
wrapping/reflow, or receive a visible instruction/affordance identifying the
table's horizontal continuation. Do not shrink table text or alter filenames,
quota semantics, release status or existing heading destinations. If scrolling
is retained, independently inspect an initial and rightmost screenshot and
confirm that reaching the right column does not leave the surrounding prose
displaced for continued reading. Implementation choice belongs to the site
owner, not this review.

## Inspected visual evidence

Every `{320,390,768,1440}-{home,manual,changelog}-{viewport,full}.png` pair was
viewed. Full manual captures are very tall and were used for layout/content
ordering overview, not an assertion that every small glyph was readable in the
scaled overview. All 12 `{width}-manual-table-{0,1,2}.png` captures were inspected
at practical reading scale. Original-scale crops of the lower privacy section
from `*-manual-full.png` were inspected in repository-local ignored
`.temp/screenshot-crops/`; these are inspection derivatives, not fresh browser
evidence.

| Aspect | Observed result and representative filenames |
| --- | --- |
| Hierarchy and brand | Warm cream/coral/dark-brown palette, amail mark, navigation, section headings and footer remain consistent across all routes and widths. Main headings, body text and action labels remain legible without clipped functional controls: `320-home-viewport.png`, `390-manual-viewport.png`, `768-changelog-viewport.png`, `1440-home-full.png`. Narrow home illustration cropping is decorative; it does not hide a CTA or change the explained workflow. |
| Truthful candidate journey | Home actions say candidate design / preview installation; visible text says v0.1.0 and Skill downloads are unavailable and Mail/sending is not opened. Manual and changelog repeat the candidate/service boundary before their content. The changelog date is visibly labeled candidate-record date, not release date: `1440-home-viewport.png`, `320-manual-viewport.png`, `390-changelog-viewport.png`. No misleading download CTA was observed. |
| Privacy prominence | Home disclosure precedes both primary actions at every width and explicitly says indexing happens even without semantic search. Manual introduction discloses OpenRouter/upstream processing and no per-account opt-out before installation/address instructions: `320-home-viewport.png`, `390-home-viewport.png`, `768-manual-table-0.png`, `1440-manual-table-0.png`. The lower privacy section remains visibly structured and readable in original-scale full-image crops; its provider/retention claims were not independently verified here. |
| Contents navigation | Desktop presents a separate manual/changelog contents rail; narrow widths move it above the body. Indentation and wrapped entries remain readable: `320-manual-viewport.png`, `390-manual-viewport.png`, `768-manual-viewport.png`, `1440-changelog-full.png`. Actual destination/heading behavior is report evidence, not inferred from static screenshots. |
| Focus appearance | `320-home-skip-focus.png` and `320-manual-skip-focus.png` show a prominent dark skip control; `320-home-main-continuation-focus.png` and `320-manual-main-continuation-focus.png` visibly mark the privacy/contents continuation. `1440-changelog-main-continuation-focus.png` shows the focused contents location. This is a bounded appearance check, not a full independent keyboard traversal. |
| Wider tables | At 768 and 1440 px, responsibilities, device/package mapping and scope/limit mapping are readable and visually separated: `768-manual-table-0.png`, `768-manual-table-1.png`, `768-manual-table-2.png`, and their `1440-` equivalents. Narrow tables are the P2 finding above. |

## Boundaries and performed work

Recovered existing product/release/browser acceptance documents by filename,
read the downloaded report, viewed public-page screenshots, generated local
inspection-only crops, and wrote this documentation in isolated worktree
`.temp/site-visual-human-review`. No local project test, build or browser was
run; no dependency was installed. No private mail, session, provider call,
production source edit, push, deployment, DNS, tag or Release operation occurred.
Other browser engines, real touch use, screen-reader announcements, 200% zoom,
dark mode and contrast compliance remain unverified, as already bounded by
`site-browser-acceptance.md`.
