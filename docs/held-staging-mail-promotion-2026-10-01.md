# Held-only staging Mail promotion after main reconciliation

Date: 2026-10-01 local (observations around 2026-09-30 22:12 UTC).
Status: **actionable dependency handoff; rollout not authorized or executed**.
No local project test/build, provider mutation, mail send, Queue body read,
private artifact download, or raw/private log inspection was performed.
Investigation reused existing records before inspecting the relevant source;
new external reads were GitHub metadata, public documentation, public DNS and
the public staging health endpoint only.

## Decision

Reconcile the complete reviewed source onto main first, but **do not dispatch
`target=staging` merely because main is populated or source CI is green**.
The current rollout cannot pass its containment prerequisite. Its previous
settings correction failed effective-state acceptance; a successful read-only
diagnostic is not its missing immutable mutation attestation.

The shortest next discriminating operation is the exact Worker's official
Issues setting/onboarding page, read without opening occurrence/request details
or changing the setting. Missing API Issues state remains unknown, not enabled
or disabled. If the page supplies positive off evidence, record only the fixed
state, Worker/version identity, UTC and operator; separately review how that
independent evidence enters the machine gate. If it is ambiguous, obtain an
official provider clarification or separately approve a containment-only
deployment. Do not repeat either already-attempted PATCH or redeploy the current
Queue-bound source through an ad hoc command.

This is an evidence dependency, not a new architecture project. The existing
Queue-only trace design, direct-forward-only contact contract and send hold
remain the target. Main integration registers workflows; it does not deploy
code, adopt contacts, grant sending, attest privacy or publish a release.

## Bounded state and evidence inventory

| Item | Observation / contract | Remaining acceptance |
| --- | --- | --- |
| GitHub source snapshot | Remote main `c08a1b6bb6a7181a62d12d6ddd3a46babd4826be`; development branch `6cb7e091104d483b2720e77473dc2640adb0b117`; local inspected source `6bcf05c6e126faa95290f2c58b581792b63cb052` | Sources were moving under root coordination; settle and review final immutable SHA rather than treating these snapshots as a release pin |
| Workflow | `ci.yml`, ID `369045879`, active; main contents GET for this path returned 404 at inspection | Confirm file exists on reconciled default branch; dispatch still uses the reviewed development ref under existing guards |
| Current Mail version | Parent supplied fresh single-100 serving evidence for `c3f6401a-1e84-4f51-91df-ae77d90683e9` | Recheck immediately before any approved transition; source tip is not this deployed version |
| Current capture | Parent/Logs/traces false; Issues omitted; privacy **UNVERIFIED** | Positive effective Issues-off evidence, not omission interpretation |
| Attempted correction | [36761367007](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36761367007), attempt 1, failed; immutable SHA `daaab1f79cd985030d8d502fd647e16757673052` | PATCH accepted but no successful all-off attestation; do not rerun |
| Independent diagnostic | [36761475455](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36761475455), attempt 1, completed/success at same SHA | Job success describes categorical diagnosis; Issues remains unknown |
| Trace graph | Queue/sink source not deployed, per parent live evidence; repository variable-name listing returned `[]` | Inventory absence/ownership before create; not proof every similarly named provider resource is absent |
| Mail dependencies | Existing isolated Mail D1/R2, ingress, lifecycle consumer and synthetic Identity account have historical deployment/use evidence | Current exact dependency identities/capture and migration state must be checked for a new deployment |
| Staging DNS | Authoritative `jermaine.ns.cloudflare.com`: mail MX 3, mail TXT 1, bounce MX 3, bounce TXT 1, DKIM TXT 1, DMARC TXT 1; HTTPS `/health` 200 | Counts prove presence, not current TXT content, alignment, SMTP delivery or ownership isolation |
| Previous inbound acceptance | [36682429638](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36682429638), source `3dbc961`, Mail `a5429622-67ac-4570-b771-a50c3683e5d4`: native PKCE, real two-message SMTP-to-ZIP/semantic/search/delete and route cleanup | Genuine historical bounded acceptance, not current source/privacy/two-principal/outbound acceptance; do not erase it or repeat solely for progress |

Use [current Issues correction](staging-current-worker-issues-alternative.md),
[omission semantics](issues-false-omission-semantics-2026-10-01.md),
[direct-only API contract](direct-forward-api-deployment.md), and
[existing trace rollout](privacy-trace-sink-deployment.md) for underlying facts.
This handoff supersedes that rollout document's historical statement that source
pushes may redeploy staging services: current push/PR/checks are non-deploying.

## Exact target graph and source guards

```text
reviewed development ref + protected staging Environment
  -> hosted cli / worker / site / infra + synthetic OpenRouter contract
  -> immutable containment evidence + still-serving pre-Queue predecessor
  -> events/DLQ ownership -> Queue-only trace sink -> sink isolation pin
  -> Mail hold -> Sending privacy -> routing read -> containment recheck
  -> additive Mail D1 migrations -> new Mail runtime + matching TOML
  -> exact queue-api bindings / capture / api-only topology / sink / hold
  -> existing SMTP ingress -> existing Sending lifecycle consumer/subscription
  -> private Identity inbox only after all exact test routes are absent

trace events: amail-mail-staging -> amail-trace-events-staging
             -> amail-trace-sink-staging -> amail-trace-dlq-staging on failure
Sending events: exact mail-staging.moesegfault.dev subscription
               -> amail-sending-events-staging -> amail-events-staging
               -> amail-sending-events-dlq-staging on failure
```

These are separate Queues: trace envelopes are closed, privacy-safe typed data;
Sending event payloads can contain recipient/subject/SMTP data. Neither permits
public logs, payload polling, arbitrary export, purge or a diagnostic consumer.
Trace events/DLQ retain exactly 86,400 seconds. Events has exactly API producer,
one sink consumer, batch 10, wait 1,000 ms, retries 3, retry delay 30 s,
concurrency 2; DLQ has no producer/consumer attachment. No role producer is
accepted. Preserve existing four direct operational forwards and private
destination; do not deploy role monitoring or isolated role D1 as a prerequisite.

Staging Mail has exactly `MAIL_DB` -> `moesegfault-mail-staging`, `MAIL_BODIES`
-> `moesegfault-mail-raw-staging`, staging Email, staging issuer/client/domain,
and new `TRACE_EVENTS` -> the independently pinned staging events Queue.
`OFFICIAL_EMAIL` and production resources must remain absent. The new runtime
and its direct-only TOML must be deployed together: an old role-dependent
runtime without its old binding is unsupported.

The current `staging-worker`, `staging-trace-sink`, deployment helper and sink
canary explicitly require `refs/heads/codex/amail-v0.1.0`. Reconciliation onto
main **does not change those guards**. Run the reviewed development ref after
main registration, or separately review a coordinated branch-contract change;
do not dispatch on main and mistake skipped Mail jobs for a successful rollout.

`target=staging` also deploys the staging site independently after the site job.
Thus an otherwise rejected Mail rollout may still replace that site. It is not
a dry-run/preflight target. The Mail chain additionally replaces ingress,
lifecycle consumer and private inbox. Approve that entire bounded impact or
review a component target before use; do not silently imply API-only execution.

## Two source/provenance gaps to resolve before dispatch

1. **Containment evidence gap.** `require_trace_containment.py` accepts only
   `deploy-v1` or `settings-v1`. Deploy evidence needs a successful immutable
   first-attempt run and exact Mail deploy version output plus all-off historical
   TOML. Settings evidence needs the dedicated legacy correction job, one exact
   successful settings-v1 marker and unchanged c3f version. The current-Worker
   PATCH job is a different job/kind and failed; the successful diagnostic job,
   Audit page, Dashboard observation, source CI or mutable Variable cannot be
   substituted. A new evidence path requires explicit review and hosted tests.
2. **Historical versus target binding policy.** Current
   `expected_bindings(pre-queue)` derives a direct-only single-D1 contract from
   current TOML; `settings-v1` uses it on the old c3f version. Historical
   containment source `f3d389c` declares `ROLE_MONITOR` in staging in addition to
   `MAIL_DB`. The historical hosted operation also establishes that old exact
   contract matched real immutable version bindings (proof below), **not a new
   live read or current privacy acceptance**. Keep
   an exact independently reviewed predecessor policy separate from the future
   queue-api direct-only policy; do not permit arbitrary extra bindings or strip
   an old runtime capability before deploying the matching new runtime.

### Confirmed historical c3f binding evidence and minimal correction interface

This is stronger than inference from f3d TOML alone. The real hosted
current-resource operation [36761367007](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36761367007)
ran at immutable source `daaab1f79cd985030d8d502fd647e16757673052`, confirmed by
fresh run metadata. Its retained fixed phase evidence, already recorded in
[the operation record](staging-current-worker-issues-alternative.md#one-shot-current-resource-outcome-2026-10-01),
was `projection:ready serving_pin:before_match patch:accepted readback:checking`.
At that exact source, `apply_staging_current_worker_capture_off.apply()` reaches
`serving_pin=before_match` **only after**:

1. Exact current deployment is single-100 at c3f.
2. `bindings_match(fetch(..., versions/c3f), c3f)` returned true.
3. The current Worker projection passed and deployment was unchanged on a
   second GET.

At `daaab1f`, `pin_staging_mail.expected_bindings()` explicitly includes
`ROLE_MONITOR`, and `bindings_match` requires exact name/type/target and exact
total count. Therefore the historical real version-bound response matched
the following 14-binding pre-Queue contract; this is not a raw-record export:

| Binding(s) | Type and approved target |
| --- | --- |
| `MAIL_DB` | `d1`, `74f35f95-42ce-482c-86e6-dffbdd35cbbe` |
| `ROLE_MONITOR` | `d1`, `272e024c-453a-461b-bea0-c37a62c89d24` |
| `MAIL_BODIES` | `r2_bucket`, `moesegfault-mail-raw-staging` |
| `EMAIL` | `send_email`; no independently reported destination/sender value |
| `OPENROUTER_API_KEY`, `CF_EMAIL_ROUTING_TOKEN`, `INGRESS_SECRET` | Exactly three `secret_text` names; no secret bytes inspected/attested |
| `ADDRESS_DIAGNOSTICS` | `plain_text`, `v1` |
| `IDENTITY_ISSUER`, `OIDC_CLIENT_ID` | `plain_text`, `https://identity-staging.moesegfault.dev`, `amail-cli-staging` |
| `CF_ZONE_ID`, `MAIL_DOMAIN` | `plain_text`, `6edff81c6ed02f412e70868076411a5e`, `mail-staging.moesegfault.dev` |
| `EMAIL_INGRESS_WORKER_NAME`, `OPENROUTER_EMBEDDING_MODEL` | `plain_text`, `amail-inbound-staging`, `qwen/qwen3-embedding-8b` |

`TRACE_EVENTS` and `OFFICIAL_EMAIL` were absent under that exact comparison.
This proves the historical observed binding contract at the successful
pre-write bracket, even though the operation later failed privacy acceptance.
It does not prove later unaffected-state comparison, current secret bytes or
current capture. The parent supplied the same current serving version, not
a new independently inspected version-binding response in this investigation.

The current call chain is concrete:

```text
staging sink/API rollout
  -> require_trace_containment.verify(kind=settings-v1)
     -> immutable_evidence (fails today: no successful settings attestation)
     -> bindings_match(version=c3f, phase omitted)
        -> expected_bindings(pre-queue, current TOML)
           -> mail_resources requires len(d1_databases) == 1
           -> excludes historical ROLE_MONITOR
```

Once the immutable evidence gap is genuinely resolved, this second comparison
rejects the documented historical c3f predecessor. It is a temporal contract
mismatch, not permission to add an optional role binding to the new API.

**Recommended smallest source interface:** retain current direct-only
`expected_bindings()` and strict `queue-api` policy unchanged. Add one named,
internal historical contract factory/matcher, for example
`containment_predecessor_bindings()` and
`containment_bindings_match(version, expected_version)`. The latter accepts
only staging c3f and the exact 14-binding snapshot above, independently anchored
to immutable `daaab1f` evidence; no environment/dispatch-configurable binding
list or optional ROLE_MONITOR union. Extract the existing pure shape/name/type/
target comparison into an internal matcher receiving the already-selected
contract rather than duplicate parsing rules. Do not infer a contract from the
returned provider bindings or automatically fall back when target matching fails.

Call the explicit historical matcher at the settings-v1 branch of
`require_trace_containment.verify`, and all exact-c3f historical read/correction
helpers: `apply_staging_capture_off`,
`apply_staging_current_worker_capture_off`, and
`diagnose_staging_capture_preflight` (including its shape diagnostics' expected
list). These helpers are fixed historical operations; changing their checker
does **not** authorize rerunning their already-spent mutation. New deployment,
production graph checks, queue-api pin and direct-only resource config continue
to use the current target contract. Source search must identify any further
no-argument `bindings_match` historical caller before integration.

Required hosted synthetic regressions (no live operations):

- Fixed literal historical fixture, **not generated from the current TOML**,
  matches c3f; direct-only predecessor and queue-api fixture do not match it.
- Missing/extra/duplicate/renamed ROLE_MONITOR, wrong role or Mail D1 ID,
  production target, wrong version, extra TRACE_EVENTS or OFFICIAL_EMAIL,
  malformed/wrapped unknown bindings and secret-type substitution all reject.
- New direct-only queue-api accepts exactly MAIL_DB plus reviewed TRACE_EVENTS
  and rejects ROLE_MONITOR even when all other target values match.
- Changing current TOML cannot mutate the frozen historical contract; changing
  the frozen contract must fail its explicit provenance/config fixture.
- Settings-v1 caller selects only historical contract; ordinary/default and
  production callers do not acquire a permissive fallback. Historical helpers
  select the same exact contract both before and after their existing brackets.
- Correct historical bindings with missing/null/true Issues still fail the
  unchanged privacy predicate; failed/missing immutable settings marker still
  blocks before provider verification. Redacted-output tests retain fixed labels.

This slice repairs binding-policy compatibility only. It supplies neither a
successful settings attestation nor a new Issues-off proof. Review it separately
from any future privacy-evidence extension so a valid predecessor match cannot
accidentally reopen the independent privacy gate.

If an explicit containment-only redeploy becomes necessary, the required small
source slice is: a named guarded hosted target, one reviewed immutable source
whose actual Wrangler config has **no Queue producer** and explicit all-off
capture, exact source/config provenance, hold checks, private-secret cleanup,
redacted returned version and post-deploy strict pin. It must not provision
Queues, mutate routes, register addresses, send mail, deploy role/Identity/site,
or apply unrelated schema changes. The current deployment helper explicitly
requires queue-api and cannot already implement this path. Treat this as a
bounded implementation gap, not an executable command hidden in this document.
Preserve all user-facing handlers/contracts and the additive-data rollback
rules; never rewind the active branch or fake the old run's historical TOML.

## Ordered execution once those gates genuinely pass

1. **Settle source and writers.** Record final reviewed full SHA, green hosted
   source evidence, default-branch workflow registration and dispatch ref SHA.
   Freeze Mail/sink/Queue/settings/routing writers across workflows and
   out-of-band operators. Existing per-ref and per-job locks do not freeze all
   external writers or a separate canary lock. Stop if an acceptance run or
   disposable verification route is active. No public release/tag operation.
2. **Read exact live preconditions privately.** Same single-100 contained
   predecessor; independently accepted capture evidence; fixed staging D1/R2,
   Email/Ingress/Identity origins and migrations; global `held` and no separately
   authorized active one-use send experiment; preserved account/recipient holds;
   no contact adoption/attestation from this deployment. Check current Sending
   privacy and DNS values, routing token access, trace resource ownership and
   lifecycle subscription graph. Do not infer absent resources from failed GETs.
3. **Select immutable containment evidence.** Only a truly accepted evidence
   kind/run/version may be supplied. The old failed correction run is not that
   run. Check the predecessor binding issue above before spending a rollout.
4. **Approve and dispatch exactly once**, after the prerequisites, using the
   existing command shape below; record all input pins and resulting run ID.
   The protected staging Environment selects capabilities; values never go in
   inputs/logs. Its ordered sink -> Mail -> ingress -> events -> inbox chain
   performs held checks before graph/schema/provider changes and after readback.
5. **Persist graph identities.** Review only the exact
   `trace-queue-provision-staging-<run>-<attempt>` artifact containing non-secret
   system IDs. Pin exact Queue/DLQ IDs in project Variables for later canary
   preflight. Do not adopt existing resources by name. A partially created pair
   requires existing read-only `--phase recover`, not another blind dispatch.
6. **Accept the deployed graph before traffic.** Require new single-100 API and
   sink versions, exact queue-api binding list, API capture-off current-resource
   predicate, sink isolation, exact api-only Queue graph and final `held`.
   Record successful jobs/markers, exact source/version/resource pins and UTC.
   A returned deployment UUID or `/health` 200 is not these checks.
7. **Run existing no-send retained-record acceptance**, preflight first, then
   one approved canary on the same frozen versions. It logs in to the existing
   synthetic account, lists addresses and submits the reviewed anonymous marker
   denial; no mailbox creation, SMTP or Email Sending is required. Require
   whole-record forbidden-marker absence, valid causal roots and zero source
   API retention, with before/after serving/settings/graph checks. Record only
   fixed verdicts/pins. A safe custom JSON line alone does not pass privacy.
8. **Only then decide one source-relevant inbound regression**, if direct-only
   runtime/migration or ingestion changes warrant it. Use existing native PKCE,
   two synthetic SMTP fixtures, real ZIP/content/search oracle and exact
   route/message cleanup; keep public send held throughout. Previous acceptance
   remains valid for its old bounded deployment. No outbound canary, grant or
   new second principal is bundled into this promotion.

Command shapes are deliberately conditional, not permission to run now:

```powershell
gh workflow run ci.yml --ref codex/amail-v0.1.0 `
  -f target=staging -f confirm=RUN_STAGING_TRACE_SINK_ROLLOUT `
  -f trace_containment_run=<accepted-immutable-run> `
  -f trace_containment_kind=<reviewed-supported-kind> `
  -f expected_worker_version=<accepted-contained-predecessor>

gh workflow run ci.yml --ref codex/amail-v0.1.0 `
  -f target=staging-trace-sink-canary -f trace_mode=preflight `
  -f expected_worker_version=<new-api-version> `
  -f trace_sink_version=<new-sink-version>

gh workflow run ci.yml --ref codex/amail-v0.1.0 `
  -f target=staging-trace-sink-canary -f trace_mode=canary `
  -f confirm=RUN_STAGING_TRACE_SINK_CANARY `
  -f expected_worker_version=<same-frozen-api-version> `
  -f trace_sink_version=<same-frozen-sink-version>
```

## Failure and privacy ownership

Keep global held; do not issue a one-use grant, clear account/recipient holds,
set release attestations or adopt contacts to make deployment pass.
`check_send_hold.py` proves only the exact global row held; it does not revoke
an existing one-use grant or recall an in-flight provider send. Any preexisting
ambiguous send remains under its original private reconciliation owner.

A sink failure stops before API replacement. An ambiguous create/deploy stops
without automatic write retry. Recover exact IDs/versions privately; never print
provider errors, SQL rows, Identity subjects, destination addresses, MIME, ZIP,
URLs with markers, Queue payloads or raw retained records. Maintain secrets in
restricted step memory and root-local `.temp` files with exact cleanup; no
business-data artifacts or development-machine test/build work.

After API replacement, capture the returned version even if later verification
fails, freeze additional writers, and read back the actual graph. Rollback must
restore a **reviewed capture-off** compatible runtime/config pair, keep additive
Mail migrations/data and preserve role storage/direct forwards. Never restore
logging-on source, fake a role lease, purge trace Queues/DLQs or consume their
bodies. A whole-record privacy failure closes acceptance and prompts a bounded
source/sink diagnosis, not another real mail experiment.

## External operational contracts consulted

- [GitHub manual workflow dispatch](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow): workflow registration on the default branch and explicit alternate `--ref` are distinct requirements.
- [Cloudflare Custom Domains](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/): Worker attachment creates DNS/certificate handling; no placeholder A/CNAME or repeated mail-domain onboarding is needed here.
- [Issues public-contract investigation](issues-false-omission-semantics-2026-10-01.md): official response optionality does not define omitted as false; Issues capture is independent. Its pinned official raw docs were reused because the public Issues web reader remained inaccessible.

Academic novelty is not a prerequisite for this operational transition. The
informative experiment is positive evidence for the actual independent capture
state and later a whole-record deployed canary, not another benchmark, new
transport abstraction or generalized migration framework.
