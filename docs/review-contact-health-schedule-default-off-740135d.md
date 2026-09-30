# Independent review: default-off direct-contact health schedule

Date: 2026-10-01. Base: `de2caf2`. Reviewed implementation:
`740135dc1c752ec74ec78b24b3449e55f073b0f5`; reviewed documentation follow-up:
`8372a5910cf913be813375013f3bc104ef1f9047`.

## Decision

**GO for narrow source integration and non-mutating hosted checks.** No
substantive unresolved defect was found within this change. **NO-GO for
schedule activation, adoption, affirmative coverage attestation, public
release or unhold without their separate operational readiness evidence.**
This review did not run tests, builds, operational workflows, provider calls,
database queries, deployments, pushes, mailbox retrieval or sends. Only this
review artifact was written. The production run mentioned in the operational
document was not independently retrieved or verified.

## Evidence and boundaries

The base-to-tip diff changes only `direct-contact-health.yml`, its existing
source-contract test module, and `direct-forward-contact-workflows.md`.
The prior contact/schema review was consulted; this patch neither reopens its
resolved executable-schema finding nor changes the helper or SQL model.

| Contract | Static assessment |
| --- | --- |
| Default-off schedule | The sole `refresh` job's `if` requires the existing main ref plus either manual dispatch or schedule with `vars.AMAIL_CONTACT_HEALTH_ACTIVE == 'true'`. An unset effective variable is empty and does not match. False, whitespace-padded true and unrelated values do not grant schedule admission. |
| Skip before capability use | The activation guard is at job level, not inside the helper or a secret-bearing step. A skipped schedule executes no checkout, Python helper, D1 query or provider read. All existing credential references remain confined to the skipped job's step. This is not a claim that GitHub itself cannot access repository Secrets. |
| Manual path | Manual staging/production choices remain unchanged and do not depend on the activation variable. The full existing main-ref condition applies to both event alternatives, rather than only one side of the OR. |
| Existing behavior | Cron minute 17, repository-level Secrets, production fallback, GET-only/scoped-health helper, timeout, permissions and shared non-canceling realm concurrency remain unchanged. No release predicate, SQL guard, attestation or unhold path changes. |
| Activation discipline | Documentation requires production migration/schema, exact global-held readback, continuing Inbox/Junk and 24-hour response coverage, and a successful controlled manual production observation before opting in. Staging evidence does not substitute. These are operator prerequisites, not newly enforced database predicates. |
| Variable semantics | Documentation explicitly recognizes case-insensitive equality and inherited organization variables. Absence of a repository override is not default-off if a same-named organization variable is already true; use a repository false override until ready. Actual variable configuration is outside this review. |
| Disable/recovery | Disabling future job admission cannot recall an admitted run or instantly revoke existing health. Documentation preserves explicit revoke/hold and expiry response; success never unholds. |
| Test intent | The new test isolates the job, requires exactly one job-level guard of the specified grammar, pins constants/parentheses, then models 96 combinations of refs, events and variable values. It does not call providers. Existing hosted `infra/tests` discovery includes this module. No test result is claimed. |

The test is a narrow source contract plus a synthetic expression model, not
execution by GitHub's expression engine. Independent hosted YAML/workflow
syntax validation and the exact candidate's non-mutating hosted suite remain
necessary evidence. No material research uncertainty justifies expanding this
small operational fix into an architecture change.

## Documentation correction

The first candidate retained a rollout sentence expecting newly registered
hourly runs to report `unadopted_held`. Review pointed out that default-off runs
are now skipped. The docs-only follow-up corrects this: controlled manual
observation may prove idle, while automatic activation waits for the separately
stated readiness conditions. This concern is resolved, not an open blocker.

## External semantics checked

- [GitHub variable documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-variables): unset configuration variables evaluate to empty strings; job conditions are processed before dispatch to a runner; scope precedence matters.
- [GitHub expression operators](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions#operators): grouping and logical operators support the guard; string equality ignores case.

These official platform contracts, rather than an unrelated academic analogy,
are the relevant external evidence for this two-line workflow change. Existing
runtime/SQL contact safety remains governed by the prior implementation and
independent review, not by an activation variable.
