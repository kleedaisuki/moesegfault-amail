# Explicit staging D1 schema and synthetic provider proof

Date: 2026-10-01. Status: **original schema dispatch failed; read-only incident
discriminator implemented and independently reviewed (Source GO); exact hosted
source CI / separately authorized inspection still pending**. No local project
tests/builds, provider operations, migration, workflow dispatch, push, or deploy
were performed while authoring this slice. Live ten-address acceptance remains
**NO-GO**. This is not a 24-hour accountable-intake demonstration.

## Reused knowledge and the exact gap

Reuse `staging-quota-d1-recovery-escrow-design.md`, the escrow source review,
`staging-quota-d1-artifact-expiry-recovery-architecture.md`, and terminal
retention correction `6bcf05c`/review closure `b373c35`. Existing hosted test
source exercises SQLite and real AES-GCM but is not a native Cloudflare D1
DDL/REST observation. The new manual path targets that provider gap only.

The actual recovery terminal check set, `quota-readonly-native-teardown-v1`,
requires concrete independent mailbox/provider recovery and native teardown.
An invented ciphertext roundtrip cannot manufacture that evidence. Therefore
the proof uses a **fixed synthetic mirror namespace**, not real escrow rows.

| State | Resource | Permitted operation | Meaning |
| --- | --- | --- | --- |
| Real schema | `staging_acceptance_*` | Explicit additive CREATE and complete DDL readback only | Native compatibility of checked-in operations schema; no record admission |
| Synthetic schema | `staging_d1_probe_*` | Same DDL with only fixed namespace substitution | Representative identical SQL/constraint/trigger mechanics |
| Synthetic encrypted fixture | Mirror tables only | Insert chunks, seal, attach synthetic numeric ID, one-time arm, read and terminal receipt | Native response/readback mechanics, **not** an immutable artifact or mutation permit |
| Real mailbox/alias/send/recovery | No capability supplied | None | No acceptance, cleanup, or expiry-recovery claim |

The mirror receipt contains the existing check-set string to exercise the exact
reviewed DDL and terminal validator. Its table namespace, public fixture key,
generation `synthetic-d1-provider-v1`, and evidence field
`real_cleanup_attested: false` identify it as synthetic. The actual coordinator
queries only the real namespace and cannot consume this receipt. No real
`writing`, `sealed`, `armed`, or `cleanup_verified` record is written by the
proof, so it cannot occupy or release the real outstanding-campaign slot.

## Fixed resources and execution admission

`infra/tests/staging_ten_address_d1_proof.py` and
`.github/workflows/staging-ten-address-d1-proof.yml` are the only entry point.
There is no generic SQL, database/table selector, mailbox API, mail-send
callback, alias mutation, recovery-key access, artifact upload, issue creation,
automatic scheduled dispatch, deployment, or ordinary migration integration.

Every mode requires all of:

1. Hosted GitHub runner, exact repository `kleedaisuki/moesegfault-amail`, branch
   `refs/heads/codex/amail-v0.1.0`, manual `workflow_dispatch`, and attempt 1.
2. Protected `staging` environment and mode-specific exact confirmation, checked
   in an independent before-Secrets step and again in the program.
3. Actual git checkout equals the current run's SHA; independent GitHub current
   run-attempt relation points to this fixed proof workflow at that SHA.
4. Existing `successful_source` gate: all six source jobs and real-cipher step
   passed at this exact SHA. Integration/cherry-pick changes the SHA and requires
   fresh exact source evidence; a worktree commit is not a deployable attestation.
5. Protected existing `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` only.
   No recovery, login, routing, R2, mail-send, or new credentials are requested.
6. Native DB GET returns UUID `74f35f95-42ce-482c-86e6-dffbdd35cbbe` and name
   `moesegfault-mail-staging`. This pins the target even though account ID comes
   from an existing protected Secret and the token itself is not table-scoped.
7. `amail-mail-staging` has one 100%-serving deployment; its exact version has
   exactly one D1 binding, `MAIL_DB`, with the fixed DB UUID. Repeat deployment
   GET brackets the version, and complete provenance is repeated after the
   phase, rejecting changed deployment/version or a non-held sending singleton.

All proof modes share `staging-native-mail-acceptance` concurrency, with
`cancel-in-progress: false`. This serializes participating workflows, not
arbitrary external control-plane writers. Require operational exclusion from
other staging administration while demonstrating. It does not make a D1
transition plus an external mail mutation atomic; this workflow performs none.
This narrow synthetic path checks actual Mail/DB binding and held policy,
not full three-service/capture-off or authenticated-owner campaign admission.

## Original independently confirmed manual phases (not a retry plan)

| Mode | Exact confirmation | Inputs | Expected fixed result |
| --- | --- | --- | --- |
| `apply-schema` | `APPLY_STAGING_D1_ESCROW_SCHEMA` | Exact successful `source_run`; empty `prior_run` | `d1_proof_schema_verified` |
| `write-synthetic` | `WRITE_STAGING_D1_SYNTHETIC_ONLY` | Exact successful `source_run`; empty `prior_run` | `d1_proof_synthetic_armed_retained` |
| `read-terminal` | `READ_TERMINAL_STAGING_D1_SYNTHETIC_ONLY` | Current exact successful `source_run`; exact original synthetic `prior_run` | `d1_proof_cross_dispatch_terminal_ciphertext_retained` |

### Default-branch workflow registration is a separate prerequisite

GitHub's [official workflow-trigger documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)
requires a `workflow_dispatch` workflow file to exist on the repository's
default branch before it can receive manual events. The workflow was subsequently registered on `main` at `de2caf2` (parent supplied
registration evidence; not re-observed by this implementation workstream).
A workflow existing only on the feature branch would **not be dispatchable**, even with
`gh workflow run ... --ref codex/amail-v0.1.0`. A successful feature-branch source
CI does not satisfy registration, and `--ref` selects an execution revision; it
does not register an otherwise feature-only workflow.

Registration is separate from execution source: `--ref codex/amail-v0.1.0`
selects that branch's workflow version after its source push; registering an
existing path on main neither deploys source nor authorizes mutation. Preserve
feature-branch/staging/first-attempt gates. An inspect addition does not require
inventing a second workflow name, and must not be dispatched on main where the
feature guard skips the job. Record main registration, exact feature SHA and
successful source CI separately. No registration/push/dispatch was performed by
this discriminator implementation.

The single authorized original `apply-schema` run
[36787173756](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36787173756)
at `242b5abfee461d04188757e8b365d387d46fcdf9` failed only in the final provider
step after before-Secrets guard and hosted synthetic tests passed, according to
the parent-supplied nonsecret step metadata. Its generic fixed failure label
cannot prove that no DDL committed. **Do not rerun apply-schema, write-synthetic
or read-terminal as diagnosis; all mutation state remains unknown until the
separately authorized read-only observation below.** The historical phase table
above explains original contracts, not a standing sequence to execute.

`apply-schema` checks both namespaces before any CREATE. Each must be absent or
exactly match every checked-in table/index/trigger DDL. Existing equivalent
schema is a no-op; unknown, extra, changed, or partial DDL is a hard stop.
CREATEs are separate native requests, not an assumed multi-statement atomic
migration. A committed-but-lost response can leave partial schema: no retry,
`IF NOT EXISTS`, DROP, rollback, ordinary migration runner, production schema,
or automatic repair is provided. Independently inspect and review an exact
restricted continuation if a partial migration occurs.
Both schemas are checked again before successful evidence is returned; a
second pre-CREATE read also compares equality rather than trusting nonemptiness.

`write-synthetic` uses actual AES-GCM from the pinned hosted dependency and
invented owner/username/service revisions plus 80 invented object keys. The
opened manifest is larger than 65,536 bytes and smaller than 131,072 bytes,
so native transport exercises one full 87,384-character base64 chunk and one
partial last chunk. The key is a checked-in **public synthetic fixture key**;
it must never encrypt or decrypt actual recovery/owner material. No real
provider/mailbox baseline is read into the payload. An existing original-run
row is rejected before a fresh nonce is generated. The synthetic artifact ID
is the original proof run ID, not an artifact-presence claim. Known changes=1
and complete authenticated readback are required to arm; its result is discarded.

`read-terminal` runs in a different invocation/process with no retained local
envelope or artifact. Independently read original GitHub run-attempt metadata,
require its original process completed, and bind D1 ciphertext to the original
SHA/run/generation and exactly reconstructed invented plaintext. Original
conclusion need not be success: a cancelled original writer can leave complete
synthetic sealed/armed content. A writing-only/incomplete record remains
blocked. Current SHA may differ from original SHA; it is separately source
tested and never substitutes for the original fixture's SHA. The mirror receipt
is created only after those exact reads; complete authenticated ciphertext is
read again and retained. There is no per-chunk purge, DELETE, TTL, or DROP.

Public evidence JSON emits only fixed mode/result labels, source/schema digest,
synthetic original coordinates, ciphertext length/digest/chunk count and mirror
state/receipt digest. Never emit the account, token, raw SQL/provider body,
plaintext owner/addresses, key, base64 chunk, or full ciphertext.

## Native parser and source-test evidence

The original escrow adapter and proof share `escrow.query_result`, preserving
the native REST envelope with one `result` batch, literal top-level/batch
success, dictionary rows and typed nonnegative integer `meta.changes`.
Missing, Boolean, negative or malformed counters do not become acknowledgements.
Additional native metadata is permitted but does not grant authority. Each
request rejects redirects, is bounded by existing response limits and a
25-second timeout, and is never retried. Commitment after timeout is possible;
retained state/readback never fabricates a lost current-invocation arm ACK.

`test_staging_ten_address_d1_proof.py` is discoverable through the existing
`test_staging_ten_address*.py` hosted source pattern. It authors fixture tests
below actual HTTP JSON encoding/parsing rather than replacing `Escrow._query`:

- Exact DDL application/no-op, extra/partial schema rejection, and lost CREATE
  response retaining partial state without automatic repair.
- Native-shaped multi-chunk create/seal/attach/arm/read/terminal retention,
  formal escrow table remains empty, and absence of any purge capability.
- Native lost arm/terminal ACK, missing counters/Boolean ACK, failed/multiple
  query batches, malformed result rows and fixed capability rejection.
- Manual-only/first-attempt/confirmation guard and workflow Secret boundary.
- Exact native DB UUID/name and Worker D1 binding fixtures.
- Controller write/read-terminal orchestration with independent original-run
  completion requirement, original plaintext binding and unchanged envelope
  digest across separate fixture invocations.

These are **inspected test sources, not executed/passing runs** at authoring.
SQLite plus a native-shaped JSON fixture is not actual Cloudflare evidence.
Pinned actual AES-GCM source CI and future native provider demonstration remain
separate obligations. The native fixture is two chunks, not a measured
31-chunk maximum-envelope provider/latency test. Persistent mirror ciphertext
also consumes finite staging DB storage; it has its own reviewed 16 MiB logical
budget and one outstanding record. Partial writes can block subsequent proofs
until separately reviewed manual reconciliation; never silently abandon a row
or DROP schemas. They do not block the independent real campaign slot.

## Required acceptance evidence and remaining live NO-GO

Before closing this provider gap, retain verified default-branch workflow
registration evidence and its exact commit, then exact hosted CI/dispatch IDs, attempts,
integration/source SHAs and successful step conclusions for all three phases.
Compare write/read-terminal JSON original run, original SHA, envelope digest,
byte length and chunk count exactly. Require schema verification against actual
native DDL and the terminal JSON's `real_cleanup_attested: false` distinction.
Do not treat queued, cancelled, failed or merely registered workflows as passing.

This proves bounded provider schema/REST mechanics and independent-process
ciphertext survival at the observed interval. It does not prove an indefinite
retention SLA, Time Travel restore, a 24-hour elapsed monitor/intake/ack cycle,
actual mailbox cleanup, immutable artifact admission, future mutation race
safety, or live ten-address GO. A full real recovery coordinator and separately
exercised accountable 24-hour intake are still mandatory. No boolean option,
synthetic receipt, successful issue POST, or proof workflow conclusion bypasses
those gates.

## External grounding

- [Cloudflare D1 query API](https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/)
  documents SQL/params, native result/metadata and optional changes based on
  SQLite total changes. Treat it as a narrow checked-schema observation, not a
  universal exactly-once token.
- [Get D1 database API](https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/get/)
  grounds the independently checked UUID/name metadata relation.
- [D1 SQL statements](https://developers.cloudflare.com/d1/sql-api/sql-statements/)
  and [foreign-key enforcement](https://developers.cloudflare.com/d1/sql-api/foreign-keys/)
  ground native SQLite compatibility; source reasoning still requires real D1
  execution/readback.
- [D1 migrations](https://developers.cloudflare.com/d1/reference/migrations/)
  describes the ordinary migration stream. This explicit operational schema
  deliberately does not join the public Worker migration stream.
- Lee et al., [RIFL, SOSP 2015](https://web.stanford.edu/~ouster/cgi-bin/papers/rifl.pdf)
  explains recording completed operations/results for retry safety. Its
  deduplication lesson does not make an unrelated downstream mailbox operation
  replayable after a lost arm response; this proof exposes no downstream mutator.

## Incident-bound read-only `inspect` discriminator

Entry remains the existing registered proof workflow. New exact confirmation:
`INSPECT_STAGING_D1_READ_ONLY`; input `prior_run` must be exactly `36787173756`.
No generic incident/run selector is introduced. The historical attempt must be
independently read as the same workflow/repository/feature branch, attempt 1,
completed/failure and SHA `242b5abfee461d04188757e8b365d387d46fcdf9`.
Current checkout/run and six-job successful `source_run` are separately bound
to the **new exact inspect source SHA**, not borrowed from the historical run.

`staging_ten_address_d1_inspect.py` has an independent `ReadOnlyProvider`
facade, not a subclass of the mutation-capable Provider. It exposes only exact
DB GET, fixed staging Worker deployments GET, UUID-shaped version GET,
fixed global-hold SELECT and fixed two-namespace sqlite_master SELECT.
D1 SELECT transport is HTTP POST by the official API; the payload remains
strictly source-owned SELECT with exact reviewed parameters. No DDL,
INSERT/UPDATE/DELETE, SyntheticEscrow, mailbox, send, real escrow row/ciphertext,
R2, routing, artifact or recovery-key operation is reachable in inspect.
Every SELECT must have the existing successful native envelope/typed
`meta.changes` contract plus `changes == 0`. No private exception or body is
printed. Provider responses and raw namespaced DDL stay in memory.

| Stage / public label | What is independently checked | Failure behavior |
| --- | --- | --- |
| `guard` / `checkout` | Explicit read-only confirmation, protected staging/hosted/manual/attempt-1/feature gates, exact checkout SHA | Stop before provider capabilities; `unverified` |
| `github_dispatch` | Current GitHub proof attempt/workflow/repository/branch/SHA | Stop; no provider calls |
| `github_failed_apply` | Original failed exact run/SHA relation | Stop; no provider calls |
| `source` | Six successful actual source jobs + real crypto step at new exact SHA | Stop; no provider calls |
| `capability` | Protected account/token structural presence | Stop without rendering values |
| `database` | Exact DB UUID and staging name | Stop before SQL |
| `worker` / `binding` | Actual single 100% serving version; sole exact MAIL_DB; no duplicate MAIL_DB | Stop before SQL |
| `held` | Exact global singleton `held` | Stop before schema observation |
| `formal_schema` / `mirror_schema` | Complete expected tables/indexes/triggers, not existence-only | Separately `absent`, `exact`, `partial_or_drift`, or `unverified` |
| `worker_recheck` / `held_recheck` / `schema_recheck` | Stable serving tuple, still-held singleton, unchanged schema observations | Stop; prior observations do not become current acceptance |

### Integer versus numeric-string schema parameters: bounded hypothesis

The official [D1 REST Query reference](https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/)
models `params` as `string[]`. The existing schema SELECT binds an integer
`len(prefix)` and the exact prefix. This is a **candidate cause**, not evidence
of the historical failure. Inspect independently probes the same SELECT with
both `(len(prefix), prefix)` and `(str(len(prefix)), prefix)`; only these four
exact namespace/length tuples are admitted. The numeric string is the exact
decimal length, not an arbitrary numeric expression or SQL fragment.

Each shape gets a fixed `_integer` / `_numeric_string` verified/unverified
stage label; public `schema_parameter_shapes` emits only
`integer_and_numeric_string`, `integer_only`, `numeric_string_only` or
`unverified`. If both succeed their complete parsed schema must agree. A single
working shape can classify the actual schema; failed shapes do not fabricate
absence. Final schema recheck uses only shapes successfully observed before,
and compares exact DDL maps. These distinct read-only protocol observations do
not replay a DDL request, recover a lost ACK or change the existing apply
Provider/escrow parameter contract.

`numeric_string_only` after DB/worker/binding/held gates would support the
parameter-shape hypothesis for current observation, but does not establish a
historical root cause or justify schema mutation. Any `partial_or_drift` stays
an explicit failed diagnosis with nonzero exit, even if the other namespace is
absent/exact. Both namespaces are inspected even if one query/shape fails;
unknown is never converted to absent. Drift between shape observations is
`unverified`, never an equality pass.

### Results and next authorized action boundary

- Complete stable absent/exact observation emits
  `d1_proof_inspect_readonly_complete_no_mutation_authority` with exit 0.
  This is diagnostic completion, **not** native schema success / a new apply
  permit / live ten-address GO. Absence does not prove historical DDL was never
  sent; exactness does not reconstruct historical lost acknowledgements.
- Stable partial/drift observation emits
  `d1_proof_inspect_partial_or_drift_no_mutation_authority` with exit 1.
  No repair, rollback, CREATE continuation or mutation recommendation is encoded.
- Unverified gate/query/change emits
  `d1_proof_inspect_failed_no_mutation_authority` with exit 1 and fixed stages.
  Later stages remain `not_checked`; the private response is not exported.

All outputs carry `read_only: true`, `mutation_authority: false` and
`real_cleanup_attested: false`. They include only fixed labels and nonsecret
current source SHA / historical run ID. Do not equate workflow green with GO.
Same-repository noncanceling concurrency remains unchanged; operational exclusion
from external administrators is still required for meaningful observations.

The only conditional next command, **not executed or authorized here**, after
independent review, feature source push, exact successful hosted source CI and
explicit administrator authorization is:

```shell
# READ ONLY; existing default-branch registration does not authorize dispatch.
gh workflow run staging-ten-address-d1-proof.yml --ref codex/amail-v0.1.0 \
  -f mode=inspect -f confirm=INSPECT_STAGING_D1_READ_ONLY \
  -f source_run=EXACT_NEW_SUCCESSFUL_SOURCE_RUN -f prior_run=36787173756
```

The added `test_staging_ten_address_d1_inspect.py` is included by the existing
hosted `test_staging_ten_address*.py` pattern. Source fixtures cover incident/
source/guard separation, DB/worker/binding/held failure stages, absent/exact/
partial formal+mirror classification, unchanged SQLite dumps, forbidden
mutator seams, exact read whitelist, changed-row rejection, private-output
redaction, nonzero partial exit and integer-rejected/numeric-string-admitted
protocol observation. They are authored **not locally executed**. Local
verification is only Python AST parsing, YAML parsing and `git diff --check`.
No account/provider request, push, workflow dispatch, local unittest/build or
mutation retry occurred in this source workstream. Hosted tests and authorized
provider observations remain external acceptance requirements.

External grounding reuses the original API/SQL/RIFL references above plus
[GitHub manual workflow semantics](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow):
default-branch registration and selected execution `--ref` are distinct. The
engineering lesson of recorded operation results still applies: later schema
readback cannot manufacture an earlier missing mutation acknowledgement.
