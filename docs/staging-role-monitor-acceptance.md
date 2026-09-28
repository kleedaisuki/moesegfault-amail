# Deployed staging acceptance: reserved-role monitor

Status (2026-09-29): **procedure only; not an executed acceptance result**. Use the deployed `amail-role-monitor-staging` and the single disposable `amail-role-e2e@moesegfault.dev` route. Never point one of the four live `abuse`/`postmaster` rules at this Worker during this test. This plan complements [the monitoring contract](role-mail-monitoring.md), [Worker runbook](../workers/role-monitor/README.md), and the existing [real-SMTP harness](../infra/tests/staging_mail_e2e.py). It deliberately needs no account, amail login, public send-gate change, or owner Inbox action to establish the **machine-side** path. Consequently, it cannot attest human notice, response, or `abuse_contact_verified=1`.

## Preconditions and privacy boundary

1. Pin a Git commit and the successful hosted CI/deploy run; require the Rust Worker/native/Wasm jobs, role-route tests, migration, and staging deployment to have passed. **Before opening the route, inspect the effective deployed observability configuration and require automatic traces disabled**: Cloudflare Email Worker automatic traces can include the envelope `from`/`to`, defeating the role monitor's metadata-minimization policy even when application logs are safe. Keep only reviewed application logs with fixed phase labels, role enum, and opaque generated reference; inspect actual log output for accidental envelope fields. The CI deploy refuses to replace the Worker while the synthetic route is open; freeze staging deployments for the probe window. Confirm the staging D1 contains exactly the reviewed two role tables and the single health row using `workers/role-monitor/check_staging_db.py`. The four production rules must remain direct `forward` rules.
2. Acquire the existing scoped zone routing token, zone ID and staging SMTP sending token through protected environment variables. Do not type a token into a shell command, persist it in a transcript, print it, or put it in a test artifact. `staging_mail_e2e.py` already has the relevant pattern: `assert_staging_sender`, `smtp_send`, TLS SMTP at `smtp.mx.cloudflare.net:465`, and a synthetic sender under `mail-staging.moesegfault.dev`. Extract/reuse those helpers in a future narrowly scoped harness rather than calling the ingress HTTP API or sending from a private human account. Use only a generated nonce in Subject/body and Message-ID; keep nonce and MIME under repo `.temp`, not Actions logs.
3. Audit `python workers/role-monitor/staging_route.py` and require `absent` before starting. Audit D1 counts and maximum `arrival_seq` before the run; if old `unknown`/unalerted rows exist, investigate rather than treating this as a clean acceptance run. Confirm the monitor's private recipient secret is provisioned **without reading or logging its value**. Read-only account API can attest one verified destination by equality inside the Worker; the local test need only check the Worker result.
4. Treat the isolated D1 and Cloudflare's provider message views as restricted. Automatic Worker traces must remain disabled, not merely hidden from the exported report. The only exportable evidence is a case label, commit/deployment ID, UTC timestamp, elapsed time, SMTP response class, D1 counts/state booleans, Cron outcome, and provider event-state booleans. Do not export raw MIME, sender/recipient addresses, subject, destination, token, full GraphQL nodes, or trace attributes containing them. Even a hash of a report field would exceed this Worker's metadata contract.

## One-run lifecycle and independent oracles

The test driver must own only the synthetic rule it created. Implement a `try/finally` (plus process-exit recovery checklist), not a sequence of manual `apply`/`remove` commands that can leave the route open on assertion failure:

```python
# Sketch, not a script that has been run. Invoke the reviewed route helper,
# and keep token-bearing subprocess output suppressed. Never use a production alias.
assert route.reconcile(zone, token, "audit") == "absent"
created = False
try:
    assert route.reconcile(zone, token, "apply") == "created"
    created = True
    assert route.reconcile(zone, token, "audit") == "enabled"
    sleep(60)  # Observed minimum propagation probe, not a universal guarantee.
    assert route.reconcile(zone, token, "audit") == "enabled"
    run_one_smtp_probe_and_poll_restricted_oracles()
finally:
    if created:
        assert route.reconcile(zone, token, "remove") in ("removed", "absent")
    assert route.reconcile(zone, token, "audit") == "absent"
```

If removal/readback fails, **stop**: leave the staging deployment frozen and reconcile the exact rule ID with restricted access; do not create another alias, clear the error, or silently turn the test into a permanent intake. A crash that bypasses `finally` requires the same explicit absent-rule recovery before any later run. Route `apply` returning `enabled` at baseline is a conflict with the test's ownership assumption, not permission to remove someone else's rule.

For the clean successful probe, send exactly one generated RFC 5322 message through authenticated real SMTP. Record the source-generated nonce only inside `.temp`; record public evidence as `case=happy`, not the nonce or header. SMTP `250` establishes submission only. Wait for the new D1 `arrival_seq` above the baseline: exactly one `role='staging_probe'`, opaque UUID ID, positive millisecond `received_at`, `forward_state='accepted'`, and initially `alerted_at IS NULL`; never `SELECT *` or print the ID. A restricted query sufficient for the ledger is:

```sql
SELECT role, forward_state, COUNT(*) AS n,
       SUM(CASE WHEN alerted_at IS NULL THEN 1 ELSE 0 END) AS unalerted
FROM role_arrivals WHERE arrival_seq > :baseline_seq
GROUP BY role, forward_state;
SELECT COUNT(*) AS malformed_refs FROM role_arrivals
WHERE arrival_seq > :baseline_seq AND (length(id) != 36 OR received_at <= 0);
SELECT lease_until > (unixepoch('now') * 1000) AS live_lease,
       checked_at > 0 AS cron_checked
FROM role_monitor_health WHERE singleton=1;
```

Wait for a **natural** five-minute Cron invocation and inspect the corresponding Cloudflare Cron Trigger **Past Events** outcome. A direct `scheduled()` invocation or `wrangler dev` is useful for logic diagnosis but is *not* Past Events evidence. Allow the documented trigger propagation window after first deployment, then bound the observation window (e.g. two normal periods plus propagation); record latency rather than rerunning until a pass. The expected row transition is `accepted, unalerted` → `accepted, alerted`, and the health row has `checked_at` inside this run and `lease_until > current time`. Verify that the official-sender digest is accepted through the `ROLE_ALERT` binding; use a restricted Cloudflare **Email Sending** event/log lookup within the small UTC window to distinguish `accepted`, `delivered`, `deliveryFailed`, or absent. This is a different signal from the forward event. Correlate the original forward using its provider Routing event window/action/recipient and its `X-Amail-Role-Ref` only **inside** restricted views; do not export the header value. If the provider exposes no durable message-ID linkage for `forward()`, report aggregate count/time correlation as weaker evidence, not exact per-message delivery. Cloudflare Routing GraphQL is adaptively sampled; it can corroborate a canary but cannot serve as the once-per-arrival oracle. The D1 row and provider event are independent checks with different failure semantics. Both `forward()` resolution and Email Sending `delivered` are insufficient to prove destination Inbox placement; the owner-facing phase remains unverified until a later private Inbox/Junk check.

For the final machine-side state, verify one alert-marked row, no new `unknown` row, no aged unalerted row, successful Cron Past Event, and a fresh lease. Close the route in `finally`, re-audit absence, then record that subsequent Cron will fail the exact-route audit and the lease will expire; a clean staging-only test must **not** leave a falsely healthy permanent monitoring channel. Do not make public mail send `allowed` or flip any release attestation merely to exercise this Worker.

## Fault matrix (separate isolated runs)

Set **one** `ROLE_TEST_FAULT` phase on the staging Worker at a time. Production ignores that secret. A secret update/deploy can change runtime version, and Cron continues to run independently: freeze the route, allow propagation, record the active version/UTC window, then open the route for one probe. Clear the fault and confirm the active version before the next case. Observe first failure, do not replay SMTP with a new nonce merely to make a dashboard green. A forward ambiguity is not safe to automatically resend. Each case must own and close the same synthetic route as above; use pre/post `arrival_seq` and count deltas rather than deleting rows to hide failures.

| Phase / trigger | Expected D1 and provider observation | Cron/lease expectation and ambiguity |
| --- | --- | --- |
| `before_insert`, one real SMTP message | No new row; Email Worker invocation fails. Record **actual** SMTP response, bounce/retry, and Routing outcome. A `250` followed by silent loss would be a blocker. | Cron cannot see an uninserted report. This tests a hard limit: only provider retry/rejection or external reconciliation can reveal it; never claim D1 proves completeness for messages failing before insert. |
| `before_forward`, one real SMTP message | One new `unknown`, unalerted row; no intended forward call. Capture actual SMTP outcome and any provider routing failure. | Cron may send an `unknown` digest, but `unknown > 0` must reject lease renewal; Past Events must show failure. Do not infer exactly-once retry. |
| `after_forward`, one real SMTP message | One new `unknown` row even if the forward was accepted. The destination may get the original; provider status is a separate oracle. | Cron may alert, then must fail lease renewal because forward is ambiguous. Never blindly replay the forward. |
| `before_alert`, a previously accepted/unalerted row | Forward remains `accepted`; `alerted_at` stays null and no official digest should be submitted in that Cron invocation. | Cron Past Event failure; lease not renewed. If an earlier lease exists it remains usable **until expiry**, so test the boundary rather than claiming instant hold. |
| `after_alert`, a previously accepted/unalerted row | Official digest may be provider-accepted, but `alerted_at` remains null. Later retry can duplicate digest; this is correct at-least-once behavior. | Cron Past Event failure, then replay after clearing fault should eventually mark the row once; compare provider submission counts, not just D1 final state. |
| Route absent/drift or Cron outage | With route absent, no new email should reach the Worker; rule audit must fail on Cron. With Cron disabled/stopped, `checked_at` stops advancing. | Existing 30-minute lease expires and the mail API lease predicate must deny in a **separately controlled** staging policy test. Current global `held` plus false attestations already deny sends and cannot isolate this predicate; do not count `send_held` under those conditions as proof of lease enforcement. |

`ROLE_TEST_FAULT` does not simulate an arbitrary D1 outage or a provider `forward()` rejection; `before_insert`/`before_forward` merely bracket those calls. For a genuine D1-unavailable case, use a separate controlled provider-supported fault if available, or mark it unexercised—do not mislabel the hook. Likewise, `before_alert` is not an actual Email Sending API failure. A real send-binding permission/rejection test requires a safely reversible staging-only configuration fault and deployment review. Failure cases deliberately leave `unknown` rows; do not purge or convert them to `accepted` as part of the test. After evidence capture, either use a fresh isolated test database under an audited migration or explicitly document and review any cleanup of run-owned rows before declaring a clean later run. The normal 90-day cleanup intentionally excludes unresolved rows.

## Verdict and release boundary

Maintain a private case ledger under `.temp` with timestamped **sanitized** observations and a durable, non-sensitive summary in `docs/validation.md`: `not run`, `passed`, `failed`, or `unexercised` per phase, deployed SHA, CLI/harness version, Cloudflare Past Events outcome and correlation strength. Preserve the first failure even if a subsequent retry passes. Do not upload MIME, D1 row dumps, Cloudflare GraphQL nodes, Worker logs with arbitrary attributes, browser profiles, or destination-bearing screenshots as artifacts. The CI harness tests and source review are preparation, not deployed evidence.

Machine-side success is necessary but **not sufficient** for production cutover. Remaining independent gates include forwarding and digest delivery in the actual destination (digest in Inbox, original discoverable in Inbox or Junk), owner or authorized agent response workflow, controlled rollback of each of four exact production rules, expiry-induced mail API denial under an otherwise-enabled staging policy, and ongoing ownership. Until then keep the four production direct forwards unchanged, `abuse_contact_verified=0`, and public sending held.
