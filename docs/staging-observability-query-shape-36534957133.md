# Retained-event query shape after staging read-only diagnostic 36534957133

Status: **UNVERIFIED** (2026-09-29). This note records fixed stage outcomes and source/API contracts only. No retained record, request identifier, address, credential, provider text, or user request content is copied here. The investigation made no mail, routing, deployment, or database mutation.

## Observation and narrow interpretation

The explicit hosted read-only address diagnostic for the earlier address-add incident passed deployed-privacy and Observability-key preflight, then returned `staging_address_incident: UNVERIFIED (observability_events_malformed)`. Source inspection places this label after the dry query HTTP response was parsed as JSON with `success=true`, but before any page could be accepted. It **does not** establish whether the event view was absent, malformed, still running, empty, sampled out, or otherwise different from the parser's expected shape. In particular, neither preflight nor this fixed label proves that no logs were retained or that the privacy canary passed.

Cloudflare's [telemetry query API](https://developers.cloudflare.com/api/resources/workers/subresources/observability/subresources/telemetry/methods/query/) specifies an `events` view under `parameters.view`; its response schema marks `result.events` optional even for that view, with optional `count` and `events` inside the container. The same schema exposes a query-run status (`STARTED` or `COMPLETED`) and the request's `dry` property. A missing view field is therefore not automatically a malformed HTTP response, but it is also **not an explicit zero-event result**. The indexed service key was present during preflight; that checks filter syntax availability, not whether this Worker had retained events in the selected window.

The parser now distinguishes:

| Bounded query shape | Fixed outcome | What it does **not** imply |
| --- | --- | --- |
| Run explicitly `STARTED` | `observability_query_incomplete` | No absence or privacy proof |
| Missing `result.events` | `observability_events_view_absent` | No claim of zero events |
| Present container with `count=0` and `events=[]` | Accepted as an empty page; downstream canary/incident remains `UNVERIFIED` for missing causal evidence | No privacy pass |
| Missing/invalid count, invalid list, or partial page | Existing count/shape/page failure | No completeness proof |
| Echoed non-dry, non-events view, wrong timeframe, or wrong service filter | `observability_query_echo_unverified` | No acceptance of a different query |

The query parser checks the documented `run` object, completion, dry flag, exact requested timeframe, and the echoed events-view/service filter. It does **not** compare `run.query.parameters.limit` to the top-level request limit: those are distinct API fields with different bounds. Instead, each returned page is capped at the requested 200 rows, and the total-count/cursor logic still rejects incomplete pages. The child full-canary process still never prints records. Its hosted wrapper now forwards only an exact, reviewed fixed query code from suppressed child output; all other output maps to `retained_canary_unverified`. This preserves a primary diagnostic even if cleanup also fails, without forwarding arbitrary child text.

## Validation and next read-only discriminator

The incident diagnostic now first calls Cloudflare's read-only [telemetry values API](https://developers.cloudflare.com/api/resources/workers/subresources/observability/subresources/telemetry/methods/values/) for `$metadata.service`, using **the same 33-second incident window** and an exact filter for the expected staging service. It accepts only the expected typed membership row in memory, emits only `service_value_present`, `service_value_absent`, or `service_value_unverified`, and skips the event query unless present. An API failure retains its existing fixed error code beside `service_value_unverified`. Even `service_value_absent` remains **UNVERIFIED**: it could reflect retention, sampling, or provider behavior rather than no Worker request.

Synthetic offline unit tests cover the explicit empty container, absent view, missing run, unfinished/unknown status, missing count, contradictory dry/view echo, and exact child-code forwarding alongside cleanup failure. On Windows with `PYTHONDONTWRITEBYTECODE=1`, `python -m unittest infra.tests.test_staging_trace_canary infra.tests.test_staging_address_failure_logs infra.tests.test_staging_hosted_trace_canary -q` completed **36 tests, all passing** before the additional values-gate and echo refinements; those refinements require hosted verification. No live query was rerun for this source change, so the **actual** shape that triggered run 36534957133 remains unknown. The Worker service name in the staging configuration matches the hardcoded filter, but that is source configuration, not a retained-event count.

The shortest next operator probe is the same reviewed **read-only** incident diagnostic once this source reaches its explicit hosted target. Its values gate reports one fixed membership state, then (only if present) its dry events query reports a bounded fixed shape/causal outcome. Pair it with a second exact known-request window from the earlier full canary only if necessary; do not broaden across unrelated traffic. Do not print raw JSON, field values other than reviewed fixed labels, or cursor IDs. If the query returns an explicit empty view, retain **UNVERIFIED** and investigate sampling/retention or filter mismatch privately. Do not create another address or send mail to manufacture evidence.
