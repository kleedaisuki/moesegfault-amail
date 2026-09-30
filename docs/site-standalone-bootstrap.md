# Standalone candidate site bootstrap

Date: 2026-10-01. Explicitly authorized alternative to importing the full Mail
branch merely to register a production candidate page.

## Source and ownership

Base: freshly fetched `origin/main` at
`7baea1adc0da08259a1f03f7307e989ec3bf8250`. Its LICENSE and staging R2 capability
workflow remain unchanged. Isolated worktree: `.temp/amail-site-candidate`;
branch: `codex/amail-site-candidate`. Resolved target was verified under
repository `.temp` before creation. Shared primary branch/worktree is untouched.

Initial import is the exact 30-file `site/` tree from reviewed
`e35b7439e45f10eabc86de13f7c72a75a940ab6c` (candidate feature
`496f75826f74417081a8558b8018aadd329c9168` plus publication correction).
Focused subsequent changes make CI/documentation independent of Mail and
strengthen candidate-only service-availability language.

## Exact integration boundary

| Added paths | Purpose |
| --- | --- |
| `site/**` | Complete static three-page site, lock, assets, checks, site-only Wrangler config |
| `.github/workflows/site-ci.yml` | Dedicated hosted source evidence and reusable same-commit checks |
| `.github/workflows/site-candidate.yml` | Main-only manual candidate deployment with preserved publication boundaries |
| `infra/release/candidate_site.py` | Generated-only production noindex/source pin and route-local smoke |
| `infra/release/check_candidate_site_gate.py` | Exact-SHA successful site-ci.yml job and read-only public publication exclusion |
| `infra/release/test_candidate_site.py` | Synthetic page/TOC/header acceptance regressions |
| `infra/release/test_candidate_site_gate.py` | Trusted source/publication regressions |
| `infra/release/test_candidate_site_workflow.py` | Hosted static workflow identity/no-secret/no-mutation source checks |
| `docs/site-production-candidate-lane.md`, `docs/site-standalone-bootstrap.md` | Standalone operator contract, scope, migration, evidence and limits |
| `docs/review-site-standalone-bootstrap-f8a4772.md` | Independent static review of bootstrap and hosted-syntax follow-up, with bounded GO |
| `docs/site-standalone-bootstrap-review.md` | Root-assigned independent review, including separate static YAML parsing and bounded GO |
| `.gitignore` | Repository-local fixture/interpreter cache exclusions |

No `ci.yml`, `release.yml`, CLI, Mail/Identity runtime/configuration, Skill,
Queue/D1/R2 provisioning helper, send gate, release verification/attestation,
or existing staging workflow edit is imported. Source validation needs only
site, five allowlisted Python helpers/tests, standard Python and Node tools.
Provider secrets are used only in separately guarded manual deploy steps.

## Dedicated CI and same-commit reuse

Original gate required absent `ci.yml` and `Astro release site` job. Instead of
adding Mail dependencies or loosening evidence, this bootstrap fixes workflow
identity to `site-ci.yml`, successful job to `Astro candidate site source checks`,
and trusted branches to main and bootstrap. A different workflow, SHA, untrusted
branch, PR event, missing/duplicate/skipped/failed site job is rejected.

Manual workflow reuses source workflow through a repository-relative same-commit
reference. Prior hosted evidence and same-run candidate/published-header checks
exercise one implementation, without duplicated commands or inherited provider
secrets. Published mode is a compatibility fixture, not a deploy lane.

## Content boundary and future full-branch merge

Each candidate route explicitly says the site does not establish Mail or public
send availability. Homepage CTAs are previews, not invitations to use an
unlaunched service. Manual install instructions are future-release instructions;
general Releases-list links are retained without actual version-specific
tag/download links. Source-preserved platform filenames and intended CLI
semantics are not runtime acceptance claims or new artifact commitments.

A future full Mail branch merge must reconcile duplicated site/helper paths
explicitly and retain **site-ci.yml evidence**; do not silently restore Mail CI
as the candidate evidence dependency or discard standalone fixes by replacing
the tree with older source. Preserve all existing Mail workflow/input contracts
and send gates. Update site README/runbook to reflect actual added CLI/release
lanes at that integration. Published writers must share `deploy-site-production`
and require separately reviewed asset/Mail gates; this bootstrap supplies none.

## Acceptance plan and current evidence

1. Independent static review of the complete standalone diff before push.
2. Push only focused branch for GitHub Actions checks, including actionlint
   syntax/reusable-call checks for both site workflows. No local tests/builds or
   dependency install for this workstream.
3. Record actual hosted run/job and failures; repair in bounded commits, rerun
   affected checks. PR integration/merge stays root-owned and separate.
4. After approved merge, require exact main SHA evidence and default-branch
   registration. Operator authorization and external publication freeze remain
   prerequisites to any candidate deployment.
5. Actual live three-route smoke, source/indexing headers, Worker version and
   public DNS/HTTPS establish site acceptance, not public release or Mail.

At initial implementation, no hosted result or deployed acceptance is claimed.
No local tests/builds, deployment, DNS/provider mutation, tag/Release, SMTP or
shared worktree modification occurred. Source review and hosted outcomes must
be separately recorded when available.

This narrow integration/production-safety task progresses by identifiable,
truthful candidate-only site evidence, not speculative academic machinery or a
new claim of Mail acceptance.

Hosted syntax tooling uses actionlint v1.7.11, with Linux amd64 archive digest
`900919a84f2229bac68ca9cd4103ea297abc35e9689ebb842c6e34a3d1b01b0a` pinned from
the [official release asset metadata](https://api.github.com/repos/rhysd/actionlint/releases/tags/v1.7.11)
on 2026-10-01. The archive is downloaded/verified/extracted only in hosted
repository `.temp`, before syntax checking the two allowlisted workflows.
This adds no provider permission or local install; unexpected upstream bytes
fail checksum before execution. See [actionlint](https://github.com/rhysd/actionlint)
for workflow syntax, expressions and reusable-workflow validation scope.

## First hosted source/syntax acceptance

[Candidate site CI run 36781340287](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36781340287),
attempt 1, push event, source `c88c0a983cfef2a9d1d3319d69b0c3d7652d0f24`,
completed successfully at 2026-09-30 21:44:55 UTC. Exact job
`Astro candidate site source checks` (110112069033) passed all material steps.
This is hosted source acceptance, **not** deployed/public/Mail acceptance.

| Check | Observed hosted result |
| --- | --- |
| Pinned actionlint and both workflow syntaxes | Archive checksum OK; exact two workflow syntax/expression/reusable-call checks passed |
| Python candidate/gate/workflow regressions | 13 tests passed, fully synthetic |
| Locked site dependencies | Installation succeeded on Ubuntu 24.04.5, Node 22.23.2, workflow-pinned pnpm 12.4.1 |
| Astro source checks | 10 files, 0 errors, 0 warnings, 5 hints about deprecated `z` import, retained from reviewed source |
| Node route-local regressions | 22 tests passed, 0 failures |
| Candidate build and prepare | Three pages built; route-local candidate/service copy, both TOCs and generated-only noindex/source preparation passed |
| Published compatibility | Three pages built, published state checks passed, final headers byte-identical to source via successful cmp |

Runner logs also report dependency deprecation notices and older action Node 20
runtimes being forced to Node 24 by the hosted platform. These did not fail the
run; no silent dependency/action upgrade was folded into this bounded import.
Later toolchain maintenance should address them independently. No Cloudflare
credentials, deployment, provider/DNS operation or tag/Release occurred.

This evidence covers the stated immutable source SHA. A subsequent docs-only
commit, PR merge/squash, or any other new SHA still requires its own exact hosted
source result before being represented as the gate's deployment evidence.
