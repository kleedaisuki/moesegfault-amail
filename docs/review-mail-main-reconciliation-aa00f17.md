# Independent review: narrow Mail/main reconciliation

Date: 2026-10-01. Verdict: **GO for the bounded source reconciliation** at
`aa00f17db297875f44863be64858952abdea8d61`, tree
`b0b92e4b18fa4b64216506f6edca3a2635442515`. This is not approval to merge the
complete Mail PR into main, deploy, publish v0.1.0, or enable sending.

## Scope and source identities

The two merge parents are the fixed Mail feature
`6cb7e091104d483b2720e77473dc2640adb0b117` and default main
`c08a1b6bb6a7181a62d12d6ddd3a46babd4826be`; their common ancestor is
`5c22160d96f5fb9c8fac7aabc5a4adfc4975a068`. Review used the isolated
`.temp/mail-main-reconciliation` worktree. No production files were modified
by this review, and no tests, builds, dependency installs, provider calls,
pushes, workflow dispatches or deployments were performed.

The reviewer inspected staged and committed diffs, parent identities, conflict
resolution inventory, candidate helpers, site workflows, and the existing Mail
CI/release site writers. The scope is integration preservation, not a new audit
of all 565 remaining Mail PR paths or newer primary-worktree changes.

## Independently established evidence

- Every path changed on main since the common ancestor, except `.gitignore`,
  has an identical Git blob in the reconciled index. The independent mismatch
  count was zero. The complete `site/` tree, both site workflows, candidate
  helpers/tests and existing main documentation compare identically to main.
- Relative to the fixed Mail parent, every changed path belongs to the main
  import allowlist or the new reconciliation note. The unexpected-change count
  was zero. Runtime, CLI, Identity, Skills, `ci.yml`, `release.yml` and
  `.gitignore` compare identically to the Mail parent. There are no deletions,
  unresolved conflict paths or whitespace errors in the bounded diff.
- Retaining the feature `.gitignore` preserves private environment, SQLite,
  Wrangler, dependency, build and experiment exclusions rather than replacing
  them with the standalone site's smaller ignore policy.
- Candidate deployment remains manual/main-only with exact confirmation and
  exact-SHA dedicated `site-ci.yml` evidence. Its same-commit reusable source
  call does not inherit provider secrets. Candidate code retains service-not-
  open copy, generated noindex/source headers, tag/public-Release exclusion,
  and three-route live smoke. Importing the reviewed main blobs does not
  convert Mail CI into candidate deploy evidence.
- Candidate, existing production CI and tagged published-site writers all
  retain `deploy-site-production` with cancellation disabled. Published builds
  explicitly select `AMAIL_RELEASE_STATE=published`; the imported service
  disclaimer is candidate-only. No changed helper caller was found outside
  the candidate workflow and its synthetic tests that would require Mail CI
  evidence under the former helper contract.

## Findings and limits

**No substantive defect was found in the narrow reconciliation.** This statement
does not establish hosted CI success for the new merge SHA, live Mail readiness,
or the correctness of unchanged release/runtime code. The prior public site
deployment remains pinned to `de2f150`, not this new merge.

The preserved standalone README/runbook still describe a checkout without Mail
code. The reconciliation note explicitly scopes those statements to the
historical standalone bootstrap. A later documentation-only alignment would
improve navigation, but this contextual wording is not a blocker to the assigned
exact-preservation merge and must not silently rewrite deployment evidence.

Newer quota/recovery work on the primary branch is not included in the first
parent. Root must integrate this ancestry with the current reviewed feature
head and obtain fresh hosted checks for that resulting SHA; this verdict does
not transfer to arbitrary subsequent resolutions. No production availability,
privacy gate, contact coverage, quota acceptance or Release claim changes.

The preserved site-only push allowlist is main plus the standalone bootstrap
branch, not the Mail feature branch. A Mail feature push runs its unchanged
full source CI but does not automatically produce dedicated site-only evidence.
PR checks or a separately authorized check-only site dispatch can check source;
candidate deployment still requires later exact-main site CI evidence. Do not
broaden the deployment gate's trusted branches to avoid this requirement.

## Reproduction (source inspection only)

```powershell
git show -s --format='%P' aa00f17
git rev-parse 'aa00f17^{tree}'
git diff --check 6cb7e09 aa00f17
git diff c08a1b6 aa00f17 -- site .github/workflows/site-ci.yml .github/workflows/site-candidate.yml
git diff 6cb7e09 aa00f17 -- crates workers skills .agents .github/workflows/ci.yml .github/workflows/release.yml .gitignore
```

For full allowlist verification, enumerate `git diff --name-only 5c22160 c08a1b6`,
exclude only `.gitignore`, and compare each parent blob against the merge blob.
Then ensure `git diff --name-only 6cb7e09 aa00f17` contains only those imports and
`docs/main-mail-reconciliation-2026-10-01.md`.

## Supplemental review: current feature integration at 6000faa

Root requested preservation review of the subsequent merge
`6000faa7bf8ef20280a991f3133af295028a12f8`, tree
`6dcf323870ebada66e28cff4c6c7e71bf0b02f65`. Its parents are the reviewed
reconciliation plus review artifact `95b02ccbcdb50368f276e6245478cc50c5fc34d5`
and latest reviewed feature `b373c35ad3eeb6b548f83d5d7f3a02d81e82c767`.

**Verdict: GO for this bounded integration; no substantive integration defect
found.** Independent source inspection established all of the following:

- All six paths changed between the old feature `6cb7e09` and latest feature
  `b373c35` have exact latest-feature blobs in the resulting merge. These
  include both quota acceptance implementation/regression files, architecture,
  escrow contract, independent recovery review and release-gap audit. The
  newer final authenticated ciphertext/terminal-readback correction is not lost.
- Every main import except `.gitignore` remains byte-identical to `c08a1b6`.
  Main's candidate site/workflows/helpers and live evidence are unchanged.
- The latest-feature-to-merge diff contains only the previously reviewed main
  import allowlist and the reconciliation/review documents. Independent counts:
  main blob mismatches **0**, newer-feature blob mismatches **0**, unexpected
  latest-feature changes **0**. The first-parent diff contains exactly six
  incoming paths plus the 42-line integration note; no quota hand resolution or
  unknown deletion is present. Both main and latest feature are ancestors.
- The worktree is clean and `git diff --check 95b02cc 6000faa` passes.

The existing independent quota review closes the dormant-source terminal
readback finding while keeping live acceptance NO-GO. This preservation review
does not repeat or enlarge that algorithm review, turn inspected tests into
executed results, or establish D1/provider/Agent-intake readiness. No local
tests/builds, provider operations, pushes or deployment were performed. Fresh
hosted checks must target the resulting source SHA after root-authorized push;
the dedicated site CI branch and exact-main deployment limitations above still
apply. The large Mail PR and public-send holds remain outside this GO.
