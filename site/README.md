# amail release site

Astro/TypeScript static product site for `https://amail.moesegfault.dev/`, deployed as Cloudflare Workers Static Assets. It is a release page and user guide, not the API reference. The authoritative CLI/ZIP contract is in `../docs/architecture.md` and must be kept aligned with `../crates/amail` before publication.

## Build and deploy

Use Node >=22.12 and pnpm with the checked-in lockfile:

```sh
pnpm install --frozen-lockfile
pnpm check
pnpm build
pnpm run deploy
```

The build-time `AMAIL_RELEASE_STATE` is typed and fail-closed: unset or `candidate`
renders honest pre-release copy; `published` renders the published links and status.
Only the release-gated production deploy jobs set `published`, after a non-draft
GitHub Release and expected assets exist. CI builds and checks both variants;
staging always uses the default candidate variant. Unknown values fail the build.

The build yields `dist/`; `wrangler.jsonc` deploys it as the `amail-release-site` Worker on the `amail.moesegfault.dev` custom domain. An isolated `staging` environment deploys `amail-release-site-staging` to `amail-staging.moesegfault.dev` with explicit route/asset settings; use `pnpm run deploy:staging`. CI owns deploy and live smoke checks. The expected routes are `/`, `/manual/`, and `/changelog/`. For production, use `pnpm run deploy` explicitly: pnpm 12.4.1 also has a built-in `deploy` command.

The source-managed static asset `_headers` rule matches **only** the staging hostname and sends `X-Robots-Tag: noindex, nofollow`. The shared `robots.txt` remains crawlable so search engines can actually see the noindex header; ordinary published production builds get no such header. CI should smoke-check the staging response header after deploy. See [Cloudflare Workers Static Assets headers](https://developers.cloudflare.com/workers/static-assets/headers/).

Before v0.1.0 publication, a separate reviewed, main-only manual
`Production candidate site` workflow can serve truthful candidate copy on the
production hostname without changing Mail/send/release gates. It adds
production noindex/nofollow and an opaque source revision **only to generated
candidate dist headers**, never to source `_headers`; a fresh published build
must not inherit them. Exact-source hosted CI, absence of a public v0.1.0 tag or
published Release, and three-route truthfulness/TOC/header smoke are mandatory.
Independent review
and a freeze of other site/tag writers are operator prerequisites. The read-only
token does not inventory internal untagged draft Releases. See
[the candidate lane contract](../docs/site-production-candidate-lane.md).

`node scripts/check-release-state.mjs candidate|published` checks each rendered
route's own release copy, links, navigation, and HTML indexability, plus the
staging-only `_headers` rule. `node --test scripts/check-release-state.test.mjs`
exercises missing status/link regressions without building or deploying. These
source checks do not establish live response headers or published asset bytes;
the deploy smoke and Release checksum gate remain necessary.

## Appending a release

Add **one** Markdown file named `src/content/releases/vX.Y.Z.md` with `version`, UTC `date`, and `summary` frontmatter. Keep the body reader-focused. The content collection validates versions and automatically sorts entries newest-first; its table of contents uses stable version anchors. Update the main-page download link and manual installation link when the latest public version changes. Do not publish a changelog claim ahead of release/smoke gates.

The v0.1.0 candidate copy does not claim a release exists. The production workflow
sets the published build state only after its release gate; verify real asset
downloads against `SHA256SUMS` during cutover. For later releases, update the
tagged links and versioned installation instructions together with the new
entry. The manual's five platform filenames must match the `release.yml` target
matrix; its checksum instructions use OS-native tools and fail before extraction.

## MoeSegfault Style integration

The site self-hosts unmodified, exact-version `v0.1.2` **public static distribution** files from [`kleedaisuki/moesegfault-style`](https://github.com/kleedaisuki/moesegfault-style) under `public/vendor/moesegfault-style/v0.1.2/`: `tokens.css`, `foundation.css`, `components.css`, and `assets/icons/brand.svg`. Their source paths are `static-releases/v0.1.2/` in that repository. Host-specific CSS uses the documented `--moe-*` semantic tokens; the product pages use the public `.moe-button` class. We self-host instead of depending on a remote stylesheet at page-load time. The upstream repository and these assets are GPL-3.0-or-later; retain attribution and version pin when updating. Do not edit the vendored files, and do not import upstream private `dist` paths.

## Design rationale

- Static rendering keeps the marketing site independent of the authenticated mail API.
- The manual TOC is derived from Markdown headings, so edits cannot leave stale links.
- Changelog entries are separate append-only files, avoiding a long manually maintained index.
- The public guide discloses the 10-address/account and current 198-user-address service capacity (two of the provider's 200 literal routes are reserved for `postmaster` and `abuse`), and the fact that semantic search sends text to the embedding provider.

Cloudflare deployment uses [Workers Static Assets](https://developers.cloudflare.com/workers/static-assets/routing/static-site-generation/) with a [Custom Domain](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/). Markdown heading behavior follows the [Astro Markdown guide](https://docs.astro.build/en/guides/markdown-content/).
