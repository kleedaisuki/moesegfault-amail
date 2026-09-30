# Review: dormant ten-address hosted controller at 6a877b9

Date: 2026-10-01. Verdict: **request changes for the controller contract; keep live dispatch unwired**.

## Scope and method

Reviewed commit `6a877b9bfd4d61685c976d182a4e5e2d159d66ed`, its campaign and synthetic tests, the existing manifest recovery implementation, the acceptance design, native CLI error formatting, Mail address deletion and reconciliation, staging ingress configuration, and hosted infra test discovery. No local tests/builds, provider calls, or production edits were performed. Findings below follow executable source paths; they are not measured live failures.

## Findings

### P2: denial oracle rejects the actual native CLI diagnostic

Location: `infra/tests/staging_ten_address_hosted.py:102-107`.

`negative()` requires the exact fragment `HTTP 409, code=...`. The CLI constructs its error with `format!("... HTTP {status}, ...")` in `crates/amail/src/api.rs:366-369`, where `status` is the reqwest/http `StatusCode`, whose display includes the reason phrase: `409 Conflict`. Existing native-format fixtures in `infra/tests/test_staging_mail_e2e.py:473-482` and `test_staging_fifth_mail_cleanup.py:44` also use `HTTP 409 Conflict`.

Therefore a correctly rejected first reserved submission fails the controller oracle, runs recovery, and reports an ambiguous campaign rather than reserved-name/quota acceptance. `test_staging_ten_address_hosted.py:27-31` manufactures the same incorrect diagnostic, so its positive synthetic tests do not exercise the actual CLI contract.

Remedy: match the actual fixed native `409 Conflict` diagnostic (without relaxing the exact status/code/stdout requirements), and make the positive fixture reflect the CLI output. Retain wrong status, wrong code and extra-line negative tests. A hosted contract binding to actual native diagnostic formatting would avoid repeating this assumption.

Confidence: high. Impact is test-harness availability/correctness; no dispatch is currently exposed.

### P2: cleanup does not wait for supported DELETE reconciliation

Location: `infra/tests/staging_ten_address_hosted.py:228-229`, with `infra/tests/staging_ten_address_manifest.py:354-365`.

`recover()` supplies `adapter.read` to `manifest.reconcile`, which reads immediately before each delete and once at the end. The supported Mail deletion path sets the row to `retired` with `needs_reconcile=1` and returns HTTP 202 (`crates/mail-worker/src/lib.rs:1592-1597`). Cron subsequently verifies provider absence and clears reconciliation work (`lib.rs:416-423`). Before Cron completes, the next `recovery_actions()` rejects that retired row as `retirement_unsettled` (`staging_ten_address_manifest.py:308-310`).

With the declared adapter behavior of invoking the supported B CLI, normal ten-route cleanup therefore stops after the first successful delete if Cron has not yet settled that row; even one-route cleanup can fail its final read. The synthetic `World.delete()` instead immediately sets `needs_reconcile=0` (`test_staging_ten_address_hosted.py:82`), hiding the normal asynchronous lifecycle.

Remedy: explicitly implement or require bounded **read-only** settlement of each successful delete before the next eligibility audit/final verdict. Keep exact owner/rule/baseline guards, deadlines, and no automatic DELETE replay on uncertain outcomes. A future adapter may own this wait, but its contract must say so and the hosted synthetic controller tests must include the real 202 -> retired/reconciliation-pending -> settled lifecycle. Do not conflate activation polling with cleanup polling or allow a generic wait to suppress foreign-resource failures.

Confidence: high for the current declared adapter contract; an unwritten future adapter that blocks inside `delete` until exact settlement could prevent the failure, but is not implemented or tested here.

## Checks without additional findings

* Ingress oracle correction to `amail-inbound-staging` matches the actual staging `EMAIL_INGRESS_WORKER_NAME`; eligibility still requires exact API-owned enabled rule and saved-ID correspondence.
* New test filename is discovered by hosted `dns`/Infrastructure probe unit tests: `.github/workflows/ci.yml` runs `python -m unittest discover -s infra/tests -v` on push/checks. This verifies discovery, not a completed hosted test result for this commit.
* Source remains dormant: no network/subprocess implementation, live wrapper, workflow target or new mutation capability was added. Documentation correctly retains NO-GO and explicitly lists missing trusted provenance, real encryption, adapters and artifact orchestration.
* Campaign authenticates full intent before add, never replays add on ambiguous outcomes, and uses `finally` for cooperative interruption. Hard kills still require external recovery. Fixed controller failure labels avoid rendering captured CLI/provider exception text in the campaign body.

No live ten-address, encryption, cleanup or production readiness result is implied by this review. Current [Cloudflare Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/) were consulted for platform review context; both findings are established by the repository's native CLI and asynchronous retirement implementation, not an assumed provider guarantee.
