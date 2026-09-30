# Independent review: explicit D1-only artifact-expiry recovery

Date: 2026-10-01. Reviewed source: `bec62632cf4d386ad5a852009ecb55982718a9b4`.
Contracts: architecture `871ac00`, revised escrow design/review, and coordinator
settlement correction `9890d48` / independent follow-up `6cb7e09`.

## Decision and limits

**After independently reviewing correction `6bcf05c`: GO for the bounded dormant
source seam and hosted source-only validation.** The original `bec6263` decision
was NO-GO pending the P2 below; the follow-up at the end closes it while retaining
the original failure mechanism. **Live remains NO-GO**, independently of this
resolved finding, because real D1 transport/schema/key and actual Agent intake
proof remain absent. No local tests/builds, executable harness invocation, private
provider/account request, migration, key access, artifact download or workflow
dispatch was performed in either review. Source fixtures are inspected evidence,
not test results.

The change correctly separates explicit D1 transport from artifact fallback,
historical identity from current implementation, and read-only recovery from
address mutation. There is one concrete conditional false-success path in
terminal-resume handling. It does not grant mutation or cause this invocation to
delete ciphertext, but it can assert ciphertext retention without observing the
current complete envelope after fresh recovery.

Reused the architecture, design, prior escrow/terminal/coordinator reviews;
inspected the three-file diff, surrounding acceptance, escrow, manifest, hosted,
provenance and native composition contracts, migration triggers and all seam /
purge callers. Unrelated worktree changes are excluded. Only this review document
is written; production source and tests are not modified.

## P2: terminal resume omits final authenticated ciphertext/receipt readback

Status: **resolved by `6bcf05c` after independent static follow-up below**.

**Location:** `infra/tests/staging_ten_address_acceptance.py:270-278`, especially
the `cleanup_verified` skip and the immediate D1 retained-result return.
**Confidence:** high for the source-derived failure path; conditional on a
concurrent permitted terminal chunk deletion. Not executed locally.

The D1 path initially calls `Escrow.read`, which exhausts and authenticates the
complete stable original parent/chunks. If the parent was already terminal, it
also validates `_terminal` before native recovery. After fresh native recovery,
native teardown, scratch removal and the full postchecks, however, it only reads
the current parent and checks whether its state is `cleanup_verified`. That state
skips `_finalize`; the new transport branch then returns
`ten_address_escrow_receipt_retained` without another `read`, byte comparison or
terminal-receipt validation.

An executable interleaving supported by the checked-in schema is:

1. A prior recovery has left a valid terminal receipt and complete chunks.
2. This invocation authenticates that complete envelope and starts its fresh
   native/external checks.
3. Another terminal artifact coordinator, using the existing `_purge`, deletes
   one or all chunks while those checks are in progress. The
   `staging_acceptance_chunks_retained` trigger expressly permits DELETE once
   the parent is terminal; the parent/receipt itself remains unchanged. An
   interruption of the other per-chunk purge can leave a partial envelope.
4. This invocation's remote checks and teardown succeed. Its final parent read
   still observes `cleanup_verified`, so it skips `_finalize` and reports the
   ciphertext-retained result although the complete envelope is no longer in D1.

This is not a fabricated malicious rewrite: the other deletion path and the
terminal deletion trigger already exist. Initial complete loading prevents
starting from a partial envelope but does not catch loss during the potentially
long fresh recovery. The artifact transport continues into `_purge`, which
validates the current relation; the new early return removes that last boundary
for D1 terminal resume. New-receipt `_finalize` does perform complete authenticated
readback, so the clearest gap is the already-terminal branch.

Impact is a false recovery/retention observation at the exact point intended to
distinguish complete retained ciphertext from historical metadata or partial
escrow. The architecture requires partial-envelope NO-GO and stable complete
encrypted readback. After artifact expiry, surviving partial chunks and the key
cannot reconstruct missing bytes. This seam does not itself destroy them, but its
result can hide the loss from its caller.

Future workflow concurrency and operational exclusion are mandatory and reduce
this risk, but no such entrypoint or executable exclusion is established by this
slice. A source-only coordinator should keep the bounded observational contract
instead of relying on a future lock to justify its final success label. This
finding does not ask for an impossible permanent-retention guarantee after the
function returns; it asks for complete authenticated evidence at the final
observation boundary, just as the initial loader already requires.

**Correction:** before returning the D1 retained label, call the existing complete
`Escrow.read(original_run, secret, generation)`, compare its exact envelope to
`downloaded`, and validate `_terminal` against the original binding. For prior
receipt resume, preserve the authenticated immutable receipt/lifecycle relation;
do not rewrite it as this invocation's receipt or infer a lost ACK. This can be
one common final D1 readback after either receipt creation or resume, without a
new format, purge permission or generic transaction abstraction.

**Hosted synthetic regression:** add an initially terminal/complete escrow
fixture that proves full fresh native/postcheck execution, unchanged receipt and
all chunks retained. Inject schema-permitted chunk deletion at native exit or
post-teardown privacy/readback; both partial and zero loss must fail without
receipt rewrite/purge SQL from this invocation. Add a competing receipt fixture
if terminalization during the checks is intentionally accepted. Existing tests
always prepare a sealed parent and therefore do not cover this resume branch.

## Confirmed source properties

| Requirement | Inspected evidence and boundary |
| --- | --- |
| Independent original invocation | `dispatch_record` queries `/actions/runs/{run}/attempts/1`, checks repository, fixed workflow, branch, manual event, run/attempt and exact SHA. D1 transport additionally requires distinct current/original run and original `completed`; historical success is not demanded. Missing metadata fails closed. |
| Original/current SHA separation | Authenticated `plan.checkout` must equal historical GitHub `head_sha`; current `checkout`, manual-run admission, all six source jobs / real-cipher step and Windows binary lookup use current `sha`. The new fixture deliberately uses different historical/current SHAs. Historical source CI ID or expired ZIP digest is not invented. |
| Exact existing crypto | No format/nonce/AAD/key derivation change. V2 canonical AAD is `[repository, original_run_string, "1", 2, generation]`; checkout is in authenticated plaintext, not AAD. Fixed generation is `ten-address-v1`; no arbitrary Secret lookup, resealing or key rotation is added. |
| Exact full D1 transport | Existing `read` checks source-fixed staging schema, immutable binding/reservation arithmetic, aggregate count/bytes, every bounded index, strict canonical base64, per-chunk length/hash, full envelope length/hash, authentication and repeated stable parent/chunk readback. Owner/baseline/services remain authenticated plan fields. |
| No artifact fallback | Explicit recover-only seam requires empty supplied artifact ID. Artifact content download is never called on D1 transport. Ordinary `execute/main` stays artifact-only; there is no exception catch that selects D1. Current binary artifact remains mandatory. |
| No address mutation | Recovery adapter receives forbidden add/delete callbacks; hosted read-only recovery ultimately reconciles with `delete=None`. Active/pending/provisioning allocation needs fixed manual intervention; bounded settlement polling grants no DELETE. |
| Settled tombstones | Corrected final `manifest.reconcile(..., None, ...)` accepts legitimate ten owned retired tombstones with no route/saved rule and `needs_reconcile=0`, including old scheduling metadata. Foreign baseline/resource/owner/pending drift is not filtered away. |
| Native and teardown checks | Fresh native principal and protected username must match sealed owner. Service/hold/privacy, full inventory/storage and recovery checks precede native exit; owned scratch removal and repeated service/full cleanup/storage/privacy checks precede receipt. Exceptions/cancellation bypass terminal SQL. |
| Receipt without purge | Newly created receipt uses existing server-time/lifecycle CAS, typed one-change ACK and exact authenticated readback. D1 branch does not call per-chunk `_purge`; historical artifact relation, including genuine null, is not replaced. Prior-receipt final readback has the P2 above. |
| Dormant scope | Searches found no CLI/workflow caller of either terminal seam. Tests are the only callers of the new public seam. No prepare/campaign terminal capability, mutation replay input or purge toggle is introduced. |

New inspected failure fixtures include missing/unsettled/same original run,
historical SHA mismatch, unsupported generation, wrong key, altered chunk digest
and active-alias manual intervention. Existing teardown/privacy/foreign-drift
fixtures exercise the shared coordinator, though these are not executed evidence
and do not replace transport-specific terminal-resume fixtures. Existing maximum
real AES/SQLite loader tests are separate from mocked composition and from D1.

## Independent live gates remain open

The current [D1 REST query reference](https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/)
types `params` as an optional array of strings and `meta.changes` as optional.
The existing `_http` sends integer/null values in fixed statements and requires
a nonnegative integer `changes` even for reads. This is an unresolved provider
shape/behavior gate, not newly introduced by this seam and not proof of a
demonstrated production rejection. Do not weaken ACK parsing or stringify null
without separately validating actual binding semantics. Real protected staging
proof must include SELECT results/metadata, null and non-null lifecycle CAS,
receipt ACK/readback, maximum-envelope/chunk transport and interruption behavior.
Any future atomic purge needs separate source/provider review; current D1 recovery
must continue retaining ciphertext.

GitHub's [specific run-attempt endpoint](https://docs.github.com/en/rest/actions/workflow-runs#get-a-workflow-run-attempt)
supports independent original-attempt retrieval. The implementation cannot
replace deleted/inaccessible run metadata with D1 coordinates. It also cannot
re-prove the vanished original GitHub ZIP digest from the ciphertext digest.

Actual Agent polling/dispatch intake, consumer health/freshness, protected
scheduled availability, authorization and actual handler acknowledgement within
the defined 24-hour intake deadline are still absent. A receipt-only seam is not
a watchdog or cleanup SLA. Acknowledgement cannot purge, close unresolved cleanup
or release the staging campaign gate. Shared mutation/recovery exclusion, key
retention and schema/provider proof remain separately required before live GO.

[RIFL, SOSP 2015](https://web.stanford.edu/~ouster/cgi-bin/papers/rifl.pdf) grounds
the useful distinction between durable completion identity and safe reclamation
of recovery state. Its exactly-once RPC machinery does not supply missing address
DELETE history here. The project's simpler retained-envelope/read-only model is
appropriate; the final observation should preserve its actual contract rather
than accepting old receipt metadata as proof of presently complete recovery data.

## Independent correction follow-up: `6bcf05c`

Reviewed complete three-file diff of
`6bcf05c6e126faa95290f2c58b581792b63cb052`, the surrounding final coordinator
boundary, unchanged `Escrow.read` / `_finalize` / `_terminal` contracts, the
synthetic database/fixture setup and namespaced migration deletion constraints.
No local test/build or deployment was performed. No new substantive finding was
identified in this bounded correction; the original P2 is closed.

The correction at `staging_ten_address_acceptance.py:271-284` assigns the exact
validated parent returned by `_finalize` to `row` when creating a new receipt.
Both that path and an existing terminal parent now pass through one common D1
final observation:

1. `Escrow.read(original_run, secret, generation)` repeats schema, exhaustive
   aggregate/index/canonical chunk validation, full envelope hash/length,
   authentication, immutable binding and stable complete parent/chunk readback.
2. `binding(downloaded, ...)` reconstructs the authenticated original envelope
   relation; `_terminal(final, binding)` checks terminal state, immutable original
   relation, verifier fields/check-set and exact receipt hash.
3. `actual == downloaded` compares full original ciphertext, not just receipt
   status or a parent hash. `final == row` compares the complete parent to the
   observed existing terminal parent or the exact acknowledged newly created
   receipt. Mismatch raises the fixed failure before the retained result.

The new-receipt helper still requires this invocation's known one-change ACK and
its own exact authenticated return. If that ACK is lost or zero, it raises before
the common final read; readback is not used to repair the lost acknowledgement.
An already-terminal path does not rewrite its historical receipt or substitute
the current verifier identity. If another valid verifier completed the terminal
transition before the final parent read, the common boundary validates that
current terminal relation after this invocation's full fresh recovery; it does
not claim this invocation wrote the receipt.

The final D1 validation contains no write or purge call. Its exceptions propagate
before the success return, and do not fall through to the artifact `_purge` below
the branch. Partial/zero chunks therefore fail in `read`; altered exact content,
parent/receipt relation or unstable readback also cannot produce the retained
label. The other admission, fresh-native, settled-tombstone, teardown and
postcheck boundaries are unchanged.

Inspected new source fixtures:

| Case | Evidence expected by the fixture |
| --- | --- |
| Prior terminal, complete ciphertext | Full fresh native recovery/teardown, same historical receipt/verifier, only the synthetic seeded receipt write, no artifact content download, add, address DELETE or purge. |
| Prior terminal, zero/partial late loss | Separate receipt-authorized SQLite actor removes chunks at native exit, after initial loading; final complete aggregate rejects, old receipt unchanged, no coordinator receipt rewrite/purge. |
| New receipt, zero/partial late loss | Wrapper first completes real synthetic `_finalize` and its authenticated return, then the separate SQLite actor removes chunks; the new common final read rejects, acknowledged receipt unchanged, no purge. |

For partial-loss fixtures, 100 bounded baseline object keys and SHA-shaped
metadata enlarge the authenticated envelope beyond one 65,536-byte chunk while
remaining legal under `Snapshot.validate`. The live synthetic world receives
that same baseline so the remote recovery oracle does not fail prematurely on
invented baseline drift. Deletion uses the schema's legitimate terminal gate,
not an impossible mutation of immutable ciphertext. Receipt-call counting
includes the synthetic seed and proves no second write on resume. These are
discriminating regression fixtures for the previously missing boundary, not
executed test evidence or a replacement for existing real-cipher/provider gates.

The result is an authenticated final observation, not a perpetual guarantee
against later privileged deletion. Existing workflow/staging writer exclusion,
separately reviewed atomic purge, retained generation key, D1 REST parameter and
metadata proof, and actual Agent intake/acknowledgement remain the independent
live requirements stated above. This follow-up grants no migration, provider
operation, key use, workflow wiring, dispatch or live campaign authorization.
