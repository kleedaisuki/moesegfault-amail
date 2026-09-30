# Release-site route-local state review: `3c0eeed`

Date: 2026-09-30. Scope: the commit's script, tests and README, current page templates, and both production deploy smoke steps. I ran only `node --test site/scripts/check-release-state.test.mjs` (16/16 pass) and one minimal checker reproduction; I did not build, deploy, or inspect live routes or Release bytes. Unrelated working-tree changes were not touched.

## Verdict

The commit closes the **pre-deploy route-local copy gap** identified in `site-release-acceptance-review.md`: each rendered page must now carry its own state string and, in published mode, its own exact v0.1.0 Release destination. Candidate mode rejects that version-specific destination. It also checks the source `_headers` staging-only rule and rejects any rendered HTML containing `noindex`. The current page templates match these assertions. This is a useful source gate, not a deployed-site acceptance pass.

## Findings

1. **P2 — The companion post-deploy gap remains open.** `.github/workflows/release.yml` `launch-site` and `.github/workflows/ci.yml` `deploy-site` still fetch `/manual/` and `/changelog/` only for HTTP success. They inspect publication copy and `X-Robots-Tag` only on `/`, and do not check any live route's exact v0.1.0 Release link. A stale manual/changelog response can therefore pass both the new pre-deploy check (which reads local `dist`) and the live smoke (which checks only 200), leaving visitors with candidate wording or dead/wrong links. Fetch each deployed page once and check its page-specific published status, exact tag `href`, absence of candidate status, and production `noindex` header; retain the separate staging hostname header assertion. This is a required acceptance correction, not evidence that the current deployed site is wrong.

2. **P2 — `hasHref` can certify a non-navigable link.** In `site/scripts/check-release-state.mjs`, `/<a\b[^>]*\bhref="([^"]*)"[^>]*>/g` matches the `href` suffix of `data-href` (and similarly `aria-href`). I passed published fixtures for all three routes with only `<a data-href="https://github.com/kleedaisuki/moesegfault-amail/releases/tag/v0.1.0">` and no actual tag `href`; `checkReleaseState('published', ...)` returned successfully (`FALSE_PASS`). The tests cover a wrong real `href` but not a missing real `href` accompanied by a lookalike attribute. Parse HTML attributes or at least require an attribute boundary that excludes `-` before `href`, then add this negative fixture. The same helper protects navigation links and candidate generic Releases links, so the failure is not confined to the tag check.

The whole-document `/noindex/i` is deliberately stricter than an HTML robots-directive check: harmless future prose or an HTML comment mentioning the word would fail. This is a conditional false positive, not a present defect; if such copy becomes necessary, target actual robots metadata instead of weakening the staging response-header contract.

## Unverified boundary

The static checker cannot establish live response headers, route freshness, redirect destinations, or published asset integrity. The existing checksum and deployment gates remain distinct. The old changelog date/cutover evidence item in `site-release-acceptance-review.md` was not changed by this commit and is not re-reviewed here.
