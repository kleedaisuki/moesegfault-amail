# Operator intake independent static review

Reviewed 2026-09-28 against the WIP `workers/mail-ops/`, `docs/operator-intake.md`, and `.agents/skills/amail-operator/SKILL.md`. This is a source review, not a deployed SMTP/Access test. Only empty isolated D1/R2 resources exist; no operator Worker, Access app, role routes, or canary has been verified. The findings below record issues corrected during review. Cloudflare's [Worker-level Access policy](https://developers.cloudflare.com/workers/configuration/cloudflare-access/) can protect all associated domains and previews; the source's independent JWT validation is a useful second boundary, but the policy itself still needs live proof.

**Final incremental pass:** No open P0/P1/P2 source finding remains after the reviewed corrections. The post-review delta checks R2 after a failed PUT; a confirmed miss best-effort deletes the reservation, while an ambiguous result retains a `failed` row for reconciliation. Old missing-R2 rows expire after seven days, and a D1-persisted R2 cursor walks at most 100 objects per cron tick to remove old objects with no case row. I verified the `worker` 0.8.7 source exposes the used `Range::Prefix`, `ObjectBody::response_body`, `Object::uploaded().as_millis()`, list cursor, `truncated()` and `objects()` APIs. This is API-surface inspection only, not a WASM build or deployed behavior test.

## Resolved P1 — Receiving reconciliation could turn a failed reservation into false SMTP success

**Location:** `workers/mail-ops/src/lib.rs`, `receive()` D1 reservation → R2 PUT → final D1 UPDATE; `reconcile_receiving()` R2 GET miss → D1 DELETE.

**Trigger:** A `receiving` row reaches the 10-minute cutoff while its R2 PUT is delayed. Cron sees no object and deletes the row. The PUT then succeeds, but `receive()`'s `UPDATE ... WHERE state='receiving'` changes zero rows. `.run().await?` reports a successful SQL execution, and `receive()` returns `Ok(())`. The SMTP transaction is therefore acknowledged while no reviewable D1 case exists; the R2 object is orphaned. The 10-minute window makes this uncommon in the normal path, but stalled storage/retries are precisely when the invariant matters.

**Resolution in current WIP:** Reconciliation no longer deletes a reservation after an R2 miss. `receive()` checks the final D1 update's change count; if another task already opened the row, it re-reads the case and verifies the object key, otherwise it fails instead of acknowledging. This removes the identified false-success interleaving. A hosted SMTP/storage-failure test is still needed; the existing sequential SQLite trigger test does not exercise this path. The new never-delete behavior has a separate P2 issue below.

## Resolved P1 — Retention cleanup could erase a report reopened by an operator

**Location:** `workers/mail-ops/src/lib.rs`, `clean_closed()` selecting aged `closed` rows, guarded transition to `expiring`, then unconditional R2 delete; `transition()` also ignores a zero-row guarded UPDATE.

**Trigger:** Cron selects a 180-day-old closed case. An operator reopens it before cron's `UPDATE ... WHERE state='closed'`. That UPDATE changes zero rows, but cron still deletes the R2 report and case audit. Its final `DELETE ... WHERE state='expiring'` also changes zero rows. The now-`open` case survives without its original report. Independently, a concurrent cron transition can make an operator's state-change POST redirect as if it succeeded although its guarded UPDATE changed zero rows.

**Resolution in current WIP:** Cleanup now checks the guarded `closed→expiring` update's change count before touching R2, and operator transitions return HTTP 409 on a lost compare-and-swap. This removes the demonstrated reopen/delete race. A deterministic interleaving test would be stronger than the current sequential SQLite trigger test.

## Resolved P2 — Failed R2 writes briefly left unbounded `receiving` reservations

**Location:** `reconcile_receiving()` now deliberately leaves old `receiving` rows in place whenever R2 GET misses.

**Trigger/impact:** If an R2 PUT fails after D1 reservation (or the Worker terminates before PUT), no task ever retires that D1 row. Repeated failures during a storage incident accumulate inert case records without any retention bound. The current approach correctly avoids the earlier false SMTP success, but it turns a transient outage into indefinite metadata growth and can eventually impede the intake queue.

**Resolution in current WIP:** Cron now retires missing-R2 `receiving`/`failed` rows after seven days. `receive()` still checks its final D1 transition and errors instead of falsely acknowledging if a row was retired. It attempts to delete an orphan R2 object on that path. The live provider/storage failure test remains pending. The architecture paragraph in `docs/operator-intake.md` still said such rows were never deleted at this review pass; owner was notified to align it.

## Resolved P2 — Full-object browser reads imposed avoidable memory and latency cost

**Location:** `detail()` and `raw()` call R2 `.body().bytes().await?`; `detail()` subsequently retains only the first 16 KiB, while `raw()` creates another response body from up to 25 MiB.

**Resolution in current WIP:** `detail()` now requests a 16 KiB R2 prefix, and `raw()` uses the R2 body stream in the response. Forced attachment and private cache headers remain. Hosted WASM compilation and a 25 MiB canary are still needed to validate worker-rs runtime behavior.

## Security and rollout observations (not additional findings)

- The HTTP path calls `operator()` before dispatch, including `/health`; JWT signature, RS256, issuer, audience, token type and exact operator email are checked. POST also requires exact `Origin`. No unauthorized route was found in source. The external Access application is not yet configured; live tests must cover custom domain, direct Worker URL, and preview URL. [Cloudflare Access docs](https://developers.cloudflare.com/workers/configuration/cloudflare-access/) explicitly distinguish Worker-level coverage from hostname-only coverage.
- The route reconciler is read-only by default, owns exact literal role addresses and refuses a conflicting enabled/destination state; it does not use Wrangler `addresses` reconciliation. Cloudflare documents that `addresses` redeploys can remove managed rules, so this narrower approach is justified ([routing rules](https://developers.cloudflare.com/email-service/configuration/email-routing-addresses/)). Live read-back and SMTP canaries remain required.
- D1 keeps only opaque case metadata and operator subject; raw MIME is in isolated R2; alerts contain role/case URL but no report text. The scheduled alert means `sent` is provider-accepted, not delivered. The documentation correctly keeps `abuse_contact_verified=0` until a staffed alert path and external canary are proven.
- The existing SQLite test proves trigger behavior only in a sequential in-memory database. No worker-rs/WASM compile or Cloudflare Email Routing failure-path semantics were verified locally; hosted CI and deployment tests must validate these before routing public reports.
