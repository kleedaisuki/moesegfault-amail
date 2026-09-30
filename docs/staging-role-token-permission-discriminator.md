# Staging role Routing token permission discriminator

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
must execute these tests before a manual provider probe. No live provider
request has been made by this implementation or its synthetic tests.
