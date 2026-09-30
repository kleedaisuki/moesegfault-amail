# Routing create diagnostics review (2026-09-29)

Scope: commit `90ce360` only, read against `docs/staging-address-add-incident-36524101354.md`, `docs/mail-trace-privacy-decision.md`, address provisioning/reconciliation, and the existing trace schema. Static review only; no provider mutation, deployment, or heavy local test was performed.

## Assessment

No blocking correctness or compatibility defect found. The create-rule result now retains only numeric HTTP status and the first parseable Cloudflare error code (at least 1000), while discarding the raw body and message from returned errors and retained trace records. The old public capacity-text heuristic remains confined to non-200/201 responses, preserving the established `409 capacity_exhausted` versus `503 routing_unavailable` mapping. Other uncertain results remain `503 routing_unavailable`. The list phase is emitted before return, and a create phase is emitted only if no existing rule was found; this distinguishes pre-POST failures from POST failures without exposing the address. A failed or uncertain create leaves the row in `provisioning`; the existing scheduled reconciler checks exact provider rules and either activates a found rule or eventually returns a ruleless row to `pending`. The change does not remove that recovery path.

The new unit tests cover the classifier, public mapping, and JSON trace allowlist. They do not establish the actual Cloudflare response code or prove that retained Workers Logs index these JSON strings in deployment. Do not treat this static review as a live diagnosis of run 36524101354 or as authorization for another address-add attempt.

## Operational interpretation

`routing_create` with `outcome=phase_failure` and `provider_http_status=200` is possible when Cloudflare returns HTTP 200 with `success=false`; the numeric field is an HTTP fact, not an assertion that provisioning succeeded. Absence of `provider_http_status` means request construction/send/read failed before a usable response, not proof that Cloudflare saw no POST. A failed `routing_list` and no `routing_create` event identifies the earlier boundary. Sampling/retention can still make an absent event inconclusive.

## Existing limitations outside this change

The capacity classification is still a heuristic over provider text, so a non-capacity provider error mentioning `limit`, `maximum`, or `quota` may map to 409. This was pre-existing behavior and should be replaced only when a documented provider capacity code is available. On a permanent provider denial, the row cycles through provisioning and later pending; this too predates the diagnostic change and does not alter the public contract here.
