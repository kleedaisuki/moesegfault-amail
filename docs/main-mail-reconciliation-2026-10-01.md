# Main candidate site / Mail source reconciliation

Date: 2026-10-01. Status: local merge preparation only; independent review and
root push approval are required. Nothing here approves PR #1, production Mail,
public sending, a release/tag, or a new site deployment.

## Fixed source and authority

| Identity | Exact value |
| --- | --- |
| Remote main, freshly fetched | `c08a1b6bb6a7181a62d12d6ddd3a46babd4826be` |
| Remote Mail feature, read with ls-remote | `6cb7e091104d483b2720e77473dc2640adb0b117` |
| Common ancestor | `5c22160d96f5fb9c8fac7aabc5a4adfc4975a068` |
| Isolated local branch | `codex/mail-main-reconciliation` |
| Isolated worktree | `.temp/mail-main-reconciliation` |

The resolved absolute worktree target was verified strictly under the repository
`.temp` before creation. It was created from the exact feature SHA, not the
shared primary checkout. That checkout already had unrelated local edits;
none were changed, staged, or committed here. A main fetch updates a remote
tracking reference, not a shared local main or feature branch.

The deployed candidate's recorded source is **de2f150**, not c08a1b6: the latter
adds deployment/evidence documentation, not a new deployed site revision.
Preserving the c08a1b6 source tree therefore preserves deployed candidate source
and the later historical evidence, without claiming a deployment at a new SHA.

## Conflict inventory before resolution

Main changed 43 paths since the common ancestor; 38 are also added or changed
on the feature, and five exist only on main. Most shared additions are already
byte-identical. A no-commit, no-fast-forward merge with rerere disabled reported
exactly **15 add/add conflicts**, with no runtime, CLI, Identity, migration,
provider configuration, send gate, or release workflow conflict.

| Conflicting path | Resolution |
| --- | --- |
| `.github/workflows/site-candidate.yml` | Exact main blob |
| `.gitignore` | Exact feature blob; retain credential and build exclusions |
| `docs/site-production-candidate-lane.md` | Exact main blob including deployed evidence |
| `infra/release/candidate_site.py` | Exact main blob |
| `infra/release/check_candidate_site_gate.py` | Exact main blob |
| `infra/release/test_candidate_site.py` | Exact main blob |
| `infra/release/test_candidate_site_gate.py` | Exact main blob |
| `site/README.md` | Exact main blob |
| `site/scripts/check-release-state.mjs` | Exact main blob |
| `site/scripts/check-release-state.test.mjs` | Exact main blob |
| `site/src/layouts/ManualLayout.astro` | Exact main blob |
| `site/src/pages/changelog.astro` | Exact main blob |
| `site/src/pages/index.astro` | Exact main blob |
| `site/src/pages/manual.md` | Exact main blob |
| `site/src/releaseState.ts` | Exact main blob |

Five main-only additions are carried unchanged: `site-ci.yml`, the two independent
standalone review documents, `docs/site-standalone-bootstrap.md`, and
`infra/release/test_candidate_site_workflow.py`. All of `site/` and all four
main-tracked documents are preserved byte-for-byte. The shared staging R2
workflow has identical blobs on both parents and requires no resolution.

The root `.gitignore` deliberately retains the more complete feature policy;
using standalone main's four-line policy would discard established `.env`,
`.dev.vars`, database, Rust target, Wrangler, dependency and build exclusions.
No broad ours/theirs merge strategy is used. File ownership determines explicit
blob selection. Relative to the feature, reconciliation imports 19 main changes
and adds this one integration note; all other feature paths remain unchanged.

## Contracts after the prepared merge

- Candidate deployment remains main-only and manual-only, with the exact
  confirmation, same-commit reusable source workflow, fresh exact-SHA
  **site-ci.yml** evidence, two public-tag/published-Release exclusion gates,
  generated-only source/noindex headers, service disclaimer, and live-route smoke.
- The site CI gate still trusts only main and the standalone bootstrap branch.
  Do not substitute feature-branch Mail CI or a PR run for candidate deploy
  evidence. PR source checks may validate the reconciled tree, but later main
  deployment still requires its own exact main SHA push/dispatch evidence.
- Feature `ci.yml` and `release.yml`, their manual targets/inputs, runtime/CLI/
  Identity code, Skills, quotas, recovery, public-send policy and release gates
  stay byte-identical to the fixed feature source. Existing published site writers
  already use `deploy-site-production` with cancellation disabled; do not weaken
  them to make the candidate lane pass.
- No push, PR edit, hosted dispatch, deployment, DNS/provider mutation, release/
  tag, or local dependency installation/test/build is performed here.

### Preserved standalone documentation has a bounded contextual limitation

`site/README.md` and the standalone lane runbook say the bootstrap checkout has
no CLI/backend, Mail CI, or published deployment lane. Those statements describe
the **standalone bootstrap boundary**, not the integrated repository after this
merge. The files are deliberately preserved exactly under the assigned source
preservation constraint. This integration note supplies the current context:
the reconciled feature checkout contains the existing Mail/Identity/CLI and
gated release workflows, but their presence is not acceptance or public launch.
The statement "do not add Mail ci.yml" remains a prohibition on using Mail CI
to bypass the candidate registration/evidence boundary, not a prohibition on
this separately reviewed source integration.

A future root-authorized documentation alignment should update checkout-level
phrasing and navigation without changing historical deployment evidence,
candidate content, workflow inputs, source-gate identity, or public-send holds.
No such cleanup is silently folded into this exact-preservation merge.

## PR #1 review scope and a safer integration strategy

At the fixed remote SHAs, `git diff --name-only main...feature` contains **601
files**. It compares against the old common ancestor, so it includes older site
additions now already on main. Removing merge conflicts does not review that
Mail source, prove integration correctness, or authorize merging the whole PR.

A stacked review strategy is safer if root does not already have complete,
traceable approval of all contracts: first land a non-deploying source foundation
(types/schema, CLI/Identity/Mail contracts and focused tests); then layer
staging/acceptance/recovery tooling; finally review public release/production
workflow registration and operational controls. Use cohesive dependent stacks,
not arbitrary directory slices: schemas, runtime bindings, recovery envelopes,
workflow inputs and tests may need to move together. Determine those boundaries
from the actual dependency graph before creating replacement PRs.

Do not reset, rebase, force-push, close PR #1, or remove operational protections
merely to shrink its displayed diff. A narrow reconciliation merge is useful
now because it preserves ancestry and published candidate ownership, while
stack decomposition remains a separate root/product review decision.

## Static evidence and reproducible checks

Only Git source/diff/status inspection is used for the prepared merge:

```powershell
git ls-remote origin refs/heads/main refs/heads/codex/amail-v0.1.0
git merge-base 6cb7e09 c08a1b6
git diff --name-only 5c22160 c08a1b6
git merge-tree 5c22160 6cb7e09 c08a1b6
git -c rerere.enabled=false merge --no-commit --no-ff c08a1b6
git diff --name-only --diff-filter=U
git diff --cached --check
# The complete explicit path list is documented above; no wildcard outside it.
git diff --cached c08a1b6 -- site .github/workflows/site-ci.yml .github/workflows/site-candidate.yml
git diff --cached 6cb7e09 -- crates workers skills .github/workflows/ci.yml .github/workflows/release.yml .gitignore
```

For independent review, compare every main-changed path except `.gitignore`
against main and every feature path outside that allowlist against the feature.
Both comparisons must be empty, apart from this integration note. `git diff
--cached --check` must pass and the unresolved-path list must be empty.

Hosted validation is deferred until root reviews/approves the exact merged SHA.
Prior de2f150 candidate evidence remains historical and does not transfer to
this merge. After any future default-main integration, obtain fresh successful
site-ci.yml evidence for that main SHA before a separately approved candidate
deployment. Full Mail/CLI hosted evidence and independent review remain separate.

## External contract references

Official sources rechecked on 2026-10-01:

- [Git merge](https://git-scm.com/docs/git-merge): a no-commit true merge allows
  path review before committing; explicit parent ancestry prevents repeated
  reconciliation of the same main changes.
- [GitHub reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows): repository-relative calls use the caller's
  same commit, preserving site source identity without inherited provider secrets.
- [GitHub pull requests](https://docs.github.com/en/pull-requests/reference/pull-requests): PRs are review/integration proposals, not release or deployment
  approval. Smaller cohesive proposals improve review focus, but require explicit
  dependency and operational-boundary design.

The controlling uncertainty is source ownership and integration evidence, not
an unresolved research algorithm. Production-proven Git ancestry and explicit
workflow contracts directly resolve it; unrelated academic machinery would not
establish readiness of the remaining 601-file Mail proposal.
