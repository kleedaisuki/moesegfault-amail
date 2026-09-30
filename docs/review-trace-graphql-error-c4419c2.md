# Review: bounded GraphQL error classification (`c4419c2`)

## Verdict and scope

**GO for one already-confirmed, read-only hosted diagnostic after the relevant CI gate.** No substantive defect was found in the source change. This is a source and synthetic-test review, not a live Cloudflare query or verification of token privileges, data retention, or the historical request's producer.

Reviewed the commit diff, the complete probe and synthetic tests, the `staging-trace-security-events` workflow job, prior probe review, and [Cloudflare's GraphQL error documentation](https://developers.cloudflare.com/analytics/graphql-api/errors/). Cloudflare confirms that an HTTP 200 response can carry a non-null `errors` array and publishes the phrases used for the new fixed categories.

## Contract assessment

| Concern | Evidence and conclusion |
| --- | --- |
| Request surface | The diff changes only failure classification, tests, and explanatory documentation. `ENDPOINT`, `QUERY`, exact zone/host/time variables, `limit: 100`, selected fields, `fetch`, one POST, timeout, size cap, no redirects, and no retries are unchanged. No broader fallback was added. |
| Privacy | Provider `message`, `path`, and the raw response remain in memory. The classifier emits only one of six fixed GraphQL failure labels. `main` also gates these through `REASONS`; arbitrary exceptions collapse to `internal`. Neither the original error nor a fragment of it reaches stdout. |
| Error handling | A non-null GraphQL `errors` value always raises `Unverified`, including when `data` is present. The classifier caps the array at eight and each message at 2,048 characters; malformed and heterogeneous categories collapse to `graphql_unverified`. It never interprets an error-bearing response as Security Events evidence. |
| Inference | All added labels end in `unverified`. `graphql_auth_unverified` concerns GraphQL authorization only, not the mail API 403; parse/retention/limit labels do not identify a specific offending field or prove that events exist. The existing sampled-event result remains deliberately non-attributive. |
| Tests | Synthetic tests exercise each new category, unknown text, mixed categories, and non-echo of a private marker. Pre-existing tests cover request field scope, no sensitive selected fields, malformed/out-of-window data, duplicate JSON keys, confirmation-before-network, and generic exception suppression. Hosted CI is still required before live dispatch. |

## Residual limitations, not blockers

Classification uses substring matches rather than parsing a stable machine-readable provider error code, because Cloudflare documents illustrative human-readable messages. A future provider wording change or a message that incidentally includes one of those phrases can mislabel the *hint*; it cannot turn the query into a success, disclose the message, or attribute the historical 403. An unrecognized authorization or rate-limit phrase remains generic, which is safer than guessing. The result should be recorded exactly as a diagnostic hint, without automatic remediation or repeated querying. The incident window is fixed, so provider retention may make a delayed rerun uninformative.
