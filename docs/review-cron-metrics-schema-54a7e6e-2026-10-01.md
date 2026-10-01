# Independent review: fixed Cron metrics schema discriminator

Date: 2026-10-01.
Reviewed candidate: `54a7e6ecc1158b8c6801e50060d447222d50e467`.
Reviewed main base (candidate parent): `13b2c284bae38e196a0d63c721675d007a3f790a`.
Reviewer scope: the four-file, 431-insertion candidate diff and relevant callers,
workflow-source extractor, existing workflow lint, and internal contracts.

## Decision

**GO for source integration / hosted synthetic validation. No substantive
source-level blocker found.** This is not approval to dispatch a provider read,
deploy Mail, admit Cron runtime resources, or relax the Issues/privacy gate.
Hosted synthetic contracts and workflow syntax validation must pass before a
separately authorized main/staging schema read. No passing hosted result is
claimed by this review.

## Knowledge reused

Selected by filename before reading: `cron-runtime-observation-gate-2026-10-01.md`,
`workers-tier-cron-preflight-2026-10-01.md`,
`hosted-infra-fast-feedback-design.md`,
`private-provider-offline-graphql-classifier-research-2026-10-01.md`, and
`review-staging-fourth-invocation-metrics.md`. These establish that CPU fit is
unmeasured, provider text must not escape, workflow-only fast feedback does not
replace source acceptance, and GraphQL/schema success must not imply runtime,
permission, privacy or release acceptance.

## Verified source paths

| Contract | Evidence and assessment |
| --- | --- |
| PR without provider credentials | Workflow `contracts` job uses only contents:read, no Environment, no secrets, no provider invocation; checkout persists no credentials. `pull_request`, not `pull_request_target`. |
| Exact guarded manual read | `schema` needs successful contracts; job predicate requires workflow_dispatch, refs/heads/main and exact READ_CRON_METRICS_SCHEMA; staging Environment and isolated concurrency; token only in final invocation step. No user-controlled shell interpolation. |
| Least credential exposure | Only CF_OBSERVABILITY_TOKEN is referenced. No deployment/account/routing/Billing token, account ID, scope expansion, write permission or artifact upload. Actual secret policy was not inspected: a secret name does not prove its permissions. |
| Query scope | probe lines 17-30 construct exactly eight fixed __type aliases with type name, kind and member name only. No viewer/accounts, dataset records, variables, descriptions, logs, mutation, fallback or discovery traversal. |
| Transport | lines 91-104: one fixed HTTPS POST; NoRedirect rejects redirect traversal; no explicit retry; HTTP 200 required; read at most 262145 bytes and reject above 262144; 20-second blocking-operation timeout; schema job capped at two minutes. |
| Closed parsing | lines 46-88 reject duplicate JSON keys, nonstandard constants, GraphQL errors, partial/extra aliases, wrong identity/kind, malformed member rows, duplicate names and >500 members/type. Every alias is validated before any output. |
| Safe output | Only static selected keys and present/absent/unavailable values escape. Valid unknown names are discarded. Null type is unavailable rather than absent. All successful classifications end with admission UNVERIFIED, no runtime measurement and unchanged Issues privacy gate. |
| Error confidentiality | main catches ordinary transport/JSON/schema failures; only closed reasons or internal are printed. Provider HTTP/error text, raw body, dynamic identifiers, token, traceback and arbitrary exception arguments are never formatted. |
| Compatibility and destructive surface | New independent workflow/probe/tests/docs only; no existing CI/deploy job or Mail runtime changed. No workload generation, account dataset read, provider mutation, dispatch, push or PR is present in this candidate. |

## Complexity challenge

431 lines are **131 probe + 108 tests + 62 workflow + 130 documentation**, not a
431-line runtime observer. One declarative TYPES table drives both query and
projection; a null-type rule replaces eight special cases. The implementation
has no dependency installation for the probe, generic query framework, registry,
configuration parser, retry state, adaptive query engine or admission thresholds.
A substantially shorter curl/JSON-print script would lose bounded parsing,
redirect refusal and closed error projection. Those are real privacy contracts,
not theoretical edge-case machinery. The separate workflow avoids modifying
existing deployment orchestration and keeps PR checks credential-free.

The synthetic fixture uses the production TYPES table, so its all-present case
checks projection mechanics, not independent truth of Cloudflare's type names.
This is appropriate only because names are explicitly hypotheses and null types
remain unavailable. Actual type visibility, metric units, event filter semantics,
version attribution and runtime access remain future evidence. No arbitrary
CPU/wall/memory headroom or metric thresholds were introduced.

## Non-blocking limitations / optional hardening

1. `actions/setup-python@v5` is tag-pinned, unlike checkout's full SHA. Pinning its
   reviewed release to a full commit would improve reproducibility and supply-chain
   control, particularly in the secret job. This is an existing ecosystem trust
   choice, not a demonstrated defect in this candidate.
2. The 20-second urllib timeout is for blocking operations, not an end-to-end
   deadline; a dribbling response can outlast it. The hosted two-minute job
   timeout supplies the overall operational bound. A future standalone use must
   not claim a strict 20-second total deadline. No custom timer is necessary for
   the current hosted-only execution contract.
3. Tests mock the opener and directly exercise redirect_request; they do not
   reproduce a complete urllib redirect/HTTPError lifecycle. Additional synthetic
   HTTPError(401/403) and redirect integration fixtures would strengthen evidence,
   but inspected executable paths already map to fixed safe failure reasons.
4. Schema fields() omits deprecated fields by GraphQL default. Membership is of
   the queried visible shape, not a historical inventory. A negative bin is not
   proof that a concept never existed. This does not create runtime admission.

## External reality check

Primary public documentation retrieved on 2026-10-01; no authenticated API call:

- [Cloudflare introspection](https://developers.cloudflare.com/analytics/graphql-api/features/discovery/introspection/)
  distinguishes dynamic schema discovery from user-specific dataset availability.
- [Cloudflare Analytics token](https://developers.cloudflare.com/analytics/graphql-api/getting-started/authentication/api-token-auth/)
  supports a dedicated analytics credential; this review did not verify the
  stored token policy or request broader scopes.
- [GraphQL specification, __Type](https://spec.graphql.org/October2021/#sec-The-__Type-Type)
  defines type/member introspection, including default exclusion of deprecated
  fields. Name-only metadata is deliberately weaker than type/unit validation.
- [GitHub secure use](https://docs.github.com/en/actions/reference/security/secure-use)
  recommends minimal permissions and immutable action SHAs; setup-python pinning
  is an optional concrete improvement, not a reason to grow the observer.
- [Python 3.12 urllib.request](https://docs.python.org/3.12/library/urllib.request.html)
  documents blocking-operation timeout semantics.
- [ServiceLab, OSDI 2024](https://www.usenix.org/conference/osdi24/presentation/chow)
  is relevant to the later repeated controlled performance-observation problem.
  Its experimental capability is not inherited by this schema discriminator.

## Verification performed and explicitly excluded

Performed source and diff inspection, primary public-document retrieval, and
`git diff HEAD^ HEAD --check` (passed). Candidate/base SHAs were resolved locally.
No local project test, build, YAML parser execution, authenticated provider call,
credential read, mail operation, push, PR, workflow dispatch or source edit was
performed. The review artifact was initially an untracked file in the implementation
worktree; it was copied to the new isolated review worktree
`.temp/cron-metrics-schema-independent-review` for a single-file review commit.
The original untracked duplicate is left for the implementation owner to remove after coordination; no implementation branch commit or source modification occurred. No live schema, token permission, metric values, workload coverage, privacy setting or hosted test outcome was verified. Root retains authorization and integration decisions.
