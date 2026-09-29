# Staging Mail Worker serving-version pin

## Current bounded evidence

The successful [CI/deploy run 36545383777](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36545383777) checked out `4fe312c5d55f75a7f57906e5cf7bee1893dd5dd5`. Its Mail API [deploy job 109332749996](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36545383777/job/109332749996) reported Wrangler Version ID `988a2f02-da5d-406d-9f60-2723e19c2398` at 2026-09-29 09:01:46 UTC. The same job's private deployment step displayed the expected **staging** binding names and target names, without printing credential values; the pre-deploy Email Routing Rules GET succeeded, and the post-deploy existing `check_observability.py --realm staging` returned `safe`. Those observations establish a successful deployment and settings readback at that time, **not** current 100%-serving status, binding target IDs in the logs, Rules Write authority, or the behavior of an authenticated address-add request.

No local Cloudflare API token/OAuth session is available for an independent readback. The `staging-serving-pin` GitHub-hosted manual job closes that narrow gap using the existing project credential; it performs GETs only. Cloudflare's [List Worker Deployments API](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/deployments/methods/list/) specifies that the first returned deployment is the latest actively serving traffic and includes version traffic percentages. Cloudflare's [script/version settings API](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/script_and_version_settings/methods/get/) exposes binding names and resource target IDs. The script also reuses the existing settings privacy predicate, then re-reads the deployment to reject a rollout during inspection. A successful pin describes the observed interval, not a perpetual deployment lock or a proof that any particular request hit that version. Deployments must remain externally frozen during the subsequent one-use E2E.

## Guarded use

After reviewing and merging the job, dispatch **once immediately before** the controlled staging E2E, using the Version ID from the latest successful mail API deploy job (not automatically assuming the ID above is still current):

```powershell
gh workflow run ci.yml --ref codex/amail-v0.1.0 -f target=staging-serving-pin -f expected_worker_version=<reviewed-version-uuid>
```

The script emits exactly one fixed `staging_mail_serving_pin=<label>` line; only `match` is success. `version_mismatch`, `deployment_changed`, `bindings_mismatch`, `privacy_unverified`, `deployment_unverified`, `unavailable`, and `invalid_input` fail closed. It does not print token values, account/zone/database identifiers, binding values, provider response bodies, or unexpected version IDs. It derives expected binding targets from `crates/mail-worker/wrangler.toml` at the **checked-out dispatch ref**, checks exact names/types and non-secret target values, and rejects an unreviewed binding. Its broad existing token is scoped to one workflow step; no token value is uploaded or placed in shell arguments. A pass must be logged in `docs/validation.md` together with the run URL, expected Version ID, time, and exact checkout, while clearly separating it from SMTP-to-ZIP acceptance. If this project token lacks Workers Scripts Read, the probe is unavailable; do not infer a mismatch or broaden permissions automatically.

The synthetic parser/logic tests are in `infra/tests/test_pin_staging_mail.py` and run in the GitHub-hosted infrastructure test job. They do not perform network calls, authenticate users, register addresses, or attest Cloudflare live state.
