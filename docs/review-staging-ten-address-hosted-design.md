# Independent review: B-only hosted ten-address acceptance design

Scope: design commit `0df935b`, corrections `6a6a5af` and `64cfc6d`; static source and
official platform-documentation review only, 2026-09-30. No local test/build,
workflow dispatch, account, SMTP, address, provider-rule or production mutation
was performed. This review does not authorize a live campaign.

## Initial finding: global capacity masks the owner-quota oracle

**P1 in the initial design, resolved by `6a6a5af`.** The original provider
capacity gate is not sufficient for the exact eleventh-address assertion.
`crates/mail-worker/src/lib.rs::add_address` counts all rows with
`state!='retired'` and returns `409/capacity_exhausted` at
`USER_ADDRESS_CAPACITY=198` **before** the owner-scoped ten-slot insertion.
Pending/provisioning/deleting rows need not have a corresponding provider
rule. Thus a complete inventory with 188 rules does not establish sufficient
application capacity; even a D1 baseline of 188 reaches 198 after ten adds,
and the eleventh request cannot reach `409/address_limit`.

Require the full global non-retired D1 baseline to be at most **187**, preserve
its count and unrelated-state commitment in the sealed manifest, and verify
before the eleventh call that it remains exactly `baseline+10 <=197`. Drift
must stop the quota claim and enter same-manifest reconciliation, not broaden
the accepted negative codes. Hosted synthetic tests need the provider-safe
but D1-full counterexample and the boundary 187/188 cases.

## Required implementation contracts clarified during review

1. **Resource identity and syntax.** The Worker local-part maximum is 32
   bytes. A 128-bit hexadecimal nonce produces a 37-byte `qt10-<nonce>` and
   fails the name oracle instead of quota. Specify a lowercase unpadded
   26-character RFC 4648 base32 encoding of 16 HMAC-derived bytes; the longest
   candidate is then 31 bytes. Keep ordered raw submissions, including case
   variants, separate from the unique normalized resource-baseline map.
   Uppercase and lowercase submissions intentionally address one resource;
   rejecting duplicated canonical baseline keys must not reject that test.
2. **Complete pre-delete observation.** `delete_address` enumerates every
   exact matching provider rule and may also delete the saved D1 rule ID.
   Before invoking it, recovery must observe the complete matching set as
   either empty or exactly the expected enabled API-owned staging ingress
   rule bound by the owned D1 row. A good rule plus an additional foreign,
   disabled or action-mismatched rule is not safe. Preserve any preexisting
   role route or row; an unexpected reserved-name side effect against such a
   baseline requires explicit reconciliation, never ordinary CLI deletion.
3. **Durable artifact is a checked state, not a successful-looking step.**
   The ciphertext lives under repository `.temp`, a hidden directory.
   `upload-artifact` excludes hidden content by default and missing paths
   only warn by default. Use the exact reviewed ciphertext path, never a
   `.temp` wildcard, explicitly include hidden content, fail on missing files,
   prohibit overwrite, require an artifact ID, then download/authenticate and
   compare with the frozen manifest before permitting any `address add`.
   Exclude CLI homes, browser profiles and plaintext from artifacts.
4. **Recovery lifetime.** Specify an artifact retention period, recovery
   deadline and protected key-generation identifier. Do not delete the
   artifact/run or rotate the key while cleanup is unresolved. A deadline is
   an escalation point, not permission to discard the baseline or retry the
   campaign. If extending retention, preserve the original authenticated
   bytes and run binding rather than regenerating a guessed baseline.

These are concrete contracts for the future wrapper, not requests to add
provider writes, extra test principals or a general-purpose journal service.
The narrow recheck confirms that `6a6a5af` and `64cfc6d` explicitly incorporate
all four contracts, including 30-day ciphertext retention, a 24-hour recovery
escalation boundary, and preservation of unresolved baselines before expiry.

## Sound parts of the chosen design

The B-only, zero-SMTP slice separates a serial quota boundary from the prior
two-principal authorization relation. Fresh normal B PKCE plus restricted
Identity subject/contact binding avoids mistaking two local homes for two
accounts. The full pre-mutation candidate plan covers an unexpectedly
successful reserved or eleventh call even when the process dies before an
acknowledgment. Exact typed HTTP status/code and unchanged D1/provider
snapshots distinguish a true rejection from an unrelated transport failure
or rejection with side effects.

Complete bounded provider pagination, duplicate-ID/count checks, counting
disabled rules, and conservative admission with two spare provider slots are
appropriate. The total-zone <=188 condition is intentionally stricter than
the documented per-domain limit, not a claim that Cloudflare documents a
shared 200-rule zone ceiling. Admission is not reservation; foreign mutation,
Cron drift or a deployment change must fail closed. The future deployment
jobs must actually share the relevant repository concurrency exclusion;
different group names do not serialize them. Sibling-repository/manual
deployments remain outside that lock and need explicit coordination and
pin readback.

Accepting owned retired tombstones, zero live slots and completed route
reconciliation is the correct final-state model. Pretending retirement
restores database absence would hide established product semantics. The
campaign must not claim concurrent quota-race coverage, public-send safety,
production capacity or release readiness.

## Evidence and references

- `crates/mail-worker/src/lib.rs`: `local_part`, `add_address`,
  `delete_address`, global `USER_ADDRESS_CAPACITY` and retirement behavior.
- `infra/tests/staging_mail_e2e.py`: `cf_rules`, `validated_rule_page`,
  `assert_route`; complete inventories are already bounded and count-checked.
- `infra/tests/staging_address_isolation_e2e.py`: explicit 25-name oracle;
  existing combined campaign retains mutation intent only in process memory.
- [Cloudflare Email Service limits](https://developers.cloudflare.com/email-service/platform/limits/),
  accessed 2026-09-30: 200 inbound routing rules per domain. Destination-address
  account limits are distinct from routing-rule capacity.
- [GitHub Actions concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency):
  serialization applies to the same concurrency group in one repository;
  `cancel-in-progress:false` does not eliminate manual cancellation.
- [Official upload-artifact instructions](https://github.com/actions/upload-artifact):
  hidden-file defaults, missing-file policy, immutable artifacts, artifact
  outputs and retention. Pin/review the chosen action and crypto dependency
  in the implementation rather than copying an unpinned current example.

## Verdict and next gate

**Corrected design through `64cfc6d`: GO for implementing the dormant wrapper
and hosted synthetic/recovery tests.** The missing global D1 headroom gate
and concrete resource/artifact/delete contracts are now resolved in the
design; no further design-level blocker was found in the changed scope.
The initial `0df935b` was NO-GO as written. **Live dispatch remains NO-GO independently**:
B verification, the smaller two-principal isolation run, source-reviewed
wrapper/recovery implementation, hosted synthetic CI and deployed serving-pin
evidence are required. Implementation review must check the actual workflow
step boundaries, exact manifest upload/download, pinned crypto library and
dependencies, full current provider-set checks and source-owned failure
labels. A preflight native login necessarily possesses an address-capable
token: the artifact gate must forbid mutator invocation before durable
readback, not falsely claim that no capable token exists during authenticated
preflight. Do not repeat already completed inbound fixtures merely to obtain
the prerequisite record.
