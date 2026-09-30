# Worker-R2 historical GraphQL error-class review

Reviewed 2026-10-01 at `6c34c430fc708e642e28d702a1fc66d3a92b408d`.
Scope: the new error-class helper, focused synthetic tests, appended decision
record, and imported original provenance/transport implementations. Existing
uncommitted deployment changes are excluded. No local tests, authenticated
provider requests, mail sends, routing/R2 operations, or production edits were
performed.

## Decision

**GO for nondeploying hosted source checks. No substantive source defect found.**
The source is suitable for a separately reviewed manual workflow lane followed
by one distinct historical query, provided hosted checks pass. This review is
not live-query authorization, delivery evidence, R2 capability acceptance,
permission inspection, or release acceptance. The new workflow wiring is not
part of this commit and must be reviewed independently.

## Contract trace

| Boundary | Evidence | Assessment |
| --- | --- | --- |
| Original experiment | `run()` and imported `historical_window()` | Requires exact new confirmation, original run `36751791789`, repository identity, failed first dispatch attempt, original SHA `15b50a5d1102873a81ff6628d491966852c2b76c`, workflow/branch, one exact failed job and step, complete bounded jobs list and coherent times. Uses the unchanged original step interval minus two minutes / plus ten minutes; does not substitute a current-time window. |
| Content minimization | `QUERY` | Same two zone-level event datasets, `Time!` variables, time filters and ordering as the original query. Each limit is reduced to one and only `__typename` is selected. No event identity, content, timestamp, status, or provider error-detail field is requested. |
| Transport | `fetch()` and imported `OPENER` | One GraphQL POST, no redirect forwarding or retry, fixed HTTPS endpoint, 20-second socket timeout, and 128 KiB body limit. HTTP error bodies receive the same bounded JSON processing; duplicate object keys reject via the imported hook. HTTP status is classified separately from GraphQL error content. |
| Message classifier | `TEMPLATES`, `message_class()`, `errors_bin()` | Case-sensitive full-string matching of public phrases, bounded newline-free variable suffixes, 2048-character messages, at most 100 errors. Arbitrary codes/messages stay unknown; only documented `extensions.code=budget` adds positive rate/resource evidence. Conflicts are mixed, not cherry-picked. Malformed/oversized messages remain invalid. |
| Error paths | `error_scope()` | Exact `viewer/zones` position accepts integer zero and exact string zero, excludes booleans/floats/other indices, and recognizes only source-owned aliases or canonical dataset names. No path values leave the process. Unscoped remains a scope hint, not a root-error assertion. |
| Partial/clean data | `minimal_data()`, `run()` | Error-bearing responses keep data unverified. No-error responses check only the selected bounded metadata shape; empty rows can match shape without implying historical completeness. HTTP and error bins remain separate even for unexpected combinations. |
| Output and authority | `main()` | Fixed field order and closed bins; raw messages, suffixes, type names, paths, URLs, status text, credentials, and exception text cannot enter output. All classified results include `delivery=UNVERIFIED`. Exit zero means classification, including mixed, invalid, unknown and non-200 cases, not provider success or permission to retry/send. |

## External evidence

Consulted Cloudflare's official [GraphQL error reference](https://developers.cloudflare.com/analytics/graphql-api/errors/)
and [account-based rate-limit reference](https://developers.cloudflare.com/analytics/graphql-api/account-based-rate-limiting/)
on October 1, 2026. The allowlist follows the documented authentication/access,
parsing, dataset-limit, rate/resource, availability and internal-error examples.
The references also support error-bearing HTTP 200 responses, string-index
error paths and the budget extension. Recognition is intentionally incomplete:
undocumented wording remains unknown rather than guessed. Access-category
evidence cannot by itself distinguish a token grant from dataset entitlement.

The newly selected meta-field can itself be rejected by a provider schema or
implementation. Therefore a schema-category result does not establish which
field the older queries rejected. The durable document correctly preserves
this distinction and does not reconstruct the original failure from a new
response.

## Synthetic coverage and limits

Statically inspected fixtures cover public message categories and lookalikes,
unknown/newline/case variants, extension conflicts, malformed/oversized messages,
bounded error collections, string/integer indices and invalid alternatives,
metadata-only row bounds, exact time variables and reduced query selection,
one request, HTTP-error JSON handling, exact confirmation/run gates, and closed
output under unexpected exceptions. Original provenance fixtures remain
necessary in hosted checks because the focused test mocks that shared helper.
Tests were not executed locally and no hosted pass is attested here.

The focused tests do not independently exercise duplicate/oversized JSON or a
real redirect against this new fetch function; those mechanisms are reused and
directly visible in source, with existing shared tests. This is a coverage limit,
not a demonstrated failure path. Workflow review must enforce branch, first
attempt, staging, prerequisite tests and a job timeout: a socket timeout alone
does not bound a slowly trickling response's total wall-clock duration.

Unknown/mixed errors, transport failure, or even a clean metadata-only response
leave historical delivery and B registration unresolved. No category warrants
automatic token widening, repeated historical queries, a new synthetic send,
or lifting any release gate.
