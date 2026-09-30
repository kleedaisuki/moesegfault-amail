# Independent review: bounded staging native D1 provider proof

Date: 2026-10-01. Scope: the uncommitted native proof slice in the isolated
`.temp/quota-d1-native-proof` worktree: `staging_ten_address_d1_proof.py`, its
unit-test source, `staging-ten-address-d1-proof.yml`, and the `query_result`
extraction in `staging_ten_address_escrow.py`.

## Decision and evidence boundary

**No substantive outstanding blocking defect found in the inspected source paths. GO for
this bounded source slice, not a claim of hosted/provider success or authorization
to dispatch it. Real quota acceptance/recovery remains outside this approval.**

The review inspected the diff, escrow implementation, additive migration,
manifest/provenance/checkout/HTTP helpers, workflow and test source, relevant
existing escrow design/reviews, and public official Cloudflare documentation.
No local tests/builds, application provider API requests, workflow dispatch,
migration, secrets access, push or deploy were performed. Public documentation
retrieval is not a Cloudflare account/control-plane request. All test observations
below concern inspected test code, not executed results. Only this review artifact
was written; production source was not modified.

## Safety and correctness assessment

| Contract | Inspected evidence and result |
| --- | --- |
| Explicit migration | `guard()` requires manual first-attempt dispatch, exact repository/branch, hosted runner, staging environment and mode-specific confirmation before capability extraction. Workflow guard/test steps precede its sole Secrets-bearing execution step. Only `execute('apply-schema')` invokes `Provider.apply()`. |
| DB and Worker identity | Fixed D1 UUID is inherited from reviewed staging readback. `provenance()` also checks DB name, exact `amail-mail-staging` script, single 100% deployment/version through existing `serving_deployment()`, version ID and its sole D1 binding named `MAIL_DB` with exact UUID. Deployment is read again inside each provenance call, and the full tuple is compared before/after work. Global sending state must read exactly `held`. |
| Additive DDL and drift | Both original and synthetic namespaces must be absent or exactly equal before any CREATE. A second read precedes each namespace application and again requires absence or exact expected equality before skipping an existing namespace; each object is applied once in migration source order. Partial, extra or drifted namespaced objects fail; there is no IF NOT EXISTS, DROP, repair/retry or rollback. A lost DDL ACK may leave a partial namespace and intentionally blocks subsequent automatic application. Ordinary tenant migration streams are unchanged. |
| Synthetic-only writes | Normal query whitelist contains mirror-renamed source-owned statements, fixed schema inspection and global hold read. Original escrow INSERT/receipt/purge and arbitrary SELECT are not admitted. DDL capability is distinct. Mirror tables, indexes, triggers, foreign keys and embedded namespaced references derive from the same reviewed migration by fixed prefix substitution. |
| Synthetic terminal versus cleanup | `SyntheticEscrow` removes `purge` from available operations. `read-terminal` calls the existing private receipt mechanics only on synthetic tables, retains complete ciphertext, and emits fixed-field public synthetic-mechanics evidence JSON. It does not execute or attest real mailbox cleanup. Invented manifest owner/object IDs and public fixture key never come from a real recovery key or owner authentication. No artifact upload/attestation is implied by using run ID as a synthetic artifact field. |
| Native HTTP shape | Requests go through existing one-request, bounded, no-redirect/no-retry REST helper, with fixed account/DB endpoint and SQL/parameter/body limits. Shared `query_result()` requires successful outer and single inner envelopes, dictionary rows, metadata and an actual nonnegative integer changes counter; extra metadata is tolerated. Missing/boolean/string changes cannot manufacture an ACK. |
| Cross-dispatch persistence | Write requires an absent original-run mirror parent, encrypts a two-chunk invented fixture, seals/attaches/arms it and discards Arm authority. Later read independently verifies the original attempt-1 manual proof workflow/run, requires completed status and decrypts persisted bytes. Expected fixture binds the original run's SHA, not the later reader SHA. Reader run/SHA are bound into terminal receipt; full original ciphertext is read again after terminalization. |
| Failures and retention | Transport/provider errors stop without exposing provider response bodies. Top-level failure emits one fixed label and returns failure. There is no automatic arm/receipt replay, DELETE, TTL, mutation callback or rollback. Both complete schemas are rechecked after the phase before final provenance and evidence return. A failed final schema/provenance read may leave a committed synthetic or DDL state, but cannot produce the success label. |
| External contracts | Escrow parser extraction tightens malformed row/envelope rejection while preserving expected successful native envelopes; ordinary Worker APIs, bindings and user-facing SQL tables are unchanged. Workflow grants only contents/actions read and serializes with existing native acceptance concurrency group. |

## Test-source assessment and remaining evidence

The new fixture deliberately patches transport below request encoding and native
response parsing. Its SQLite setup enables foreign keys. Inspected tests cover
full-chunk/partial-tail roundtrip, terminal ciphertext retention, zero original
escrow rows, absence of DELETE, mirror purge rejection, exact-schema no-op,
drift/partial-schema stop, lost migration ACK, lost receipt ACK without replay,
real/generic SQL rejection, selected guard failures and workflow secret boundary.
Existing escrow tests also inspect invalid changes-counter native envelopes.

Two limits should remain explicit:

1. SQLite plus fabricated native envelopes is not actual D1 evidence. Current
   provider DDL acceptance, metadata availability/counters and latency remain
   unobserved. The public API documents `meta`/`changes` as optional, so rejecting
   their absence is deliberately fail-closed, not a promise they always exist.
2. Updated test source now exercises two `execute()` phases over the native JSON
   facade, rejects an original run still in progress before receipt writes,
   compares envelope digest across terminalization, and explicitly reports no
   real cleanup attestation. It also adds DB UUID/name/binding provenance cases,
   native lost-arm ACK and malformed native-envelope cases. The cross-dispatch fixture now uses distinct writer/reader SHAs and asserts original/source SHA separation. Split/changing deployment cases
   also remain source-inspection evidence rather than direct new tests.

### Resolved finding in the updated test source

**Resolved P1, high confidence: missing native deployment strategy in provenance success
fixture.** In `test_exact_native_database_binding_and_deployment_relation`,
`serving['deployments'][0]` lacks `strategy='percentage'`. Existing
`pin_staging_mail.serving_deployment()` immediately rejects any other/missing
strategy, so the first expected-success provenance call raises
`d1_proof_worker_unverified`, failing the required hosted pre-provider test step.
The author added the actual native strategy field to the fixture; a subsequent source inspection confirms `strategy: percentage` is present. This finding was established
by executable source tracing, not by executing the test. No production safety
failure is implied; the workflow fails closed before provider access.
Original run conclusion is not required to be success. This is coherent with
retained-state recovery: a completed failed original run may already have a
sealed/armed mirror record, and the later reader independently authenticates
its exact fixture and permitted state. It still cannot terminalize a partial
writing record or an already terminal record. Those unsupported recovery cases
stop for manual review rather than silently reopening permission.

## Operational interpretation

The control-plane token is not SQL/table-scoped. Fixed source-owned capabilities
and protected workflow provenance constrain this program, not the credential's
IAM authority. An external administrator can still race changes; before/after
readbacks detect many changes but do not create a global lock against unrelated
provider operations. This source is a bounded synthetic provider discriminator,
not an exactly-once external-mail transaction or full failure-escalation proof.

Retained synthetic terminal records consume the mirror's budget; no purge is
available here. Repeated proofs are therefore intentionally finite. A failed
write can leave the mirror's one-outstanding index occupied. Do not treat that
condition as permission for an unreviewed DELETE or repair script. Likewise,
partial real DDL requires explicit operator review rather than retrying dispatch.

The next admissible evidence, if separately authorized, is hosted source CI and
then separately confirmed schema / synthetic-write / later synthetic-read runs.
Their outcomes must be recorded independently; none follows from this review.

## External grounding

- [Cloudflare D1 query API](https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/): native single-query result structure; optional metadata and changes based on SQLite total changes. Exact ACK plus authenticated readback is meaningful only with this exact validation-only trigger schema.
- [Cloudflare Worker versions and deployments](https://developers.cloudflare.com/workers/versions-and-deployments/): version-scoped bindings represent configuration, while D1 storage state is not versioned with Worker code; hence explicit DB schema/state readback remains necessary.
- [Cloudflare Workers API](https://developers.cloudflare.com/api/resources/workers/): version resources/bindings and D1 binding identity. Malformed or unavailable metadata fails closed; no compatibility workaround was assumed.
- Existing repository review `review-staging-quota-d1-escrow-source-901327a.md` relates the conservative ambiguous-arm rule to [RIFL, SOSP 2015](https://web.stanford.edu/~ouster/cgi-bin/papers/rifl.pdf). This change preserves that narrower rule rather than claiming exactly-once downstream mailbox effects. No new academic result is asserted.




## Final incremental closure

The author subsequently tightened the second pre-CREATE/existing-schema read in
`Provider.apply()` to reassert exact equality, and added an exact two-namespace
schema readback in `execute()` immediately before final provenance/success
return. Static reinspection confirms both changes fail closed on detected drift
without adding retries, repairs or broader SQL capabilities. No additional
substantive issue was found. This incremental closure also used no test execution
or application provider requests.
