# Review: fifth hosted mail aggregate audit

Scope: uncommitted `infra/tests/staging_fifth_mail_audit.py`, its synthetic tests, the manual `staging-fifth-mail-audit` addition to `.github/workflows/ci.yml`, and `docs/staging-fifth-mail-aggregate-audit.md`. Source-only review on 2026-09-29; no local test, provider request, live D1 read, SMTP, cleanup, push, or deployment was performed.

## Findings and resolution

**No remaining substantive blocker found in the revised source for the manual, read-only diagnostic.** Two earlier P2 findings were corrected before this assessment:

1. The query now uses bound exact `Signal` and `Distractor` subjects reconstructed privately from the same HMAC alias suffix. It returns separate capped fixture and other-inbound counts, with invariants that partition the total inbound count. Thus an unrelated inbound delivery cannot by itself be misread as both fixtures.
2. The exact address row is now read independently of issuer. A fixed `owner_expected` aggregate distinguishes an unexpected issuer from an absent address, and the script exits nonzero on mismatch. Message and generation aggregation still require the staging issuer. No raw owner identifier is returned.

`generation_present` reports only whether a current generation row exists, not the current generation value requested by the incident plan. That is a documented reduction in diagnostic power rather than a privacy or correctness defect: neither value alone can reconstruct the historical 409 race. Expose a bounded value only if longitudinal comparison is actually needed.

## Positive boundaries and limits

The run ID and attempt are fixed in both workflow preflight and script, and the existing v1 HMAC helper reconstructs one address privately. Secrets are scoped to the final workflow step. The code reuses page-complete Routing Rules inventory before exact literal-`to` matching. Its D1 request is HTTP POST only because Cloudflare's [query API](https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/) requires POST; the literal SQL is one parameterized `WITH ... SELECT`, not a row export or mutation. The SQL result shape exposes only aggregate counts, address state, fixed issuer-match status, reconciliation flag, and generation-row presence. Provider exceptions, aliases, identities, subjects, message bodies, IDs, vectors, and tokens do not reach printed output. The manual dispatch target does not trigger the existing deployment jobs, which are conditioned on push or explicit staging/production dispatch.

The staging branch's **push** event separately triggers staging deployments; pushing this diagnostic must not be described as a read-only operation. A zero diagnostic exit currently means only complete route/D1 reads, exact literal route absence, and expected address issuer—not successful E2E, fixture delivery, message cleanup, or a 409 diagnosis. The documentation states this correctly. No live behavior was verified here.
