# Fresh held bootstrap: independent source validation plan

Date: 2026-10-01. Baseline: `da6bb3c`. This is source and hosted-synthetic
validation, not authorization or evidence of actual provider bootstrap.

## Expected behavior and independent basis

The owner-approved first-bootstrap contract is recorded in
`fresh-mail-bootstrap-workstream.md`. The maintainer lane and infrastructure
ledger require hosted runtime tests, a single original build, immutable artifact
coordinates, retained original stores, held sending, and no ambiguous replay.
These are the expected results; existing implementation behavior is not the oracle.

The critical distinction is between syntax and authority: constructing `Epoch`
or `Scope` validates coordinates but does not establish successful CI or creation.
The controller must verify original same-run full-gate evidence and complete OLD
scope prerequisites before allocation; only successful create plus exact provider
readback can establish a new resource witness. NEW-scope migration and held-empty
verification must address the new database, never silently recheck the original.

## Discriminating synthetic checks

| Boundary | Positive expectation | Negative control |
| --- | --- | --- |
| Hosted source/artifact | Exact current source, run, attempt one, original artifact ID, compiler and hash | Failed/skipped source gate; ancestor artifact; altered run/hash/compiler |
| Original storage | Complete empty inventory, explicit held policy, no grant, no Mail owner-state/mail/journals/reservations; unattached routing and unchanged sending prerequisites | Retained Mail owner state with otherwise empty mail; failed/incomplete inventory; attached routing; enabled policy/grant |
| New storage | Fixed source/run-derived names, response-bound new D1/R2 scope | Original/staging D1 substitution; arbitrary operator names |
| Write sequence | Durable intent before each one-attempt write; new held checks before scripts; exact readback before receipt | Timeout/nonzero submit, failed readback, incomplete result: no successful receipt or retry |
| Recovery | Read-only bounded observation from owned original coordinates | No create/deploy/delete; absent or failed read cannot authorize replay |
| Workflow | Full CLI/Worker/build/site/infrastructure dependencies, fixed same-run artifact restore before provider credentials/steps, shared workflow writer group | Nested same-group lock, floating builds, early secrets, rerun admission |
| Compatibility | First receipt remains paused, activation not granted, original stores retained, v1 untouched | Any implicit activation, old store deletion or changes to v1 admission |

Mock adapters must expose event order and exact resource identities. A mock that
returns a receipt without independently asserting its inputs cannot prove the
contract. Provider transport/readback tests are owned by the respective modules;
controller tests cover their orchestration and rejection boundaries.

## Execution and limitations

No local tests, imports of production modules, dependency installs, builds,
provider reads/writes, Actions dispatches, mail or account operations are allowed
in this task. Local checks are source inspection, AST parsing and `git diff
--check`. Parent integrates the tests into credential-free hosted source CI.
Until exact hosted commands and outcomes are recorded, tests are authored, not
passed. Even a successful synthetic run cannot establish fresh provider creation,
actual paused deployment, drain, activation or source adoption.

The existing opaque-domain old-scope reader failure must remain a hard blocker.
No synthetic fixture or source test is evidence that this runtime debt is fixed.

## Authored artifact status

The controller and workflow contract drafts are isolated in
`infra/tests/test_fresh_mail_bootstrap.py` and
`infra/tests/test_fresh_bootstrap_workflow.py`. The positive orchestration check
requires sink → maintenance → API submission, exact new-scope arguments, all
three pinned script identities at readback, and no receipt before full readback.
These mocked checks intentionally do not claim provider parsing or migration
correctness. Recovery fixtures await the concrete durable-journal interface;
absence of such a fixture is an explicit coverage gap, not a passing result.
