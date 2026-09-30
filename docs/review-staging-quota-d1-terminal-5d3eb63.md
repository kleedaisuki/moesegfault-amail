# Independent review: dormant private D1 terminal receipt and purge

Date: 2026-10-01. Scope: `5d3eb63`, against revised design `23e4ae4`
and the independently reviewed dormant source through `f9f67bc`. Reused
`review-staging-quota-d1-escrow-source-901327a.md` and its follow-up evidence.

## Decision and execution boundary

**NO-GO for accepting this terminal slice as ready for hosted source validation
until the P2 below is corrected and independently re-reviewed. Live remains
NO-GO regardless of that correction.** This decision does not prohibit a
separately authorized diagnostic hosted test, but no such dispatch was made.

Inspected the complete four-file diff, full adapter/DDL, synthetic fixture and
test additions, manifest/transport contracts, and call-site search. No local
test, build, live/provider request, migration, key access, workflow dispatch,
or production-source modification occurred. Public documentation browsing was
limited to official provider/SQLite, industry, and academic sources. Tests
below were inspected, not executed. Unrelated working-tree changes are excluded.

## P2: compare the receipt-bound lifecycle relation in the terminal UPDATE

**Location:** `infra/tests/staging_ten_address_escrow.py:49` (`SQL["receipt"]`),
and `_finalize` at lines 331-347. **Confidence: high, source-derived executable
interleaving; not locally executed.**

The receipt digest includes `artifact_id` and `armed_at` from the authenticated
parent read. The later UPDATE only compares original run/digest, accepts *any*
of writing/sealed/armed, and checks null receipt and server-time bounds. It
does not compare the observed state, artifact relation, or arm time. Thus a
different legitimate adapter operation can change hashed fields between read
and terminal commit:

| Step | Finalizer | Competing operation | Durable parent |
| --- | --- | --- | --- |
| 1 | Reads complete sealed envelope with artifact `123`, null arm time | | sealed |
| 2 | Builds receipt hash for the observed relation | `arm` transitions this exact parent to armed | armed, nonnull arm time |
| 3 | Executes the current receipt SQL; its state-IN guard still matches | | cleanup_verified with hash for the old null arm time |
| 4 | Authenticated readback rejects the hash | | invalid terminal receipt remains committed |

Similarly, `attach` can change null artifact ID to the exact ID after the
finalizer's sealed read and before its UPDATE. These are existing source-owned
operations, not an administrator bypassing schema constraints. The concurrent
receipt test only races another terminal writer and does not exercise either
interleaving.

The helper does **not** return success or automatically purge in this case;
its readback correctly fails. Nevertheless, the failure leaves an immutable,
internally inconsistent receipt. `_terminal` rejects it on every later purge,
`_finalize` rejects terminal state, and the schema prohibits rewriting its
receipt or arm time and deleting its parent. Repair therefore requires
restricted intervention outside the reviewed API. Retained chunks continue
consuming budget, while the outstanding-state index no longer treats this
parent as outstanding. This violates the promised exact immutable receipt
contract, even though current live paths remain dormant and ciphertext is not
silently removed.

**Correction:** make the single UPDATE a compare-and-swap of the exact observed
lifecycle relation, including observed state and null-safe artifact/arm-time
equality. Original coordinates/creation time are already immutable and bound
by run/digest plus exact schema; do not replace this with another post-write
check or weaken receipt immutability. A lifecycle race should return zero
changes, leaving the winner's valid nonterminal relation intact and retaining
all chunks. Add deterministic competing attach and arm fixtures asserting no
terminal receipt is committed, no purge query occurs, and the resulting parent
remains usable for an explicitly new independently verified recovery attempt.

## Assessment of the remaining bounded slice

| Contract | Assessment |
| --- | --- |
| Receipt contents | Canonical digest includes all original bound fields, artifact relation, creation/arm/terminal time, verifier run/SHA and source-fixed check-set. Only public metadata is persisted. Verifier provenance and executed checks remain future coordinator obligations, not properties of a digest. |
| Atomic receipt attachment | State and all receipt fields are attached in one UPDATE. The P2 above concerns its incomplete compare predicate, not split state/receipt writes. |
| Server time | A fixed D1 `unixepoch()` observation is accepted only within the subsequent UPDATE's 30-second server window and at/after creation. This is intentionally a recent server-observed timestamp, not necessarily the exact UPDATE second. No caller clock or backdating flag is exposed. |
| Known response | Exactly typed changes=1 is required before complete authenticated readback. A lost response or zero-change competing receipt stops; an existing terminal readback is not repaired into acknowledgement. |
| Immutable terminal metadata | Terminal receipt fields cannot be updated; established arm time cannot change. Original bound coordinates are immutable; parent DELETE always aborts. |
| Exact bounded purge | The private helper authenticates the provided original envelope, validates the terminal metadata digest, checks each present index/decoded bytes, and DELETEs only matching run/index/hash/ciphertext under the matching terminal receipt. Known changes=1 and exact absence follow each DELETE; final typed aggregate must be zero and parent unchanged. |
| Lost/partial purge | A committed-but-lost DELETE stops immediately without retry. A separately invoked helper can observe an absent index and skip it rather than resubmit. It needs retained authentic original bytes because complete D1 read fails after partial purge. Repeating external attestation before resumption remains the absent coordinator's explicit obligation. |
| Tombstone and resource accounting | Parent receipt remains permanently. Same original run cannot be prepared again. Existing one-writing/sealed/armed uniqueness and all-nonpurged reservation remain unchanged; terminal retained chunks still count and empty receipts retain their 4096-byte allowance. |
| Capability/privacy boundary | No public CLI, workflow wiring, generic passed boolean, alias mutation callback, key storage, plaintext mail/owner SQL parameter, or logging path is added. Python underscore methods are conventions, not access-control capabilities; this is trusted dormant library code. |
| Compatibility | New columns/triggers amend an unapplied staging-only create-once migration. Tenant tables, normal migration streams, Mail runtime/API and established artifact contract are unchanged. No migration/latency proof is inferred. |

Receipt hashing is public consistency checking, **not cryptographic proof of
external cleanup**. `_finalize` and `_purge` are expressly private, unwired
low-level boundaries. No concrete independent read-only recovery/native-session
and scratch-teardown coordinator exists yet. Its absence is not disguised by
the synthetic fixture's `terminal()` helper, whose docstring explicitly excludes
real attestation. This remains a live blocker.

## Tests and provider evidence limits

The inspected additions exercise atomic receipt fields, verifier/check-set
binding, terminal/arm immutability, retained permanent parent, rejected reprepare,
lost receipt response, competing terminal zero-change loser, receipt/foreign
envelope rejection, and a maximum 31-chunk partial purge after a committed-but-
lost DELETE. These are injected in-memory SQLite and synthetic-crypto contracts;
the existing real-AES hosted check has not been extended to terminal/purge by
this commit. Earlier hosted passes through `f9f67bc` do not validate new code.

Additional discriminating coverage after the P2 fix should reject stale/future
or malformed server-time observations without terminal mutation, and zero-change
purge responses without continuing to the next chunk. These are evidence gaps,
not additional demonstrated defects. Real D1 SQL/schema/response semantics,
staging token authority, latency/shared-mail regression and synthetic encrypted
roundtrip remain separately authorized hosted/provider gates.

Cloudflare documents broad [SQLite SQL compatibility](https://developers.cloudflare.com/d1/sql-api/sql-statements/),
and SQLite documents [UPDATE-OF triggers and RAISE](https://www.sqlite.org/lang_createtrigger.html).
The added triggers are validation-only; no trigger introduces extra row writes.
Consequently the previous narrow reasoning for the optional typed
[D1 query changes counter](https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/)
still applies under exact schema: one matching primary-key transition plus
authenticated readback is needed, not a generic HTTP-success claim. This is
source compatibility reasoning, not evidence of applied real-D1 behavior.

Industry practice distinguishes request identity and unknown side effects,
as described in [AWS's idempotent API guidance](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/).
The academic [RIFL work, SOSP 2015](https://sigops.org/s/conferences/sosp/2015/current/abstracts.html)
likewise motivates associating operation completion metadata with the operation.
These support the conservative no-ACK-repair/no-DELETE-replay boundary; neither
turns this operations receipt into exactly-once Mail/provider cleanup or replaces
the missing independent coordinator. No new distributed framework is warranted
to fix the local predicate: an exact conditional write is the smaller remedy.

## Unchanged live blockers

After correction and independent source review, hosted dormant tests may be the
next bounded step. Live remains NO-GO until concrete executed recovery and native
teardown, wrapper/expiry-recovery integration, metadata watchdog/real Agent intake,
acknowledgement/freshness gates, exact staging provenance/migration/schema,
permission/latency evidence and all existing owner/service/hold/capture-off and
immutable artifact admission gates are complete. No key retirement, age purge,
schema rollback/drop, admission bypass or unknown Mail DELETE replay is authorized.
