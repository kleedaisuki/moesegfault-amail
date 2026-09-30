# Staging quota recovery escrow and 24-hour escalation

Date: 2026-10-01. Status: **design only, pending independent review; no migration,
source adapter, alert, escrow write or live quota dispatch is authorized**.

## Problem and bounded decision

The current acceptance wrapper independently authenticates a 30-day immutable
GitHub recovery artifact and retains its encryption key. That does not preserve
ciphertext after artifact expiry and does not identify an accountable response
when a runner dies. Hard cancellation can skip every workflow `always()` step.
The reviewed workflow therefore remains live NO-GO until both durable encrypted
escrow and accountable failure escalation are exercised, not merely documented.

Do not add R2 credentials or a new bucket while the independent R2 PUT path is
unverified. Use a small **staging-only additive D1 escrow** in the already bound
`MAIL_DB` (`74f35f95-42ce-482c-86e6-dffbdd35cbbe`) through the existing protected
Cloudflare control-plane token. No new Worker route, mailbox, user quota,
Identity mechanism, root recovery key or credential scope is proposed. This is
acceptance operations state, not a public Mail API or a tenant-visible record.

The public mail schema migration stream must not silently acquire this test
facility. Prefer an explicit, independently reviewed **staging-acceptance
migration** under `infra/deploy/staging-acceptance-migrations/`, applied only by
a guarded staging administrator step after exact DB/service provenance. Do not
renumber or overlap the ordinary `0009_direct_role_contact` stream, deploy the
escrow to production, or pretend `IF NOT EXISTS` proves schema equivalence.
Record exact schema/version readback and a fixed successful synthetic escrow
roundtrip before allowing an alias. The normal Mail Worker does not query this
schema and old versions remain compatible.

## Limits and representation

Cloudflare documents a 2,000,000-byte maximum value/row, 100,000-byte SQL text,
100 bound parameters, and 30-second query limit; database operations are
single-threaded. See [D1 limits](https://developers.cloudflare.com/d1/platform/limits/)
and [D1 query API](https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/).
A complete encrypted manifest can be slightly larger than the maximum row, and
base64 expands it. Consequently **one giant base64 row is not acceptable**.

| Item | Proposed source-owned bound |
| --- | --- |
| Original authenticated envelope | Existing `LIMIT + 256` = 2,000,256 bytes maximum |
| Ciphertext chunk | 65,536 bytes before base64; at most 87,384 encoded bytes |
| Chunk count | At most 31, with exact expected indices and lengths |
| SQL text | Small fixed statements, under 4 KiB; ciphertext always bound params |
| One response | One chunk plus bounded metadata, under 128 KiB |
| Total retained escrow budget | 16 MB logical escrow payload plus conservative per-row metadata allowance, including **all nonpurged writing/sealed/armed/cleanup-verified ciphertext**, not merely unverified states |
| Outstanding envelope | **One total** across writing/sealed/armed states in this staging database; retained verified nonpurged chunks still consume the budget |

These are conservative application bounds, not provider guarantees or measured
performance. Chunking avoids giant row/response/SQL limits and gives bounded
failure recovery. No JSON manifests, subjects, addresses, usernames, owner
subjects, provider-rule records, ZIP/mail bytes, credentials or model text appear
in plaintext escrow columns. The payload is **only the already authenticated
AES-GCM ciphertext**; the recovery key remains exclusively in its versioned
repository Secret. Raw ciphertext/SQL response bodies are not logged either.

## Proposed schema and invariants

Two tables suffice; do not build a general campaign framework.

1. `staging_acceptance_escrows`: exact original repository, run/attempt=1,
   workflow path, source SHA, schema/generation, envelope SHA-256, envelope byte
   length, chunk count, nullable immutable artifact ID, server-created time,
   state (`writing`, `sealed`, `armed`, `cleanup_verified`), nullable armed and
   cleanup-verified times, nullable metadata-only issue number.
2. `staging_acceptance_escrow_chunks`: `(original_run, chunk_index)` primary key,
   encoded ciphertext, decoded length and SHA-256, with a foreign key to the
   parent. Every row is insert-once; duplicates must read back equal or reject,
   never overwrite. Strict indices, canonical base64, shape and size are checked
   on both upload and download.

Use [D1 foreign-key enforcement](https://developers.cloudflare.com/d1/sql-api/foreign-keys/)
for referential integrity, but a foreign key is not permission to purge an
unresolved parent. Initially prefer explicit conditional chunk removal after a
verified receipt rather than an unrestricted parent `ON DELETE CASCADE` path.
A cleanup receipt remains after ciphertext removal to prevent the same original
run from being resealed/rearmed. Validate the complete schema (`sqlite_master`,
`PRAGMA table_info`, foreign-key/index/trigger readback), not table names alone.

There is **no TTL or automatic age-based DELETE**. Twenty-four hours is an
escalation deadline, not destructive expiry. This escrow is not a per-DELETE
attempt journal and cannot resolve unknown earlier DELETE attempts. External
recovery remains read-only with fixed manual intervention for active/pending/
provisioning rows; this design does not grant a replay flag or restore batching.

## One-way preparation and mutation admission

1. Obtain exact successful source and tested binary, current three-service/
   binding/held/capture-off evidence, fresh synthetic A login and full baseline
   through the reviewed wrapper. Build/seal the existing manifest without alias
   mutation. Require the unverified/armed budget and exact escrow schema.
2. Enforce one outstanding parent across `writing`, `sealed` and `armed` with
   a database uniqueness/conditional-admission constraint, not a caller count.
   Insert parent `writing` with fixed original coordinates and envelope digest.
   Bind ciphertext chunks in small insert-once statements. On ambiguous writes,
   only read the exact row/chunk and compare; do not create a new run/nonce or
   replace a different value. Complete encrypted plaintext stays only in memory;
   the existing exact local ciphertext file remains available for upload.
3. Exhaust all expected chunks, reject gaps/duplicates/extras/metadata drift,
   base64-decode with strict canonical validation, compare byte length/digest,
   open AES-GCM with original coordinates/generation, and compare exact local
   ciphertext. Repeat metadata/chunk readback for stability. Only then perform
   a conditional `writing -> sealed` transition and re-read the complete sealed
   content. This is durable escrow admission, not a CLI mutation permission.
4. Upload the same ciphertext to immutable GitHub artifact as already designed;
   independently validate original artifact ID/run/name/SHA/lifetime/digest and
   exact bytes. Attach artifact ID once (`NULL -> exact ID`, or equal same ID),
   never replace it. Artifact transport remains useful; D1 is independent durable
   backup rather than an excuse to skip the original readback gate.
5. Immediately before any alias mutation, read back sealed escrow and complete
   ciphertext/AES-GCM, source/owner/service/hold/capture-off proof. Atomically
   transition this exact parent to `armed` only from the exact sealed relation,
   maintaining the one-outstanding-envelope constraint. Require the original
   current invocation's bounded successful response to report exactly one
   conditional transition, then independently re-read armed relation/ciphertext
   before granting add. **An ambiguous arm write, zero-change response or an
   already-armed readback never authorizes add or DELETE.** Do not recover a
   lost transition acknowledgement by reading `armed` and assuming this process
   made it: another phase/invocation may have attempted an unknown mutation.
   A killed process after arm remains conservatively unknown even when it never
   submitted its first add. Recovery stays read-only and may only attest the
   actual full baseline/retired state or request manual intervention.

Additive D1 escrow writes mean prepare is no longer globally remote read-only:
it remains **no account/alias/send mutation**, but creates its exact encrypted
operations record. Update that product/runbook language explicitly. No provider
permission failure, missing table, partial upload, unsealed row, changed digest,
foreign run or alert-readiness failure can be bypassed with a workflow boolean.

## Cleanup, retention and recovery after artifact expiry

A campaign success marker is not a terminal escrow receipt. After same-process
cleanup, execute the separate **full independent read-only recovery attestation**
against the exact sealed envelope: current complete provider/global-owner/R2/
storage/service/held/capture-off observations, original baseline preservation,
no pending/unsettled work and fresh sealed-owner identity relation. Complete
native local-session teardown and scratch cleanup before `cleanup_verified`.
The receiver constructs its receipt only from those executed checks, not an
operator `passed` input, issue acknowledgement or existing database state flag.
Bind receipt to original envelope digest/source/run and server time. If any
attestation or local teardown is unknown, retain ciphertext and remain pending;
an empty known readback is distinct from claiming a previously unknown DELETE
was never attempted.

Only a `cleanup_verified` row may have its encrypted chunks removed, through a
conditional fixed SQL cleanup and exact readback. Preserve its nonprivate receipt
and original digest to prevent reuse. Failure/manual intervention/cancellation
preserves **all** encrypted chunks and the key indefinitely. An ordinary rollback
cannot DROP these tables, restore the database or erase unresolved state.

After GitHub artifact expiry, a confirmed recovery reads exact D1 parent/chunks,
validates original schema/coordinates/workflow/SHA/generation/digest, authenticates
the envelope and reacquires the sealed owner with the current reviewed CI binary.
It still requires original run provenance where available and current compatible
service/hold/capture-off evidence, and still does not replay an unknown DELETE.
If original run metadata was deleted or service revisions changed, escalate to
restricted reconciliation rather than forge historical authority. D1's point-in-
time backup is an operational recovery aid, **not** the escrow retention policy;
its finite backup window does not delete the persistent escrow rows.

## Accountable failure escalation

The accountable handler is the **project-maintenance Agent** consuming the
repository's staging-recovery issues; the repository owner is the escalation
recipient, not an assumed human who must operate an inbox UI. Before live GO,
verify that an owner/Agent watches this channel and demonstrate one synthetic
alert receipt/acknowledgement. Do not infer notification delivery from API 201 or
issue creation, and do not disclose the private operational mailbox in issues.

Use a dedicated metadata-only GitHub watchdog workflow, with `contents: read`,
`issues: write` and the existing protected staging D1 control-plane capability.
Its source adapter may SELECT indexed public escrow metadata and conditionally
attach an exact immutable issue number/acknowledgement receipt in the operations
parent row; it exposes no general SQL, ciphertext-chunk read, mail table access
or DELETE. This is not a claim that the underlying account-level token is
read-only or table-scoped. It needs no recovery key, mail content, artifact
download, Cloudflare routing write or destructive callback. Run it on a
conservative periodic schedule and explicit dispatch, and use an immediate
post-failure alert attempt in the acceptance workflow when possible. Do **not**
wire Agent intake solely to `on: issues`: issues created using `GITHUB_TOKEN`
do not trigger ordinary downstream Actions workflows. Use an independently
proven polling/Agent intake mechanism or a specifically reviewed dispatch
mechanism; changing credentials just to bypass recursion protection is not
part of this design. See [GitHub workflow-triggering semantics](https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-when-your-workflow-runs/triggering-a-workflow). The durable
D1 `armed` state covers hard cancellation when that step never runs.

Issue body contains only the fixed staging category, public original Actions
URL/run/attempt/source SHA, UTC deadline and fixed failure/manual-intervention
label. No ciphertext, envelope chunks, manifest-derived aliases/owner metadata,
provider records, Secrets or private contact is permitted. Deduplicate by a
source-fixed exact original-run marker and recorded issue number; check existing
issue metadata before creating another. Alert transport ambiguity is tracked and
reconciled, never reported as acknowledged delivery. Duplicate metadata-only
alerts are less harmful than silently missing an overdue recovery, but unbounded
retry/issue spam is not permitted.

Set recovery due time from D1 server `armed_at + 24 hours`. An unresolved failed
run creates an issue promptly; the watchdog catches orphaned/overdue armed rows
and repeats/escalates the existing issue rather than inventing new campaigns.
Require actual **Agent acknowledgement/intake within 24 hours**. This records
responsibility and an actionable response, **not completed recovery**. Unknown
active rows may still require restricted reconciliation; no deadline permits
DELETE replay or receipt forgery. Exact cleanup remains pending until the full
independent attestation and local teardown succeed; pending ciphertext/key stay
retained indefinitely and no new campaign is admitted. Absent acknowledgement at
24 hours is an explicit owner escalation and release blocker. An acknowledgement
must be read back from the real handler's documented intake path; a bot posting
its own issue or an automatic self-acknowledgement is not proof that a recovery
Agent received the incident. GitHub scheduled jobs can be delayed or disabled, so their
schedule alone cannot promise a hard wall-clock SLA. Check/watchdog freshness is
part of admission, and any failure opens an actionable issue/explicit operator
question rather than claiming silent autonomous recovery.

## Permissions, coupling, migration and rollback

* No new Cloudflare token is required **if** the existing staging D1 query token
  can write this exact database; prove that capability in a small synthetic
  encrypted-only escrow roundtrip, not from a successful SELECT or prior D1
  migration. Cloudflare D1 permissions are broader than individual tables, so
  the source adapter must expose only fixed reviewed escrow SQL and the fixed
  staging database. Do not broaden the existing SELECT-only `Readback` adapter.
* The Mail runtime already binds this DB and could access escrow ciphertext;
  it receives no recovery key and exposes no escrow API. AEAD protects the
  private baseline even from accidental DB/log access. This is shared-failure-
  domain coupling, not independent disaster backup: losing this staging DB or
  deleting its rows together with artifacts can still destroy recovery. For a
  bounded acceptance this avoids new unverified storage credentials, but it is
  not a production-grade multi-provider archive.
* Small chunk writes share D1's single-threaded database with mail metadata.
  Enforce the 16 MB budget across **every nonpurged ciphertext state**, one
  outstanding envelope, fixed bounded statements and no large scans; measure hosted synthetic write/read latency and normal mail
  query regression. If storage/latency/schema coupling is unacceptable, stop and
  revisit a dedicated confirmed storage mechanism instead of forcing D1.
* Migration creates only new staging-operations tables/indexes/constraints;
  it changes no tenant table, user quota or established API. Validate rollback
  compatibility by old Worker source tests and no dependency on the new tables.
  Stop new admissions before rollback. Retain unresolved tables/chunks/key;
  remove the adapter/watchdog source only after every pending record is handled.
* Watchdog must be registered/enabled on the default branch and independently
  tested for failure, cancellation, missing acknowledgement, stale monitor and
  artifact expiry. Do not treat a feature-branch YAML file as running monitoring.

## Acceptance and next bounded implementation

Independent design review precedes source implementation. Then implement only
an additive staging schema, fixed escrow adapter, exact wrapper gates and the
metadata-only watchdog/issue contract in coherent source commits. Hosted tests
must cover maximum envelope/chunk boundaries, partial write/read ambiguity,
no-overwrite/digest/AAD errors, foreign coordinates, ambiguous/already-armed
non-admission, one outstanding envelope, total nonpurged budget, artifact expiry
recovery, immutable receipt-only purge, no-key watchdog privacy
and deadline/acknowledgement failures. No local test, real migration, key setup,
issue creation, alias or live quota run is implied by this document.

Until those gates are implemented and actually evidenced, existing quota source
and workflow remain **live NO-GO**. Key creation/default-workflow registration
must not be interpreted as granting missing escrow/escalation acceptance.

## Review revision and unchanged current behavior

The first review (`5e2acd4`) grants only conditional dormant-source exploration,
not live admission. This revision closes the design ambiguities: ambiguous or
already-armed state is never mutation permission; one outstanding envelope and
all retained ciphertext states count toward budget; terminal purge requires
full independent read-only recovery plus local native teardown; 24-hour receipt
is a distinct Agent acknowledgement, not cleanup; real intake must work despite
GITHUB_TOKEN recursion prevention; scheduled jobs alone are not a hard SLA.

Preserve the current 30-day immutable GitHub artifact upload/readback semantics
until the new escrow is migrated, permission-tested, encrypted-roundtrip-tested
and independently accepted. Do not shorten retention, silently use D1 as an
unimplemented fallback, register a source YAML as proof of running monitoring,
create a new key, or dispatch a quota campaign while these gates remain open.
