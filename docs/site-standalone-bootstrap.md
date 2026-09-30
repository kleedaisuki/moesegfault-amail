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
