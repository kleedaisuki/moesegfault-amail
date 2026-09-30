# Explicit staging D1 schema and synthetic provider proof

Date: 2026-10-01. Status: **exact hosted feature source CI, corrected read-only
inspection, native schema and synthetic cross-dispatch protocol passed; real
quota/campaign, 24-hour intake and production acceptance remain NO-GO**. No local project
tests/builds, provider operations, migration, workflow dispatch, push, or deploy
were performed while authoring this slice. Live ten-address acceptance remains
**NO-GO**. This is not a 24-hour accountable-intake demonstration.

## Current native D1 and synthetic-only evidence (2026-10-01)

These later operations followed a reviewed correction and independently
successful source/read-only evidence; they were not unchanged blind replays.
[Exact feature source CI 36789400291](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36789400291)
passed all six source jobs at `9499e7f20049b853b41da6790489f02fbfe20569`.
The corrected exact-c3f binding matcher received independent **Source GO**;
source review did not itself authorize provider operations.

| Operation | Evidence | Bounded observation |
| --- | --- | --- |
| First read-only inspect | [36788755759](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36788755759), feature `48f960b` | Stopped at `binding=unverified`; later held/schema phases were not established. This is not schema absence or a diagnosis of the original failure. |
| Corrected independent read-only inspect | [36789711030](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36789711030), feature `9499e7f` | Guard, exact source, database, Worker, complete binding, held state and recheck verified; formal and mirror schemas absent at this observation. Both integer and numeric-string REST parameters were accepted. No DDL was performed by the inspector. |
| New separately authorized apply-schema | [36789780146](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36789780146), feature `9499e7f` | Succeeded with `d1_proof_schema_verified`: native formal and mirror schema readback passed. This accepts the bounded native schema, not a real campaign. |
| Synthetic encrypted write | [36789867723](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36789867723), feature `9499e7f` | Succeeded: two ciphertext chunks, 82,592-byte encrypted envelope/ciphertext, synthetic-only mirror retention. No real recovery row or mutation permit. |
| Independent cross-dispatch read-terminal | [36789986151](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36789986151), feature `9499e7f` | Succeeded with the same envelope digest and retained mirror terminal receipt; `real_cleanup_attested=false`, synthetic-only. Not real mailbox cleanup or expiry-recovery acceptance. |

Public synthetic evidence digests (SHA-256; not keys or private mail):

| Artifact | Digest | Provenance |
| --- | --- | --- |
| Verified schema | `8e8f98365779c7d8d9c3607b00b891f2bff639b99a5c69307cd8a6996125d88d` | [Schema run 36789780146](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36789780146) |
| Synthetic encrypted envelope/ciphertext | `8988f551e833960e53f94e7bba02b41ec65aec9399449c5013d7667d8c6bd1cc` | [Write 36789867723](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36789867723), [independent read 36789986151](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36789986151) |
| Retained synthetic mirror terminal receipt | `526d173e4233f1b41dc5224845c9dae4bfdd148f0b2b652df024e43b749f22b2` | [Read-terminal 36789986151](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36789986151) |

The native provider mechanics gap is now closed **only for this bounded staging
schema and synthetic cross-dispatch protocol**. Real escrow admission, native
quota/reserved-name campaign, authenticated-owner mailbox/R2 recovery and
teardown, artifact-expiry recovery, accountable 24-hour intake, direct-contact
adoption/health and production remain **NO-GO / unaccepted**. Do not repeat the
completed synthetic proof for another green result. No provider operation or
project test/build was performed for this documentation update.

[PR #6](https://github.com/kleedaisuki/moesegfault-amail/pull/6) subsequently
merged the inspector and exact-c3f correction into main
`c691f99cba8cab96d11e5d74bee61f94784415aa`. This is integration evidence,
not a provider rerun at main or a retroactive change to the feature run SHAs.
The source-era design/review notes below retain their authoring context; where
they describe then-pending observations, this current evidence section governs.

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
7. `amail-mail-staging` has one 100%-serving deployment of exactly the frozen
   historical version `c3f6401a-1e84-4f51-91df-ae77d90683e9`. Its complete
   14-binding inventory must pass existing `mail_pin.containment_bindings_match`:
   fixed MAIL_DB plus historical ROLE_MONITOR, staging body bucket, approved
   scalar/secret names and Email binding. D1 targets use native `database_id`.
   No current-policy/other-version/optional-role fallback is accepted. Repeat
   deployment GET brackets the version; complete provenance is repeated after
   the phase, rejecting changed deployment/version or non-held sending state.
   This is historical binding provenance only, never effective privacy or
   sending acceptance. Every SQL operation still targets only fixed MAIL_DB.

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
default branch before it can receive manual events. [PR #1](https://github.com/kleedaisuki/moesegfault-amail/pull/1)
registered the workflow on main at `de2caf2e7d63c492b75ad7bddf89c0a8892e647b`;
[exact-main CI 36786862389](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36786862389)
and [feature source CI 36786388230](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36786388230)
each passed six source jobs with 51 non-source jobs skipped.
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
`d1_proof_failed_retained_no_campaign_authority` cannot prove that no DDL
committed. The later independent inspect established absence at its own
observation, not the original failed request's exact phase or state. The
checkable historical no-DDL implication below remains explicitly conditional.
Do not use mutation as diagnosis or repeat completed synthetic phases: see the
[current evidence](#current-native-d1-and-synthetic-only-evidence-2026-10-01).
The historical phase table explains contracts, not a standing execution plan.

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
- Exact native DB UUID/name and frozen c3f complete Worker binding fixtures,
  including wrong role/mail DB, missing/extra/duplicate bindings and wrong version.
- Controller write/read-terminal orchestration with independent original-run
  completion requirement, original plaintext binding and unchanged envelope
  digest across separate fixture invocations.

These are **inspected test sources, not executed/passing runs** at authoring.
SQLite plus a native-shaped JSON fixture is not actual Cloudflare evidence.
The [current evidence](#current-native-d1-and-synthetic-only-evidence-2026-10-01)
records subsequent exact source CI and the bounded native demonstration. The native fixture is two chunks, not a measured
31-chunk maximum-envelope provider/latency test. Persistent mirror ciphertext
also consumes finite staging DB storage; it has its own reviewed 16 MiB logical
budget and one outstanding record. Partial writes can block subsequent proofs
until separately reviewed manual reconciliation; never silently abandon a row
or DROP schemas. They do not block the independent real campaign slot.

## Required acceptance evidence and remaining live NO-GO

The bounded provider gap is closed by the current evidence above. Preserve
verified default-branch workflow
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
| `worker` / `binding` | Single 100% serving exact c3f version; complete frozen 14-binding match (including fixed MAIL_DB and historical ROLE_MONITOR) | Stop before SQL |
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

The following is reference syntax for the now-completed read-only discriminator,
not a next command or an authorization to repeat it. Any future inspection
requires a new discriminating question, exact source CI and explicit
administrator authorization:

```shell
# READ-ONLY REFERENCE; the bounded inspect already completed, not a replay plan.
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
provider observations were subsequently recorded in the current evidence
section; real campaign acceptance remains separate.

External grounding reuses the original API/SQL/RIFL references above plus
[GitHub manual workflow semantics](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow):
default-branch registration and selected execution `--ref` are distinct. The
engineering lesson of recorded operation results still applies: later schema
readback cannot manufacture an earlier missing mutation acknowledgement.

## Narrow c3f binding correction after inspect 36788755759

Parent-supplied categorical evidence from the read-only run
[36788755759](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36788755759)
at source `48f960b44da454140aa7140870267be5f0ceda7d` reports verified guard,
checkout, current/historical GitHub relations, source, capability, database and
worker, then `binding=unverified`. Held/formal/mirror schema were `not_checked`.
This implementation workstream did not retrieve provider/account data or logs.
That diagnostic stopped before schema SELECTs; it does **not** establish schema
absence, current mutation state or historical failure phase on its own.

The source defect is concrete: the former proof and inspector demanded one D1
binding with `id`, whereas the already reviewed historical c3f contract contains
both MAIL_DB and ROLE_MONITOR and matches native D1 fields via `database_id`.
The correction explicitly selects **only** the existing historical comparator
in both `Provider.provenance()` and `ReadOnlyProvider.binding()`. It does not
accept an arbitrary serving version or apply current TOML to old runtime.
See [frozen predecessor provenance](historical-containment-binding-contract-2026-10-01.md).
No change to that literal contract, current direct-only matcher, runtime,
workflow permissions, fixed SQL target, held gate or mutation confirmation is
introduced. The role binding is observed only as metadata; no role DB capability
or role SQL endpoint is added.

### Checkable no-DDL implication in immutable original source

Inspecting `242b5abfee461d04188757e8b365d387d46fcdf9` yields this ordering:

```text
execute('apply-schema')
  -> guard / checkout / dispatch / successful_source
  -> Provider(...)                          # construction only
  -> Provider.provenance()
       -> DB GET / deployment GET / version GET
       -> require(len(D1 bindings) == 1,
                  name == MAIL_DB, id == fixed DB)
       -> deployment GET / held SELECT     # only if old binding gate passed
  -> Provider.apply()                      # schema SELECT / CREATE only here
```

The frozen c3f inventory has two D1 bindings, so **if that inventory was observed
by the original run's provenance read**, the old predicate necessarily failed
before even its held SELECT; `Provider.apply()` and every schema query/CREATE
were unreachable. The same source rejects native MAIL_DB using `database_id`
in place of its expected `id`. This is a source/control-flow implication, not
an invented successful/no-op mutation acknowledgement.

The parent historical evidence establishes c3f's reviewed inventory; the later
inspect establishes its own binding stop. Neither the original generic fixed
failure label nor the later read alone independently timestamps the original
version response. Therefore do not claim unconditional historical no-DDL from
those two markers, infer absence from the failed inspect, or disregard changes
by another actor. Where the original run's c3f-serving relation is independently
retained, the source implication proves **that run** could not reach DDL; it
still says nothing about schemas created by other actors.

### Test-source and next-step boundary

Both synthetic provider metadata fixtures now consume the existing independent
literal `historical_containment_fixture.historical_version()` rather than
manufacturing a one-binding success response. New/extended source assertions
reject missing ROLE_MONITOR, wrong role/mail DB, duplicate/extra bindings and an
otherwise matching inventory attached to another version. Inspect failure at
binding must leave held/schema phases unobserved and SQL call list empty.
The prior read-only, dual-parameter and stability tests continue unchanged in
semantics. Tests are authored and source-traced only; no local unittest/build.

At source-review time the correction enabled a future separately authorized,
exact-source-tested inspect; the review itself supplied no mutation permission.
The subsequent successful corrected inspect and newly authorized schema/write/
read phases are recorded in the [current evidence](#current-native-d1-and-synthetic-only-evidence-2026-10-01).
The earlier failed inspect remains negative evidence, not schema proof. No
provider/dispatch/push operation occurred while authoring that correction or
this evidence update. Completed phases should not be repeated for another
passing result; any new operation requires its own scope and authorization.
