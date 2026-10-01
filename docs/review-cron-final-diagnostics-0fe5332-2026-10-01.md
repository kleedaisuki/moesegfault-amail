# Independent review: final Cron diagnostic batch

Date: 2026-10-01.
Exact implementation candidate: `0fe53325207fca7635394718f5ed0c670f22e0e1`.
Merged main/base: `59ab7a55f38c4646e08cdf2539176fff2ab4a46d`.
Review worktree: `.temp/cron-final-diagnostics`.

## Decision and scope

**GO for exact-candidate GitHub-hosted non-deploying checks.** No substantive
source defect was found in the complete eight-file candidate diff. Confidence is
high for the inspected control/data flow and moderate for native integration
pending hosted execution. This is **not deployment or release approval**, a test
pass claim, a hard wall-time guarantee, or approval of the unresolved embedding
HTTP/R2 slice sequencing. Do not push or deploy on the strength of this review.

Only this English review artifact is committed on a separate review branch.
The implementation branch is not modified. No local project tests, builds,
provider calls, private-data reads, pushes or deployments were performed.
Public platform documentation retrieval is not a provider operation.

Relevant documents were selected by filename first: the candidate implementation
record, existing trace Queue sink decision, and prior integrated Cron budget
review. Source inspection included all changed files, scheduled dispatch,
address/embedding durable boundaries, shared schema, sink, Python privacy mirror,
CI step placement, and the pinned locally cached workers-rs/worker-sys 0.8.7 Queue
implementation. Merge-base equals the exact merged main named above.

## Evidence matrix

| Contract | Source evidence | Assessment |
| --- | --- | --- |
| Invocation-owned eight terminal slots and five presence facts | `maintenance.rs`: private `[Option<PhaseOutcome>; 8]`, `[bool; 5]`; explicit exhaustive identity mapping | No global production state or retained error/item data. Successful and unfinished slots emit nothing. |
| Exact terminal classification | `finish`: SQL marker first, deadline marker second, otherwise existing phase-specific code | Previous standalone vocabulary preserved; deferrals for distinct phases are not deduplicated. Duplicate finish is a debug programming assertion and release first-result retention. |
| Exactly five nested emitter replacements | `lib.rs`: address batch-full, committed disabled rule, provisioning disabled rule, document quarantine, dependency cooldown | All prior Queue awaits become synchronous notes. Quarantine remains after its original work-ledger update and cooldown after dependency-ledger update. SQL, leases and attempts are unchanged. |
| Business work precedes Queue access | `scheduled`: finish each awaited phase, then consume collector and await one final flush | Queue failure or latency cannot serially block a later business phase in this invocation. |
| All-or-nothing application admission | `trace.rs`: whole-buffer event validation, count cap 13, actual serialized UTF-8 body lengths cap 1,024, checked aggregate charge cap 240,000 | No binding lookup until a nonempty entire buffer is valid. No filtering, split, retry or partial application submission. This does not assert transactional consumer processing. |
| Actual native submission | `flush_maintenance` builds one default typed JSON batch and awaits `send_batch` once | Pinned builder supplies JSON defaults; worker-sys catches synchronous native exceptions and workers-rs maps rejected Promises to `Result`. Discarded transport error preserves existing best-effort semantics without logging source context. |
| Foreground compatibility | Ordinary `Trace`, `flush`, 100-record batch helper and request handling unchanged | No foreground schema/API/CLI or SQL migration change. |
| Sink compatibility | Existing shared schema and Python mirror allow both deferral/resource pairs; sink uses shared `Record::from_value` | No new sink code required by this candidate; serving sink compatibility still requires independent verification before producer rollout. An old sink may acknowledge/drop unsupported records. |
| Privacy | Collector contains only closed enums/bits; standalone records contain generated IDs, fixed vocabulary and zero duration | No SQL/binds, owners, addresses, message IDs, mail/provider body, URL, credentials or error prose enter the collector/envelope. No console fallback introduced. |

The conservative maximum charge at thirteen maximum-size bodies is
`2 + 13*1024 + 12 + 4096 + 13*512 = 24,078` bytes, well below 240,000. Thus the
aggregate guard is defensive headroom, not a frequently reached operating limit.
Actual JSON bytes are measured rather than inferred from field count. Native
serialization subsequently occurs in workers-rs; fixed ASCII fields and the
independent native envelope observer make the transport-size assumption explicit.

## Test discrimination assessed from source, not executed

- Pure Rust tests independently cover all eight failure identities under rotated
  dispatch, repeated deep-condition deduplication, thirteen maximum facts,
  success/no-op and unfinished omission, repeated phase deferrals, exact error
  classification, duplicate finish, invalid whole-buffer/count rejection,
  actual-byte charge, exact aggregate threshold and overflow.
- Literal twelve-field serialization checks are cross-checked by native observer
  field/value/ID validation and `TextEncoder` byte counts. The native observer is
  synthetic-only and imports the unchanged built production shim.
- Positive native control requires constructor `WorkerQueue`, one Queue lookup,
  `sendBatch=1`, `send=0`, native forwarded=1 and native settled=1. A missing
  binding or failed Rust Queue cast therefore cannot falsely satisfy success by
  sending nothing. Native receiver binding is preserved with `target.sendBatch`.
- Dependency-category tape asserts no D1/R2 submission after Queue lookup. Eight
  independent first-submission failures assert every phase is reached and all
  eight expected codes remain; healthy phases assert no Queue lookup at all.
- Deep fixtures exercise thirty mixed disabled routes and repeated quarantines,
  requiring all five condition codes exactly once, two durable quarantines and
  persisted provider cooldown. This probes actual emitter wiring, not only the
  collector enum mapping.
- Missing/wrong Queue binding, synchronous throw, rejected Promise and delayed
  final completion cases check scheduled success, committed accepted projection
  and later cleanup. Delayed completion observes all phase submissions before
  native settlement. Back-to-back rotation checks fresh invocation state.
- Synthetic logical clock jumps model four 30-second submissions followed by
  four denied phases. They are a useful admission discriminator, **not real D1
  latency evidence**, cancellation proof or a 120-second invocation bound.
- Strict fixture egress allows only reviewed synthetic routing GET and selected
  embedding error responses; all other egress is rejected. Private runtime logs
  and fixed stats are checked against synthetic sensitive/error sentinels.
- CI explicitly runs the dedicated diagnostics script after building the Worker
  and existing business suites. This is not hidden behind default test discovery.

## Remaining gates, not implementation findings

1. Run non-deploying hosted checks on the **exact reviewed implementation SHA**;
   merge-ref success or historical baseline success is not substituted here.
2. Reconcile explicit collector parameter overlap when sequencing the independent
   embedding HTTP/R2 changes. Preserve its durable lease/deadline/failure cleanup
   semantics and re-review the integrated candidate; this review does not approve
   unseen conflict resolution.
3. Before any future producer rollout, independently verify serving sink support
   for deferral/resource pairs and retain existing privacy/deployment gates.
4. A final Queue Promise has no cancellation parameter and may overrun soft Cron
   headroom; already submitted D1 work can also stall. Diagnostic collection can
   be lost on invocation termination before final flush. These are explicitly
   documented best-effort trade-offs, not newly claimed hard guarantees.

## External authority

Retrieved public primary sources during review:

- [Cloudflare Queue JavaScript API](https://developers.cloudflare.com/queues/configuration/javascript-apis/):
  one `sendBatch` Promise confirms persistence when fulfilled; no AbortSignal
  option is exposed; JSON is the documented default content type.
- [Cloudflare Queue limits](https://developers.cloudflare.com/queues/platform/limits/):
  100-message/256-KB batch boundaries are comfortably above this fixed buffer.
- [Cloudflare Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/):
  invocation-local production state, native bindings and owned/awaited work.
- [Pinned workers-rs Queue source](https://github.com/cloudflare/workers-rs/blob/v0.8.7/worker/src/queue.rs)
  and [worker-sys Queue binding](https://github.com/cloudflare/workers-rs/blob/v0.8.7/worker-sys/src/types/queue.rs):
  actual serialization, JSON builder defaults and caught native failures.

No novel algorithm or research-adoption decision is present in this bounded
transport refactor. Its authorities are existing durable/privacy contracts and
native platform semantics, not a speculative telemetry framework.
