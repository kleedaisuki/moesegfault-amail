# Staging retained-log privacy and causal-trace canary

Status: **harness implemented, live retained-log acceptance not yet run** (2026-09-29). This is not a claim that Cloudflare has retained only safe data. The existing source-level [privacy decision](mail-trace-privacy-decision.md), [implementation](mail-trace-implementation.md), and [independent review](review-privacy-trace-implementation.md) explain the threat model and static evidence.

## Boundary and operation

`infra/tests/staging_trace_canary.py` is explicitly staging-only; it never calls a production host or changes an address, message, route, sending gate, D1 row, or deployment. It first reads back the currently deployed mail API privacy settings using `crates/mail-worker/check_observability.py`, then checks that an Observability token can list the indexed `$metadata.service` key. **If either precondition fails it sends no canary request.** This prevents a deliberate sensitive-path probe while native traces/invocation capture might still be enabled.

With an already authenticated staging CLI home, it runs one ordinary `amail address list` using the native binary, suppresses the CLI output, and privately reads the one new redacted SQLite journal row `(T,C,R)`: trace ID, CLI span ID, and server request ID. It then issues one unauthenticated `GET` to a unique rejected path with a distinct synthetic query marker, expects HTTP 401 and a different server request ID, and never reads or prints either response body. It allows Workers Logs to index, then queries the **retained** staging Worker events for a narrow time window via Cloudflare's REST API with `dry=true`, an indexed exact-service filter, cursor pagination, a 1600-record upper bound, and no raw response artifact. Any missing/incomplete page fails closed.

The in-memory checker scans the **entire retained event JSON**, not just the Rust custom source, for both markers; asserts no marker appears; parses allowlisted application JSON from the `source` and, if present, the indexed message; rejects unreviewed event fields/free-form enum values; and requires exactly one API `addresses_list` request-exit record with trace `T`, new server span `S`, `parent_span_id=C`, and request ID `R`. **Every nonempty retained `source` and indexed `$metadata.message` must parse as the reviewed trace schema, regardless of the optional `$metadata.type`.** There is no unreviewed platform-event exemption: an otherwise fixed warning or platform error from another invocation in the bounded window deliberately yields **UNVERIFIED** until separately reviewed. The currently reviewed `routing_list`/`routing_create` phases and numeric provider status/error-code fields are accepted, but free-form provider text is not. The checker also requires an independent 4xx exit record for the rejected URL with **no accepted parent**. Only a fixed pass/failure code is printed; no log row, CLI output, OAuth secret, mailbox address, or canary value is written to CI output or documentation. Cloudflare's own platform metadata is not claimed to be an application-controlled allowlist; the whole record is scanned for the test markers.

### Required private invocation

Do not make this an automatic CI step. Run only after the deployment's effective-setting gate is green, from the repository root, using a **GitHub-built** native executable and an already authorized staging-only `AMAIL_HOME` beneath ignored `.temp`. The authorized home must remain on the same OS account because the CLI uses OS-protected key material. Both paths must resolve under this repository's `.temp`; the script rejects other paths.

```powershell
# Template only. Provision the three environment variables through a private
# credential channel before this shell; never type token values into history.
python infra/tests/staging_trace_canary.py `
  --confirm RUN_STAGING_TRACE_CANARY `
  --amail .temp/staging-cli/amail.exe `
  --home .temp/staging-trace-canary/amail-home
```

Use a token with **Workers Observability Write** at the Cloudflare account level for the query API. Despite the name, this permission is currently required for the read/query endpoint; the harness sets `dry=true` so query results are not persisted. Do not reuse a broad production token for retained logs. The separate deployment token must be able to read the two mail API settings endpoints. The Cloudflare API token is passed only through the process environment, never a command argument, printed exception, or committed file. The script does not fetch an OAuth token directly: it delegates the authenticated request to `amail` and observes its safe local journal. Do not set `AMAIL_TELEMETRY=off` for this run, because the journal row is the CLI-side correlation oracle.

## What a passing run would and would not prove

| Assertion | Evidence if live run passes | Not established |
| --- | --- | --- |
| Rejected path/query markers absent | Every returned retained staging API event in the complete bounded window lacks the two random markers | Other Cloudflare logs outside Workers Observability, arbitrary future URLs, or unsampled/expired events |
| CLI→API causality | CLI journal `T,C,R` matches retained API span `T,S,parent=C,R` | Cloudflare **native** Traces waterfall, automatic D1/R2 spans, or external OpenRouter propagation |
| Retained payload schema | Every nonempty `source` and indexed message in the bounded window parses as the reviewed trace schema with fixed fields/enums/numeric provider facts, even when event type is missing | Platform-owned metadata beyond those payloads is not governed by the application allowlist; hidden error/panic fields outside the sample need separate canaries |
| Anonymous denial isolation | 401 exit record has no caller parent | Malformed authenticated traceparent, exception path, storage/provider failure, or mail ZIP/body privacy |

An empty query, absent indexed key, 403, truncation, row mismatch, or stalled cursor is **UNVERIFIED**, not a privacy pass. Worker log retention is limited and indexing may lag; rerun only after diagnosing the specific failure, not as an indefinite retry loop. Do not broaden the query window to encompass unrelated users merely to turn missing data into a pass. A separate synthetic mail-content and failure-path canary remains needed before production privacy attestation.

## Current access blocker and safer next action

The previous restricted local Wrangler OAuth probe of `/workers/observability/telemetry/keys` returned HTTP 403. The deployed CI token's Observability permission has not been established. The current harness therefore has **no live retained-log result**. The least-privilege next step is a short-lived, account-scoped Cloudflare API token with `Workers Observability Write`, supplied privately as `CF_OBSERVABILITY_TOKEN` to a controlled local run, not pasted into chat or stored in an Actions log. If policy prevents this permission, use Cloudflare's account Dashboard Query Builder with a narrow staging-service/time filter and a private human inspection against the same assertions; record only boolean outcomes and no raw rows. Dashboard screenshots or copied logs must not become public artifacts. Neither a settings readback nor a dry-run unit test substitutes for retained-log inspection.

## External platform contract

Cloudflare's [Workers Observability query API](https://developers.cloudflare.com/api/resources/workers/subresources/observability/subresources/telemetry/methods/query/) documents `view=events`, cursor pagination, `dry=true`, filters, event count, and the `Workers Observability Write` permission. Its [keys endpoint](https://developers.cloudflare.com/api/resources/workers/subresources/observability/subresources/telemetry/methods/keys/) lets the harness verify the service key before filtering. The [Query Builder documentation](https://developers.cloudflare.com/workers/observability/query-builder/) says it searches retained Workers Logs, rather than merely a transient live tail. See [Workers Logs](https://developers.cloudflare.com/workers/observability/logs/workers-logs/) for the separate invocation/custom/error/uncaught-exception capture paths; this canary currently exercises only normal success and authentication denial.
