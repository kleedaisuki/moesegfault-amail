# Staging role-monitor SMTP readiness checkpoint, 2026-09-29

This is a bounded **read-only** checkpoint, not SMTP acceptance or permission to dispatch. At 13:13 UTC, the local Wrangler OAuth token was used only in memory for Cloudflare GETs. No token, account address, forwarding destination, rule ID, or provider response body was written or printed. The repository's public GitHub Actions metadata and the exact successful role deploy job log were read with `gh`; only the version line was emitted from the log.

| Gate | Observation | Scope |
| --- | --- | --- |
| CI deployment origin | [CI run 36569543296](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36569543296) completed successfully at source `588206001bd9fc6c182d6cb88fd4cc6482f6ab70`. Its exact `Deploy isolated staging role monitor` job [109412389465](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36569543296/job/109412389465) succeeded, 12:46:02–12:49:21 UTC. Its bounded log had exactly one `Current Version ID`: `1f4b9ccf-757c-46eb-9282-1356c8cbd040`. | Proven successful deploy job, not SMTP acceptance. |
| Currently serving role Worker | Cloudflare `GET /accounts/{account}/workers/scripts/amail-role-monitor-staging/deployments?per_page=1` returned one latest deployment created 12:49:18.250384 UTC, with exactly one version `1f4b9ccf-757c-46eb-9282-1356c8cbd040` at 100% traffic. The account ID was resolved privately from the one OAuth-visible account. | Point-in-time provider readback matches the CI version and job interval. It may drift after this check. |
| Disposable synthetic route | The reviewed paginated `staging_route.rules` GET inventory completed; no matcher for the exact synthetic staging role address was present. | Point-in-time absence. Four standard direct forwards and isolated D1 were **not** freshly audited at this checkpoint. |
| Deployment freeze | GitHub listed no in-progress or queued `ci.yml` run for this branch at the checkpoint, but active local branch changes were present. No one has frozen pushes, manual dispatches, or out-of-band Wrangler deployments. | **Not enforced.** A zero-running-jobs snapshot is not a distributed lock. Do not dispatch the SMTP job yet. |

The earlier pin `8bb3a1a1-aa7f-4b3b-b861-c10db4a2865a` from run 36532066688 is superseded. The parent maintainer confirmed that reviewed HEAD `51ddd39` is about to be pushed for hosted boundary/probe tests and will redeploy the staging role Worker. Therefore the `1f4b...` pin above is **historical checkpoint evidence, not an authorization or expected pin for a later SMTP dispatch**. The hosted acceptance wrapper must repeat exact job-log, active-version, private-binding, route and D1 checks just before opening the disposable route, and recheck version and route after cleanup.

## Remaining gates before a one-message SMTP dispatch

1. Resolve or explicitly disposition the failed hosted user-mail E2E; the latest normal run [36567571204](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36567571204) failed at address registration and did not reach SMTP, ZIP, or search. Role-mail machine acceptance is a separate path, but should not be presented as after-E2E product acceptance while that failure remains open.
2. Stop branch pushes/manual deploy dispatches capable of replacing `amail-role-monitor-staging`; coordinate with all contributors. Also exclude out-of-band Wrangler deployments. Wait for any role deploy already running, then re-read the current 100%-serving version, its successful exact CI deploy job, synthetic-route absence, four standard forwards, private bindings/observability, and isolated D1 baseline. Only then attest the external freeze. The workflow's shared concurrency group cannot block Wrangler or a push started after the gate.
3. After the pending push/deploy, derive a **new** pin from its successful exact deploy job and current 100%-serving version. Dispatch the reviewed manual `staging-role-smtp` job only with its required confirmation/freeze tokens and that new run/version pair. The earlier `36569543296` / `1f4b...` pair must not be reused without a fresh readback proving it still serves, which the announced deploy is expected to invalidate. Do not put secrets, destinations, nonces, or mail content in dispatch inputs.
4. Keep the freeze through independent exact-route absence after the harness. On failure/cancellation/ambiguous create or cleanup, retain the freeze and use only reviewed ID-bound recovery plus restricted inventory; never retry ambiguous SMTP merely to obtain green output. The strongest harness pass is `machine_d1_only`. Cron Past Events, provider forwarding and digest events, and destination Inbox/Junk remain distinct oracles. Public sending stays held.

See [the full role-monitor acceptance runbook](staging-role-monitor-acceptance.md) and [hosted gate review](review-staging-role-hosted-acceptance.md) for the exact safety protocol and evidence limits.

## Pin semantics and next invocation (follow-up, 2026-09-29)

The hosted gate does **not** require its selected successful role-deploy run to have the branch's latest source SHA. It requires a completed successful `ci.yml` push/manual run on the selected branch, its exact successful `Deploy isolated staging role monitor` job and deploy step, one version UUID from that step's bounded private log, and Cloudflare's currently single 100%-serving version equal to that UUID and the input pin. Thus an older SHA is not intrinsically rejected, but an older run cannot attest acceptance *after* newer CI, and any newer serving deployment invalidates its version pin. At this follow-up, branch and remote HEAD were `63abdb42319603054622a1b65dabd81514def113`; push [run 36579868487](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36579868487) had a failed `Rust Worker (Wasm)` job and skipped the role-deploy job. It cannot provide a new role-deployment pin. This is a point-in-time CI observation, not a provider readback.

After stable successful CI/deploy and the external freeze/readbacks described above, invoke the branch-local manual workflow with only public control inputs (replace placeholders with the **newly verified** exact run ID and serving version):

```text
gh workflow run ci.yml --ref codex/amail-v0.1.0 \
  -f target=staging-role-smtp \
  -f confirm=RUN_STAGING_ROLE_SMTP \
  -f role_deploy_run=<successful-current-role-deploy-run-id> \
  -f role_version=<matching-100%-serving-version-uuid> \
  -f role_freeze=FREEZE_STAGING_ROLE_DEPLOYS
```

The GitHub job uses the protected `staging` environment and requires its configured account/API/routing secrets. The existing staging Cloudflare API token is also mapped in memory to the SMTP token; sender-read capability does not establish SMTP AUTH capability. Its 30-minute timeout and shared Actions concurrency group are not an external deployment lock. Keep all branch pushes, manual role deploys, and out-of-band Wrangler changes frozen until the post-run exact-route and version audits complete. The harness arms an ignored local recovery marker before route creation, deletes only the provider ID it recorded, compares all four standard forwards, then requires two exact-route absence readbacks separated by 60 seconds. A canceled hosted runner may not leave a usable marker or upload an artifact; restricted inventory and ownership reconciliation therefore precede any retry or unfreeze. An ambiguous SMTP result must not trigger a second message just to obtain a pass.
