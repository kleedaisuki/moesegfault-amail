# Staging containment readback discriminator

Status: **read-only diagnostics executed; explicit current Worker capture-off
flags observed; containment-policy/retained-data acceptance remains pending**.
No result here is a completed Queue rollout or privacy attestation.

The staging containment upload in run `36725878855` did not pass the existing
post-deploy observability checker. Do not infer Logs-off from source intent or
loosen `check_observability.py` before examining the discrepancy.

## Original four-GET read-only experiment

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
Independent review and hosted execution were prerequisites of the completed
diagnostics below; this source-test contract is not a privacy acceptance result.

## Executed current Worker resource discriminator

The original coarse read in [run `36730461386`](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36730461386)
left observability missing/non-object on the older endpoints. The separately
reviewed five-GET discriminator at source `34db41a`,
`infra/tests/staging_worker_resource_readback.py`, added the exact current Worker
resource GET between the settings reads and final deployment check. It never
lists unrelated Workers or emits the actual resource ID. The refined fixed
shape vocabulary distinguishes JSON null from absent/other and validates typed
export lists without copying their members.

[Read-only run `36736823997`](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36736823997)
returned `stable100` for staging Mail version `c3f6401a` (abbreviated ID), with
`worker_name=match`, `worker_id=valid`, and these current Worker categories:

```text
observability_shape=object enabled=false logs=false traces=false
logpush=false tails=empty invocation=true persist=true redact=false sampling=one
```

The older `/settings` observability remained `missing`; the older
`/script-settings` observability was refined to `null`. These older endpoint
representations must not be silently converted into false flags or treated as
equivalent to the explicit current Worker object. Exact name match plus a
nonempty typed ID verifies the inspected resource identity without publishing
the ID. The deployment/version pair was unchanged at expected 100% traffic
before and after the five reads.

This is stronger positive configuration evidence than legacy omission: the
current Worker object explicitly reports disabled top-level, Logs and native
Traces enable flags, plus Logpush false and an empty typed tail list. It is
still a current Worker-level, non-versioned observation, not an immutable
configuration snapshot tied to `c3f6401a` or an atomic settings lock.

The diagnostic reports subordinate invocation/persistence true, redaction false
and full sampling without interpreting whether they are effective under the
disabled hierarchy. **Neither those true options alone nor `stable100` settles
the privacy claim.** Official parent-off semantics and the endpoint-specific
containment policy are under independent review. The read queried no retained
logs or Queue payloads, generated no Mail requests and mutated nothing.

Do not declare whole-retained-record privacy or completed Queue rollout, enable
the old source logger for comparison, or relax enabled-sink policy based on this
disabled-resource shape. Resolve/review the effective-settings contract, then
obtain hosted verifier tests and the separately required pinned rollout and
retained-data gates. See [the detailed fixed-result interpretation](mail-trace-sink-remediation-options.md#current-worker-resource-readback-explicit-disabled-capture-acceptance-pending)
and [effective-readback decision](observability-effective-readback-decision.md).

## Official references

- [Script/version settings](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/script_and_version_settings/methods/get/)
- [Script-level settings](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/settings/methods/get/)
- [Deployment listing](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/deployments/methods/list/)
- [Current Worker resource](https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/methods/get/)

Cloudflare documents the first listed deployment as currently serving, with
version traffic percentages. These references justify control-plane comparison,
not a claim that absent fields have safe effective defaults.
