# One-run hosted alias reconciliation

The hosted native staging E2E constructs an address from the protected
`STAGING_E2E_PASSWORD`, `github.run_id`, and `github.run_attempt` using its v1
HMAC contract. The manual `staging-hosted-alias-reconcile` workflow checks one
**completed** run's exact address after E2E cleanup, without printing or
accepting that address as an input. This is a cleanup gate, not an address
registration, routing-permission, or SMTP delivery test.

From the GitHub Actions run page, record the E2E run ID and attempt. Dispatch
`CI and deploy` with target `staging-hosted-alias-reconcile`, confirmation
`READ_ONE_STAGING_ALIAS`, `alias_run_id` set to that run ID, and `alias_attempt`
set to its run attempt. Never infer the attempt from a retry count or use a
different E2E run's ID. Only protected staging secrets are read, in the final
step. The job has no mutation command or write-scoped GitHub permission.

The implementation reuses the prior-alias reconciliation's exhaustive Email
Routing Rules pagination and one parameterized staging D1 `SELECT`. The D1
control-plane API uses HTTP POST to execute this read-only query. A clean gate
requires **both** an absent exact literal `to` rule and either an absent D1
row or a `retired` row with null Cloudflare rule ID, zero
`needs_reconcile`, and the staging issuer. Incomplete pagination, malformed
responses, missing credentials, and other read failures remain `unverified`;
a known route or unreconciled row is `not_clean`. Output is limited to fixed
`hosted_alias_route`, `hosted_alias_row`, and `hosted_alias_gate` labels.

The job cannot prove that a different alias is clean, that the supplied run
metadata belongs to an E2E workflow, or that an absent row was previously
registered. The operator must use actual run metadata; the test only verifies
the exact derived address. A passing result is not evidence of production
readiness or permission to repeat a failed address registration.
