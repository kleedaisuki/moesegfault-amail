# amail release site

Astro/TypeScript static product site for `https://amail.moesegfault.dev/`, deployed as Cloudflare Workers Static Assets. It is a release page and user guide, not the API reference. The authoritative CLI/ZIP contract is in `../docs/architecture.md` and must be kept aligned with `../crates/amail` before publication.

## Build and deploy

Use Node >=22.12 and pnpm with the checked-in lockfile:

```sh
pnpm install --frozen-lockfile
pnpm check
pnpm build
pnpm deploy
```

The build yields `dist/`; `wrangler.jsonc` deploys it as the `amail-release-site` Worker on the `amail.moesegfault.dev` custom domain. CI owns deploy and live smoke checks. The expected routes are `/`, `/manual/`, and `/changelog/`.

## Appending a release

Add **one** Markdown file named `src/content/releases/vX.Y.Z.md` with `version`, UTC `date`, and `summary` frontmatter. Keep the body reader-focused. The content collection validates versions and automatically sorts entries newest-first; its table of contents uses stable version anchors. Update the main-page download link and manual installation link when the latest public version changes. Do not publish a changelog claim ahead of release/smoke gates.

## MoeSegfault Style integration

The site self-hosts unmodified, exact-version `v0.1.2` **public static distribution** files from [`kleedaisuki/moesegfault-style`](https://github.com/kleedaisuki/moesegfault-style) under `public/vendor/moesegfault-style/v0.1.2/`: `tokens.css`, `foundation.css`, `components.css`, and `assets/icons/brand.svg`. Their source paths are `static-releases/v0.1.2/` in that repository. Host-specific CSS uses the documented `--moe-*` semantic tokens; the product pages use the public `.moe-button` class. We self-host instead of depending on a remote stylesheet at page-load time. The upstream repository and these assets are GPL-3.0-or-later; retain attribution and version pin when updating. Do not edit the vendored files, and do not import upstream private `dist` paths.

## Design rationale

- Static rendering keeps the marketing site independent of the authenticated mail API.
- The manual TOC is derived from Markdown headings, so edits cannot leave stale links.
- Changelog entries are separate append-only files, avoiding a long manually maintained index.
- The public guide discloses the 10-address/account and current 200-address service capacity, and the fact that semantic search sends text to the embedding provider.

Cloudflare deployment uses [Workers Static Assets](https://developers.cloudflare.com/workers/static-assets/routing/static-site-generation/) with a [Custom Domain](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/). Markdown heading behavior follows the [Astro Markdown guide](https://docs.astro.build/en/guides/markdown-content/).
