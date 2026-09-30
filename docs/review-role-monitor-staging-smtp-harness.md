# Review: staging role-monitor SMTP acceptance harness (`8e68158`)

Reviewed `workers/role-monitor/acceptance.py`, its exact-route helper, the SMTP helper, offline tests, deployment guard, and the acceptance contract. This is a source review only: no Cloudflare mutation, SMTP submission, deployment, or local heavy test was performed. The prior REST probe remains a failed/limited observation, not SMTP acceptance.

## Follow-up disposition (`846274f`)

Focused source review of the follow-up found **no remaining blocker in the ID-bound create/delete or SMTP-token paths**. `create_owned()` now returns only the provider POST's rule ID after an independent matching-ID inventory readback. `remove_if_id()` refuses a replacement rule; a missing/ambiguous ID leaves the marker and permits only absence audit during recovery. The marker's ID upgrade is atomic, and the send-mode sender check now uses `AMAIL_TEST_SMTP_TOKEN`; read-only preflight explicitly does not claim sender readiness. New offline tests cover timeout ambiguity, replacement, ID readback, and credential selection. Findings P1 and the credential P2 below are **resolved in source, pending hosted tests**. The deployment race P2 is **mitigated procedurally, not mechanically eliminated**: the runbook now requires an externally enforced freeze, no in-flight deploy, and Worker-version checks before/after. No live SMTP or provider acceptance is implied by this review.

## Findings

### P1 — Cleanup does not prove that the route is the one this run created

`acceptance.py:286-298,315-319` arms a local marker and invokes `ROUTE.reconcile(..., "apply")`; `cleanup()` later calls the helper's shape-based `"remove"`. In `staging_route.py`, `reconcile("remove")` deletes **whichever current rule** has the expected name, source, matcher, and action; it does not compare the provider rule ID returned by this run's creation. If the POST times out, or another operator replaces the same dedicated rule between `apply` and `finally`, the harness can delete a rule it did not create. The `outcome == "enabled"` branch protects only the particular race detected by `apply` returning normally; it does not cover an ambiguous POST/readback exception or post-create replacement. The local marker records neither ID nor creation result and is not a cross-host ownership record. This violates the documented “own only the synthetic rule it created” contract. The four standard role rules are still protected by the exact alias matcher; this finding concerns ownership of the disposable route, not a demonstrated standard-rule deletion.

**Correction:** Make `apply` return the created provider rule ID (or an explicit ambiguous outcome) and provide a remove-if-ID-equals operation that re-reads the route immediately before deletion. On ambiguous create, do not automatically delete a shape-matching rule unless ownership can be established; retain the marker and require restricted reconciliation. Bind recovery to the recorded ID where known, and explicitly document the ambiguous-ID manual case. Add tests for POST timeout followed by another writer's matching rule, and for replacement after successful creation.

### P2 — Sender-read preflight uses the wrong credential

`acceptance.py:142` passes `CLOUDFLARE_API_TOKEN` to `SMTP.assert_staging_sender()`, while the existing hosted SMTP harness (`infra/tests/staging_mail_e2e.py:496`) passes `AMAIL_TEST_SMTP_TOKEN` to the same API read. The acceptance harness validates only the latter as the SMTP credential in send mode (`acceptance.py:78-79`). If the deploy/audit token lacks Email Sending read permission, both `--preflight` and `--confirm-staging-smtp` fail before route creation even when the working SMTP token is available. The failure is safe but makes this acceptance path depend on an unstated extra grant.

**Correction:** In send mode, check the sender domain with `AMAIL_TEST_SMTP_TOKEN`, matching the existing SMTP contract. Keep `--preflight` independent of SMTP credentials by either reporting sender readiness as not checked or offering an explicit send-capability preflight that requires that token. Test the actual argument passed to the helper, not only a mocked successful call.

### P2 (conditional) — The staging deployment freeze is procedural, not interlocked

The CI deploy job checks route absence immediately before and after Worker replacement (`.github/workflows/ci.yml:808-833`), but the local harness opens the route later without participating in the workflow's `deploy-role-monitor-staging` concurrency group. A push/deploy can pass its precheck while the route is absent, then the harness opens the route and sends while the Worker is being replaced; the postcheck cannot detect the temporary overlap after cleanup. The document does require an explicit staging deployment freeze, so this is a residual operational hazard rather than proof that the current run was unsafe.

**Correction:** Before a live run, make the freeze enforceable (for example, temporarily disable staging deployment or use a shared provider-backed lease/guard honored by both deploy and probe), and record the active Worker version before/after the run. Do not rely on two route snapshots or a repository-local marker as a distributed lock. A narrowly scoped production-grade interlock is preferable to a general locking framework.

## Sound boundaries observed

- The harness never changes the public send gate or the four standard forward rules; it snapshots their IDs and private targets and compares them after cleanup.
- The transient `unknown` state is bounded, and `accepted` plus D1 alert/lease is not mislabeled as provider delivery, Cron Past Events, or destination Inbox acceptance.
- Printed outcomes are fixed labels; credentials, destination, nonce, MIME, and raw provider responses are not intentionally emitted. The private nonce file remains under ignored repository `.temp`.
- Offline tests are discoverable by the hosted infrastructure test job. They do not establish a live SMTP/Cron/provider outcome.
