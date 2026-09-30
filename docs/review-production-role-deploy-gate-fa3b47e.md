# Review: production unrouted role deployment gate (`fa3b47e`)

Date: 2026-10-01. Scope: the six-file change at
`fa3b47e128a4cc91cf272b37dd53285183535cfd`, its production graph checker,
shared role capability checker, role migration and existing staged phase-one
provenance/deployment counterpart. Read the production graph-transition decision
and staging role rollout contract before tracing callers.

## Verdict

**GO for hosted source checks only. No new substantive defect identified in the
six-file change. NO authorization for production deployment, route cutover,
release-gate changes or public sending.** No local tests, build, provider request
or live deployment was run during this review. This is source/control-flow
review, not acceptance of provider response shapes or actual privacy.

The prerequisite consumer intentionally references future production/staged
acceptance workflows. Their absence fails closed before migration/deployment;
it must not be repaired by substituting configuration markers or printing an
acceptance marker without the real harness. This implementation is therefore a
guarded transition, not a completed deployable production rollout.

## Evidence and assessed behavior

* `require_production_role_phase1.py:log/verify` separates three historical run
  kinds and validates repository, workflow, realm branch, exact source SHA,
  completed successful first attempt, complete bounded job inventory, unique
  successful exact job, and exact single marker. Production API/sink privacy
  evidence binds both serving versions and independently supplied Queue/DLQ IDs.
  Staged acceptance requires Email, Cron, fault and restoration success at the
  same source SHA. The logs stay in captured memory, not stdout.
* `deploy-role-monitor-production.yml` runs historical evidence before any
  provider mutation, then exact graph/storage checks before migration and again
  immediately before deployment. Its after step supplies the new captured role
  version and explicit `api-role` topology; it never calls a route-writing
  helper. API/sink version inputs remain unchanged. The graph checker brackets
  serving deployments and unchanged four private direct-forward shapes and
  requires all-capture-off effective settings rather than source intent.
* `migrate_production_role.py` rechecks pristine/empty-expired storage before one
  migration, suppresses Wrangler output, does not retry, and verifies the
  migrated state afterward. Partial/unexpected schema or pending ledger/lease
  state is not made acceptable by deleting data. The reviewed migration is
  additive; known tables/data are not destructively reset.
* `deploy_production_role_monitor.py` requires main and the production-only
  confirmation, requires an output destination before mutation, and selects the
  production base Wrangler configuration rather than staging. The shared helper
  validates all three protected secret values, creates a 0600 file under root
  `.temp`, captures raw deployment output, and removes the file in `finally`.
  Neither destination nor routing credential is deliberately logged. A parsed
  version from nonzero Wrangler exit is recovery information, never a success
  attestation. Timeout/no-version remains ambiguous and stops; no automatic
  redeploy or route mutation follows.
* Natural Cron before route cutover cannot renew the initial lease: role code
  audits all rules before `check_and_renew`, and the four direct forwards fail
  the role-target audit. The postdeploy first-bootstrap zero lease/check time
  contract is consequently consistent with that expected Cron failure.
* Fixture tests cover historical metadata mismatch/retry/duplicate jobs and
  production-vs-staging confirmation. They do not establish actual whole-record
  retained privacy or provider execution; those remain separate mandatory live
  acceptance work.

## Integration prerequisites and limits

1. At `fa3b47e` alone, the role workflow uses the new shared graph writer group
   but `ci.yml` does not yet use it. Subsequent `60627a8` adds workflow-level
   cross-workflow exclusion. The combined rollout must retain that integration;
   the role-only commit is not sufficient to serialize API/sink replacements.
   Operator freeze is also necessary for writers outside GitHub Actions.
2. The previously reported `d58921f` bootstrap held-send bug was explicitly
   excluded from this change's verdict. Correction `0191a32` was observed in
   the working tree, but is not re-certified here. Likewise the separately
   reviewed complete production binding contracts have their own artifact.
3. Exact SHA matching is intentional. A merge yielding another SHA must use a
   genuinely accepted same-source staged run (or a separately reviewed source
   manifest design); do not loosen the historical verifier to promote merely
   similar source.
4. Readback is not an atomic provider transaction. An ambiguous migration or
   deployment requires exact identity/state reconciliation. These helpers do
   not promise rollback of D1, Queue attachments, Cron, capture settings or mail
   rules. No production operational lease/delivery/privacy success is claimed.

## External reference

Reviewed current [Cloudflare Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/)
for configuration and deployment context. The project's stronger privacy
boundary deliberately disables original-context observability in producers and
permits only the reviewed typed Queue sink; generic advice to enable logs does
not override the mail confidentiality contract.
