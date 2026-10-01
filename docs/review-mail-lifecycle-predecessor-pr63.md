# Independent review: lifecycle predecessor source guard (PR 63)

Reviewed exact head `1c21f7d5f65bf75578f2c1f45479107b3374a927` (implementation153abea on accepted55 source), in `.temp/mail-lifecycle-predecessor`, 2026-10-01. Scope: receipt loader/validation, preflight/recovery guard, existing pure transition model and full graph reader, hosted synthetic tests, design completion path and deterministic tamper-fixture repair. Source-only: no provider operations, local runtime tests/builds, secrets reads, deployment, production edits or merge.

## Verdict

**No demonstrated substantive blocker found for the stated partial source-only slice.** The implementation is intentionally non-admitting for activation/replacement/rollback, and does not export a provider writer. It is not yet an executable lifecycle and cannot produce/admit a real receipt today because the fixed protected producer does not exist.

| Boundary | Assessment |
| --- | --- |
| Fixed origin | Exact repository/main/manual/first-attempt successful run, fixed workflow path and one successful realm job; bounded complete job/artifact inventories and unique live fixed-name artifact ID. Arbitrary bootstrap/PR/inspection runs cannot qualify. Protection itself depends on the future reviewed producer/environment implementation, not the mere job name. |
| Artifact/parser | Download bound, one exact regular receipt.json ZIP member, expanded bound, duplicate JSON keys refused and closed schema. Source/run/attempt/state/realm pins are validated; no extraction or alternate paths. The immutable payload returns isolated copies, preventing ordinary mutable pin aliases. |
| Graph | Current readback selects exact resource/version coordinates, invokes the existing full graph bracket, then compares exact deployment IDs plus versions/schedules/topology. Failed/malformed/drift reads fail. Existing resource/privacy/Queue/forward/hold readers remain required. |
| Stop/hold | Closed transition plans select only fixed script and empty successor schedules. Empty schedules describe paused/draining, never old invocation completion. Unknown drain remains UNVERIFIED. |
| Missing verifier | Activate and code replacement/rollback fail with distinct missing-proof reasons before graph provider reads. No arbitrary admission string, age, zero rows, missing log or timeout bypass was added. |
| Recovery | One successful checked read distinguishes exact predecessor/successor or unresolved graph; fixedFalse replay permission cannot be constructor-enabled. Exceptions propagate and never mean write-not-applied or safe retry. |
| Compatibility | Existing pure transition contract is unchanged; this slice does not change CLI/HTTP/storage/ZIP/Identity behavior, enable Cron or mutate the send hold. |

## Integration obligations and viable completion

The partial contract is not intrinsically a permanent dead end: the design provides a concrete fresh isolated/bootstrap provenance path, followed by protected observation receipt production, cooperative established-writer fence/immutable external-intent coverage, and a separately implemented old-work-end/compatibility verifier. However those are real missing work, not solved by the schema.

Important authority boundaries for future callers: constructing `Receipt` validates content but does not prove GitHub provenance; production integration must enter through `load`. Similarly recovery's supplied callback must implement the complete graph/resource/privacy/hold bracket; `checked_graph` alone validates a graph summary's shape, not external reads. Tests legitimately inject inert receipts/readbacks, but the future protected runner must not accept caller-authored dictionaries as these authorities. The code/documentation already states these obligations; no current writer bypass exists to demonstrate a vulnerability.

Fresh scope evidence must positively establish provisioning/history/writer ownership and separately handle shared provider/routing effects. Reusing current inventory, a manual type label or generic elapsed Cron lifetime is insufficient. Cooperative proof should start with existing accepted leases/fencing/intents and actual call-graph coverage rather than adding a parallel registry. Rollback must account for resource/schema compatibility and preserved schedules, not merely old code/version. Versioned binary artifact identity remains required separately from orchestration source.

Coordinator reports scopedCI36880235255 and syntax36880234958 success. This reviewer did not fetch receipts; no actual producer, transition, stopped invocation, drain, rollback or deployed privacy acceptance is claimed. The quota tamper test's XOR byte mutation makes the test deterministically modify authenticated bytes rather than occasionally retaining the original final byte; it does not weaken rejection.

## Primary references

* [Cloudflare Cron Triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/) and [platform limits](https://developers.cloudflare.com/workers/platform/limits/) — schedule and execution guarantees have scope; legacy HTTP cannot inherit a Cron-only proof.
* [Cloudflare rollbacks](https://developers.cloudflare.com/workers/versions-and-deployments/rollbacks/) — code rollback is not resource/schema/data rollback.
* [GitHub deployment controls](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments) — protected environments and concurrency belong in the actual producer/runner.
