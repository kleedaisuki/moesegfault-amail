# First staging role Cron: retained fixed-phase log oracle

Status: the first guarded query returned
`UNVERIFIED (scheduled_payload_unreviewed)` in
[run 36676440622](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36676440622)
at source `da86b13`. The revised typed-log query
[36679973792](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36679973792)
returned `UNVERIFIED (scheduled_kind_unverified)`. Both results fail closed:
**no historical phase has been attributed**, and the provider-owned Cron-event
explanation remains a hypothesis rather than a confirmed row. Do not repeat
the unchanged query or infer a phase from unreviewed scheduled records. The
separate [current Routing-token probe](staging-role-token-permission-discriminator.md#first-live-read-only-result-2026-09-30)
found account Addresses forbidden and zone Rules accessible; it does not prove
the token had those permissions in the historical run or that the Cron failed
in `audit_destination`.

The original guarded SMTP run [36603362864](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36603362864)
failed between 2026-09-29 17:13:08 and 17:30:41 UTC at source
`337925fe45a12d7a9a17d0441c278e76357713d9`. Its hosted preflight pinned
the staging role Worker Version ID
`cc4c263c-387c-4ce1-99e7-f911b88bd91a`. The independent D1-only audit
subsequently found one accepted role forward and marked digest, but no
probe-window health check or lease renewal. This makes the post-digest Cron
phase important, **not known**.

`infra/tests/staging_role_phase_logs.py` is a manual-only, read-only classifier.
It first verifies the exact failed GitHub run and SHA, then asks Cloudflare's
[telemetry query API](https://developers.cloudflare.com/api/resources/workers/subresources/observability/subresources/telemetry/methods/query/)
for the exact interval and `$metadata.service=amail-role-monitor-staging`.
It requires a completed dry-query scope echo, complete bounded cursor pages,
per-record indexed service, Worker `scriptName`, and timestamp checks, Worker
`scheduled`/`cron` event type, and the
historical Worker version embedded in each relevant provider record. It
recognizes only reviewed source literals for digest acceptance, fixed failed
phase, static health failure, and bounded healthy count. Cloudflare's opaque
request ID correlates labels **in memory only**; no ID or raw event is printed.
Dynamic Email Handler logs are ignored only when their event type is `email`.
An unreviewed scheduled payload or missing version/request ID is `UNVERIFIED`,
not an inferred absence. Redirects and oversized responses fail closed.
The classifier also rejects impossible same-invocation evidence: a failed
phase paired with `healthy`, or a digest failure paired with the accepted
digest marker. Either indicates a malformed provider view or a correlation
anomaly, not a reliable phase localization. Missing or contradictory
`$workers.scriptName` likewise makes scope unverified; Cloudflare documents
that Worker name in the telemetry event schema, but its historical retention
shape has not yet been observed for this Worker.

The historical dispatch contract (not an instruction to retry unchanged):

```text
gh workflow run ci.yml --ref codex/amail-v0.1.0 \
  -f target=staging-role-phase-logs \
  -f confirm=READ_FIRST_ROLE_PHASE_LOGS \
  -f role_probe_run_id=36603362864
```

The workflow sends `CF_OBSERVABILITY_TOKEN` only to the final classifier step,
and GitHub's read-only Actions token to verify the run. It needs neither the
private forwarding destination nor the Routing token. Fixed outputs are
`same_invocation_destination_failed`, `same_invocation_routes_failed`,
`same_invocation_lease_failed`, `same_invocation_healthy`,
`digest_only_inconclusive`, or an `UNVERIFIED` reason from a closed enum. A
failure in a different invocation never becomes the digest's failure. Even a
same-invocation phase failure localizes code execution, **not** downstream
Inbox delivery. A `healthy` label in the exact digest invocation would require
reconciling the D1 health snapshot rather than retroactively passing the
original acceptance.

Cloudflare documents [Workers Logs retention](https://developers.cloudflare.com/workers/observability/logs/workers-logs/)
as up to 3 days on Free and 7 days on Paid plans; daily volume can also trigger
sampling. The historical window may be unavailable after 2026-10-02 or
2026-10-06 depending on plan, and a complete **returned** page does not prove
every application log was ingested. Missing digest/failure is therefore
inconclusive. Do not widen the window, relax privacy checks, or resend SMTP
merely to obtain a convenient phase label.

## A provider-owned Cron event is not an application phase

The first query's `scheduled_payload_unreviewed` means at least one scoped
scheduled record's payload was not in the exact application allowlist. It does
**not** reveal whether it was an invocation summary, a different transport
wrapper, a runtime exception, or an unreviewed application log. The classifier
had treated every scheduled record as an application log. Cloudflare's
[Workers Logs documentation](https://developers.cloudflare.com/workers/observability/logs/workers-logs/)
states that each Cron invocation has a provider-owned invocation log, marked
`$metadata.type=cf-worker-event`, with the Cron schedule as its message.
The [telemetry schema](https://developers.cloudflare.com/api/resources/workers/subresources/observability/subresources/telemetry/methods/query/)
also documents `$metadata.type`, the request ID, Worker event type and script
version. This is a plausible explanation for the first failure, not an
observation of that row.

The revised classifier still requires each scheduled record's exact service,
script, timestamp, historical Worker version, and well-formed matching request
ID. It then skips a payload **only** if the indexed type is exactly
`cf-worker-event`; such a provider summary can never supply a phase marker.
An application phase is attributed **only** from `cf-worker-log` and an exact
reviewed literal. A missing/other type remains `UNVERIFIED
(scheduled_kind_unverified)`. Unknown wrapper shapes are distinguished by
fixed `scheduled_source_shape_unreviewed` or
`scheduled_message_shape_unreviewed`; a parseable but unknown text is
`scheduled_text_unreviewed`; missing text is `scheduled_payload_missing`.
No unknown source, message, metadata value or request ID is printed. A typed
provider event alongside a digest merely leaves `digest_only_inconclusive`
unless a correlated, reviewed application phase also exists. Missing retained
logs, sampling, and a different unknown scheduled event still fail closed.
