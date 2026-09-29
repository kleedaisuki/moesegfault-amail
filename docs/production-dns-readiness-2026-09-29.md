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
