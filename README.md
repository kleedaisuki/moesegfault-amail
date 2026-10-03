# amail

**amail** is an agent-first mail CLI backed by a Rust Cloudflare Worker at
`mail.moesegfault.dev`. A moeSegFault account can manage up to ten
`@mail.moesegfault.dev` addresses. Authentication is delegated to
moeSegFault Identity; agents handle mailbox operations through the CLI.
Public sending is scoped to agent-workflow transactional notifications and
related replies, not campaigns or unrestricted person-to-person mail. New storage
starts held; production sending was explicitly enabled for v0.1.0.
Emergency holds and abuse operations remain in
[`docs/outbound-abuse-operations.md`](docs/outbound-abuse-operations.md).

Mail bodies and attachments cross the agent boundary as ZIP packages, not
unstructured CLI output. Search supports structured filters and server-side
semantic matching. The default CLI output is compact, pipe-friendly text;
`--human` opts into presentation for a person.

| Component | Location | Runtime |
| --- | --- | --- |
| CLI | `crates/amail` | Rust, Windows/macOS/Linux |
| Mail API and business logic | `crates/mail-worker` | Rust/Wasm on Cloudflare Workers |
| Email-event transport Worker | `workers/mail-ingress` | Rust/Wasm Worker forwarding bounded MIME into the Rust mail API |
| Sending lifecycle Worker | `workers/mail-events` | Rust/Wasm Queue consumer for delivery, bounce and complaint feedback |
| Public release site | `site` | Astro/TypeScript on Cloudflare Workers |

## Install

Download the published `v0.1.2` archive for your platform from
[GitHub Releases](https://github.com/kleedaisuki/moesegfault-amail/releases).
Check its digest against `SHA256SUMS` in the same release. Each CLI archive
contains the `amail` binary and license. Source builds use `cargo build -p amail
--release` from the repository root.

The public introduction, user manual, and append-only changelog are available at
<https://amail.moesegfault.dev/>. The CLI's `amail --help` and command help
remain the source of truth for the installed version.

Agent clients can use the checked-in [amail skill](skills/amail/SKILL.md),
also packaged as a ZIP in each GitHub Release. The skill is instructional; it
does not replace the CLI's own authentication or authorization checks.

## Repository development

Development builds and cross-platform tests run in GitHub Actions to avoid
requiring a local Rust/Wasm/Node toolchain or large caches on a contributor's
machine. `.github/workflows/ci.yml` tests the CLI on Linux, Windows, and macOS,
builds the Workers for Wasm, and checks the Astro site. Pushes are non-deploying
checks; `workflow_dispatch target=checks` repeats that source-only validation.
Isolated staging and reviewed production promotion are explicit manual targets;
privacy, artifact and graph confirmations remain required. The API is fetch-only;
a private scheduled maintenance Worker shares its business logic and storage. A main push alone does not
deploy production. `.github/workflows/release.yml` builds
five native CLI archives plus the agent skill from a version tag, and publishes
checksums and provenance attestations.

Deployment prerequisites, operational checks, and the release process are in
[`docs/operations.md`](docs/operations.md). Do not put account credentials or
mail content in the repository or GitHub Actions logs.

## Maintainer knowledge

| Need | Canonical document |
| --- | --- |
| Agent-first product priorities and task acceptance | [Product direction](docs/agent-first-product.md) |
| Wire/data/ZIP invariants | [Architecture](docs/architecture.md) |
| Deploy, recover and maintain | [Operations](docs/operations.md) |
| Delivered release evidence and limits | [Validation](docs/validation.md) |
| Sending policy and contact response | [Outbound](docs/outbound-abuse-operations.md), [contacts](docs/operator-intake.md) |
| Search/indexing internals | [Search jobs](docs/search-jobs.md), [indexer](docs/semantic-indexer-operations.md) |
| Credential/content privacy | [Auth storage](docs/auth-storage.md), [indexing privacy](docs/semantic-indexing-privacy-decision.md), [diagnostics](docs/runtime-observability-foundation.md) |

The public manual and installed command help own user workflows. Internal documents
cover durable contracts, not a second manual. Historical incident/review snapshots
are in Git history; do not grow a parallel audit knowledge base per task.

## License

See [LICENSE](LICENSE).
