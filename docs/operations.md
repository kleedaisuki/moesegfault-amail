# amail deployment and release operations

This document records deployment contracts and recovery procedures. It is not
the public user manual.

## Production topology

| Service | Hostname | Source |
| --- | --- | --- |
| Mail HTTP API | `mail.moesegfault.dev` | `crates/mail-worker` |
| Public introduction/manual/changelog | `amail.moesegfault.dev` | `site` |
| Identity login UX | `login.moesegfault.dev` | Existing Identity product; not deployed here |
| OIDC issuer | Discovered and pinned separately from the login UX | Existing Identity product |

`moesegfault.dev` is not the public mailbox domain. Registered user addresses
end in `@mail.moesegfault.dev`; site mail is sent from
`mail@moesegfault.dev` only after that identity is authorized by the outbound
provider. An HTTP Worker route/custom domain and SMTP MX records are separate
DNS concerns. A successful HTTP health probe does **not** prove inbound or
outbound mail delivery. As of 2026-09-28, Cloudflare reports Email Routing and
Email Sending enabled for `mail.moesegfault.dev`, and Email Sending enabled for
the root `moesegfault.dev` sender domain. Authoritative DNS returned the
provider-required mail-subdomain bounce MX, SPF, DKIM, and DMARC records; the
CI read-only DNS gate rechecks them on each deployment. **Actual inbound and
outbound message delivery remains unverified until the live checklist below
passes.**

## Cloudflare resources and GitHub secrets

The Worker expects the D1 `MAIL_DB` binding, R2 `MAIL_BODIES` binding, Email
Routing ingress Worker (`workers/mail-ingress`), and outbound email binding specified by its Wrangler
configuration. Resource IDs belong in checked-in Wrangler configuration once
provisioned; credentials do not. Before the first deployment, create those
resources and ensure all Wrangler names agree. Production currently uses D1
`moesegfault-mail-production` (`ad06f7f3-8897-4150-b9a9-7a46a8e55b30`) and
R2 `moesegfault-mail-raw-production` in Cloudflare zone
`6edff81c6ed02f412e70868076411a5e`. Staging uses D1
`moesegfault-mail-staging` (`74f35f95-42ce-482c-86e6-dffbdd35cbbe`) and R2
`moesegfault-mail-raw-staging`; do not cross-bind staging and production.
Apply D1 migrations before
deploying a Worker that depends on them.

GitHub Actions requires these repository secrets:

| Secret | Purpose |
| --- | --- |
| `CLOUDFLARE_ACCOUNT_ID` | Wrangler account selection |
| `CLOUDFLARE_API_TOKEN` | Scoped Workers/D1/R2 deployment token |
| `OPENROUTER_API_KEY` | Worker-side embedding generation |
| `CF_EMAIL_ROUTING_TOKEN` | Zone-scoped Email Routing Rules Read+Write token for production address rules and reconciliation; required, with no fallback |
| `CF_EMAIL_ROUTING_TOKEN_STAGING` | Separate zone-scoped Email Routing Rules Read+Write token for staging; required, with no fallback |
| `INGRESS_SECRET` | One stable random secret shared by the Email-event adapter and Rust mail Worker; provision once, never regenerate per deployment |
| `INGRESS_SECRET_STAGING` | Different stable random secret for the two staging Workers; never copy the production value |

Do not fall back to an account-global key or a browser token. Verify the
production OIDC native client ID/redirect URI with Identity's owner; client registration is a
deployment-controlled operation, not dynamic registration.
The non-secret `CF_ZONE_ID` and `OIDC_CLIENT_ID` are checked into the Worker
Wrangler `vars` after review. `CF_ZONE_ID` also scopes the read-only DNS gate in
Actions; the gate never changes apex or mail records. Do not deploy until the
Identity client registration actually exists.

The deployment workflow uses GitHub-hosted runners, builds Rust/Wasm, applies
remote D1 migrations, deploys the mail Worker atomically with its secrets, then
deploys the email-event ingress adapter and Astro site. It probes `/health`, `/`, `/manual/`, and
`/changelog/`. Before deployment, it also compares live provider-required MX,
SPF, DKIM, and DMARC records against authoritative DNS and calls OpenRouter
with synthetic text to require one finite 256-dimensional
`qwen/qwen3-embedding-8b` vector under the Worker's zero-data-retention and
data-collection-denied routing preferences. The live embedding probe runs as an
independent hosted CI job, so missing routing credentials cannot hide provider
incompatibility. It also checks the runtime Routing
token can list rules for cron reconciliation without logging any address; this
does **not** prove Write permission. These are provider/availability probes, not
an end-to-end delivery test.

The first candidate branch `codex/amail-v0.1.0` triggers a staging deployment
on push after all CI gates because GitHub manual-dispatch workflows must first
exist on the default branch. Remove this one-time branch trigger after the
first successful staging run and merge. This branch's duplicate PR matrix is
skipped while the same commit is checked by the push matrix; remove that
one-time skip together with the branch trigger. After the workflow exists on the default branch,
later candidate branches can manually dispatch `CI and deploy` with
`target=staging`. The workflow runs the same cross-platform and Wasm checks,
then verifies an explicit isolation contract (`infra/deploy/check_staging.py`),
checks `mail-staging.moesegfault.dev` sending DNS, probes OpenRouter, migrates
only staging D1, deploys the mail and ingress Workers with `--env staging`, and
checks staging `/health`. It does **not** deploy production or the public site.
The staging CLI must explicitly use the staging issuer, client ID, and API base;
staging OIDC registration and live delivery remain separate acceptance steps.
The deployment token lacks Email Routing Rules Read (HTTP 403 in staging run
36416776818), so neither Worker is deployed with it as a routing-token fallback.
Staging and production routing tokens should be separate, although both mail
domains share a Cloudflare zone and zone-scoped tokens still have
cross-environment control-plane privilege. The first real staging `amail address add`
is also the write-permission probe for Email Routing Rules; a read-only API
check cannot prove that the token has the required Write permission.
On the initial candidate branch only, the Windows CI matrix uploads the tested
`amail.exe` as a three-day `amail-windows-smoke-<commit>` artifact. Download it
under the repository `.temp/` directory for browser-login and real mailbox
acceptance; no local Rust build is required. This debug artifact is not a
release binary and must not be redistributed as one.
For example: `gh run download <RUN_ID> -n amail-windows-smoke-<COMMIT_SHA> -D .temp/smoke`.

## Live acceptance checklist

Perform these checks against **deployed** services after the first successful
Actions deployment or an SMTP/DNS change. Use a dedicated test account and
recipient; do not put tokens, message bodies, or address ownership details in
CI logs.

1. Confirm HTTP health and public site pages load at their production URLs.
2. Complete native `amail login` against the registered Identity client.
3. Register a disposable `@mail.moesegfault.dev` address via `amail` and verify
   the address routes to the ingress Worker. Ensure reserved names and the
   eleven-address attempt are denied without creating routing rules.
4. Send a real external message to the new address. Use `amail` to query and
   fetch it, unpack its ZIP, and verify text/HTML and attachments. Query by
   metadata, date, content, and semantic similarity; verify read/unread state.
5. Package a reply with `amail`, send it to an external mailbox, and check
   sender identity, delivered MIME/HTML, attachment integrity, and reply
   threading. Check SPF/DKIM/DMARC alignment and bounces in Cloudflare/provider
   diagnostics. Separately verify site-originated mail uses
   `mail@moesegfault.dev` rather than a user mailbox address.
6. Delete the disposable message and address; verify the routing rule is
   removed and data is not returned by subsequent queries.
7. Correlate a CLI diagnostic trace ID with Worker traces while verifying that
   local SQLite telemetry and Worker logs contain no token, message body,
   attachment, or raw private search query.

If a smoke step fails, preserve only sanitized trace IDs, status codes, and
timestamps in the incident record. Re-run affected checks after the fix;
unrelated passing checks need not be repeated.

## Release v0.1.0 and later

Update the CLI version and append a dated changelog entry in the site. Merge
to `main`, wait for CI and production deployment, and perform live acceptance.
Then create and push a version tag matching `crates/amail/Cargo.toml`,
for example `v0.1.0`. The release workflow performs native builds on x64 and
ARM64 Linux, Windows x64, Apple Silicon, and Intel macOS, tests each binary
platform, first verifies the tag points to a commit merged into `main`, attests
the archives and agent skill ZIP, checks all six SHA-256
digests, and creates a GitHub Release.
The workflow intentionally fails rather than silently replacing an existing
release asset. Investigate a failed release run before publishing any tag
replacement.

## Sources informing these operations

- [Cloudflare GitHub Actions deployment](https://developers.cloudflare.com/workers/ci-cd/external-cicd/github-actions/)
- [Cloudflare D1 migrations](https://developers.cloudflare.com/d1/wrangler-commands/)
- [Cloudflare Worker custom domains](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/)
- [Cloudflare Rust Workers](https://developers.cloudflare.com/workers/languages/rust/)
- [GitHub artifact attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)
- [GitHub manual workflow dispatch on default branch](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
- [OpenRouter embeddings request contract](https://openrouter.ai/docs/api/api-reference/embeddings/create-embeddings)
- [Cloudflare Email Sending generated DNS records](https://developers.cloudflare.com/api/resources/email_sending/subresources/subdomains/subresources/dns/methods/get/)
- [Cloudflare Email Routing Rules Write requirement](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/create/)
