# Frozen staging predecessor binding policy

## Scope and immutable provenance

The isolated change starts at source `1a77a50`. The parent handoff is
`held-staging-mail-promotion-2026-10-01.md`, committed in the primary repository
at `ae46ec4`. Immutable `daaab1f79cd985030d8d502fd647e16757673052` and retained
phase evidence of hosted operation `36761367007` establish the exact 14-binding
pre-write match for staging version `c3f6401a-1e84-4f51-91df-ae77d90683e9`.
The operation subsequently failed privacy acceptance. This is historical binding
provenance only, not fresh provider evidence, current privacy or retry authority.

## Implementation and caller audit

`pin_staging_mail.containment_predecessor_bindings()` returns a fresh literal
contract independent of current TOML. `containment_bindings_match()` accepts
only the fixed c3f version; it has no realm, dispatch configuration or fallback.
The existing pure comparison is shared privately by both explicit policies.
The current `expected_bindings()` policy remains direct-only, including its
single Mail D1 guard and strict queue-api producer identity.

Explicit historical selection is limited to settings-v1 containment verification,
legacy settings correction, current-resource correction, and GET-only preflight.
Both correction helpers retain their before/after version comparisons. Diagnostic
shape classification uses the same frozen expected list. Source search identified
no further historical no-argument deployment caller: ordinary Mail pin and test
provenance retain current policy; production graph and trace rollout explicitly
select queue-api. No configuration, privacy predicate, attestation parser,
mutation payload, output label, deployment workflow or permission was changed.

## Synthetic source coverage and verification limit

The literal fixture is independent of current TOML and the historical factory.
Hosted regressions cover exact old success, current direct-only/queue-api
separation, wrong/missing/extra/duplicate bindings, version/target/type/shape
drift, production mismatch, config independence and fresh factory ownership.
Existing historical helper fixtures now consume the literal fixture; existing
before/after bracket and redacted-output assertions remain. Settings-v1 tests
add literal historical bindings with missing/null/true Issues and immutable
failed-run/missing-marker provider-read refusal, plus default-kind separation.

By explicit parent instruction, no local project tests/build were run. Source
review and `git diff --check` are the available local verification; hosted
synthetic execution is still required before integration acceptance. No provider
operation, mail operation, PATCH retry, push or deployment was performed or
authorized. The immutable containment-evidence gap remains blocking rollout.
