# Same-window retained-marker second discriminator

Status: **historical read completed; request-context carriers located; privacy
acceptance remains unverified**. This document records the fixed hosted result,
not raw telemetry. The read created no traffic or configuration change.

Maintenance update (2026-10-01): the completed fixed-window dispatch target and
job are retired from current `ci.yml`. The classifier and synthetic tests remain;
the execution-gate section below describes historical source, not a current
invocation. See [current operational lanes](maintenance-operational-lanes.md).

## Motivation and immutable scope

Historical read-only run `36713163067`, workflow source SHA `17abe25`, returned
`carrier=other_or_multiple type=other_or_mixed component=path_only records=1`.
One matched record means its type is absent, malformed, or unknown, not that
several row types were mixed. Its carrier may be one unknown leaf or multiple
categories inside that single row. These alternatives change the next action:
platform enrichment requires sink containment, while source payload retention
requires tracing the application serialization path. The second result below
now supports the containment branch, without proving a specific producer.

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

## Live result and bounded decision (2026-09-30)

[Hosted run `36723490687`](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36723490687)
at classifier source `d8b9631` queried only the unchanged historical window and
returned:

```text
carrier=metadata_context+workers_event_request carriers=2_plus leaves=2_plus metadata_type=unrecognized wrapper_type=wrapper_absent trigger=fetch source_shape=allowlisted_application component=path_only records=1
```

One matching record has at least two matching string leaves across exactly two
declared categories: indexed context (`trigger`, `spanName` or
`transactionName`) and the Worker request envelope. Its source validated as a
reviewed application event and was not a marker carrier. This is consistent
with request-context enrichment, not a leak in the inspected application event.
However, the indexed type is an **unrecognized string**, not absent/malformed,
and the exact wrapper is absent; neither custom-log nor invocation-log type is
established. `fetch` describes eventType, not the logger. No raw type string,
leaf name, value, marker suffix or identifier was exported.

This scoped result supports a **reviewed staging Queue-only logging sink
experiment**, not an attribution claim or a whole-system privacy pass. It cannot
attest unqueried records, body/attachment/header or exception paths, global query
redaction, or exact correlation to the discarded original request ID. Keep the
privacy gate closed. Do not repeat/widen the historical query or retain unsafe
source logs in parallel for comparison. See the [bounded mechanism and selected
next branch](mail-trace-sink-remediation-options.md#second-historical-result-request-context-retention-located)
and the [superseding privacy decision](mail-trace-privacy-decision.md).

## Execution gates and historical next-decision table

The retired `ci.yml` target `staging-trace-marker-discriminator` required exact
`READ_STAGING_TRACE_MARKER_DISCRIMINATOR` confirmation and the project branch.
It uses staging Environment, read-only repository permission, five-minute
timeout, non-cancelling dedicated concurrency, and final-step-only repository
secrets. First obtain independent source review and hosted synthetic CI at the
reviewed SHA. Those prerequisites preceded the completed read above; they do
not authorize another dispatch. No broadened search is authorized on failure.

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
