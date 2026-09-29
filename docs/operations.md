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
| `CF_EMAIL_ROUTING_TOKEN` | Dedicated zone-scoped Email Routing Rules Read+Write token for both environments' address rules and reconciliation; required, with no fallback |
| `INGRESS_SECRET` | One stable random secret shared by the Email-event adapter and Rust mail Worker; provision once, never regenerate per deployment |
| `INGRESS_SECRET_STAGING` | Different stable random secret for the two staging Workers; never copy the production value |

Do not fall back to an account-global key or a browser token. Verify the
production OIDC native client ID/redirect URI with Identity's owner; client registration is a
deployment-controlled operation, not dynamic registration.
The non-secret `CF_ZONE_ID` and `OIDC_CLIENT_ID` are checked into the Worker
Wrangler `vars` after review. `CF_ZONE_ID` also scopes the read-only DNS gate in
Actions; the gate never changes apex or mail records. Do not deploy until the
Identity client registration actually exists.

### Routing token rotation and expiry

One dedicated zone-scoped `CF_EMAIL_ROUTING_TOKEN` grants Email Routing Rules
Read+Write to both environments. Set its expiration deliberately and rotate
before expiry. A GitHub Secret update alone does **not** update already-deployed
Worker secrets: after updating the GitHub Secret, dispatch
`gh workflow run ci.yml --ref main -f target=staging`, verify staging, then
dispatch `gh workflow run ci.yml --ref main -f target=production`. The latter
is guarded to `main`, runs the normal CI/provider gates, redeploys only the
production mail and ingress Workers, and leaves the public release site alone.
Retire the old token only after both environments have passed Rules Read and a
disposable staging/production address add-and-delete test. Send a real message
to an already-active test address during the rotation to check the data plane.
Keep the token out of chat, logs, test artifacts, and source. On a bad rotation,
restore the prior still-valid token in the GitHub Secret and redeploy both
environments; if it has expired/revoked, issue another scoped token instead.

Cloudflare documents token TTL as an **API authorization** limit and routing
rules as separately configured zone objects. From that separation, an expired
token should not by itself delete existing enabled rules, so already-routed
addresses are *expected* to continue receiving; Cloudflare does not explicitly
guarantee this failure mode in those documents, and live delivery must be
verified. Registration, deletion, and cron rule reconciliation **will fail or
remain pending** while the token cannot authorize the Rules API; do not claim
zero impact. See [token TTL](https://developers.cloudflare.com/fundamentals/api/how-to/restrict-tokens/),
[routing-rule configuration](https://developers.cloudflare.com/email-service/configuration/email-routing-addresses/),
and [Rules API permissions](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/create/).

In staging [run 36426742153, attempt 2](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36426742153/attempts/2),
the newly configured secret passed the presence check but the Rules list
returned HTTP 403 before any D1 migration or Worker deployment. The diagnostic
probe now calls Cloudflare's [user-token](https://developers.cloudflare.com/api/resources/user/subresources/tokens/methods/verify/)
or [account-token](https://developers.cloudflare.com/api/resources/accounts/subresources/tokens/methods/verify/)
verification endpoint after a failed list request, logging only HTTP status,
bounded numeric Cloudflare error codes, and `active`/`disabled`/`expired`
state—not the token, token ID, rules, or provider response body. An active
token with Rules HTTP 403 points to a zone-resource or Email Routing Rules
permission mismatch; an unconfirmed verify result is **not** proof of an
invalid token. Cloudflare documents [Email Routing Rules Read/Write as zone
permissions](https://developers.cloudflare.com/fundamentals/api/reference/permissions/)
and the [Rules list endpoint](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/list/)
requires a `per_page` of at least 5. Re-provision the secret only after the
diagnostic identifies the fault; do not rerun an unchanged unauthorized token.
The next [diagnostic run 36429070159, attempt 2](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36429070159/attempts/2)
returned Rules HTTP 403, Cloudflare code 10000, and `account:active` from the
account-token verification endpoint. Thus the configured token is active, but
the Rules API still denies it. Cloudflare's [account-token compatibility
matrix](https://developers.cloudflare.com/fundamentals/api/get-started/account-owned-tokens/)
lists Email Relay but not Email Routing; the [account-token permission-group
schema](https://developers.cloudflare.com/api/resources/accounts/subresources/tokens/)
does allow zone-scoped permissions generally. These sources do **not** prove
whether this denial is an unsupported product/token combination or a missing
Rules/zone grant. The shortest supported route is a **user API token**, created
under User Profile > API Tokens (not Account API Tokens), with both zone-level
Email Routing Rules Read and Write and resource restricted to the single
`moesegfault.dev` zone. Replace only the GitHub Secret, never share its value,
then rerun failed staging jobs; do not widen the general deployment token.

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
The independent OpenRouter job passed in candidate
[run 36418072370](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36418072370)
on 2026-09-28; this establishes that the configured external model can return
the requested vector shape, not that mailbox semantic indexing has run.

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
The main branch push runs build/test gates only. Production promotion is a
separate reviewed `CI and deploy` manual dispatch with `target=production` on
`main`; this runs the same gates, deploys API/ingress/lifecycle Workers, and
deploys the public site only when the matching GitHub Release assets are
published. Before this workflow is merged to `main`, GitHub cannot manually
dispatch it or the new canary operator workflows; the candidate staging send
policy remains held unless a restricted D1 operator grant is explicitly used.
The staging CLI must explicitly use the staging issuer, client ID, and API base;
staging OIDC registration and live delivery remain separate acceptance steps.
The staging Astro launch page deploys independently to
`amail-staging.moesegfault.dev` after its own site build; this deliberately does
not depend on mail deployment or the routing token. Production site remains
gated on production mail and ingress deployment. Use `pnpm run deploy:staging`
and `pnpm run deploy`, not pnpm's built-in `pnpm deploy` command.
The staging site deployment succeeded in
[run 36419037567, job 108917364676](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36419037567/job/108917364676)
on 2026-09-28 (Worker version `81db8159-e051-4b9c-a40e-9741c528d747`).
The job's HTTPS smoke eventually passed after an initial DNS-resolution retry;
an independent probe returned HTTP 200 for `/`, `/manual/`, and `/changelog/`.
This proves the **staging launch site**, not the mail service or production
site, is reachable.
Staging assets use a host-scoped `X-Robots-Tag: noindex, nofollow` rule in
`site/public/_headers`; the CI smoke checks that staging HTML has `noindex`
while production HTML does not. This keeps the pre-release CTA out of search
results without changing the production `robots.txt` or sitemap.
The staging header assertion passed in
[run 36422475913, job 108928465373](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36422475913/job/108928465373)
after the `_headers` change; production header behavior remains untested until
the public-site launch job runs.

The production launch site intentionally does **not** deploy on the first
`main` push while its `v0.1.0` download CTA would be dead. Main's
`release-ready` job checks that the site's version has a published GitHub
Release with all five platform archives, the agent skill ZIP, and
`SHA256SUMS`; only then may the normal production site job deploy. The tag
release workflow publishes those assets first, downloads all seven published
files back from the GitHub Release into repository `.temp`, and verifies the
exact five native archives, skill ZIP, and six matching SHA-256 digests before
launching the public site. The public site cannot deploy if the download or
byte check fails. Live mail API health remains a separate launch check. The
manifest is not a cryptographic trust root by itself; tag ancestry and archive
attestations are separate provenance controls. This ordering preserves a
working download path without blocking earlier mail API/ingress deployment
and live acceptance.
The deployment token lacks Email Routing Rules Read (HTTP 403 in staging run
36416776818), so neither Worker is deployed with it as a routing-token fallback.
Missing dedicated routing secrets fail immediately before checkout or tool
installation, while the separate OpenRouter job can still establish provider
evidence.
The same dedicated zone-scoped `CF_EMAIL_ROUTING_TOKEN` is used by staging and
production because both mail domains share one Cloudflare zone. It is not an
account-global deployment token, but its control-plane scope still spans both
mail subdomains; isolation depends on the Workers' pinned `MAIL_DOMAIN`,
distinct ingress secret and storage bindings. The first real staging `amail address add`
is also the write-permission probe for Email Routing Rules; a read-only API
check cannot prove that the token has the required Write permission.
On the initial candidate branch only, the Windows CI matrix uploads the tested
`amail.exe` as a three-day `amail-windows-smoke-<commit>` artifact. Download it
under the repository `.temp/` directory for browser-login and real mailbox
acceptance; no local Rust build is required. This debug artifact is not a
release binary and must not be redistributed as one.
For example: `gh run download <RUN_ID> -n amail-windows-smoke-<COMMIT_SHA> -D .temp/smoke`.
On Windows, set **all** staging overrides before browser authorization so a
staging test cannot register a production address by accident:

```powershell
$env:AMAIL_HOME = Join-Path (Get-Location) '.temp/amail-staging'
$env:AMAIL_API_BASE = 'https://mail-staging.moesegfault.dev'
$env:AMAIL_ISSUER = 'https://identity-staging.moesegfault.dev'
$env:AMAIL_CLIENT_ID = 'amail-cli-staging'
& .\.temp\smoke\amail.exe config
& .\.temp\smoke\amail.exe auth login
```

The staging native client must already be registered in Identity. Keep the
staging home and draft ZIPs in `.temp/`; do not copy them into production CLI
state or commit them.

## Live acceptance checklist

### Candidate staging Rules Write/Delete probe (not executed)

After a replacement token passes the **read** gate and both staging mail/API
and `amail-inbound-staging` are deployed, prefer an authenticated staging
`amail address add` followed by `amail address delete` under a disposable test
account: that checks the actual address-ownership and routing transaction, not
just provider permissions. If browser authorization is not yet available, a
smaller operator-only control-plane probe may verify Write/Delete without
creating a user mailbox or sending SMTP:

1. Read **all pages** of zone routing rules (`per_page=50`) and filter literal
   recipient rules for `mail-staging.moesegfault.dev` only. Cloudflare's
   [200-rule limit is per domain](https://developers.cloudflare.com/email-service/platform/limits/),
   not per zone. Refuse to create if the staging domain already has 198 or
   more rules, preserving the two reserved slots; do not count production
   rules against staging. Confirm no rule already matches a new random
   `probe-<nonce>@mail-staging.moesegfault.dev` address.
2. POST one rule to the [Rules API](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/create/)
   with `enabled:false`, `source:"api"`, name
   `amail-control-probe-<nonce>` (deliberately unlike the Worker's
   `amail <address>` reconciliation name), one literal `to` matcher for that
   staging address, and one `worker` action targeting **only**
   `amail-inbound-staging`. Never create a production-domain rule or a
   catch-all. Confirm the returned ID and disabled state without printing
   the token, address, or provider response body.
3. In a `finally` cleanup, DELETE **only the returned ID** using the
   [delete endpoint](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/delete/),
   then list again to confirm absence. If POST timed out after creating a
   rule, locate the unique nonce/name and delete that exact disabled rule.
   If cleanup cannot be confirmed, stop acceptance and manually remove the
   orphan before proceeding. A cancelled job may bypass `finally`, so audit
   for the `amail-control-probe-` prefix on the next read.

This candidate procedure is **not** a deployed workflow step and must not be
executed before Rules Read succeeds. A passing provider probe would prove
only scoped rule creation/deletion; it would not validate Identity, D1
ownership/quota, inbound delivery, or the CLI's registration contract.

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
to `main`, wait for CI and production mail deployment, and perform live
acceptance. Before tagging, manually dispatch `Release amail CLI` on `main`
(`gh workflow run release.yml --ref main`). This uses GitHub-hosted runners to
test and build all five native targets, assembles the skill ZIP and six-entry
`SHA256SUMS`, verifies the checksums, and uploads
`release-bundle-v0.1.0` as a short-lived workflow artifact. It does **not**
create a GitHub Release, provenance attestations, or deploy the production
site. Inspect or download the artifact under `.temp/release-verify`; repair
any platform/packaging failure before freezing the tag. The final tag run
builds the exact tagged source again because its attestations must bind to
that immutable source identity, not to a prior dry-run commit.

For this first pre-merge candidate, the release workflow is not yet present
on `main`, so GitHub cannot accept a `workflow_dispatch` for it even with
`--ref codex/amail-v0.1.0` ([GitHub manual-workflow rule](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)).
A temporary exact-branch, release-workflow-file path trigger enabled the
first five-target dry-run without publishing or launching the site. That
bootstrap trigger was removed after its successful run, avoiding repeated
five-platform builds for later candidate edits. The verified bundle remains
available for 14 days; the later `main` dispatch can dry-run merged source.

The first candidate dry-run at commit `59c9b09` succeeded in
[run 36426742183](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36426742183):
all five hosted native platform tests/builds and assembly passed; attestation,
Release publication, and public-site launch were correctly skipped. Its
[`release-bundle-v0.1.0` artifact](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36426742183/artifacts/10971906268)
has five `amail-v0.1.0-<target>` archives for x86_64/aarch64 Linux,
x86_64/aarch64 macOS, and x86_64 Windows, plus
`amail-agent-skill-v0.1.0.zip` and `SHA256SUMS`. The bundle's six recorded
SHA-256 digests were independently recomputed after downloading into
`.temp/release-verify` and all matched. The skill ZIP contains
`amail/SKILL.md`, `amail/references/archive.md`, and
`amail/references/search-jobs.md`. The CLI source at this commit uses `include_str!`
for both local OAuth success/failure HTML pages; the released Windows binary
contains the updated success-page title. This validates packaging of the
candidate source, **not** a live browser login or mail delivery.

Then create and push a version tag matching `crates/amail/Cargo.toml`,
for example `v0.1.0`. The release workflow performs native builds on x64 and
ARM64 Linux, Windows x64, Apple Silicon, and Intel macOS, tests each binary
platform, first verifies the tag points to a commit merged into `main`, attests
the archives and agent skill ZIP, checks all six SHA-256
digests, and checks production outbound readiness **before** creating a GitHub
Release. The tag-only prepublish job requires production mail `/health` and a
read-only [D1 query](https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/)
against the exact production database: one global `send_policy` row in
`allowed` state plus the sole `send_release_gates` row with
`feedback_verified`, `abuse_contact_verified`, `delivery_canary_verified`,
and `preview_reviewed` all equal to 1. Missing schema, held policy, absent or
duplicate rows, failed API access, or unhealthy mail fails closed. It prints
only a sanitized readiness result, never D1 identifiers, token, user fields,
or response bodies. Candidate-branch and manual-main dry-runs skip this live
gate; an accidental early tag may still build archives, but cannot publish or
launch the public site while send remains held. Only after the gate passes
does the workflow create the GitHub Release and deploy the production site.
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
