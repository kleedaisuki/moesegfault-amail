# Independent review: first dormant staging D1 escrow source

Date: 2026-10-01. Scope: `901327a`, with documentation correction `d34c5c9`,
against revised design `23e4ae4` and its approval `cc49e04`.

## Decision and execution boundary

**GO for this bounded dormant source slice and hosted synthetic/source tests.
Live quota acceptance/recovery dispatch remains NO-GO.** No substantive blocking
defect was identified in the inspected executable paths. This is not approval
to apply the migration, write a live escrow, configure/access a key, create an
issue, run a watchdog, or dispatch an alias campaign.

The review inspected source, DDL, surrounding manifest/readback/HTTP contracts,
existing workflow test discovery, and official provider documentation. It ran
no local tests/builds, provider requests, migration, hosted workflow dispatch,
or key access. Tests described below were inspected, not executed; their
presence/discovery is not a passing-run claim. Unrelated working-tree changes
were not reviewed or included in the review commit.

## Contract assessment

| Area | Source assessment | Remaining evidence boundary |
| --- | --- | --- |
| Migration isolation | New DDL lives under `infra/deploy/staging-acceptance-migrations/`, outside `crates/mail-worker/migrations`. No ordinary migration runner, Worker binding, workflow, or production config was changed. | Exact staging DB/service provenance and guarded explicit application are still required. |
| Backward compatibility/rollback | DDL is additive and namespaced; it does not alter a tenant table or existing API. Normal Worker source has no new escrow dependency. Parent DELETE always aborts; unresolved chunk DELETE aborts; no TTL, cascade, DROP, or rollback executor was added. | Future rollback must stop admissions and retain unresolved rows/chunks/key plus the last accountable monitor. |
| Fixed provider capabilities | SQL dictionary exposes only operations metadata/chunks and schema readback against the existing fixed staging DB. No DB selector, public table query, alias callback, DELETE capability, terminal receipt writer, or generic SQL CLI was introduced. | The actual control-plane token is not table-scoped; source restriction is not an IAM guarantee. |
| Parent/chunk insert-once | Coordinates and complete envelope binding are immutable. Parent/chunk insertion uses conflict-do-nothing, followed by exact readback; different envelopes/chunks cannot be overwritten. Partial writing state is retained. | Ambiguous preparation stops and does not authorize any CLI mutation; a later exact same-envelope durability continuation is distinct from recovering an arm ACK. |
| Seal | `put` authenticates the original envelope, uploads slices, verifies complete count/size/digest and exact local bytes, requires seal changes=1, then authenticates stable complete sealed readback. Existing identical sealed content remains preparation evidence only. | The source is not yet composed with fresh owner/service/hold/capture-off gates. |
| One-time arm | `arm` requires sealed state, exact digest/artifact/local bytes and null armed time; fixed conditional UPDATE must return a typed integer changes=1. Full authenticated armed readback follows before an `Arm` is returned. | An `Arm` is not currently connected to add or DELETE; future composition must preserve this boundary. |
| Lost ACK/concurrent entry | Exception, zero-change and already-armed state all fail closed. There is no retry, read-armed-to-permit branch or backward state transition. Competing arm callers cannot both satisfy the fixed sealed predicate. | Real D1 response semantics and concurrency still need explicit evidence; source reasoning is not a provider race experiment. |
| Outstanding/budget | Partial unique index on constant `(1)` admits at most one writing/sealed/armed parent. BEFORE INSERT reserves the complete declared encoded payload plus per-chunk/parent allowances, counting terminal records with any retained chunk. | Reservation is a logical 16 MiB application budget, not a physical SQLite page-size guarantee. |
| Privacy | Existing AES-GCM envelope is the only payload. Run/repository/workflow/source/generation/digest/size and lifecycle are public operations metadata. Recovery key and decoded owner/addresses are not SQL parameters. Provider exceptions are translated to fixed codes without body rendering. | Future watchdog/receipt integrations must preserve the same no-key/no-private-data boundary. |

### Why changes=1 is sufficiently narrow here, but not a universal D1 proof

Cloudflare's [query API](https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/)
documents `meta.changes` as optional and based on SQLite total changes, not an
intrinsic authorization token. `_http` rejects a missing, negative or boolean
value. The current arm statement targets one original-run primary key and exact
digest/artifact/sealed relation. The expected complete namespaced DDL has only
validation triggers, not triggers writing other records. Under this exact
source/schema contract, a known response of one change plus authenticated
readback has the intended narrow meaning. Any future trigger that writes rows
must reopen this reasoning; an aggregate counter alone must not be treated as
exact transition proof in a more general schema.

The lost-response rule is particularly important: durable `armed` state proves
the envelope is retained, not that this invocation still owns unused alias
permission. Database transition and a later external CLI mutation are not one
transaction. General RPC deduplication work such as Lee et al.,
[RIFL, SOSP 2015](https://web.stanford.edu/~ouster/cgi-bin/papers/rifl.pdf), records
completed operations/results to make retries safe. That does not justify
replaying a different downstream mutation whose result was never journaled.
The present conservative stop-on-ambiguous-arm rule is appropriate, rather than
adding a general exactly-once machinery claim.

## D1/SQLite compatibility and bounded representation

Official [D1 SQL documentation](https://developers.cloudflare.com/d1/sql-api/sql-statements/)
describes its SQLite engine compatibility. The DDL uses ordinary SQLite CHECKs,
foreign keys, partial expression indexes, BEFORE triggers/RAISE, scalar MIN and
unixepoch; no unsupported transaction management or extension dependency was
identified by source review. [D1 foreign-key documentation](https://developers.cloudflare.com/d1/sql-api/foreign-keys/)
documents enforcement. This is a compatibility assessment, not an observed
successful real D1 migration.

`schema()` compares the complete namespaced table/index/trigger DDL, rejecting
missing, altered or extra namespaced objects. It does not merely check table
names. [SQLite's schema table specification](https://www.sqlite.org/schematab.html)
explains stored DDL normalization and null SQL for implicit indexes; the current
uppercase unqualified CREATE statements and whitespace normalization fit that
representation. Future migration tooling must preserve or explicitly account
for equivalent DDL formatting rather than bypassing mismatch checks. Real
staging schema readback, including the design's table/foreign-key/index/trigger
observations, remains an operational prerequisite.

The following source limits fit the current official
[D1 limits](https://developers.cloudflare.com/d1/platform/limits/):

* Original envelope is bounded by 2,000,256 bytes, split into at most 31 slices
  of 65,536 bytes rather than stored as one oversized row.
* A full encoded slice is at most 87,384 characters. Fixed SQL is below 4 KiB,
  and no statement approaches the 100 bound-parameter limit. The HTTP adapter
  additionally caps its encoded JSON request below 100,000 bytes.
* Each chunk response is bounded at 128 KiB; count/size aggregate plus all
  expected indices rejects gaps/extras. Each slice checks exact decoded size,
  SHA-256 and canonical strict base64. Concatenated bytes check complete size
  and original envelope SHA-256.
* `binding()` calls the original manifest authenticator, preserving repository,
  run/attempt, schema and generation associated data and checked source metadata.
  Stable readback repeats parent and complete chunk retrieval; it never
  relabels or regenerates ciphertext after artifact expiry.
* Existing HTTP transport performs one bounded request without redirect/retry,
  with a 25-second timeout. A D1 query may run up to 30 seconds, so response loss
  after commitment is possible and is correctly treated as unknown, not success.

D1 is single-threaded per database. The adapter performs multiple bounded
point reads instead of one giant response; this is sensible for the bounded
acceptance purpose, but its real latency and shared mail-query impact have not
been measured. Budget aggregation scans operations parents, not tenant/mail
tables. Permanent empty receipts still reserve 4096 bytes each, keeping the
logical historical population bounded instead of allowing unbounded free
receipt growth.

## Test discovery and limits of existing coverage

`test_staging_ten_address_escrow.py` is discovered by the existing broad
`ci.yml` infrastructure unittest command and the quota workflow's existing
`test_staging_ten_address*.py` pattern. The explicit
`staging_ten_address_crypto_check.py` entry point is already called after the
pinned dependency installation in both workflows. Its new test uses actual
AES-GCM through the isolated in-memory SQLite insert/seal/read/attach/arm path;
it does not patch the cipher and fails rather than skips a missing/mismatched
dependency. Existing synthetic fixtures remain isolated from that real-cipher
check. No new live workflow integration was added by either reviewed commit.

Inspected tests exercise roundtrip/idempotent sealed readback, lost and
zero-change arm responses, no arm re-entry, conflicting envelope/artifact/chunk,
partial admission blocking another run, metadata typing, schema drift,
foreign key/AAD/generation failure, and retained terminal ciphertext budget.
The maximum-envelope test checks size arithmetic, not an actual maximum-size
authenticated multi-chunk upload/download. The real-cipher integration uses a
small fixture and injected SQLite query execution, not the real D1 HTTP parser.
There is no claim that these source tests cover provider behavior or every
future recovery/watchdog scenario.

Before a separately authorized live synthetic escrow demonstration, expand
hosted contracts for maximum-size multi-chunk transport, malformed/noncanonical
base64 and chunk/envelope digest mismatch, committed-but-lost create/chunk/seal
responses, competing arm/admission callers, and `_http` response shape/size /
missing changes. These are next-gate evidence requirements, not demonstrated
current defects or permission to run locally/live now.

## Unchanged blockers for live use

The first slice intentionally has no full independent terminal attestation,
immutable executed-recovery receipt writer, ciphertext purge adapter,
artifact-expiry wrapper integration, metadata watchdog, real Agent intake,
acknowledgement/freshness/deadline evidence, or current serving admission hooks.
The schema's receipt-shaped columns and receipt-gated DELETE trigger do not
prove actual cleanup; future receipt implementation must make receipt/state
attachment conditional and inseparable and enforce final receipt immutability.
These omissions are explicitly scoped, not hidden completed capabilities.

`d34c5c9` correctly updates the design status, all-nonpurged budget wording and
sealed-readback timing without expanding executable authority. Preserve the
existing immutable 30-day artifact gate. Hosted source test success can advance
the dormant implementation only; exact staging migration/permission/schema /
latency proof, wrapper integration and accountable recovery acceptance remain
separately reviewed and explicitly authorized steps before eventual live GO.
