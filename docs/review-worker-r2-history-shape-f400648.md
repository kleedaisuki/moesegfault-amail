# Reduced Worker-R2 historical schema discriminator review

Reviewed 2026-10-01 at `f40064842f4b429aca194b56868e45f0ade57845`.
Scope: `staging_worker_r2_history_shape.py`, its synthetic tests, the design
record, and imported original provenance/transport contracts. The unrelated
uncommitted `ci.yml` change was not reviewed or included. No local tests,
private/live queries, sends, route/R2 operations or production edits were made.

## Decision

**GO for nondeploying hosted source checks. No substantive defect found.**
This is source review only, not authorization for a live read or acceptance of
mail delivery, R2 capability, B registration, capture containment or release.
Manual hosted wiring must receive a separate review before a new query.

## Evidence and contract trace

| Boundary | Executable evidence | Assessment |
| --- | --- | --- |
| Original experiment | `run()` and imported `historical_window()` | Requires the new exact confirmation, original run `36751791789`, repository identity and authenticated original failed attempt/job/step provenance, original SHA and workflow. Derives the identical bounded historical interval rather than a new current-time interval. |
| Reduced read | `QUERY`, `fetch()` | Two original zone-level datasets, only `datetime status`, each limit 100; no sender, recipient, subject, message/rule ID, terminal flag or provider error detail is selected. Exactly one GraphQL POST; imported no-redirect opener, 20-second socket timeout and 128 KiB response cap remain. |
| Envelope and errors | `diagnose()`, `error_bins()` | Describes extra top-level keys without printing their names. Null/absent, empty, nonempty and malformed error collections are distinct. Error scope uses exact canonical alias positions, not message/extension substring inspection. Partial GraphQL data does not erase the error bin or become a delivery claim. |
| Row/type bins | `row_bins()`, `date_bin()`, `group()` | Lists are bounded; selected row keys must match; nulls, unsupported scalars, timestamps outside the immutable interval, empty datasets and full pages remain distinct fixed observations. Mixed includes mixtures with invalid values and is not acceptance. |
| Privacy | `main()`, closed `FIELDS` and `BINS` | Only source-owned fixed labels can leave the process. Provider status/timestamp values and error messages/extensions stay in memory. Duplicate JSON keys and oversized/malformed responses fail closed; unexpected exceptions print no traceback or value. |
| No delivery inference | `main()`, design decision tree | Every classified result explicitly carries `delivery=UNVERIFIED`, including zero rows, complete-looking rows, errors and full pages. Exit zero means diagnostic classification only. Neither baseline compatibility nor incompatibility reconstructs the rejected original response. |

## Official schema comparison

Cloudflare's [Email metrics reference](https://developers.cloudflare.com/email-service/observability/metrics-analytics/)
(consulted October 1, 2026) documents the two zone-level individual-event
datasets, Analytics Read access, 31-day retention, `datetime`/`status`, and
`Time!` event filters. The reduced selection and variable/filter syntax are
consistent with its event examples. The reference does not guarantee non-null
scalars, strict envelope shape or a particular private token's dataset access;
therefore these remain diagnostic bins rather than undocumented assumptions.

The original `reason=schema` at reported run `36756920203` combines JSON,
envelope, GraphQL and richer-row failures. This query materially reduces the
selection without pretending to identify that past failure. In particular,
clean baseline bins do not demonstrate a richer-field defect, and Adaptive
absence remains inconclusive. No new provider read was made during review.

## Synthetic tests and limits

Statically examined fixtures cover empty/normal/null/mixed/invalid/full rows,
extra envelope keys, missing/null/multiple zones, GraphQL error alias bins,
one reduced request with exact variables and bounded read, duplicate/oversized
JSON, confirmation/run gating, and closed success/unexpected-exception output.
Tests reuse the imported original provenance mechanism rather than recreating
its assumptions; original provenance coverage remains necessary in hosted CI.
Fixtures are not evidence of the actual historical response or live schema.

The helper alone does not enforce a hosted first-attempt gate or overall job
wall-clock deadline. Those are expressly deferred to separately reviewed manual
wiring. A socket timeout is not a total trickling-response deadline. This is not
a source defect within the stated scope, but that wiring is a prerequisite to
considering one bounded read. No live result or hosted test pass is attested.
