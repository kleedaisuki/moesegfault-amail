# Release-site state review: `7e8b569`

Date: 2026-09-29. Scope: source review of the build-time candidate/published split, three page templates, `ci.yml` and `release.yml` gates. This review did not build, deploy, download a Release asset, or perform browser/visual acceptance. Existing unrelated working-tree changes were not touched.

## Verdict

The change resolves the earlier **stale copy at publication** blocker at the source/workflow level. The default and staging build select `candidate`; the tag workflow selects `published` only in `launch-site`, which needs successful `publish`, and `publish` needs the production send gate. A manual production `ci.yml` deploy selects `published` only after `release-ready` finds a non-draft Release with the seven expected asset names. The v0.1.0 homepage, manual page head, and changelog intro now render publication status from the same state, and candidate copy does not link to the unpublished v0.1.0 tag. No demonstrated production-launch blocker was found in this change.

The published homepage and manual page head link to the exact v0.1.0 GitHub Release page. The changelog links its one current entry to that same tag. The manual names the five platform archives, Skill ZIP, and `SHA256SUMS`; those names agree with `release.yml` assembly. These are **Release-page links**, not direct archive URLs, so release cutover still must follow the links and verify downloaded bytes against `SHA256SUMS` as the existing runbook requires.

## Follow-up findings

1. **P2, test gap: state checks are aggregate, not per-page.** `site/scripts/check-release-state.mjs` joins all three HTML pages before checking publication strings and the tag link. If a later edit drops the status paragraph from `ManualLayout.astro`, or the release link from one of the three pages, the other pages can satisfy every aggregate claim and the test still passes. The post-deploy smoke in both workflows checks status on the homepage only; it fetches manual/changelog but does not inspect their state or links. Current source is coherent, so this is not a current false claim. Make the static check assert each page's expected status and published destination independently, and inspect the rendered manual/changelog status after production deploy. Prefer checking concrete `href` values or parsed HTML over the loose `releases/tag/v0.1.0` substring.
2. **P2, cutover evidence gap: asset names are not downloaded-byte integrity.** `.github/workflows/ci.yml` `release-ready` checks a non-draft Release and asset names, while `release.yml` verifies checksums before artifact upload, then publishes the bundle and deploys the site. None of the site gates downloads the public assets and checks `SHA256SUMS` after publication. This is not evidence of corruption or a reason to block source merge; it is an unclosed launch acceptance check already identified in `docs/release-gap-audit.md`. A bounded post-publish check should download the six archives plus checksum file from the just-created Release, verify all six, and then verify the three site destinations and exact tag links. On failure, do not claim public launch acceptance.

## Boundaries and evidence

- The tag workflow's `preflight` requires a version-matching tag reachable from `origin/main`; `launch-site` depends on `publish`, rather than running on any tag independently. The `publish` job depends on `send-release-gate` and `assemble`.
- Staging deployment runs only for the named branch push or staging dispatch, and builds without `AMAIL_RELEASE_STATE`; `parseReleaseState` therefore selects `candidate`. A tag event does not enter `staging-site`.
- Manual `ci.yml` production site deployment requires `main`, successful mail deployment dependencies, site check, and `release-ready == true`. Its publication selector is scoped to the build step, not the staging job.
- `parseReleaseState` rejects unknown values; it is a copy-selection guard, **not** an authorization boundary. Someone with independent deployment rights can set an environment variable, so operational permissions remain the true protection against out-of-workflow publication.
- No claim is made about currently deployed assets, GitHub Release availability, or successful actual downloads. The preceding site acceptance review remains in `docs/site-release-acceptance-review.md`.
