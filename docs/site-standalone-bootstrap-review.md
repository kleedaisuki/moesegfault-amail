# Independent standalone candidate-site bootstrap review

Date: 2026-10-01. Reviewer scope: repository-relative isolated worktree
`.temp/amail-site-candidate`, branch
`codex/amail-site-candidate`, base
`7baea1adc0da08259a1f03f7307e989ec3bf8250`, implementation commits
`59567d0`, `f8a4772`, and subsequently observed syntax-tooling correction
`d076efef806aadaf5bb1f9e97ee1e5861706bc99`.

## Verdict and authority boundary

**GO for pushing the focused PR source and obtaining hosted source checks.**
No substantive defect was found within this reviewed scope. This is **not**
merge approval, deployment authorization, live acceptance, public v0.1.0
publication, Mail acceptance, or authorization to unhold sending. Those are
separate decisions with unexecuted prerequisites.

No production source was modified by this reviewer. Only this review artifact
is added. No local project tests, builds, dependency installation, actionlint
execution, hosted dispatch, deployment, Cloudflare/DNS operation, SMTP, tag or
Release mutation was performed. No shared primary-worktree edit was made.

## Source evidence and review results

| Boundary | Independent assessment |
| --- | --- |
| Base compatibility and import provenance | The base tree contains LICENSE and the existing staging R2 dispatch workflow. Both remain byte-identical. `git diff e35b743 59567d0 -- site` is empty and the imported site tree has exactly 30 tracked files. This establishes exact initial copying, not merely similarity. Later content/docs changes were separately inspected. |
| Standalone dependency floor | The final implementation adds two site workflows, five Python helpers/test modules, site/docs and root ignore rules. It does not import Mail/Identity runtime/config, CLI, Skill, release workflow, Queue/D1/R2 provisioning, send-policy or attestation machinery. Site Wrangler is assets-only with no request handler or service/storage binding. The pre-existing staging workflow remains outside the new source dependency graph. |
| Dedicated hosted source identity | `site-ci.yml` fixes one job name, `Astro candidate site source checks`. The GitHub gate requires this workflow's ID, exact full deployment SHA, trusted main/bootstrap branch, push/manual event, completed successful run and exactly one actually successful matching job. Missing, skipped, duplicate, failed or wrong-name jobs cannot satisfy it. A green unrelated run or PR merge SHA cannot stand in for the required source. |
| Reuse and capabilities | `source` calls `./.github/workflows/site-ci.yml`, which has `workflow_call` and comes from the caller's same commit. No provider secrets are passed or inherited; the called workflow has no production environment or provider-secret references. The separate ordinary deploy job consumes production environment/repository Cloudflare secrets only at its mutation step. The automatic read-only GitHub token is not absence of all credentials; it is distinct from provider capabilities. |
| Manual/default-branch registration | Candidate workflow is manual-only and defaults to checks. Mutation requires main, deploy-candidate target, successful same-run source checks and explicit confirmation; Python independently checks main. The runbook correctly requires default-branch registration and fresh exact-main-SHA hosted evidence after integration. Pushing this source branch cannot deploy it through this lane. |
| YAML and syntax-tool evidence | Both workflows parse successfully with existing Python 3.14/PyYAML BaseLoader; parsed events are push/PR/dispatch/call for CI and dispatch only for candidate, with expected job maps. This is static YAML parsing, not GitHub expression/schema or executable workflow acceptance. `d076efe` adds hosted actionlint on the exact two workflows before project checks. Its v1.7.11 Linux amd64 archive URL and SHA-256 independently match official GitHub release metadata, and checksum verification precedes extraction/execution. No actionlint binary was downloaded or executed locally. |
| Test discovery and contracts | `python -m unittest discover -s infra/release -p 'test_candidate_site*.py' -v` includes all three committed candidate test modules; top-level imports are compatible with that discovery directory. Tests use standard-library mocks and repository-local `.temp` fixtures. They cover wrong source/publication/job metadata, route-local truthfulness, real links, TOC targets, HTTP/MIME/indexing/source headers, and generated/source header isolation. Workflow string checks explicitly do not pretend to be arbitrary YAML validation; hosted actionlint supplies separate structural checking. Tests were inspected, not run. |
| Candidate content | Each route includes its own candidate status plus an explicit disclaimer that candidate documentation does not establish Mail/send availability. Home CTAs are design/install previews. Manual filenames/checksums are framed as post-publication instructions, not currently downloadable assets. Candidate changelog labels its date as a candidate record date. Actual candidate anchors use generic Releases listing, not v0.1.0 tag/download endpoints. No unmerged CLI/Skill link is presented as an existing local dependency. |
| Three routes and TOCs | Astro statically emits home/manual/changelog. Manual navigation derives from Markdown headings; changelog version fragments correspond to explicit version heading IDs. `candidate_site.prepare` validates all three generated pages, both nonempty route-local TOCs and existing targets, exact navigation, local candidate status and service disclaimer before modifying headers. Smoke repeats these checks on fetched responses rather than accepting unrelated-page status or URL text. |
| Indexing and promotion compatibility | Source `_headers` remains staging-host-only. Preparation requires a clean generated copy of source headers, then modifies generated `dist/_headers` only, adding production-host-only noindex/nofollow and exact source SHA. Robots permits crawling so the header is observable. Dedicated CI then performs a fresh published compatibility build and byte-compares its headers to source. Deployment builds a separate candidate in its own job/checkout, so it cannot upload the last published fixture from the source job. |
| Publication boundary | Full read-only preflight runs twice, initially and immediately before Wrangler. Any existing public v0.1.0 tag blocks, as does any returned non-draft Release. Missing/nonboolean publication metadata fails. Explicit denial/transport errors fail rather than imply absence. A token-visible 404 does not establish internal untagged draft absence; the code/runbook preserve the previously reviewed narrowed public-publication contract instead of reintroducing that false claim. |
| External freeze and ordering | The deploy job uses `deploy-site-production`, with cancel-in-progress false and no top-level cancellation. Publication/tag/dashboard/other-group writers are not serialized by that lock; runbook explicitly requires an external site/tag/Release publication freeze. The confirmation is acknowledgment, not proof of an independent review or freeze. Later published writers must adopt the same lock and retain their separately reviewed gates. |
| Provider and live acceptance | `pnpm run deploy` selects the configured site script, not pnpm's unrelated built-in deploy command. Mutation targets the site Worker and Custom Domain. Cloudflare may create DNS/certificates during first domain deployment, so source review does not describe that as non-mutating. No placeholder DNS operation is added. Live smoke curls the exact HTTPS home/manual/changelog URLs without following redirects, requires HTTP 200, HTML MIME, exact source pin, noindex/nofollow and page/TOC assertions; fixture files stay under repository `.temp` and are removed. Separate DNS/HTTPS and deployed Worker-version observations are operator obligations, not proven zone topology from curl alone. |
| Permissions and diagnostics | Source jobs use contents:read; deploy additionally uses actions:read and production environment. Checkout disables credential persistence. Cloudflare values are step-local and checked without printing. There is no permissions expansion for draft inventory, no provider capability in source validation, no Release/tag write, and no Mail gate mutation. Environment protection policy and actual token scope cannot be established from YAML alone. |

## Reproducible static procedures

Git inspection used repository-relative isolated-worktree paths:

```powershell
git -C .temp/amail-site-candidate status --short --branch
git -C .temp/amail-site-candidate log -5 --oneline
git -C .temp/amail-site-candidate diff --stat 7baea1a..HEAD
git -C .temp/amail-site-candidate diff e35b743 59567d0 -- site
git -C .temp/amail-site-candidate ls-tree -r --name-only 59567d0 -- site
git -C .temp/amail-site-candidate diff 59567d0 f8a4772 -- site
git -C .temp/amail-site-candidate diff f8a4772 d076efe
git -C .temp/amail-site-candidate diff 7baea1a HEAD -- LICENSE .github/workflows/staging-worker-r2-capability.yml
git -C .temp/amail-site-candidate diff --check 7baea1a HEAD
```

The initial-copy diff, preserved-base-file diff, and whitespace check have no
output. Relevant implementations, workflow configuration, page templates,
content, lock/configuration and synthetic tests were inspected. Existing
`docs/review-site-production-candidate-496f758.md` and the split-decision
document were consulted before assessing the standalone adaptation; the old
resolved draft-visibility concern was not reopened without new evidence.

Static YAML parsing loaded only the two workflow files using
`yaml.load(text, Loader=yaml.BaseLoader)` with PYTHONDONTWRITEBYTECODE=1; no
project code was imported and no tests/builds were run. The loader keeps the
`on` key as a string, avoiding YAML 1.1 boolean-key interpretation. Its success
does not replace the new hosted actionlint result.

Official actionlint asset metadata was read without authentication or saving an
archive, using the public release endpoint below. Observed asset:
`actionlint_1.7.11_linux_amd64.tar.gz`; digest:
`sha256:900919a84f2229bac68ca9cd4103ea297abc35e9689ebb842c6e34a3d1b01b0a`.

## Remaining discriminating evidence

1. Push only the reviewed focused branch and obtain an actual successful
   Candidate site CI run/job for its resulting source SHA, including hosted
   actionlint, all discovered synthetic tests, locked dependency install, Astro
   checks, candidate prepare and fresh published-header isolation.
2. Root separately owns PR/merge approval. After integration, obtain a new
   exact-main-SHA CI run and default-branch workflow registration; review-doc
   inclusion does not permit reusing a different implementation SHA.
3. Only separately authorized deployment may inspect/use production provider
   capabilities or mutate the site/domain. Establish environment protections,
   review/freeze prerequisites and actual provider capability then; source YAML
   alone cannot prove them.
4. Only completed live smoke plus recorded public DNS/HTTPS and Worker version
   can establish candidate-site acceptance. None establishes public artifact,
   clean-install, accessibility, Mail, sending or delivery acceptance.

These are verification/authority limits, not speculative findings. The narrow
assets-only integration uses mature platform header, domain and workflow
mechanisms; an academic redesign does not materially improve this bounded
publication-safety decision.

## Primary references independently checked

- [GitHub reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows): relative same-commit calls and explicit secret passing/environment boundaries.
- [GitHub manual workflow dispatch](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow): default-branch registration.
- [GitHub workflow runs API](https://docs.github.com/en/rest/actions/workflow-runs#get-a-workflow-run) and [workflow jobs API](https://docs.github.com/en/rest/actions/workflow-jobs#list-jobs-for-a-workflow-run): source/run/job identity and outcomes.
- [GitHub Releases API](https://docs.github.com/en/rest/releases/releases#get-a-release-by-tag-name): published release lookup and draft-visibility limits.
- [Cloudflare Static Assets headers](https://developers.cloudflare.com/workers/static-assets/headers/): final asset-directory headers, hostname patterns and static responses.
- [Cloudflare Custom Domains](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/): automatic DNS/certificate provisioning and ownership/conflict prerequisites.
- [Cloudflare production best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/): production framework; no unnecessary handler or state binding is introduced here.
- [actionlint checks](https://github.com/rhysd/actionlint/blob/main/docs/checks.md) and [official v1.7.11 release asset metadata](https://api.github.com/repos/rhysd/actionlint/releases/tags/v1.7.11): distinction between YAML parsing and hosted workflow/reusable/expression validation, plus archive pin provenance.
