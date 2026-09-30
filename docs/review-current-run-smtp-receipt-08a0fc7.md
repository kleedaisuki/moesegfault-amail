# Review: current-run SMTP DATA receipt oracle (08a0fc7)

Scope: `infra/tests/staging_mail_e2e.py` and its synthetic tests, with both cross-module users of the shared SMTP helper. This is a source review, not a live SMTP or GitHub-hosted test result.

## Finding requiring correction before hosted use

**P1 — shared helper signature breaks two existing live probes.** Commit `08a0fc7` changed `smtp_send` from `list[EmailMessage]` to `list[tuple[EmailMessage, dict]]`. `workers/role-monitor/acceptance.py:331` and `infra/tests/staging_address_isolation_e2e.py:248` still call it with a plain message list. The loop's tuple unpack fails before `MAIL FROM`, so the role and isolation probes cannot submit their intended message. Keep the prior helper contract and put receipt-correlated sends behind a separate named helper, or migrate both callers deliberately with suitable oracles. Add an explicit compatibility test. A shared-worktree follow-up now makes this split; review it and the hosted suite before dispatch.

## Receipt and cleanup assessment

The new `mail`/`rcpt`/`data` sequence retains the prior exact envelope, one-recipient policy and implicit TLS. It stores each `DATA 250` provider ID in its original in-memory fixture before proceeding to the next message. The parser requires one bounded angle-bracket ID and never logs the raw reply. Cloudflare's [SMTP reference](https://developers.cloudflare.com/email-service/api/send-emails/smtp/) documents the normal `250 2.0.0 Ok <assigned-id>` response and expressly warns that an accepted `250` may omit an ID when all recipients are dropped; failing closed in that case is correct.

`verify_fixture` compares the independent DATA receipt to owner-scoped GET metadata before ZIP acceptance or cleanup. `verify_archive` requires all immutable manifest fields, the expected file set, rich/text MIME shape, independent phrase/CID/asset bytes, and matches the provider ID. Positive and negative metadata searches use the same receipt. The old dangerous fallback that learned the expected ID from GET was removed. A partial send retains the first receipt; a missing second receipt stops deletion rather than guessing. This is a meaningful safety improvement, not yet live acceptance evidence.

Review limit: the receipt demonstrates SMTP acceptance and an ID to correlate with ingress; it does not by itself prove inbox delivery, rule stability, external role-mail delivery, or an adversarially impossible spoof. Those require the existing independent staging gates. The historical fifth-run cleanup cannot inherit this new oracle because its SMTP DATA reply was not retained.

## Follow-up status

Commit `e2f2c66` restores the legacy plain-message-list helper and exposes the new receipt-correlated path as `smtp_send_receipts`. It also adds a compatibility test. The final source has the `smtp_recipient_refused` assertions in the second-RCPT rejection case and `smtp_receipt_unverified` assertions in the accepted-DATA-without-ID case. `git diff --check` is clean. This resolves the P1 source blocker. **Source-level GO** for the combined `08a0fc7` + `e2f2c66` change; live SMTP dispatch remains contingent on a GitHub-hosted green suite and the usual staging serving-version/control-plane gates. No live delivery result is claimed here.
