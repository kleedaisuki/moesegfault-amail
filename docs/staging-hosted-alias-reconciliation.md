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

The gate is a **point-in-time** cleanup check, not a promise that a dirty row
will remain dirty. An address delete can race in-flight provisioning and leave
the D1 row `deleting`; the five-minute staging Cron in
`crates/mail-worker/wrangler.toml` runs `reconcile_addresses` to retire it and
later clear `needs_reconcile`. A `not_clean` result after the E2E cleanup
therefore freezes new creation and warrants a later **read of the same run and
attempt**, not an alternate alias or a manual rule/D1 mutation. Conversely,
`not_clean` alone does not identify the row state, and a later `clean` result
does not diagnose why registration failed. The 2026-09-29 run-specific evidence
is recorded in [`validation.md`](validation.md#third-hosted-address-add-failure-and-delayed-exact-alias-reconciliation).

## Fifth hosted inbound attempt: delayed exact cleanup gate

The fifth hosted E2E [run 36589042183, attempt 1](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36589042183) at source `0e6064eafb8e98f73b7e58c20e037733948847ed` reached `address_and_literal_route_verified` and `smtp_submitted`, then reported `address_add_primary:sync_failed_http_409_unknown_code` and `address_add_cleanup:message_cleanup_failed`. These are fixed harness labels: SMTP submission is not proof of delivery, and the unknown-code label does not disclose the underlying API error code. In `infra/tests/staging_mail_e2e.py::cleanup_run`, a failed message sync does not prevent the independent address-retirement attempt or the route/address-absence polling. Conversely, `message_cleanup_failed` does not prove that test messages were removed.

The first exact, read-only [reconciliation run 36589786011](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36589786011), completed at 15:23:31 UTC on 2026-09-29, reported `hosted_alias_route:absent`, `hosted_alias_row:not_clean`, and `hosted_alias_gate:not_clean`. This proves only that no exact literal route was seen and that the exact D1 row failed the conservative clean predicate at that read. It does not identify the row state or the cause of the sync failure. At that point, new address creation was frozen pending a delayed read of **the same run and attempt** after the five-minute Cron interval; no alternate alias or manual route/D1 mutation was justified by this result.

The delayed, same-run [reconciliation run 36590503290](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36590503290) was dispatched after the five-minute interval. At 15:29:04 UTC it reported `hosted_alias_route:absent`, `hosted_alias_row:clean`, and `hosted_alias_gate:clean`. Thus this exact alias met the point-in-time route-and-D1 cleanup gate without a manual mutation. The change from `not_clean` to `clean` is compatible with asynchronous reconciliation, but the fixed labels do not establish the intermediate row state or prove Cron causality. It does not reverse the E2E failure or establish message cleanup, mailbox delivery, or the cause of the HTTP 409.
