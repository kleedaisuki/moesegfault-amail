# One-shot private provider capture: live-readiness checklist

Date: 2026-10-01. Scope: the original Email Analytics unknown-error diagnostic,
not a new SMTP send, R2 PUT, B registration, deployment or acceptance result.

## Decision

**GO to request explicit root/operator approval for the bounded preparation and
one-shot procedure below. Live execution remains NOT AUTHORIZED.** The previously
identified source coverage gaps have actual hosted passing evidence. No new
substantive source defect was demonstrated by this readiness pass. Do not turn
that statement into a claim that a real local key lifecycle or real private
artifact download has already happened.

No local tests/builds, real key generation, dispatch, provider query, private
artifact download/decryption, variable writes or cleanup mutations occurred.
Inspection used source, authenticated GitHub public run/job/variable metadata,
and **only the secret-free synthetic workflow's logs**. The static query hash
was calculated by parsing its source literal, without importing/executing the
application or a test.

The design/implementation documents' original pending-evidence status is historical.
This record supplies newer hosted evidence; it does not silently authorize their
next live step. Existing independent reviews remain the source-review authority:
[capture security](review-private-provider-capture-security-70589cc.md) and
[operator lifecycle](review-private-provider-operator-lifecycle-5728707.md),
especially its `a948d42` follow-up.

## Verified hosted evidence

| Evidence | Exact binding and observed result | Scope |
| --- | --- | --- |
| Source CI [36774241992](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36774241992) | `b3587bfcacbe400ce617732d445e9611b3f77f41`; six successful jobs | Infra, CLI on Ubuntu/macOS/Windows, Rust Worker/Wasm, Astro site |
| Synthetic [36774249823](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36774249823) | Same SHA; attempt 1; actual Ubuntu and Windows logs: **27 tests each, OK, native crypto not skipped** | Native memory-key crypto/production Python pipe, confidentiality and operator fixtures |
| Current branch source CI [36775433360](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36775433360) | `7719d674a85eaee7df66a487368367ef4fff3c8d`; completed/success, same six successful jobs | Permits proposing a branch-tip SHA instead of incorrectly pinning the older branch SHA |
| Current branch synthetic [36775438131](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36775438131) | Same current SHA; completed/success, both OS jobs successful | Additional exact-tip evidence; 27-test detailed log review above was at `b3587bf` |

The capture/operator/crypto scripts, both private test modules, `ci.yml` and the
synthetic workflow have no diff between `b3587bf` and inspected `7719d67`.
Only unrelated documentation changed. The operator script's last modifying
commit is `a05d374004954a332fd47817627381b59a761e38`; positive fixture source
coverage was separately reviewed at `a948d42` / `6d78b89`.

Actual passing operator fixtures include real bounded provenance/download code
with substituted HTTP transport, bearer-free signed-host request, archive digest
and host rejection, exact DELETE/404 recovery, DELETE failure retaining the key
fixture, terminal-run/late-upload ordering, interruption receipt preservation,
and retained local envelope/classification validation with no network.
The retained-classification fixture substitutes both the native child and fixture
path locator. Native crypto is tested separately with an in-memory synthetic
private key. Windows raw ACL descriptors are exercised, not actual OS directory
permission changes. Do not call these an unmocked end-to-end operator lifecycle.

## GO/NO-GO matrix

| Gate | State at inspection | Required action before the single provider POST |
| --- | --- | --- |
| Independent capture and operator source review | GO for implemented source/fixtures; earlier findings resolved | Preserve reviewed boundary; re-review any behavioral change |
| Hosted crypto and operator fixture execution | GO; actual dual-platform execution above | Do not rerun unrelated builds merely to rediscover the same evidence |
| Manual workflow registration | `.github/workflows/ci.yml`, active workflow **369045879**; existing successful manual runs observed | Recheck active state; use this existing workflow, not a new unregistered file |
| Manual target guards | Exact branch, target, confirmation, reviewed full SHA, attempt 1; debug checks; 5-minute timeout | Freeze branch and independently read back SHA/key variables |
| Repository capture variables | Authenticated repository variable listing: `total_count=0`; neither capture variable exists | Keep unset until approval; this is currently fail-closed |
| Original run and historical window | Authenticated attempt/job/failed-step metadata verified; details below | Keep imported query/provenance validator unchanged |
| Provider and GitHub credentials | Capture step only: existing Analytics token and GitHub contents/actions read; no send/R2/routing/deploy credential | Do not add broader credentials or migrate existing Secrets |
| One-shot enforcement | Attempt guard prevents rerun, **not a second new dispatch** | Owner records exactly one run; clear both enabling variables after the sole job has consumed them |
| Local key and permissions | Source reviewed; no real session created or OS permission mutation tested here | Approved operator creates one ephemeral session and verifies current-user-only directory/file access before enabling capture |
| Artifact boundary | Exact encrypted hidden file; pinned upload; 1-day retention; no wildcard/compression/overwrite; success-only upload; always exact runner cleanup | Verify actual upload/runner cleanup outcome from fixed statuses only |
| Local lifetime | Helper rejects inspect/classify after 24 hours from key creation; no expiry daemon | Named operator owns an explicit UTC deadline, earlier than capture-plus-24h if key was created earlier |
| Remote/local recovery and disable | Mechanisms tested synthetically; operational execution outstanding | Follow procedure below; never claim CLEANED from mere retention expiry |
| Live authorization | **NO-GO / not granted** | Root/operator must explicitly approve bounded preparation and exactly one provider read |

## Exact historical identity and query

The authenticated original metadata is:

- Run `36751791789`, attempt `1`, failed/completed manual dispatch on
  `codex/amail-v0.1.0`, SHA `15b50a5d1102873a81ff6628d491966852c2b76c`.
- Workflow `.github/workflows/staging-worker-r2-capability.yml`.
- Unique job `One-shot Worker-created R2 GET/DELETE`; exact failed step
  `Probe Worker-created private R2 object` ran from
  `2026-09-30T17:30:05Z` to `2026-09-30T17:33:55Z`.
- `historical_window()` therefore returns exactly
  **`2026-09-30T17:28:05Z` through `2026-09-30T17:43:55Z`**
  (step start minus 2 minutes; step end plus 10 minutes).
- Query is the unchanged `staging_worker_r2_history_error.QUERY`, one
  `__typename` selection per dataset, each limit 1. SHA-256:
  `e81c959a4358353c68abb1714aad0c8d72ff482405c7c8d0b6218465ea7f661f`.

No caller-supplied query/window/original-run override is permitted. A historical
window derived from this source is not a current-time query. The original run
must remain within the validator's 31-day limit at actual execution.
Only HTTP status and nonempty `errors` survive projection; the `data` subtree,
headers and identifying request variables do not. Error prose itself remains
confidential and must never be printed, pasted into chat or ingested by a model.

## Exact approval plan (proposal, not executed commands)

Root approval should explicitly name: one local ephemeral session; reviewed
full source SHA; one fixed-query historical GraphQL POST; existing GitHub-only
artifact retrieval/retirement; offline fixed-category interpretation; deadline
cleanup owner; and fail-closed disabling after use. It must exclude mail sends,
R2 PUT, B registration, deployment, additional capture or raw provider disclosure.

1. **Freeze and bind source.** At inspection the dispatch branch points to
   `7719d674a85eaee7df66a487368367ef4fff3c8d`, with exact source CI above.
   Propose that full SHA, not `b3587bf`: the latter is no longer branch tip and
   would correctly fail the live SHA guard. If a new commit is pushed, settle
   its review/evidence before using it; do not rewind the branch for this probe.
   An active workflow entry is evidence of existing registration, not an excuse
   to weaken GitHub's documented dispatch constraints if dispatch is rejected.
2. **After separate preparation approval only**, use
   `python infra/tests/private_provider_operator.py keygen <lowercase-session>`.
   Validate resolved root-local `.temp/private-provider-diag/<session>/`, no
   symlink/junction/reparse ancestors, Windows current-user-owned protected
   directory DACL and private-file inherited owner-only access (or Unix 0700/0600).
   Validate permissions on the actual operator machine. No private-file reads
   through assistant tools, backups, clipboard or uploads. An unexpected result
   stops before enabling variables or contacting Cloudflare.
3. Record the public session identity, full source SHA, fingerprint
   `SHA256(base64_decode(public.spki))`, and UTC cleanup deadline. Public SPKI is
   not secret; private PKCS#8 must remain local. Independently bind the public
   fingerprint before setting `PRIVATE_PROVIDER_CAPTURE_PUBLIC_KEY` and
   `PRIVATE_PROVIDER_CAPTURE_REVIEWED_SHA`. Read back only those public values.
4. **After explicit one-read approval**, dispatch once:

   ```powershell
   gh workflow run ci.yml --ref codex/amail-v0.1.0 `
     -f target=staging-private-provider-error-capture `
     -f confirm=CAPTURE_PRIVATE_WORKER_R2_ERROR_36751791789_ONCE
   ```

   Record the exact numeric run ID immediately. No automatic second dispatch if
   the CLI response is ambiguous: reconcile existing run metadata first. No
   rerun/attempt 2. Once the capture step has consumed the approved variables,
   remove **both** repository variables and verify their absence. Removing them
   too early may prevent the approved capture; do not compensate by recapturing.
   Their absence disables future provider reads through this target. Later
   source removal may eliminate the target entirely without disabling general CI.
5. Await terminal completion. Successful outcome permits
   `python infra/tests/private_provider_operator.py inspect <session> <run-id> <full-sha>`.
   This authenticates first-attempt source/job/artifact/digest and the stored
   public fingerprint, reads exactly one bounded ZIP member without extraction,
   decrypts privately, emits only a closed category, and verifies remote
   DELETE/404. Successful output is `LOCAL_RETAINED remote=CLEANED`, not full
   cleanup. Failure is not permission to print the plaintext or widen scope.
6. Optional `classify <session>` reuses the same local ciphertext with no
   Cloudflare/GitHub request. Unknown results may receive a newly reviewed
   bounded offline interpreter, never an arbitrary-output decoder. An operator-
   only unrecorded raw view requires separate explicit authorization; it is not
   part of this plan. If no safe actionable category emerges, record unresolved.
7. At conclusion or deadline, run `cleanup <session>` and require exact local
   path absence, remote artifact absence, and both enabling variables absent.
   Record only public coordinates, fixed outcomes and safe repair hypotheses.

## Failure recovery and hard deadline ownership

- Before inspection, preserve the captured run ID/SHA externally as public
  recovery coordinates. A key-only session may already have been dispatched;
  normal cleanup intentionally refuses uncertain remote state. For a known
  run, `inspect` persists run/SHA intent before its first API request; even a
  failed/cancelled terminal run can then be retired using `cleanup`. Do not
  invoke inspect repeatedly over an existing receipt; recover with cleanup.
- For an interrupted inspect, retry `cleanup`, not provider capture. Its
  receipt binds numeric artifact ID or exact run-scoped name. A queued/running
  run is not evidence of artifact absence: await terminal completion (or
  separately authorize cancellation) before normal retirement.
- If inspection/classification fails after upload, retain only encrypted
  evidence and its protected key until the explicit deadline. If the upload
  fails or no artifact is produced, stop; no second provider POST is authorized.
- A missing/corrupt/pending-only receipt or GitHub deletion/API outage fails
  closed. Do not alter receipt prose or declare deletion from an empty unauthenticated
  listing. Escalate promptly to the owner using only public run/SHA/artifact
  coordinates. The normal CLI retains the key while remote retirement is
  unresolved and does **not** automatically enforce the 24-hour deadline.
- Consequently approval must name the owner for a **deadline fallback**: if
  verified remote retirement is still impossible by the deadline, disable both
  capture variables, preserve public recovery coordinates outside the private
  session, and obtain explicit authorization for exact-path local key/ciphertext
  retirement despite unresolved remote cleanup. This is not a normal CLI success
  path and must remain `remote=UNVERIFIED`, followed by GitHub-only deletion
  recovery when available. Do not retain a key indefinitely, claim physical
  secure erasure, or call one-day artifact retention proof of deletion. The
  current approved design has no automatic emergency-retirement command.
- If preparation is cancelled **before any dispatch**, the owner must attest
  that no run was started before authorizing exact enumerated local retirement;
  `cleanup` intentionally cannot infer this from a missing receipt.

This explicit fallback/owner decision is a procedural prerequisite before live
authorization, not a reason to invent a new cryptographic defect.

## Smallest remaining synthetic evidence

There is **no pending rerun of the previously identified positive fixture gaps**:
those actually passed. The smallest *additional*, useful synthetic smoke would
exercise the shared native local-file permission/reading primitives on both OSes
under root `.temp`, using non-key fixture bytes and a real on-disk ACL/mode check;
validate unmocked session-path discovery and exact enumerated retirement. Existing
Windows tests inspect synthetic descriptors, not OS ACL application/inheritance.
This should avoid weakening production's CI keygen prohibition, avoid writing
real operator keys, and require no provider/GitHub artifact request or builds.

A full keygen/download/decrypt end-to-end synthetic redesign is not needed just
to re-establish already passing memory-key crypto and mocked-HTTP semantics.
The independent review treats the remaining actual-key permission verification,
fingerprint/SHA binding, one-shot coordinates, deadline and disabling as operator
prerequisites. If root chooses the additional filesystem smoke as a new gate,
it remains a hosted-only follow-up; none was run or dispatched here.

## Primary-source operational cross-checks

GitHub documents default-branch availability for manual triggering, branch
selection and the 25-input cap; this assessment reuses an authenticated active
workflow with existing manual execution history, not a speculative new workflow.
[Manual workflows](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).

Artifact APIs expose run binding and SHA-256 digest and require separate read
versus deletion authorization. Artifact access is not operator-only;
confidentiality depends on encryption. The capture job does not gain deletion
privileges. [Artifact API](https://docs.github.com/en/rest/actions/artifacts).

The reviewed pinned upload implementation supplies exact-file upload, hidden-path
opt-in and bounded retention; remote expiry is not immediate verified cleanup.
[Upload action](https://github.com/actions/upload-artifact).

## Bounded live outcome addendum — 2026-10-01

The root operator subsequently reports that the authorized single capture
[36776658592](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36776658592)
completed at exact source SHA
`7719d674a85eaee7df66a487368367ef4fff3c8d`. The only diagnostic category reported
is **`errors=unclassified`**. The root operator reports that the remote encrypted
artifact was deleted and its absence confirmed. These are owner-reported live
outcomes, separate from this readiness pass's directly inspected synthetic
evidence; this addendum did not download artifacts or independently inspect
private evidence.

The local protected key/ciphertext session remains retained pending an
independently reviewed **offline-only** bounded classifier and its existing
24-hour deadline. Remote artifact retirement is not full local cleanup. Do not
extend the deadline, authorize another provider read, expose raw error prose,
or infer delivery, B readiness or the original historical failure's cause from
`unclassified`. Final exact local retirement and disabling verification remain
operator-owned completion evidence.

No local session/key was accessed, and no provider call, local test or build was
performed when adding this outcome record. It contains only public run/source
coordinates and fixed status information, not provider text or local absolute
paths.
