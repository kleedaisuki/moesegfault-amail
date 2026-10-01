# Workers tier and five-minute Cron release preflight

Date: 2026-10-01. Source context: Mail `7bcbbf98667ec92ac1f99e7ac4b8f3c94e6eceb5` (main after PR #19). This extends [full Cron budget review](mail-cron-budget-review-2026-10-01.md) and [routing budget](routing-reconcile-subrequest-budget.md). It is a bounded authenticated **read-only** provider probe and primary-document analysis, not a deployment, project test, build, limit-stress experiment, subscription change, or request for additional billing privileges.

## Decision

The account and actual staging Mail Worker both return `standard` usage-model labels. This is consistent with Workers Paid/Enterprise and is stronger evidence than successful deployment or a zone plan, but it is **not independently verified active subscription/tier evidence**. The public account-settings schema only describes an optional string; it does not promise that this value certifies current billing entitlement. The pricing page establishes Paid access to Standard, not a public reverse implication for every API state or contract.

The staging settings response omits `limits.cpu_ms`. **Omission is not an effective CPU budget measurement.** No actual Cron CPU usage, enforced D1 statement ceiling, Enterprise adjustment, or active Workers subscription has been observed. Paid-first source may be designed against the stricter published 1,000-D1/30-second short-interval Cron contract, but its live release precondition is not satisfied by these probes alone.

Do not request Billing scope just to remove this uncertainty, and do not run a synthetic limit-exhaustion experiment against the held live Mail Worker. The minimal next evidence is an accountable operator read of the exact account's Workers plan and exact Worker CPU settings in the Cloudflare Dashboard, recording only safe labels below. This decision is a release gate, not a reason to stop source implementation.

## Observed probe results

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

No Actions dispatch or workflow production modification is part of this investigation. If root later chooses a hosted settings read, require exact reviewed account/Worker, no redirects, bounded body, no raw body/error logging, and emit allowlisted labels only. It would confirm model/override metadata, not remove the subscription evidence requirement.

## Minimal accountable operator verification

One read-only Dashboard visit can combine the already-pending privacy setting verification with this bounded tier question; it must not change plan, limits or privacy settings implicitly.

1. Select the **same reviewed account** used for Mail deployment, not merely the `moesegfault.dev` zone.
2. Check the current **Workers subscription/plan** under Workers & Pages or account Billing/Subscriptions. Record `workers_plan=paid`, `free`, `enterprise`, or `unknown`; verify an active plan rather than inferring it from a Standard default. If Enterprise, obtain the applicable Cron/D1 contract without copying private billing documents into logs.
3. Open **amail-mail-staging > Settings > CPU Limits** and record the displayed configured value or `provider_default`; also check the production Worker when it actually exists. Keep environment-specific evidence separate. Do not change it as part of a read-only preflight.
4. Record reviewed `cron_interval_minutes=5`, `short_interval_cpu_ceiling_ms=30000` only if Paid/default applicability is established, and `d1_query_ceiling=1000` as the stricter documented Paid policy, not a measured ceiling. An override/custom contract requires a separate explicit decision; omission is `unknown` until applicability is verified.
5. Record `verified_by=operator` and a UTC timestamp. Do not ask for screenshots containing identifiers, billing amounts, payment details, account email or token values. A short structured confirmation suffices.

Safe audit labels: `workers_plan`, `worker_usage_model`, `cpu_limit_source`, `configured_cpu_ms`, `cron_interval_minutes`, `documented_short_interval_cpu_ms`, `documented_d1_queries`, `verification_method`, `verified_at_utc`. `unknown` or `permission_denied` must remain non-admitting outcomes. Never log full subscription/settings bodies, account IDs, credential scopes beyond explicitly selected non-sensitive permission labels, private contacts, or provider error text.

Once tier/settings are verified, the remaining CPU question is workload fit, not subscription discovery: use privacy-admitted hosted/deployed synthetic Cron evidence and the platform invocation CPU metric, while preserving the global D1 bound. A source binding-call counter alone cannot prove 30-second CPU fit, and no such live probe is authorized here.
