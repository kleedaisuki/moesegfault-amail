# Second hosted staging address-add failure: bounded retained-log diagnosis

Status: **source and Actions-log analysis complete; historical retained-event query not yet run** (2026-09-29). The investigation performed no address, routing, mail, deployment, or database mutation. The original address and all credentials remain private. See [the first incident](staging-address-add-incident-36524101354.md) for provider API and cleanup background.

## Observed boundary and what it does not prove

The [hosted run 36533465672](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36533465672), at source `565fa2996752b9cbdaf68920a3312d4185b32d01`, built the CLI and ran the staging acceptance step from 06:55:31 to 06:56:02 UTC. Native PKCE login and mail authorization passed. The harness emitted only `staging_hosted_e2e_failed:mail_address_register_failed` followed by `address_route_retired`. This shows the run's cleanup readback found no route and no CLI-visible owned address at its deadline; it does **not** establish the original add response, whether the provider POST occurred, or the final D1 state. The harness uses `AMAIL_TELEMETRY=off` and deletes its run directory, so this job retained neither CLI stderr nor its local operation journal.

The new `cli_failure` parser at that revision would expose a *known* outer HTTP status/public code, but its allowlist omitted `service_unavailable`. In `mail-worker/src/lib.rs`, any `worker::Error` from `platform::rules_for_address` maps to HTTP 503 `service_unavailable`, whereas a typed `create_rule` provider failure maps to 503 `routing_unavailable` or 409 `capacity_exhausted`. Thus a **pre-POST Routing Rules list failure** is a concrete alternative explanation for the bare label. The successful preflight `assert_route` used the harness's GitHub routing token, while the Worker uses its deployed secret; success of one does not validate the other. Other possibilities are CLI transport/non-HTTP failure, a code outside the harness allowlist, or a failure after a successful provider operation. The bare label alone cannot rank them reliably.

The separate [trace preflight run 36533828217](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36533828217) passed at the same source revision: effective deployed privacy settings and the `$metadata.service` Observability key were verified. It did **not** call the retained-event query endpoint, inspect an event, or prove that the historic incident event was sampled or retained. A 403, missing record, ambiguous same-window add, or incomplete page must remain **UNVERIFIED**.

## Restricted read-only method

`infra/tests/staging_address_failure_logs.py` has a hardcoded 06:55:30–06:56:03 UTC window and staging service filter. Its manual `staging-routing-diagnostic` CI target requires the exact `READ_STAGING_ADDRESS_INCIDENT_36533465672` confirmation. It first repeats the deployed-privacy and Observability-key preflight, then uses a dry, cursor-complete query with the existing 1600-event cap. It neither constructs nor calls a mail API URL and never calls a routing-rule write endpoint. All returned records stay in memory; the script rejects unreviewed custom `source`/message payloads, extracts only schema-checked application events, and requires exactly one failed `addresses_add` request-exit plus causally linked `routing_list` and optional `routing_create` phase. It outputs only a fixed classification and bounded numeric HTTP/error facts. No raw event, address, URL, token, request ID, provider text, screenshot, or artifact is emitted.

Cloudflare's [query API](https://developers.cloudflare.com/api/resources/workers/subresources/observability/subresources/telemetry/methods/query/) documents `dry=true` as execution without persisting results and the event cursor; its [Workers Logs limits](https://developers.cloudflare.com/workers/observability/logs/workers-logs/) specify at most seven days of paid-plan retention and possible sampling after account limits. Consequently a missing result cannot be promoted to a finding about whether the Worker executed a phase.

The observations discriminate these cases:

| Reviewed event result | Supported conclusion | Limit |
| --- | --- | --- |
| One failed `routing_list`; no `routing_create` | Worker failed before the create call | Phase loss is still possible in general; this requires the linked list event |
| Successful list, failed create, numeric provider status/code | Provider POST boundary was reached; status/code narrow permission vs validation vs provider incident | A numeric Cloudflare code needs its documented meaning checked privately; no provider text is exposed |
| Successful list, no create event | Create **not observed** | Could reflect reuse of an existing rule or a missing event; not proof of no POST |
| Successful create, failed request exit | Failure happened after a reported provider success | Requires private exact route/D1 reconciliation before any new attempt |
| Missing, duplicate, malformed, unreviewed or truncated evidence | `UNVERIFIED` | Never infer a cause from absence alone |

No manual diagnostic has been dispatched. The root operator will review the workflow and script before any dispatch; **do not rerun hosted address creation** to fill this evidence gap. If retained evidence is unavailable, inspect the deployed Worker token's zone-scoped Rules Read/Write policy privately and report the incident as indeterminate. The source-only harness correction adds `service_unavailable` to the safe public-code allowlist for a future authorized attempt; it is **not** evidence that this historic failure had that code or a fix to the underlying routing failure.
