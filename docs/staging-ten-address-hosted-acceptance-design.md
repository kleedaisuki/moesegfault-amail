# Single-account hosted ten-address and reserved-name acceptance

Status (2026-10-01): **single-account source increment; NO-GO for live dispatch**.
The quota/reserved-name campaign is independent of two-principal mailbox
isolation. A single already verified synthetic staging account can prove ten
simultaneous owned allocations, exact reserved-name rejection, the eleventh
owner-limit rejection and route cleanup. It cannot prove cross-owner access
control. Requiring B or an earlier isolation run here unnecessarily serialized
an orthogonal boundary behind B's verification-inbox/R2 capability blocker.

The current intended principal is existing synthetic **A**, authenticated afresh
through normal native PKCE and independently bound to its verified contact,
protected username and Identity pairwise subject. This is not the user's account.
No account is created or contact-verification transport exercised by this job.
An account with any non-retired address fails preflight; do not delete unrelated
data to obtain an empty test account. Earlier one-principal SMTP acceptance is
reused as evidence of the native flow, not as a quota or isolation pass.

Manifest schema/envelope **v2** authenticates Identity and Login immutable
revision IDs, the verified username and exact native client ID alongside Mail
version, owner, checkout and full baseline. Dormant v1 source never uploaded
live recovery artifacts, so no deployed recovery contract is migrated. V1
ciphertext is rejected rather than silently supplied incomplete provenance.
Independent review and hosted source tests remain prerequisites. No local
execution, live alias, provider mutation, SMTP or deployment is performed by
this source change.

Hosted source evidence (2026-10-01): exact checkout `3542a5f` passed the
[normal source CI run 36766439483](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36766439483)
(all six selected jobs), and independent
[workflow lint run 36766439302](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36766439302)
passed. The infrastructure lane explicitly executed and passed the pinned real
AES-GCM test step; this closes the earlier **real cipher integration** source
prerequisite for the containing identity/manifest/readback/crypto commits.
This source run predates native adapter `8d39444` and fixture correction
`acc68ea`; those later native fixtures are not covered by this evidence and
still require hosted execution on a containing reviewed SHA. None of these
source runs created an address, provider rule, message, account or deployment.
**Live ten-address acceptance remains NO-GO and not executed.**

Readback source increment (2026-10-01): the non-executable
`staging_ten_address_readback.py` adapter reads only configured staging D1/R2
and complete zone rules. It brackets a bounded full allocation SELECT with
independent counts, captures every address column, exhausts provider pages,
classifies literal worker/forward/drop rules and rejects unknown matcher/action
shapes. A digest of **every raw rule field** supplements semantic normalization;
forward targets, priorities or unknown fields cannot silently disappear from
unrelated drift checks. Two equal consecutive complete snapshots are required,
not an assertion that separate services share an atomic transaction.

The v2 baseline now also authenticates the full bounded R2 key/metadata digest
inventory. ETag/size/last-modified metadata must be present to support the
same-key replacement check; their documented optional API shape is not
silently treated as evidence. Prefix/cleanup checks reject new, removed or
same-key changed objects;
an independent unfiltered D1 message aggregate includes deleted and outbound
rows for all campaign candidates. No mail object GET is needed by this quota-only
probe. This avoids coupling quota acceptance to the separate verification
inbox's existing-object GET/DELETE capability. It does require successful
complete **mail-bucket LIST** observations and fails closed if that capability,
inventory bound, or stable snapshot is unavailable. Unrelated storage change
can conservatively invalidate a campaign; it never authorizes deleting an object.

Still missing for live dispatch: normal PKCE wrapper and subject readback, exact
CI/binary provenance, serving/binding/hold checks, immutable upload/download
orchestration, same-artifact recovery entry point and pinned real AES-GCM hosted
integration. No manual workflow target has been added; independent review and
hosted synthetic CI must pass first.

Source increment (2026-10-01): `staging_ten_address_hosted.py` implements the
dormant campaign controller: structured execution/provenance gate contracts,
pre-mutation sealing, exact immutable artifact readback, strict native CLI
HTTP-409/code/empty-stdout oracles, 28 reserved submissions, ten serial adds,
one eleventh denial, complete prefix/global/provider/owner readback and
full-manifest reconciliation in `finally`. Success labels are returned only
after exact cleanup and final serving-pin/storage readback. Captured outputs
and adapter exception text are never emitted. Cooperative interruption enters
cleanup; a killed process still requires external same-artifact recovery.

The existing recovery oracle incorrectly named `amail-ingress-staging`;
source config and deployed acceptance adapters name `amail-inbound-staging`.
The oracle and fixtures now use the actual configured ingress, with a hosted
synthetic test binding it to `crates/mail-worker/wrangler.toml`. This fixes a
false unsafe-rule rejection; it does not broaden deletion eligibility.

`test_staging_ten_address_hosted.py` adds synthetic positive/denial, provenance,
durability, ambiguous-create, reserved regression, eleventh success, capacity
denial, cancellation and cleanup contracts. These tests remain pending hosted
execution; only static AST parsing and diff whitespace checks were performed
locally. Synthetic AEAD remains deliberately authentication-only.

There is still **no live entry point or integrated normal
PKCE wrapper, artifact uploader/
downloader or workflow dispatch target**. `Evidence` describes observations
that a reviewed wrapper must independently obtain, not authorization for an
operator to supply booleans or arbitrary provenance. The v2 manifest seals Mail, Identity/Login revisions and verified username;
the wrapper must obtain these observations independently before exposing mutation.
The wrapper must also validate a CI-built Windows binary, staging bindings,
full provider matcher/action inventory and independent message/R2 absence.
Pinned `cryptography` installation and real AES-GCM integration tests remain
required. No live run, cleanup or quota pass is claimed by this increment.

Independent-review corrections: negative CLI parsing now accepts the actual
reqwest `HTTP 409 Conflict` status display (and numeric-only legacy display),
while requiring the exact 409/code pair, canonical correlation field and only
the CLI's closed optional diagnostic grammar. Provider bodies, other reason
phrases/statuses, appended JSON/HTML, duplicate diagnostic lines and generic
errors cannot satisfy the negative oracle. Fixtures now model actual status
display instead of hiding the reason phrase.

Recovery now sends each supported DELETE once and polls exact readback until
the row is retired with zero reconciliation work, no saved rule ID and no
matching route. A DELETE-202 `retired + needs_reconcile=1` state is transient,
not an immediate cleanup failure. Waiting is read-only and bounded to six
minutes per in-flight retirement, covering the configured five-minute Cron
interval plus headroom. Already-pending retirement from an interrupted run
is likewise settled without resending DELETE. A timeout fails cleanup and
requires same-manifest recovery. Synthetic fixtures exercise deferred route
removal, timeout/no replay and recovery of an earlier DELETE 202. These
corrections still require hosted tests; no live provider behavior is claimed.

Source increment: `infra/tests/staging_ten_address_manifest.py` now implements
the dormant, side-effect-free candidate/manifest envelope, private artifact
readback gate, complete normalized snapshot contracts, prefix/drift checks and
exact supported-delete recovery controller. Its synthetic contracts are in
`test_staging_ten_address_manifest.py`, discovered by the existing hosted
infra unittest job. No browser wrapper, integrated campaign mutator
or workflow target is exposed. The later readback source is non-executable. The normalized snapshot input must eventually
come from a complete source-reviewed adapter, not a filtered caller-provided
inventory. Independent identity/provenance verification, service-version checks,
message/storage absence, deadline/key retention enforcement and artifact
upload/download orchestration remain **unimplemented integration gates**.

AES-GCM sealing/opening follows the
[cryptography AEAD API](https://cryptography.io/en/latest/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESGCM)
and lazily requires the reviewed `cryptography` package;
missing dependency fails closed. A future hosted wrapper must pin/install it
and execute actual AES-GCM integration tests before receiving mutation
capabilities. Current envelope tests inject an authentication-only synthetic
fixture and do **not** prove encryption/library behavior. All code errors are
fixed source-owned codes; there is no live CLI entry point or raw-data output.
The root recovery key is domain-separated into a cipher key, independently of
the candidate-derivation namespace. No secret is configured by this increment.
Snapshot rows retain every column from address migrations `0001` and `0008`:
the resource-map key is `address`, and values include `local_part`, `slot`,
owner issuer/subject, state, rule ID, creation time, `needs_reconcile` and signed
`next_reconcile_at`. The latter legitimately allows `-1`; production may leave
its old value after retirement settles, so a settled tombstone does not require
a zero schedule. Full baseline equality nevertheless catches unrelated
local-part, slot and schedule changes. Hosted synthetic tests bind this field
set to the actual migrations, reject projections/malformed types, and cover
these count-preserving drift cases.

## Scope and source evidence

Use the already verified synthetic principal A with its current protected
credentials. Keep [second-principal provisioning](staging-second-principal.md)
and [two-principal mailbox isolation](staging-two-principal-mail-isolation.md)
as separate acceptance paths: neither their pass nor a user-supplied override
is required or claimed by quota acceptance. Do not create another principal,
use the owner account, repeat SMTP fixtures, or turn the mixed
`staging_address_isolation_e2e.execute` into the default acceptance path.
This narrower test uses **one account, ten temporary literal routes, zero SMTP
submissions and zero mail messages**.

The reviewed source observations motivating a separate path are:

* `staging_address_isolation_e2e.execute` puts ten aliases on A, requires SMTP,
  and records mutation intent only in a process-local dictionary. Cancellation
  loses that dictionary and its reserved-name baseline.
* `staging_hosted_e2e.execute` already implements normal synthetic PKCE and restricted
  Identity readback binding verified contacts to protected usernames
  and their pairwise subjects; only the selected account is required here. Reuse this contract, not auth-store
  copying or a fabricated verified D1 row.
* `staging_mail_e2e.cf_rules` exhausts bounded count-consistent pages and rejects
  duplicate rule IDs; `assert_route` verifies the exact enabled API-owned rule
  and staging ingress action. Reuse these complete observations.
* `add_address` in `crates/mail-worker/src/lib.rs` returns HTTP 409 with
  `reserved_or_invalid_name` before address lookup, and `address_limit` when
  its owner-scoped insertion cannot claim a slot. Before that insertion it
  checks global `USER_ADDRESS_CAPACITY=198` against all `state!='retired'`
  D1 rows, returning `capacity_exhausted` at that boundary. Negative acceptance must
  match status and code, not merely a nonzero CLI exit or code substring.

The old harness remains prepared, not an executed ten-address result. Its
mock tests remain useful but do not prove the stronger hosted contract here.

## Mutation budget and prerequisite evidence

| Gate | Required evidence before any `address add` |
| --- | --- |
| Execution boundary | `workflow_dispatch` only; exact branch `refs/heads/codex/amail-v0.1.0`; staging Environment; literal `RUN_STAGING_TEN_ADDRESSES`; attempt 1 only; no push/schedule/reusable unconfirmed call |
| Hosted source | Green hosted CI for the exact checkout SHA, including synthetic denial/recovery contracts; CI-built Windows `amail.exe`; no local test/build |
| Account readiness | Normal verified synthetic A contact, username/pairwise-subject binding via current Identity readback; fresh native PKCE in this run; no account provision/recovery in quota job |
| Service provenance | Single 100% serving Mail version matches expected pin, staged Identity/Login revisions recorded; no concurrent staging deployment; recheck Mail serving pin before mutation and after cleanup |
| Empty account | API `address list` empty, owner-scoped D1 non-retired count zero, no preexisting provisioning/deleting/reconciliation row; do not delete data to make the precondition true |
| Global application capacity | Complete staging D1 global `state!='retired'` baseline count **at most 187**, across every owner and all pending/provisioning/active/deleting states; complete canonical non-retired row baseline sealed before mutation; unknown schema, incomplete inventory or count disagreement fails closed |
| Provider capacity | Complete rule inventory, configured domain confirmed as `mail-staging.moesegfault.dev`, at least 12 free rule slots (10 planned + 2 reserve); no truncated/unknown matcher inventory |
| Global hold | Public sending remains held; staging-only resource bindings independently checked; no SMTP credential passed to this job |
| Recovery readiness | All candidate D1/provider baseline and exact authenticated owner captured and durably sealed before mutation; protected recovery key available; upload confirmation established; same-run recovery procedure source-reviewed |

[Cloudflare's current limits](https://developers.cloudflare.com/email-service/platform/limits/)
document 200 routing rules per domain. Conservatively gate on **both** the
staging-domain count and total zone rule inventory staying at or below 188
before the ten-route campaign, unless a separately evidenced provider account
contract establishes a different shared ceiling. This can reject a safe run
but cannot invent headroom from a narrower subdomain filter. Count disabled
rules too. Unknown/multiple/nonliteral matchers must be classified explicitly
or fail closed, not silently omitted. The check is an admission observation,
not a provider reservation; the serial campaign must stop on capacity errors.

Provider inventory alone is insufficient: pending or deleting allocations
can consume application slots without active provider rules. Independently
read bound staging D1 `SELECT COUNT(*) AS n FROM addresses WHERE
state!='retired'` and a complete bounded, stable-order inventory of those
rows; inventory length must equal the aggregate count. Baseline ceiling
**187**, rather than 188, ensures ten accepted aliases bring global allocation
to at most 197. At 198 the eleventh request can return `capacity_exhausted`
before reaching the owner-slot check, obscuring the intended quota oracle.
Count every owner and every state except `retired`, including unknown states;
never infer this number from active provider rules or the selected owner alone.

Capture global inventory/count in a consistent D1 read snapshot where
possible. For paged observations, verify independent final count and canonical
digest stability and reject drift. This is not a reservation against concurrent
clients or Cron. After each accepted alias and immediately before/after the
eleventh request, require global count equal to baseline plus the exact live
run-owned prefix, and unchanged canonical unrelated-row state. Any other
allocation, retirement or state change stops the quota claim, even if a later
response contains `address_limit`; reconcile this manifest without replaying
the campaign.

Use the existing `staging-native-mail-acceptance` concurrency group, with
`cancel-in-progress: false`, and ensure deployment jobs share an equivalent
exclusion. Workflow-level cancellation, manual deploys and Cron are not fully
prevented by a job lock, hence the independent pin and reconciliation gates.

## Exact candidate plan and private recovery manifest

Derive eleven lowercase local parts `qt0-<nonce>` through `qt10-<nonce>` from a
domain-separated HMAC of the protected recovery key, exact GitHub repository,
workflow run ID and original attempt 1. Encode exactly 128 private nonce bits
as unpadded lowercase base32 (26 characters): `qt10-<nonce>` is 31 characters,
within the Worker's 32-character local-part bound. A 32-character hexadecimal
nonce would make that candidate invalid and is forbidden here.
The recovery command takes only numeric original run coordinates, never an
operator-supplied alias or owner. A restarted Actions attempt must refuse to
run the campaign; it may only dispatch the separate reconciliation target.

Freeze the 25 reserved names already declared in the existing harness as a
source oracle. Validate their equality against the Worker source during
hosted tests so a newly reserved microservice name cannot silently escape the
campaign. Check representative uppercase spellings while A is empty, before
quota filling, to separate normalization/reservation failures from the slot
limit. The static reserved candidates are not run-unique and therefore need
stronger recovery protection than nonce-scoped aliases.

Before the first mutating call, capture a versioned full-plan manifest:

* repository, exact checkout SHA, workflow identity, original run/attempt,
  UTC preflight time and deployed serving-version pins;
* exact issuer/subject owner A and protected username binding, in memory;
* ordered raw CLI submissions, including case variants, and a separate
  deduplicated canonical normalized resource-baseline map for all eleven
  nonce aliases and reserved candidates; multiple spellings intentionally
  point to one canonical resource, not duplicate map entries;
* exact D1 baseline for every candidate, including absent vs retired/active
  state, owner, creation time, provider rule ID and reconciliation fields;
* complete exact provider rule baseline for every candidate, including any
  existing operational rule; store unrelated rules only as canonical digest;
* A's baseline owner count and the capacity/hold observations;
* complete global non-retired D1 baseline rows, aggregate count at most 187,
  canonical digest and predicate/schema version, including all owners and
  pending/provisioning/deleting allocations.

Seal this manifest using authenticated encryption with a **repository-level**
protected recovery key. The ciphertext can be retained as a short-lived
Actions artifact; plaintext remains only under repository `.temp` and must
never be uploaded or logged. Bind repository/run/attempt/schema as associated
data; reject swapped, truncated, duplicate canonical map keys, invalid
submission-to-resource mappings or wrong-owner manifests.
Do not reuse a login password as an encryption key or rotate/delete the key
while a campaign may still need recovery. Implement this only with a reviewed
library and pinned hosted dependency, not handwritten cryptography.

Use a separately generated 256-bit random key with an explicit nonsecret key
generation ID in the authenticated envelope. Retain ciphertext for at least
30 days, require routine same-run recovery within 24 hours of interruption,
and keep the corresponding key generation until exact cleanup is documented
and the artifact retention period has elapsed. The 24-hour bound triggers
escalation, not destructive expiry or permission to abandon cleanup. A missing
artifact or unavailable key fails closed and requires restricted operator
reconciliation; it never authorizes a fresh campaign. Artifact expiry must not
precede confirmed cleanup: unresolved runs require preserving their sealed
manifest in a protected durable store before expiry, with no plaintext logs.

The manifest-upload step must complete successfully **before** a later step
can load mutation credentials and start the campaign. A write in `finally`
or a post-job artifact upload is insufficient: a killed runner skips it.
Use an exact reviewed ciphertext-file path, never a directory or wildcard;
require `include-hidden-files: true` for that file under `.temp`,
`if-no-files-found: error`, a nonempty returned artifact ID and immutable
no-overwrite semantics. Download the exact artifact ID and authenticate its
envelope, then compare the complete manifest with the in-memory baseline
before mutation. A successful upload step alone does not establish durable
content: [upload-artifact's documented defaults](https://github.com/actions/upload-artifact#inputs)
exclude hidden files and only warn on missing files.
Full candidate scope, not a best-effort list of acknowledged successes, covers
an unexpectedly successful reserved or eleventh-name call. Secret-free logs
can show only manifest-present/version/validated booleans and fixed labels.

## Minimal hosted sequence

1. Authenticate and perform every gate above. Capture and durably seal the
   complete pre-mutation manifest. Stop on any unknown state; no cleanup of
   unrelated baseline state is allowed.
2. While A has zero slots, submit each source-listed reserved local part plus
   representative case variants once. Require nonzero exit, **empty stdout**,
   bounded stderr parsed as exact HTTP 409/`reserved_or_invalid_name`. After
   each call require A's owner count unchanged and candidate D1/rule baseline
   unchanged. Stop immediately on unexpected success or side effect.
3. Add `qt0` through `qt9` serially, once each. For each, require the CLI's
   returned exact address, owner-scoped D1 state `active`, matching issuer/sub,
   one exact enabled API-owned ingress rule, and A's full list/count equal to
   the expected prefix. Require global non-retired count equal to baseline
   plus prefix length and unchanged unrelated-row state. Activation polling
   is read-only; it must not replay
   `address add`. No success-path idempotent re-add is needed for this slice.
4. With all ten active simultaneously, snapshot all ten D1 rows and exact
   provider rules. Independently require global non-retired count equal to
   baseline plus ten and **at most 197**, unchanged unrelated-row state and
   provider-capacity headroom. Submit `qt10` **once** and require exact HTTP
   409/`address_limit`, empty stdout, no eleventh D1 row/rule, and ten-row
   owner/provider/global count and unrelated-row snapshots unchanged.
   `capacity_exhausted` is not a per-owner quota pass. This distinguishes genuine quota
   enforcement from a failed unrelated provider request or silent eviction.
5. Always enter exact-manifest reconciliation. Emit the success label only
   after cleanup and final serving-pin match. If primary acceptance succeeds
   but cleanup is uncertain, the overall run fails; it is not a pass.

Possible terminal labels: `ten_address_reserved_verified`,
`ten_address_limit_verified`, `ten_address_cleanup_verified`,
`ten_address_provenance_unverified`, `ten_address_mutation_ambiguous`,
`ten_address_cleanup_required`. They are fixed source-owned labels; no alias,
subject, owner, username, rule ID, timestamps, provider response, raw CLI
output, credentials or token claims are interpolated.

## Cancellation-safe reconciliation and ambiguity policy

Recovery loads and authenticates the exact original manifest and obtains a
fresh **normal selected owner login**, with the same current verified owner binding. It
does not register an account, send SMTP, add an alias, or replay the failed
request. The source and staging bindings must still match the recovery
contract; a newer deployed revision needs deliberate review, not a wildcard
override of the pin.

For each candidate absent from both baseline D1 and provider rules, delete
through the supported A CLI only if current D1 proves the exact authenticated owner,
creation time not before the manifest's preflight, and current rule is either
absent or the expected exact API-owned staging ingress rule bound by D1. A
foreign owner, altered provider action, inconsistent rule ID or unowned orphan
requires manual reconciliation, **never direct blanket provider deletion**.
The **complete current exact-match rule set** must be empty or exactly one
expected enabled API-owned ingress rule, with the saved D1 rule ID bound to
that rule (or independently confirmed absent when the match set is empty).
Any additional rule, foreign/disabled rule, duplicate or action mismatch
blocks CLI deletion: `delete_address` enumerates all exact matching rules and
the saved ID, so checking one good rule while ignoring another can destroy
unrelated provider state. A saved ID pointing to another extant rule likewise
blocks deletion even when no address matcher remains.
For candidates with any preexisting D1 row or provider rule, preserve the
baseline and require its unchanged readback. In particular do not delete an
operational `abuse` or `postmaster` rule after a reserved-name regression.

Retirement is intentionally not database restoration: successful aliases
leave A-owned `retired` tombstones, with no rule ID, no reconciliation work and
zero non-retired A slots. Record this as the allowed final state rather than
claiming all D1 rows are absent. Assert no messages/storage were created (zero
SMTP budget), and compare unrelated provider state against its baseline
digest. A preexisting tombstone is never deleted. Read-only retries may wait
for the documented reconciliation deadline; uncertain DELETE is not blindly
resent. First inspect the exact row/rule; if still live, re-enter only the
reviewed same-manifest recovery path, not the quota campaign.

This follows [AWS's production retry guidance](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/):
an uncertain response is not evidence that the side effect did not happen.
The test uses the original resource identity for reconciliation and does not
consume new aliases to conceal ambiguous outcomes. The separate two-principal
test supplies an independent security relation; this campaign supplies the
serial capacity boundary, not a concurrent-race proof.

## Hosted synthetic acceptance contracts before wiring

The future `test_staging_ten_address_*` suite must run only in hosted CI and
must contact no live service. Required failures and positive contracts:

* unconfirmed/nonbranch/attempt>1 dispatch stops before secret loading;
* absent, pending or wrong-username synthetic A fails before mutation;
* missing hosted source provenance or a fresh PKCE/Identity subject mismatch fails;
* a quota pass never supplies or substitutes for two-principal isolation evidence;
* split/mismatched Worker pin and a pin changed during the campaign fail;
* paged counts changing, duplicate IDs, unknown matchers, 189 rules, or
  existing candidate state fail closed; 188 complete conservative rules pass;
* global D1 baseline 187 passes admission; 188 fails despite provider
  headroom; pending/provisioning/deleting and all owners count; incomplete or
  unstable inventory and aggregate disagreement fail;
* after ten accepted aliases, count must equal baseline plus ten and be at
  most 197; external allocation/retirement/state drift around the eleventh
  request stops the claim; `capacity_exhausted` never proves owner quota;
* all generated local parts fit 32 characters; normalization variants share
  one canonical resource map entry without skipping raw submissions;
* envelope key generation and original coordinates bind recovery; missing
  key/artifact or overdue recovery cannot authorize a new campaign;
* ten serial allowed aliases pass; transport errors and generic 409 do not
  satisfy either negative oracle; unexpected stdout is failure;
* eleventh success/eviction, reserved success and a rejected call with side
  effects enter cleanup for the **entire** manifest candidate set;
* timeout immediately after a created alias, process cancellation after
  manifest upload and upload failure before mutation are recoverable without
  generating a new plan or repeating `add`;
* recovery rejects altered ciphertext, wrong run/owner, baseline operational
  rules, foreign rows and action/rule-ID mismatches; no wildcard deletion;
* missing/hidden ciphertext, empty artifact ID or failed authenticated
  download/readback blocks mutation; duplicate or foreign current exact-match
  rules block CLI deletion, including a saved ID bound to unrelated state;
* retired tombstones are accepted only with zero live slots, no exact route,
  no pending reconciliation and unchanged unrelated/operational state;
* fixed-label failures never print mocked secrets, aliases or provider bodies.

Until these source, workflow and recovery contracts receive independent
review and hosted tests, **leave `ci.yml` dispatch options unchanged**. No new
secret is configured by this design. Implement the dormant single-account wrapper/manifest layer using the already
verified synthetic A, independently obtain fresh native PKCE and current
Identity/service provenance, review it, run hosted CI, then permit one guarded
campaign. B verification and two-principal isolation remain separate work. Record checkout
SHA, deployed pins, Actions URL and privacy-safe outcome in validation notes.
No current result claims ten-address, reserved-name, concurrent quota races,
outbound ownership, production capacity or release readiness.

## Complete inventory adapter references

The readback shape is grounded in the official
[Cloudflare routing-rule LIST API](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/list/)
and [R2 object LIST API](https://developers.cloudflare.com/api/resources/r2/subresources/buckets/subresources/objects/methods/list/)
(accessed 2026-10-01). R2 documents lexicographic `start_after` and optional
ETag/size/last-modified metadata. The adapter deliberately requires these
metadata fields for an existing object and explicit empty keyset completion;
metadata omission is an inconclusive capability, not an empty bucket. Complete
provider source-owned fixtures remain hosted-only tests; this reference check
is not live tenant acceptance.

## Real recovery cipher hosted integration

`infra/tests/ten_address_requirements.txt` pins `cryptography==50.0.1` from the
[PyCA-maintained package release](https://pypi.org/project/cryptography/50.0.1/)
(accessed 2026-10-01). The existing infrastructure probe CI lane installs a
binary wheel and explicitly runs `staging_ten_address_crypto_check.py` before
the ordinary synthetic suite. This is a real AES-GCM roundtrip/tamper/AAD/private
ciphertext integration test; a missing or different package version fails
instead of skipping. It uses only synthetic in-memory records, never Secrets,
local builds or live provider resources. Hosted execution remains pending until
the reviewed commit passes CI; source wiring is not an encryption acceptance
result or permission to dispatch quota mutation.

## Native adapter source boundary

`staging_ten_address_native.py` now provides a non-executable composition seam
for supported CLI operations and one fresh hosted-Windows native login. The
CLI child inherits only the existing staging environment allowlist, never
provider/GitHub/synthetic-login Secrets. Only source-listed reserved submissions
or eleven exact run-derived aliases can be added; supported deletes remain
subject to the controller's immediate complete owner/rule audit. Captured CLI
output stays private and is never replayed after an ambiguous process outcome.

The account scope reuses normal first-party synthetic A credentials and fresh
browser/CLI-home PKCE, reads A's verified username/contact/pairwise subject
independently before/after login, and ignores B's presence or verification state.
Current CLI `auth status` intentionally does not disclose a token subject. The
identity relation follows the submitted exact username in a fresh browser and
independent current Identity ownership readback; it does **not** copy/decrypt a
local token to manufacture a subject attestation. A successful or partially
persisted native home is locally logged out before deleting only its newly
created repository `.temp/ten-address-native-*` directory. Normal logout attempts
remote refresh revocation but its local result is not evidence of successful
remote revocation on a provider outage.

This adapter alone grants no live acceptance. Full wrapper assembly still needs
source/binary and single-serving service readback, actual hold/binding evidence,
immutable manifest upload/download metadata validation, external same-artifact
recovery and manual-only workflow review. Native synthetic fixtures are
hosted-only; no CLI/browser/provider was run locally by this change.

## Concrete remaining hosted composition

Do not add a generic configurable campaign framework or a caller-supplied
"passed" boolean. The source seams compose into one narrow three-phase job:

1. **Prepare (read-only remote state).** Verify exact successful hosted source
   run and its tested Windows binary artifact for the checkout, then read the
   single 100%-serving Mail/Identity/Login revisions, staging resource bindings
   and persisted global sending hold. Reuse normal native A login through
   `native_account`; independently obtain the selected verified subject via
   `selected_owner`. Construct `Evidence` only from these observations. Derive
   eleven aliases from the separate recovery key and original run coordinates.
   Build `Readback` from the fixed staging resources, expose `Cli.owned`, and
   call `hosted.prepare` to seal the full baseline. Write only ciphertext to
   an exact new `.temp` file; no plaintext manifest or token may be uploaded.
2. **Durability boundary, then campaign.** Upload exactly that ciphertext file
   using immutable/no-overwrite artifact semantics with retained key generation
   and >=30-day retention. Independently read artifact metadata: exact original
   run, checkout/workflow identity, name, artifact ID and nonexpired lifetime.
   Download that **same ID**, reject additional/symlink/unexpected files,
   authenticate envelope and compare exact downloaded/local ciphertext before
   loading add/delete capabilities. Re-establish native/service observations
   for the campaign process rather than carrying an unverified CLI-home path
   through job output. Compose `Adapter(read=Readback.read, list_owned=Cli.owned,
   add=Cli.add, delete=Cli.delete, storage_empty=Readback.storage_empty, pin=...)`.
   Implement read-only bounded activation settlement for the exact expected
   prefix, never replay add on timeout. The controller owns reserved/quota
   sequencing and `finally` recovery; no SMTP credential belongs to this job.
3. **Same-artifact recovery.** An interrupted/killed run must be recoverable by
   original run/attempt/artifact ID and retained key generation, not a nonce
   guessed from public logs. Verify the original immutable artifact's metadata,
   authenticate its manifest, perform fresh normal login for the sealed owner,
   and recheck reviewed staging bindings and pinned service versions. Invoke
   only `hosted.recover`; no add capability is granted. Preserve uncertain
   encrypted artifacts and key generations until exact cleanup is recorded.
   Logout and remove only each phase's newly created `.temp` files/homes; never
   blanket-delete provider rules, messages, R2 objects or unrelated addresses.

A standalone manual-only workflow avoids increasing `ci.yml` dispatch inputs
or rebuilding/deploying unrelated services for this one acceptance. It must
share `staging-native-mail-acceptance`, use `cancel-in-progress: false`, attempt
1 and exact branch/confirmation guards, no push/schedule trigger, and recovery
that remains possible after a hard cancellation. These integration phases,
activation adapter and workflow are **not implemented or live-authorized** by
this document; they identify the remaining minimum trustworthy work rather
than allowing an unsafe shortcut through the dormant controller.

## Source/service admission increment (still no live entry point)

`staging_ten_address_provenance.py` independently reads the exact successful
push source run, complete bounded job inventory, all six executed cross-platform/
Worker/site/infra jobs and the explicitly successful real recovery crypto step.
It reads the **serving** single-100% Mail, Identity and Login versions with
version-scoped bindings and serving read brackets; split traffic, drift, omitted
binding inventory and provider errors fail closed. Mail reuses the existing
exact reviewed phase-aware binding checker. Identity requires the known staging
DB/audit/avatar resources, exact issuer/first-party origins/environment, and
constrained email sender binding; additional persistent/network/service kinds
are rejected. Version-bound scalar vars and secret names may evolve/rotate
without making amail own Identity's mechanism. Static Login must explicitly
read back an empty binding inventory, not omit it.

`Readback.sending_state` independently SELECTs the actual singleton global
`send_policy` row. Only explicit `held` supplies admission; absence, an allowed
row or malformed results do not become a fabricated hold observation. The
three-service relation and hold are repeated before admission returns. This
cannot reserve global services or prevent changes between reads; original
version equality must still bracket mutation and recovery in the assembled
workflow. CI binary artifact ID/digest validation and actual encrypted artifact
transport remain the next source increment; this module does not attest
uploaded/extracted binary bytes. No local test or live provider request occurred.

Identity binding expectations were retrieved from the sibling repository's
reviewed `wrangler.identity.jsonc`/`wrangler.login.jsonc` and bootstrap secret
contract (local sibling is named `moesegfault-indentity`, matching its remote).
The acceptance source imports no sibling runtime/config path on GitHub runners;
protocol-critical fixed expectations are explicit here, while the exact service
revision is obtained from provider readback and sealed by the manifest.
