# Independent review: direct-forward contact gate, a93fe58

Date: 2026-10-01. Reviewed commit: `a93fe58981429b81427bd827a1f2a2f1e6908b34`.
This is source inspection, not executed validation or hosted acceptance.
No local tests/builds, live provider calls, database mutations, deployment,
mailbox access, route changes, or sends were performed. Only this review
artifact was written. Concurrent deployment/workflow edits are outside scope.

## Decision

**GO for hosted source-only checks of the held candidate.** No critical
public-send bypass was identified in this change. **NO-GO for public release
or unheld deployment:** explicit human coverage, hosted migration/runtime
acceptance, scheduled checker integration, and independent release evidence
remain absent/pending by design. A source-review GO must not be relabeled as
proof that any test, D1 migration, or production configuration passed.

## Contract distinction: admission is enforced; arbitrary unhold is not

**Resolved by source correction `212cfe07e84fbc5740e85a1f9166af300fcbf2c7`,
independently re-reviewed on 2026-10-01.** The discussion below describes the
original a93fe58 state, not the corrected candidate. See the correction review
at the end of this document; do not reopen this gap without new evidence.

Location: `0009_direct_role_contact.sql`, the two `BEFORE INSERT ON
send_requests` guards; `infra/operator/send_control.py::statement`.

The stated architecture requires same-database SQL **send admission** and a
guarded operator allow statement. These are implemented. However, a stronger
requirement that a SQL trigger reject **every global unhold write** is not
implemented: there is no `BEFORE INSERT/UPDATE ON send_policy` readiness guard.
For example, immediately after 0009, a privileged raw
`UPDATE send_policy SET state='allowed' WHERE scope='global'` can commit with
no adopted policy/health/human acceptance. The source test itself uses this
write in `test_held_canary_does_not_depend_on_contact_health` before proving
admission still denies the consumed canary.

**Impact and calibration:** this is high-confidence, conditional contract
gap, not a demonstrated public-send authorization bypass. The new runtime,
new-request SQL triggers, and release checker continue to deny. It does not
block obtaining hosted source evidence. If the review task's stronger
every-unhold invariant is normative, classify it as a necessary medium-priority
correction before claiming that invariant. Otherwise it is optional
defense-in-depth at a documented trusted-code boundary; do not invent a
critical vulnerability from an operator credential already able to rewrite
all evidence or drop triggers.

Minimal coherent correction, if that stronger invariant is adopted: add
`BEFORE INSERT` and `BEFORE UPDATE` guards on `send_policy`, each conditioned
on `NEW.scope='global' AND NEW.owner_iss='*' AND NEW.owner_sub='*' AND
NEW.state='allowed'`; abort with `send_held` unless both the four-static-gate
predicate and `EXISTS(SELECT 1 FROM direct_role_contact_ready)` hold. Apply on
all allowed writes rather than only OLD-held transitions so an already
allowed but expired row cannot be rewritten as renewed authorization. Hold
writes and account-local writes remain unconditional. Keep the operator's
guarded statement as well. Adapt the direct-migration raw-unhold test to expect
rejection; retain the pre-0009 test unchanged. Add missing/expired/wrong-contract,
future/equality, healthy-but-unattested, allowed-to-allowed, account allow,
and unconditional emergency-hold cases on the hosted lane.

## Evidence traced

| Surface | Assessment by inspection |
| --- | --- |
| Migration | Additive contact/gate columns and tables; does not rebuild or drop mail/idempotency state. Clears only contact acceptance, starts/keeps global held, creates no policy or health. Changes the gate audit trigger to retain contract binding. |
| Data model | Singleton/version, distinct fixed role IDs, adoption ledger forbidding reused IDs, exact human contract equality, and database-time exclusive expiry eliminate legacy boolean/lease fallback. Policy insert/update/delete clear health/contact acceptance and atomically hold through trigger execution. |
| Health ordering | Positive database observation time and exact six-hour expiry; same-second failure wins; equal/older successes cannot replace recorded failure. Recovery alone never allows. A replaced contract cannot receive an old checker's write. |
| New send admission | Independent 0009 guards are not dependent on 0006 canary-trigger ordering. Missing global/expired contact under allow cannot fall back to consumed or fresh canary permission. Static flags/account holds remain enforced by 0006. |
| Repeated sends | Existing preparing-request retries call `check_send_policy`; fresh requests check before INSERT; all actual submissions check again after claiming submitting and before the provider call. Completed/unknown idempotent paths do not blindly resubmit. No runtime read of `ROLE_MONITOR` remains in the changed predicate. |
| Operator paths | Adoption creates a fresh UUID, uses fixed database coordinates and opaque references, reads back ambiguous adoption without retry. Human contact verification demands the explicit coverage phrase and exact input contract; machine refresh never writes human gates. Revocation needs neither phrase nor valid contract. |
| Provider observation | Bounded complete pagination is reused; exact enabled API-owned four single-matcher/single-forward shapes, pinned identities, unique verified destination, literal-role conflicts, and two snapshots are checked. Current `id` and legacy `tag` cannot disagree for selected routes. |
| Failure/readback | Provider exceptions become unverified, scoped D1 writes invalidate/hold when reachable; ambiguous renewal has one exact readback and no retry. Missing policy/query/config failures cannot renew. D1 outage does not magically revoke existing health immediately; expiry is the documented bound. |
| Destination privacy | Private destination stays in memory/Secret and provider request responses; new SQL stores IDs, not destination/hash. New helpers print fixed labels, suppress provider bodies, bound replies, and reject credential-bearing redirects. No mailbox capability added. |
| Held helper | Its executable SQL references only pre-existing send_policy; exact global row/count/type checks deny missing/malformed/allowed state. Importing the helper does not query new contact tables, so migration 0009 is not a runtime prerequisite. |
| Compatibility | Changed Rust permission failure retains public `send_held`. Account/recipient rules, held one-use canary, API/CLI/ZIP interfaces and stored mail are not rewritten. Existing non-contact operator attestations preserve input contracts. New contact attestation intentionally cannot silently succeed through the old workflow. |
| Release gate | Adds the same view's exact singleton readiness to existing global/static release requirements; does not substitute `/health` for contact health or prove the serving topology. |

The unavoidable final precheck-to-provider interval is explicitly documented:
neither D1 nor a periodic routing observation can recall a provider submission
already in flight. This is not represented as continuous provider integrity or
proof of human Inbox/Junk review.

## Hosted acceptance obligations, not executed results

1. Execute the new SQL/provider synthetic suite through normal hosted discovery;
   execute the Rust build/tests. Source tests do not prove remote splitter behavior.
2. Prove held state before/after real D1 0009 migration and serving changes;
   test real D1 trigger support/splitting and synthetic expiry/failure admission.
3. Preserve held-only rollback. An old binary lacks the direct pre-provider
   freshness check, especially for already preparing send requests, even though
   the migrated fresh-INSERT guards remain present.
4. Wire/review adoption, explicit human coverage inputs, and scheduled health
   checker separately. No current workflow automatically grants pending coverage.
5. Continue independent deployment topology, privacy, outbound, protocol and
   intervention acceptance. Do not replay historical receipts simply to produce
   a cosmetic aggregate success.

Test gaps relevant to assurance: current tests inspect only the ambiguous write
that did **not** commit, not a committed-but-response-lost success resolved by
readback. They do not exercise the actual Rust provider-call boundary or remote
D1 migration splitter. These are evidence gaps, not established defects; add
the positive ambiguous-write case and real hosted integration checks.

## External evidence and its limits

Current official primary documentation was fetched on 2026-10-01:
[Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/),
[D1 SQL statements](https://developers.cloudflare.com/d1/sql-api/sql-statements/),
[routing rule inventory](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/list/),
and [destination inventory](https://developers.cloudflare.com/api/resources/email_routing/subresources/addresses/methods/list/).
These inform platform/configuration contracts; none demonstrates this actual
migration or proves SMTP delivery or mailbox attention. Native MAIL_DB binding
reads and explicit denial paths are consistent with the production guidance;
hosted REST belongs to the external operator, not the Worker hot path.

The architecture's existing Gray Failure reference usefully separates
control-plane observations from user outcomes; no new speculative academic
mechanism is necessary to review these executable authorization paths. Human
coverage and delivery/intervention remain separately owned evidence.

## Correction review: 212cfe0

Scope: inspected the correction diff for migration 0009, direct-contact SQL
tests, and implementation documentation. No local tests/builds or live calls
were executed. This review assesses source logic, not D1 execution evidence.

**GO for hosted source-only checks of the corrected held candidate.** The
every-unhold source gap is resolved; no new substantive defect was identified.
**NO-GO for public release or unheld deployment remains unchanged** because
human coverage, scheduled checking and real hosted acceptance are not supplied
by a source trigger correction.

The new `send_policy_direct_allow_insert` and
`send_policy_direct_allow_update` guards condition on every NEW global allowed
row, not just held-to-allowed transitions. Both reject unless the four static
flags and the exact shared `direct_role_contact_ready` view pass in database
time. Existing send_policy CHECK constraints already require global owner pins
`*`/`*`, so omitting duplicate owner checks in their WHEN clause does not widen
the accepted global row domain. Allowed-to-allowed edits recheck freshness.
Global held and account-local writes are outside these conditions, preserving
emergency hold and account policy operations. The migration's final contact
revocation/hold writes do not trigger an allowed-only guard, and policy/health
failure holds do not acquire a readiness dependency.

The added synthetic test covers missing-evidence raw UPDATE, raw INSERT after
global-row removal, successful ready reassertion, a missing static flag, exact
expiry on allowed-to-allowed reassertion, emergency hold and account allow.
The existing held-canary test now expects raw unhold to fail, then explicitly
drops only the update guard to verify the independent send-request admission
defense. This intentional test-only fault injection avoids claiming one guard's
rejection proves another guard's behavior. The pre-0009 hold-readback test is
correctly retained unchanged. Positive global INSERT with complete readiness
and account UPDATE could broaden hosted coverage, but inspection establishes
no production defect requiring them before source-check execution.

Because 0009 has not been represented as deployed, correcting its source is
consistent with the pending held rollout. If contrary deployment evidence
appears, do not assume editing 0009 retrofits an already migrated database;
create an additive follow-up migration and re-review that rollout separately.

## Operator extension review: 0fab849

Date: 2026-10-01. Reviewed `0fab849f36f53f6de885dfb005c6bcd10adff41a`
against the corrected 212cfe0 source. Scope is helper/migration/test/doc changes;
integrated workflow 1c13b38 and its shared concurrency-lock implementation are
outside this narrow review. No tests/builds or live calls were executed.

**GO for hosted source-only checks.** No substantive authorization defect was
identified. Public release/unheld acceptance remains **NO-GO** pending the
independent evidence already described. This is not approval of unexamined
workflow serialization or actual D1 catalog-query compatibility.

* **Held-only no-adoption skip:** `optional_held_policy` positively queries the
  catalog, distinguishes fully absent from expected object-count shapes, and
  rejects partial counts/query errors/malformed results. The upgraded path
  compares the actual policy inventory count to version-filtered results, so
  unsupported-version rows are not interpreted as absence. No policy requires
  exact established global-held evidence. The main skip occurs before routing
  credential/destination validation or client construction, needs no routing
  Secret, writes no health and prints `unadopted_held`, never `healthy_recorded`.
  Policy absence observed concurrently with later adoption cannot grant send
  authority; it merely omits that run's configuration renewal.
* **Atomic adoption comparison:** SQL SELECT/UPSERT guards expected `NONE`
  absence or the exact existing version-1 UUID in the same statement. A stale
  expected UUID cannot overwrite a newer contract. Both absence and replacement
  retain the fresh-ID ledger and automatic held/revoked behavior. Ambiguous
  outcome uses the generated UUID's exact readback without write retry.
* **Explicit revocation:** the new AFTER UPDATE OF contact columns trigger
  clears health and holds even on repeated zero-to-zero revoke. Non-contact
  gate/canary-only updates do not activate it. Verification does not renew
  health. Interaction with 0006 hold triggers is safe: all resulting global
  writes are held, outside the allowed-only readiness guards.
* **Routing-mutation barrier:** production-only invalidation requires expected
  schema object counts and revoke-trigger presence, then an acknowledged
  one-row revoke plus exact held/revoked/health-empty readback. Committed-but-
  response-lost revocation still fails the barrier; no automatic write retry
  or downstream mutation permit is created. New tests model this conservative
  ambiguity branch and repeated revoke, adoption comparison, and no-secret
  skip. Their source is not evidence they executed successfully.

### Catalog integrity boundary: optional diagnostic, not readiness proof

The no-policy upgraded skip does **not** execute the readiness view. Therefore
its object-count check does not demonstrate that the view definition is
executable, semantically correct, or that every migration trigger is present.
A catalog-present but broken view may still produce an idle-held skip. This is
not a send-permission defect: skip requires global held, writes no evidence,
and does not claim migration or release acceptance. Describe these counts as
object-shape diagnostics, not complete schema-integrity verification.

Optionally execute `SELECT COUNT(*) FROM direct_role_contact_ready` on the
upgraded no-policy branch to fail early for missing referenced columns or other
view-resolution errors. This inexpensive diagnostic is useful if that branch
is intended to detect executable-schema damage, but is **not required for the
held-only safety contract** and cannot prove view semantics or complete trigger
integrity. Do not turn it into a substitute for hosted D1 migration/admission
acceptance. This review raises no necessary correction solely to add it.

The helper explicitly depends on external non-canceling realm serialization:
an invalidation readback is not a database lease preventing a later checker or
attestation from running. Confirm that workflow-level contract independently,
especially across routing mutation, adoption, attestation and health checks.
