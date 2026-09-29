# One-use staging Routing Rules Write self-test

Status: **design only; no rule created** (2026-09-29). This is a narrower control-plane diagnostic than an authenticated mailbox E2E. It tests the existing single GitHub `CF_EMAIL_ROUTING_TOKEN` with one *valid* staging rule, without registering a user address, using Mail/D1, or sending SMTP. It does not explain the three historical address-add failures. The existing [read-only policy probe](staging-routing-write-probe.md) verified that token as active but could not read its policy (separate reader got 403/9109). An invalid or empty POST is not an acceptable permission probe.

## Contract and ownership

Only `mail-staging.moesegfault.dev` under the known staging zone (`CF_ZONE_ID=6edff81c6ed02f412e70868076411a5e`) is in scope; reject a mismatched zone setting rather than using it. Derive a 128-bit local-part nonce as the first 32 lowercase hexadecimal characters of `HMAC-SHA256(key=protected staging synthetic password, message="amail-routing-write-probe/v1:<GITHUB_RUN_ID>:<GITHUB_RUN_ATTEMPT>")`. The exact alias is `probe-<nonce>@mail-staging.moesegfault.dev`; the exact rule name is `amail probe <alias>`. The run ID and attempt are not secrets, but the password and derived alias must not appear in Actions logs or artifacts. The namespace prevents collisions with the normal E2E aliases. This deterministic derivation is primarily a **crash-recovery locator**; it does not grant permission to delete any rule sharing just the prefix.

The single authorized create request uses the [Cloudflare Create rule API](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/create/) with the same *real* Worker action and literal matcher schema as `crates/mail-worker/src/platform.rs::create_rule`, except `enabled=false` so it cannot receive mail while present:

```json
{
  "name": "amail probe <exact derived alias>",
  "enabled": false,
  "source": "api",
  "actions": [{"type": "worker", "value": ["amail-inbound-staging"]}],
  "matchers": [{"type": "literal", "field": "to", "value": "<exact derived alias>"}]
}
```

The action references the real staging ingress Worker; it is not a dummy rule. The rule is intentionally disabled, so a positive result proves creation of this *valid disabled rule*, not that provider delivery, the Mail Worker endpoint, or enabled-rule behavior works. No production or reserved-role address/rule may be touched.

## Required executable preflight, mutation, and recovery

| Phase | Required behavior | Fail-closed result |
| --- | --- | --- |
| Pre-implementation | Land and hosted-test both the one-shot probe and a **separate guarded manual recovery target**. The recovery target takes the original run ID/attempt, reconstructs the alias from the protected password, and only reads/deletes that exact run-owned rule. A `finally` block alone is insufficient if a runner is cancelled. | No live POST until executable recovery is present. |
| Quiet-window preflight | Pin staging zone/ingress target and reviewed checkout; share a GitHub Actions concurrency group with the staging E2E and establish an operator quiet window for out-of-band mutations. Read every unfiltered zone Rules page with `per_page=50`, consistent `page`, `count`, `per_page`, `total_count` and optional `total_pages`; reject pagination drift or malformed matcher/action structures. Check **both** exact alias matcher and exact rule name absent across the complete inventory, irrespective of enabled state. Count staging-domain literal rules and require a spare slot under Cloudflare's 200-rules-per-domain limit. | Any uncertainty, collision, or capacity exhaustion stops before POST. |
| One create | Issue exactly one `POST /zones/{staging_zone_id}/email/routing/rules` with the body above; never retry a timed-out or ambiguous POST. Bound response bytes/time. Record only fixed stage labels, numeric HTTP status, and first numeric Cloudflare error code, never response messages, URL, alias, rule ID, or token. | Non-2xx, `success=false`, malformed response, missing ID, timeout, or transport error does not authorize another POST. |
| Readback | Regardless of POST result, repeat complete Rules inventory (bounded stabilization reads if necessary). If exactly one rule has either the exact alias or name, require **both** to match, plus `enabled=false`, `source=api`, one exact literal matcher, one exact staging Worker action and a valid ID. If POST returned a trustworthy ID, it **must equal** the complete-list ID. Verify the same ID through [GET rule](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/get/) immediately before deletion. Multiple candidates, a POST/list ID mismatch, any other contradiction, or incomplete readback freezes cleanup rather than guessing ownership. | A successful HTTP response without strict owned readback is **not** a passing Write test. An unknown POST outcome is resolved by readback, never by replay. |
| Cleanup | Delete only the ID consistent across POST (when known), complete list, and GET-by-ID through the [Delete rule API](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/delete/). After an ambiguous DELETE, first read back; do not blindly replay. Require complete-inventory absence of both alias and name, then use a **separately dispatched read-only audit target** with the original run coordinates after a delay, so provider visibility lag cannot be mistaken for clean state. The guarded recovery target is for cancellation/unknown POST **without a conflicting known ID**, or after separate controlled operator evidence resolves a contradiction; it is not a universal fallback for failed cleanup. | Missing/ambiguous cleanup, duplicate/mismatched rule, or audit failure freezes further creates and production promotion. |

The [List rule API](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/list/) documents page numbers and `per_page` from 5 to 50. The [Email Service limit](https://developers.cloudflare.com/email-service/platform/limits/) is 200 routing rules **per domain**. Full zone pagination is still required: filtering only enabled rules would miss the disabled probe, and filtering by a guessed rule name would not prove absence. A `GET`-then-`DELETE` check is not atomic; the quiet window, high-entropy run identifier, exact multi-field ownership check, and rule-ID verification reduce—not eliminate—the control-plane race. If any concurrent actor changes the candidate, do not delete.

## Manual hosted runbook: three gates, no retry loop

These invocations match `.github/workflows/ci.yml` and `infra/provider/probe_routing_effective_write.py`. They must run from the same reviewed branch/ref after its GitHub-hosted infrastructure tests pass. The three ordinary invocations are **recovery-on-absent rehearsal → one live probe → delayed independent audit**. The `staging` Environment supplies `STAGING_E2E_PASSWORD` and the existing single `CF_EMAIL_ROUTING_TOKEN`; neither is a command argument. **Freeze `STAGING_E2E_PASSWORD` from before the probe through any recovery and the delayed audit**: it is the HMAC key for locating the original alias, so changing it makes the script inspect a *different* address and can yield a false `absent`. If the secret was rotated or its continuity cannot be established, do not run or trust automated recovery/audit; freeze further creates and use controlled private evidence to locate the original exact rule, then review an ID-proven cleanup and independent audit. Do not guess the alias, restore/expose the old secret in logs, or treat an audit of a newly derived alias as proof of cleanliness. Keep the common `staging-native-mail-acceptance` concurrency group idle, stop other staging route writers, and verify the staging Worker/zone and remaining route capacity before the live step. Do not run an old workflow revision after reviewing a newer script.

1. **Prove the interruption-recovery target is executable before any live POST.** Use arbitrary valid coordinates deliberately unrelated to a real probe; the high-entropy HMAC alias must be absent. This is a `recover` dispatch, but its expected branch performs only complete Rules GETs and no DELETE:

   ```powershell
   gh workflow run ci.yml --ref codex/amail-v0.1.0 -f target=staging-routing-write-recover -f confirm=RECOVER_ONE_STAGING_ROUTING_PROBE -f routing_probe_run_id=999999999999999999 -f routing_probe_attempt=1
   ```

   Require a successful hosted conclusion and exactly `routing_write_recovery=absent`. A failed/uncertain job or an unexpected `removed` is a stop condition; inspect only the fixed labels, not raw Cloudflare bodies. This rehearsal proves wiring and absent-path logic, **not** that deletion will succeed after a crash. Hosted synthetic tests must independently cover the strict owned-delete path before step 2.

2. **Create at most one run-owned disabled rule.** After independently confirming quiet-window and live preflight gates, dispatch once:

   ```powershell
   gh workflow run ci.yml --ref codex/amail-v0.1.0 -f target=staging-routing-write-probe -f confirm=CREATE_ONE_DISABLED_STAGING_ROUTING_PROBE
   ```

   Record the exact Actions **probe run ID, attempt, checkout SHA, and job URL** from that dispatch, without the derived alias or rule ID. Do not use `gh run rerun`: a new attempt derives a different alias and would be a second write experiment. The only positive immediate outcome is `routing_write_probe=created` with `routing_write_cleanup=removed`; even that is provisional until step 3. Rejection, ambiguous create, cleanup failure, cancellation, or missing output freezes further creates. **Do not automatically invoke alias-only recovery merely because cleanup is not conclusively absent.** If the runner was cancelled or POST outcome is unknown **and no contradictory known ID exists**, the guarded `staging-routing-write-recover` target may be dispatched with the original probe run ID/attempt; it may delete only an exact, single owned disabled rule. If POST returned ID B but list/GET shows ID A, or a denied POST conflicts with a candidate rule, `create_id_mismatch`/other contradiction forbids both automatic cleanup and alias-only recovery. Freeze, gather controlled provider evidence privately, and authorize a specifically ID-proven resolution before any deletion. A `recovery_ownership_unverified` or inconclusive readback likewise requires operator investigation, not a broader delete or another POST.

3. **Audit later in a separate read-only job.** Wait at least 60 seconds after the probe or recovery job finishes. Use the **original probe run ID/attempt**, not the audit job's new coordinates:

   ```powershell
   gh workflow run ci.yml --ref codex/amail-v0.1.0 -f target=staging-routing-write-audit -f confirm=AUDIT_ONE_STAGING_ROUTING_PROBE -f routing_probe_run_id=<original probe run ID> -f routing_probe_attempt=<original attempt>
   ```

   Require hosted success with `routing_write_audit=absent`. `present`, a failed inventory, or an unavailable job keeps the probe unclean and freezes further creates. Use the guarded original-coordinate recovery path only for an unknown/cancelled POST **without** conflicting known ID, or after controlled operator evidence resolves any contradiction; then dispatch another separate delayed audit. The audit sends only Rules GETs. Preserve the run URLs, fixed result labels, numeric HTTP/provider codes and timing in `docs/validation.md`; never retain raw responses, secret values, derived aliases, rule IDs, or mail content in Actions logs/artifacts. Do not add shell tracing or print child-process stderr.

## Result interpretation

| Observation | Supported conclusion | Not supported |
| --- | --- | --- |
| 200/201, `success=true`, exact disabled rule readback, and clean deletion/audit | The **GitHub job's** current token exercised effective Rules Write for one valid staging rule at that moment. | The deployed Mail Worker uses the same current token bytes/policy; enabled address registration, ingress, or historic failures are solved. |
| Numeric 403 or provider authorization code, no owned rule on complete readback | This **job request** was denied Write or another provider authorization condition at that time. | A specific policy clause, or the deployed Worker's independently injected secret, is known. |
| 400/409/429/5xx, `success=false`, malformed/timeout, or ambiguous readback | The provider operation did not yield a verified positive result; retain numeric diagnostics and exact-state audit. | Absence of Write permission, absence of a POST side effect, or a reason to retry. |
| Exact rule exists after unclear POST, strict ownership verified | POST may have succeeded; clean only this rule and report operation outcome indeterminate unless the original response itself passed. | The historical CLI add cause, or a passing probe based solely on existence. |

The normal staging deployment injects the **same named GitHub secret** into the Worker via `wrangler deploy --secrets-file`, but a hosted probe cannot read back the effective Worker secret or account for deployment drift, IP conditions, or runtime request behavior. After this diagnostic, an authenticated address-add E2E remains necessary; do not use this result to lift public sending or ship v0.1.0.
