# Staging quota recovery after GitHub artifact expiry

Date: 2026-10-01. Status: **proposed bounded architecture, not implemented or
authorized for live use**. Live acceptance remains NO-GO. Scope: dormant escrow
`901327a` and subsequent coverage, terminal correction `63f9d11`, and concrete
coordinator `4e7929e` (whose post-teardown settlement oracle is being corrected
independently). No production code, local test/build, migration, provider/account
request, key access, or dispatch was performed. Public documentation was read.

## Decision and evidence reused

Reuse `staging-quota-d1-recovery-escrow-design.md`,
`review-staging-quota-d1-escrow-source-901327a.md`,
`review-staging-quota-d1-terminal-5d3eb63.md`, and the actual manifest, escrow,
artifact, provenance, native and acceptance modules under `infra/tests/`.

**A complete D1 envelope can replace expired artifact transport, not historical
workflow identity or executed recovery.** Preserve the original immutable
artifact admission gate for every new campaign. Add one explicit recover-only
D1 transport path feeding the same concrete independent recovery coordinator.
Do not add a generic artifact-error fallback, a mutation replay flag, or another
manifest format. Stop with retained ciphertext when an independent original
run relation or the exact full envelope cannot be obtained.

There is a second required change before claiming durable expiry recovery:
replace per-chunk terminal purge with one bounded, receipt-conditional,
all-chunks SQL statement. The existing per-chunk path can permanently lose the
only complete envelope after artifact expiry. This is not resolved by the
current receipt, encryption key, or a successful campaign marker.

## Four distinct identities, not one substituted SHA

| Relation | Source of evidence | Required binding |
| --- | --- | --- |
| Original manual invocation | Independent GitHub run-attempt record | Fixed repository/branch/workflow, original run, attempt 1, `workflow_dispatch`, exact original `head_sha` |
| Original encrypted intent | Complete D1 chunks plus retained generation key | Original coordinates, schema 2, exact envelope bytes/digest, authenticated checkout, owner, baseline and service revisions |
| Current recovery implementation | Current checkout, current manual run and successful source CI | Current checkout equals current run SHA; all existing six source jobs and real-cipher step; exact tested Windows binary artifact |
| Executed terminal verifier | Concrete successful recovery plus native/binary teardown | Current verifier run/SHA, original envelope/lifecycle relation, existing check-set, observed D1 server time |

Never require the current implementation SHA to equal the historical checkout
merely because a manifest survived. Never overwrite the original SHA with the
new one. The current reviewed reader must explicitly support the existing v2
manifest/schema and unchanged service contract. Changed service revisions or
unknown compatibility remain restricted reconciliation, not a new pass flag.

GitHub exposes a specific [run-attempt endpoint](https://docs.github.com/en/rest/actions/workflow-runs#get-a-workflow-run-attempt).
Use the existing `dispatch_record(original_run)` checks and compare its SHA to
both the authenticated plan and escrow binding. For this *external expiry*
path, additionally require the original invocation to have completed and the
current recovery to be a distinct invocation; successful campaign conclusion
is not required. Shared workflow concurrency and an operational staging
mutation exclusion must prevent another campaign/recovery from running during
attestation. Held sending is not an alias-write lock. Do not finalize while the
original process might still use an earlier mutation capability.

**Missing/deleted/inaccessible original run metadata is NO-GO for this terminal
path.** A D1 row supplies stored coordinates; it does not independently prove
that GitHub ever executed that workflow. AES-GCM authenticates possession of
the generation key, not GitHub execution or the key holder's honesty. The
manifest has no original source-CI run ID, so do not invent one or claim a new
CI success proves the historical CI result. If the requirement is to re-prove
the original GitHub ZIP digest/artifact lifetime after deletion, the existing
schema cannot satisfy it: only the original artifact ID and envelope digest
survive. That stronger requirement is also NO-GO without separately designed
independent retained provenance. Ordinary expiry recovery instead relies on
the reviewed original admission contract plus fresh original run identity.

## Exact reconstruction and authentication

The existing `Escrow.read(original_run, key, generation)` already provides the
bounded reusable mechanism; no resealing, fresh nonce or alias regeneration is
needed. A new transport seam should invoke it, then return its complete original
row, exact bytes and opened validated plan in memory to the coordinator:

1. Validate the exact namespaced schema against the checked-in DDL and the fixed
   staging DB. Read one parent by original run; require generation selected by
   a source-fixed supported-key mapping, never by an arbitrary Secret name.
2. Exhaust the independent exact count/decoded-byte aggregate, then all indices
   `0..chunk_count-1`. Keep the existing 65,536-byte slices, at most 31 chunks,
   strict canonical base64, exact per-slice length and SHA-256. Reject missing,
   duplicate, extra, altered or oversized chunks. Do not assemble guessed gaps.
3. Compare concatenated envelope length/SHA-256 to the parent. Open the existing
   `AMAIL-TEN-V2\0 || 12-byte nonce || ciphertext-and-tag` with the unchanged
   derived key `HMAC-SHA256(key, "amail-ten-address/aead-key/v2")`.
4. Preserve the *exact* AAD: canonical JSON
   `["kleedaisuki/moesegfault-amail", original_run_string, "1", 2, generation]`.
   Neither workflow path nor checkout SHA is in that AAD: checkout is in the
   authenticated plaintext and workflow is independently checked. Do not
   silently describe either as an AAD field or change the original encoding.
5. Existing `manifest.validate` must bind schema/repository/run/attempt/
   generation, issuer/subject, checkout, username/client, original services,
   deterministic allowed resources and full baseline. `escrow.binding` must
   equal all immutable parent binding fields, including reservation arithmetic.
6. Repeat complete parent/chunk readback as today; require stable exact bytes
   and relation. Compare historical GitHub SHA as above. Retain `artifact_id`
   unchanged, including a genuine null for incomplete preparation; an expired
   attached ID is not replaced by another upload or used as a download permit.

[NIST's GCM specification](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-38d.pdf)
supports the separation between authenticated data and unauthenticated provider
metadata. The envelope SHA is a transport/integrity binding, not an independent
signature. The GitHub artifact digest hashes its ZIP archive, not necessarily
`manifest.bin`; do not compare those different digests or fabricate the ZIP.

Use an explicit source-only `finalize_escrow_recovery` seam, initially without a
CLI/workflow entrypoint, and a small internal envelope loader shared with the
artifact path. The D1 path selects transport deliberately; it must not catch
every artifact exception and then continue. Missing permissions, timeout,
wrong digest and expired artifact are different observations. No D1 path is
available to prepare/campaign, and no supplied boolean proves attestation.

## Same concrete recovery, including settled mail tombstones

After reconstruction, reuse current source/binary admission, exact three-service
binding/held/effective-capture-off checks and the fresh synthetic A native login.
The independently observed pairwise subject and protected username must equal
the sealed owner and verified username. No fallback account, cached home or
guessed subject is allowed. Read the complete global D1 ownership inventory,
entire zone rule relation, R2 key/metadata baseline and exact candidate storage.

The adapter has **neither add nor address DELETE**. Active/pending/provisioning
rows require the existing fixed manual-intervention result and preserved escrow.
Deleting or unsettled retired rows may only use the bounded read-only settlement
poll; timeout retains recovery. A settled owned retired tombstone is acceptable
when it has no route/rule ID and `needs_reconcile=0`; its old
`next_reconcile_at` does not itself mean pending work. Foreign owner/rule,
baseline/resource/aggregate drift, unexpected messages or unknown inventory
reject the full attestation rather than being filtered out.

Use `manifest.reconcile(plan, reader.read, delete=None, ...)` for the **full
post-teardown oracle**, not `assert_prefix(..., 0)`: the latter incorrectly
requires all newly allocated rows to disappear, although supported retirement
leaves settled tombstones. Repeat storage, service/hold and effective privacy
checks after native context exit and verified removal of the owned binary
scratch. Native logout proves local session removal and only attempts remote
refresh revocation. Any native/browser/home/binary cleanup failure or cancellation
bypasses terminal SQL. Plaintext and credentials remain in memory/owned `.temp`
only; fixed result labels contain no observed private data.

## Receipt and purge: eliminate the destructive partial-envelope case

Keep `63f9d11`'s exact lifecycle compare-and-swap: observed state, null-safe
artifact/arm relation, creation time and envelope binding must still match when
the server-time-bound receipt is written. Require this invocation's known typed
one-change acknowledgement plus unchanged authenticated receipt readback.
Receipt ambiguity stops without purge. A later separate invocation with a
complete envelope repeats every external check/teardown before accepting the
existing immutable receipt and attempting purge; it never rewrites the receipt
or treats readback as the lost invocation's acknowledgement.

**Recommended purge:** after that sequence and a final complete stable encrypted
readback, issue one fixed DELETE covering this original run's entire chunk set,
conditioned on the exact immutable terminal receipt/original binding and complete
count/byte relation. No per-chunk loop, unrestricted parent delete, age purge,
cascade, multiple-statement batch or user SQL. The original at-most-31 rows are
insert-once and cannot gain new parts once terminal; complete authentication
before the statement therefore checks the exact data being removed. Require
typed known changes equal the expected chunk count and independent typed zero
aggregate, exact-index absence and unchanged parent/receipt readback.

This is a proposed source change, not a claim about existing `_purge`. SQLite's
[implicit transaction model](https://www.sqlite.org/lang_transaction.html) and
[D1's SQLite SQL compatibility](https://developers.cloudflare.com/d1/sql-api/sql-statements/)
motivate a single-statement all-or-none operation. Provider execution/fault
behavior must be independently demonstrated before operational use. Keep the
existing receipt-retained DDL; no new private row or general transaction
framework is needed. Do not infer REST batch atomicity from SQLite semantics.

| Durable observation after interruption | Permitted next action |
| --- | --- |
| Nonterminal, complete authenticated envelope | Independent original/current provenance and full recovery; receipt only after teardown/readback |
| Terminal receipt, complete authenticated envelope | Repeat full fresh recovery/teardown; validate existing receipt; one atomic purge attempt |
| Terminal receipt, zero chunks | Metadata-only historical settlement status; no new receipt, fresh-recovery claim, alias permission or resend |
| Terminal receipt, some but not all chunks | NO-GO for artifact-free fresh attestation/purge; preserve remaining chunks/key and escalate restricted reconciliation |
| Writing row, incomplete chunks | NO-GO without an independently authenticated complete original envelope; no guessed manifest or abandonment |
| Any wrong key/generation/coordinates/digest/schema | Stop and retain; never rotate/reseal to hide the mismatch |

An ambiguous atomic purge stops the current invocation; a later read may
distinguish intact from zero chunks, not manufacture its predecessor's ACK.
An empty terminal operations tombstone is *not* the settled mail-address
tombstone discussed above, and its receipt hash is unkeyed metadata, not a fresh
cryptographic authentication of a now-absent manifest. A separate metadata-only
status must say historical receipt/empty escrow, never the existing full-recovery
success label. If fresh attestation is demanded even after intentional complete
purge, no architecture retaining only this public receipt can meet it.

Legacy partial purges can still resume through the existing artifact path while
that exact artifact survives and all fresh checks pass. Once it expires, no
remaining chunk hash or key can recover the missing bytes. A backup might supply
the exact envelope only under a separate reviewed procedure; do not restore the
whole tenant DB to repair escrow. Until atomic purge has provider evidence,
retain all chunks after receipt rather than creating another partial state.

## Provider uncertainty, key retention and implementation slices

[The D1 REST query reference](https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/)
currently types `params` as strings and `meta.changes` as optional, with SQLite
total-change semantics. Existing source requires a nonnegative integer even for
SELECT and sends integer/null parameters. Missing or unfamiliar metadata must
fail closed, not default to zero/one or infer commitment from HTTP 200. A future
parser may separate read results from write acknowledgement after independent
review, but must not weaken receipt/arm authorization. `changes` is not a
capability; the precise fixed statement, non-writing validation triggers,
schema, known response and complete independent readback provide its meaning.

For a separately authorized provider gate, explicitly check parent/chunk SELECT
metadata, null/non-null lifecycle bindings, integer timestamps/counts, receipt
changes=1, all-chunks DELETE changes=N, exact zero aggregate, interruption and
rollback behavior, maximum 31-chunk payload and shared-mail latency. Current
in-memory SQLite/hosted source evidence is not real D1 transport evidence.

Retain `AMAIL_TEN_ADDRESS_RECOVERY_KEY_V1` for `ten-address-v1`; future generations
get new immutable names and a reviewed fixed supported-generation mapping.
Never replace V1 in place, try every key, log key/digest/AAD-derived resources,
or select arbitrary Secrets from D1 input. A generation stays retained while any
unresolved/writing/sealed/armed/terminal-with-chunks escrow or required encrypted
artifact needs it; artifact expiry alone never permits retirement. Lost or
compromised keys block automated provenance/recovery rather than being replaced
with a newly encrypted plan. Key metadata presence is not proof of decryptability.
Ordinary rollback preserves tables, chunks, historical receipts and keys.

Implementation order, with separate independent reviews and hosted-only tests:

1. Finish the coordinator settlement-oracle correction and inspect its negative
   drift/foreign ownership fixtures before sharing that coordinator.
2. Add explicit D1-only envelope loading/current-original identity distinction;
   real AES maximum-envelope roundtrip, wrong generation/AAD/digest/schema,
   missing original run, source SHA mismatch and forbidden mutation fixtures.
3. Replace terminal chunk purge with the bounded atomic statement; cover known,
   lost/zero-change receipt and purge, competing coordinators, full retained vs
   empty state and deliberate partial-state NO-GO. Until ready, retain chunks.
4. Independently review source; run hosted synthetic/real-cipher contracts, then
   separately authorize exact staging schema/provider roundtrip and latency.
5. Only later wire explicit protected recovery transport and accountable
   watchdog/intake/freshness/24-hour acknowledgement. No such workflow wiring,
   migration/key operation or live campaign is authorized by this design.

[AWS's production retry guidance](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/)
and [RIFL (SOSP 2015)](https://web.stanford.edu/~ouster/cgi-bin/papers/rifl.pdf)
distinguish operation identity from unknown downstream effects. Here a receipt
records verified cleanup, not a journal of address DELETE attempts. Exactly-once
RPC machinery cannot retrospectively supply that missing history. The simpler
design is read-only external recovery, exact retained identity, and a local
single-statement ciphertext purge, with explicit NO-GO when essential evidence
has been irreversibly lost.
