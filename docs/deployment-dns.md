# DNS and email deployment readiness (2026-09-28)

## Decision-relevant finding

The requested `xxx@mail.moesegfault.dev` service cannot scale beyond **200 distinct inbound addresses** using Cloudflare Email Routing on the existing `moesegfault.dev` zone. Cloudflare supports catch-all routing only at the **zone apex**, not at an Email Routing subdomain, and allows 200 routing rules per domain. A separate Cloudflare child zone would turn `mail.moesegfault.dev` into an apex, but Cloudflare subdomain-zone setup is Enterprise-only. This is a product architecture constraint, not a DNS typo or a Worker implementation detail. Ten addresses per account therefore implies at most 20 fully provisioned accounts in the worst case if Email Routing is the sole inbound MX. Do not advertise unbounded public registration until an inbound provider/topology is selected and tested.

References: [Cloudflare subdomain email configuration](https://developers.cloudflare.com/email-service/configuration/subdomains/), [routing rules](https://developers.cloudflare.com/email-service/configuration/email-routing-addresses/), [email limits](https://developers.cloudflare.com/email-service/platform/limits/), [Cloudflare child-zone availability](https://developers.cloudflare.com/dns/zone-setups/subdomain-setup/).

## Observed public DNS

Initial snapshot checked with PowerShell `Resolve-DnsName` before 2026-09-28 11:01 UTC. DNS observations are not a substitute for checking authenticated Cloudflare product state. The initial `mail` rows below are historical; see the onboarding update immediately afterward.

| Host | Observation | Implication |
| --- | --- | --- |
| `moesegfault.dev` | NS `jermaine.ns.cloudflare.com`, `raquel.ns.cloudflare.com`; MX `route1/2/3.mx.cloudflare.net`; TXT SPF `v=spf1 include:_spf.mx.cloudflare.net ~all` | Apex DNS and inbound mail are already on Cloudflare. Preserve existing behavior. |
| `_dmarc.moesegfault.dev` | `v=DMARC1; p=reject;` | Outbound mail from apex needs aligned SPF or DKIM; do not replace or weaken this record casually. |
| `cf-bounce.moesegfault.dev` | Cloudflare MX and SPF records observed | Suggests apex Email Sending onboarding, but product state and DKIM verification remain unconfirmed. |
| `mail.moesegfault.dev` | No A, AAAA, CNAME, MX, or TXT observed | Neither public API nor mail receipt at requested host is live yet. |
| `_dmarc.mail.moesegfault.dev`, `cf-bounce.mail.moesegfault.dev` | No TXT observed | Subdomain sending is not visibly onboarded. Parent DMARC `p=reject` is inherited absent an explicit subdomain policy. |
| `amail.moesegfault.dev` | No A, AAAA, CNAME, MX, or TXT observed | Release site is not live yet. |
| `login.moesegfault.dev` | Cloudflare A/AAAA observed | Existing login DNS is live; leave untouched. |

### Onboarding update: 2026-09-28 11:01 UTC

The project operator successfully called Cloudflare's API for zone `6edff81c6ed02f412e70868076411a5e`: `POST /zones/{zone}/email/routing/dns` and `POST /zones/{zone}/email/sending/subdomains` for `mail.moesegfault.dev`. Both API responses had `success=true`; routing was reported **enabled** and sending **ready**. The pre-onboarding `mail` observations above are no longer current. Existing apex records were not changed by this operation according to the operator.

An authoritative lookup against `jermaine.ns.cloudflare.com` after the API calls returned these `mail.moesegfault.dev` records:

| Type | Owner | Value |
| --- | --- | --- |
| MX | `mail.moesegfault.dev` | `route1.mx.cloudflare.net` (39), `route2.mx.cloudflare.net` (49), `route3.mx.cloudflare.net` (94) |
| TXT | `mail.moesegfault.dev` | `v=spf1 include:_spf.mx.cloudflare.net ~all` |

The first lookup found no `_dmarc.mail.moesegfault.dev` or `cf-bounce.mail.moesegfault.dev` TXT. A later authoritative lookup against `jermaine.ns.cloudflare.com` found **all six required sending records**, confirming the initial absence was DNS propagation timing rather than missing DNS permissions:

| Type | Owner | Value |
| --- | --- | --- |
| MX (3 records) | `cf-bounce.mail.moesegfault.dev` | `route1.mx.cloudflare.net` (39), `route2.mx.cloudflare.net` (49), `route3.mx.cloudflare.net` (94) |
| TXT (SPF) | `cf-bounce.mail.moesegfault.dev` | `v=spf1 include:_spf.mx.cloudflare.net ~all` |
| TXT (DKIM) | `cf-bounce._domainkey.mail.moesegfault.dev` | Present; key value omitted from this note. |
| TXT (DMARC) | `_dmarc.mail.moesegfault.dev` | `v=DMARC1; p=reject;` |

DNS setup for both routing and sending is now visible at the authoritative server. Next, query an independent public recursive resolver to confirm propagation; then verify SPF/DKIM/DMARC alignment with a delivered external message, since DNS presence alone does not prove successful delivery. Preserve the apex's `p=reject` policy and existing records.

### Isolated staging mail domain

The project operator also onboarded `mail-staging.moesegfault.dev` as a separate Cloudflare Email Routing and Email Sending subdomain. The reported Email Sending identifier/tag is `176c49089bf54e7e91e3e537eadcc140`; product API reported Routing **ready** and Sending **enabled**. This staging domain is intended for end-to-end tests without creating user addresses or sending test traffic on `mail.moesegfault.dev`. It remains within the same parent Cloudflare zone and is **not** a separate zone apex, so the same no-catch-all and 200-literal-rule limits apply independently to it. Staging routing rules and sender domain must not be confused with production rules or sender identities.

Initial authoritative query of `jermaine.ns.cloudflare.com` after onboarding found:

| Type | Owner | Value / status |
| --- | --- | --- |
| MX (3 records) | `mail-staging.moesegfault.dev` | `route1.mx.cloudflare.net` (39), `route2.mx.cloudflare.net` (49), `route3.mx.cloudflare.net` (94) |
| TXT (SPF) | `mail-staging.moesegfault.dev` | `v=spf1 include:_spf.mx.cloudflare.net ~all` |
| Sending records | `cf-bounce.mail-staging.moesegfault.dev`, `cf-bounce._domainkey.mail-staging.moesegfault.dev`, `_dmarc.mail-staging.moesegfault.dev` | Not yet returned at this first query; subsequent verification below confirms propagation. |

After approximately 30 seconds, a second query against `jermaine.ns.cloudflare.com` returned all six sending records: `cf-bounce.mail-staging.moesegfault.dev` MX x3 (`route1/2/3.mx.cloudflare.net`, priorities 39/49/94), SPF TXT (`v=spf1 include:_spf.mx.cloudflare.net ~all`), `cf-bounce._domainkey.mail-staging.moesegfault.dev` DKIM TXT (present; key omitted), and `_dmarc.mail-staging.moesegfault.dev` TXT (`v=DMARC1; p=reject;`). A separate query through the workstation's default recursive resolver also returned staging MX x3, bounce MX x3, DKIM TXT, and DMARC TXT. Thus staging is **DNS-propagated for the tested resolvers**. A direct query to `1.1.1.1` timed out from this environment, so it was not used as evidence of absence. A delivered staging email with authentication results is the final test. Do not infer record absence from a single early query or manually create duplicate records.

## Deployment topology and DNS procedure

1. **HTTP Worker API**: Attach `mail.moesegfault.dev` as a Wrangler Worker Custom Domain using `routes = [{ pattern = "mail.moesegfault.dev", custom_domain = true }]`. Cloudflare creates the HTTP DNS record and certificate on deployment; no placeholder A/CNAME is necessary. Existing CNAME on the hostname would conflict. MX and TXT at the same owner name can coexist with an A-like Worker custom-domain record; verify resulting DNS in deployment. [Custom Domains](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/).
2. **Astro release site**: Use its own Worker Custom Domain, `amail.moesegfault.dev`, by the same method. This should not alter apex DNS.
3. **Inbound email**: The `mail` subdomain is enabled for Email Routing and its MX records are authoritative. If Cloudflare Email Routing is selected despite the 200-address cap, each claimed address must be provisioned as a literal routing rule to the mail Worker, via the Email Routing REST API or dashboard, with failure/rollback semantics coupled to registration. A static Wrangler `addresses` list is inappropriate for dynamic user registrations; Wrangler 4.113+ supports it but reconciles only deployed literals and deletion can be destructive. Do not enable a catch-all at `moesegfault.dev` to simulate `mail.moesegfault.dev`: domains are distinct SMTP destinations. [Subdomains](https://developers.cloudflare.com/email-service/configuration/subdomains/), [routing rules and Wrangler caveats](https://developers.cloudflare.com/email-service/configuration/email-routing-addresses/).
4. **Outbound email**: `mail.moesegfault.dev` is onboarded to Cloudflare Email Sending, with `cf-bounce` MX/SPF/DKIM and subdomain DMARC records now visible at the authoritative server. Check authentication and alignment with a real external recipient before declaring delivery ready. For site-originated messages, use `mail@moesegfault.dev`; verify apex Email Sending status/DKIM without changing existing apex MX or SPF. Email Sending binding/REST API requires an onboarded sender domain; forwarding-only Email Routing does not imply arbitrary-recipient sending. [Sending setup](https://developers.cloudflare.com/email-service/get-started/send-emails/), [subdomain sending](https://developers.cloudflare.com/email-service/configuration/subdomains/), [Workers send API](https://developers.cloudflare.com/email-service/api/send-emails/workers-api/).
5. **Size contracts**: Cloudflare Email Sending's documented total outbound message size is 5 MiB, except 25 MiB to verified destinations; max 50 recipients. Email Routing inbound max is 25 MiB. ZIP content/attachments must be bounded and users must see explicit errors rather than silent truncation. [Email limits](https://developers.cloudflare.com/email-service/platform/limits/).

## Credentials and operational guardrails

- Local `gh` is authenticated to `kleedaisuki` and has `repo`/`workflow` scopes. The repository has GitHub secret names `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, Cloudflare R2/S3 keys, and `OPENROUTER_API_KEY`; values were not read.
- Local Wrangler 4.130.0 is authenticated to the user's Cloudflare account. Its OAuth permissions include Workers write, Email Routing write, Email Sending write, and zone read, **but not DNS write**. Do not assume the local token can create arbitrary MX/TXT records. Worker Custom Domain deployment can itself create its required HTTP DNS record. A CI token's actual scopes cannot be inferred from the GitHub secret's name.
- The project operator onboarded the `mail` subdomain for Email Routing and Email Sending as noted above; this investigation did not make additional mutations. In particular, existing apex MX, SPF, DMARC, and login records were not changed. Do not create routing rules for user addresses until the 200-address architecture decision is settled.
- After deployment, verify with authoritative DNS lookup, HTTPS fetch for both custom domains, authenticated product-state checks, and actual SMTP receive/send tests (including an unregistered recipient rejection, SPF/DKIM/DMARC results, bounce/error visibility, and a non-verified external recipient). The tests should run from GitHub Actions or deployed environments, as requested; avoid downloading local test toolchains.

## Open architecture decision

Either (A) accept a hard 200-address cap for this zone, with dynamic Cloudflare route management and honest account-capacity policy; (B) obtain Cloudflare Enterprise child-zone setup and verify apex catch-all on that child zone; or (C) use a different inbound MX provider that supports catch-all on `mail.moesegfault.dev` and delivers securely to the Rust Worker (HTTP webhook or queue). Option C preserves unbounded registration while keeping application logic in Cloudflare Workers, but the external transport/provider and its costs, authentication, reliability, size limits, and privacy obligations must be evaluated before implementation. The 200-address limit is the decisive blocker for a public ten-address-per-account service built solely on Cloudflare Email Routing.
