# One-shot sampled Security Events diagnostic for staging trace run 36671177226

This document records the exact implementation and interpretation contract for
`infra/provider/probe_staging_trace_security_events.py`. It is a read-only
discriminator, **not** a retained-log privacy acceptance or proof of the
historical request's producer. The canary's 403 occurred near **2026-09-30
04:59:42 UTC** without an application request ID; see
[staging-trace-canary.md](staging-trace-canary.md).

Maintenance update (2026-10-01): the completed fixed-window dispatch target and
job are retired from current `ci.yml`; source classifier and synthetic tests are
retained. The wiring described below is historical evidence, not current run
instructions. See [current operational lanes](maintenance-operational-lanes.md).

## Bounded query and invocation

The retired GitHub Actions `ci.yml` target `staging-trace-security-events` was
fixed to run `36671177226`, the staging environment, and the exact confirmation
`READ_STAGING_TRACE_SECURITY_EVENTS_36671177226`. It uses the repository's
fixed, public zone ID and the existing `CLOUDFLARE_API_TOKEN` secret, injected
only into the final query step. The first hosted dispatch
[36673249868](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36673249868)
stopped **before any provider request** with `reason=credential`: unlike the
other staging jobs, its workflow incorrectly read a nonexistent `CF_ZONE_ID`
secret. This wiring was corrected. The next hosted dispatch
[36675301214](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36675301214)
reached GraphQL and received HTTP 200 with a non-null `errors` array, but the
original privacy gate collapsed all provider errors to `graphql_unverified`.
The revised fixed-taxonomy dispatch
[36678625568](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36678625568)
also returned `graphql_unverified`. Neither run established Security Events
rows, a WAF action, or the producer of the mail API's 403. The provider's raw
error messages were not logged. This is a **fail-closed diagnostic result**:
do not repeat the unchanged query or infer that no edge intervention occurred.
The invocation below is retained as the bounded contract, not a retry
instruction. Its retired confirmation was
`READ_STAGING_TRACE_SECURITY_EVENTS_36671177226`; do not replay the historical
workflow or widen the expired incident window.

The script performs one POST to Cloudflare Analytics GraphQL, no redirect and
no retry. It selects only `datetime`, `clientRequestHTTPHost`, `action`,
`source`, and `description` from zone-scoped `firewallEventsAdaptive`. Query
variables constrain the exact host `mail-staging.moesegfault.dev` and inclusive
**04:58:42–05:00:42 UTC** interval. A 100-row page is deliberately rejected as
possibly truncated; accepted pages contain at most 99 rows and 64 KiB. Returned
rows are checked again for exact host and window before any result is emitted.
The API does not echo the zone tag, so the zone scope depends on the exact
`zones(filter: {zoneTag: ...})` query and requiring exactly one returned zone.

Only fixed count classes, allowlisted action/source/rule labels, capped bucket
counts, and a fixed result label are printed. The description is classified
in memory by exact equality; all other descriptions map to `other`. The
program does not select or print URL, path, query, IP, Ray ID, user agent,
response body, GraphQL error message, redirect target, or raw event. Any
401/403 on GraphQL is `permission` and says nothing about the mail API's 403.
GraphQL errors never print provider text. A subsequent source revision
classifies only the fixed phrases documented by Cloudflare into
`graphql_retention_unverified`, `graphql_limit_unverified`,
`graphql_parse_unverified`, `graphql_auth_unverified`, or
`graphql_transient_unverified`; unknown, malformed, or mixed errors remain
`graphql_unverified`. These are **diagnostic hints**, not proof of a specific
invalid field or of the origin of the mail API's 403. The same exact zone,
host, window, selected fields, 100-row limit, credential, and one-request
contract remain unchanged. There is no broader fallback or raw error logging.

## Interpretation and limitations

- `sampled_edge_candidate` means at least one sampled mitigating action on the
  host during the two-minute window. It is **not exact attribution**: the
  historical request has no captured Ray ID and other traffic can coexist.
- `no_sample_or_non_edge` means no sampled mitigating action appeared in this
  bounded page. It does **not** rule out an edge intervention: Security Events
  are sampled, and some early 403s may be absent.
- `unverified` means the query could not support even this limited inference.
  Do not broaden the query, change WAF rules, or create a second token
  automatically. If permission fails, review an Analytics Read grant or use a
  private dashboard inspection before retention expires.

The query uses inline `Time` and `string` variables rather than naming the
filter input type. Cloudflare official examples disagree between
`FirewallEventsAdaptiveFilter_InputObject` and
`ZoneFirewallEventsAdaptiveFilter_InputObject`; neither type is assumed.
Cloudflare's documentation establishes the selected fields and dataset, but a
live schema call has not been run at source time. If the account rejects the
host filter or `description` field, the job fails closed with a fixed code;
it must not retry with an unscoped or larger query.

Primary Cloudflare references:

- [Firewall Events GraphQL tutorial](https://developers.cloudflare.com/analytics/graphql-api/tutorials/querying-firewall-events/)
- [GraphQL querying basics, including host field](https://developers.cloudflare.com/analytics/graphql-api/getting-started/querying-basics/)
- [Firewall Events source values](https://developers.cloudflare.com/logs/logpush/logpush-job/datasets/zone/firewall_events/)
- [Security Events sampling and retention](https://developers.cloudflare.com/waf/analytics/security-events/)
- [GraphQL field-change notice for `description`](https://developers.cloudflare.com/logs/reference/change-notices/2023-02-01-security-fields-updates/)
- [Analytics API token permissions](https://developers.cloudflare.com/analytics/graphql-api/getting-started/authentication/api-token-auth/)
- [GraphQL error response categories and HTTP 200 behavior](https://developers.cloudflare.com/analytics/graphql-api/errors/)
