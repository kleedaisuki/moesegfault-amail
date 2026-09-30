# Candidate site / main split decision — 2026-10-01

## Decision and authority

**STOP the minimal backport; no implementation PR or remote push is made.**
The current default-branch substrate cannot run the reviewed candidate lane.
This is a source-integration blocker, not a Mail acceptance result or a reason
to loosen the send hold. Root coordination explicitly agreed not to force a
partial backport or publish a PR from this investigation.

The bounded fallback is either a later, comprehensively reviewed development
branch merge, or a separately authorized **standalone site bootstrap**. The
latter is a new integration change requiring its own review, not the original
nine-file candidate feature applied unchanged. Neither option is executed here.

## Reproducible source evidence

The remote `main` was freshly fetched from
`https://github.com/kleedaisuki/moesegfault-amail.git` on 2026-10-01. Its SHA is
`7baea1adc0da08259a1f03f7307e989ec3bf8250`; its complete tracked tree is:

```text
.github/workflows/staging-worker-r2-capability.yml
LICENSE
```

There is no `site/`, `infra/release/`, or `.github/workflows/ci.yml` on main.
The existing staging workflow is not an Astro CI source and is not changed.

Reviewed feature sources:

- `496f75826f74417081a8558b8018aadd329c9168`: candidate lane addition.
- `e35b7439e45f10eabc86de13f7c72a75a940ab6c`: publication-boundary correction.
- Existing scoped review on the development branch:
  `docs/review-site-production-candidate-496f758.md`.
- Existing operator contract on the development branch:
  `docs/site-production-candidate-lane.md`.

Commands used to establish the tree and dependency floor (Git inspection only):

```powershell
git fetch origin main
git rev-parse origin/main
git ls-tree -r --name-only origin/main
git show --stat 496f758
git show --stat e35b743
git ls-tree -r --name-only e35b743 -- site infra/release
git show e35b743:infra/release/check_candidate_site_gate.py
git show e35b743:.github/workflows/site-candidate.yml
```

An isolated worktree was created at the repository-relative path
`.temp/candidate-site-split`, on local branch
`codex/candidate-site-split-plan`, from the fetched main SHA. The resolved
absolute target was checked to lie strictly under the repository `.temp`
before creation. No worktree move/removal occurred. Its only added artifact is
this document. The shared primary worktree and branch were not edited.

## Dependency graph and why a cherry-pick is insufficient

```text
site-candidate.yml
  source checks
    -> complete Astro site + lockfile + assets + release-state checks
    -> candidate_site.py + both synthetic candidate test modules
    -> clean candidate build and clean published-header isolation build
  manual deploy (main only)
    -> exact-SHA successful ci.yml run
       -> exactly one successful "Astro release site" job
    -> public v0.1.0 tag / published Release read-only gates (twice)
    -> independent review + operator site/tag/publication freeze
    -> generated production noindex and source-SHA headers
    -> existing site Wrangler configuration / Custom Domain
    -> exact home/manual/changelog live smoke and both route-local TOCs
```

`check_candidate_site_gate.py` hardcodes
`actions/workflows/ci.yml`, and its run/job checks require successful source
evidence for the exact deployment `GITHUB_SHA`, on main or the trusted
development branch, with the named Astro job actually successful rather than
skipped. Main has no such workflow or site job. A green candidate workflow alone
does not meet the reviewed contract. Registering only the candidate YAML would
not produce a valid deployable lane.

The reviewed feature modifies existing site files; main lacks those files.
Copying the complete site is therefore a bootstrap, not a minimal backport.
The site itself is static and does not require Mail runtime code, but its
README/manual refer to the CLI, Skill and architecture contracts outside main.
Those references and any available-feature language would need an explicit
content audit before standalone publication.

### Exact standalone dependency floor (not authorized or implemented)

The following allowlist contains **36 files / 7,919 inserted lines** relative
to the fetched main, all measured from `e35b743` with `git diff --numstat`.
It excludes all Mail and Identity implementation. The 30-file site directory
includes 3,828 lockfile lines and 1,509 vendored CSS lines; raw line count alone
does not imply equivalent logic risk, but does establish that the nine-file
feature is not the entire integration surface.

| Paths | Files | Purpose |
| --- | ---: | --- |
| `site/**` as tracked at `e35b743` | 30 | Full three-page Astro site, release-state code/checks, dependency lock, styles/vendor provenance, static headers and site-only Wrangler configuration |
| `.github/workflows/site-candidate.yml` | 1 | Candidate checks and main-only guarded manual site deployment |
| `infra/release/candidate_site.py` | 1 | Generated-only headers and route-local live smoke |
| `infra/release/check_candidate_site_gate.py` | 1 | Exact source CI identity and public publication state |
| `infra/release/test_candidate_site.py` | 1 | Synthetic header/smoke contracts |
| `infra/release/test_candidate_site_gate.py` | 1 | Synthetic source/publication gates |
| `docs/site-production-candidate-lane.md` | 1 | Deployment contract and operator obligations |

This floor is **still incomplete**: source-CI registration must be supplied.
Importing the development branch's entire `ci.yml` would drag in CLI/Worker,
provider, Queue/D1, and deployment dependencies, violating the intended focused
split. A deliberately new, site-only `ci.yml` with the exact successful job
contract could avoid those dependencies, but then needs independent integration
review, hosted exact-SHA evidence, and a plan for reconciling future full-branch
CI without losing external workflow/input contracts. It cannot be represented
as unchanged already-reviewed behavior.

Explicit exclusions for any future standalone proposal: `crates/**`,
`workers/**`, Identity clients/configuration, all other `infra/**` except the
four allowlisted candidate helpers/tests, Mail/send gates, migrations, routing,
Queue/D1/R2 provisioning, existing staging workflow modifications, tag/Release
workflows, and public-send policy/attestations. In particular, do not copy
`check_send_gate.py` or `verify_published_assets.py` just because they share the
`infra/release` directory.

## Safe continuation options

### Preferred when the complete source branch is ready

1. Independently review the development branch's complete merge scope. The
   narrow candidate-site review is not approval of every Mail/Identity change.
2. Merge reviewed source to default main only through the root-owned delivery
   decision. A source merge is not production acceptance; keep all operational
   holds and existing published-release gates unchanged.
3. Wait for candidate workflow registration and hosted checks on the exact main
   SHA. Obtain a successful `ci.yml` run for that SHA with the Astro job passed.
   Branch evidence from a different SHA is insufficient after a merge commit.
4. Re-review the candidate deploy source if changed from the reviewed commits;
   freeze other site writers and v0.1.0 tag/publication operations externally.
5. Only on separate root/operator authorization, manually dispatch candidate
   deployment from main with the exact source-run ID and reviewed confirmation.
6. Accept only actual three-route HTTP/header/source/TOC smoke plus recorded
   public DNS/HTTPS and Worker-version evidence. Do not infer Mail readiness,
   download availability, or permission to unhold from a green site operation.

### If an earlier independent public candidate is required

Authorize a **new standalone-site bootstrap proposal** first, with the above
allowlist and site-only CI as its explicit scope. Require an audit of manual
links/current capability claims, future CI integration, and publication-mode
compatibility. Run tests/builds only in GitHub Actions. Do not open the PR until
its contract is intentionally agreed; no partial registration workaround is
useful now. The source import may be bounded in logical scope, but the necessary
new CI and documentation semantics make it larger than the current authorized
minimal backport.

## Preserved cutover invariants and material risks

| Invariant / risk | Required treatment |
| --- | --- |
| Manual workflow registration | GitHub requires the workflow on the default branch. Keep the separate main-only deploy guards in YAML and Python; never relax them for a development-branch dispatch. |
| Exact source identity | Require successful hosted source checks for the same full SHA; do not substitute the original development SHA after a different merge SHA. |
| Publication truth | Reject a public v0.1.0 tag or published Release. Read-only token visibility is not proof that internal untagged drafts are absent. |
| Concurrent publication / other writers | Shared `deploy-site-production` with no cancellation serializes cooperating site workflows, not independent Release creation or dashboard operations. An external operator freeze remains necessary. |
| Candidate indexing and promotion | Add production-host noindex/nofollow and exact revision only to generated `site/dist/_headers`; source headers remain staging-only. Fresh published output must restore byte-identical source headers. |
| No false download | Home, manual and changelog must each carry candidate state; reject actual version-specific tag/download links and published phrases. Future install instructions are not current release availability. |
| Three-route usability | Require exact `/`, `/manual/`, `/changelog/` 200 HTML without following redirects; manual/changelog TOCs must be nonempty and resolve locally. No homepage TOC is implied. |
| Provider mutation boundary | Existing site-only Worker/Custom Domain/assets only; no Mail Worker, send policy, route, migration, provisioning or placeholder DNS record. Initial Custom Domain deployment may itself provision DNS/certificates, so even that operation needs separate authorization. |
| Evidence / review limits | This investigation proves source absence and dependency constraints, not dependency-install success, live provider permissions, domain reachability, candidate deployment, or full-branch readiness. |

## External contract checks

Official documentation rechecked on 2026-10-01:

- [GitHub: manually running a workflow](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow): default-branch workflow presence is required for manual dispatch.
- [Cloudflare: Static Assets headers](https://developers.cloudflare.com/workers/static-assets/headers/): final asset-directory `_headers` governs static responses, including hostname-qualified rules. This matches generated-only candidate preparation, without a new Worker request handler.

The unresolved issue is repository integration and evidence ownership, not a
novel algorithm. Additional academic machinery would not resolve a missing main
tree or a hardcoded absent CI workflow; a concrete source contract and hosted
acceptance are the discriminating evidence here.

## Actual execution and deliverable scope

Performed: relevant existing-document reading, fresh main fetch, Git tree/diff
inspection, safe isolated worktree creation, official contract verification, and
this durable English plan. The local documentation commit changes only this
file and can be cherry-picked by the root without importing site or Mail code.

Not performed: local tests/builds, dependency installation, hosted dispatch,
remote push, PR creation, merge, deployment, DNS/provider mutation, tag/Release
creation, SMTP, or changes to shared primary branch/worktree files.
