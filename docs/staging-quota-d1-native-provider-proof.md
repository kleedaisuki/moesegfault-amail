# Explicit staging D1 schema and synthetic provider proof

Date: 2026-10-01. Status: **source implemented and independently reviewed;
awaiting hosted evidence and separately authorized manual dispatch**. No local project
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

## Three independently confirmed manual phases

| Mode | Exact confirmation | Inputs | Expected fixed result |
| --- | --- | --- | --- |
| `apply-schema` | `APPLY_STAGING_D1_ESCROW_SCHEMA` | Exact successful `source_run`; empty `prior_run` | `d1_proof_schema_verified` |
| `write-synthetic` | `WRITE_STAGING_D1_SYNTHETIC_ONLY` | Exact successful `source_run`; empty `prior_run` | `d1_proof_synthetic_armed_retained` |
| `read-terminal` | `READ_TERMINAL_STAGING_D1_SYNTHETIC_ONLY` | Current exact successful `source_run`; exact original synthetic `prior_run` | `d1_proof_cross_dispatch_terminal_ciphertext_retained` |

Only after independent review and explicit administrative authorization should
an operator dispatch these modes, in that order. Example syntax (placeholders
must be replaced with independently checked public run IDs):

```shell
# These are future manually authorized operations, not executed authoring steps.
gh workflow run staging-ten-address-d1-proof.yml --ref codex/amail-v0.1.0 \
  -f mode=apply-schema -f confirm=APPLY_STAGING_D1_ESCROW_SCHEMA \
  -f source_run=EXACT_SUCCESSFUL_SOURCE_RUN
gh workflow run staging-ten-address-d1-proof.yml --ref codex/amail-v0.1.0 \
  -f mode=write-synthetic -f confirm=WRITE_STAGING_D1_SYNTHETIC_ONLY \
  -f source_run=EXACT_SUCCESSFUL_SOURCE_RUN
gh workflow run staging-ten-address-d1-proof.yml --ref codex/amail-v0.1.0 \
  -f mode=read-terminal -f confirm=READ_TERMINAL_STAGING_D1_SYNTHETIC_ONLY \
  -f source_run=EXACT_CURRENT_SUCCESSFUL_SOURCE_RUN -f prior_run=EXACT_SYNTHETIC_WRITE_RUN
```

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

Before closing this provider gap, retain exact hosted CI/dispatch IDs, attempts,
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
