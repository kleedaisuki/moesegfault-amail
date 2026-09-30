# Review: explicit production binding contracts (`dfa727e`)

Date: 2026-10-01. Verdict: **GO for non-deploying hosted source checks only.**
No substantive defect was found in this shared-checker slice. This is not
production deployment approval, a passing hosted-test result, or provider/privacy
acceptance.

## Scope and method

Reviewed the exact three-file change in `dfa727ec34d2fc3b9a9e8d09f68a7adac76568e7`:
`infra/deploy/pin_staging_mail.py`,
`infra/deploy/verify_role_monitor_staging.py`, and
`infra/tests/test_production_role_bindings.py`. Traced existing staging callers,
their fixtures, the Mail and role Wrangler configurations, and the production
graph-transition design. Static `git diff --check` passed. No local tests/builds,
provider requests, live deployments, secret reads, or production edits occurred.
Unrelated concurrent working-tree changes are outside this review.

## Checked contracts

- Existing staging positional/default calls still select staging. The historical
  pre-Queue `bindings_match()` path still invokes `expected_bindings()` without
  arguments, preserving the existing zero-argument fixture/containment contract.
  Queue-phase callers retain the exact staging Queue name and reviewed ID check.
- Production Mail derives D1, R2 and plain-text values from top-level reviewed
  configuration; its extra `OFFICIAL_EMAIL` is required, not tolerated as an
  arbitrary extra. Exact binding count/name/type checks remain. The official
  sender requires the singleton `mail@moesegfault.dev` allowlist; a missing or
  broader list fails. Destination-bound Mail send bindings remain rejected.
- Production Queue naming is explicitly `amail-trace-events`; staging remains
  `amail-trace-events-staging`. Queue pin validation is unchanged, not replaced
  by matching only a resource name.
- Role immutable-version binding checks pass the selected realm and reviewed
  database pin through to the same pure checker. Production requires the
  official sender allowlist and excludes the staging-only fault secret. Added
  duplicate-name rejection prevents contradictory realm/resource rows from
  satisfying independent existential checks. Existing staging minimal fixtures
  need not suddenly include a sender allowlist; an explicitly present wrong
  list is still rejected.
- No collector, route, topology, lease or release gate is removed. The change
  adds no provider calls or success markers. Original-context privacy checks
  still require separate effective current-resource capture-off evidence.

## Integration obligations and verification limits

The role helper's `database` remains an explicit independently reviewed caller
pin, with the historical staging default. Selecting `realm="production"` alone
does not select the production database automatically. The upcoming production
caller must pass the production D1 ID from reviewed configuration, never adopt
the ID from provider readback. This slice's new test supplies that explicit pin;
the later orchestration must receive independent review.

New fixtures exercise production API acceptance/staging rejection, omitted
official sender rejection, role production acceptance, forbidden fault and
duplicate rejection, and staging-default rejection of production rows. Existing
fixtures cover incorrect D1/Queue resources and current-resource collector
checks. These are source-inspected expectations, not executed results. Hosted
source checks should run both existing suites and the new suite before any
dependent live operation. Exact source, serving versions, graph topology,
whole-record privacy, role lease/arrival state and actual delivery remain
separate production acceptance obligations.

## External references

- [Cloudflare send binding configuration](https://developers.cloudflare.com/email-service/configuration/send-bindings/): sender and destination restrictions are distinct attributes. The sender singleton checked here is an explicit capability restriction, not proof of actual delivery.
- [Cloudflare bindings](https://developers.cloudflare.com/workers/runtime-apis/bindings/): bindings grant access to resources; name matching alone is not resource identity validation.
- [Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/): platform mechanisms and controlled bindings support the chosen design; generic logging advice does not supersede this project's stricter original-context privacy boundary.
