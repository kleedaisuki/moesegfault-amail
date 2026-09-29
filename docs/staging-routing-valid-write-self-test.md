# One-use staging Routing Rules Write self-test

Status: **design only; no rule created** (2026-09-29). This is a narrower control-plane diagnostic than an authenticated mailbox E2E. It tests the existing single GitHub `CF_EMAIL_ROUTING_TOKEN` with one *valid* staging rule, without registering a user address, using Mail/D1, or sending SMTP. It does not explain the three historical address-add failures. The existing [read-only policy probe](staging-routing-write-probe.md) verified that token as active but could not read its policy (separate reader got 403/9109). An invalid or empty POST is not an acceptable permission probe.

## Contract and ownership

Only `mail-staging.moesegfault.dev` under the known staging zone is in scope. Derive a 128-bit local-part nonce as the first 32 lowercase hexadecimal characters of `HMAC-SHA256(key=protected staging synthetic password, message="amail-routing-write-probe/v1:<GITHUB_RUN_ID>:<GITHUB_RUN_ATTEMPT>")`. The exact alias is `probe-<nonce>@mail-staging.moesegfault.dev`; the exact rule name is `amail probe <alias>`. The run ID and attempt are not secrets, but the password and derived alias must not appear in Actions logs or artifacts. The namespace prevents collisions with the normal E2E aliases. This deterministic derivation is primarily a **crash-recovery locator**; it does not grant permission to delete any rule sharing just the prefix.

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
| Quiet-window preflight | Pin staging zone/ingress target and reviewed checkout; rule out concurrent staging address/routing mutation. Read every unfiltered zone Rules page with `per_page=50`, consistent `page`, `count`, `per_page`, `total_count` and optional `total_pages`; reject pagination drift or malformed matcher/action structures. Check **both** exact alias matcher and exact rule name absent across the complete inventory, irrespective of enabled state. Count staging-domain literal rules and require a spare slot under Cloudflare's 200-rules-per-domain limit. | Any uncertainty, collision, or capacity exhaustion stops before POST. |
| One create | Issue exactly one `POST /zones/{staging_zone_id}/email/routing/rules` with the body above; never retry a timed-out or ambiguous POST. Bound response bytes/time. Record only fixed stage labels, numeric HTTP status, and first numeric Cloudflare error code, never response messages, URL, alias, rule ID, or token. | Non-2xx, `success=false`, malformed response, missing ID, timeout, or transport error does not authorize another POST. |
| Readback | Regardless of POST result, repeat complete Rules inventory (bounded stabilization reads if necessary). If exactly one rule has either the exact alias or name, require **both** to match, plus `enabled=false`, `source=api`, one exact literal matcher, one exact staging Worker action and a valid ID. Verify the same ID through [GET rule](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/get/) immediately before deletion. Multiple candidates, any mismatch, or incomplete readback freezes cleanup rather than guessing ownership. | A successful HTTP response without strict owned readback is **not** a passing Write test. An unknown POST outcome is resolved by readback, never by replay. |
| Cleanup | Delete only that freshly verified rule ID through the [Delete rule API](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/delete/). After an ambiguous DELETE, first read back; do not blindly replay. Require complete-inventory absence of both alias and name, then a separate delayed read-only audit so provider visibility lag cannot be mistaken for clean state. The guarded recovery target applies the same ownership and post-delete checks when `finally` never ran. | Missing/ambiguous cleanup, duplicate/mismatched rule, or audit failure freezes further creates and production promotion. |

The [List rule API](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/list/) documents page numbers and `per_page` from 5 to 50. The [Email Service limit](https://developers.cloudflare.com/email-service/platform/limits/) is 200 routing rules **per domain**. Full zone pagination is still required: filtering only enabled rules would miss the disabled probe, and filtering by a guessed rule name would not prove absence. A `GET`-then-`DELETE` check is not atomic; the quiet window, high-entropy run identifier, exact multi-field ownership check, and rule-ID verification reduce—not eliminate—the control-plane race. If any concurrent actor changes the candidate, do not delete.

## Result interpretation

| Observation | Supported conclusion | Not supported |
| --- | --- | --- |
| 200/201, `success=true`, exact disabled rule readback, and clean deletion/audit | The **GitHub job's** current token exercised effective Rules Write for one valid staging rule at that moment. | The deployed Mail Worker uses the same current token bytes/policy; enabled address registration, ingress, or historic failures are solved. |
| Numeric 403 or provider authorization code, no owned rule on complete readback | This **job request** was denied Write or another provider authorization condition at that time. | A specific policy clause, or the deployed Worker's independently injected secret, is known. |
| 400/409/429/5xx, `success=false`, malformed/timeout, or ambiguous readback | The provider operation did not yield a verified positive result; retain numeric diagnostics and exact-state audit. | Absence of Write permission, absence of a POST side effect, or a reason to retry. |
| Exact rule exists after unclear POST, strict ownership verified | POST may have succeeded; clean only this rule and report operation outcome indeterminate unless the original response itself passed. | The historical CLI add cause, or a passing probe based solely on existence. |

The normal staging deployment injects the **same named GitHub secret** into the Worker via `wrangler deploy --secrets-file`, but a hosted probe cannot read back the effective Worker secret or account for deployment drift, IP conditions, or runtime request behavior. After this diagnostic, an authenticated address-add E2E remains necessary; do not use this result to lift public sending or ship v0.1.0.
