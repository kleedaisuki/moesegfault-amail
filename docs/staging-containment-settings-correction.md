# Decision: correct staging API capture settings without redeploying code

Date: 2026-09-30. Status: **implemented source contract; first live correction
attempt UNVERIFIED, with no accepted settings attestation**. The original design
investigation performed no private API call, local test/build, deployment, push,
or production change; the bounded hosted attempt is recorded below. This supplements
[effective readback](observability-effective-readback-decision.md) and the
[Queue migration](privacy-trace-sink-deployment.md).

## Problem and chosen boundary

The current Queue producer/sink rollout requires a successful immutable
containment deployment run. The currently serving containment-only API version
`c3f6401a-1e84-4f51-91df-ae77d90683e9` was observed at 100%, with general
observability, Logs, and native traces explicitly disabled, but Issues omitted.
The newer all-capture gate correctly rejects missing Issues. Historical source
also lacks explicit Issues-off; historical diagnostic success does not make a
failed deployment workflow successful.

Current source cannot simply be deployed to obtain that proof: it already binds
the Queue producer, whose Queue/sink provisioning requires the proof first.
Rewinding the active branch or bypassing the gate would hide rather than solve
this dependency cycle.

**Decision:** introduce one narrowly scoped manual staging settings-correction
job and a distinct `settings-v1` immutable attestation. Keep the exact currently
serving containment-only code, bindings, routes, triggers and deployment unchanged.
Change only its non-versioned observability object. After positive effective
all-capture-off readback, that settings run plus the unchanged serving-version
pin becomes sufficient provenance for the next Queue migration. Keep the old
deployment attestation as a separate kind; never silently broaden it.

```text
reviewed current source -> hosted source CI
                         -> manual settings correction on existing c3f
                            -> successful settings-v1 run + current all-off pin
                               -> Queue provision/sink -> producer deployment
```

This is containment correction, not Mail code deployment or full privacy
acceptance. No new Worker Version ID is expected. Production sending, retained
record acceptance, and other Workers remain outside this job.

## Official API contract and the merge question

The official [Patch Worker Script Settings API](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/settings/methods/edit/)
uses JSON `PATCH /accounts/{account}/workers/scripts/{name}/script-settings`.
Its request fields are observability, Logpush, tags and tail consumers; its
observability schema explicitly supports `issues.enabled`. The alternative
multipart `/settings` endpoint is a script-and-version update and is **not** the
selected operation. The [pinned Wrangler investigation](wrangler-observability-readback-research.md)
independently identifies `/script-settings` as its non-versioned PATCH.

No explicit published nested merge-versus-replacement guarantee was found. Do
not rely on a one-field `issues` delta, JSON Merge Patch semantics, or a guessed
default. Instead submit the complete reviewed staging observability object
extracted from the immutable run-head `crates/mail-worker/wrangler.toml`:

```json
{
  "observability": {
    "enabled": false,
    "head_sampling_rate": 1.0,
    "redact_query_string": true,
    "logs": { "enabled": false, "invocation_logs": false },
    "traces": { "enabled": false },
    "issues": { "enabled": false }
  }
}
```

This establishes explicit capture switches whether the object merges or
replaces. Optional inactive provider defaults need not be guessed; positive
capture-off readback remains mandatory. Do not add Logpush, tags, tails,
bindings, code, migrations or secrets to this body. The endpoint's documented
domain excludes code/bindings; pre/post equality additionally checks the actual
unaffected state rather than treating that domain as a universal server guarantee.

## Implementation slice: one job and one bounded helper

Add a `ci.yml` dispatch target `staging-containment-settings` and dedicated job
ID `staging-containment-settings`, display name:

```text
Apply isolated staging API capture-off settings
```

Require `github.event_name == workflow_dispatch`, exact project branch
`refs/heads/codex/amail-v0.1.0`, confirmation
`APPLY_STAGING_API_CAPTURE_OFF_SETTINGS`, and canonical supplied expected version.
For this one-shot correction the helper must additionally require the reviewed
literal `c3f6401a-1e84-4f51-91df-ae77d90683e9`; accepting arbitrary API versions is
not needed. Require `GITHUB_RUN_ATTEMPT == 1` before credentials or mutation.
Use the existing non-cancelable manual workflow group and
`deploy-mail-staging` service concurrency. Maintain the external deployment and
settings freeze; GitHub concurrency does not exclude out-of-band mutations.

Use GitHub-hosted Ubuntu, Python, checkout of `github.sha`, only project
`CLOUDFLARE_ACCOUNT_ID`/`CLOUDFLARE_API_TOKEN`, and no Rust/Node/Wrangler install.
Do not set a `needs` on the sink or the usual staging-worker job. Either attest
an already successful same-SHA hosted checks run, or run the helper/effective
checker synthetic contracts in this job before exposing credentials; the
parent should choose one explicit policy rather than require unrelated deploys.
Independent source review and hosted checks remain prerequisites to dispatch.

Suggested helper: `infra/deploy/apply_staging_capture_off.py`, fixed Worker name
`amail-mail-staging`; no realm/URL/body override. Ordered operations:

1. Validate confirmation, first attempt, account/token shape, exact expected
   version and local staging name/source `safe_observability` policy. Extract
   **only** staging `observability` for serialization; never deploy the current
   run-head Rust handlers or its Queue binding.
2. Read latest serving deployment; require one expected version at exactly
   100%. Keep the deployment/version pair privately.
3. Read the immutable expected version; reuse exact `bindings_match` to verify
   existing Mail/role D1, R2, Email, vars and secret **names**, including rejection
   of extra Queue bindings. Never read secret values. Current stage resource
   config is compatible with this old version; do not extend the expected
   binding set to admit TRACE_EVENTS in this job.
4. Read `/settings`, `/script-settings`, and exact Worker resource. Require
   correct name/typed stable Worker ID, explicit general/Logs/traces off,
   Logpush false, typed empty tails, no populated streaming-tail consumers, no
   external export, and valid optional shapes. Issues may be missing/null,
   false or true at this pre-correction boundary; this is **not** preflight
   all-capture acceptance. Reject other field shape/identity drift. Preserve
   unaffected typed tags/Logpush/tail projections privately, with presence/null
   distinctions; do not print them.
5. Recheck the identical serving pair **immediately before PATCH**. Issue one
   bounded HTTPS PATCH with JSON above, successful HTTP/provider envelope and
   object result; do not log raw response or exception. Never automatically
   retry the mutation. If already positive all-off, a read-only verified no-op
   can be attested explicitly rather than writing again.
6. Read exact Worker resource and both legacy settings; require the existing
   full `effective_api_settings` predicate, including positive Issues=false.
   Require same private Worker ID and unchanged unaffected projections.
   Re-read the immutable version if desired for independent equality; the
   identical deployment/version is mandatory regardless.
7. Finish with identical serving deployment/version pair at 100%, no newly
   admitted bindings, and final effective policy. Emit the attestation marker
   **only after every required check passes**. No business/health request,
   login, SMTP, address mutation, Queue provisioning or retained-log query is
   needed in this correction job.

Use existing bounded safe readers as the model: finite timeout, byte cap,
typed provider envelope, no redirect to arbitrary host, no raw error fallback.
Define fixed failure categories for source, preflight, PATCH ambiguous/failure,
post-readback, unaffected-state drift and deployment drift. A failed postcheck
is UNVERIFIED even if PATCH returned success.

## Distinct immutable settings attestation

Proposal for exact successful helper log marker:

```text
staging_api_capture_off_attestation=settings-v1 version=c3f6401a-1e84-4f51-91df-ae77d90683e9
```

The only variable is the prevalidated exact expected version. This UUID is an
already approved operator pin, not an arbitrary provider response printed to
logs. Do not emit `Current Version ID:`: no deployment occurred. Parser must
handle GitHub's job/step/time prefix but require the marker content anchored to
line end, exactly one occurrence, correct kind and version. Reject duplicate,
mixed-kind or deployment-version markers in this settings job.

Extend `require_trace_containment.py` with explicit
`--kind {deploy-v1,settings-v1}`, defaulting to existing `deploy-v1`; thread a
matching `trace_containment_kind` dispatch choice through both sink/API prechecks
and sink postcheck. Existing callers remain compatible. Do not infer kind from
any successful diagnostic name or fall back from failed deploy-v1 to settings-v1.

For `settings-v1`, immutable evidence must require:

| Evidence | Required contract |
| --- | --- |
| Run | Exact numeric ID, first attempt, completed success, workflow_dispatch, exact repository/branch and `.github/workflows/ci.yml`, canonical immutable `head_sha`. |
| Jobs | Complete bounded job page, exactly one matching dedicated job, successful conclusion; unrelated diagnostic/deploy job is not interchangeable. |
| Marker | Exactly the settings-v1 marker above for supplied version; no contradictory/duplicate deploy marker. |
| Historical source | Fetch TOML at exact run `head_sha`, exact staging Worker name, strict `safe_observability` including Issues=false. |
| Source operation | The reviewed helper/workflow at this SHA runs the fixed settings-only operation and emits marker only after stable serving/effective checks. This is a source review obligation, not proof from the TOML alone. |
| Current state | Existing runtime stable single100 expected-version bracket and full `effective_api_settings`, including Issues=false. Source/run success never replaces this readback. |

The settings-kind TOML may contain the future Queue producer: its attested scope
is **only** extracted observability intent. It does not claim that Rust source
or bindings at run head were deployed. The exact immutable version/bindings
checks attest the code-side state separately. This is why a different kind/job
name is required. Preserve deployment-only evidence checks unchanged.

No artifact is essential for this tiny attestation: immutable hosted run/SHA,
dedicated successful job and unique typed marker match the existing log-based
deployment evidence model. An optional private artifact may retain non-secret
run/version/policy metadata, but is not a substitute for those checks.

## Failure and recovery

A timeout, transport failure, malformed response, killed run or failed
post-readback may have applied the setting. Do not undo it, rerun the PATCH
blindly, or restore an old logging-on config. Existing read-only Worker-resource
readback may reconcile exact expected version/settings. A failed original run
never becomes acceptable provenance. A reviewed recovery dispatch may produce
the same settings-v1 attestation through a **read-only positive all-off no-op**
after full unchanged-version/binding/settings checks. It must be a new first
attempt successful run; preserve the original failed ID as incident evidence.

If effective Issues remains absent despite successful explicit PATCH, stop
Queue rollout: do not reinterpret omission as false, lower the gate, or patch
repeatedly. This then warrants provider clarification or the independently
reviewed full-redeploy fallback, not further identical probes.

## Fallback comparison

| Option | Benefit | Material cost/risk | Judgment |
| --- | --- | --- | --- |
| Settings-only, distinct immutable proof | Preserves code/bindings and user contracts; no Rust rebuild; no Queue dependency. | Requires explicit new evidence kind and narrow API reader/writer; nested server semantics must be checked by effective readback. | Recommended. |
| Separate containment-only branch | Genuine deploy run with no Queue producer and Issues=false, can preserve old deploy evidence shape. | Current gate hardcodes active branch; old source checkout can trigger auto staging mutations; assembly/head-TOML provenance must be exact; hosted Rust rebuild and new serving version required. | Fallback after separate source review, not immediate. |
| New dedicated containment redeploy job on active branch | Keeps one branch, can use immutable known containment handlers and committed dedicated config. | Must prove exact old code SHA + actual dedicated config, not fetch unrelated run-head TOML; more provenance machinery and build time than needed. | Only if provider requires redeploy. |
| Rerun historical failed deployment | Familiar workflow. | Source lacks Issues; overall failure and first-attempt constraint remain; does not add needed evidence. | Reject. |
| Disable current Queue gate / roll back pre-containment | Fast apparent progress. | Introduces unproved producer/runtime state or restores known unsafe retention. | Reject. |

If a full redeploy becomes necessary, use a new reviewed immutable source commit
with known containment-only handlers, no TRACE_EVENTS binding, strict disabled
observability including Issues, and an isolated manual deploy job. The actual
deployed TOML must be committed and fetched from the exact artifact/source SHA
used by the job. Do not mutate/rebase the active branch or assume a dynamically
assembled config equals its run-head TOML. Hosted tests/build and effective
readback are then required before a new accepted deployment proof.

## Hosted verification and acceptance

`infra/deploy/apply_staging_capture_off.py`, its focused synthetic contracts in
`infra/tests/test_staging_capture_off.py`, and the dedicated manual CI job now
implement this narrow path. All provider requests use a byte/time-bounded reader
that rejects redirects and never retries. The helper verifies exact source
policy and existing no-Queue bindings, allows only the independent Issues
switch to be unverified in the pre-correction boundary, issues at most one
PATCH, checks unaffected projections/identity/bindings/serving after it, and
emits the typed marker only after success. Positive already-off recovery is
read-only. Failure output is fixed `staging_api_capture_off=UNVERIFIED`, never
provider/error text. The manual job runs focused correction/effective-checker
synthetic tests before credential-bearing execution and installs no build tools.

The existing source infrastructure test discovery includes these contracts;
no local test suite was executed. Static Python AST parsing and `git diff
--check` passed. Independent source review and hosted execution remain required.

Synthetic tests should discriminate wrong version/name/ID, split traffic,
extra Queue binding, first-attempt violation, unsafe source, missing Issues
after PATCH, all-off no-op, pre/post deployment drift, unaffected-state drift,
ambiguous PATCH, byte/time bound, and no marker on any failed check. Attestation
tests cover wrong run event/path/branch/SHA/job/conclusion, incomplete jobs,
duplicate/mixed markers, wrong version, unsafe historical TOML and explicit
kind handling. Run these on GitHub Actions, not the workstation.

The intended acceptance sequence is one narrow settings dispatch after source
review and successful hosted checks, followed by recording its exact successful
run/SHA, unchanged expected version and effective all-off result. Only then
dispatch Queue rollout with
`trace_containment_kind=settings-v1` and that run/version. The later complete
retained-record synthetic canary remains necessary; settings success does not
attest erased historical records, future uninterrupted privacy, role Email/Cron
capture, Security Events, or lossless Queue tracing.

## First hosted attempt: no accepted correction evidence

[Source CI `36742065920`](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36742065920)
completed successfully at immutable source
`a30cd5d46f36e373feb1bf7933aab2fdfce0b122`. The subsequent isolated
[settings run `36742914068`](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36742914068)
used the same SHA. Its confirmation and credential-free synthetic contracts
passed; the credential-bearing correction step failed at 2026-09-30
16:16:04 UTC with only the fixed helper result:

```text
staging_api_capture_off=UNVERIFIED
```

No settings-v1 attestation was emitted. This aggregate failure does **not**
identify a phase, establish that PATCH was attempted, or establish that PATCH
was not attempted. It is not evidence of either successful mutation or a
provider rejection. Successful source/synthetic checks cannot replace live
postconditions or make this failed run valid containment provenance.

The subsequent read-only
[Worker-resource run `36743104235`](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36743104235),
also at `a30cd5d`, succeeded. Its five-GET observation reported `stable100`
around the expected serving Version ID
`c3f6401a-1e84-4f51-91df-ae77d90683e9`. The distinct **current Worker resource**
(non-versioned settings, not the immutable version object) passed name/ID checks
and returned:

| Read boundary | Bounded observation |
| --- | --- |
| Current Worker resource | Observability object; parent enabled=false, Logs=false, traces=false; Issues shape/member missing; Logpush=false; tails typed empty list. |
| Current Worker subordinate options | invocation=true, persist=true, redact=false; sampling=one; Logs/traces destinations typed empty lists. |
| Legacy `/settings` | Observability missing; Logpush=false; tails typed empty list. |
| Legacy `/script-settings` | Observability explicit null; Logpush=false; tails explicit null. |

These explicit parent/Logs/traces false flags are positive observations, but
Issues omission remains **unverified**, not false. Stable serving traffic
brackets code selection; it does not atomically freeze non-versioned settings,
prove a PATCH phase, or provide a whole-retained-record privacy result.

**Next discriminator:** diagnose the failed helper's phase through reviewed
bounded fixed-category instrumentation/readback. Do not retry the mutation
before that diagnosis, infer the PATCH outcome from unchanged bins, accept the
failed run as an attestation, or open Queue rollout/public sending. No active
privacy pass or Queue rollout follows from either run.

### Fixed read-only phase diagnosis (source only)

`infra/deploy/diagnose_staging_capture_preflight.py` and its focused synthetic
contracts implement the next discriminator without invoking the correction
helper's `apply`/PATCH path. Dispatch `ci.yml` on the reviewed source branch with
`target=staging-capture-preflight`,
`confirm=READ_STAGING_CAPTURE_SETTINGS_PREFLIGHT` and the same literal expected
c3f Version ID. The dedicated job requires first attempt and runs synthetic
contracts before credentials. Source review and hosted execution are still
required; no diagnostic was deployed or run in this source change.

After exact source-policy validation and the initial expected single100 pin,
the only provider operations are six bounded GETs: deployment, immutable
version, legacy settings, script-settings, exact current Worker resource, and
deployment again. Each uses the existing no-redirect/no-retry bounded reader.
The version and three settings resources are inspected even if one independent
phase fails, avoiding repeated narrow diagnostic runs. A failed read is never
retried. An observed final deployment change discards the collected bins.

Output is a closed list of fixed categorical fields prefixed
`staging_capture_preflight_`: source, serving, version read/bindings and a fixed
binding mismatch cause, per-endpoint read status, independent normalized-policy
phases, unaffected projection shape, closing serving pin and aggregate
preflight. No provider binding names, identifiers, values, counts, source text,
error bodies, credentials or retained records are output. Transport/timeout,
HTTP denial/not-found/5xx and provider-envelope failures have fixed categories.
No `settings-v1` or `Current Version ID` attestation marker is emitted.

`diagnosed` means the bounded reads were complete under the serving bracket,
not that containment is safe. `preflight=pass` means only that the existing
helper's **Issues-relaxed pre-correction** predicates currently pass. Missing
Issues still fails actual all-capture-off acceptance. The synthetic fixture
matching the reported dormant defaults, missing Issues and null legacy
observability passes that relaxed preflight while failing the actual full
policy; those bins alone therefore do not establish a helper source bug.

The diagnostic may identify a current blocker; it cannot establish which
phase the historical failed run reached or whether its PATCH was attempted.
Even a current preflight pass does not authorize retrying the mutation. Keep
the failed run, absent Issues and closed rollout state until a reviewed next
step resolves the actual failure.

### Hosted preflight result and next discriminator

The parent reports that read-only run
[`36748417146`](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36748417146)
at immutable source `fbbce7314fdf8f0c41729975203876d8ba7d08ff` completed
successfully for the expected c3f version. Source, serving, version/bindings,
both normalized legacy policies, normalized current Worker policy, unaffected
projection and the closing serving bracket matched; aggregate
`preflight=pass`. These results were reused, not independently re-queried by
this follow-up.

Inspection of the exact `a30cd5d` to `fbbce73` diff shows no change to the
correction helper, Mail TOML or effective capture policy. The binding/pin helper
gained an explicit Queue phase but preserved the default historical pre-Queue
contract used here. Thus no **persistent current** source/binding/preflight
blocker was found. This does not recreate historical credentials, network
responses, settings or deployment observations. Transient failure before the
historical PATCH remains possible.

The helper's remaining ordered failure branches are:

| Boundary in `apply_staging_capture_off.py` | Unresolved failure mechanism | What would discriminate it |
| --- | --- | --- |
| Historical preflight or immediate pre-PATCH serving recheck | An earlier transport/envelope failure, old snapshot mismatch, or observed deployment change. | Original phase records, if any; today's preflight cannot reconstruct them. |
| PATCH construction/send | HTTP denial/error, refused redirect, transport failure, timeout, or request never reaching the server. | Exact historical audit receipt/outcome; absent audit coverage remains ambiguous. |
| PATCH response validation | Helper requires HTTP 200, bounded parseable JSON, literal success=true and object result; a rejected, lost or unaccepted response prevents later reads. | Provider audit status can distinguish reported server outcome, but cannot prove client receipt/parsing. |
| Post-PATCH three GETs and full policy | Any read failure, Issues still omitted/enabled/malformed, conflicting legacy data, or changed Worker identity. | Current explicit Issues-off would improve present-state evidence; current omission alone does not prove which historical phase ran. |
| Unaffected projection comparison | Tags/Logpush/tail presence or values changed between snapshots. | Privately correlated historical before/after projection evidence; none was retained in aggregate output. |
| Immutable-version binding reread | Read failure or an unexpectedly mismatching version/resource contract. | Historical phase evidence; today's exact match does not prove an earlier read succeeded. |
| Final serving bracket | Changed deployment/version pair or final-read failure. | Historical phase or control-plane change evidence, not merely a currently stable version. |

These are source-derived possibilities, not claims that each occurred. In
particular, the current Issues omission would fail a **current full-policy
postcheck**, but cannot establish that the historical helper reached that check.
No server-success response or timing assumption is inferred from aggregate
UNVERIFIED.

The public PATCH successful response contract and audit permissions/limits are
researched separately in
[staging-settings-patch-forensics.md](staging-settings-patch-forensics.md).
The published HTTP-200/object-result example matches the implemented validator;
no retrieved contract justifies accepting empty 204, inventing a propagation
deadline, or converting absent Issues to false. There is no demonstrated
response-shape source defect to fix without new evidence.

**Recommended next action:** one independently reviewed, strictly read-only
historical Audit Logs v2 query for the already reported 16:16:01–04 UTC helper
step, using the fixed covering interval 16:16:00–06 UTC on 2026-09-30. Privately
match only the exact PATCH method and staging script-settings URI. Output
closed receipt/status/action/completeness bins only; never actor/IP/token,
payload, arbitrary provider fields or raw rows. Confirm existing account-level
audit permission separately from Workers Scripts permission. Do not widen,
retry, paginate an incomplete first discriminator, query resource-change
payloads, or run a new settings mutation.

A positive unique matching audit record establishes a provider-reported write
in that interval and its reported outcome. Attribution to the helper additionally
depends on the external settings freeze or private actor/source correlation;
method/path/time uniqueness alone cannot exclude an out-of-band caller. Even
an attributed success cannot prove client parsing or present Issues-off.
Denied, missing, incomplete or zero matching audit evidence leaves the
historical request unresolved and is not permission to retry.

The concrete engineering issue demonstrated so far is **insufficient original
phase diagnostics**, not a proven settings correctness bug. Before any later
separately authorized mutation, use fixed phase labels for preflight completion,
logical PATCH boundary, accepted response and each postcheck. An emitted
"attempt started" label still does not prove server receipt; interruption may
occur between the label and transport. Preserve timeout/ambiguity/no-retry
semantics and the existing all-off gate. These instrumentation recommendations
are not implemented or authorized for live use by this follow-up.

## Evidence boundary

Public API schema was retrieved on 2026-09-30. Repository files inspected by
name before content: `ci.yml`, `require_trace_containment.py`, `pin_staging_mail.py`,
Mail TOML/checker and the existing readback/Queue rollout decisions. Parent's
reported live run results were reused; this investigation did not repeat them.
No academic result can establish this account's control-plane setting. The
relevant production pattern is separating immutable serving code from
non-versioned control state, and using explicit typed evidence for each.
