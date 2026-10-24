# Provider adapters

## Temporary-address domains

The existing `ensure_tmpaddr_staging.py` entry point preserves its staging default
and accepts only the two fixed `Target` enum members, never an arbitrary domain:

| CLI target | Exact domain | Apply authority |
| --- | --- | --- |
| `staging` (default) | `tmpaddr-staging.moesegfault.dev` | Admitted candidate staging writer |
| `production` (explicit) | `tmpaddr.moesegfault.dev` | Admitted trusted-main production writer |

Its default mode is a read-only readiness check. The admitted v0.3.0 writers run:

```sh
python infra/provider/ensure_tmpaddr_staging.py --apply
MAIL_SENDING_DOMAIN=tmpaddr-staging.moesegfault.dev python infra/dns/verify_sending.py
# Production is never inferred from the branch or credential.
python infra/provider/ensure_tmpaddr_staging.py --target production --apply
MAIL_SENDING_DOMAIN=tmpaddr.moesegfault.dev python infra/dns/verify_sending.py
```

For a failed onboarding step, the existing protected `staging-inspect` lane uses
`--inspect --output .temp/tmpaddr-staging-inspection.json`. This mode executes only
independent fixed-domain GETs: deployment-token DNS inventory, zone-settings
access with each existing credential independently, and Sending inventory/generated DNS. A failed read records
`state=unknown`, never absence. Output includes only closed phase/method/HTTP/
credential-role diagnostics and boolean/count predicates, never DNS contents,
domain identifiers, token values or provider prose. Inspection completion does not
mean configuration is ready, and successful read access does not prove Write
permission. In particular, Routing DNS onboarding requires Zone Settings Write;
a successful rules-only query cannot establish that permission.
The existing production inspection lane uses
`--target production --inspect --output .temp/tmpaddr-production-inspection.json`.
It has identical GET-only behavior and a production-specific schema/domain label;
inspection never invokes either realm's apply functions or grants write authority.

Sending DNS inspection also reports each generated requirement's closed role,
record type/purpose, equality, existing type/count and conflict predicates. It
does not expose names, values, keys or identifiers. DNS RRsets can contain
multiple MX values and unrelated TXT purposes; these are retained, not replaced.
A different existing SPF/DMARC policy or DKIM selector candidate remains a
conflict, as does CNAME coexistence. No SPF merging is performed. This follows
[RFC 7208 section 3](https://www.rfc-editor.org/rfc/rfc7208#section-3): unrelated
TXT is permitted, but multiple SPF policies at the same owner name are not.
Cloudflare's [authentication documentation](https://developers.cloudflare.com/email-service/concepts/email-authentication/)
places Routing SPF at the domain and Sending SPF separately at `cf-bounce`;
those names must not be conflated into a synthetic merged record.

TXT comparison uses the existing pinned `dnspython==2.8.0` dependency, shared
through `infra/dns/txt_record.py`. Its public tokenizer decodes quoted presentation
tokens into bytes, concatenated without inserted spaces. This deliberately does
not construct wire RDATA: provider APIs can present an already-joined logical
DKIM value as one quoted string longer than the 255-byte wire-component limit.
Malformed escapes, non-string trailing tokens and non-UTF-8 values fail closed.
Unquoted logical
API content is preserved exactly: parsing it as zone text would incorrectly turn
semicolons into comments and split meaningful spaces. The read-only sending DNS
verifier uses the same parser for provider requirements and already concatenates
authoritative response strings. This follows [RFC 1035 section 3.3.14](https://www.rfc-editor.org/rfc/rfc1035#section-3.3.14)
and [RFC 6376 section 3.6.2.2](https://www.rfc-editor.org/rfc/rfc6376#section-3.6.2.2),
not a DKIM key rotation. Diagnostics expose only logical-content/hash equality
booleans and a presentation-changed count; neither key material nor hashes are
retained. A genuinely different selector key remains a conflict.
The pinned upstream [tokenizer](https://github.com/rthalley/dnspython/blob/v2.8.0/dns/tokenizer.py)
provides `Token.unescape_to_bytes()`; [TXT RDATA construction](https://github.com/rthalley/dnspython/blob/v2.8.0/dns/rdtypes/txtbase.py)
adds the wire-specific component limit and is therefore the wrong comparison
layer for joined API values.

Restore and verify the same-run tested artifact before mutation, and retain the
existing workflow realm writer lock. All apply calls require GitHub Actions and
the first run attempt. Staging additionally requires the exact candidate branch,
`AMAIL_STAGING_ENVIRONMENT=staging` and
`AMAIL_STAGING_CONFIRM=RUN_STAGING_V030`. Explicit production additionally requires
trusted `refs/heads/main`, `AMAIL_PRODUCTION_ENVIRONMENT=production`,
`AMAIL_PRODUCTION_CONFIRM=RUN_PRODUCTION_V030` and
`AMAIL_PRODUCTION_GRAPH_FREEZE=FREEZE_PRODUCTION_GRAPH_WRITERS`. Staging consent
cannot authorize production, and production consent cannot authorize staging.

Credentials stay in memory. `CLOUDFLARE_API_TOKEN` needs Email Sending Read/Write,
DNS Read/Write and Zone Settings Write for Routing DNS onboarding on the existing
zone. Domain onboarding uses this deployment credential, not the runtime
`CF_EMAIL_ROUTING_TOKEN`, which remains restricted to mailbox rule management.
Inspection reads zone settings separately with each credential to distinguish
their existing access; it does not broaden either token's permissions. Missing
permissions fail with a closed diagnostic rather than printing provider prose.

The adapter inventories before creating, calls Routing DNS with the exact
subdomain name, and uses the Sending API's generated requirements for DNS. It
never derives DKIM/MX/SPF values from another domain, overwrites/deletes DNS,
changes catch-all/routing rules, or enables sending policy. Conflicting records
stop provisioning. New sender content previews and partial suppressed-recipient
drops are disabled before readiness succeeds. SMTP routing rules remain owned by
normal mailbox registration and retirement.
Existing operator direct-forward contact routes, their private destination and
the global send policy remain owned by the production controller/operator model;
the temporary-domain helper neither creates catch-all/contact routes nor adopts
another domain's rules. Already-safe sender settings are retained without a PATCH.

`provider_config_verified` confirms provider configuration, not authoritative DNS
propagation, SMTP delivery or the application journey. The second command checks
provider-generated sending records at all authoritative nameservers. A timeout
after any mutation is unknown: inspect current state; never blindly retry the
write or rerun the workflow to conceal an uncertain submission.

Official contracts used:

- [Subdomain configuration](https://developers.cloudflare.com/email-service/configuration/subdomains/): literal routing is required on subdomains; receiving and sending are separately onboarded.
- [Routing DNS create](https://developers.cloudflare.com/api/resources/email_routing/subresources/dns/methods/create/): optional exact `name` and provider-owned MX/SPF creation.
- [Sending subdomain create](https://developers.cloudflare.com/api/resources/email_sending/subresources/subdomains/methods/create/), [generated DNS](https://developers.cloudflare.com/api/resources/email_sending/subresources/subdomains/subresources/dns/methods/get/), and [settings update](https://developers.cloudflare.com/api/resources/email_sending/subresources/subdomains/methods/edit/).

The deprecated Routing DNS `GET ?subdomain=` response is intentionally not used:
the official API says its shape is unmodeled and must not be relied upon.
