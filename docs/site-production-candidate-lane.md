# Production candidate site lane

Date: 2026-10-01. Scope: a truthful public candidate landing page at
`https://amail.moesegfault.dev/`, **not** publication of v0.1.0, a production
Mail rollout, acceptance of delivery, or authorization to unhold sending.

## Decision and invariants

The earlier DNS/cutover audit (`production-dns-readiness-2026-09-29.md`) found
no candidate operation: the existing production site jobs require a published
Release and force published copy. Keep those gates intact. A separate
`.github/workflows/site-candidate.yml` owns candidate preparation and explicit
manual promotion; `ci.yml` and `release.yml` remain unchanged.

| Boundary | Contract |
| --- | --- |
| Source validation | Pushes to main/the existing development branch and relevant PRs run synthetic regressions, Astro checks, candidate bundle acceptance and fresh published-build isolation. No credentials, deployment or provider access. |
| Deployment intent | Only workflow_dispatch, target deploy-candidate, refs/heads/main and exact confirmation `DEPLOY_REVIEWED_PRODUCTION_CANDIDATE`. Independent review is an operator prerequisite; the confirmation is an acknowledgement, not a cryptographic review attestation. |
| Hosted source evidence | An explicit numeric `source_ci_run_id` must identify successful `ci.yml` for exactly `GITHUB_SHA`, from main or the existing trusted development branch, with the `Astro release site` job actually successful, not skipped. Same-run candidate checks must also pass. |
| No candidate downgrade | Read-only GitHub API checks reject an existing public v0.1.0 tag or published Release, including in-flight tagged publication. Internal untagged drafts are not public releases and are outside the inventory contract. Explicit authentication/transport errors fail closed. Recheck immediately before deployment. |
| Mutation scope | Only the existing `amail-release-site` Worker and its configured Custom Domain/static assets. No new placeholder DNS record, Mail Worker, D1, Queue, route, SMTP, gate attestation or send policy operation. |
| Deployment ordering | Share `deploy-site-production` concurrency with both published-site jobs, do not cancel an in-flight deployment. No top-level cancellation can interrupt a mutation. |
| Candidate indexing | After a clean candidate build, add a production-host-only `X-Robots-Tag: noindex, nofollow` and `X-Amail-Candidate-Revision` to **generated** `site/dist/_headers`. Keep source `_headers` staging-only and robots.txt crawlable. |
| Promotion compatibility | A fresh published build copies the unchanged source headers and must compare byte-identically; published workflow behavior/indexability remains unchanged. Candidate mode cannot leak its generated production header into future builds. |
| Truthfulness smoke | Exact `/`, `/manual/`, `/changelog/` return HTTP 200 HTML without redirects, each contains its own candidate copy and no published phrase or actual version-specific tag/download link. Each carries noindex/nofollow and the exact source SHA; both route-local TOCs must be nonempty and target existing heading IDs. |

The changelog explicitly labels its pre-release date as a **candidate record
date**, rather than Release. Existing manual filename/checksum/installation
instructions describe the intended future released workflow, not current
downloadability. Candidate entry prose no longer calls a public release or Skill
download already available. At tagging, the UTC release date and evidence-based
claims still need the separate release review; relabeling is not that acceptance.

## Operator sequence (not executed by this change)

1. Obtain independent source review, resolve findings and record the artifact.
   Push reviewed source and wait for hosted CI/candidate source checks. Do not
   deploy from the development branch, or infer hosted success from local tests.
2. Merge/fast-forward reviewed source to main. Identify successful `ci.yml`
   evidence for the **exact main SHA**; merging with a different SHA requires new
   hosted CI. GitHub must first register the new workflow from the repository's
   default branch: while this file exists only on the development branch, its
   push checks may run but the new manual workflow need not be dispatchable.
   Merge the reviewed workflow into default branch main, wait for its Actions
   registration/source checks, then dispatch using main. Do not temporarily relax
   the main-only guard, edit ci.yml inputs, or create a tag to bypass registration.
   Confirm no public v0.1.0 tag or published Release exists; do not interpret
   read-token visibility as an inventory of internal untagged drafts.
3. Freeze all other production-site writers and v0.1.0 tag/publication operations
   for this dispatch. The shared deploy lock serializes site mutation, but cannot
   serialize Release creation or manual/dashboard/other-repository operations.
   GitHub's confirmation input does not itself establish this external freeze.
4. Dispatch `Production candidate site` from main with target deploy-candidate,
   the exact-source CI run ID, and the reviewed-intent confirmation. Existing
   repository Secrets remain the credential model; values are never printed.
5. Wait for the three-route live smoke. Record source SHA, workflow run/attempt,
   deployed Worker version and public DNS/HTTPS observation in the release ledger.
   A green source run alone is **not** deployed acceptance. On smoke failure,
   do not tag, publish, unhold, blindly retry a Mail operation, or claim launch.
   Investigate the exact site deployment; use only independently reviewed site
   rollback/redeployment, never a stale candidate after publication.
6. After later production acceptance, use the unchanged gated published lane.
   It builds from clean source and removes the candidate-specific generated
   header. Candidate deployment is unavailable once v0.1.0 has a public tag or
   published Release.

### Read-token publication boundary

The workflow deliberately retains `contents: read` and `actions: read`; it does
not gain repository write access merely to inspect drafts. GitHub documents
published releases as public information, while draft listings require push
access. A `releases/tags/v0.1.0` 404 with this token can therefore mean no visible
release while an internal untagged draft exists. The gate does **not** establish
draft absence. Such a draft is not a public release and does not contradict
candidate copy saying downloads are not published. If a draft is returned, it
is not itself rejected; a public tag still blocks the lane independently, and
any returned non-draft Release is rejected. Unexpected publication metadata,
explicit access rejection or transport failure remain errors. The success
diagnostic says `published_release=not_visible`, not `release=absent`.

The external freeze must still cover publishing that draft or creating its tag
during deployment. Read-only preflights and the site deployment lock do not
authorize or serialize those independent publication operations.

First Custom Domain deployment can provision DNS/certificates; do not manually
add placeholder A/CNAMEs. The bounded curl retries allow propagation but do not
certify zone topology, clean-install usability, accessibility or Mail operation.
Smoke artifacts remain beneath repository `.temp` and are removed on exit.
No body/header/provider response is printed as a diagnostic.

## Evidence and limits

Implementation files: `infra/release/candidate_site.py`,
`check_candidate_site_gate.py`, their two synthetic test modules and the separate
workflow. This change performs **no local tests/builds, deployment, live SMTP,
DNS mutation or gate change**. Hosted execution and independent review are still
required; there is no new deployed-site claim.

This is a narrow production engineering operation, not a novel algorithm or
academic contribution. Additional research machinery would not improve the
relevant failure boundary. The useful invariant is separate publication state
from site availability while making source identity and route-local truthfulness
observable. The provider's mature static asset/header mechanism avoids an
extra Worker handler or content-wide meta/header exceptions.

Primary references checked on 2026-10-01:

- [Cloudflare Static Assets headers](https://developers.cloudflare.com/workers/static-assets/headers/): `_headers` in the final asset directory, HTTPS absolute-host rules, and header application to static responses rather than Worker-generated responses.
- [Cloudflare Custom Domains](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/): Worker Custom Domain routing/DNS/certificate ownership.
- [GitHub workflow runs API](https://docs.github.com/en/rest/actions/workflow-runs#get-a-workflow-run): immutable head SHA, workflow ID and status/conclusion source evidence.
- [GitHub Releases API visibility](https://docs.github.com/en/rest/releases/releases#list-releases): published releases are publicly visible; draft listings require push access. Read-only visibility is not proof of absence of internal drafts.
- [Cloudflare production best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/): platform mechanisms and explicit environment/credential boundaries. This assets-only change adds no request handler, runtime bindings or new observability capture.
