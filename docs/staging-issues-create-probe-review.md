# Independent static review: code-free Issues create discriminator

Date: 2026-10-01. Base: `a4fc6160ca6b771da6351268d1a96af4c4a616dc`.

## Decision and scope

**GO for source integration; no material source-level defect found in the final
minimal recovery revision. NOT authorization to dispatch or create a Worker.**
Hosted synthetic checks, integration provenance, independent approval pin,
protected staging approval, actual external writer freeze and explicit operation
authorization remain required. This review is not a passing-test claim or an
attestation of original Mail privacy.

Reviewed the helper, authored synthetic tests, manual workflow and operator
document, plus the reused serving-deployment, frozen containment-binding and
capture-disabled contracts. No project tests/builds, provider requests,
Cloudflare mutation, workflow dispatch, push, or Worker creation were performed.
Only public documentation was retrieved; implementation files were not edited.

Final reviewed file SHA-256 fingerprints:

| File | SHA-256 |
| --- | --- |
| `infra/provider/staging_issues_create_probe.py` | `3A5659A3C1F7C28EAA49B945C73AD586CDD2DBACDA2B3054D16891024A8C7D85` |
| `infra/tests/test_staging_issues_create_probe.py` | `9FAA0708C61D947835D5797FD964D94057BBBAC1329DD27E1E9401B2011F57C0` |
| `.github/workflows/staging-issues-create-probe.yml` | `E14C5CA2CDA8C6DEE62EE43E43651A1DD611551675B9B92D267A49A0C7E89293` |
| `docs/staging-issues-create-probe.md` | `83A8A251E11E73C040E9938F0A1794609D02315B9DA7FCD6241802419C36E0AD` |

## Evidence-backed contract assessment

| Contract | Static evidence and assessment |
| --- | --- |
| Failure-closed absence | `name_absent` requires typed, mathematically complete metadata, stable totals, unique IDs/names and no more than five 100-item pages. Failed requests, arbitrary 404, partial inventories and schema omissions cannot authorize POST. Presence stops without adoption. |
| One-shot identity | `probe` calls create once, accepts only the fixed name and a bounded typed ID, persists that ID before readback, then independently GETs by that ID. Create observability is not used as current-state evidence. No replay, alternate name, polling or automatic cleanup exists. |
| Zero-business-data scope | The fixed six-field body contains no code, version, binding, route, domain, trigger, Mail fixture or copied original configuration. Readback requires disabled URL flags, empty references and no deployment; a separate versions query requires complete zero-total evidence. No executable/public endpoint is invoked. |
| Classification | Raw Issues omission remains distinct from false and true. Malformed or unknown capture configuration fails closed. Temporary Issues normalization is only a validator input, never persisted or presented as provider evidence. |
| Original and hold | Completed results require the same original single-100 c3f deployment, frozen bindings/version/current Worker snapshot before and after, and held/idle aggregate D1 checks. The SQL is SELECT-only despite using a POST query endpoint. |
| Manual pre-secret guard | A credential-free guard/test job precedes the protected staging job. Main/repository/reviewed SHA/independent approval SHA/first-attempt/confirmation/freeze/debug checks are repeated after environment approval and inside the operation entrypoint. Secrets occur only in the operation step. |
| Bounded safe output | Transport rejects redirects, bounds response reads and suppresses arbitrary exceptions. Normal output is closed categorical labels, not provider bodies, tokens, account IDs, URLs or unexpected resource coordinates. |
| Minimal recovery | RSA/AES, key provisioning and intent encryption are absent. Only exact validated ID plus fixed name/run/attempt/SHA/UTC/workflow/repository enter `resource.json`; no raw objects or account ID. Exclusive creation and root-local symlink/junction checks protect the artifact destination. The workflow uploads only this exact file, including after failure. |
| Retirement | There is no DELETE path. The documented later protocol requires exact artifact provenance, fresh identity/isolation/no-code checks, separate approval, non-forced exact-ID deletion and positive retirement evidence. Missing ID never permits name-based ownership inference or automatic adoption/deletion. |

## Material assumptions and limits

Final late-hunk audit: unrelated inventory names now require only bounded,
nonempty strings rather than an invented lowercase/dash grammar. Exact equality
with the fixed probe name, uniqueness, typed IDs and complete pagination remain
unchanged; unrelated names are never used in request paths or output. This
relaxation removes an unnecessary compatibility rejection without broadening
creation targeting. The added hold aggregate test inspects the exact SELECT
request and rejects zero/multiple rows represented by counts, active-canary
counts, Boolean/string/null counts. These source/test edits introduce no material
issue. The source-integration GO decision is reaffirmed for the fingerprints
above; tests were not executed.

Final artifact-upload correction also reviewed: `include-hidden-files: true`
is necessary because the exact recovery file is beneath `.temp`; otherwise the
action's default hidden-file exclusion can silently omit it. `overwrite: false`
preserves an existing same-name artifact rather than replacing its identity.
The path remains a single literal filename, not a directory/glob, so enabling
hidden-file inclusion does not expand the uploaded data boundary. Added tests
assert this exact path and both inputs; docs describe the official contract.
This resolves a concrete recovery-upload defect in the earlier workflow and
does not change provider behavior. GO is reaffirmed for the final fingerprints.

- Pagination is not a transactional snapshot. The real external writer freeze
  is necessary; stable totals do not prove no same-count replacement. GitHub
  concurrency excludes cooperating jobs, not dashboards or other API clients.
- First-attempt dispatch guarding is not an account-wide once-ever ledger.
  Operators must not dispatch again after an attempted POST, including an
  ambiguous outcome, and must retire the approval pin under the stated protocol.
- Exceptions before completed classification can skip the after bracket. The
  primary result remains UNVERIFIED and phase bins do not claim a complete
  bracket. The final document now explicitly requires retaining the freeze and
  independently resolving original/hold state. This is not a success-path defect.
- Artifact publication failure, runner interruption or missing POST identity
  can leave recovery unresolved. No compensating create/delete is allowed.
  Resource coordinates are deliberately non-secret; artifact authentication is
  not treated as confidentiality.
- Strict optional-schema rejection can stop a valid provider operation. This is
  intentional fail-closed behavior, not proof that current provider responses
  will satisfy the authored fixtures. Hosted checks and authorized observation
  are still outstanding.
- The design-document integration dependency is resolved in the final tree;
  see the integration audit below.

## Final-tree integration audit

Reviewed the full base-to-working-tree changed-file inventory: seven files,
limited to this helper, its tests/workflow, runbook/review, design document and
omission-semantics supplement. Re-read the integrated design and the three
documentation reconciliation hunks. The design retains its historical inspection
snapshot but now explicitly makes the implementation runbook authoritative for
bounded inventory absence, minimal non-secret recovery and incomplete failure
brackets. Conditional deployment/cutover slices remain unimplemented and
unauthorized. The supplement accurately says implemented, not executed or
authorized. No documentation update expands the executable operation scope.

Independently confirmed with local Git inspection:

- `b9fdbeae53d31316204ca20b718b6420e119e2df` contains only the design document
  and omission-semantics supplement, cherry-picked from the design change.
- `git merge-base --is-ancestor a4fc616 HEAD` returned 0.
- `git merge-base --is-ancestor 2ff67e HEAD` returned 1: the older primary
  inspection snapshot was not imported as ancestry.
- A static Markdown-link existence scan across the four changed documents
  found all relative file destinations present. This checks file existence,
  not remote availability or Markdown fragment anchors.
- Recomputed helper/test/workflow fingerprints are unchanged from the final
  executable review above. The updated runbook fingerprint is recorded above.

The missing design dependency is therefore resolved, and source integration GO
is reaffirmed for this final tree. Final documentation commit/provenance is an
integration step, not provider authorization. No tests/builds or provider
requests were executed during this audit.

The authored tests cover the principal positive/negative branches, including
independent readback rather than creation acknowledgement, incomplete pagination,
no replay on timeout, exact-ID recovery before readback failure, bracket drift,
malformed raw JSON and manual workflow sequencing. They were inspected, not run.

## External contract verification

Retrieved authoritative Cloudflare references on the review date:

- [List Workers](https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/methods/list/): documented name ordering, page/per-page bounds and pagination metadata support the bounded inventory gate, not exact-name filtering or atomic snapshots.
- [Create Worker](https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/methods/create/): checked the writable configuration projection and successful response envelope.
- [List Worker Versions](https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/subresources/versions/methods/list/): supports addressing by Worker ID and the independent uploaded-code inventory query; optional metadata is required by this probe for positive empty evidence.
- [Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/): bounded I/O and secret handling are relevant; generic advice to enable runtime observability is not appropriate to this explicit code-free capture discriminator.
- [Official upload-artifact inputs and hidden-file contract](https://github.com/actions/upload-artifact#inputs): hidden files include files under dot-prefixed directories; explicit inclusion is required here, and overwrite disabled prevents replacement of an existing artifact.

No unrelated academic redesign or speculative finding was introduced into this
narrow operational review. The actionable next step is hosted source validation
and immutable integration, not expanding the experiment or weakening its gates.
