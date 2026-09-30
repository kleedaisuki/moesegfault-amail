# Production DNS and cutover read-only audit — 2026-09-29

## Scope and method

This is a point-in-time, non-mutating audit at **2026-09-29 13:32 UTC** from the Windows development host. It reuses the architecture and DNS procedure in `docs/deployment-dns.md`, the acceptance ledger in `docs/validation.md`, the authoritative sending verifier in `infra/dns/verify_sending.py`, and the checked-in production/staging Wrangler and Actions configurations. `Resolve-DnsName` queried both delegated Cloudflare authoritative nameservers (`jermaine` and `raquel`) plus Google Public DNS `8.8.8.8`; `Invoke-WebRequest` performed HTTPS GETs with redirects disabled. No API token, routing destination, message, deployment, DNS record, or other provider state was changed or printed. A DNS answer is not a provider configuration audit.

## Observed state

| Host / record | Read-only observation | Consequence |
| --- | --- | --- |
| `mail.moesegfault.dev` MX | On `jermaine`: three Cloudflare routing MX records, priorities 39/49/94, pointing to route1/2/3.mx.cloudflare.net. | Inbound DNS exists, but a particular recipient requires a literal enabled routing rule and Worker path. |
| `mail.moesegfault.dev` TXT | SPF `v=spf1 include:_spf.mx.cloudflare.net ~all`. | DNS record presence only. |
| `_dmarc.mail.moesegfault.dev` TXT | `v=DMARC1; p=reject;`. | Preserve alignment and policy. |
| `cf-bounce.mail.moesegfault.dev` MX/TXT and `cf-bounce._domainkey.mail.moesegfault.dev` TXT | Bounce MX x3, Cloudflare SPF, and DKIM TXT present on `jermaine`; DKIM key deliberately omitted. | Sending DNS appears provisioned; actual delivery/authentication still needs acceptance. |
| `mail.moesegfault.dev` A/AAAA/CNAME | No address or CNAME answers on both authoritative nameservers and `8.8.8.8`; HTTPS `/health` failed with an HTTP client transport error. | Production API Custom Domain is **not live**. This is expected before the guarded production deploy, not evidence of a broken deployed Worker. |
| `amail.moesegfault.dev` A/AAAA/CNAME | Queries on both authoritative nameservers and `8.8.8.8` failed as nonexistent; HTTPS `/` failed with an HTTP client transport error. | Public release site is **not live**. Its release-tag workflow has not launched it. |
| `login.moesegfault.dev` | A/AAAA answers and HTTPS `/` 200, `text/html`. | The public login page is reachable; no login flow was exercised here. |
| `identity.moesegfault.dev` | A/AAAA answers; OIDC discovery GET 200, `application/json`. | Discovery endpoint reachable; no token/client flow was exercised here. |

The DNS/HTTPS results agree with the existing deployment topology: `crates/mail-worker/wrangler.toml` binds the production API via a Worker Custom Domain to `mail.moesegfault.dev`, while `site/wrangler.jsonc` binds the release site to `amail.moesegfault.dev`. Neither should have a manually provisioned placeholder A/CNAME. The production mail job in `.github/workflows/ci.yml` is restricted to a `workflow_dispatch` target `production` on `main`; it checks sending DNS, provider permissions/privacy, migrations, Worker upload and `/health`. `.github/workflows/release.yml` requires the production `/health` endpoint before tag-triggered public site deployment, then checks home/manual/changelog and published-copy state. Thus the intended order is **mail Worker first, published assets/tag/site second**.

## Readiness judgment and safe preparation

Production cutover is **not ready** from this DNS/HTTP evidence: neither production HTTP hostname resolves. Do not mistake the pre-existing MX and sending DNS for a working mailbox API or public release site. The production Identity/Login endpoints are reachable, and mail-subdomain DNS records for routing/sending are present. Staging SMTP→ZIP→search and address-add failure remain separate release gates in `docs/validation.md`; this audit does not relax them or the global public-send hold.

Safe work before cutover: finish the staging behavioral gates; ensure the production deployment job is reviewed and runs only from `main` when authorized; retain the DNS verifier as its preflight; prepare an independent post-deploy check of both authoritative nameservers, a recursive resolver, `/health`, and manual/changelog links; check Cloudflare effective Custom Domain state if DNS does not propagate after deployment. Do **not** create placeholder HTTP records, alter apex MX/SPF/DMARC, enable user routes, or launch the site/tag as a workaround. If the first production Custom Domain deployment is authorized, allow for the existing bounded DNS/TLS propagation retries in CI rather than treating an immediate negative lookup as a permanent failure.

## Limits

The observed negative HTTP result is only a transport failure, not an application status. The DNS snapshot cannot prove Cloudflare Email Sending approval, SPF/DKIM/DMARC outcomes for actual sent mail, individual recipient routing, operator-role monitoring, Identity login success, or edge certificates after a future deploy. The exact Cloudflare provider-generated record set was not re-read via authenticated API; `infra/dns/verify_sending.py` performs that comparison at deployment time.

## Held-send cutover preflight — 2026-09-30 18:36 UTC

This update inspects source at `d595bf665b873861fa5de208c1f9b5b9d5169c83`
and public DNS/HTTPS only. It prepares a rollout; it executes **no deployment,
provider mutation, test, build, policy change or tag**. The latest acceptance
ledger in `release-gap-audit.md` remains authoritative for staging gates.

### Public reachability recheck

`Resolve-DnsName -DnsOnly` queried A/AAAA/CNAME at both delegated Cloudflare
nameservers and `8.8.8.8`. `mail.moesegfault.dev` returned zero answers of each
requested type on all three; `amail.moesegfault.dev` queries failed on all three.
HTTPS GETs with redirects disabled and a 15-second timeout did not reach Mail
`/health` or the site `/`. Production Identity discovery returned HTTP 200 and
`application/json`. These are bounded public observations, not authenticated
provider state or proof that any existing production Worker is absent. No
placeholder HTTP DNS record is needed before a Custom Domain deploy.

### Newly actionable source gaps

| Gap | Concrete source evidence | Consequence / required preparation |
| --- | --- | --- |
| Production role rollout lacks the new trace-sink transition contract | `deploy-role-monitor-production.yml` deploys `workers/role-monitor/wrangler.toml`, whose production `ROLE_TRACE_EVENTS` producer points to `amail-trace-events`. The workflow verifies four direct forwards before/after, but does not require the existing sink/version, verify effective capture-off or attest `api-role` Queue ownership. | Do not dispatch this older workflow unchanged after the Queue redesign. Add a reviewed phase-two contract and hosted validation before production use; preserve the four direct forwards. |
| Subsequent production deploy assumes phase-one Queue ownership | `ci.yml` jobs `deploy-trace-sink` and `deploy-worker` call `ensure_trace_queues.py` with no topology argument. Its `validate_detail()` defaults to exactly `amail-mail`; `api-role` is accepted only in `phase=readback`, and `phase=queues` rejects that topology. | Once the role Worker becomes the second producer, both a provisioning pass over the existing Queue and API readback reject `producer_drift`. Merely adding `--topology api-role` everywhere is also invalid. Separate first creation from strict phase-aware existing-resource attestation; do not loosen ownership to an arbitrary producer subset. |
| Production acceptance has no reviewed hosted journey hook | `ci.yml` production dispatch deploys API, ingress and lifecycle consumer, with a health GET but no production native login/SMTP/ZIP/search journey. `staging-outbound-canary.yml` is a staging-only reusable workflow with fixed staging capabilities. `grant-send-canary.yml` supports production, but a grant is not a production delivery oracle. | Prepare a separate explicitly production-scoped, disposable-principal harness and independently readable external oracle before cutover. Do not point staging secrets/fixtures at production, infer delivery from deployment or unhold globally to run a test. |
| Candidate site promotion is unsupported by current publication workflows | `ci.yml` `release-ready` requires an already published, verified Release; `deploy-site` forces `AMAIL_RELEASE_STATE=published`. `release.yml` tag publication requires `check_send_gate.py`, which requires global `allowed` plus four gate flags. | Neither existing path can publish a truthful candidate page while global send is held. Keep the staging candidate available. A production candidate site would need a separate reviewed main-only candidate deployment, not a tag or a fake gate attestation. |

A production candidate is feasible at the content level: `site/src/releaseState.ts`
defaults to `candidate`, and home/manual/changelog explicitly say assets are not
released. It is **not** a ready workflow operation. `site/public/_headers` applies
`noindex, nofollow` only to the staging hostname; a new public candidate path must
explicitly decide indexing and check its production-host headers, as well as all
three pages, TOCs and absence of download/published claims. It must not reuse the
published-copy smoke check, and must not change the release gate.

### Shortest truthful phased rollout contract

1. **Source-ready bracket.** Finish staging privacy and role acceptance and the
   remaining product gates recorded in the release ledger. Review the production
   phase-two/redeployment gaps above, merge the tested revision to `main`, and pin
   that source. No production mutation is implied by a green source run.
2. **Phase one: private sink, then held API and transport.** The existing
   `ci.yml target=production` graph orders sink before API, then ingress and
   lifecycle consumer. First provision must attest only the two named Queue/DLQ
   resources, one sink consumer and the expected API producer; verify all-off
   effective Mail capture and private sink boundaries. Migrations seed global
   `held` (`0006_outbound_abuse.sql`), but **read back the live policy**: that seed
   does not prove an already-existing database is held. Preserve the source,
   resource identities and serving versions. Public site skips while no Release
   exists; that is an intended held cutover, not a failed release.
3. **Phase two: role diagnostics without routing replacement.** Require phase-one
   version/Queue attestations and a production retained-record privacy check;
   verify direct forwards and protected destination status without printing the
   destination. Deploy the unrouted role Worker, then attest exactly API plus
   role producers, one sink consumer, empty/unconsumed DLQ topology and effective
   role capture-off. Check natural Cron/lease and official alert receipt. Do not
   repoint the four standard roles as part of this rollout. A later API/sink
   redeploy must use an attested `api-role` state; it must not attempt first-time
   provisioning again or remove a live producer to satisfy phase-one checks.
4. **Held production behavioral acceptance.** Check authoritative/recursive DNS,
   HTTPS/Custom Domains and the production OIDC client through the prepared
   disposable native flow; one owned route, real external SMTP, ZIP/assets,
   search/mutations and exact cleanup. For outbound use only a reviewed 15-minute
   one-send production grant, external receipt/authentication/rendering oracle
   and lifecycle feedback; keep global send held throughout. Preserve unrelated
   addresses, apex MX/SPF/DMARC and existing direct forwards.
5. **Release is a distinct decision.** Attest only the observed production gates
   using opaque evidence references. Global unhold, the `v0.1.0` tag and published
   assets/site remain separate reviewed steps after all gates pass. A held API or
   candidate landing page is not the promised `v0.1.0` release. Failed phases
   stop without automated unhold, destructive Queue reconciliation, widened
   permissions or blind resend; recover only exact resources created by the run.

The user has reported adjusting the existing routing token's account-level
Addresses Read grant. This preparation does not inspect its value or assert the
grant effective: use the separately owned fixed-output read-only permission
probe and ledger result. Repo-level Secrets remain the user's chosen project
management model; this plan does not request per-environment token duplication.
