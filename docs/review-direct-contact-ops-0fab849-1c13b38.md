# Independent review: held direct-contact operational wiring

Date: 2026-10-01. Reviewed source commits: `0fab849f36f53f6de885dfb005c6bcd10adff41a`
and `1c13b3822d2613f5ca5fd99d38659deb8113d2bc`, against the direct-only
implementation and the correction review of `212cfe0` in
`review-direct-forward-contact-gate-a93fe58.md`.

## Decision and scope

**GO for non-mutating hosted source checks only. NO-GO for actual adoption,
affirmative human attestation, provider mutation, deployment acceptance, public
release or unhold.** A source-check GO does not waive the issue below or prove
successful remote D1 execution. Human Inbox/Junk coverage and 24-hour notice
response remain pending. No local tests/builds, operational Actions dispatch,
provider calls, database writes, mailbox retrieval, deployment or sends were
performed. Only this review artifact was written.

Inspected the two diffs, migration 0009, operator policy/health/invalidation
helpers, existing attest/hold helpers, six contact workflows, the provider
mutation caller, and new synthetic/source tests. Unrelated concurrent working
tree changes are outside this review. Actual repository Secret provenance,
Environment configuration, default-branch registration and live state were not
examined.

## Resolved finding: catalog presence is not executable readiness-schema validation

**Resolved by `9cd9c4b859dde08bb8c7d877ffe91db4d2a62a18`, independently
re-reviewed by source inspection on 2026-10-01.** The following explanation
describes the original two-commit candidate, not the corrected integrated
candidate. No substantive unresolved source defect was identified after this
correction; hosted source-check GO and operational NO-GO remain unchanged.

**Medium-priority assurance defect; high confidence by source inspection; not
a demonstrated send bypass.** Location:
`infra/operator/direct_contact_health.py::optional_held_policy`, migrated
`shape == (4, 1, 1)` branch.

When the policy is empty, the helper confirms object names/counts, executes
the policy query/count, and proves the exact established global row held.
It never executes `direct_role_contact_ready` or references health-table
columns in this branch. A same-named view referencing a missing health column
or nonexistent relation therefore passes the catalog count and can produce
`unadopted_held`. This contradicts the documented promise that malformed or
partial migrated schema cannot become a successful idle observation. The exact
held proof still blocks public send; the impact is a falsely quiet schema
health/rollout signal, not authorization or contact readiness.

Minimal correction: for the migrated branch execute a fixed
`SELECT COUNT(*) AS ready_rows FROM direct_role_contact_ready`, require one
typed integer result, and require zero when declaring no adopted policy.
Preparation/execution then validates the view's referenced tables/columns even
with no policy row. Add synthetic malformed-view and missing-health-column
fixtures as well as malformed count/envelope coverage. Do not replace this
with an exception-to-absence fallback. This is bounded operational validation,
not proof that every trigger definition is authentic under arbitrary privileged
schema tampering. Remote migration/trigger acceptance remains separate.

## Paths traced and assessment

| Contract | Source assessment |
| --- | --- |
| Repeated contact revoke | `AFTER UPDATE OF` contact fields with NEW flag zero clears health even when already revoked, then holds allowed global state. No OLD-to-NEW transition assumption. Other-gate/canary SQL does not name contact fields and does not erase health. |
| Migration and prior correction | Final migration revoke/hold remains unconditional; every-global-allow INSERT/UPDATE guards from 212cfe0 remain intact. No historical contact lease or human commitment is imported. |
| Idle without adoption | Pre-0009 catalog absence or empty v1 inventory plus exact one global held row is required. Errors, unknown-version inventory and allowed/missing global state deny. No routing reads, routing credentials requirement or D1 writes on idle. Executable migrated-view validation is the finding above. |
| Atomic adoption | Expected current UUID or true absence (`NONE`) is evaluated in the same INSERT/UPSERT statement. Stale queued adoption cannot replace a newer contract. New UUID, ledger and triggers bind replacement, clear evidence and hold. One exact UUID readback resolves ambiguous adoption without repeating the write. |
| Provider mutation barrier | Both `apply` and `request-verification` reach invalidation first; audit skips it. The barrier checks supported catalog/trigger presence, updates revocation once, and requires acknowledged one-row change plus exact held/no-health/actor-case readback. Even committed-but-response-lost invalidation blocks provider mutation. Default step-success dependencies preserve that order after errors/cancellation. |
| Human coverage | New manual workflow defaults revoke; affirmative coverage supplies exact UUID and explicit phrase. Existing helper checks both and SQL binds current policy. Legacy generic workflow cannot verify contact with missing new fields. Revocation does not need phrase/UUID and never unholds. A phrase records assertion, not observed mailbox visits. |
| Shared exclusion | All six workflow-level groups resolve to the same realm key; role forwarding fixes production and scheduled health falls back to production. Running work is not auto-canceled. Realm separation is intentional. External dashboard/raw SQL/other repositories are not serialized. |
| Health and failure | Provider failures record unverified/hold when D1 is reachable; exact scoped readback is required before announcing a renewal. Failed or missing runs cannot extend expiry. D1 outage cannot promise immediate revoke; old expiry remains the bound. Later success does not restore human acceptance or unhold. |
| Privacy and entry | New inputs are identifiers/opaque references, not mailbox content; values enter env, not interpolated shell. New helpers emit fixed labels, suppress provider bodies and reject redirects. No artifacts/summary exports added. New manual jobs require main and protected realm; hourly lane intentionally lacks review-dependent Environment. |

The barrier's clear-health behavior removes the old-evidence hazard without
adding another mode/lease. Shared exclusion is essential: otherwise a checker
started before invalidation could write an unchanged-contract observation
afterward. Current GitHub paths prevent that overlap. Raw/external mutation
still requires the documented freeze and invalidate-before-change discipline;
do not claim global distributed locking from a repository concurrency key.

## Hosted evidence and operational obligations

1. Run the exact integrated candidate's normal non-mutating hosted suite and
   independent workflow syntax guard. Source-string assertions do not establish
   provider execution or Actions protection configuration.
2. Obtain real held D1
   migration/splitting/trigger acceptance. Source changes to an already-applied
   migration would need an additive follow-up; no deployment is assumed here.
3. Register reviewed workflows on default main; privately verify existing
   repository Secrets and Environment restrictions. Same-named Environment
   overrides must not silently split manual and hourly credentials/destination.
4. Verify specific run/attempt outcomes. Shared default concurrency keeps one
   pending run, and newer work can replace that pending run despite
   `cancel-in-progress: false`. A queued emergency revoke/hold is not executed
   evidence or a response SLA. This documented limit is not a new source
   defect; operational response must not depend on dispatch alone.
5. Keep actual adoption and affirmative coverage blocked pending owner
   commitment and independent operational review. Keep global sending held
   through privacy, serving topology, protocol/outbound and publication gates.
   Old-binary rollback remains held-only. Do not regenerate historical receipts
   or blindly retry ambiguous provider effects.

## External grounding

Official primary documentation fetched on 2026-10-01:

- [GitHub concurrency](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#concurrency)
  confirms repository grouping and default pending replacement; the source does
  not opt into any expanded queue. This is exclusion, not durable dispatch.
- [GitHub schedule](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
  confirms default-branch execution, load-related delay/drop and public-repo
  inactivity disablement. Minute 17 reduces one load pattern, not expiry risk.
- [GitHub manual dispatch](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
  requires default-branch registration; choosing another ref does not defeat the
  reviewed main job/helper constraints in trusted source.
- [D1 SQL statements](https://developers.cloudflare.com/d1/sql-api/sql-statements/)
  supports schema inspection on a SQLite-based engine; this does not prove this
  actual remote migration or its trigger splitter passed.

The established distinction between control-plane configuration evidence and
user/human outcomes remains central (the existing architecture's Gray Failure
research framing). No speculative new academic scheduler or agent machinery
would remove pending human ownership or make Actions an emergency SLA.

## Correction review: 9cd9c4b

The empty-policy migrated branch now executes fixed `IDLE_READY_SQL` against
the actual readiness view before the legacy held proof. `one_row` enforces a
singleton object; exact dictionary equality plus `type(...) is int` rejects
extra keys, missing keys, booleans, string counts and nonzero readiness. A view
or referenced health-column preparation/execution error reaches `main`'s fixed
failure exit rather than becoming absence. Pre-0009 idle behavior remains
unchanged and does not query a nonexistent contact view. Adopted policy still
uses the strict normal observation path, not this idle assertion.

Added synthetic fixtures preserve matching catalog names while substituting
a nonzero view, a view referencing an absent relation, or a health table missing
the view's required fields. These test the failure mechanism rather than merely
checking presence of the new SQL string. They were inspected, not executed.
Existing tests provide the valid empty-policy/pre-migration held path. The
correction does not add routing access, D1 writes, acceptance or unhold.

**GO for the corrected integrated candidate's non-mutating hosted source checks.
NO-GO for actual adoption/live activation/public unhold remains unchanged.**
Runtime proof of migration definitions remains necessary; executing the view is
not cryptographic authentication of every schema object against arbitrary
privileged rewriting. No new issue warrants reopening the settled 212cfe0
every-global-unhold source correction.
