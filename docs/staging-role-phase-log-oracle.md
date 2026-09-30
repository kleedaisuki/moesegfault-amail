# First staging role Cron: retained fixed-phase log oracle

Status: **source-only, not yet reviewed, CI-tested, or dispatched**. Do not
describe any historical phase as observed from this implementation.

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

Dispatch after independent review and a green hosted infrastructure test:

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
