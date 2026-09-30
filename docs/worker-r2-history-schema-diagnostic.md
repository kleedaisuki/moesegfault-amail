# Worker-R2 historical query: schema failure discriminator

## Evidence and scope (2026-10-01)

The owner reports that hosted historical classifier run
[36756920203](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36756920203)
at `cd64c14` emitted only `worker_r2_history=UNVERIFIED reason=schema`.
This investigation inspected `infra/tests/staging_worker_r2_delivery_history.py`,
its synthetic fixtures and `review-worker-r2-delivery-history-source-e22698f.md`.
No private query, local test, send, route operation or R2 operation was performed.
The run's raw provider response is deliberately unavailable: the fixed label
cannot reconstruct it. The original probe and recovery remain governed by
[the second-principal record](staging-second-principal.md).

## What the label establishes, and what it does not

The current implementation deliberately merges multiple failures into `schema`:

| Source boundary | Plausible rejected representation |
| --- | --- |
| `unique_object()` / `fetch()` | Duplicate JSON keys, non-JSON response or non-object envelope. |
| `events()` | GraphQL errors; unexpected top-level keys; non-null `errors` (including an empty array); missing/null viewer or zones; zero/multiple zones; unexpected dataset keys or null dataset lists. |
| `scoped()` | Every returned row must have exactly the selected keys; all rows, including unrelated messages, require non-null bounded string sender, recipient, subject and status; timestamps must use the accepted UTC representation; message ID must be null or bounded string. |
| `classify()` | Matched Sending rows require integer `isLastEvent` in 0/1, not JSON Boolean/string; matched optional cause/action/rule fields have specific null/string limits. |

Therefore neither a field-name typo, a permission denial, a null subject, nor a
Boolean terminal flag is established by this result. Importantly, `scoped()`
validates **unrelated historical rows before candidate selection**: a missing
header in a different message can invalidate the entire query without proving
anything about the synthetic probe. That is a possible schema-policy mismatch,
not evidence that such a row actually occurred. The implementation is safely
fail-closed; synthetic tests verify its chosen policy rather than live schema.

The official [Email metrics reference](https://developers.cloudflare.com/email-service/observability/metrics-analytics/)
(page dated June 9, 2026; consulted October 1, 2026) documents both datasets as
zone-level, Analytics Read, 31-day retention, the selected identity fields,
`errorCause`, `ruleMatched`, `isLastEvent` as `uint8`, and Time filters for event
queries. Its examples use the same `string!`, `Time!` and time-filter syntax.
Consequently there is **no documented field-name/type typo to repair blindly**.
The reference is not a formal non-null JSON contract and does not establish
what this token/zone returned. The official
[Routing tutorial](https://developers.cloudflare.com/analytics/graphql-api/tutorials/querying-email-routing/)
shows `errors: null` in one success example, not a guarantee that all success
envelopes have exactly the existing parser's key set.

Cloudflare's [introspection reference](https://developers.cloudflare.com/analytics/graphql-api/features/discovery/introspection/)
describes a dynamic schema and per-user dataset availability. This supports
checking runtime representation, not assuming documentation alone attests it.
A full introspection dump is unnecessary for the first discriminator and would
increase response scope substantially.

## Proposed new bounded discriminator (design, not live authorization)

Use a **new, reduced query**, not the previous event query again:

```graphql
query WorkerR2HistoryBaselineShape($zoneTag: string!, $start: Time!, $end: Time!) {
  viewer {
    zones(filter: {zoneTag: $zoneTag}) {
      sendingShape: emailSendingAdaptive(
        filter: {datetime_geq: $start, datetime_leq: $end},
        limit: 100, orderBy: [datetime_ASC]
      ) { datetime status }
      routingShape: emailRoutingAdaptive(
        filter: {datetime_geq: $start, datetime_leq: $end},
        limit: 100, orderBy: [datetime_ASC]
      ) { datetime status }
    }
  }
}
```

Keep the original exact run `36751791789`, attempt 1, original SHA, workflow,
branch, failed unique job/step and authenticated GitHub provenance checks.
Derive **the identical historical window** through `historical_window()`; no
current-time query, widened time window or alternate recipient is permitted.
Require a new fixed confirmation and reviewed manual hosted wiring. Issue at
most one no-redirect GraphQL POST, retaining the existing 128 KiB body limit,
20-second socket timeout and finite hosted timeout. Receive only Analytics and
GitHub read credentials; do not expose sending, routing-write or R2 credentials.

This query requests no sender, recipient, subject, provider ID, rule ID, cause
or error detail. It tests baseline dataset access/envelope/scalars independently
of the original richer selection and candidate identity assumptions. Its
timestamps and statuses must remain in memory only. It is **not** a delivery
classifier because it cannot identify the probe's message.

Suggested closed output contract:

* `response=json_object|non_json|oversize|transport|http_other`.
* `graphql=none|empty_errors|errors|invalid`, with error-path bin
  `sending|routing|both|unscoped|invalid` derived only from exact source-owned
  alias path components. Do not print or substring-search provider messages,
  extension values, IDs, arbitrary paths or HTTP bodies.
* `envelope=exact|extra_keys|invalid`, `zones=zero|one|multiple|invalid`.
* Per source-owned alias: `rows=zero|one|multiple|full|invalid`,
  `datetime=utc_in_window|utc_outside_window|string_other|null|mixed|invalid`,
  `status=string|null|mixed|invalid`. A `full` list is incomplete evidence.

An implementation should validate duplicate keys and bound arrays/string
lengths before classification; unknown values yield a fixed invalid bin, never
interpolated output. Unknown extra envelope keys can be classified as
`extra_keys` without printing their names or accepting their semantics.
All labels are diagnostics only: none authorizes send, registration, deployment,
object access or relaxation of the original fail-closed delivery classifier.

## Decision tree after that one result

1. Baseline GraphQL errors or unavailable/null datasets: richer-field parsing
   is not yet the demonstrated cause. Resolve baseline availability through a
   separately scoped schema/settings investigation; do not resend mail.
2. Baseline accepted but envelope has extra keys/empty errors: the previous
   envelope policy is a concrete compatibility candidate, not proof of the
   original response. Add synthetic coverage before changing policy; never
   accept nonempty GraphQL errors as complete history.
3. Baseline accepted with null/unusual timestamps/status: all-row assumptions
   are an actionable candidate. Any future policy must skip only safely
   nonidentifiable rows and preserve uniqueness, full-page, exact identity and
   sampled-absence constraints. Do not normalize arbitrary dates or null fields
   into apparent matches.
4. Baseline entirely normal: original optional fields, richer row identity,
   terminal-flag representation or transient response remain unresolved.
   Consider a **separate**, narrowly targeted introspection design before a
   second historical event read; do not automatically retry the old query.

Even a clean baseline is not retrospective proof that the first response had
that shape. Adaptive event absence remains inconclusive and B remains NO-GO.

## Source implementation (not yet hosted or queried)

`infra/tests/staging_worker_r2_history_shape.py` implements the reduced query
and imports the original immutable `historical_window()`, no-redirect opener,
UTC parser, duplicate-key rejection and body limits without altering the original
classifier. Its explicit confirmation is
`READ_WORKER_R2_HISTORY_BASELINE_SHAPE_36751791789`; the second CLI argument must
be the fixed original run. Only Analytics and GitHub read credentials are read.
No workflow change or live authorization is included in this source work.

Output starts with
`worker_r2_history_shape=SHAPE_DIAGNOSED delivery=UNVERIFIED`, followed by fixed
fields in fixed order. Exit zero means the bounded object was classified, **not**
that GraphQL succeeded, history is complete, or mail was delivered. Transport,
HTTP, oversized-body and malformed/duplicate-JSON failures instead use the
existing closed `UNVERIFIED reason=provider|schema|...` categories; the more
granular proposed response bins were deliberately not implemented because they
are unnecessary for the first compatibility decision. `envelope` describes
only top-level keys, not a nested-key whitelist. `no_rows` explicitly distinguishes
an empty dataset from a known scalar representation; `full` remains incomplete.

Synthetic tests cover empty/normal/null/mixed/invalid/full rows, GraphQL errors
without raw message output, envelope variants, one distinct content-minimized
request with the same time bounds/body cap, duplicate/oversized JSON, exact
confirmation/run gating and private-error suppression. They were authored and
statically inspected, **not executed locally**. Root must obtain independent
review and hosted source checks, then separately wire the manual branch-pinned,
first-attempt-only, staging-gated read target before considering its one request.

This implementation cannot recover the rejected original condition: it can
only separate a currently rejected baseline from baseline compatibility. If it
returns normal bins, do not add automated retries or infer that the original
optional fields were the cause. The next narrower investigation remains an
explicit decision rather than another query hidden in this helper.
