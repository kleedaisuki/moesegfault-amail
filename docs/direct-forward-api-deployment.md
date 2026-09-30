# Direct-forward-only Mail API deployment contract

Date: 2026-10-01. Status: **conditional source implementation; not deployment,
operational adoption, human attestation, or public-send authorization**.
No local tests/builds, provider calls, deployment, routing mutation or mail send
were performed for this configuration change. All public sending stays held.

## Ownership and exact topology

The [v0.1 complexity decision](direct-forward-role-release-gate-architecture.md#complexity-decision-v01-is-direct-forward-only)
selects one direct-forward contract, not a selectable direct/Worker mode.
The Mail API's contact policy, observation health and attestation identity live
in `MAIL_DB`. Production and staging each bind only their existing Mail D1;
neither API binds `ROLE_MONITOR` or imports its lease. Missing contact adoption,
freshness, human commitment or release evidence denies public sending.

| Surface | v0.1 contract | Migration effect |
| --- | --- | --- |
| Mail API D1 | Exactly `MAIL_DB`, independently configured per realm | Remove API access to isolated role D1 only after the runtime no longer reads it |
| Four operational contacts | Existing Cloudflare-managed direct forwards to the confidential destination | No routing write, receipt replay, destination change or Wrangler-owned addresses |
| Trace events | Exact API producer -> existing events Queue -> private queue-only sink | Keep `api-only`; do not accept a role producer as an arbitrary extra |
| Role Worker / isolated role D1 | Dormant implementation, outside v0.1 admission | No deletion, migration, deployment or fake lease; source existence is not active-graph acceptance |
| HTTP, R2, Email, search Cron | Existing Mail realm bindings and routes | No external API/protocol or user-mail topology change |

The sink still has one consumer per realm, batch 10, wait one second, three
retries, retry delay 30 seconds, concurrency two and the existing realm DLQ.
Its private retention boundary and all API capture-off settings are unchanged.
TOML proves intended attachments only: independent hosted readback must prove
the actual **exact API-only** producer/consumer graph and stable serving pins.
The dormant role TOML still declares its future producer; it must not be deployed
into this graph by a leftover role-rollout target.

## Held rollout and rollback

1. Keep global public-send hold and all account/recipient holds. Do not translate
   an old role lease or historical `abuse_contact_verified` boolean into a new
   accepted direct contract. Owner coverage for Inbox and Junk and Cloudflare's
   response obligation remains a separate explicit adoption/attestation.
2. Independently review and run hosted source contracts for the additive Mail
   migration, runtime/operator/release predicates, configuration and workflows.
   Reconcile the staging binding pin and production graph bootstrap/maintenance
   checks with a strict `api-only` lifecycle that does not depend on role D1.
   Do not bypass a failing old role prerequisite and call that acceptance.
3. Through a separately authorized held rollout, apply the additive Mail
   migration and deploy the runtime **together with** this TOML. Deploying old
   role-dependent code without its binding is unsupported. Read back exact
   immutable version bindings, capture-off settings and Queue identities before
   claiming the API/sink graph accepted. Preserve all four direct rules.
4. Configuration-health success permits neither automatic global allow nor a
   human attestation. Public release still requires the exact adopted contract,
   fresh bounded observation and all independent release evidence. This document
   grants none of those permissions.
5. Rollback is held and reviewed: retain additive Mail data, never destroy role
   storage, and restore an older runtime only with its matching old TOML and
   independent dependency evidence. An absent/expired genuine role lease must
   keep that old runtime denied; never populate one from direct-forward reads.

Already in-flight provider sends cannot be recalled by removing a binding or
holding D1 state. Preserve existing ambiguous-delivery/idempotency handling.

## Evidence and source references

`infra/tests/test_direct_forward_api_config.py` guards the source D1 shape,
realm separation, unchanged API/sink Queue parameters, capture-off settings and
absence of Wrangler-owned operational addresses. It does not inspect live
Cloudflare rules or prove that a human reviews mail. It was authored but not
executed locally, in accordance with this assignment's hosted-only validation.

Cloudflare describes bindings as runtime resource capabilities and notes that
bindings are non-inheritable per environment; both realms are therefore explicit.
References: [Wrangler configuration](https://developers.cloudflare.com/workers/wrangler/configuration/),
[bindings](https://developers.cloudflare.com/workers/runtime-apis/bindings/),
[Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/).
The existing privacy contract takes precedence over generic observability advice.

## Active graph gate interfaces

`pin_staging_mail.py` now derives the sole `MAIL_DB` and `MAIL_BODIES` resource
by their exact binding names. Its config guard rejects missing, duplicate,
additional or renamed D1/R2 entries and malformed D1 IDs; immutable deployed
bindings must still equal the reviewed realm's complete allowlist. Removing
`ROLE_MONITOR` never permits an arbitrary substitute database. `pre-queue`
remains the strict current direct-only pin phase, not an optional-bindings variant; the
active deployed graph uses `queue-api` and the exact events Queue ID.

The active production interfaces are:

| Stage | Command / confirmation | Required contract |
| --- | --- | --- |
| First preparation | `prepare_production_graph.py --phase bootstrap`; `RUN_PRODUCTION_API_ONLY_BOOTSTRAP` | Main branch, writer freeze, held send/unset contact attestation, successful complete API/role absence inventory, four unchanged verified direct forwards, reviewed Mail resource config |
| Maintenance preparation | `prepare_production_graph.py --phase api-only-maintenance`; `RUN_PRODUCTION_API_ONLY_MAINTENANCE` | Main branch, writer freeze, full strict current api-only graph |
| Pre/post replacement or bootstrap post-deploy | `check_production_role_graph.py --phase api-only` | Exact single-100 API/sink version pins; distinct reviewed Queue/DLQ IDs; `AMAIL_TRACE_TOPOLOGY=api-only`; exactly one API producer and private sink; independent API and sink capture-off; role Worker absent; held policy; four exact unchanged forwards |

No active command reads isolated role D1 schema, arrival state, health or lease.
No role Worker version pin is required: a nonempty role version or nonzero
role-routed count is rejected as contradictory input, not silently ignored.
Provider role absence is required to rule out accidental active infrastructure,
but no role Worker is installed or required. The exact API-only Queue readback
independently rejects any role/unknown/duplicate producer. Unrelated staging
resources remain preserved; no retirement/deletion is authorized here.

The graph checker brackets API/sink deployments, Queue ownership, role absence,
direct-forward shapes and held policy. It emits only fixed outcome labels; all
provider bodies, bindings and destination values stay private. These are bounded
observations, not a provider/D1 transaction or proof of human Inbox attention.
The existing Gray Failure lesson applies: configuration health does not prove
the outcome users rely on; retained-record privacy and intervention evidence
remain separate. See [Huang et al., HotOS 2017](https://www.microsoft.com/en-us/research/publication/gray-failure-achilles-heel-cloud-scale-systems/)
and the [direct-only architecture decision](direct-forward-role-release-gate-architecture.md).

Historical `before`/`after`/`maintenance` graph helpers retain their strict role
schema checks for separately scoped future research. They cannot prepare current
production promotion: `prepare_production_graph.py` rejects
`api-role-maintenance` and its old confirmation. The production role-rollout
workflow must also be disabled, not simply hidden from the default dispatch.

### Coordinated CI integration contract

The following contract is wired by the separate CI integration change described
below. It defines source acceptance requirements, not authorization to dispatch:

1. Replace every active `production-api-role-maintenance` target/condition with
   `production-api-only-maintenance`, including build dependencies and shared
   workflow-level `amail-production-graph-writer` concurrency. Keep non-canceling
   production writer serialization and the external-writer freeze requirement.
2. Set both production sink and Mail job topology to literal `api-only`; remove
   role version and routed-count environment inputs from these jobs. Maintenance
   confirmation becomes `RUN_PRODUCTION_API_ONLY_MAINTENANCE` and preparation
   phase becomes `api-only-maintenance`.
3. In `deploy-trace-sink`, only bootstrap uses
   `ensure_trace_queues.py --phase queues --topology api-only`. Maintenance uses
   `--phase readback --topology api-only` and preserves the exact configured
   Queue/DLQ identities, never provision/recover/recreate. Old/new sink and Mail
   replacement rechecks use `check_production_role_graph.py --phase api-only`.
4. Bootstrap post-Mail deployment also uses `--phase api-only`, with captured
   new API/sink version IDs and step-linked Queue/DLQ outputs. Do not pass
   `--lifecycle first-bootstrap` or `--migrated`, apply isolated-role migrations,
   or deploy a role producer as part of either current path. Emit the existing
   exact `production_trace_graph_attestation=api-only-v1` marker after successful
   full graph readback, preserving evidence-consumer meaning for either path.
5. Remove the executable production role rollout workflow
   `deploy-role-monitor-production.yml` and the `staging-role-monitor` deploy job
   from active CI. Preserve historical code, documentation and Git history, not
   a selectable disabled second product mode. Staging research is outside this
   promotion, not implicitly accepted by it.
6. Update `infra/tests/test_production_role_workflow.py`: replace the old target
   assertion with `production-api-only-maintenance`; replace required
   `--phase readback --topology api-role` with strict `api-only`; assert all
   current graph checks use `--phase api-only` and no role D1 migration/producer
   occurs. Replace old executable production-role ordering assertions with a
   fail-closed workflow/job-absence assertion. Preserve writer-lock, dispatch-limit,
   no-routing-write, and independent evidence assertions.

`infra/tests/test_production_api_only_graph.py` contains synthetic behavioral
contracts for the direct graph/preparation and named resource guard: successful
bootstrap and maintenance without role storage reads; exact Mail D1 identity;
rejection of unexpected role bindings, contradictory role inputs, missing pins,
Queue drift, failed role-absence proof, hold failure, deployment/forward changes
and independent API/sink privacy failure. These tests were authored but **not
run locally**; hosted execution and independent review are required before any
operational adoption. No provider mutation, deployment or send was performed.

## CI source integration and operational boundary

The coordinated workflow change consumes graph commit `f62a1d9`, direct-contact
gate/hold readback commit `a93fe58`, and realm-safe deployment wrapper commit
`d3f8eba`. It changes no user-facing CLI command or wire protocol.

| Surface | Integrated source behavior | What it does not establish |
| --- | --- | --- |
| Production maintenance | One `production-api-only-maintenance` target; explicit `api-only-maintenance` preparation; strict readback preserves configured Queue/DLQ IDs; old/new sink and API use the same `--phase api-only` gate | No queue recreation, role lease, role D1 migration, direct-contact adoption, or public-send allow |
| Production bootstrap | Explicit existing bootstrap target; bootstrap-only Queue provisioning; postdeploy exact graph marker follows the API/sink/bindings/capture/hold/four-forward guard | No retained-record privacy acceptance or truthful human operational attestation from configuration alone |
| Staging promotion | Existing confirmation/containment gates; global hold before Queue, provider or schema changes; redacted exact new Mail version capture; `queue-api` immutable binding pin with step-linked Queue ID; exact API-only Queue ownership and independently pinned sink privacy; final held readback | No staging role deployment, synthetic receipt replay, contact policy adoption, or permission to send publicly |
| Separate staging pin | `staging-serving-pin` now explicitly requests `--phase queue-api` and the reviewed staging Queue ID | No acceptance of historical `pre-queue` as the current active API-only graph |
| Dormant role rollout | Production workflow file and staging deploy job/target removed; historical helpers, source suites and docs remain | No migration/deletion of role storage or authority to retire existing remote research resources |

The active CI has **24** workflow-dispatch inputs after removing the role-rollout
only sink-canary input, below the existing inclusive limit of 25. Source checks
still run the complete infrastructure suite and preserve independent privacy
evidence checks. Workflow-coupled historical tests now assert absence of the
removed deploy paths; the known missing-`fi` Bash regression remains a synthetic
positive/negative fixture instead of depending on an active role deployment.

GitHub's default-branch workflow registration and previously queued/running
workflows are external state: removing a file from this source revision does
not retroactively cancel old runs. Do not dispatch or reuse historical role
rollout runs. Independently confirm the reviewed default-branch revision and
no in-flight/external graph writer before any separately authorized held rollout.
No workflow in this change repairs or recreates the four operational forwards.

Validation performed for this integration is limited to Python AST syntax,
non-executing YAML validation (including duplicate keys and dispatch limits),
and scoped diff whitespace checks. No project test, build, provider operation,
deployment or send was run locally. The YAML guard reported 17 workflow files
and zero failures at authoring time; concurrent unrelated workflow additions
may change that inventory count. Authored source assertions still require an
independent review and successful GitHub-hosted full CI plus the independent
workflow syntax lane at the immutable integrated revision before any live use.

Missing continuing direct-contact health scheduling, owner Inbox/Junk and
24-hour-response adoption, fresh accepted health, independent release evidence,
or truthful human attestation remains a public-release blocker. Successful
held deployment/configuration checks satisfy none of those responsibilities.

### Same-repository staging resource exclusion

The quota campaign/recovery job, active CI staging Mail/sink/ingress/events and
private Identity inbox deployments, capture-off settings corrections, and the
standalone private-inbox deployment now share the exact non-canceling
`staging-native-mail-acceptance` resource group. CI holds this lock at job level,
not also at workflow level; the standalone inbox workflow holds it only at
workflow level. A parent workflow and its dependent job must not wait on the
same lock owned by that parent.

Within one staging promotion the shared-resource mutator dependency chain is
sink -> Mail -> ingress -> events -> private inbox; source checks and unrelated
site deployment remain parallel. This avoids otherwise runnable same-run
mutators replacing each other's pending slots. Existing native mutation probes
already sharing the group keep their same exclusion.

GitHub concurrency groups are scoped to a repository, not to a Cloudflare
account or sibling repository. This lock does **not** freeze Identity/Login
deployments from other repositories, dashboard writes or other external tools.
Quota acceptance still requires the independently verified three-service
version pins and an externally enforced deployment/settings freeze for those
writers. No cross-repository exclusion is inferred from a shared string.

The default queue permits one running and one pending member; a newer pending
member can replace an older pending member even when `cancel-in-progress` is
false. Thus the lock protects an executing campaign, not a guarantee that every
queued request eventually runs or dispatch-order FIFO. The newly documented
`queue: max` could support multiple pending members, but adopting that option
across this shared group is outside this bounded change. Source review and
hosted parser acceptance precede any future policy change. See the
[official GitHub concurrency contract](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).

`infra/tests/test_staging_mutation_lock.py` checks the exact shared groups,
non-canceling policy, no reentrant workflow/job ownership, and the serial CI
dependency chain. It is authored for hosted execution only. Strong cancellation,
an interrupted process, or a provider/D1 ambiguity still requires the separately
reviewed same-artifact recovery procedure; locking cannot undo a completed write.

### Hosted inbox-workflow source guard correction

Hosted Infrastructure job `110085288211` at source `c5b2fd1` failed after about
19 seconds because `workers/identity-test-inbox/test_deploy_workflow.py` still
used the removed `staging-role-monitor` job as a hard-coded slice terminator.
That `ValueError` is a source-test integration defect, not evidence of a live
inbox, route, or deployed-binding failure. The role job remains deliberately
removed; restoring executable dead machinery would be the wrong fix.

The focused correction reuses the already reviewed strict `job_block` extractor
for both CI and standalone inbox deployment jobs. All existing assertions remain:
two all-alias route audits, the pre/postdeploy order, and exactly one deployed
binding check after deployment. A positive fixture omits the role job and inserts
a credential-bearing adjacent job; a negative fixture moves the postdeploy
route/binding guards into that neighbor and requires the inbox contract to fail.
Adjacent jobs cannot supply or contaminate an inbox safety assertion.

Only the test and this documentation are changed by the correction. Validation
is Python AST syntax and scoped diff checking, not local test execution. Require
independent review followed by a fresh immutable-revision hosted Infrastructure
result and the remaining full source suites. No workflow, provider state, route,
mail store, deployment or public-send permission is changed or authorized.

## Same-run staging deployment pin

The redacted deployment helper `infra/deploy/deploy_production_mail.py` now
accepts optional `--target staging`; omission still selects **production** and
requires `refs/heads/main`. Staging requires its exact release branch,
`AMAIL_STAGING_MAIL_DEPLOY_CONFIRM=RUN_STAGING_TRACE_SINK_ROLLOUT`, literal
api-only topology and a reviewed exact Queue ID. Before writing any secret or
executing Wrangler it reuses the staging isolation guard (Identity, HTTP route,
Mail domain, D1/R2, ingress and absence of the production official sender) and
the single-Mail-D1/strict Queue config allowlist. Staging always constructs
`wrangler deploy --env staging`; there is no environment auto-detection or
fallback to default production.

Credentials are supplied by the workflow's protected realm environment; the
helper cannot prove where a secret was originally obtained. The staging job
must therefore retain `environment: staging` and map `INGRESS_SECRET_STAGING`
to the runtime `INGRESS_SECRET`, never substitute the production ingress
credential. The only uploaded secret-file keys are the existing OpenRouter,
Email Routing and ingress keys; no confidential role destination is uploaded.
Temporary files remain restricted to repository `.temp`, receive restrictive
permissions and are deleted after success, failure or timeout.

Both targets make exactly one deployment attempt with captured private stdout/
stderr and bounded-output acceptance. The helper publishes only one exact UUID
to `GITHUB_OUTPUT`. A unique version returned with a failed command is retained
as a **recovery pin**, but the command still fails and never claims acceptance.
Missing, duplicated, malformed or oversized output does not become a pin;
timeouts are not retried. This also moves the preexisting production output-size
check before recovery-pin emission, avoiding a pin derived from unbounded
output. Existing production branch, default CLI, command, secrets, labels and
failure behavior remain otherwise unchanged.

CI should name the staged helper step `api`, supply the explicit staging
confirmation, and immediately pin its returned version via
`pin_staging_mail.py --phase queue-api` with
`AMAIL_EXPECTED_WORKER_VERSION=${{ steps.api.outputs.version }}` and the
same-run reviewed Queue output as `AMAIL_EXPECTED_TRACE_QUEUE_ID`. The separate
serving-pin dispatch must also specify `queue-api`. This prevents a successful
deployment or pre-Queue check from being mistaken for current immutable binding
acceptance. Independent Queue ownership and API/sink current-resource capture-off
checks remain mandatory and public sending remains held.

`infra/tests/test_deploy_mail_realms.py` contains hosted synthetic tests for
production-default compatibility, explicit staging command and secret isolation,
branch/confirmation/config denial before mutation, exact recovery-only pins,
duplicate/malformed/oversized output, no private logging, single-attempt timeout
behavior and temporary-file cleanup. Tests were authored, not run locally.
Cloudflare documents explicit named environments and non-inherited realm
bindings/secrets: [Wrangler environments](https://developers.cloudflare.com/workers/wrangler/environments/).
The wrapper's real deployment/readback still requires separately authorized
hosted execution and independent review; this source extension authorizes none.
