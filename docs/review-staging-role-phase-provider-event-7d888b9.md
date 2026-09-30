# Review: typed provider Cron event discriminator (`7d888b9`)

Verdict: **source GO for one bounded, read-only hosted rerun**, after green hosted infrastructure tests. This review did not query Cloudflare, run local heavy tests, or establish the historical Cron phase.

## Evidence and assessment

- `classify()` validates the indexed service, in-window timestamp, untruncated record, exact Worker script name, scheduled/cron trigger, pinned historical Worker version, and a well-formed matching request ID **before** consulting `$metadata.type`. Thus an out-of-scope or malformed provider invocation cannot be silently skipped merely because it is typed `cf-worker-event`.
- Cloudflare's [Workers Logs documentation](https://developers.cloudflare.com/workers/observability/logs/workers-logs/) identifies invocation logs by `$cloudflare.$metadata.type = "cf-worker-event"` and says Cron invocation messages carry the cron schedule. Its [telemetry query schema](https://developers.cloudflare.com/api/resources/workers/subresources/observability/subresources/telemetry/methods/query/) lists event classifiers `cf-worker-event` and `cf-worker-log`. Skipping the former's *payload* is therefore supported; only exact `cf-worker-log` and reviewed application literals may yield a phase.
- Unknown or missing type, unreviewed source/message shape, absent payload, unknown text, and contradictory echoes retain distinct fixed `UNVERIFIED` codes. No branch formats the payload, request ID, provider error, or destination into output. The new tests cover a typed invocation plus an accepted digest, missing type, and two unreviewed wrappers. Prior tests cover scope/version mismatch, cross-invocation failure, and contradictory phases.
- The query remains constrained by exact failed GitHub run/SHA, service/time/version, completed dry-query echo, bounded pages and cursor integrity, no redirects, fixed outputs, and a manual confirmation in the workflow. This commit does not broaden the provider query or add a mutation.

## Residual uncertainty

The first live `scheduled_payload_unreviewed` result does **not** prove that row was `cf-worker-event`; this is a documented mechanism hypothesis. A provider record missing the optional version/request ID will still be `UNVERIFIED`, appropriately. Worker log sampling or expired retention can leave `digest_only_inconclusive` even after a successful query. The next single hosted rerun should record only its fixed outcome, without raw records; if it reports another unknown shape, revise the classifier from documented schema and synthetic evidence rather than weakening scope or printing payloads.
