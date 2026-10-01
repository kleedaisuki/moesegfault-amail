# Independent integration review: final Cron diagnostics after PR #29

Date: 2026-10-01.
Exact candidate: `eb15b38bbf509856da2184435110793195df006e`.
Merged PR #29 baseline: `6d149ee1ffdda89c2d08f1279ff2b0b8b974f4cf`.
Independent branch: `review/cron-final-diagnostics-eb15b38`.
Independent worktree: `.temp/cron-final-diagnostics-eb15b38-review`.

## Decision

**GO for exact-candidate hosted, non-deploying checks. No substantive integration
finding.** Confidence is high for the traced source preservation and moderate for
native execution pending exact-head hosted evidence. This is not a test-pass claim,
merge/release approval, deployment authorization, serving-sink verification, or a
hard invocation duration guarantee. The implementation branch was not modified,
switched, pushed or deployed.

No local project test, build, install, live provider operation, private-data read,
or deployment was performed. Actions were source/document inspection, public
primary-document retrieval, Git whitespace/equality inspection, and creation of
this separate review artifact. `git diff --check 6d149ee eb15b38` passed.

## Reused knowledge and scope

Selected documents by filename before source investigation: prior independent
review `4295dcc0e0c7f7a119369df73f53dc8f0b5e161f` of original diagnostic candidate
`0fe53325207fca7635394718f5ed0c670f22e0e1`, final-diagnostic implementation note,
PR #29 embedding/R2 deadline implementation note, embedding independent review,
and focused retained-GET review `docs/review-cron-r2-get-508c68d.md`.

Inspected all nine changed files against merged PR #29, the original diagnostic
candidate comparison, surrounding scheduled/address/embedding/outbound control
flow, shared schema, sink parsing, Python sink-canary mirror, workflow selection,
package scripts, native diagnostic fixture/observer, and cached lockfile-matched
workers-rs 0.8.7 Queue implementation. This is a narrow integration review: it
reuses rather than reclaims the previous separate deadline/diagnostic assessments.

## Integration evidence

| Contract | Exact source evidence | Assessment |
| --- | --- | --- |
| Both overlapping `process_embedding` parameters survive | `lib.rs:929-939` passes `deadline` then `diagnostics`; `1019-1027` accepts matching typed parameters; `1030` invokes `embed_cron` with deadline | No accidental return to foreground embedding or collector omission. |
| Policy deferral does not become provider failure | `lib.rs:1035-1041`: typed Deferred branch retains baseline UPDATE with `message_id=?1 AND lease_token=?2`, clears only lease fields, returns closed maintenance marker | Baseline exact-token release unchanged; no attempts, due, error/cooldown write or deep provider fact introduced. |
| Provider classification remains durable before observation | `lib.rs:1043-1054`, `1091-1140`: Provider(error) passes unchanged error/attempts/lease to retry policy plus collector; quarantine note follows work UPDATE; cooldown note follows dependency UPDATE | Ordinary provider retry/quarantine/cooldown semantics unchanged, with synchronous presence facts instead of nested Queue awaits. |
| Newly merged read-only R2 GET race is retained | `archive_read.rs`, `platform.rs`, native R2 and Cron embedding deadline test files are byte-identical to `6d149ee`; `lib.rs:699-719,759-822` retains immutable archive cutoff, `archive_read::get/read` and propagated maintenance deferral | No GET/body timeout rollback, late body allowance reset, mutation abandonment or loss of following-phase continuation. |
| Fixed per-invocation collector | `maintenance.rs:11-140`: eight private terminal slots plus five presence bits, explicit phase identity mapping, SQL/deadline marker precedence | At most thirteen records; repeated deep facts collapse, distinct phase deferrals do not. No retained errors, item identifiers or counts. |
| Business phases precede transport | `lib.rs:170-181` finishes every phase before consuming collector into one final flush | A diagnostic Queue wait cannot serially delay a later business phase. Earlier submitted D1 remains uncancellable. |
| One bounded application submission | `trace.rs:677-714`: whole-buffer validation, 13 records, real serialized bodies <=1024 bytes, checked aggregate <=240000 before lookup; one typed JSON `send_batch` awaited once | No filtering/splitting/retry/detachment/log fallback; application admission is all-or-nothing, not consumer transactionality. |
| Both hosted suites survive | `ci.yml:1625-1630` selects embedding deadline and diagnostics steps after built Worker; package scripts independently select both; default `pnpm test` still includes R2 archive suite | The integration does not hide the diagnostics suite or replace the PR #29 GET discriminators. Existing complete-item and routing steps remain. |
| Privacy/schema/sink compatibility | `trace.rs:718-748` produces existing twelve-field standalone fixed envelope; shared `valid_diagnostic` accepts resource-deferred pairs; sink uses `Record::from_value`; Python canary mirror retains both codes | No new wire vocabulary, SQL migration, foreground contract or private/error prose. Source compatibility does not prove a deployed older sink supports these pairs. |

The original diagnostic candidate and integrated candidate have identical Git
blobs for `trace.rs` (`39eeab2e06d7432ff7f4312bb0cd5e0965ca1ad8`), diagnostic test
(`e5020d056f5435cc2c2849b71d37ce069572da8b`), and native observer
(`8a1e8e8f933c2fddc45bd42f0e06a4db05012ac4`). The maintenance comparison adds
only the previously merged deadline accessors beyond the same collector.

## Hosted discriminators and limits

Authored tests are inspected, not run here. Deep diagnostic fixture exercises
three ordinary provider failures through the integrated Provider(error) path,
requiring two persisted quarantines, persisted dependency cooldown and exactly
five fixed deep records. It retains real native Queue forwarding/settlement
positive controls, independent literal schema/UTF-8 checks, privacy sentinels,
missing/wrong/throw/reject Queue cases and delayed final completion. Ordinary
R2 test selection still reaches real delayed and never-settling GET fixtures.

The Deferred collector mapping is covered by pure classification tests, while
native embedding tests exercise exact-token cleanup/later-phase liveness. The
embedding observer does not specifically capture a resulting diagnostic batch;
this integration conclusion therefore combines source tracing with the separate
existing discriminators, not an unexecuted claim of end-to-end Queue observation
on an embedding timeout. This is not a blocking source defect.

## Required next gates

1. Run hosted non-deploying checks at exactly
   `eb15b38bbf509856da2184435110793195df006e`, preserving checkout SHA and both
   deadline/diagnostics suite results. Historical original-candidate or PR #29
   green results do not establish integrated-head runtime acceptance.
2. Before a producer rollout, independently verify serving sink acceptance of both
   deferral/resource pairs and preserve existing privacy/deployment gates.
3. Retain the documented best-effort boundaries: final Queue has no exposed abort
   option and can exceed soft headroom; termination before flush can lose collected
   diagnostics; waiter drop does not prove remote GET/provider cancellation.

## External grounding

Public primary sources retrieved during review:

- [Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/): native bindings, invocation-owned state and awaited work.
- [Queue JavaScript APIs](https://developers.cloudflare.com/queues/configuration/javascript-apis/): JSON default, producer `sendBatch` Promise persistence semantics and no listed abort option.
- [Queue limits](https://developers.cloudflare.com/queues/platform/limits/): bounded application batch sits well below provider message/count/aggregate caps.
- [Queue batching/retries](https://developers.cloudflare.com/queues/configuration/batching-retries/): producer batching must not be confused with consumer processing atomicity.
- Cached locked `worker-0.8.7/src/queue.rs`: typed builder's JSON defaults, native serialization and awaited send failure conversion, inspected without executing project code.

No novel research-adoption choice exists in this narrow merge. Existing durable
and privacy contracts plus production platform semantics are the relevant
standards; speculative telemetry/workflow abstractions would add no evidence.
