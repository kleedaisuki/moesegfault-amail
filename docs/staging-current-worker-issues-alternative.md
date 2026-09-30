# Alternative: edit the current Worker resource, not legacy script settings

Investigated 2026-10-01 at local revision `1aea780`; subsequently implemented,
reviewed, and exercised once at `daaab1f`. Current status: **provider-accepted
one-shot PATCH, but acceptance UNVERIFIED; no current Issues-off proof**.
The original investigation performed no private operation or local test/build.
The hosted source checks, one-shot mutation, and independent readback are
recorded below; historical legacy evidence remains separate.

## Historical evidence update (2026-10-01)

Read-only historical Audit page run
[36758328085](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36758328085)
at `c0448ba` reported `read=ok`, `complete=unverified`, `matches=one`,
`http=expected_success`, `action=success`, and
`historical=page_reported_success`. This updates the legacy operation's evidence
to a positive provider-reported outcome on one returned page. It does **not**
establish complete attribution, client response acceptance, or effective
current Issues=false. It does not authorize another legacy settings PATCH.
See [the correction's current outcome](staging-containment-settings-correction.md#current-bounded-outcome-2026-10-01)
and [the classifier contract](staging-settings-patch-forensics.md).

The legacy historical page observation is not the current-resource operation
recorded below. Neither its success bin nor the new PATCH acceptance can
substitute for positive current readback and unchanged-state checks.

## One-shot current-resource outcome (2026-10-01)

Reviewed source run
[36761021378](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36761021378)
at `daaab1f` passed all six selected hosted checks. It established the source
contracts, not effective provider settings. The single Beta current Worker
PATCH run
[36761367007](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36761367007)
at the same source reported `staging_current_worker_capture_off=UNVERIFIED`:

| Phase | Fixed observation |
| --- | --- |
| `projection` | `ready` |
| `serving_pin` | `before_match` |
| `patch` | `accepted` |
| `readback` | `checking` |
| `unchanged_state` | `skipped` |

This localizes the failed acceptance after a provider-accepted PATCH, during
current-resource readback. It does not establish that the PATCH was ignored,
that it had no effect, or that unaffected state passed: that comparison was
skipped. No `current-worker-v1` attestation was produced. Do not retry the
mutation or substitute a fallback endpoint, redeployment, or polling.

The independent five-GET readback
[36761475455](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36761475455)
at `daaab1f` found stable single-version 100% serving for
`c3f6401a-1e84-4f51-91df-ae77d90683e9`, explicit current parent/Logs/traces
`enabled=false`, missing Issues shape/value, `logpush=false`, and empty tail
consumers. It did **not** establish effective `issues.enabled=false`.
Off-disabled preferences `redact_query_string=false`, invocation logging
`enabled=true`, and `persist=true` are not proof of active capture while the
corresponding capture switches are off. Conversely they are not proof that the
strict projected object was preserved. The readback mismatch may concern
Issues absence and/or normalized preferences; these fixed observations do not
isolate the exact helper rejection.

A deliberately delayed, read-only five-GET observation
[36762180676](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36762180676)
at 18:56:55 UTC, approximately seven minutes after the accepted PATCH, again
found the exact serving version stable at 100%, parent/Logs/traces=false,
Issues missing, logpush=false and empty tails. This adds one bounded temporal
observation beyond the immediate readback; it does not establish that the
PATCH was ignored, the state is permanent, or effective Issues=false. No
further identical readback is planned; it is not a polling-based acceptance
strategy.

Current all-off acceptance and the public-send/Queue-rollout privacy gate remain
closed. Historical Audit run `36758328085`'s `page_reported_success` remains a
separate legacy-operation observation, not a resolution of this mismatch. A
next discriminator must be separately reviewed against these phase-specific
facts; no repeated live write is authorized by this record.

## Finding and decision implication

There is a materially different documented operation on the same current
resource already used for authoritative readback:

```text
PATCH /accounts/{account_id}/workers/workers/{worker_id}
```

The official [Edit Worker reference](https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/methods/edit/)
describes a partial update preserving omitted properties and accepts
`observability.issues.enabled`. This is not the attempted legacy
`/scripts/{name}/script-settings` PATCH. The sibling
[PUT operation](https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/methods/update/)
is explicitly a full replacement that defaults omitted properties: **do not
use PUT or an SDK `update` call**.

This supplies a prospective way to set current Issues-off without uploading
code or introducing a Queue binding. It does not explain the historical failed
operation, prove that this account accepts the alternative, or justify relaxing
the positive Issues=false acceptance condition. No new documented read-only
endpoint was found that turns the existing missing Issues member into positive
effective false evidence.

## Scope and schema constraints

The [official API introduction](https://developers.cloudflare.com/changelog/post/2025-09-03-new-workers-api/)
separates persistent Worker settings from immutable Version code/bindings and
explicit Deployments. Current top-level observability belongs to the Worker
resource; a version, preview configuration, or deployment timestamp is not an
effective current capture policy. Preserve the existing serving-version bracket.

An important schema/prose tension prevents recommending a tiny JSON delta.
The reference and pinned official
[Python SDK signature](https://github.com/cloudflare/cloudflare-python/blob/c9dd8956de93575640e06ea28e802951175099a0/src/cloudflare/resources/workers/beta/workers/workers.py#L313)
require six body fields: `name`, `logpush`, `observability`, `subdomain`, `tags`,
and `tail_consumers`. The pinned
[request types](https://github.com/cloudflare/cloudflare-python/blob/c9dd8956de93575640e06ea28e802951175099a0/src/cloudflare/types/workers/beta/worker_edit_params.py)
make subdomain's writable flags `enabled` and `previews_enabled` optional;
response-only URL and preview suffix are not writable request fields.

Therefore submit all six required fields with strictly validated current
values for the five unaffected fields and a complete reviewed all-off
observability object. Do not round-trip the raw GET object: identifiers,
references, timestamps, URLs and preview environment data do not belong in the
request. Do not assume recursive nested merge semantics. Omit
`previews_base_config` entirely; compare it privately before/after rather than
copying potentially sensitive preview bindings into another operation.

## Concrete next discriminator and one-shot boundary

Implement a separate manual staging-only operation only after independent
review and hosted contract checks. It must not silently alter the existing
settings-v1 helper or retry the historical target.

1. Keep the operator freeze, staging service concurrency, first-run-attempt
   guard, fixed script name and exact currently approved serving version.
2. Read the fixed current resource and serving deployment. Require its stable
   Worker ID, known name, exact single-version 100% serving policy and existing
   approved bindings without a Queue. Preserve this ID in memory for addressing
   the alternative PATCH; never accept an operator-supplied arbitrary ID.
3. Derive a schema-valid request projection. Require explicit Boolean subdomain
   flags, typed bounded tags, logpush=false, and empty tail consumers. Missing
   required state is UNVERIFIED, not a default. Keep complete unaffected current
   resource projections privately, including preview configuration, references
   and subdomain response properties. Emit only fixed readiness bins.
4. Preserve all existing documented observability settings except the reviewed
   capture-off corrections, and require the resulting complete object to pass
   the all-off source gate. Reject unknown request fields rather than forwarding
   opaque JSON. Recheck the serving pin immediately before one PATCH. No retry,
   PUT, fallback endpoint, new Version, deployment or business traffic is allowed.
5. Require a bounded HTTP-200 successful provider object response with matching
   Worker identity. Then GET the current resource separately: only explicit
   current parent/Logs/traces/Issues false, unchanged unaffected state and stable
   serving-version bracket can establish settings acceptance. A PATCH response
   alone is not an attestation. No undocumented propagation timeout or polling
   loop should reinterpret omission as false.

The readiness read in step 3 is new information: prior diagnostics established
capture flags but not the write-schema projection's subdomain/tag readiness.
It can be included as the first stage of the guarded one-shot operation; do not
repeat prior historical queries or create another undifferentiated diagnostic.

Use fixed stage outcomes (`projection`, `patch`, `readback`, `unchanged_state`,
`serving_pin`) rather than the old single aggregate failure. Provider bodies,
private identifiers, URLs, tags, errors and tracebacks must not reach logs or
artifacts. Transport/protocol exceptions must normalize to bounded categories.
A new successful operation needs distinct immutable provenance and gate review;
do not parse its marker as historical settings-v1 success.

## Privacy evidence remains independent

The [Issues investigation guide](https://developers.cloudflare.com/workers/observability/issues/investigate/)
states Issues detection is independent of Logs/tracing and can include request
details; disabling it stops new detection, not already retained occurrences.
Effective settings acceptance consequently remains a prerequisite, not the
whole-retained-record privacy canary or a public-send approval. Missing fields,
absence of a new issue, or a successful source build cannot replace it.

## Guarded implementation and hosted-only acceptance

`infra/deploy/apply_staging_current_worker_capture_off.py` is a distinct one-shot
implementation. Its synthetic contracts are
`infra/tests/test_staging_current_worker_capture_off.py`. The implementation has
now been run once against Cloudflare after reviewed hosted checks, with the
UNVERIFIED outcome above. The contracts were not executed locally. The
implementation description below preserves its acceptance obligations; it
does not claim that the live operation met them.

Recommended separate target: `staging-current-worker-capture-off`. Required env:

| Variable | Required value |
| --- | --- |
| `AMAIL_CURRENT_WORKER_CONFIRM` | `APPLY_STAGING_CURRENT_WORKER_CAPTURE_OFF` |
| `AMAIL_CURRENT_WORKER_FREEZE` | `FREEZE_STAGING_MAIL_DEPLOYS` |
| `AMAIL_EXPECTED_WORKER_VERSION` | the exact approved `c3f6401a-1e84-4f51-91df-ae77d90683e9` |
| `GITHUB_EVENT_NAME`, `GITHUB_RUN_ATTEMPT`, `GITHUB_REF` | manual dispatch, first attempt, `refs/heads/codex/amail-v0.1.0` |
| `GITHUB_SHA` | exact reviewed 40-character hexadecimal source revision |
| `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` | existing private project credentials |

The external deployment freeze must be real: the environment value is an
operator acknowledgement, not a provider-side lock. Workflow wiring must use
the existing staging Mail service deployment concurrency group with
`cancel-in-progress: false`, and enforce confirmation before credentials. Source
tests should run before provider access. Public-send hold remains a separate
release gate; this helper neither reads nor changes its D1 state and never
attests a remote hold, privacy pass, or permission to send.

The strict decoder rejects duplicate JSON members, nonfinite constants,
oversized objects, redirects, non-200 and non-success responses. The request
projection requires explicit writable subdomain flags and tags and refuses
unknown subdomain/observability members. It retains recognized observability
preferences, overlays the reviewed all-off source policy, and requires the
result to pass the source policy predicate. Optional provider preferences that
cannot satisfy this predicate block the operation rather than being removed.
The separate writable-policy validator rejects explicit null for optional
Boolean, destination-list and sampling-number members, even where the GET
capture-off predicate tolerates null. Only `traces.propagation_policy` is a
documented nullable writable preference and remains preserved. In particular,
null logs/traces `persist`, `destinations`, or `head_sampling_rate` cannot leak
from a permissive readback representation into a schema-invalid PATCH body.
Every unaffected current response field, including private references, preview
configuration and response-only subdomain properties, is compared in memory;
only observability and mutable update timestamps are excluded. No raw response
or projection is logged or persisted.

At most one PATCH occurs. A successful PATCH response must identify the same
Worker, but does not establish acceptance. A separate current-resource GET
must show explicit parent/Logs/traces/Issues=false **and** exactly the projected
observability object (no silently dropped optional preferences). Existing code,
bindings, single100 deployment identity and Worker ID must remain unchanged.
Already explicit-off current state can reconcile without a PATCH, while still
requiring the same positive GET and serving brackets.

Failure emits only `staging_current_worker_capture_off=UNVERIFIED` and closed
phase bins (`projection`, `serving_pin`, `patch`, `readback`, `unchanged_state`).
`patch:attempted` without `accepted` means a potentially ambiguous write; it
does not mean the provider rejected or failed to apply it. Do not retry the
workflow or fall back to PUT, legacy settings, redeployment or polling. Inspect
the fixed phase evidence and independently approve the next discriminator.
Success emits distinct
`staging_current_worker_capture_attestation=current-worker-v1 version=...`.
Existing `settings-v1` attestation parsers intentionally do not recognize this
marker; downstream containment acceptance needs a separate reviewed integration.
The retained-record privacy canary and production release gates remain closed
until their independent evidence passes.

## Manual workflow integration

The separate `staging-current-worker-capture-off` job in `ci.yml` requires
manual dispatch on `codex/amail-v0.1.0`, staging Environment, first attempt,
`confirm=APPLY_STAGING_CURRENT_WORKER_CAPTURE_OFF`, the approved
`expected_worker_version`, and dedicated
`mail_deploy_freeze=FREEZE_STAGING_MAIL_DEPLOYS`. The dedicated input avoids
confusing the Mail deploy freeze with the existing role-Worker freeze and raises
dispatch input count from 23 to 24, below GitHub's limit of 25.

The job shares non-cancelable `deploy-mail-staging` concurrency with staging Mail
mutation paths. It checks operator acknowledgement before synthetic helper,
workflow guard and observability contracts; only the final helper step receives
Cloudflare credentials. Push and PR runs cannot execute this job. The historical
`staging-containment-settings` job and settings-v1 parser remain unchanged.
`infra/tests/test_current_worker_capture_off_workflow.py` guards these contracts,
including executing the extracted non-mutating Bash input gate on hosted Linux.
Local verification was limited to AST/YAML parsing and diff inspection; no tests,
provider operations or deployments were executed for this wiring change.
