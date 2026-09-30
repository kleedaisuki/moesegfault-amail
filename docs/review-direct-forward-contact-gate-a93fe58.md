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
