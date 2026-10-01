# Hidden accepted DELETE due-expiry fixture review

Date: 2026-10-01. Source correction: `46ae8cfd2a0a6f02dc0ffeee01884dc6db7fc86d`.
Inspected candidate head: `d7096d52d4bbc09a04a9931ff7de356ca9287583`
(the source correction plus a documentation-only prior-review cherry-pick).

## Decision

**GO for an exact-candidate GitHub-hosted, nondeploying source rerun.**
No substantive defect was found in this focused correction. The hosted failure
is a synthetic scheduling assumption, not demonstrated broken owner DELETE,
premature GC, or resurrection in production. Confidence: high for this source
classification and preserved assertions; corrected runtime outcome still needs
hosted execution. This does not approve deployment or close resource/privacy gates.

## Evidence inspected first

Read relevant document filenames, then the maintenance implementation record,
accepted projection cutover/source review and final integrated source review.
Fetched [run 36808092751](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36808092751)
jobs and Worker job `110196837599` logs directly through the GitHub connector.
The runner checkout was synthetic PR merge `c4f7bc1`, merging source head
`059dcd624eb6dcfe295f8f6f07e8e9d644747a63` into main `73874d6`.
Do not describe this historical run as execution of the corrected head.

Worker compilation/native contracts succeeded. Built-workerd boundary execution
reported 96 cases, 95 pass / 1 fail. Test #5, `public owner DELETE tombstones a
hidden accepted legacy projection`, failed at `real GC removed the immutable
archive`: actual R2 object, expected null. The owner/foreign/repeated DELETE
assertions preceding that line had completed. This is the specific observed
failure, not an inference from the new explanatory document.

## Executable lifecycle and assertion preservation

| Stage | Source contract | Corrected fixture observation |
| --- | --- | --- |
| First recovery | `lib.rs:587-596,645-666`: due selection followed by conditional advance to scan time + five minutes; opaque projection lease is separate | Initial Cron completes projection as sent; fixture deliberately changes only journal state back to accepted (`test:149-154`), retaining its future due slot |
| Immediate owner delete | `lib.rs:1962-1973`: atomic owner/live UPDATE RETURNING; accepted visibility filter does not prevent deleting a known owned ID | Existing foreign 404/no mutation, owner 204/finite persisted tombstone, repeat 404/unchanged timestamp (`test:156-165`) all remain unchanged |
| Immediate synthetic tick | Due selection excludes future slots; `garbage_collect`, `lib.rs:247`, excludes every accepted journal | Added future-slot assertion, real scheduled call, accepted state, same tombstone timestamp and existing ZIP (`test:166-175`); this detects premature physical GC rather than merely tolerating it |
| Explicit due expiry | Expire retry scheduling only, not shared projection authority | Fixture updates only its synthetic idem row's due column to zero (`test:178`); no clock sleep, lease reset, source deletion, or direct terminal state mutation |
| Eventual physical cleanup | `repair_accepted` recognizes exact-owned outbound tombstone, `accepted::finish_deleted` claims lease and atomically finishes ledger/sent; later deleted-GC becomes eligible | Existing next real scheduled call requires R2 ZIP null and zero message rows (`test:180-182`), before resuming delayed HTTP |
| Late writer and replay | Terminal journal prevents content reconstruction and second send | Existing stable-ID 202 responses, one provider send, unchanged reservation/usage snapshots, then zero messages/chunks/reservations/embedding work and zero used bytes (`test:187-204`) remain unchanged |

The ZIP retention requirement here is the established accepted-aware GC lifecycle,
not a claim that tombstone terminalization must parse ZIP contents. Indeed the
owned-tombstone branch can finish after legacy GC already removed its archive.
Retaining accepted tombstone/reservation evidence until an authorized terminal
transition is important; deleting it early could remove deletion intent and prevent
safe convergence. Weakening the global accepted exclusion to make an immediate
fake tick pass would repair neither the data model nor scheduling contract.

Both safety and eventual progress are asserted: archive/tombstone survive the
not-yet-due tick, and real GC succeeds after expiry before delayed HTTP resumes.
The final assertions imply successful sent terminalization under the inspected
GC predicate; a redundant explicit sent-state assertion would improve diagnosis
but is not a missing correctness check or rerun blocker. The case does not prove
a real five-minute cleanup SLA under dependency failure or sustained backlog.

## Change boundary and next evidence

The complete `46ae8cf` diff adds fourteen fixture lines and an implementation
diagnostic section only. `d7096d5` adds only the integrated review document.
No runtime source, migration, owner predicate, production cadence, grant policy,
provider behavior or existing assertion is changed. Other race modes remain
outside the `hiddenAccepted` conditional. The default boundary script still
selects this suite and all new maintenance/R2 suites.

Rerun the complete hosted checks at the final exact head, not just test #5, and
record source head plus actual tested PR-merge checkout. Historical 95/96 evidence
cannot stand in for a successful corrected run. Preserve rollout blockers already
documented: old unfenced writer drain, sink order, verified account tier and
maximum-valid CPU/RSS, plus the remaining full-maintenance ADR requirements.

## External grounding and limits

[Cloudflare D1 batch documentation](https://developers.cloudflare.com/d1/worker-api/d1-database/)
supports the ordered transactional terminalization and rollback interpretation;
it does not itself prove this test passes.
[Kubernetes controller practice](https://kubernetes.io/docs/concepts/architecture/controller/)
supports distinguishing durable desired state from an individual wake-up.
[Anvil (OSDI 2024)](https://www.usenix.org/conference/osdi24/presentation/sun-xudong)
separates eventual stable reconciliation from immediate behavior: the practical
analogy here is testing retention safety and due-eligible convergence separately,
not claiming formal verification. Current Cloudflare Workers best practices were
also retrieved; no new binding/API/config signature is introduced by this diff.

No local project tests/build, provider request/mutation, deployment, send, push,
or production modification was performed. This review used source inspection,
public documentation, historical GitHub CI readback, and an isolated documentation
worktree. Broader runtime, maximum-workload and live-account behavior was not
revalidated. No unresolved necessary correction within this focused scope.
