# Review: historical staging alias reconciliation gate

Scope: `e9cf407` (`infra/tests/staging_prior_alias_reconcile.py`, its offline tests, the manual `staging-prior-alias-reconcile` workflow target and procedure). Static review against the hosted E2E alias derivation, staging D1 schema, mail Worker address lifecycle, and the existing production-grade Cloudflare pagination helper. No credentials were read, tests were run, or provider calls were made in this review.

## Conclusion

**No remaining substantive blocker found for one read-only dispatch.** The tool reconstructs exactly the first two hosted aliases using the v1 HMAC over the protected synthetic password and recorded run ID/attempt (both attempt 1). It selects the fixed staging D1 database and issuer, and queries each address with one parameterized `SELECT`; the D1 API uses HTTP POST for this SQL query, but the script contains no address, route, mail, SMTP, or deployment mutation. Cloudflare Routing Rules access is GET only. Secrets are scoped to the single query step, not the whole job. Output consists only of fixed per-run and gate classifications, never an alias, subject, rule, token, raw response, or exception.

An initial inventory version stopped after a short Routing Rules page when `total_pages` was absent; this could have falsely marked a hidden exact rule as absent. The final version verifies `page`, `per_page`, `count`, and stable `total_count`, computes the expected size of each page, and rejects incomplete or inconsistent inventories. This follows `infra/provider/ensure_role_forwarding.py::pages`, whose existing tests cover the same live Cloudflare pagination shape. The new test includes a short first page with a larger advertised total. The route predicate deliberately checks **exact literal `to` rules**, rather than claiming to exclude wildcard delivery or fully interpret every provider matcher kind.

The D1 predicate accepts either no row or one retired row with no rule ID, `needs_reconcile=0`, the staging issuer, and a bounded subject. If both rows exist, their private subjects must match. It does **not independently prove** that a subject belongs to the synthetic Identity account: no trusted subject oracle is available to this read-only job. For the intended current-isolation gate, the immutable address primary key, retired state (which the Worker rejects on re-add), absent exact provider route, and prior authenticated cleanup observations are sufficient evidence. This gate does not diagnose the two historical registration failures or authorize a third mutating E2E run.

## Boundary and next evidence

This was a source-only assessment. A hosted dispatch may still return `unverified` because of credential scope, provider/D1 response shape, or availability. Such an outcome is not evidence of a clean state or a missing Routing Rules Write grant. Record only the fixed output and reviewed source SHA; if either alias is `not_clean` or `unverified`, do not create another address until that exact state is reconciled.

The separate `e20d831` concurrency change was reverted in `652b227`: GitHub's PR and push `github.ref` values already produce different workflow concurrency groups. That revert does not affect the alias gate.
