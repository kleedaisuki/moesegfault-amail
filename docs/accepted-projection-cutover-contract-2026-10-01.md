# Accepted projection cutover contract

Date: 2026-10-01. Inspected PR #22 snapshot: `e752075` (local accepted-recovery
branch); deployment-path inspection also used development checkout `add03b6`.
Status: **design and admission requirements, not an approved or performed rollout**.
No local project test/build, Cloudflare request/mutation, deploy, send, Queue body
read, or push was performed. Public Cloudflare documentation and academic primary
sources were read; local work was source/document inspection only.

## Decision

Keep migration 0010 additive, preserve existing idempotency keys and terminal
journals, and make the first fenced-runtime cutover a controlled quiescent
transition. Do not claim schema compatibility means old/new writer compatibility.
Old HTTP/Cron writes never check the new token, so new code cannot fence them.

A single-100 serving-version pin is necessary but **not proof that previous
invocations have finished**. Do not admit PR #22's integrity guarantee based on
a generic 15-minute sleep. All correctness admission remains false until the
old work's completion/termination is independently established.

This is deliberately not a new orchestration framework. Use the existing
protected realm workflow, exact serving/binding/privacy readers, send-hold reader
and one operator cutover record. Add only the missing schema/drain admission
checks in a separately reviewed implementation. No current helper implements the
complete contract below.

## Important correction: there is no common 15-minute invocation bound

[Official Workers limits](https://developers.cloudflare.com/workers/platform/limits/)
state that connected HTTP invocations have no hard wall-time limit; Cron and
Queue-consumer invocations have a 15-minute wall-time limit. CPU limits are not
wall-time bounds. The runtime-update grace period in that document is about
Cloudflare runtime updates, not a promise that a user deployment kills all old
HTTP invocations within 30 seconds.

Consequences:

- Stop new old-version HTTP/service work and prove existing old unfenced
  invocations completed or were terminated. A deployment response, 100% pin,
  lack of recent errors, `held`, or elapsed time alone is insufficient.
- An HTTP client timeout is not by itself proof of all server-side work ending.
  Do not enable raw request logging, Issues, Tail or Logpush to manufacture drain
  evidence contrary to the independent privacy contract.
- For Cron, distinguish trigger propagation from invocation drain.
  [Official Cron documentation](https://developers.cloudflare.com/workers/configuration/cron-triggers/)
  allows up to 15 minutes for trigger changes to propagate. If no stronger
  effective-stop proof exists, a successful trigger-removal operation starts
  the propagation allowance; the latest possible old start is after that
  allowance, and its invocation can then need a further full 15 minutes.
  An API list showing no configured schedule is not a global-propagation proof.
- Verify the account's actual execution model supports the documented bound;
  the limits page lists deprecated Bundled behavior separately. Do not infer it
  solely from a missing subscription response.
- A 20-minute token lease is a finite retry window, not an HTTP execution bound.
  Within fenced revisions, the replaced token protects correctness even if an
  old HTTP holder remains alive after expiry. Unfenced revisions do not cooperate.

Affected original locations, already reported to the implementation owner:
`accepted.rs:30`, migration `0010_accepted_projection.sql:5`, and the integrity
document's cutover checklist row at line 48. Replace the common-invocation/drain
claim with the separate HTTP and Cron obligations above. This document does not
edit the owner's source or migration.

## Data compatibility and legacy behavior

Migration 0010 adds two journal columns, a nonunique message/state index, and an
accepted-body-update embedding requeue trigger. Defaults preserve existing rows:
null token, zero lease. It neither reconstructs old mail nor rewrites states.
The nonunique index avoids imposing an unsupported uniqueness constraint on
legacy journals. Existing explicit-column SQL continues to address the original
columns. The trigger changes derived-work behavior, not public API/ZIP formats.

| Existing state | Behavior after old-work drain and fenced deployment | Admission implication |
| --- | --- | --- |
| Accepted; valid original ZIP and owned exact-byte reservation; no visible row | New Cron rebuilds all chunks and atomically publishes message/ledger/sent | Supported; verify hash, ownership and bounded workload |
| Accepted; compatible live partial row | Public read/search/embedding paths hide it until repair commits; read/delete flags preserved; old vector/work lease invalidated | Temporary invisibility is intended prevention of partial exposure, not mail loss |
| Accepted; compatible owned tombstone; reservation survives | Terminalize without reconstructing content, even if old GC removed ZIP; later GC finishes deletion | Supported; missing ZIP alone is not deletion proof |
| Accepted; neither ZIP nor tombstone survives, or foreign/mismatched owner/provider/key/bytes/reservation | Fail closed; journal remains accepted for restricted operator investigation | Do not mark sent, recreate deleted mail, replay provider send or silently erase intent |
| Accepted with missing provider/message ID | Not selected by current recovery | Inventory and operator decision required; no inferred provider rejection |
| Sent; valid live row | Retains established visibility and identifiers; not selected for projection repair | No reset/recharge/resend or blanket reindex |
| Sent; tombstone or physically collected row | Remains terminal; same-key HTTP replay still returns established 202 with stable ID | Never recreate from retained ZIP solely because row is absent |
| Sent; historical incomplete body/chunks/vector or missing live archive | PR #22 does not automatically repair it: accepted-only selection and hidden-row predicates do not cover sent | Classify privately; a separate owner/deletion-safe repair would need its own contract |
| Preparing/reserving/submitting/unknown/rejected | Existing lifecycle behavior, not converted by migration 0010 | Especially reconcile submitting/unknown before any new canary; no second key/grant on ambiguity |

Duplicate/contradictory journals and foreign collisions are not automatically
normalized. Public artifacts contain aggregate counts/classifications only.
Detailed IDs, hashes, owners, envelopes and ZIP bytes remain in restricted
operator tooling; never dump raw query results to workflow logs.

A zero accepted count is not enough to prove old foreground projection is absent:
an old HTTP projector can resume after Cron already changed its journal to sent.
A zero aggregate inventory is useful for a demonstrably never-used isolated
realm, but not a substitute for independent old-invocation provenance, especially
if rows were manually deleted. Do not add an elaborate heuristic drain detector.

## Executable ordering contract

The safest default is to drain old work before enabling any new projection work.
Migration must precede any invocation of the new runtime; it may be applied during
the quiescent window. Running additive migration alongside old source is not a
proof of fenced safety and supplies no historical backfill.

1. **Authorize exact bounded operation.** Record realm, immutable promoted source,
   successful exact-source hosted integrity checks, provider privacy acceptance,
   old Worker version, and target deployment graph. Existing privacy/Issues
   unknown remains a hard prerequisite failure. No public send release is included.
2. **Freeze writers and canaries.** Use existing noncanceling realm deployment
   serialization plus an operator freeze of ad hoc dashboard/API/deployment and
   canary/grant operations. Verify global `held` using
   `check_send_hold.py --target <realm>`. Also establish no live one-use grant or
   running canary can admit a new foreground send; that checker explicitly does
   not revoke or prove absence of grants. Preserve keys for ambiguous prior sends.
3. **Record baseline, then quiesce old entry points.** Restricted aggregate journal
   states, provider-positive counts, compatible accepted live/tombstone counts,
   missing reservations, and version/trigger identity are sufficient public
   evidence. Prevent all new old-version work through relevant HTTP/service,
   Cron and any alternate entry path. `workers_dev=false` alone says nothing about
   version URLs or service callers. Preserve existing inbound/forwarding contracts;
   any maintenance routing change requires its own bounded approval.
4. **Prove drain.** Record effective no-old-start evidence and separate HTTP
   completion/termination evidence. For Cron, record removal/propagation timing
   and full old-invocation drain as above. Keep gate false if this proof is
   unavailable; do not deploy first and hope a sleep fixes a mixed interval.
5. **Apply and verify exact additive schema.** On the hosted protected realm,
   staging uses `wrangler d1 migrations apply MAIL_DB --remote --env staging`;
   production uses the default production realm. Verify the recorded migration,
   both new columns/types/defaults, index columns/nonuniqueness, and requeue
   trigger definition/dependencies against the exact reviewed migration files.
   Do not trust a migration-name row or successful command alone. Suppress raw
   provider/DDL output; emit fixed schema-verified/unverified classifications.
6. **Deploy matching fenced runtime and configuration.** Use the existing redacted
   explicit-realm helper only after drain/schema admission. Deploy directly to a
   single 100% version, not a gradual old/new split. Ensure no old version remains
   reachable through an independently enabled alternate URL/caller. Temporarily
   paused Cron must not be implicitly restored by an unchecked default TOML.
7. **Bracket acceptance.** Pin new immutable version/bindings and effective privacy,
   verify global hold, recheck schema/schedule and aggregate journals, and retain
   deployment IDs plus UTC. Freeze continues throughout the acceptance interval.
   Admit bounded existing recovery only under a separately verified full-Cron
   resource envelope. PR #22's known LIMIT 20 budget issue remains unresolved;
   no new artificial provider send is necessary to repair accepted rows.
8. **Resume only reviewed fenced entry points.** Restore the exact intended Cron
   schedule only after its resource/liveness prerequisite is satisfied, then
   account for trigger propagation. Record before/after source, version, schema,
   drain and hold evidence. Staging integrity acceptance does not open production
   sending, satisfy mailbox delivery, or authorize a release.

If production Mail is independently confirmed absent by a complete successful
inventory and there are no old callers, there is no old-runtime drain obligation.
Still inspect existing D1 journals/schema: absent Worker does not mean empty D1.
Unknown absence is not bootstrap. For staging, treat historical old-Cron and
controlled-client activity as real until the evidence establishes otherwise.

## Queues and deployment plumbing: retain the narrow scope

Mail is not the Sending lifecycle Queue consumer. `workers/mail-events` attributes
provider events against accepted/sent journals and writes provider-event/outcome
state; it does not publish message body/chunks or transition this projection to
sent. Migration 0010 leaves that attribution contract intact. The trace sink is
another separate Queue. Neither Queue needs purging/draining/recreating merely
for this projection cutover. Keep subscriptions, identities and retry/DLQ handling;
never read private Queue bodies to assert readiness. Concurrent negative provider
feedback may tighten held policy and must not be overwritten by this procedure.

Current `ci.yml` already applies migrations before build/deploy and immediately
pins the returned new version. It does **not** enforce trigger stop, HTTP drain,
Cron propagation/drain or the legacy aggregate classification. Existing
`pin_staging_mail.py` rejects split traffic and brackets the active deployment,
but checks neither schedules nor old invocations. `deploy_production_mail.py`
captures a recovery version even on an ambiguous command failure; it does not
attest successful rollout. A timeout/failure is inspect-only, never automatic
redeploy/retry or canary replay. Also note `target=staging` has broader site,
ingress, lifecycle and inbox impacts, not an API-only dry run.

## Minimal automation and recovery boundary

Automate read-only exact schema, deployment, bindings, schedule, held/grant state
and aggregate legacy classification using existing bounded private readers and
fixed labels. Bind all results to one realm/source/version and detect drift on a
second read. Do not accept a caller-supplied `drained=true` or elapsed timestamp as
HTTP completion proof. Independent drain evidence can initially remain a reviewed
operator record; before a workflow consumes it, review its provenance/verifier.

After migration but before fenced deployment, a failure leaves the additive schema
in place and admission false. Do not drop columns/triggers or delete journals as
rollback. After fenced code has served, do not automatically roll back to an
unfenced revision: schema compatibility does not restore race safety. Prefer a
fenced corrective version; if unavailable, hold/quiesce and seek explicit operator
recovery. Never restore an old database snapshot blindly after an irreversible
provider send; that can erase idempotency/deletion evidence. Storage versions are
not rolled back with Worker versions, as documented by
[Cloudflare versions/deployments](https://developers.cloudflare.com/workers/versions-and-deployments/).

The conceptual distinction is supported by dynamic-update research:
[Rommel et al., OSDI 2020](https://www.usenix.org/conference/osdi20/presentation/rommel)
achieve safe updates through local quiescent points, not elapsed deployment time.
[Tesseract, VLDB 2023](https://arxiv.org/abs/2210.03958) studies transactional schema
changes under modified snapshot concurrency control. Neither supplies a D1 or
Workers capability to revoke this project's old application continuations; do
not transplant their guarantees into this rollout. The practical choice here is
one explicit quiescent cutover, then token-fenced coexistence of later revisions.
