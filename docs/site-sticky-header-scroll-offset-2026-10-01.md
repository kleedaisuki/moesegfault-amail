# Sticky-header fragment scrolling

## Observed defect

Hosted browser workflow run [36808670970, attempt 1](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36808670970)
tested source `d996547c92f1e2ecffcad986fb5e6c12466054da` in a hosted source
preview, not the deployed production site. The unchanged TOC visibility assertion
found the first manual heading obscured at every required width, and the first
changelog heading obscured at the three narrower widths.

| Viewport width | Sticky header bottom | Manual first heading top | Changelog first heading top |
| --- | --- | --- | --- |
| 320 | 125.188 px | 0.703 px | 110.203 px |
| 390 | 125.188 px | 0.344 px | 110.203 px |
| 768 | 128.891 px | 0.547 px | 110.672 px |
| 1440 | 77 px | 0.844 px | Passed original assertion; coordinate not recorded |

These are validator-reported measurements from the run's `site-browser-evidence/report.json`.
The original source applies fixed heading scroll margins of 105 px (prose) and
110 px (changelog). Both underestimate the wrapped mobile header. The manual's
`overflow-x: auto` also makes its computed vertical overflow `auto`, creating a
nested scroll container under the CSS Overflow rules. The manual's near-zero
heading positions are consistent with the heading scroll margin being limited
at that inner container's beginning; hosted ancestor diagnostics are required
to verify that explanation rather than treating it as directly measured fact.

## Source correction

Apply the exclusion area to the viewport using `html { scroll-padding-top: ... }`,
and remove the heading-specific scroll margins. This describes the actual
obstruction where it exists, instead of adding an exception for the first manual
heading or removing the article's horizontal scrolling. The gap below the header
is 24 px for all fragment destinations. Existing heading IDs, TOC generation,
table overflow, header layout, reduced-motion rules and release contracts remain
unchanged. The desktop sticky TOC retains its original 108 px top position.

`--site-header-height` follows existing responsive header geometry:

- Desktop: 76 px inner minimum height plus 1 px bottom border = 77 px.
- At widths <= 850 px: 30 px outer vertical padding, first-row height (the larger
  of the 31 px brand and the CTA), 14 px row gap, navigation line height plus
  16 px vertical padding, and 1 px bottom border.
- CTA height uses shared font-size, vertical-padding and line-height variables,
  plus its two 1 px borders. The <= 580 px breakpoint updates those same CTA
  variables, not a separate hard-coded anchor offset.
- The resulting wrapped-header heights are 128.9 px and 125.2 px respectively,
  matching the hosted measurements within subpixel rounding.

Maintain the header-height expression when changing navigation font size,
navigation padding, row gap, outer padding or border widths. Header line-height
is explicitly set to the existing foundation value of 1.7 so the formula does
not depend on an unrelated future body typography change.

Standards rationale: [CSS Scroll Snap, scroll-padding](https://www.w3.org/TR/css-scroll-snap-1/#scroll-padding)
applies the root element's padding to the viewport and supports scroll-into-view
operations without enabling snapping; [CSS Overflow, overflow properties](https://www.w3.org/TR/css-overflow-3/#overflow-properties)
defines the cross-axis `visible` to `auto` computation used by prose here.

## Verification boundary and skip link

This assignment performs static source/diff checks only: no local build, test,
browser, deploy or push. An independent hosted run must retain the original TOC
visibility assertion and verify every route/width against the corrected source;
source reasoning is not browser acceptance. Validate arbitrary existing heading
links and narrow-screen table scrolling as well as the first heading.

Skip-link source analysis found an offscreen absolute link, a focused top
position, z-index above the header and a visible focus outline. The validator's
original failure occurred on Tab after Enter, not initial skip-link focus; its
focus screenshot shows a clear outline. Do not change skip-link CSS on that
evidence alone. Hosted active-element and focus-continuation diagnostics own
the distinction between a production focus defect and an assertion mismatch.
