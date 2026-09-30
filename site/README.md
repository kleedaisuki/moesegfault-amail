# amail candidate site

Standalone Astro/TypeScript static product candidate at
`https://amail.moesegfault.dev/`, served by Cloudflare Workers Static Assets.
Expected routes: `/`, `/manual/`, `/changelog/`, with heading-derived manual
navigation and stable version-based changelog navigation.

The site documents intended CLI workflows. **This checkout does not contain
the CLI, Mail/Identity backend, Agent Skill, release packaging, or published
deployment workflow.** Hosting a candidate does not release those artifacts,
launch Mail, or authorize public sending. Before a later release, reconcile the
guide with the independently reviewed CLI/ZIP contract and release matrix.

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
pre-release copy; `published` renders future public-release copy, **only for a
non-deploying compatibility test here**. Unknown values fail the build. No
workflow in this bootstrap deploys published state.

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

## Future release compatibility

Append one Markdown file under `src/content/releases/` per version. The collection
validates versions and orders entries newest-first. Release dates, claims, five
intended platform filenames, Agent Skill and checksums need separate release
review; candidate record dates are not public release dates. Do not set published
mode for production upload without that future gate.

## MoeSegfault Style integration

Exact-version v0.1.2 public static distribution from
[MoeSegfault Style](https://github.com/kleedaisuki/moesegfault-style) is vendored
unmodified under `public/vendor/moesegfault-style/v0.1.2/`, with provenance.
Self-hosted `css/tokens.css`, `css/foundation.css`, `css/components.css` and
`assets/icons/brand.svg` avoid runtime cross-site CSS dependencies. Preserve
GPL-3.0-or-later attribution/version pin; do not import private upstream paths.
Host CSS uses semantic `--moe-*` tokens and public `.moe-button` classes.

Static rendering needs no authenticated API or Worker request handler. The manual
discloses intended address limits, forwarding boundary, automatic third-party
semantic indexing and operational retention; the candidate service disclaimer
prevents these from asserting a live service.

References: [Workers Static Assets](https://developers.cloudflare.com/workers/static-assets/routing/static-site-generation/),
[Custom Domains](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/),
[Static Asset headers](https://developers.cloudflare.com/workers/static-assets/headers/),
[Astro Markdown](https://docs.astro.build/en/guides/markdown-content/).
