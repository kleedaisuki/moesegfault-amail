# Same-window retained-marker second discriminator

Status: source prepared for independent review and hosted synthetic CI only.
No local tests, live query, new request, or configuration change was performed.

## Motivation and immutable scope

Historical read-only run `36713163067`, deployed SHA `17abe25`, returned
`carrier=other_or_multiple type=other_or_mixed component=path_only records=1`.
One matched record means its type is absent, malformed, or unknown, not that
several row types were mixed. Its carrier may be one unknown leaf or multiple
categories inside that single row. These alternatives change the next action:
platform enrichment requires sink containment, while source payload retention
requires tracing the application serialization path. Neither is established yet.

`infra/tests/staging_trace_marker_discriminator.py` reuses the original
preflight and complete dry cursor/count/ID validation. It queries only the
same service and **2026-09-30 10:42:00–10:42:37 UTC** window. The original
classifier first validates every row's scope, envelope, truncation and marker
suffix consistency. The follow-up also rejects malformed Cloudflare wrappers
and truncated/malformed wrapped Workers envelopes, including unrelated rows.
There is no selectable service/window, new HTTP probe, login, mail, or artifact.

## Fixed output contract

| Field | Fixed bins and meaning |
|---|---|
| `carrier` | Sorted `+`-joined set of `metadata_url`, `metadata_context`, `metadata_message`, `metadata_error`, `metadata_other`, `workers_event_request`, `workers_event_other`, `workers_diagnostic_channel`, `workers_other`, `source`, `top_level_other`; exact one `$cloudflare` wrapper uses the same bins prefixed `cloudflare_` |
| `carriers` | `1` or `2_plus` distinct structural categories |
| `leaves` | `1` or `2_plus` matching leaf occurrences; separate array elements count separately, repeated marker text in one string counts once |
| `metadata_type` | `absent`, `malformed`, `unrecognized`, `cf_worker_event`, `cf_worker_log`, `mixed` for top-level indexed type |
| `wrapper_type` | Same bins for exact wrapped metadata, plus `wrapper_absent` |
| `trigger` | Exact top-level Workers eventType mapped to `fetch`, `email`, `scheduled`, `queue`, `alarm`, `rpc`, `websocket`, or `absent`, `malformed`, `unrecognized`, `mixed` |
| `source_shape` | `allowlisted_application`, `unallowlisted_application`, `not_application_schema`, `mixed`; only existing reviewed source decoder/validator is used |
| `component`, `records` | Original validated path/query and record-count bins |

Metadata context means only trigger/spanName/transactionName; message includes
messageTemplate; error includes errorTemplate. Unknown keys never appear in
output. Nested Cloudflare wrappers do not create recursively expanding bins.
All unknown type/eventType values map to fixed bins, never copied values.
Source shape is an independent hint: an allowlisted source does not exonerate
another retained error/context field. Indexed type is not emitter identity.
No category can itself prove which logger produced the row or reverse the
existing privacy failure. A zero, malformed, expired, or incomplete query
remains `UNVERIFIED`, not a privacy pass.

## Execution gates and useful next decisions

The manual `ci.yml` target `staging-trace-marker-discriminator` requires exact
`READ_STAGING_TRACE_MARKER_DISCRIMINATOR` confirmation and the project branch.
It uses staging Environment, read-only repository permission, five-minute
timeout, non-cancelling dedicated concurrency, and final-step-only repository
secrets. First obtain independent source review and hosted synthetic CI at the
reviewed SHA. Only then consider one read-only dispatch; do not push/deploy
during root's pinned live E2E. No broadened search is authorized on failure.

| Observation | Next investigation, not conclusion |
|---|---|
| One `top_level_other` leaf | Unknown envelope remains unresolved; do not claim multiple carriers |
| Exact wrapped metadata/context with allowlisted source | Evaluate platform enrichment containment; compare effective sink behavior using synthetic traffic after a separately reviewed change |
| Source or error carrier | Trace the producer/serializer path; do not blame invocation logging solely from row type |
| Several carriers | Consider all returned fixed categories; do not select a favorite or infer separate failures |

The official [Cloudflare telemetry query schema](https://developers.cloudflare.com/api/resources/workers/subresources/observability/subresources/telemetry/methods/query/)
documents events, metadata, optional indexed type and Workers envelope fields.
It does not guarantee that row classification identifies the emitter. Existing
privacy research and sink alternatives are recorded in
`mail-trace-privacy-decision.md` and `mail-trace-sink-remediation-options.md`.
