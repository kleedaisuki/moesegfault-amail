# amail release site

Standalone Astro/TypeScript static release site at
`https://amail.moesegfault.dev/`, served by Cloudflare Workers Static Assets.
Expected routes: `/`, `/manual/`, `/changelog/`, with heading-derived manual
navigation and stable version-based changelog navigation.

The repository contains the CLI, Mail backend, versioned Agent Skill and release
pipeline. The site itself remains a static public guide, not a web inbox.
Hosting its candidate mode does not publish the CLI or authorize public sending.
The current release coordinates are v0.1.2. Production published builds require
an actual nondraft Release and all seven assets; source/candidate builds do not
assert publication. Historical v0.1.0 records remain in the changelog.

## Hosted checks and guarded deployment

Tests/builds for this workstream run in GitHub Actions, not on the developer
machine. `.github/workflows/site-ci.yml` (Candidate site CI) has one successful
job identity, `Astro candidate site source checks`, used by the deployment gate.
It runs digest-pinned actionlint on both site workflows, synthetic regressions,
locked pnpm install, Astro checks and both
candidate/published-state build fixtures. It never deploys or receives provider
credentials. Node 22 and pnpm 12.4.1 are pinned by workflow; site package versions
and lockfile remain those imported from reviewed source.

`AMAIL_RELEASE_STATE` is typed and fail-closed: unset or `candidate` renders
pre-release copy; `published` renders public-release copy and the seven exact
v0.1.2 Release downloads. Both build states retain the current and historical
changelog entries; candidate headers and global copy remain state-specific. Unknown values fail the build. Source checks exercise both
states without deploying. The tag release workflow deploys published state only
after the existing production gate, Release publication and published-byte check.

`Production candidate site` is manual-only, defaults to checks, reuses same-commit
source workflow without inheriting provider secrets, and can deploy only from
main after default-branch registration, independent review, exact-source site
CI, explicit confirmation and an external site/tag/Release publication freeze.
Its GitHub gate rejects public v0.1.0 tags and published Releases; read-only token
visibility is not inventory of internal untagged drafts. See [operator contract](../docs/site-production-candidate-lane.md).

The build yields `dist/`; Wrangler config targets `amail-release-site` and its
production Custom Domain. Staging config remains isolated as imported, but
**this bootstrap adds no staging deployment workflow**. Only the guarded
candidate workflow uses `pnpm run deploy`; explicit script invocation avoids
pnpm's distinct built-in `deploy` command. Do not bypass review/gates with raw
deploy commands. First Custom Domain deployment may provision DNS/certificates;
do not add placeholders.

Source `public/_headers` targets staging only. Candidate preparation modifies
only generated `dist/_headers`, adding production-host-only noindex/nofollow
and exact source revision. Crawlable robots.txt lets crawlers see the header.
A fresh published compatibility build restores headers byte-identical to source.
Candidate live smoke validates exact routes, local status, service-availability
disclaimer, real links, working TOCs, MIME and HTTP/source/indexing headers.
Green build checks are not live acceptance.

## Publication and release compatibility

`.github/workflows/release.yml` is the actual publication path. A manual main run
only prepares candidate bundles. After authorized production acceptance and all
genuine send attestations, a `v0.1.2` tag on the final accepted main source starts
five platform builds/tests, the Skill bundle and checksums. The existing production
gate must pass before GitHub Release creation. Its published assets are then
downloaded and compared with the same-run trusted checksum manifest before the
site is built with `AMAIL_RELEASE_STATE=published` and deployed. The public smoke
checks home/manual/changelog state and indexing. This does not run merely by
setting the build variable locally or copying candidate artifacts into a Release.

The published manual provides direct links for five native archives, Agent Skill
and `SHA256SUMS`, all at the same version. Candidate pages expose no versioned
downloads. Both CLI and Skill installation require matching checksums. The
changelog's stored date is a version record date; the linked GitHub Release
provides the actual publication timestamp. Do not guess a future release date.

Append one Markdown file under `src/content/releases/` per version. The collection
validates versions and orders entries newest-first. Release dates, claims, five
platform filenames, Agent Skill and checksums must match that version's public
assets; record dates are not publication dates. Do not bypass the release workflow
by setting published mode in the candidate deployment lane.

## MoeSegfault Style integration

Exact-version v0.1.2 public static distribution from
[MoeSegfault Style](https://github.com/kleedaisuki/moesegfault-style) is vendored
unmodified under `public/vendor/moesegfault-style/v0.1.2/`, with provenance.
Self-hosted `css/tokens.css`, `css/foundation.css`, `css/components.css` and
`assets/icons/brand.svg` avoid runtime cross-site CSS dependencies. Preserve
GPL-3.0-or-later attribution/version pin; do not import private upstream paths.
Host CSS uses semantic `--moe-*` tokens and public `.moe-button` classes.

The base layout always loads tokens and foundation; pages opt into component CSS
with `<BaseLayout components ...>` only when they use public components. Today
only the homepage uses `.moe-button`. Manual/changelog keep their existing host
styles without loading the unused 58,817-byte component library. Keep upstream
vendored bytes unchanged; do not introduce selector-purging or asynchronous CSS
that risks changing the cascade, first paint or keyboard behavior.

## Small hosted performance check

After each existing candidate/published Astro build, run:

```sh
node --test scripts/measure-performance.test.mjs
node scripts/measure-performance.mjs > ../.temp/site-performance.json
```

Create the root `.temp` directory before redirecting. The dependency-free report
records route HTML bytes, inline CSS bytes, linked CSS requests/raw/gzip bytes,
and script counts from the actual `dist` output. It also fails if component CSS
leaks back onto the guide routes or a client runtime is introduced. Existing
browser acceptance checks the same loading contract in the actual browser,
alongside its navigation, focus, overflow, mobile and fragment checks.

This is a deterministic loading-cost check, not a claim about Core Web Vitals.
Gzip is an estimate using Node defaults, not the server's observed encoding.
Do not introduce fragile hosted wall-clock budgets or rebuild a baseline on every
run. Compare JSON reports from admitted builds if future loading changes warrant
it; measure paint latency only when an actual rendering regression needs diagnosis.

Static rendering needs no authenticated API or Worker request handler. The manual
discloses intended address limits, forwarding boundary, automatic third-party
semantic indexing and operational retention; the candidate service disclaimer
prevents these from asserting a live service.

References: [Workers Static Assets](https://developers.cloudflare.com/workers/static-assets/routing/static-site-generation/),
[Custom Domains](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/),
[Static Asset headers](https://developers.cloudflare.com/workers/static-assets/headers/),
[Astro Markdown](https://docs.astro.build/en/guides/markdown-content/).

## Published browser acceptance

The hosted `Site browser acceptance` workflow supports `live-published`, alongside
source preview and existing live candidate/staging targets. Set `candidate_revision`
to the exact deployed source SHA (the input is shared by all live modes). This is
read-only verification, not deployment or publication. The published target first
requires the nondraft, nonprerelease GitHub v0.1.2 Release with all seven exact
nonempty assets, then checks published status and Release links on all three
routes, seven downloads on the manual, absence of candidate/noindex output, and
`X-Amail-Release-Revision` matching that deployed SHA. All modes retain the same
12 route/viewport geometry, focus, fragment, loading and screenshot checks.
