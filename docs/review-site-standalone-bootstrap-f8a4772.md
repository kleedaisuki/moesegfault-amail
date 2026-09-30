# Independent static review: standalone candidate site bootstrap

Date: 2026-10-01.

Reviewed source: `f8a4772bec16adead0612a65f78f7e9618e5b58d` on
`codex/amail-site-candidate`, against main
`7baea1adc0da08259a1f03f7307e989ec3bf8250`.

The GO below also covers the focused hosted-syntax follow-up
`d076efef806aadaf5bb1f9e97ee1e5861706bc99` (four files, 27 insertions and
two deletions). The artifact filename retains the initial review identity.

## Decision

**GO for a focused branch push and non-deploying hosted source CI.** No material
source defect was identified in the examined standalone bootstrap. This is not
approval to merge, dispatch deployment, mutate Cloudflare/DNS, publish a Release,
create a tag, launch Mail, or unhold sending. The root/operator retains those
decisions and the separate prerequisites below.

**Production deployment: NOT AUTHORIZED by this review.** Hosted install/build
results, exact final main-SHA evidence, default-branch workflow registration,
production environment controls, explicit operator authorization and an external
publication/site-writer freeze remain unestablished. A later deployment also
needs actual live acceptance; source review cannot establish it.

## Findings

No substantive correctness/security finding requiring a source change before
hosted source checks was found. Confidence is high for the inspected static
boundaries and moderate for overall readiness: no code, dependency install,
build, tests or provider operations were executed in this review.

## Evidence and reasoning

| Contract | Static evidence and assessment |
| --- | --- |
| Complete bounded bootstrap | Main-to-source diff adds 40 files / 8,130 lines. Paths match the site, two workflows, five Python helpers/tests, two documents and root ignore file boundary. `LICENSE` and the existing staging R2 workflow are byte-unchanged (`git diff --quiet` exit 0). No Mail/Identity/CLI/Queue/D1 runtime or release lane was imported. |
| Site-only source CI | `site-ci.yml` has one runner job named exactly `Astro candidate site source checks`. Commands address only the imported site and Python helpers. It uses read-only contents permission, checkout without persisted credentials, no provider secrets, and no deploy command. Push and PR handlers cannot execute the separate manual deployment workflow. |
| Same source for same-run checks | `site-candidate.yml` calls `./.github/workflows/site-ci.yml`, without a ref or inherited secrets. GitHub documents this form as resolving the caller's same commit. The reusable workflow declares `workflow_call` and receives no production environment. |
| Guarded mutation | Deployment requires `workflow_dispatch`, `deploy-candidate`, `refs/heads/main`, successful reusable source job, production environment and exact confirmation. Only its deployment step receives Cloudflare credentials. Concurrency is `deploy-site-production`, with cancellation disabled and no top-level cancellation. |
| Exact hosted evidence | `check_candidate_site_gate.py` resolves workflow identity through `actions/workflows/site-ci.yml`; checks run workflow ID, immutable head SHA, trusted branch, allowed event, completed status and successful conclusion; requires exactly one matching successful source job. Old Mail job identity, PR events, wrong SHA, duplicate/missing/skipped jobs are rejected by the implementation and modeled in synthetic regressions. |
| Publication exclusion | The gate rejects any visible `v0.1.0` git tag and any returned non-draft Release; it checks twice, including directly before deploy. Explicit transport/access failures fail closed. Release 404 is documented as token visibility, not proof of draft absence. Internal untagged drafts do not themselves contradict candidate copy. |
| Candidate indexing/source pin | `candidate_site.py prepare` validates a full lowercase SHA, staging-only source header rules, byte-clean copied generated headers and all three pages before modifying only `site/dist/_headers`. Production-host-only noindex/nofollow and revision headers fit documented Static Assets hostname matching. Source robots remains crawlable, so the noindex header can be observed. |
| Published compatibility | Source CI builds candidate, prepares its headers, then performs a fresh published-mode build and compares generated `_headers` byte-for-byte with source. Published copy is only a non-deploying fixture in this bootstrap. Actual output cleanliness is an explicit hosted acceptance check, not a static result claimed here. |
| Truthful three-route copy | Homepage, manual layout and changelog each add the same candidate-only service-availability disclaimer. Candidate homepage CTAs preview design/install instructions rather than invite current use; manual installation is explicitly deferred until publication. Changelog dates are marked candidate record dates. Only generic Releases-list links are rendered in candidate branches. Platform filenames and CLI examples are future/intended contracts, not demonstrated binaries or Mail acceptance. |
| Navigation and TOCs | Shared layout has all three route links. Manual TOC derives actual Astro heading slugs; changelog anchors derive stable versions. Python generated/live checking requires one nonempty designated local TOC per relevant route, verifies fragment targets exist, and rejects actual version-specific release/download links on every route. |
| Live smoke contract | Curl requests exact slash-normalized routes without following redirects; shell requires 200. The Python verifier checks per-route candidate copy/disclaimer/navigation, HTML MIME, final HTTP 200, noindex/nofollow and an exact revision header. Temporary smoke files remain under repository `.temp` and are cleaned on exit. |
| Provider boundary | `site/wrangler.jsonc` is assets-only, with no Worker handler or data bindings. Production target is `amail-release-site` and its Custom Domain; staging name/domain are explicit and isolated. Custom Domain deployment can provision DNS/certificates, correctly treated as separately authorized mutation rather than a harmless upload. |

## Scope and limits

The review began with the supplied bootstrap/runbook knowledge, then inspected
the complete added-path inventory, workflows, acceptance/gate implementations,
their synthetic tests, all route/layout/content source and relevant configuration.
Compared the site against its `e35b743` import source to distinguish deliberate
standalone changes from retained assets/lockfile. Inspected dependency declarations,
lock importer/version metadata and CSS URL/import references, but did not audit
every transitive dependency or revalidate third-party vendor provenance upstream.
There are dormant KaTeX font references in the unchanged vendor stylesheet and
no imported KaTeX font tree; current pages do not depend on mathematical rendering,
so this is not a blocking current-route defect or reason to expand this import.

`git diff --check` for the reviewed main-to-source diff emitted no diagnostics.
Only this review document was written. No production source edits, local tests,
builds, package installs, push, dispatch, deploy, SMTP, tag, Release, DNS/provider
operation or shared primary worktree modification occurred.

Static test-string assertions are supplementary guards, not a proof of arbitrary
YAML semantics. Browser visual/accessibility behavior, hosted dependency resolution,
Astro-generated slugs and output, GitHub workflow/job registration, provider token
scope/environment approvals and live responses are not empirically verified here.
The unchanged baseline staging capability workflow was checked for preservation,
not certified for operation in the site-only checkout.

## Required next evidence

1. Commit this review if desired, push only the bounded branch, and record the
   actual `Candidate site CI` run, attempt, head SHA and exact successful job.
   A failed hosted check requires bounded correction and renewed evidence; this
   static GO must not be reported as test success.
2. Root-owned integration is separate. Once integrated, obtain successful
   `site-ci.yml` evidence for the precise new main SHA and confirm both manual
   workflow registrations. Branch evidence does not transfer to a new merge SHA.
3. Before any deploy, obtain explicit operator approval and freeze competing site
   writers and tag/Release publication. API reads and the site concurrency group
   cannot serialize tag creation, draft publication or dashboard operations.
4. Record live three-route acceptance, source/indexing headers, deployed Worker
   version and public DNS/HTTPS after any separately authorized deployment.
   Neither this review nor source CI constitutes Mail or public-release acceptance.

## Hosted syntax follow-up review

Reviewed the complete `f8a4772..d076efef` patch independently before the first
focused push. It adds a hosted actionlint step, corresponding static regression
strings and tooling provenance documentation; no new permission, environment,
secret or deployment path is introduced. The step downloads only the fixed
official Linux amd64 v1.7.11 archive to repository `.temp`, validates its SHA-256
before extracting/executing `actionlint`, and targets exactly the two site
workflow files. Shell failure/checksum failure is fail-closed (`set -euo pipefail`).

Read-only official release API retrieval using PowerShell `Invoke-RestMethod`
independently confirmed asset `actionlint_1.7.11_linux_amd64.tar.gz` has digest
`sha256:900919a84f2229bac68ca9cd4103ea297abc35e9689ebb842c6e34a3d1b01b0a`,
matching the source pin. No archive was downloaded or tool run locally.
`git diff --check f8a4772 d076efef` emitted no diagnostics. No substantive
follow-up issue was found; **GO remains limited to the focused push and hosted
source/syntax checks**. Actual hosted actionlint success must precede the
root-requested draft PR, and is not claimed by this static review.

## Primary references consulted

- [GitHub reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows): repository-relative same-commit calls and explicit secret passing.
- [GitHub manual workflow dispatch](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow): workflow must exist on the default branch for manual execution.
- [Cloudflare Static Assets headers](https://developers.cloudflare.com/workers/static-assets/headers/): generated asset-directory `_headers`, absolute HTTPS hostname rules and static-response applicability.
- [Cloudflare Custom Domains](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/): domain routing and provider-managed DNS/certificates.
- [Cloudflare Workers production best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/): platform-native design and explicit secret/state boundaries.
- [Official actionlint v1.7.11 release asset metadata](https://api.github.com/repos/rhysd/actionlint/releases/tags/v1.7.11): independently verified hosted-tool archive digest.

This is a bounded platform/contract review; speculative academic mechanisms are
not needed to resolve the concrete source-registration and publication risks.
