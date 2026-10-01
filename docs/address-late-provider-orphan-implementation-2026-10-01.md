# Bounded late-provider orphan convergence: implementation contract

Date: 2026-10-01. Base source: `68769bf0bcb41528e9e0437c57222c665b12091e`.
Status: implemented source and hosted fixtures; static checks only. **Not yet independently reviewed, compiled, tested, deployed, or authorization for provider mutation.**

## Change and invariant

A provider POST may become visible after the permanent address is retired and its repair marker is cleared; its original invocation need not resume. Scheduled address maintenance therefore inventories actual provider objects even with no due D1 records. Up to five hundred provider name-derived keys are point-read through at most ten fifty-key `IN` batches. Strict retired lifetimes are conditionally rearmed only when `needs_reconcile=0`; already flagged due times are preserved. Unknown lifetimes and scope conflicts are retained anomalies, not garbage. No all-tombstone scan, TTL, new schema, endpoint, address state, issuer/subject transfer, or CLI change is introduced.

The original due rows are claimed/rotated before provider I/O, so a failed list cannot pin the first batch indefinitely. After discovery, available batch slots claim newly due records. At most thirty rows are claimed per tick. One row failure does not suppress later state-only repairs. The existing conditional state machine preserves active committed routes, enabled-only activation, immutable retirement, and pending repair rather than deletion.

## Executable boundaries

| Boundary | Source contract |
| --- | --- |
| Inventory | At most ten pages at fifty rules, five hundred unique path-safe IDs |
| Completeness | HTTP 200, `success=true`, typed result, coherent optional page/count/total metadata, actual terminal page; short intermediate or ten full pages without terminal metadata are incomplete |
| Body | Incremental read bounded to 256 KiB per list/get/create/delete response, including chunked responses without Content-Length |
| Address egress | Twenty shared calls per scheduled/address-delete invocation, debited before submission; no redirects followed |
| Destruction | GET+DELETE pair admission; current full rule scope then current permanent D1 state before DELETE |
| Scope | Exact name `amail {address}`, explicit source `api`, one exact literal-to matcher, one Worker action with one pinned ingress value |
| Saved ID | Evidence to validate against complete inventory, not a capability or unconditional append |
| Failed provider response | HTTP 200+`success=false` or malformed body never confirms removal |
| Known-ID absence | Scoped GET HTTP 404 confirms no target to delete; DELETE 204/404 is accepted absence under the existing known-resource contract |
| Provisioning absence | Keep existing ten-minute age/state gate and perform a **fresh complete** recheck; reserve its worst-case ten list calls from the same twenty-call budget before I/O |
| Budget exhaustion | Preserve unfinished marker/state; request-path accepted partial retirement returns existing 202; ordinary provider/scope failures retain existing 503 vocabulary |
| Telemetry | Existing fixed routing diagnostic only; no provider body, addresses, rule IDs, issuer/subject, tokens or mail text |

A full ten-page inventory leaves at most five GET+DELETE pairs. A one-page inventory permits at most nine pairs. Fresh absence rechecks reduce that allowance; they are not extra calls. This is an external-exchange bound, not a bound on all scheduled D1 statements. The existing twenty-item embedding phase yields a modeled forty external calls excluding its redirect behavior and any other newly added egress. The account plan and full scheduled D1 admission still require independent hosted/deployed evidence; this patch does **not** declare Workers Free safe.

## Safety assumptions and rollout gates

`source=api` includes Dashboard/API/Terraform; it does not authenticate the creator. The exact managed-name namespace for permanently allocated Mail lifetimes must be exclusively administered by Mail, and other actors must not repurpose its IDs. Without that operational precondition, do not enable this automatic destructive source; use detection/rearm/alert and authenticated baseline review. A scoped GET narrows but cannot fence a foreign edit before ID-addressed DELETE. No advertised provider content If-Match, atomic list snapshot, immutable-ID lifetime proof, create idempotency key or delayed-POST deadline was established.

Repeated provider-positive discovery closes the **retired** late-effect leak assuming eventually stable provider rules, continued scheduling, finite admitted inventory, exclusive management and eventual D1/provider success. Clearing a marker establishes point-in-time cleanup only, not historical producer quiescence, future absence or a five-minute/24-hour SLA. The independent late-route-on-clean-pending race is not claimed solved. Optional creator rearm was not added: correctness must remain independent of the creator continuation.

Existing privacy/Issues, source/version/bindings, public-send hold, recovery-owner/retained-escrow, account-plan and campaign terminal-evidence gates remain unchanged. No live provider call or mutation was performed. Old in-flight exact legacy POSTs are discoverable by the new inventory; their old unsafe destructive code does not retroactively change. Rollback restores the earlier liveness gap and cannot authorize dropping recovery evidence.

## Hosted verification to run, not results

`infra/tests/worker-boundary/address-add.test.mjs` uses the production Rust/Wasm through workerd/Miniflare, real conditional D1, persistent synthetic provider rules, explicit Promise barriers and denied unmatched egress. Fixtures include:

- Late POST commits after two independent retire/clear ticks while creator response remains blocked; a third zero-due tick must discover/remove it without another POST or creator rearm.
- Zero due rows; one thousand clean historical tombstones; disabled/unknown-enabled strict retired routes; unknown lifetimes/other realms/apex operators preserved.
- Single-purpose scope, saved-ID repurposing, changed scoped GET, uncertain GET/DELETE envelopes and D1 state changing to committed active during GET.
- 50/51/404/500/501 inventory edges, malformed and later-page failures, duplicate IDs, short intermediate pages, ten full pages without terminal metadata, oversized streamed body.
- Forty due lifetimes: every eligible route eventually obtains a turn while every full scheduled call stays within twenty address exchanges and incomplete markers persist.
- Aged provisioning initial snapshot empty but fresh recheck sees a disabled route: preserve provisioning.
- Request-path bounded partial retirement and scope conflict preserve intent without foreign deletion.

The barrier fixture does not kill an isolate; the creator cannot run its post-provider continuation during the acceptance tick. Actual killed-invocation behavior and deployed provenance remain separate evidence.

Only Rust formatting, JavaScript syntax checking and Git whitespace checking were run locally. **No local project test/build, provider call, push or deployment.** Hosted exact-head Rust/Wasm and workerd results must be appended after independent review, not inferred from source/fixtures.

## External sources

Retrieved official docs on 2026-10-01: [Rules list](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/list/), [Rules get](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/get/), [Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/), [workers-rs Response v0.8.3](https://github.com/cloudflare/workers-rs/blob/v0.8.3/worker/src/response.rs). The implementation follows bounded streamed reads and uses direct D1 bindings; Email Routing Rules require the documented external API because no equivalent Worker binding is available here. The reviewed design relates continuous actual/desired-state repair to [Kubernetes controllers](https://kubernetes.io/docs/concepts/architecture/controller/) and the safety/liveness distinction in [Anvil, OSDI 2024](https://www.usenix.org/conference/osdi24/presentation/sun-xudong); none verifies this code or the provider contract.
