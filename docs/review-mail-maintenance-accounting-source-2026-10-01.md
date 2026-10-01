# Independent static review: maintenance admission and accepted due fairness

Date: 2026-10-01. Reviewed commits `e6d37155f8769b0c12519c6f355075741622233e`
and `6e91c8ccd86ebb3e1dede3f979ced4ee189edf11`, relative to PR22 candidate
`25acdf1a160a3a57656e8e7bf43ce1007d3f9e9c`.

## Assessment

No substantive new correctness or safety defect was identified in these two
bounded source slices. This is not whole-ADR approval or a runtime-validation
result. The documented deployment blockers remain real and outside these slices.

## Inspection and positive evidence

- Read the existing whole-Cron review, architecture ADR, implementation record,
  changed source, accepted projector, migrations 0010/0011, safe telemetry mirror,
  trace sink, and changed hosted-fixture contracts. Inspected names/structure
  before relevant documents rather than scanning unrelated project material.
- All MAIL_DB acquisition in the reviewed Mail Worker source is confined to
  `database.rs`. Cron dispatch constructs one `MaintenanceBudget` and passes a
  phase-bound `Database` through each established maintenance call graph. The
  provider-delete helper now receives that same handle for its last state read.
  No reachable Cron raw-D1 reacquisition or foreground-constructor bypass was
  found. `first`, `all`, `run`, and every member of `batch` debit before the raw
  binding method. Neither failed submissions nor conditional no-ops refund.
- Grants are 170/380/90/2/65/65/5/5 = 782. Eighteen of the 800 global tokens are
  intentionally inaccessible to phase borrowing. Batch admission is atomic;
  scope identity rejects foreign invocation/phase/foreground statements. The
  shared counter is invocation-owned, not isolate-global. The current serial
  phase/item execution makes `ensure_remaining` a sufficient pre-I/O allowance
  check, although it is not a durable reservation or a general concurrent API.
- Accepted setup costs two statements. For service-valid text, k<=66 additional
  chunks. The late-path conservative item bound is due UPDATE + envelope UPDATE
  + lease claim + stale-index cleanup + k chunk writes + three publication batch
  members + terminal-resolution read + failure release = k+9<=75.
  Thus 2+5*75=377 fits the 380 outbound grant. This conservative sum combines
  branches that need not all occur together; actual submissions remain metered.
  Healthy outbound is 2+5*(k+7)<=367. The combined documented models 739/749 are
  consistent with adding five due advances to the earlier 734/744 models.
- Selection is provider-positive accepted work, ordered by durable due slot,
  original creation time and stable message ID, LIMIT 5; live projection leases
  are excluded before LIMIT. Exact-observed-slot CAS rechecks immutable journal
  identity/state and expired lease, advancing to scan_at+five minutes before
  R2/parsing. RETURNING presence avoids interpreting trigger-expanded change
  counts as due-admission authority. Missing/corrupt/foreign archives consume a
  finite turn, moving behind untouched work. This improves finite-backlog
  fairness; it does not promise bounded latency under arrival rates exceeding
  service capacity or permanent database failures.
- Due advancement is retry scheduling, not write authority. The existing
  opaque HTTP/Cron projection lease still gates accepted content publication.
  Projector SQL semantics are unchanged by adapter substitution. Caught item
  faults continue the selected batch; an admission denial stops only that phase.
  Failure release attempts also pass through statement admission and cannot
  execute unmetered when exhausted. Retained ZIPs/journals are not discarded.
- The Rust schema and active Python mirror admit only the new standalone
  MaintenanceBudgetDeferred/ResourceDeferred pair; producer emits the same pair.
  The trace sink consumes the shared Rust schema. An old deployed sink will
  acknowledge/drop unknown records, so sink-before-producer rollout remains
  necessary, as already explicitly documented in the implementation record.
- Hosted fixtures describe five maximum text projections plus later retention,
  three poison prefixes, live-lease skipping and following-item progress after a
  projection fault. They are useful behavioral contracts, not proof of adapter
  submission counts: SQL-trigger chunk counts are a lower bound and omit reads,
  no-op writes and rollback submissions.

## Scope limits and follow-up gates

No project tests/build, provider inventory/actions, deployment, push, actual-plan
inspection, CPU/RSS measurement or remote-quota experiments were performed.
This review makes no hosted-pass claim. Future changes to the LIMIT, valid text
contract, per-item SQL, retry paths, or execution concurrency require re-auditing
both the item bound and allowance semantics; the adapter remains the runtime
statement ceiling even if a source model becomes stale.

Remaining explicitly deferred ADR requirements include phase rotation and time
admission, finite Cron provider timeout, capped incremental archive reads,
bounded Queue flush behavior, and deployed resource measurements. The present
fixed phase order cannot by itself prove later phases receive CPU/wall-time
opportunities. These are acknowledged incomplete scope, not newly introduced
bugs or reasons to pretend this source candidate is deployment-ready.

## External contract checks

Retrieved official documentation during review:
[D1 database and batch](https://developers.cloudflare.com/d1/worker-api/d1-database/)
confirms ordered batch result correspondence and transaction rollback on statement
failure; the adapter correctly counts each submitted statement rather than a
binding round trip. [Workers production practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/)
is consistent with invocation-local rather than global mutable admission state.
The prior ADR's controller/liveness grounding is reused, not a claim of formal
verification or new academic investigation.
