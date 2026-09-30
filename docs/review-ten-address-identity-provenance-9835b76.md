# Review: single-account quota and Identity provenance slice (9835b76)

## Scope and verdict

Reviewed commit `9835b7602ea6a6a76363e520012a6682dce39583`: the two dormant
quota/manifest modules, their synthetic tests and design-document changes,
with surrounding recovery/prefix contracts and the existing native Identity
wrapper. No local tests, live requests, provider mutations or production fixes
were performed. The reviewed module files remain unchanged at review time.

**GO for hosted source checks, not for live dispatch.** No new substantive
executable defect was found in this increment. The contradictory design-document
requirement identified below was corrected by `58b0fe6`; that focused follow-up
was also reviewed.
This is not a quota, encryption, deployed provenance or recovery acceptance.

## Resolved P2: remaining design requirements reinstated the removed B/isolation gate

Location: `docs/staging-ten-address-hosted-acceptance-design.md:356-357` and
`:389-390` (at 9835b76).

The new introduction and execution/account table correctly require only the
already verified synthetic A account. `Evidence` removes the second owner and
prior-isolation run, and the new synthetic test explicitly checks their absence.
However, the same design's required acceptance-contract list still says that a
same-subject B and absent/failed prior isolation provenance must fail, and its
implementation sequence still says to wait for B verification and the smaller
isolation run before implementing the wrapper. Following those instructions
would put the orthogonal B capability blocker back on the quota critical path,
or lead a future adapter to add a gate that the reviewed controller deliberately
removed.

Correction: require verified selected-owner identity/username/PKCE binding and
exact source/service provenance, with no second-owner or isolation prerequisite.
Normalize the old B labels in the manifest/sequence/recovery sections to
"selected owner" (lines 211, 220, 229, 275-282, 316, 334-335). Keep cross-owner
mail isolation explicitly separate and unclaimed by this campaign.

Confidence: high; demonstrated contradictory written requirements. Impact is
integration direction, not an exposed runtime security defect. Source-only CI
need not be held for this wording, but it should not survive into live wiring.

Resolution: `58b0fe6cefab4bb2ac2d97d921f0734ca69b00b0` replaces the stale
B operational labels with A, replaces prior-isolation prerequisites with hosted
source/native identity provenance, and explicitly keeps B/isolation separate.
Focused static review found the contradiction resolved without broadening live
authority. No open substantive finding remains in this reviewed increment.

## Positive contract checks

* Single-account quota/reserved-name evidence does not require SMTP, a second
  principal or prior mailbox-isolation acceptance. The returned success labels
  are quota/reservation/cleanup only; no isolation result is fabricated.
* `prepare` binds selected issuer/subject, immutable Mail version, checkout and
  the new Identity/Login revision IDs, verified username and fixed staging native
  client ID into the authenticated private manifest. `campaign` compares the
  opened provenance with current wrapper evidence before mutation.
* UUID and username shape checks are not mistaken for deployment verification:
  module documentation says observations must be independently obtained by a
  reviewed wrapper. There is no network adapter, command entry point or workflow
  dispatch capability in this slice. A future wrapper must actually read and pin
  the serving Identity/Login revisions and authenticate the native client.
* New tests cover missing/invalid provenance, old-schema/envelope rejection and
  individually valid but manifest-mismatched revisions/username before `add`.
  Their synthetic AEAD fixture does not establish real AES-GCM behavior, as the
  design explicitly acknowledges.
* v2 updates schema, envelope magic, authenticated associated-data version and
  cipher-key derivation together. Candidate HMAC namespace remains v1, preserving
  exact alias reconstruction for original run coordinates. Repository references
  show only these dormant controller/tests consume `build`; the preceding design
  documents no deployed v1 recovery artifacts. Rejecting v1 is therefore an
  intentional internal schema change, not breaking an established live recovery
  contract. If any prior artifact is later discovered, this assumption must be
  revisited before discarding its recovery decoder/key.
* Existing full-intent sealing/readback, complete baseline, global/provider
  capacity, selected-owner checks, exact supported deletion and bounded read-only
  retirement settlement remain in place. Cooperative interruption still enters
  cleanup; hard process termination still requires same-artifact recovery.
* Private fields remain in the sealed plan/in-memory evidence; dataclasses suppress
  repr and fixed module failure codes do not introduce raw username, alias,
  credential or provider-response logging.

## Required next evidence

With the documented correction applied, run the existing hosted source
suite at the reviewed source SHA, then separately review the missing live adapter,
real pinned encryption dependency, durable artifact orchestration, fresh native
PKCE/Identity revision readback and full Cloudflare/D1/R2 inventory. The quota
live path remains **NO-GO** until those contracts are implemented and verified.

