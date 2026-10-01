# Code-free staging Issues create discriminator

Date: 2026-10-01. Status: **source integrated; first live attempt UNVERIFIED,
stopped before create**. See the [bounded live outcome](#first-live-outcome-2026-10-01)
for current evidence. The implementation-stage record below is historical:
it was based on main `a4fc6160ca6b771da6351268d1a96af4c4a616dc` in an isolated
root-local worktree; no local project test/build, provider request/mutation,
workflow dispatch, Worker creation, code upload, Mail invocation, or push was
performed during that implementation stage.

## First live outcome (2026-10-01)

| Evidence class | Exact evidence | Bounded conclusion |
| --- | --- | --- |
| Integrated source | [PR #8](https://github.com/kleedaisuki/moesegfault-amail/pull/8), main [`3cc82499ad2fe7ee2c0f8008fedf1edc5085d61c`](https://github.com/kleedaisuki/moesegfault-amail/commit/3cc82499ad2fe7ee2c0f8008fedf1edc5085d61c); exact-main six-job source CI [36793347106](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36793347106) succeeded | Source validation only; no live Issues or privacy acceptance follows. |
| First manual live attempt | [36793625509, attempt 1](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36793625509/attempts/1), at that exact main SHA | Credential-free guard/tests succeeded; provider operation step failed with the fixed UNVERIFIED result below. |
| Recovery and approval retirement | Same run's [artifact inventory](https://api.github.com/repos/kleedaisuki/moesegfault-amail/actions/runs/36793625509/artifacts) had `total_count=0`; repository variable `STAGING_ISSUES_CREATE_REVIEWED_SHA` was removed and independently verified absent | No Worker ID or recovery artifact was produced. Approval is retired, not permission for another dispatch. |

```text
staging_issues_create_probe=UNVERIFIED
staging_issues_create_phases=absence:checking original_pin:before_match hold:before_match create:skipped identity:skipped isolation:skipped readback:skipped recovery:skipped
```

The phase boundary is decisive: the first attempt stopped during fixed-name
absence checking, **before the Worker-create POST**. No Worker was created by
this attempt. The original pin and hold matched before that phase; no completed
after-state bracket, fresh-Worker identity/isolation, or Issues readback was
obtained. Artifact absence is consistent with skipped creation/recovery, not
independent proof of provider namespace absence.

This result does **not** establish provider root cause, a permission defect,
Issues true/false/omission, or original Mail privacy. Do not reinterpret
`absence:checking` as confirmed absence or weaken the fail-closed gate. Keep
public sending and all previously held release gates unchanged. **No unchanged
retry, rerun, alternate name, or fresh dispatch is authorized.** Any next
investigation requires separately reviewed phase-discriminating evidence and
an explicit new decision, not repetition of this attempt.

## Purpose and evidence boundary

Create exactly one fixed Worker, `amail-issues-contract-staging`, **without code**,
then read its current settings independently by returned immutable ID. Classify
`issues.enabled=false`, omitted Issues, true, or an unverified result. The
creation response is identity/write-acceptance evidence only, never current
capture evidence. This implementation does not relax the original Mail capture
gate, attach a Queue, release sending, promote a shadow, or authorize migration.

**A shadow's explicit false does not prove `amail-mail-staging` private.** Its
evidence belongs only to that fresh code-free identity at that observation.
Omission is unknown, not false. Successful workflow execution with `omitted`
means the bounded experiment completed, not containment acceptance. No runtime
retention claim can follow from a Worker with no executable version.

The initial design is recorded in
[`staging-issues-no-route-discriminator-2026-10-01.md`](staging-issues-no-route-discriminator-2026-10-01.md)
(design commit `3424a56568bd5f06f76801422e57fb1263f75c53`, cherry-picked without
its older primary-branch ancestors into this isolated main-based tree). Reuse
the [held Mail promotion](held-staging-mail-promotion-2026-10-01.md)
and [omission semantics](issues-false-omission-semantics-2026-10-01.md).

## Material revision: documented bounded absence rather than guessed 404

The official [Get Worker schema](https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/methods/get/)
does not document an endpoint-specific name-not-found error code. A 403, timeout,
arbitrary 404, malformed body, legacy error code, or unavailable exact-name GET
must not be permission to create. In particular, no guessed `10007` rule is
implemented. Shipping a dormant guessed gate would not produce a trustworthy
discriminator.

Under parent coordination, this implementation **replaces**, rather than falls
back from, the design's exact-name GET absence premise with the official
[List Workers](https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/methods/list/)
pagination contract. That contract supports order/name and page/per-page, but
does not offer an exact-name filter.

- Read `per_page=100`, `order_by=name`, `order=asc`, at most five pages.
- Require literal integer page/per-page/count/total-count/total-pages metadata,
  mathematically consistent counts and complete pages. A zero-total response
  can advertise zero or one total page; neither implies a nonempty inventory.
- Require stable totals across pages and unique typed IDs/names. Missing
  metadata, an oversized response, more than 500 Workers, duplicate identities,
  changed totals, malformed entries, errors or a partial page stop before POST.
- Examine only fixed-name equality in memory. No suffix search, adoption,
  replacement, name generation, arbitrary target input, or list body output.
- Presence of the fixed name emits `absence:name_occupied`, then stops. No
  existing resource is read for adoption, patched, deployed, or deleted.

Pagination is not a transactional snapshot. Stable counts cannot rule out
same-count concurrent replacement. The actual external account/Worker writer
freeze is therefore a **necessary assumption**, not a capability supplied by
GitHub concurrency. Name conflict or any ambiguous POST stops without a second
creation or alternate name. If complete namespace metadata is unavailable, the
operation remains UNVERIFIED; do not weaken it into an error-as-absence rule.

## Fixed request and operation sequence

The official [new Workers API announcement](https://developers.cloudflare.com/changelog/post/2025-09-03-new-workers-api/)
permits creating a Worker before uploading code. The
[Create Worker API](https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/methods/create/)
accepts the six fields used here:

```json
{
  "name": "amail-issues-contract-staging",
  "logpush": false,
  "tags": [],
  "tail_consumers": [],
  "subdomain": {"enabled": false, "previews_enabled": false},
  "observability": {
    "enabled": false,
    "head_sampling_rate": 1,
    "redact_query_string": true,
    "logs": {"enabled": false, "invocation_logs": false},
    "traces": {"enabled": false},
    "issues": {"enabled": false}
  }
}
```

There are no modules, version, preview template, bindings, secrets, route,
Custom Domain, trigger, builds integration, Mail data, Email/Queue capability,
or public request. Sampling one is a retained preference; the explicit switches
turn capture off. The helper does not copy the original Worker's configuration.

```text
credential-free immutable dispatch guard + synthetic tests
  -> protected staging approval + shared writer concurrency
  -> root-local exclusive recovery artifact destination validation
  -> original c3f single-100 + version/bindings/current-Worker snapshot
  -> held global sending + no usable one-use canary (aggregate SELECT only)
  -> bounded complete fixed-name absence
  -> ONE fixed POST; valid returned ID/name -> non-secret resource pin saved
  -> ONE independent current GET addressed by returned immutable ID
  -> explicit off URL flags + no inbound references/exports/deployment
  -> independent zero uploaded versions read
  -> Issues classification from raw current JSON
  -> unchanged original deployment/version/bindings/current-Worker snapshot
  -> recheck held global sending + idle one-use canary
  -> fixed bins + allowlisted non-secret recovery artifact; STOP
```

The [List Worker Versions API](https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/subresources/versions/methods/list/)
must return an empty result with typed zero-total metadata. `deployed_on=null`
alone proves only never-deployed, not absence of uploaded executable versions.
Both checks are required. No second current GET, waiting loop, retry, PATCH,
deployment, invocation, default/preview URL request, routing write, trigger
read/write, rollback or automatic DELETE exists.

Current readback requires explicit parent/Logs/traces false, query redaction
true, sampling one, invocation logging false, Logpush false and empty tails.
Recognized optional retention preferences do not override disabled capture
switches, but external destinations and unknown observation mechanisms fail
closed. Issues may be missing (including a missing enabled child), literal
false, or literal true; null, numeric/string flags, unknown Issues fields and
malformed containers are UNVERIFIED. Capture policy validation reuses the
existing `capture_disabled` contract with a private temporary Issues-only
normalization; that normalized object never becomes provider evidence.

Isolation requires both writable subdomain flags explicitly false, empty known
inbound reference lists, no deployment, no preview configuration, no uploaded
versions, empty tags, and no unknown top-level capability. URL/suffix response
strings may remain even when disabled; their presence does not mean a live
endpoint, as the current Get Worker schema states. These checks are confined to
the code-free discriminator. They are **not sufficient authorization to upload
code** or bypass newer URL/event-product isolation checks for a future slice.

Original Mail is read, not altered. For a completed observation, the same original Worker object, exact
version/bindings response and single-100 serving identity must bracket the
probe. Hold reads use only fixed aggregate counts from `send_policy` and
`send_release_gates`. No SQL rows containing recipients/subjects/principals are
read or persisted. The SQL query uses D1's POST query endpoint but contains only
SELECTs and makes no database mutation. No routing, zone or ingress write API
exists in the helper. Original domain/ingress cannot be claimed independently
re-attested here: external writer freeze and absence of any such mutation path
are the applicable assumptions; current Worker inbound references/bindings are
included in the unchanged snapshot. A failure before completing classification
does not claim a completed original/hold bracket: phase labels retain
`before_match` or `checking_after`, the primary result is UNVERIFIED, and the
operator must retain the external freeze and independently resolve that state.

## Manual workflow contract and launch prerequisites

Files:

- `.github/workflows/staging-issues-create-probe.yml`
- `infra/provider/staging_issues_create_probe.py`
- `infra/tests/test_staging_issues_create_probe.py`

The workflow is manual-only, fixed repository/main ref, first attempt only. A
credential-free `guard` job precedes the protected `staging` job. Guard and
synthetic source tests must pass before the provider job can start. Provider
secrets appear only in its single operation step. The live job repeats the
guard after Environment approval and holds `staging-native-mail-acceptance`
with cancellation disabled throughout the experiment. This excludes cooperating
repository jobs, **not** dashboards, API clients, automatic Builds or other
repositories.

Required independently approved inputs/configuration, none created by source
integration:

| Coordinate | Contract |
| --- | --- |
| `confirm` | `CREATE_STAGING_CODE_FREE_ISSUES_PROBE_ONCE` |
| `writer_freeze` | `FREEZE_STAGING_MAIL_SETTINGS_ROUTING_AND_PROBE_WRITERS`; must describe a real, externally established freeze, not a magic string |
| `reviewed_sha` | Exact independently reviewed immutable main SHA |
| Repository variable `STAGING_ISSUES_CREATE_REVIEWED_SHA` | Independent approval pin, exactly equal to the input and `GITHUB_SHA`; missing fails the credential-free guard |
| Staging secrets | Exact account ID and reviewed Cloudflare API token, sufficient for Workers read/create and fixed Mail D1 aggregate SELECT; no zone/routing token |
| Environment | Protected staging reviewers and actual external account/Mail/settings/routing/probe writer freeze |
| Original/hold | Approved c3f single-100 original Mail binding contract, global send hold, no usable one-use canary |

No debug runner/step logging is accepted. No arbitrary resource ID, endpoint,
Worker name, code or account target input is supplied. Missing approval pins or
a safe recovery artifact destination fails closed. Source integration does not constitute
these prerequisites or operation approval.

GitHub `run_attempt=1` prohibits rerunning an attempt; it is not an account-wide
once-ever ledger. **Do not create another dispatch** after an attempted POST,
even if its result is unknown or a later inventory appears empty. Preserve the
original run and retire/clear its approval variable under operator control.
Do not use a new SHA/name/run as a retry workaround. A new authorized experiment
would require an explicit reviewed protocol and recovery decision, outside this
workflow.

## Output, recovery and bounded exact-identity retirement

Output consists only of:

```text
staging_issues_create_probe=explicit_off|omitted|true|UNVERIFIED
staging_issues_create_phases=absence:... original_pin:... hold:... create:... identity:... isolation:... readback:... recovery:...
```

`explicit_off` and `omitted` return success because they are discriminating
observations after a stable bracket, not original-resource attestations. True
returns failure. Any schema/transport/identity/isolation/bracket failure prints
UNVERIFIED, with only already completed/attempted phase bins. All exceptions are
suppressed without strings, tracebacks, URLs or provider bodies.

Recovery is intentionally minimal. The fixed code-free resource name and
immutable UUID/opaque ID are system identifiers, not email, request content,
credentials, account IDs, or secrets. A single exclusive-create
`.temp/issues-create-probe/resource.json` contains **only** fixed name, validated
returned immutable Worker ID, run, attempt, reviewed SHA, observation UTC,
workflow and repository. It is saved immediately after successful identity
validation and **before** independent readback/isolation can fail. No generic
escrow, public-key provisioning, cryptographic subprocess, dependency, or new
decryption/recovery protocol is needed for these non-secret coordinates.

The file must not contain raw API objects, arbitrary key/value, reference ID,
provider error, URL, account identifier, binding, header, mail field or SQL row.
Only the actual fixed allowlist is serialized; duplicate JSON keys, nonfinite
constants and provider bodies are never persisted. Recovery directories reject
symlink/junction ancestors and preexisting material; exclusive creation prevents
replacing an existing record.

The always-run upload targets **only** that exact JSON filename, with seven-day
retention, overwrite disabled, and explicit `include-hidden-files=true` because
the reviewed path is beneath `.temp`. The
[official upload-artifact contract](https://github.com/actions/upload-artifact#inputs)
defaults to excluding hidden files; a broad directory/glob is not used.
GitHub artifact access requires authentication, but a public
repository artifact is **not** represented as confidential or owner-only.
These approved non-secret recovery pins are deliberately safe under repository
read access. No privacy boundary depends on hiding them. GitHub metadata already
provides run/SHA/start-window when an attempted POST yields no reliable resource
ID, so a second encrypted intent artifact would add machinery rather than
ownership authority. Artifact upload failure or missing ID is still unresolved;
the probe is not automatically deleted. Retain the immutable artifact/run
coordinates in the operator record before expiry.

**No retirement capability is bundled into this first discriminator.** A safe
later exact-identity retirement plan is:

1. Stop new dispatches and keep the external freeze. Retrieve only the exact
   original system-ID artifact in the approved operator process; verify
   repository/workflow/run/attempt/SHA, fixed name and artifact identity.
2. If no validated resource ID survived, or POST/identity/artifact outcome is ambiguous, do
   not infer ownership from name, list/suffix search, or absence. Seek bounded
   operator/provider recovery. No name-only delete, forced delete or second
   create is permitted.
3. With a successfully recovered valid resource ID, obtain a fresh current GET
   **by that immutable ID**, require same fixed name and identity, preserve
   recovery evidence, require empty references, disabled URL flags and no code
   or deployment. If it gained code/references/capability or was renamed, stop;
   do not detach other resources or delete a newly changed identity.
4. Separately approve exactly one
   [Delete Worker](https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/methods/delete/)
   addressed by that immutable ID with force deletion disabled (the helper has
   no DELETE path). Recheck original pin and hold. Provider failure or an
   ambiguous delete remains unresolved; do not retry or reinterpret arbitrary
   404 as confirmed deletion.
5. Require separately reviewed positive retirement evidence/provider contract.
   The generic GET error schema is still not an automatic deletion attestation.
   Record only fixed retirement status and approved recovery coordinates.

The fixed resource deliberately survives the first experiment, including a
true/omitted result. It has no executable version and cannot receive business
data. Never delete in `finally`; that could erase the only recoverable identity
of a partially accepted operation and destroy evidence needed for support.

## Synthetic acceptance and next decision

Authored tests cover body projection, independent false/omitted/true evidence,
malformed Issues, unknown capture/export/capability fields, both URL flags,
references, deployment and uploaded-code absence, identity mismatch, complete
pagination and inconsistent/oversized inventories, occupied names, transport
failures, one POST/no replay, allowlisted non-secret ID persistence, changed original
pin/hold, provenance/debug guards, raw JSON duplicate/nonfinite/body bounds,
redirect rejection, fixed categorical output and manual workflow dependencies.

Hosted verification command (not run locally during implementation):

```sh
python -m unittest discover -s infra/tests -p 'test_staging_issues_create_probe.py' -v
```

| Result | Interpretation | Allowed next decision |
| --- | --- | --- |
| explicit_off | This account/API represented off on this fresh code-free identity at that instant | Consider a separately reviewed inert no-route deployment; never infer original Mail privacy |
| omitted | Omission is not confined to the original Mail PATCH path | Stop experiments; offer zero-business-data reproduction to provider support |
| true | Requested false and independent read disagree | Keep isolated and escalate; no code/Mail capability |
| UNVERIFIED | Discriminator lacks trustworthy evidence | Preserve run/resource pins; bounded private recovery, no replay |

The source-level milestone and first live outcome are distinguished above.
The live attempt did not reach any classification branch except UNVERIFIED;
the other table rows remain prospective protocol semantics, not observations.
Any further operation requires a separately reviewed decision and fresh
authorization; the retired approval does not carry forward.

## Failure localization of run 36793625509 (2026-10-01)

**Conclusion: the first attempt stopped inside the namespace-absence check,
not inside Worker creation or Issues readback. The exact failed assertion or
transport outcome cannot be recovered from the deliberately categorical logs.**
No repeat or provider request was performed for this analysis. The evidence is
the [first run](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36793625509)
and source at `3cc82499ad2fe7ee2c0f8008fedf1edc5085d61c`.

The credential-free contract job passed. The provider job's guarded invocation
at 23:56:33 UTC ended at 23:56:36 UTC with:

```text
staging_issues_create_probe=UNVERIFIED
staging_issues_create_phases=absence:checking original_pin:before_match hold:before_match create:skipped identity:skipped isolation:skipped readback:skipped recovery:skipped
```

Tracing `probe` -> `name_absent` -> `Client.workers_page` -> `_request` shows:

- The original exact serving/binding/current-resource comparison and aggregate
  held/idle checks completed before the inventory check began. Those are
  time-local checks, not indefinite guarantees or an Issues-off attestation.
- `create:attempted` is assigned only after `name_absent` returns true. Thus the
  probe did not issue its Worker-create POST. D1's earlier read-only SQL uses
  HTTP POST, so saying *no POST of any kind* would be inaccurate.
- `name_occupied` would be assigned if a valid inventory contained the fixed
  name. It was not emitted. This does **not** prove the name absent: malformed
  pagination/identity or transport failure can stop before name detection.
- An exception somewhere within `name_absent` escaped into `main`'s broad,
  privacy-preserving exception handler. Neither page number, HTTP status,
  assertion identity, response size nor exception class survives in the output.
  A roughly three-second duration does not establish a single successful page
  or rule out later-page failure.

### Competing explanations, not established causes

| Candidate | Why it fits the observed phase | What current evidence says |
| --- | --- | --- |
| List-specific HTTP rejection, redirect, transport or timeout | `_request` fails before inventory validation | Earlier successful current-Worker GET does not prove List access; no status was retained |
| Response decoding/envelope rejection | Bounded bytes, duplicate JSON keys, nonfinite values, successful envelope and empty errors are required | No raw payload/size/category was retained; unknown |
| Missing or differently represented pagination metadata | All five metadata fields must be Python integers and internally consistent | Plausible contract strictness mismatch: official metadata fields are optional; not a demonstrated live mismatch |
| Inventory outside safety bounds or inconsistent across pages | More than 500 Workers, changed totals, incomplete count/pages fail closed | No count/page diagnostics retained; unknown |
| Item identity/name or duplicate rejection | Every returned item needs a bounded valid ID/name; IDs and names must be unique | No item diagnostics retained; unknown |

The official [List Workers API](https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/methods/list/)
inspected on 2026-10-01 accepts sorting by name and a page size of 100. It marks
`result_info` and its count/page/page-size/total fields optional. Consequently,
the helper requests a documented query but imposes **stronger absence-proof
requirements than the published minimum response schema**. Failing those
requirements is a valid fail-closed stop, not proof of a provider bug, missing
permission, or a reason to accept partial inventory. The illustrative response
example is not observed account data and cannot diagnose this run.

### One minimal discriminating next step (proposal only)

If inventory diagnosis is still worth pursuing, separately review one **read-only
first-page List request** with the same documented query and credential context;
no creation, automatic pagination, dispatch replay, settings write or relaxed
absence acceptance. Retain only a fixed enum for HTTP/transport versus decoding
versus metadata versus item-validation failure, bounded response-size category,
and allowlisted metadata-presence/type/consistency booleans. Do not emit worker
names, IDs, URLs, raw bodies, provider error text or credentials. Hosted synthetic
checks must verify that sensitive sentinel fixtures cannot escape before a
credential-bearing diagnostic is authorized. This is not implemented here.

That single diagnostic can distinguish several competing explanations, but
cannot establish complete absence or any Issues state. If page one is valid or
still uninformative, **stop rather than walking more pages, trying another token,
changing the proof rules or creating a replacement resource**. The remaining
route is a resource-bound Dashboard/provider clarification already identified
above. No unchanged rerun of 36793625509 is justified by this analysis.
