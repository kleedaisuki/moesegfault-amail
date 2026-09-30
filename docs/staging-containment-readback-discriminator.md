# Staging containment readback discriminator

Status: source-only diagnostic, not a containment or privacy attestation.

The staging containment upload in run `36725878855` did not pass the existing
post-deploy observability checker. Do not infer Logs-off from source intent or
loosen `check_observability.py` before examining the discrepancy.

## Read-only experiment

On `codex/amail-v0.1.0`, dispatch `ci.yml` with target
`staging-containment-readback`, confirmation `READ_STAGING_CONTAINMENT_SETTINGS`,
and the exact expected 100%-serving Mail Worker version in
`expected_worker_version`. Run source contracts on a GitHub-hosted runner before
injecting the existing repository deployment credentials. No new Mail API request,
login, telemetry query, setting update, or deployment is performed.

The discriminator uses only four bounded Cloudflare control-plane GETs:
latest deployment, script/version settings, script-level settings, latest
deployment. It requires a single expected version at exactly 100% in the first
read and an identical deployment/version pair in the last read. A rollout change
discards all collected settings categories. It does not print version or account
IDs, URLs, raw JSON, bindings, tail identities, tokens, exception text, or provider
error bodies. Both settings endpoints are compared independently; neither is
silently used as a fallback for the other.

All output keys are fixed. Field values are `missing`, `false`, `true`, or `other`:
strict booleans preserve those values; numeric sampling is `true` for one,
`false` for zero, otherwise `other` (including booleans); container shape is
`true` for a dictionary and `other` for malformed/null containers; tail lists are
`false` when empty, `true` when populated, otherwise `other`; destination lists
are `false` when empty or exclusively Cloudflare, `true` when containing other
strings, otherwise `other`. Missing/null remains distinct. Absent child fields
stay missing, while parent-shape fields distinguish malformed parents. No policy
inference is made from these categories.

`staging_containment_readback=stable100` proves only a stable expected deployment
around successfully read settings, **not safe observability**. The existing
privacy gate remains authoritative and unchanged. Endpoint failure or deployment
ambiguity returns nonzero. The result guides a narrow provider-schema/settings
investigation without exposing payloads or causing fresh sensitive request logs.

## Verification

Focused synthetic tests cover strict types, missing fields, exact GET ordering,
version mismatch, deployment change, endpoint failure and secret-free output.
Tests execute only in GitHub Actions; no local tests/build/live probe was run.
Independent review and hosted execution remain required.

## Official references

- [Script/version settings](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/script_and_version_settings/methods/get/)
- [Script-level settings](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/settings/methods/get/)
- [Deployment listing](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/deployments/methods/list/)

Cloudflare documents the first listed deployment as currently serving, with
version traffic percentages. These references justify control-plane comparison,
not a claim that absent fields have safe effective defaults.
