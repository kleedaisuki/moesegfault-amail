# amail

**amail** is an agent-first mail CLI backed by a Rust Cloudflare Worker at
`mail.moesegfault.dev`. A moeSegFault account can manage up to ten
`@mail.moesegfault.dev` addresses. Authentication is delegated to
moeSegFault Identity; agents handle mailbox operations through the CLI.

Mail bodies and attachments cross the agent boundary as ZIP packages, not
unstructured CLI output. Search supports structured filters and server-side
semantic matching. The default CLI output is compact, pipe-friendly text;
`--human` opts into presentation for a person.

| Component | Location | Runtime |
| --- | --- | --- |
| CLI | `crates/amail` | Rust, Windows/macOS/Linux |
| Mail API and business logic | `crates/mail-worker` | Rust/Wasm on Cloudflare Workers |
| Email-event transport Worker | `workers/mail-ingress` | Rust/Wasm Worker forwarding bounded MIME into the Rust mail API |
| Public release site | `site` | Astro/TypeScript on Cloudflare Workers |

## Install

After `v0.1.0` is published, download the archive for your platform from
[GitHub Releases](https://github.com/kleedaisuki/moesegfault-amail/releases).
Check its digest against `SHA256SUMS` in the same release. Each CLI archive
contains the `amail` binary and license. Source builds use `cargo build -p amail
--release` from the repository root.

The public introduction, user manual, and append-only changelog are designed
for <https://amail.moesegfault.dev/>. The CLI's `amail --help` and command help
remain the source of truth for the installed version.

Agent clients can use the checked-in [amail skill](skills/amail/SKILL.md),
also packaged as a ZIP in each GitHub Release. The skill is instructional; it
does not replace the CLI's own authentication or authorization checks.

## Repository development

Development builds and cross-platform tests run in GitHub Actions to avoid
requiring a local Rust/Wasm/Node toolchain or large caches on a contributor's
machine. `.github/workflows/ci.yml` tests the CLI on Linux, Windows, and macOS,
builds the Worker for Wasm, checks the Astro site, deploys both Workers from
`main`, and probes their public routes. `.github/workflows/release.yml` builds
five native CLI archives plus the agent skill from a version tag, and publishes
checksums and provenance attestations.

Deployment prerequisites, operational checks, and the release process are in
[`docs/operations.md`](docs/operations.md). Do not put account credentials or
mail content in the repository or GitHub Actions logs.

## License

See [LICENSE](LICENSE).
