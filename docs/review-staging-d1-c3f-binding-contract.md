# Independent review: exact c3f D1 proof and inspection binding gate

Date: 2026-10-01. Candidate `c66c973fcb62f498ebc1814cdb54e07b41de93e2`,
parent `48f960b44da454140aa7140870267be5f0ceda7d`.

## Decision

**Source GO, subject to green hosted synthetic tests at the final integrated
SHA.** No substantive defect was found in this six-file bounded correction.
**Operational NO-GO:** this review grants no dispatch, DDL, correction replay,
privacy acceptance, mail/role operation or live quota-acceptance authority.

No local project tests/build, provider queries, private log/body access, push,
deployment or migration were performed. Tests below were inspected, not run.

## Scope and evidence

Reused the native-proof design and read-only discriminator review, plus the
previous exact historical-binding review. Inspected all six candidate changes,
shared `containment_bindings_match`, literal historical fixture, provenance
import path, workflow guards/test discovery, and original immutable
`242b5abfee461d04188757e8b365d387d46fcdf9` control flow.

| Boundary | Assessment |
| --- | --- |
| Selected policy | Both `Provider.provenance()` and `ReadOnlyProvider.binding()` explicitly invoke only the existing historical matcher. It requires exact c3f response/expected version and the complete frozen 14-binding contract. There is no direct-only fallback, optional role or arbitrary-version acceptance. |
| Native identity | Fixed MAIL_DB/ROLE_MONITOR targets are compared using native `database_id`, not the former local `id` assumption. DB GET separately requires fixed Mail DB UUID/name. |
| Current deployment | Shared current `expected_bindings`/`bindings_match`, runtime and Wrangler config are unchanged. Current direct-only and queue-api policies do not acquire a historical role capability. |
| Read-only capability | The inspector retains its independent endpoint/SQL allowlist, fixed Mail DB, two SELECTs, exact parameter pairs, zero-change requirement and absence of DDL/writer methods. Historical role metadata does not provide role SQL access. |
| Existing writer | The proof's existing DDL and synthetic SQL allowlists, mode confirmations, protected environment, source evidence, sending hold, provenance brackets and workflow permissions are unchanged. Removing the erroneous precondition permits an otherwise separately authorized original operation to proceed; this is not new authorization. |
| Failure handling | Failed historical binding validation still precedes held/schema SQL. Inspector stop labels remain categorical, leave later phases not_checked and return no mutation authority. |

## Historical no-DDL conclusion: exact limit

At original immutable `242b5ab`, `execute('apply-schema')` invokes
`Provider.provenance()` before `Provider.apply()`. Construction performs no
schema write. The old sole-D1 predicate occurs before even the held SELECT;
schema SELECT/CREATE occur only after provenance returns successfully.
Therefore, **if the original provenance read observed the documented two-D1
c3f inventory, that run could not reach any schema write**. This implication
is source-checkable and does not need an invented no-op acknowledgement.

The later parent-supplied inspect `36788755759` binding=unverified observation
establishes its own stop before held/schema queries. It does not independently
timestamp the earlier version response, locate the original generic failure,
prove current schema absence or exclude another writer. Candidate documentation
preserves these conditions explicitly. An unconditional historical no-DDL claim
still requires independently retained original-serving relation evidence.

## Fixtures and acceptance

Both metadata fixtures now use the existing independent literal historical
fixture; neither generates a passing response from production matcher/current
TOML. Inspected assertions cover c3f success, wrong Mail/role target, removed
role/direct-only inventory, duplicate/extra binding and another otherwise
matching version. Inspector rejection additionally asserts no SQL calls and
unobserved held/schema stages. Existing schema classification, parameter-shape,
read-only capability and stability tests remain semantically unchanged.
The existing workflow discovers both changed test files; fixture module import
matches its `unittest discover -s infra/tests` setup.

These are source findings, not passing test or provider observations. Require
fresh exact-SHA hosted source CI and separate operator authorization before any
new inspect. Do not repeat apply-schema as diagnosis. No Issues-off evidence,
successful DDL observation or live schema state is supplied by this correction.

References: [native-proof record](staging-quota-d1-native-provider-proof.md),
[read-only review](review-staging-quota-d1-readonly-discriminator.md),
[frozen predecessor](historical-containment-binding-contract-2026-10-01.md).
