# Fifth hosted E2E: exact read-only mail aggregate

This diagnostic is limited to hosted staging E2E [run 36589042183, attempt 1](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36589042183). It is a review-gated observation—not a replay, cleanup, or successful acceptance claim. The incident reasoning and limits are in [`staging-fifth-mail-sync-409-incident-36589042183.md`](staging-fifth-mail-sync-409-incident-36589042183.md).

After independent review, dispatch **CI and deploy** with target `staging-fifth-mail-audit`, confirmation `READ_FIFTH_MAIL_AGGREGATES`, `alias_run_id=36589042183`, and `alias_attempt=1`. Both workflow and script reject any different coordinates. Staging secrets are scoped only to the final read step. Do not enter or print the alias: `staging_prior_alias_reconcile.alias` derives it in memory from the protected `STAGING_E2E_PASSWORD` and the existing v1 HMAC contract.

The script reuses the existing bounded Email Routing Rules inventory and exact literal-`to` absence check. Independently, it sends one parameterized **SELECT** to staging D1's query endpoint (HTTP POST is the API transport, not a mutation). It first reads the exact address row regardless of issuer, reporting only `expected` or `mismatch` ownership—not raw identity. An unexpected issuer cannot be mistaken for an absent row or yield a successful exit. Message counts are restricted to the expected staging issuer and exact address. The same private HMAC nonce deterministically forms the two E2E subjects, `Signal` and `Distractor`; they are sent as bound SQL parameters, never logged. This separates exact fixture counts from any other inbound mail at the address. The query never returns owner identity, message rows, subject, body, metadata, message IDs, vectors, tokens, or raw provider responses.

The returned aggregates are address state and `needs_reconcile`, whether an expected-owner search-generation row exists, inbound/outbound × active/deleted counts, Signal/Distractor/other-inbound × active/deleted counts, and embedding succeeded/pending/quarantined/no-work counts. If the address row is absent or has an unexpected issuer, owner-generation presence is `unverified`, not `absent`: there is no verified owner key to query. Embedding counts cover **all expected-owner messages** at that address, including deleted ones; `no-work` can be normal for a deleted message. The script checks that the four base message counts equal the four embedding counts, and that the six fixture/other counts partition inbound active/deleted, then logs each count as `0`, `1`, `2`, or `more`. A D1 shape/read failure becomes `unverified` rather than partial message data. Route and D1 reads are independent, so one failure does not suppress the other's fixed-status report. A zero exit code means only that both reads completed, the exact literal route was absent, and the exact address row had the expected staging issuer; it does **not** mean the E2E passed or messages were removed.

| Observation | What it can establish | What it cannot establish |
| --- | --- | --- |
| Signal/Distractor active/deleted bucket nonzero | D1 persisted a matching exact-subject fixture at the exact run address at read time. | Provider timing, ZIP availability, or the 409's code. |
| Other inbound bucket nonzero | Additional expected-owner inbound messages existed at that address. | Their source or identity. |
| Embedding bucket | Present aggregate embedding/work state at read time. | A historical generation change during the failed list request. |
| Generation present | An owner generation row exists now. | Its value at the 409 instant or causality. |
| Exact route absent | No exact literal `to` rule in a complete inventory at read time. | Wildcard behavior or historical route state. |

## Reviewed live readback

The manually dispatched [audit run 36594138488](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36594138488) at source SHA `415f27b` completed its exact-run read. Its fixed-label output reported:

| Dimension | Observed bucket/status |
| --- | --- |
| Exact literal route | absent |
| Exact address / owner / reconciliation | retired / expected / `0` |
| Inbound active / deleted | `2` / `0` |
| Signal active / deleted | `1` / `0` |
| Distractor active / deleted | `1` / `0` |
| Other inbound active / deleted | `0` / `0` |
| Outbound active / deleted | `0` / `0` |
| Embedding succeeded / pending / quarantined / no-work | `2` / `0` / `0` / `0` |
| Owner search generation | present |

The two exact-subject fixture matches establish that both synthetic messages were present as **active D1 records at the audit read time**, despite the harness's earlier list 409 and failed message cleanup. Their embedding work had completed by this later read. The retired address and absent exact literal route describe current routing/address state; they do not delete those active messages. These observations do not establish when ingress occurred, whether ZIP retrieval or search succeeded, what exact 409 code was returned, or whether a search-generation change caused it. `generation:present` is not a historical generation value. The original E2E acceptance remains failed, and the two remaining active fixture records require separately reviewed exact-run cleanup rather than a broad delete or SMTP replay.

The diagnostic was independently reviewed before dispatch. No local test was run during preparation; the pre-dispatch checks were syntax and diff inspection. The synthetic test module covers query shape, privacy, aggregation invariants, and workflow guard for later CI validation. No further live query is implied by this readback.

## Post-second-cleanup readback

The [second guarded cleanup run 36601847525](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36601847525) stopped at `fifth_cleanup_failed:fixture_get_mismatch` before its first per-ID delete. The separate read-only [audit run 36602396858](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36602396858) then reported the following fixed-label state for the same exact run and attempt:

| Dimension | Observed bucket/status |
| --- | --- |
| Exact literal route | absent |
| Exact address / owner / reconciliation | retired / expected / `0` |
| Inbound active / deleted | `2` / `0` |
| Signal active / deleted | `1` / `0` |
| Distractor active / deleted | `1` / `0` |
| Other inbound active / deleted | `0` / `0` |
| Outbound active / deleted | `0` / `0` |
| Embedding succeeded / pending / quarantined / no-work | `2` / `0` / `0` / `0` |

This independent current-state readback corroborates that neither fixture had been soft-deleted by audit time. It does not diagnose which `get` predicate failed, prove a historical lack of transient mutations, or turn the original E2E into a pass. Cleanup remains incomplete; any further live mutation needs its own reviewed, fail-closed gate.
