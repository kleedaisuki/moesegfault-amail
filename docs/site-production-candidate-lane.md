# Standalone production candidate site lane

Date: 2026-10-01. Scope: a truthful public candidate landing page at
`https://amail.moesegfault.dev/`, **not** publication of v0.1.0, a production
Mail rollout, acceptance of delivery, or authorization to unhold sending.

This standalone site bootstrap contains no Mail/Identity code, `ci.yml`, Release
workflow, Queue/D1/R2 operation, or send policy. It ports the reviewed static site
and candidate helpers from `e35b743`/`496f758`, replacing the absent Mail CI
with dedicated site-only source evidence. See [bootstrap scope](site-standalone-bootstrap.md).

## Decision and invariants

| Boundary | Contract |
| --- | --- |
| Source validation | `.github/workflows/site-ci.yml` runs on relevant main/bootstrap-branch pushes, PRs, check-only dispatches, or same-commit reuse. Its single `Astro candidate site source checks` job runs synthetic regressions, Astro checks, candidate bundle acceptance and fresh published-build isolation. No credentials, deployment or provider access. |
| Deployment intent | `.github/workflows/site-candidate.yml` is manual only. Default target is checks; deploy requires target deploy-candidate, refs/heads/main, and exact confirmation `DEPLOY_REVIEWED_PRODUCTION_CANDIDATE`. Independent review is an operator prerequisite; confirmation is acknowledgement, not cryptographic review attestation. |
| Hosted source evidence | Numeric `source_ci_run_id` identifies successful **site-ci.yml**, not Mail CI, for exactly `GITHUB_SHA`, from main or codex/amail-site-candidate. Event is push or workflow_dispatch and exact `Astro candidate site source checks` job must pass, not skip. Same-run checks reuse site-ci.yml from the caller's same commit without inheriting provider secrets. |
| No candidate downgrade | Read-only GitHub API checks reject an existing public v0.1.0 tag or published Release, including in-flight tagged publication. Internal untagged drafts are outside the inventory contract. Explicit access/transport errors fail closed. Recheck immediately before deployment. |
| Mutation scope | Only `amail-release-site` Worker and its configured Custom Domain/static assets. No Mail Worker, D1, Queue, route, SMTP, gate attestation, send policy or placeholder DNS operation. First Custom Domain deployment may provision DNS/certificates, so still requires explicit authorization. |
| Deployment ordering | Preserve shared `deploy-site-production` concurrency with cancel-in-progress false. No top-level cancellation interrupts mutation. Later published-site writers must use the same group. |
| Candidate indexing | Clean candidate build gets production-host-only `X-Robots-Tag: noindex, nofollow` and `X-Amail-Candidate-Revision` in generated `site/dist/_headers`. Source `_headers` stays staging-only and robots.txt remains crawlable. |
| Promotion compatibility | Fresh synthetic published build restores headers byte-identical to source. Published mode exists only as a compatibility fixture here; this branch provides **no published deployment lane**. |
| Truthfulness smoke | Exact `/`, `/manual/`, `/changelog/` return 200 HTML without redirects; each has its own candidate copy, service-availability disclaimer, no published phrase and no actual version-specific tag/download link. Each carries noindex/nofollow and exact source SHA. Both route-local manual/changelog TOCs are nonempty and target existing heading IDs. |

Changelog dates are **candidate record dates**, not public publication. Manual
filename/checksum/install instructions describe the future released workflow,
not current downloadability. Candidate pages explicitly state that site
availability does not establish Mail/service/send availability. General GitHub
repository and Releases-list links do not assert a version, binary, Skill or
checksum file exists.

## Operator sequence (not executed by this source change)

1. Obtain independent review of the complete standalone scope, resolve findings,
   push reviewed source and wait for hosted **Candidate site CI**. Do not deploy
   from the bootstrap branch or infer CI success from local tests.
2. Root owns merge approval. After approved integration into default main, wait
   for registration of both workflows and successful site-ci.yml evidence on
   the **exact main SHA**. A merge/squash commit with a different SHA requires
   fresh hosted evidence. GitHub requires the workflow in the default branch
   for manual dispatch. Do not relax main-only guards, add Mail ci.yml, or
   create a tag to bypass registration.
3. Freeze all other production-site writers and v0.1.0 tag/Release-publication
   operations. The shared lock cannot serialize tag creation, draft publication,
   dashboard operations or other concurrency groups. Confirmation input does
   not establish this external freeze.
4. Only after separate operator approval, dispatch `Production candidate site`
   from main with deploy-candidate, exact-source **site-ci.yml** run ID, and
   reviewed-intent confirmation. Repository/production environment Secrets
   remain the credential model; values are never printed. Source checks use
   no Cloudflare credentials or inherited secrets.
5. Wait for live three-route smoke. Record source SHA, run/attempt, deployed
   Worker version and public DNS/HTTPS observation. Green source CI is **not**
   deployed acceptance. On smoke failure, do not tag, publish, unhold, blindly
   retry Mail or claim launch. Investigate the exact site deploy; only
   independently reviewed site rollback/redeployment is appropriate.
6. Later public release requires a separately reviewed, fully gated published
   lane and actual asset/CLI/Mail acceptance. This branch cannot publish it.
   Preserve generated-only candidate headers and the shared site lock. Candidate
   deployment is unavailable after a public v0.1.0 tag or published Release;
   never redeploy a stale candidate as a downgrade.

### Read-token publication boundary

The deployment workflow retains `contents: read` and `actions: read`; it does
not gain write access to inspect internal drafts. A release-tag lookup 404 can
mean no visible release while an internal untagged draft exists. The gate does
**not** establish draft absence. Such a draft is not a public release and does
not contradict candidate copy saying public downloads are not published. If a
draft is returned, it is allowed; a public tag blocks independently and any
returned non-draft Release is rejected. Unexpected publication metadata, explicit
access rejection or transport failure remain errors. Diagnostic:
`published_release=not_visible`, not a universal `release=absent` claim.

External freeze covers publishing that draft or creating its tag during deploy.
Repeated read-only preflights and the shared lock do not authorize or serialize
those independent publication operations.

Bounded curl retries allow propagation but do not certify zone topology,
clean-install usability, accessibility or Mail operation. Smoke files stay under
repository `.temp` and are removed on exit. No body/header/provider response is
printed as a diagnostic.

## Evidence and limits

Implementation: complete `site/`, two site-only workflows, `candidate_site.py`,
`check_candidate_site_gate.py`, and three synthetic candidate test modules in
`infra/release`. There is no other runtime dependency on the unmerged Mail
branch. Install/build success and hosted acceptance are recorded only after
execution; source review alone does not establish them. This change executes no
local tests/builds, deployment, SMTP, DNS mutation or gate change.

Primary references rechecked on 2026-10-01:

- [GitHub manual workflow dispatch](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow): default-branch registration.
- [GitHub reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows): repository-relative calls use the caller's same commit; no provider secrets are inherited here.
- [GitHub workflow runs API](https://docs.github.com/en/rest/actions/workflow-runs#get-a-workflow-run): workflow identity, immutable head SHA and status/conclusion evidence.
- [GitHub Releases API](https://docs.github.com/en/rest/releases/releases#list-releases): public visibility is not read-token draft inventory.
- [Cloudflare Static Assets headers](https://developers.cloudflare.com/workers/static-assets/headers/): generated asset-directory headers and HTTPS hostname rules.
- [Cloudflare Custom Domains](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/): Worker domain/DNS/certificate ownership.
- [Cloudflare production best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/): platform mechanisms and explicit credential/state boundaries. This assets-only design needs no request handler or runtime binding.

## Fixed post-merge source and workflow-registration outcome

Root merged [focused PR #3](https://github.com/kleedaisuki/moesegfault-amail/pull/3)
at 2026-09-30 21:54:31 UTC. The fixed main merge source is
`de2f1508005ff84841bc197b7181c5177f145857`; a fresh remote main read and Git
fetch confirmed this exact SHA. Site/workflows/helpers/docs at this main commit
match the reviewed branch tree byte-for-byte before this evidence-only update.

**GO for the source-CI and default-branch-registration prerequisites of a
separate root deployment decision. No deployment is authorized or executed by
this evidence record.**

| Fixed evidence | Observed result |
| --- | --- |
| [Exact-main Candidate site CI run 36782391377](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36782391377) | Push event, head_branch main, exact head SHA de2f1508005ff84841bc197b7181c5177f145857, attempt 1; completed success at 2026-09-30 21:55:01 UTC |
| Exact source workflow/job | site-ci.yml workflow ID 371604893; job `Astro candidate site source checks` ID 110115566308; every material and cleanup step completed successfully |
| Both workflow syntaxes | Hosted digest-pinned actionlint passed both site workflows, including reusable-call validation; archive SHA-256 OK |
| Synthetic regressions | 13 Python tests passed; 22 Node route-local tests passed with 0 failures |
| Locked install / Astro checks | Hosted frozen-lockfile install passed; Astro checked 10 files with 0 errors, 0 warnings, 5 retained deprecated-z hints |
| Candidate output | Three pages built; route-local state and service boundary, both local TOCs and generated-only candidate header preparation passed |
| Published isolation fixture | Fresh three-page published-mode build and state checks passed; source/generated headers byte-identical via successful cmp; no published deployment occurred |
| Default branch | Repository API reports main; branch API reports the exact merge SHA above |
| Candidate workflow registration | [site-candidate.yml on main](https://github.com/kleedaisuki/moesegfault-amail/blob/main/.github/workflows/site-candidate.yml) is present and manual-only; Actions metadata reports `Production candidate site`, ID 371555196, state active |
| Source workflow registration | [site-ci.yml on main](https://github.com/kleedaisuki/moesegfault-amail/blob/main/.github/workflows/site-ci.yml) is present; Actions metadata reports `Candidate site CI`, ID 371604893, state active |

Registration was verified with read-only repository/branch/workflow metadata
and default-main file inspection, not by trying a dispatch. Workflow active plus
default-branch file presence establishes the documented registration boundary;
it does not establish production environment protections, provider capability,
DNS/TLS readiness or an already deployed site.

For this fixed main source, the reviewed manual lane's source_ci_run_id evidence
is **36782391377**, not a pre-merge branch run or PR run. If main changes,
including integration of this documentation-only commit, obtain successful
site-ci.yml evidence for the new exact main SHA before dispatch. This entry is
historical evidence about de2f150, not an exemption from exact-source checks.

Still required before any separately authorized mutation: root/operator intent,
an externally established freeze of competing site and v0.1.0 tag/publication
writers, production capability/environment verification, and the workflow's
fresh public-tag/published-Release preflights. This audit did not inspect or
establish live public publication absence; the deploy lane checks that state
again twice. Live three-route acceptance, public DNS/HTTPS and Worker version
are post-deployment obligations, and no Mail/public-release conclusion follows.

The evidence audit itself ran no local project tests/build/install and did not
dispatch workflows, deploy, mutate DNS/provider state, create tags/Releases or
perform SMTP. Root-owned operations are recorded separately below.
The evidence-only document commit remains isolated/local for root coordination;
it does not advance the remote main source or silently invalidate the fixed run.

## Fixed root-authorized candidate deployment and live acceptance

Root explicitly authorized and dispatched exactly one candidate deployment,
[Production candidate site run 36782618160](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36782618160),
at source `de2f1508005ff84841bc197b7181c5177f145857`, main, workflow_dispatch,
attempt 1. Created 2026-09-30 21:56:46 UTC; completed **success** at 21:57:58 UTC.
Root reported prior secret-name/default-registration/branch-policy/publication-
absence/concurrency preflight. This follow-up observed outcomes only; it did not
dispatch, repeat, authorize or retry a deployment and did not independently
inventory out-of-workflow writers.

**PASS for candidate-site deployment and the bounded three-route live contract
at this fixed source/run. This is not v0.1.0 publication or Mail availability.**

### Fixed hosted job and step outcomes

| Boundary | Observed result |
| --- | --- |
| Same-run source job | Job 110116324741, `Candidate source and publication-isolation checks / Astro candidate site source checks`, completed success; both-workflow syntax, synthetic regressions, locked install, Astro, candidate preparation and fresh published isolation all passed |
| Deployment job | Job 110116473345, `Deploy reviewed candidate only, not v0.1.0`, completed success; no skipped/failing material steps |
| First reviewed-intent/source/publication gate | Step passed; diagnostic at 21:57:32 UTC reported exact-source CI passed, public tag absent and published Release not visible |
| Candidate output before mutation | Candidate build/state/three-page preparation passed at 21:57:39 UTC, with generated-only production headers |
| Immediate pre-mutation publication recheck | Step passed at 21:57:41 UTC; public tag absent and published Release not visible, without claiming internal draft inventory |
| Site-only upload/deployment | Step completed success for configured `amail-release-site` and production Custom Domain; deployment output identifies version `39a2dae4-c1b2-440c-8c27-ef7c386c7441` |
| Actual hosted live smoke | Step completed success at 21:57:53 UTC: `pages=3 toc=2 state=candidate`, including exact-route HTTP/HTML, candidate copy/service boundary, no premature links, local TOC targets, noindex/nofollow and exact source revision |

Source CI evidence for this deployment remains run **36782391377**, not a
pre-merge branch or PR run. The fixed Worker version is an identity extracted
from sanitized deployment evidence; no raw provider body/log or secret value
is persisted or reproduced here.

### Independent public HTTPS/HTML observation

At **2026-09-30 21:59:03 UTC**, PowerShell `Invoke-WebRequest` requested each
exact production route, with `MaximumRedirection 0` and a 30-second timeout.
All returned HTTP 200 and `Content-Type: text/html`, with:

```text
X-Robots-Tag: noindex, nofollow
X-Amail-Candidate-Revision: de2f1508005ff84841bc197b7181c5177f145857
```

Public HTML was inspected in memory without storing/printing body contents.
The independent observer checked actual anchor hrefs, designated navigation
labels, decoded fragment targets and HTML IDs; the stronger full hosted smoke
above also passed. These are point-in-time public observations, not a new local
project test/build or a reproduction of provider state.

| Exact route | Route-local status and service disclaimer | Version tag/download anchors | Designated local TOC | Local links / missing targets |
| --- | --- | ---: | ---: | --- |
| `/` | Candidate status present; service availability explicitly not asserted | 0 | Not required | Not applicable |
| `/manual/` | Candidate/download-unavailable status and service disclaimer present | 0 | 1 | 12 / 0 |
| `/changelog/` | Candidate-under-acceptance status and service disclaimer present | 0 | 1 | 1 / 0 |

### Independent public DNS observation

The same observation window freshly queried apex NS through `8.8.8.8`, finding
`raquel.ns.cloudflare.com` and `jermaine.ns.cloudflare.com`. `Resolve-DnsName
-DnsOnly` then queried A, AAAA and CNAME for `amail.moesegfault.dev` at both
authoritative servers and Google Public DNS. All three returned the same sets:

| Record | Answers at both authoritative servers and 8.8.8.8 |
| --- | --- |
| A | 104.21.2.174; 172.67.129.129 |
| AAAA | 2606:4700:3033::6815:2ae; 2606:4700:3035::ac43:8181 |
| CNAME | Zero answers, no query failure |

Together with the HTTPS 200 observations, this establishes public candidate-host
resolution/reachability from the observation host and named DNS servers. These
are public edge answers, not an authenticated zone topology audit; answer order
may vary. No global DNS-propagation guarantee, independent IPv6 transport test,
clean-install/CLI/Skill usability, visual/accessibility acceptance, or Mail/API,
identity, delivery, SMTP or send-policy readiness is inferred.

### Authority and continuation

This acceptance records the one root-authorized run only. No retry, new
dispatch, manual DNS record, tag/Release or Mail operation was performed by
this observer. The candidate currently documents intended workflows without
claiming downloadable artifacts or a publicly available Mail service. Later
site source changes still require fresh exact-main-SHA source evidence;
publication/tag changes permanently close this candidate lane for v0.1.0.
Further deployment or public release decisions remain separately root-owned.
