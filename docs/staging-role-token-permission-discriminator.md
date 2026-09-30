# Staging role Routing token permission discriminator

## Least-privilege decision update (2026-10-01)

**Keep the existing single repository-level `CF_EMAIL_ROUTING_TOKEN`.** The
documented remedy is an additional **Account > Email Routing Addresses > Read**
grant scoped to the one Cloudflare account that owns this zone, while preserving
the existing zone-specific Routing Rules grants. Do not create a second token,
move the secret to an environment, grant Addresses Edit/Write, or add token
administration permissions to the runtime credential.

### Why this is a separate permission boundary

Cloudflare's [destination-list API](https://developers.cloudflare.com/api/resources/email_routing/subresources/addresses/methods/list/)
is account-scoped, and accepts `Email Routing Addresses Read` or Write. Its
[permission catalogue](https://developers.cloudflare.com/fundamentals/api/reference/permissions/)
classifies Addresses Read under account permissions, separately from zone
Routing Rules permissions. Thus the observed accessible Rules / forbidden
Addresses split is compatible with a missing account grant or an incorrect
account resource selection. It does not identify the token policy: the probe
does not inspect policy, and an HTTP 403 alone is not proof of a specific missing
permission. Check the resource account, token status/conditions and creator's
effective account access before claiming a confirmed scope defect. No new live
request was made for this update.

The Rust source makes this boundary consequential: `run_monitor()` in
`workers/role-monitor/src/lib.rs` runs `flush_alerts()`, then
`audit_destination()`, then `audit_rules()`, before `check_and_renew()`.
`audit_destination()` uses the same routing secret, reads the account Addresses
inventory, requires exactly one case-insensitive private-secret match and a
nonempty provider `verified` field, and fails on non-200 or pagination drift.
The current split would therefore prevent lease renewal **if the deployed
Worker uses the same current token and this implementation**; that conditional
source inference must not be presented as the cause of the historical SMTP
timeout. A digest accepted before the audit is not a successful health run.

### Alternatives that do not resolve the evidence requirement

| Alternative | Decision |
| --- | --- |
| GET one known destination ID rather than listing addresses | Cloudflare's [destination-detail API](https://developers.cloudflare.com/api/resources/email_routing/subresources/addresses/methods/get/) requires the same Addresses permission. This could reduce response data in a future design, but cannot bypass this 403; no protected ID is currently part of the contract. |
| Trust the four direct forwards or earlier successful delivery forever | They do not prove that the destination remains provider-verified now; do not weaken the health audit to turn a permission failure into a lease. |
| Use a broad deployment credential or give the routing token API Tokens Write | Reject: it increases credential authority rather than granting the specific read capability. |

Account-scoped Read can expose other registered destination addresses in that
account to the credential. The documented scope is not a per-mailbox ACL. The
existing strict in-memory match and fixed public labels remain necessary;
neither raw inventory nor the confidential destination belongs in logs or this
document.

### One bounded next step, after a real policy change

Have the existing token's authorized owner privately inspect and, if needed,
**edit that same token's policy** with the account-only Read grant above. Preserve
other policies, selected resources, status, expiry and client-IP restrictions;
do not roll its value merely to edit permissions. Cloudflare exposes
[Update Token](https://developers.cloudflare.com/api/resources/user/subresources/tokens/methods/update/)
for an existing token, requiring API Tokens Write on the *administration*
credential; that is not a reason to grant it to this application token. Use the
appropriate owner/dashboard or account-owned-token administration path, not a
speculative self-escalation call. This investigation does not establish that an
available automation credential can administer the owner's token.

After the policy is corrected, run the **existing** bounded GET-only
`staging-role-token-phase-probe` once with the current serving-role version pin
and the same repository secret. That is new evidence after a changed condition,
not an unchanged replay. Require accessible Addresses, exactly one verified
private match and preserved rules/version; if it still returns forbidden, stop
and reconcile the effective token/account policy instead of looping. A pass
only removes this current capability blocker: deployed-secret parity, natural
Cron health/lease, private Inbox/Junk notice, the shared-sink privacy gate and
production acceptance remain separate. No SMTP, token mutation, deployment,
local test or private-address disclosure was performed by this decision update.

## First live read-only result (2026-09-30)

[Manual run 36676551506](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36676551506) on source `da86b13` reported the fixed labels `role_token_addresses=forbidden`, `role_token_rules=accessible`, `role_token_destination=not_checked`, `role_token_standard_rules=four_direct`, `role_token_disposable_route=absent`, `role_token_worker_version=match`, and `role_token_probe=inconclusive`. The same repository routing token can currently read zone Routing Rules but cannot read account destination addresses. The destination could not be checked because its inventory GET was forbidden; `four_direct` describes the current rule shape, not successful delivery or verification of the confidential destination.

This **current permission split** makes an account Addresses-read scope defect actionable to investigate. It does not prove that the token had the same permissions during historical SMTP run `36603362864`, nor does it establish that the historical Cron stopped in `audit_destination`: the token or deployed secret could have changed, and no historical phase log was observed by this probe. It also provides no destination Inbox/Junk evidence. Keep public sending held; resolve the historical phase with the separately scoped fixed-phase log oracle rather than replaying SMTP or treating this read-only result as acceptance.

## Scope and invocation

The first guarded role SMTP run, `36603362864`, failed machine-side acceptance;
the later read-only aggregate audit, `36670688163`, found one accepted forward and
one marked digest but no persisted probe-window health check or renewed lease.
This manual discriminator answers a narrower **current-state** question: can the
same GitHub `CF_EMAIL_ROUTING_TOKEN` secret that staging role deployment uses
read both account Email Routing destination addresses and zone Routing Rules,
and does exactly one provider-verified address equal the private Worker
`ROLE_FORWARD_DESTINATION` secret? It also checks that four standard role
rules still forward directly to that destination, the disposable probe rule is
absent, and the supplied staging role Worker version is the current sole
100%-serving version. This does not prove which token bytes or permissions were
deployed during the historical SMTP run; a secret may have rotated. It cannot
by itself identify the historical Cron failure phase or attest Inbox delivery.

Dispatch only from the reviewed branch through `ci.yml` with
`target=staging-role-token-phase-probe`,
`confirm=READ_FIRST_ROLE_TOKEN_PERMISSIONS`,
`role_probe_run_id=36603362864`, and
`role_version=<current staging role Worker version UUID>`. The exact-run gate
runs before any secret-bearing step. The final step alone receives the routing
token, API token, account ID, version pin, and private destination. No SMTP,
Worker deployment, route mutation, D1 write, or retained-log query occurs.

## Interpretation

The script issues only GETs. It uses bounded complete pagination for account
`/email/routing/addresses` and zone `/email/routing/rules`; a shifted or
truncated inventory is `invalid_response`, not an inferred absence. Every
provider read rejects HTTP redirects without forwarding a bearer. Only fixed
status labels enter the Actions log:

| Label | Meaning |
| --- | --- |
| `role_token_addresses=accessible|forbidden|unauthorized|redirect|unavailable|invalid_response` | Current account Addresses GET capability and inventory quality. |
| `role_token_rules=...` | Independent current zone Rules GET capability and inventory quality. |
| `role_token_destination=verified|missing|pending|duplicate|invalid|not_checked` | Exact private-secret match against one provider-verified address; no address printed. |
| `role_token_standard_rules=four_direct|incomplete|contract_mismatch|not_checked` | Four present enabled API-owned direct forwards to the same secret destination. |
| `role_token_disposable_route=absent|present|invalid|not_checked` | Current disposable staging rule state. |
| `role_token_worker_version=match|drift|unavailable` | Current single 100%-serving deployment against the private UUID pin. |
| `role_token_probe=read_only_pass|inconclusive` | Pass requires all six preceding conditions. |

A `forbidden` Addresses result with accessible Rules identifies a **current
permission split** and is actionable for token scope review. It is not proof
that this split existed during `36603362864`. Likewise a `read_only_pass`
rules out the current split but not a historical transient, Cron exception, or
missing retained phase. The historical phase cause still needs a separate
privacy-reviewed fixed-phase application-log oracle. Keep the public send
gate held; do not replay SMTP on the strength of this probe.

## Verification contract

`infra/tests/test_staging_role_token_phase_probe.py` supplies synthetic 200,
independent 403, redirect, missing/pending/duplicate, rule-mismatch, truncated
page, and version-drift cases, plus workflow secret-scope assertions. Hosted CI
must execute these tests before a manual provider probe. The synthetic tests
make no live provider request; the first separately guarded live GET result is
recorded above.
