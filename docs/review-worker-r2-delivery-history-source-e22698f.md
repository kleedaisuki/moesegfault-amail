# Historical Worker-created R2 delivery discriminator source review

Reviewed 2026-10-01 at `e22698f`. Scope: new historical classifier, synthetic
tests, manual job and runbook changes; surrounding immutable GitHub reader,
marker derivation and original probe; earlier interpretation review
`review-worker-r2-delivery-history-42fdd05.md`. No local tests/builds, private
queries, workflow dispatch, source edits or push were performed.

## Decision

**GO for nondeploying hosted source checks. No substantive defect found in
the reviewed read-only implementation.** A single historical read can proceed
only after those checks pass at the reviewed source revision and the owner
confirms the intended pinned diagnostic. This is not permission for resend,
route opening, R2 operations, B registration or production rollout.

## Contract trace

| Boundary | Reviewed executable evidence | Assessment |
| --- | --- | --- |
| Immutable experiment | Classifier constants and `historical_window()` | Pins run `36751791789`, first attempt, 40-hex original source, branch, exact workflow, completed failed run/job and uniquely named failed probe step; authenticates GitHub metadata and rejects incomplete jobs pagination. |
| Explicit finite time scope | `historical_window()` | Requires ordered run/job/step timestamps and positive step duration at most 20 minutes; query covers step minus two minutes through step plus ten minutes. This is wider than actual send time, but bounded and tied to immutable execution, not guessed timestamps. Outside-window outcomes remain unverified. |
| Read-only provider path | `fetch()`, imported `github_json()` | Only bounded GitHub metadata GETs and one GraphQL POST query. No routing/sending/R2 mutation helpers called. Separate no-redirect openers prevent bearer forwarding. Body limits and socket timeouts exist; job timeout bounds hosted lifetime, not each trickling read's total duration. |
| Exact candidate identity | `scoped()` | Exact derived subject, exact normalized sender/recipient, bounded UTC timestamps and expected selected-field shape; no prefix/fuzzy subject join. Display-name address formats will safely fail to match rather than broaden scope. |
| Positive join only | `classify()` | Requires one nonempty Sending message ID; Routing correlation requires every matched Routing ID equal that ID. Reports only correlation and explicitly leaves intended Worker/R2 unverified. No `handled`/rule UUID target inference remains. |
| Lifecycle ambiguity | `classify()` | Multiple Sending rows need one terminal row, one provider ID and no row later than the terminal timestamp. Duplicate terminal markers, multiple IDs or missing required terminal state remain inconclusive; matched-row cardinality is not declared a send count. |
| Sampled absence and truncation | `events()`, `classify()` | Full event lists at limit 100 reject before selection; zero Sending rows are inconclusive. No missing Routing row becomes a claim that Routing did not occur. One short page is used only for positive observations, not lossless absence proof. |
| Privacy | Query fields, exception paths, `main()` | Does not select MIME or `errorDetail`; no raw persistence or provider-event output. JSON duplicate keys, errors, oversized bodies, exceptions and unknown failures yield fixed labels; output includes only source-owned result/reason and zero/one/multiple matched-row cardinalities. |
| Hosted wiring | `.github/workflows/ci.yml:252-288` | Manual-only exact target, reviewed branch, staging Environment, fixed confirmation, five-minute timeout, Actions/contents read; Python tests precede sole Analytics-secret-bearing step. Does not pass send/routing/R2 secrets. Adds a target choice but no top-level input, preserving the 23-input contract. |

## External semantics and limits

Official [Email metrics](https://developers.cloudflare.com/email-service/observability/metrics-analytics/)
documents the selected zone-level individual datasets and identity fields,
Analytics Read and 31-day retention. GraphQL field access/permission and actual
response shape remain runtime facts: source fails closed on unavailable fields
or errors rather than printing them. No private schema was introspected here.

[Email logs](https://developers.cloudflare.com/email-service/observability/logs/)
describes Sent as accepted/queued, Delivered as recipient-server acceptance,
Rejected and Failed as sending failures, and maps Delivery failed to
`deliveryFailed`. The narrow progress/failure labels therefore have appropriate
scope: neither is an end-to-end Worker/R2 assertion. Unknown status values fall
back to a status-unverified observation. The specific positive failure cause
`routing_unknown_address` is exact-allowlisted and only used with terminal
`deliveryFailed`; no inference by analogy with another experiment is made.

[Sampling](https://developers.cloudflare.com/analytics/graphql-api/sampling/)
explains Adaptive datasets can be sampled. The code's absence handling is
appropriately weaker than a delivery-negative assertion. Selected timestamp
ordering and finite limits do not give a lossless history cursor; full-page
rejection avoids silently treating truncation as unique evidence.

A shared message ID plus exact synthetic identity/time is a positive
correlation, not a documented universal cross-dataset join or intended-rule
attestation. The current result name and runbook preserve that distinction.

## Test assessment and unverified scope

Synthetic tests exercise positive terminal unknown-address evidence, narrow
correlation, missing/unjoined IDs, exact subject/recipient matching, lifecycle
ambiguity, full-page rejection, time bounds, no private output under unexpected
exceptions, GitHub step provenance and tests-before-secret manual wiring.
The fixtures are not proof of live provider schema/status representation or
actual run metadata. Additional negative provenance/response-shape tests could
strengthen regression coverage but no concrete failure requiring them was
identified in this review.

No live result is attested. In particular, this review does not prove current
Analytics grants, historic row retention, source checks passing, mail acceptance,
Worker invocation, object persistence, perpetual absence, or GET/DELETE
capability. Existing B NO-GO and no-auto-resend boundaries remain unchanged.
