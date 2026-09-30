# Independent review: dormant ten-address manifest contracts

Scope: `b8a8e7b` and hardening `35cc2f6`, reviewed 2026-09-30. This is a
static review of the dormant Python module, its 14 synthetic test methods,
the associated design, existing hosted discovery command and address table/
Worker deletion semantics. No local tests/builds, workflow dispatch, login,
artifact upload, provider mutation or live acceptance was performed.

## Verdict

**NO-GO for accepting the current source contract as complete; one P2
correction is required before hosted source CI sign-off.** This does not mean
the dormant module must not be run in secret-free hosted tests. Live dispatch
remains independently NO-GO: the design explicitly leaves adapters, workflow
gates, real crypto integration, prior-isolation evidence and retention/pin
enforcement unimplemented.

## P2: normalized row contract drops fields needed by the drift oracle

Location: `infra/tests/staging_ten_address_manifest.py:32-33` (`ROW_KEYS`),
`Snapshot.validate`, `assert_prefix` and the final `reconcile` row comparison.
Confidence: high, established by source/schema inspection.

The exact allowed row keys omit `local_part`, `slot` and `next_reconcile_at`,
although all are stored address columns (`0001_initial.sql` and
`0008_address_reconcile_schedule.sql`). A future adapter cannot include them:
`set(row) == ROW_KEYS` rejects the fuller readback. It must discard them, so a
change in any omitted column produces the identical normalized snapshot.
Both the prefix oracle and final cleanup comparison then report unchanged
unrelated D1 rows. A candidate's preexisting reconciliation schedule likewise
cannot be sealed or compared, contrary to the design's explicit requirement
for complete candidate reconciliation fields. This is a readback/oracle gap,
not evidence of a currently deployed database corruption or unsafe deletion.

Correction: define a schema-versioned complete address-row representation,
including the three omitted columns and their domain validation (slot 0..9;
integer schedule allowing the established -1 urgency sentinel). Preserve
those fields in the sealed baseline and comparison. Add hosted synthetic
tests in which a baseline unrelated row changes only slot, local part or
next-reconcile time, plus a preexisting role/candidate schedule change; require
the existing fixed drift labels. Do not widen successful outcomes or add
provider mutation to solve this representation issue.

## Positive assessment and discovery evidence

- The root key requires 256-bit hexadecimal material. Candidate HMAC and
  cipher-key HMAC use distinct fixed domains. AES-GCM uses a fresh 96-bit
  `os.urandom` nonce, repository/run/attempt/schema/generation associated data,
  and authenticated bounded JSON; unavailable crypto fails closed. This
  matches the official library API's key/nonce/AAD contracts, but the injected
  synthetic AEAD does not attest real encryption or the unpinned dependency.
- Artifact readback requires an explicit numeric ID, byte-for-byte equality
  and successful authenticated opening. Actual immutable upload, hidden-file
  handling, retention/deadline/key preservation and download remain honest
  integration gates, not evidence already provided by this module.
- 187 global non-retired allocations plus ten yields at most 197, so the
  next request can reach the owner-quota check before the 198 global gate.
  Independent provider rule count includes disabled normalized rules; the
  full raw inventory/matcher/action adapter remains to be reviewed.
- Eleven 128-bit base32 nonce aliases have a longest local part of 31 bytes.
  Ordered uppercase submissions are separate from the deduplicated 36-resource
  map. Source reservation parity is tested statically against the Worker.
- Recovery audits the full exact-address rule set and saved ID, not merely
  existence of one good rule. Duplicate/foreign/action-mismatched rules and
  operational-baseline changes stop before candidate deletion. A delete
  exception is converted to a fixed ambiguous-outcome label with no replay;
  later recovery must load the same manifest and re-read current state.
- `35cc2f6` adds fixed-label snapshot callback handling, Snapshot type checks,
  malformed-state protection and random-generator failure handling. No raw
  provider/CLI exception rendering was found in these reviewed paths.
- `.github/workflows/ci.yml:1106` runs `python -m unittest discover -s
  infra/tests -v`. The filename `test_staging_ten_address_manifest.py` matches
  default `test*.py`; all **14** methods are named `test_*` on a
  `unittest.TestCase`. The sibling module is in the discovery start directory.
  Thus they are in existing hosted discovery scope by static inspection;
  neither discovery success nor test passage was executed or asserted here.

## External references

- [cryptography AESGCM API](https://cryptography.io/en/latest/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESGCM),
  accessed 2026-09-30: AES key sizes, 96-bit nonce recommendation, nonce reuse
  prohibition and authenticated associated-data failure behavior.
- [Python unittest discovery](https://docs.python.org/3/library/unittest.html#test-discovery),
  accessed 2026-09-30: default filename pattern and discovery/import model.

No general crypto redesign or additional campaign is requested. Re-review the
specific row representation and tests after correction; do not repeat already
established inbound acceptance or treat this source review as ten-address,
production capacity, outbound or release validation.
