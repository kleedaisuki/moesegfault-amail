# Outbound abuse controls: independent review

Reviewed 2026-09-28 against migration 0006, Rust API send path, Rust Email Sending Queue consumer, operator workflows, provisioning/privacy scripts, CI promotion sequence, and manual. Final static pass included the send-request DoS cleanup/refactor, opaque request ID on provider feedback, 120-second Queue retry, and explicit production promotion. This remains source review, not deployed validation. I did not run local builds or mutate production code. **No open, demonstrated P0/P1 was found in the final snapshot.**

## Resolved during review

### P1 — Canary and insert-time hold trigger was dropped by the migration

**Original evidence:** An earlier WIP snapshot created `send_request_policy_guard BEFORE INSERT ON send_requests` before `DROP TABLE send_requests; ALTER TABLE send_requests_v2 RENAME TO send_requests`. In SQLite, dropping a table drops triggers attached to it, leaving no insert guard. The send handler's `check_send_policy` reads `canary_used_by`, but only that trigger writes the field.

**Impact:** A 15-minute, recipient-pinned canary grant can be used with multiple distinct idempotency keys, up to other quotas (currently five messages/hour), rather than once. The intended atomic insert-time global/account hold protection is absent, so independent policy checks can race a hold. This does not bypass recipient pinning or sender ownership, but it invalidates the stated one-use release exception and fail-closed race invariant.

**Resolution in current WIP source:** The owner moved the trigger below the v2 rename (`0006_outbound_abuse.sql`, now lines 121–136) and added `held_admission_is_bounded_by_one_canary_key`, which asserts the trigger in `sqlite_master` and rejects a second key. This is a source-level correction, still awaiting hosted CI and live D1 evidence. Do not report the original bug as currently open unless validation contradicts this correction.

## Further resolved during review

### P2 — Abnormal accepted sends could retain private envelopes beyond the stated 90 days

**Original evidence:** An earlier WIP snapshot of `crates/mail-worker/src/lib.rs::expire_abuse_data` cleared `sender` and `envelope_json` only for `send_requests.state IN ('sent','rejected')` older than 90 days. `accepted` rows can persist if `reconcile_sends` repeatedly fails (for example, the ZIP object is missing or cannot be parsed). Accepted rows contain the complete To/Cc/Bcc envelope and sender.

**Impact:** The documented 90-day maximum retention of restricted raw addresses is not an invariant under a real recovery failure. This is a privacy/retention defect, not a demonstrated send bypass.

**Resolution in current WIP source:** The scrub now expires populated sender/envelope columns by `created_at` independent of state; migration backfill skips old rows, and accepted-row reconciliation does not re-populate them after 90 days. A realistic-epoch TTL fixture was added. Hosted CI has not yet established the result.

## Additional correction made during review

### P2 — Canary grant/consumption history was not reconstructible from the durable audit

**Original evidence:** An earlier WIP snapshot of `infra/operator/grant_canary.py` overwrote `send_release_gates` with the canary owner, SHA-256 recipient, expiry and reset `canary_used_by`. `send_release_gate_audit`'s UPDATE trigger stored only the four release-attestation booleans, actor, case reference and time—not the canary grant fields or the consuming idempotency key. A later grant overwrote the only copy of the former grant.

**Impact:** The runbook calls grants auditable, but an incident review cannot establish which account/recipient hash was granted or which idempotency key consumed a prior exception after a regrant. This does not itself allow a send bypass; it weakens accountability over the exceptional path that temporarily bypasses the launch hold.

**Resolution in current WIP source:** The audit table and trigger now include canary owner issuer/subject, recipient hash, expiry and `canary_used_by` on every update. Raw recipient is not stored. The claim trigger also sets `updated_at=unixepoch()`, so the append-only audit records the consumption time rather than reusing grant time.

## Conditional integration risks to verify before release

1. **Provider Queue event body and Worker configuration:** `workers/mail-events/src/lib.rs` parses each Queue body as a direct Cloudflare event object. That matches [Cloudflare's documented event schema](https://developers.cloudflare.com/email-service/platform/event-subscriptions/), but the end-to-end Queue delivery shape and attribution must be confirmed with a deployed canary. The `wrangler.toml` consumer fields (`max_retries`, `retry_delay`, `dead_letter_queue`) and `infra/deploy/ensure_email_events.py` subscription flags match the current [official Wrangler references](https://developers.cloudflare.com/workers/wrangler/configuration/) and [Queues command reference](https://developers.cloudflare.com/queues/reference/wrangler-commands/); no static API mismatch was found.
2. **Legacy attribution repair window, mitigated:** the consumer now retries an unattributable provider ID five times at a 120-second delay. That nominal retry horizon exceeds the five-minute `reconcile_sends` cron that backfills old accepted rows. Queue scheduling and an actual old-row repair remain to verify in staging; the DLQ preserves an event that still cannot be attributed for operator review.
3. **No public-send claim before external evidence:** migration 0006 holds global sending by default and the operator global-allow workflow requires four attestations. Production Worker deployment is now manually promoted rather than triggered by a push to `main`; Queue resources are created before consumer deployment, and the Event Subscription is created only afterward. The site manual explicitly calls `send_held` a protection period. Do not count the HTTP 202 provider acceptance as delivered mail; the pending live Queue/canary/abuse-inbox checks are release gates, not unit-test substitutions.

## Scope and positive observations

The send path keeps accepted/ambiguous idempotency states distinct and does not blind-resend an unknown outcome. It checks sender ownership, account/global holds, local recipient blocks, and quotas before provider submission; it stores provider ID with sender and full private To/Cc/Bcc envelope in one D1 update for later feedback attribution. The Queue consumer avoids logging raw event bodies and matches provider ID plus sender and envelope recipient before inserting a deduplicated event. Complaint processing is atomic at the SQL trigger level and cannot be regressed by a late lower-risk outcome. These observations are static and do not establish runtime correctness or provider delivery.

The final-pass privacy script uses Cloudflare's documented [sending-subdomain PATCH fields](https://developers.cloudflare.com/api/resources/email_sending/subresources/subdomains/methods/edit/) to disable previews and partial suppressed-recipient drops, then reads the exact subdomain back. Queue provisioning now creates the Queues before deploying the consumer and subscribes only after the consumer is deployed. The provider event consumer logs only an API-generated opaque request UUID for newly accepted sends and suppresses duplicate-event logs. These are sensible source-level changes; credential permissions and live provider behavior remain unverified.
