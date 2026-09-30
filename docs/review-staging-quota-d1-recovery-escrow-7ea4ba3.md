# Independent review: encrypted D1 quota recovery escrow

Date: 2026-10-01. Reviewed design commit:
`7ea4ba3caab64a741f1bf98fb816a0245b0d292d`.
Narrow clarification also inspected:
`ff398d6a3f80285b23ca64ad249da3ffc8273a8d`.
Revised design independently re-reviewed:
`23e4ae4aca1aeb26df1a930573bd8ac971f51fda`.

## Decision and scope

**Latest decision (`23e4ae4`): GO for dormant, source-only implementation;
NO-GO for live quota dispatch.** The original conditional findings below remain
historical evidence; the follow-up assessment at the end governs their status.
The revised design adopts the material safety boundaries and explicitly narrows
24 hours to accountable Agent intake, not guaranteed completed cleanup.
The two-table encrypted escrow is a reasonable bounded staging design. No R2
PUT retry, new bucket, mail API, or general campaign framework is necessary.
This review does not authorize a migration, key operation, issue creation,
deployment, workflow dispatch, test run, or provider operation.

Inspected the design, the v2 manifest encryption/opening code, acceptance wrapper,
artifact validation, protected-key creation helper, configured staging MAIL_DB,
and earlier recovery/R2 reviews. Consulted current public Cloudflare, SQLite,
GitHub, AWS, and peer-reviewed systems sources. No local tests, executable
harnesses, live/account/provider calls, or production code changes were made.
Unrelated worktree changes were not reviewed or staged.

The achievable promise is **durable retrieval and authentication of the original
bounded recovery manifest after Actions artifact expiry**, provided D1 and the
retained key survive. It is not guaranteed autonomous cleanup of an ambiguous
DELETE, nor recovery from simultaneous database/key destruction. The design
correctly preserves the existing read-only cross-run reconciliation boundary.

## Required contract amendments

### P1: arming is one-use mutation admission, not a renewable lock

The design requires atomic `sealed -> armed` and a readback, but must explicitly
distinguish a *successful transition performed by this still-running controller*
from finding an already armed record. Otherwise a lost UPDATE response, second
invocation, or duplicate caller can read `armed` and mistakenly receive add/DELETE
authority. Database uniqueness prevents two campaigns; it does not prove which
process may execute the external side effect.

Minimum contract:

* A campaign enters once, from `sealed`, and needs an unambiguous successful
  conditional transition of its exact row plus full authenticated readback.
  Return the exact transitioned row, rather than treating HTTP success or an
  optional aggregate `changes` counter as proof of this state transition.
* A lost/invalid transition response means **no add callback**. Readback may
  establish that escrow is now armed for recovery/escalation; it cannot resume
  mutation. This conservative false alarm is intentional.
* Pre-existing `armed`, terminal receipts, reruns, duplicate entry, and foreign
  original coordinates never acquire mutation capability. Never retry arming
  into a success path, create a new envelope/nonce, or reset to `sealed`.
* A partial unique index on a fixed singleton value for armed records, together
  with a conditional state transition, enforces the global one-armed invariant.
  Hosted schema proof must cover the chosen D1-supported SQL. A process-side
  count followed by UPDATE is insufficient.

Do not solve this with a lease expiry: expiry cannot establish that a paused
external mutator has stopped. Keep the unresolved arm until verified settlement.
This escrow remains a recovery record, not an external-operation attempt journal.

### P1: the watchdog must have an executable capability and consumer contract

The original proposal calls the watchdog D1-read-only, but deduplication also
refers to a recorded parent `issue_number`. Clarification `ff398d6` resolves this
specific inconsistency: it permits fixed conditional issue-number/ack-receipt
writes, excludes destructive/general-SQL/ciphertext/mail-table callbacks, and
expressly disclaims provider-enforced read-only/table-scoped token authority.
That clarification is acceptable. Reusing the acceptance Cloudflare token may
still give the process provider authority its adapter does not expose: source
restrictions are not provider RBAC. Audit and approve the actual token blast
radius; do not claim capability isolation from table names or fixed SQL alone.

For the simplest slice, watchdog correctness need not depend on a D1
issue-number write. Whether using the permitted write or omitting it, deduplicate
in GitHub by an exact source-owned marker containing only public original
coordinates. Use one dedicated watchdog concurrency group independent
of the acceptance mutation lock. Enumerate a bounded, complete issue set including
closed issues, reject PR objects, validate category/marker/author, then create or
update the exact issue. Closure, label removal, or operator comment is never a D1
cleanup receipt. Ambiguous creation is reconciled on the next bounded scan, not
blindly retried. Exceeding the scan bound is a visible failure, not permission to
create another issue. A lost D1 issue-number attachment must be reconciled against
that exact issue marker, never cause a fresh issue/campaign. An attached number
is a locator, not evidence of delivery, acknowledgement, or cleanup. A stored
acknowledgement receipt must be constructed from the authenticated consumer
acknowledgement below; arbitrary operator input is not a receipt.

Verify whether the chosen protected credential is available to default-branch
scheduled jobs without indefinite approval waiting. The permitted metadata
writes require proved D1 write authority. If the actual token is broad, either
record/approve its blast radius under existing protections or stop and request
a separately approved narrower credential; do not silently relocate Secrets or
weaken the Environment. A separately approved read-only token is an alternative
only if watchdog correctness omits those D1 writes.
If run status or monitor-run freshness is queried, explicitly grant `actions:
read`, in addition to `contents: read` and `issues: write`; no Actions write
permission or recovery key is needed.

GitHub documents that `GITHUB_TOKEN`-generated issue events do **not** trigger a
new Actions issue workflow. Therefore an Agent implemented solely as
`on: issues` can silently miss every watchdog alert. Name the actual consumer
(for example, an already operating independent issue poller), its owner, bounded
poll/ack expectations, and how a test proves receipt. Do not assume a new App/PAT
exists, or introduce one without separate review. A synthetic acknowledgement
must traverse the exact watchdog-token/issue/consumer path, not a manually
created substitute. See [GitHub workflow triggering](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).

### P1: acknowledgement and cleanup are separate obligations

An Agent acknowledgement does not resolve an armed escrow. At server
`armed_at + 24 hours`, **either missing acknowledgement or missing exact cleanup
evidence** must block release and cause owner escalation. Otherwise a quick
comment can accidentally suppress an indefinitely unresolved resource.

The minimal alert state is inferred from durable arm + verified cleanup receipt,
and public issue receipt/ack/escalation comments. Require a source-fixed ack
format from an explicitly authorized Agent identity, original-run binding,
timestamp, and next action. An API 201, assignment, issue closure, or any
untrusted matching comment is not acknowledgement. Keep escalation bounded:
one initial issue, one verified deadline escalation marker, and rate-limited
subsequent updates. An acknowledged but unclean record keeps its key/chunks and
continues blocking fresh campaigns.

Use server time for deadline comparison; tolerate no client-controlled backdating
of `armed_at`. An in-progress run still unresolved at the deadline is overdue.
When arm exists but GitHub run status is missing/unreadable, preserve it and
escalate with a fixed unknown-status reason. Failure before arming creates no
alias exposure, but a partial escrow/monitor failure must remain visible.

Scheduled Actions may be delayed, dropped, disabled, or absent from the default
branch. Freshness before admission is necessary but does not guarantee future
execution. Record a concrete admitted freshness bound and a demonstrated
independent owner/Agent check of monitor health. If both watchdog and consumer
depend exclusively on that same schedule, a hard 24-hour detection guarantee
is unsupported. Present 24 hours as an accountable recovery/escalation deadline,
not a guaranteed scheduler SLA. [GitHub schedule semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
document these constraints.

### P1: retained-ciphertext budgeting must include every state

The budget wording names four prepared/writing envelopes and one armed envelope.
`sealed` records and `cleanup_verified` records whose purge failed also retain
ciphertext. A caller-only count and a byte total over uploaded chunks permit
concurrent partial records to reserve more space than the eventual bound.

Count/reserve the declared maximum encoded length atomically at parent admission
and retain that reservation until exact chunk-removal readback, including
writing, sealed, armed, and cleanup-verified-but-unpurged rows. Reject metadata
drift rather than reducing a reservation from partially observed upload size.
The 16 MB number is a logical escrow budget, not a hard SQLite physical-file
limit: indexes, pages, tombstones, and provider backups have additional cost.
Measure actual capacity headroom and latency before hosted admission.

**Simpler recommended first slice:** only one outstanding ciphertext-bearing
escrow across all states, with new prepare blocked until the previous receipt
is verified and its chunks are absent. There is one serial campaign in the
dominant workflow; four speculative prepared escrows do not improve its safety.
This lowers retained payload to roughly 2.67 MB and eliminates much of the
multi-reservation machinery. A bounded conditional parent INSERT must still
make admission atomic. Keep immutable receipt rows; do not delete an abandoned
partial upload merely because it is old. Its disposition must be explicitly
reviewed, or it conservatively blocks further admissions.

### P1: specify terminal recovery and cleanup-receipt ownership

The design currently describes marking `cleanup_verified` after successful
same-invocation cleanup. A canceled arm can later settle via Cron/restricted
intervention, and independent read-only recovery can prove exact final cleanup.
Without a specified receipt path, that safe outcome cannot release the arm.

Permit a separately confirmed recovery wrapper to construct the same terminal
receipt **only after authenticated original-envelope recovery and all current
final invariant checks**, including native-session/scratch teardown. It has no
add/DELETE capability. A failed campaign whose private cleanup succeeded may
also get a cleanup receipt once all final checks actually pass; distinguish
campaign acceptance failure from residual-resource exposure. Unknown or changed
service/run provenance goes to restricted reconciliation, not receipt forgery.

Bind receipt to original coordinates, schema/generation, ciphertext digest,
original source, verifier source/run, executed check-set version, and server
time. Store public/fixed metadata only. Do not accept a user `passed=true` field.
State transition and receipt creation must be one conditional write. Key/chunk
retention continues if session teardown or any final observation fails.

## Data, crypto, and transport model

The following are required details, not reasons to replace the chosen design:

| Concern | Recommended invariant |
| --- | --- |
| Identity | Original run/artifact IDs are canonical decimal TEXT, never JS floating-point or a SQLite INTEGER limited to signed 64-bit. Repository/workflow/schema/generation/source are exact source-owned coordinates. |
| Escrow bytes | Split **the entire original `manifest.bin` envelope**, including version header and nonce, not just AES-GCM's encrypted plaintext/tag. Never re-encrypt during readback recovery. |
| Immutable data | Parent coordinates/declared length/digest/count cannot change. Chunk inserts are allowed only while writing; exact duplicate is checked, never overwritten. No REPLACE/upsert-update. Sealing forbids new chunks; deletion is allowed only for a verified receipt. |
| Seal | Verify expected index set, canonical base64, exact per-chunk/full lengths, per-chunk/full digests, complete AES-GCM authentication, and exact local bytes. State guards and immutability make interleaved chunk reads safe; repeated readback alone is not a transaction. |
| Crypto binding | Existing v2 AAD is `[repository, original_run, "1", 2, key_generation]`. Source SHA is authenticated inside plaintext and must equal parent/original-run proof. Workflow path is **not** in existing AAD/plaintext; verify it independently from original run metadata while available. Missing historical authority yields restricted reconciliation. |
| Recovery key | Keep the versioned key out of D1, issue/workflow output, migration files, argv, and watchdog environment. Key retirement must check all unresolved escrow records, not Actions artifact age. Repository Secret metadata confirms presence, not recovery of the original secret value. |
| API envelope | Fixed endpoint/account/database and SQL only. HTTP 200 alone is insufficient; validate top-level and each statement success, exact result cardinality/shape, bounded body, and final row readback. Suppress response bodies and SQL parameters from error/debug logging. |
| Ambiguous inserts | Read the exact expected row once/boundedly, compare immutable bytes/metadata, and stop when equality cannot be established. Missing row is not authority to create another run, regenerate ciphertext, or grant campaign mutation. |

The current maximum accepted envelope is 2,000,256 bytes. Splitting at 65,536
bytes requires at most 31 chunks. Full-chunk base64 length is 87,384; maximum
sum of separately encoded chunks is 2,667,088 bytes. Five such payloads total
13,335,440 bytes, before schema/storage overhead. One chunk per fixed request
and bounded response is valid for the proposed representation.

Cloudflare currently documents 2,000,000-byte values/rows, 100,000-byte SQL,
100 parameters, and 30-second queries; each DB processes queries serially.
The REST batch call also must finish within 30 seconds. Avoid one giant
31-chunk transaction/read response. A small conditional statement or tested
small batch is sufficient for transitions. [D1 limits](https://developers.cloudflare.com/d1/platform/limits/)
support the sizing choice. The [REST query API](https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/)
documents a single `{sql, params}` or `{batch}` request and string parameters;
use decimal string + explicitly constrained numeric SQL conversion where
appropriate. Optional response fields cannot be invented as guarantees.

Cloudflare's [Worker binding batch contract](https://developers.cloudflare.com/d1/worker-api/d1-database/#batch)
describes transaction rollback on statement failure; this is not permission to
hold a transaction across separate HTTP readbacks or external alias calls.
[Foreign keys](https://developers.cloudflare.com/d1/sql-api/foreign-keys/)
are enforced by default. [SQLite unique partial indexes](https://www.sqlite.org/partialindex.html)
give a simple global armed guard, subject to exact hosted schema verification.

## Coupling, confidentiality, compatibility, and rollback

Additive staging-only tables in the configured `MAIL_DB` preserve external Mail
API/user quota behavior and old Worker source expectations. This is not a new
permission boundary: the Mail runtime can read/write that DB, including escrow
tables, and a sufficiently privileged administrator can erase or falsify public
escrow state. AEAD protects manifest confidentiality/authentication, not deletion
resistance or truthful plaintext `cleanup_verified` metadata. Fixed trusted
adapters, protected admission, and immutable schema rules are operational trust
controls. Explicitly audit the actual token scopes rather than assuming
database/table-level isolation from the token name.

Use the separate staging-acceptance migration directory and a fixed schema
version/fingerprint covering columns, keys, indexes, constraints, and triggers.
Do not repoint ordinary Mail migration configuration or modify production/tenant
tables. Hosted old-Worker/source-schema compatibility evidence is required;
source inspection alone does not establish runtime latency/capacity neutrality.

Stop admissions before source rollback. Roll back adapters while retaining
unresolved ciphertext, key, and a compatible metadata watcher/recovery reader.
Do not remove the sole watcher while any arm remains unresolved. Never use D1
restore, DROP, ordinary migration rollback, or age deletion to undo escrow
admission. Cloudflare documents [Time Travel restore](https://developers.cloudflare.com/d1/reference/time-travel/#restore-a-database)
as an in-place destructive overwrite: restoring MAIL_DB can simultaneously
erase escrow and rewind mail state without rewinding external provider resources.

Retaining ciphertext indefinitely also retains the decrypted private baseline's
future disclosure potential if the key is compromised. Only verified cleanup
permits logical chunk removal; document that provider backups and the retained
Actions artifact may still hold prior ciphertext. No immediate physical erasure
or immunity from repository Secret deletion is established. Keep the current
single-failure-domain limitation explicit, rather than branding it a complete
disaster archive.

## Alternatives and minimum implementation order

| Alternative | Decision |
| --- | --- |
| Longer/repeated Actions artifact retention | Simpler transport, but finite and runner-dependent; does not close durable escrow or accountable kill recovery. |
| One giant base64 D1 row | Reject: exceeds the documented row bound at the accepted envelope maximum. |
| Smaller single-row plaintext bound or REST BLOB | Changes an existing manifest contract or introduces an unproven transport shape. Not the minimum compatible fix. |
| Separate D1/R2 archive | Better isolation, but new resource/credentials/provenance need independent approval and proof. Do not retry the unverified R2 PUT just to make this design convenient. |
| Two tables, one outstanding envelope, public-issue dedup | Recommended first slice: bounded existing storage, no new public API, minimal state/reservation bookkeeping. |
| Durable per-operation replay journal | A different project; this manifest escrow cannot make uncertain DELETE retries safe. |

AWS production guidance separates retriable requests from ambiguous side effects
through durable idempotency identity, rather than a client retry loop.
[Making retries safe](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/)
supports retaining the no-replay boundary. Peer-reviewed
[RIFL, SOSP 2015](https://web.stanford.edu/~ouster/cgi-bin/papers/rifl.pdf)
uses completion records coordinated with the operation to prevent reexecution;
our manifest/armed record lacks that linkage. This research informs the boundary,
not a recommendation to build RIFL or claim exactly-once quota cleanup.

Implement in coherent, independently reviewed source slices:

1. Adopt these authority, budgeting, receipt, and consumer amendments. Resolve
   actual scheduled credential/Environment availability and Agent intake design
   before wiring a supposedly autonomous monitor.
2. Add dormant staging schema plus fixed insert/read/seal/arm/receipt/purge
   adapter. Keep one outstanding payload initially. Hosted synthetic contracts
   cover maximum envelope, gaps/extras/base64, wrong digest/AAD/coordinates,
   duplicate writes, response loss, concurrency, immutable receipts, and purge
   failure. No executable migration is authorized by this review.
3. Integrate wrapper admission and artifact-expiry recovery, preserving the
   exact existing artifact gate for campaign and forbidden add/DELETE in
   external recovery. Write terminal receipt only after complete teardown.
4. Add default-branch metadata watchdog, exact GitHub marker/dedup/authorized
   ack/deadline escalation, and monitor freshness gates. Test cancellation,
   absent run, missed schedules, deleted/closed issue, ambiguous issue creation,
   acknowledged-but-unclean deadline, and no-key/privacy behavior.
5. Only after independent source review and hosted source evidence, separately
   authorize exact staging provenance/schema migration and a synthetic encrypted
   roundtrip/latency check plus actual consumer receipt. A later explicit live
   GO requires these observations and all existing service/hold/capture-off,
   owner, artifact, recovery, and concurrency gates.

**Bottom line:** accept D1 escrow as the simple bounded direction, adopt the
one-use arm + retained-payload + verified receipt + executable alert amendments,
and keep live NO-GO until they are implemented and demonstrated. Nothing here
authorizes R2 PUT retry, DELETE replay, or bypassing historical provenance.

## Follow-up design review: `23e4ae4`

Date: 2026-10-01. Inspected the complete revised design and its commit diff, not
only the revision summary. **GO for dormant, source-only implementation. Live
quota/recovery dispatch remains NO-GO.** No new blocking design defect was
identified. No tests, source adapters, migrations, Secrets, issue operations,
workflow/provider calls, or live acceptance were executed for this follow-up.
The external documentation verified in the original same-day review remains
applicable; this revision does not change the provider limits or transport APIs.

| Original concern | Revised design assessment |
| --- | --- |
| Arm response loss/re-entry | Resolved: only the current invocation's unambiguous one-transition response followed by authenticated readback admits add. Ambiguous, zero-change, and already-armed cases explicitly cannot authorize add/DELETE. |
| Retained ciphertext budget | Resolved at design level: one outstanding writing/sealed/armed parent, database-enforced admission, and 16 MB accounting across all nonpurged states, including verified chunks whose purge failed. |
| Terminal recovery receipt | Resolved at design level: campaign success is insufficient; full independent read-only baseline/owner/provider/storage/service/privacy attestation and native/scratch teardown precede cleanup_verified. Apply this same contract to independently confirmed recovery after settlement, not only the original campaign process. |
| Watchdog token/callback distinction | `ff398d6` remains acceptable: fixed public-metadata writes are allowed, while table-scoped/read-only provider authority is expressly not claimed. Actual credential authority remains a hosted admission prerequisite. |
| Agent issue intake | Resolved at design level: intake cannot rely solely on on:issues generated by GITHUB_TOKEN. Real polling/reviewed dispatch intake must be independently demonstrated, without silently introducing a new token. |
| Acknowledgement vs cleanup | Resolved with an explicit scope clarification: 24 hours is the actual handler's acknowledgement/intake deadline, not an automatic cleanup deadline. Self-acknowledgement is rejected. Unverified cleanup still retains chunks/key and blocks another campaign indefinitely. |
| Scheduler guarantee | Resolved: no hard wall-clock SLA is inferred from Actions schedule; monitor freshness and actual default-branch operation remain separate evidence gates. |

The original review recommended escalating both missing acknowledgement and
missing cleanup at 24 hours. The revision instead explicitly defines a bounded
**intake obligation** and an unbounded-but-blocking verified-cleanup obligation.
This is acceptable for the stated conservative design, provided user-facing
runbooks call the timestamp an intake/escalation deadline and never advertise
guaranteed complete cleanup within 24 hours. An acknowledged-but-unclean issue
must remain actionable; acknowledgement cannot close the recovery obligation,
purge ciphertext, or unblock release. No new deletion permission follows from
either elapsed time or the handler's acknowledgement.

Implementation review must still check the concrete realization, rather than
treating this design approval as executable evidence:

1. Exact transitioned-row/result proof, state/coordinate guards, and immutability
   must enforce the one-use admission even under lost responses and concurrent
   callers. A generic HTTP success or optional aggregate counter is insufficient.
2. Reserve complete declared payload size atomically, including nonpurged
   terminal records; retained verified rows cannot accumulate past the budget.
   Prefer blocking new prepare until previous chunks are absent if that makes
   the concrete implementation smaller. No age-based abandonment/purge.
3. Chunk the entire original envelope, keep original v2 AAD/source checks, and
   compare exact bytes. Recovery after artifact expiry never creates a new
   envelope or fakes original workflow/source provenance.
4. Independent terminal recovery may write only the verified operations receipt,
   after all checks and teardown; it never receives address add/DELETE callbacks.
   Receipt attachment and state transition must be conditional and inseparable.
5. Public issue markers/metadata, bounded ambiguity reconciliation, authorized
   handler receipt, real consumer health, and scheduled Environment availability
   need source tests and hosted proof. Add explicit Actions read permission if
   the watchdog queries run status/freshness. Preserve pending monitoring during
   rollback; do not remove the last consumer while unresolved escrow exists.

The minimum implementation path remains separate additive staging schema +
fixed escrow adapter, wrapper gates/expiry recovery, and metadata watchdog/intake
contract in reviewed source slices. Preserve the existing 30-day immutable
GitHub artifact upload/readback contract throughout. Independently reviewed
source and hosted test evidence precede any separately authorized staging
migration, synthetic encrypted roundtrip, alert acknowledgement demonstration,
or eventual live GO. This follow-up grants none of those operational actions.
