# Workers tier and five-minute Cron release preflight

Date: 2026-10-01. Source context: Mail `7bcbbf98667ec92ac1f99e7ac4b8f3c94e6eceb5` (main after PR #19). This extends [full Cron budget review](mail-cron-budget-review-2026-10-01.md) and [routing budget](routing-reconcile-subrequest-budget.md). It records a historical bounded authenticated provider probe, primary-document analysis, and a subsequent operator attestation. None is a deployment, project test, build, limit-stress experiment, subscription change, or request for additional billing privileges.

## Decision

**Current status: operator-attested Paid/default staging.**

On **2026-10-01**, the operator confirmed in the task conversation that the Workers plan is **Paid** and that **amail-mail-staging > Settings > CPU Limits** displays **default**. Accept this as accountable operator attestation for the staging plan/settings precondition; do not describe it as an independent billing API verification, numeric runtime measurement, or permission to deploy. The earlier `standard` usage-model labels and omitted API `limits.cpu_ms` remain historical metadata, not the decisive tier evidence.

| Evidence label | Value | Basis / boundary |
| --- | --- | --- |
| `workers_plan` | `paid` | Operator confirmation of Workers plan, not zone plan inference. |
| `cpu_limit_source` | `provider_default` | Operator reports exact staging Dashboard setting as `default`. |
| `configured_cpu_ms` | `not_explicitly_configured` | No numeric override claimed by the operator; reviewed source config has no `cpu_ms`. |
| `cron_interval_minutes` | `5` | Both realms of `crates/mail-worker/wrangler.toml` at `13b2c284bae38e196a0d63c721675d007a3f790a` use `*/5 * * * *`. |
| `documented_short_interval_cpu_ms` | `30000` | Derived published Paid/default contract, **not measured CPU usage**. |
| `verification_method` | `operator_attestation` | Confirmation in task conversation; no new authenticated provider query. |
| `verified_on` | `2026-10-01` | Date supplied by task context; exact observation time / `verified_at_utc` was not supplied and must not be invented. |

The [Workers limits CPU table](https://developers.cloudflare.com/workers/platform/limits/#cpu-time), rechecked on 2026-10-01, gives Paid Cron with intervals below one hour **30 seconds of CPU time**. The [duration table](https://developers.cloudflare.com/workers/platform/limits/#duration) separately gives Cron **15 minutes of wall time**. Network/database waits do not count toward CPU time. Thus the five-minute staging Cron is evaluated against **30,000 ms CPU**, not 15 minutes CPU and not the higher general HTTP CPU maximum.

Static source inspection found no explicit `cpu_ms` in `crates/mail-worker/wrangler.toml`. Together with the operator's `default` report, there is no reason in this evidence to add an override or change the schedule. Production settings remain separately unverified: the shared source schedule does not attest a production Worker Dashboard value. Reverify applicability if the plan, Worker settings, source schedule, or published contract changes.

This resolves **staging plan/default applicability only**. Actual workload CPU fit, memory fit, enforced D1 statement ceiling, privacy/capture settings, Issues availability, deployment identity and serving state remain unproven by this attestation. The stricter documented D1 Paid policy remains 1,000 queries/invocation as discussed below; it is not a measurement of enforcement. Preserve the existing release/privacy holds and the global D1 admission policy. Do not request Billing scope or run a synthetic limit-exhaustion experiment to revisit a now-attested plan label.

## Historical decision before operator confirmation

The earlier provider probes alone did not satisfy the tier/settings precondition: `standard` usage labels were consistent with Paid/Enterprise but did not independently certify an active subscription, and omission of `limits.cpu_ms` was not an effective CPU budget measurement. The minimal next evidence then was the accountable Dashboard check now recorded above. No runtime CPU fit was established at either stage.

## Observed probe results

**Historical observations, before the operator confirmation above.**

Credential provenance: existing local Wrangler OAuth read in memory, never printed or persisted. Selected allowlisted scope labels were `account:read` and `workers:write`; no `billing:read` label was present. No GitHub Secret value was accessible or read. GET responses were reduced to the following safe fields, without raw provider errors, account identifiers, names, email addresses, bindings, token material, or billing details.

| Read | HTTP | API result | Safe extracted observation |
| --- | --- | --- | --- |
| `GET /accounts` | 200 | One account returned | Only count=1 exposed; its identifier used privately for later fixed requests. |
| `GET /accounts/{account_id}/workers/account-settings` | 200 | `success=true` | `default_usage_model=standard` |
| `GET /accounts/{account_id}/subscriptions` | 403 | No result interpreted | `subscription_read=permission_denied`; not evidence of Free or missing subscription. |
| `GET /accounts/{account_id}/workers/scripts/amail-mail-staging/settings` | 200 | `success=true` | `usage_model=standard`, `cpu_ms=omitted` |

Requests used Python standard-library HTTPS with a 30-second network timeout; no project tests or compiler/toolchain ran. The exploratory probe file remained under the isolated repository `.temp` worktree and contains no credentials or account identifiers. No further adaptive provider endpoints were probed after root instructed this investigation to stop.

## Primary-source contract and scopes

- [Workers account settings GET](https://developers.cloudflare.com/api/resources/workers/subresources/account_settings/methods/get/) returns optional `default_usage_model` and `green_compute`. Its accepted permissions include Workers Scripts Read/Write and Account Settings Read/Write. This endpoint is a plausible minimal hosted read using the existing deployment token, without adding Billing authority.
- [Account subscriptions GET](https://developers.cloudflare.com/api/resources/accounts/subresources/subscriptions/methods/get/) explicitly requires **Billing Read or Billing Write**. It includes prices, currency, renewal timestamps and rate-plan fields; raw subscription results should never enter Actions logs or an audit artifact. Existing local OAuth demonstrably cannot use it. GitHub token permissions cannot be established from Secret names alone.
- [Workers pricing](https://developers.cloudflare.com/workers/platform/pricing/) distinguishes the Workers subscription from the zone's Free/Pro/Business plan. Paid accounts can use Standard; Enterprise terms can differ. Changing account default usage model does not update existing Workers. Thus an account default alone is insufficient: read the exact Worker, too. The page also notes old Bundled migration could add an explicit 50-ms Worker limit.
- [Worker script settings GET](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/settings/methods/get/) is the existing fixed Worker metadata read. A provider-returned usage label is useful context, not an observed runtime stress result.
- [Workers limits](https://developers.cloudflare.com/workers/platform/limits/) lists CPU per Cron of **10 ms Free / 30 seconds Paid for intervals less than one hour**, versus 15 minutes Paid for intervals at least one hour. The same page lists **15 minutes wall time** per Cron invocation. These are different clocks; network wait does not consume CPU time. The source trigger is `*/5 * * * *` in both environments.
- [D1 limits](https://developers.cloudflare.com/d1/platform/limits/) still lists **50 queries/invocation Free / 1,000 Paid**. Use this stricter product-specific bound pending clarification; do not replace it with the larger generic internal-subrequest ceiling or assume `batch()` makes constituent statements disappear. Account tier evidence does not by itself measure actual enforcement or workload CPU fit.

### Existing GitHub token likelihood (not verified permission contents)

A Secret-name-only `gh secret list --repo kleedaisuki/moesegfault-amail` read confirms `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CF_OBSERVABILITY_TOKEN`, and `CF_EMAIL_ROUTING_TOKEN` exist. Their values and policy scopes were not retrieved. Prior deployment success makes `CLOUDFLARE_API_TOKEN` a reasonable candidate for Workers settings GET because that endpoint accepts Workers Scripts permissions; it does **not** establish Billing Read. Routing Rules/Addresses permissions are unrelated to subscriptions. Neither the role routing token nor the observability token should gain broad Billing permissions for this preflight.

No Actions dispatch or workflow production modification is part of this investigation. Any separately authorized future hosted settings read must use the exact reviewed account/Worker, no redirects, bounded body, no raw body/error logging, and allowlisted labels only. Such a read confirms model/override metadata, not an active subscription; staging subscription evidence is now supplied by the operator attestation above.

## Operator verification checklist for future revalidation

The staging plan/default labels have been attested above; do not treat this historical checklist as a still-missing request for those same labels. It remains applicable to changed settings and separately unverified production settings. A future Dashboard visit may also address the independent privacy setting gate, but the Paid/default confirmation does not satisfy that gate and must not change any settings implicitly.

1. Select the **same reviewed account** used for Mail deployment, not merely the `moesegfault.dev` zone.
2. Check the current **Workers subscription/plan** under Workers & Pages or account Billing/Subscriptions. Record `workers_plan=paid`, `free`, `enterprise`, or `unknown`; verify an active plan rather than inferring it from a Standard default. If Enterprise, obtain the applicable Cron/D1 contract without copying private billing documents into logs.
3. Open **amail-mail-staging > Settings > CPU Limits** and record the displayed configured value or `provider_default`; also check the production Worker when it actually exists. Keep environment-specific evidence separate. Do not change it as part of a read-only preflight.
4. Record reviewed `cron_interval_minutes=5`, `short_interval_cpu_ceiling_ms=30000` only if Paid/default applicability is established, and `d1_query_ceiling=1000` as the stricter documented Paid policy, not a measured ceiling. An override/custom contract requires a separate explicit decision; omission is `unknown` until applicability is verified.
5. Record `verified_by=operator` and a UTC timestamp. Do not ask for screenshots containing identifiers, billing amounts, payment details, account email or token values. A short structured confirmation suffices.

Safe audit labels: `workers_plan`, `worker_usage_model`, `cpu_limit_source`, `configured_cpu_ms`, `cron_interval_minutes`, `documented_short_interval_cpu_ms`, `documented_d1_queries`, `verification_method`, `verified_at_utc`. `unknown` or `permission_denied` must remain non-admitting outcomes. Never log full subscription/settings bodies, account IDs, credential scopes beyond explicitly selected non-sensitive permission labels, private contacts, or provider error text.

With staging tier/default applicability now operator-attested, the remaining staging CPU question is workload fit, not subscription discovery: use privacy-admitted hosted/deployed synthetic Cron evidence and the platform invocation CPU metric, while preserving the global D1 bound. A source binding-call counter alone cannot prove 30-second CPU fit, and no such live probe is authorized here.
