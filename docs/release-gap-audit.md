# v0.1.0 release-gap and cutover audit

Snapshot: 2026-09-29 04:31 UTC. This is a decision aid, not fresh acceptance evidence. It summarizes only unresolved gates from `product-audit.md`, `validation.md`, `staging-e2e-plan.md`, `staging-role-monitor-acceptance.md`, and `operations.md`. Do not rerun already-passed unit, cross-platform, staging-site, or five-target packaging checks without a failure affecting them. Do not copy private destinations, tokens, raw MIME, or account identifiers into release records.

## Current state and critical path

The public release is **not ready**. PR #1 is open on `codex/amail-v0.1.0` (observed HEAD `9feba94`), and its check set was still running at this snapshot; the staging role-monitor deploy check showed failure, while some staging jobs were pending. This is a transient check snapshot, not a final PR verdict. `gh release view v0.1.0` and the tag-ref lookup both returned not found. Direct workstation HTTPS probes did not reach either production HTTP host; the staging release-site root returned 200. Do not infer the exact production DNS or TLS fault from the HTTPS failure alone. The prior staging mail `/health` and staging site routes passed in documented Actions runs, but no authenticated SMTP-to-ZIP user journey has passed.

The dependency chain is:

```text
Identity authorization-resume fix in staging
  -> verified native CLI session on a hosted runner
  -> real staging address/rule + SMTP -> ZIP/search + cleanup
  -> separate outbound delivery/feedback and role-monitor acceptance
  -> reviewed PR merge and production Worker deployment, held initially
  -> production DNS/HTTPS and real delivery/cutover evidence
  -> controlled outbound gate attestations and global allowed state
  -> tag-only Release publish (archives, skill, checksums, attestations)
  -> public site deploy and links/content/HTTPS verification
```

Some branches can proceed in parallel, but no downstream pass substitutes for an upstream one. In particular, a green site build, `/health`, provider `202`, or Queue subscription cannot establish delivered mail.

## Prioritized unresolved gates

| Priority | Gate and current evidence | Next executable step / stopping rule |
| --- | --- | --- |
| P0 | **Staging native authorization is blocked.** One synthetic account was registered and verified, but the CLI's OAuth flow remained `authenticated`, not `completed`; `auth status` was false. The documented first-party Identity authorization-resume origin defect is outside this repository. | Deploy the generic Identity fix to staging, then retry **login only** for the same synthetic account. Do not re-register or inject tokens. A successful distinct-process `auth status` plus authenticated staging `address list` is the minimum authorization oracle. See `validation.md` and `staging-identity-flow.md`. |
| P0 | **Feature E2E has preparation, not a pass.** The manual `staging-e2e` job and SMTP-to-ZIP harness exist; no hosted run has completed. It covers one principal, address/rule, SMTP ingress, ZIP/asset, some search/mutation and cleanup, but not second-principal isolation, exact semantic cosine, outbound send, Queue feedback, or post-retirement SMTP rejection. | After Identity repair and protected synthetic credentials are ready, review the deployed staging SHA and launch `gh workflow run ci.yml --ref codex/amail-v0.1.0 -f target=staging-e2e -f confirm=RUN_STAGING_E2E`. Record the first failure and exact cleanup state in `validation.md`. Add separate bounded probes for isolation, semantic ranking/cursors, privacy/tracing, held-send/idempotency, one-use external delivery, feedback, and rejected retired alias. Keep sending held except the reviewed one-use canary. |
| P0 | **Abuse/role-mail release gate is incomplete.** Four exact production `abuse`/`postmaster` forwards had provider-reported delivery and owner-confirmed receipt, but messages landed in Junk; monitored response, lease behavior, and operational readiness were not established. `abuse_contact_verified` remains 0 and global send remains held. The current PR role-monitor staging deploy check was failing at the snapshot. | Resolve only the failing role-monitor deployment, then execute the isolated staging role-monitor acceptance and fault probes in `staging-role-monitor-acceptance.md` without repointing live production rules. Establish private destination Inbox/Junk monitoring and response ownership before production cutover. Do not flip attestations based on a synthetic SMTP acceptance or Cron configuration alone. |
| P0 | **Production mail and HTTP cutover have not occurred.** The production custom-domain HTTP probes failed locally; no production deployment or actual user-mail receive/send pass is recorded. Email Routing/Sending DNS onboarding is documented, but DNS record presence is not delivery. | After review/merge, manually dispatch `gh workflow run ci.yml --ref main -f target=production`, while keeping global send held. Require migrations, mail API, ingress and lifecycle consumer jobs to pass; verify authoritative and independent recursive DNS, HTTPS `/health`, the exact deployed Worker bindings, rule ownership, and a disposable production native-client SMTP→ZIP smoke. Check authentication results and a controlled outbound canary before any broad send enablement. Stop on orphan routes, wrong environment binding, unexpected send, or privacy leak. |
| P0 | **Release assets and public site are absent.** A candidate five-platform dry-run bundle and six matching digests passed earlier; there is no tag, published `v0.1.0` Release, or production site. `release.yml` intentionally requires production `/health`, `send_policy=allowed`, and four production D1 attestations before publication. `ci.yml` also refuses to deploy the site before all expected asset *names* exist. | Once the real production evidence justifies every attestation, dispatch `release.yml` on `main` for an exact merged-source dry run; inspect the bundle under repo `.temp`. Push the matching tag only after the outbound gate is truly met. Verify the tag job publishes five native archives, agent skill ZIP, `SHA256SUMS`, and attestations, then verify **downloaded bytes** against checksums/provenance; asset-name presence alone is not integrity proof. The tag workflow launches the public site only after publish and API health. Check `/`, `/manual/`, `/changelog/`, TOC anchors, CTA/manual links, indexability header and HTTPS on the production host. |
| P1 | **Source-level release UX is staged but not publicly verified.** Staging site three-route/TOC checks passed, and the static public page refers to a not-yet-published download. | Keep public deployment gated. After publication, check real link destinations and archive compatibility with at least one clean install per supported OS family, without treating the older candidate dry run as tagged-binary evidence. |

## Boundary and recovery decisions

1. Preserve exact-user contracts: native CLI authorization, ten-address/account limit, two reserved operational routes, ZIP-only content exchange, and exact search semantics. No web mailbox or unbounded routing promise is needed for v0.1.0. The selected bounded launch remains 198 user aliases per mail domain under the provider's [200-routing-rules-per-domain limit](https://developers.cloudflare.com/email-service/platform/limits/) (rechecked against official docs on 2026-09-29); monitor real capacity instead of inventing a catch-all.
2. Keep deployment and publication distinct. It is valid to deploy and smoke production mail Workers with public sending **held**, but not to publish a downloadable release/site while their user journey and abuse controls are unproved. The existing release gate encodes this; bypassing it would turn an operational unknown into a public promise.
3. Do not use a fresh idempotency key after an ambiguous provider send. Do not create a replacement alias to hide uncertain route deletion. Reconcile the exact run-owned rule and provider outcome before retrying. Preserve the first failed run in `validation.md` even when later attempts pass.
4. Before cutover, pin the reviewed commit, deployed Worker versions, domain bindings, D1/R2/Queue names, routing-rule IDs and current policy state in a restricted operator record. Public documentation should retain only redacted status, timestamps, counts, checksums, opaque trace IDs and links to Actions runs. If production promotion fails mid-sequence, leave send held, restore the prior Worker version/configuration where needed, and verify exact rules and prior mail delivery rather than blindly replaying migrations or SMTP.

## Evidence pointers

- `docs/validation.md`: observed staging deployment, synthetic registration, OAuth failure, production operational-role forwarding, and packaging dry run.
- `docs/staging-e2e-plan.md`: manual hosted command, coverage and missing feature probes.
- `docs/operations.md`: production dispatch, release ordering, release gate and live checklist.
- `.github/workflows/ci.yml` and `.github/workflows/release.yml`: executable promotion and publication contracts. `release-ready` checks asset names; `release.yml` checks production send-gate state and builds tagged assets.
- `docs/deployment-dns.md`: provider DNS onboarding and bounded literal-routing topology; record live DNS/delivery observations in `validation.md`, not as an inferred pass here.
