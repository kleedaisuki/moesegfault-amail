# v0.3.1 privacy cutover and production delivery

The owner authorized production publication **after successful staging acceptance**,
then upgrade of every local CLI entrypoint and the global amail Skill. This note
records the ordered cutover and eventual delivery coordinates; authorization and
prepared source do not establish deployment or publication success.

## Why this is not an ordinary model upgrade

v0.3.0 automatically indexed eligible mail through Qwen. v0.3.1 introduces
account-wide default-off semantic consent and Voyage 4 through OpenRouter.
Migration `0018_semantic_consent.sql` keeps existing document embeddings, defaults
all accounts off, invalidates prior semantic search generations and blocks old
Workers from acquiring fresh indexing leases. Applying a new model variable alone
would neither revoke existing egress nor produce compatible vectors.

The new runtime admits document/query provider requests only for an enabled
account generation; publication also requires that exact generation and claim.
Only `user` can enable or disable the switch, with normal browser approval or the
human's existing explicit YOLO preference. Each off-to-on transition re-indexes
all eligible retained mail. Disable retains embeddings but revokes new work;
already dispatched provider bytes cannot be recalled. See
[indexer semantics](../semantic-indexer-operations.md), not this deployment note,
for the durable state machine.

## Approved provider policy

Before any v0.3.1 runtime or migration write, the synthetic Voyage provider gate
must pass the owner-approved `voyage4_no_training_retention_v1` contract: only
`voyageai`, no fallbacks, `data_collection: deny`, response cache off and no request
`zdr` override. The route is non-ZDR; upstream may retain inputs and outputs for an
unspecified period under its terms. The enable consent page and status must carry
that disclosure/policy identity. Disable or mail deletion does not prove remote
erasure. Do not alter stricter account-level ZDR or OpenRouter content logging/use
preferences as a rollout workaround. Provider gate failure stops before writes;
no migration or deployment success follows from a locally prepared policy change.

## Production predecessor and preservation

The accepted predecessor is completed v0.3.0 production run
[40116604490](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/40116604490),
source `d3d913d4bf59f48790a2753bc066033b4d8cf7a6`, receipt `12570076705`.
The [completed v0.3.0 delivery](../v0.3.0/production-delivery.md) holds its exact
serving versions. Fresh read-only admission must match that reviewed epoch and
preserve the stores, address ownership, all profile/mailbox fences, accepted or
unknown sends, paid grants, budgets, currencies, current sending policy, direct
contacts, lifecycle subscriptions and retained ingress/events graph. No customer
mail is a test fixture and no production account is enabled by the migration.

## Rollout and readiness

### Actual staging readiness

Producer run `40188956353` at
`f262e8e433ffeabb7d67d0fc26c363be7e4133f8` passed the native/Worker/provider
source gates, including 144 Worker boundary cases, but its overall writer failed
before maintenance activation. Named recovery
[40193614404](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/40193614404)
then completed successfully at orchestration source
`802bc116dde3e2f6390a90b66346920c18dee72e`, artifact `12599375984`.
All 163 schema objects and full column/index metadata matched, with no unknown or
drifted objects. Only maintenance advanced to
`c00d2f51-096d-4b83-8d49-e42e196b85ec`; API
`d592cd2a-95a3-4c89-859a-18a191bd641a` and sink
`5e556087-9a75-40db-9eb5-869a4b56372e` were retained. Applied 0018 and the
completed scheduled witness were reused, not replayed.

Narrow semantic-only acceptance run
[40195321997](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/40195321997)
completed **SUCCESS** on 2026-10-25 at 21:05:15 Asia/Singapore (13:05:15 UTC),
checkout `205eb3dd3f7e723ff1be9ac08c9838e4635e17a5`, artifact `12600320617`.
Its single owned SMTP fixture passed default-off, enable/full-index readiness,
one semantic query, disable/literal search, re-enable/full-index readiness and
final disable, followed by complete owned cleanup before receipt publication.
The receipt keeps original producer `40188956353` / `f262e8e...` separate from
the acceptance checkout/run and binds API `d592cd2a-95a3-4c89-859a-18a191bd641a`,
maintenance `c00d2f51-096d-4b83-8d49-e42e196b85ec` and sink
`5e556087-9a75-40db-9eb5-869a4b56372e`. No full regression or deployment replay
was used to obtain this acceptance. The earlier 420-second wait failure remains
failed; it occurred inside schedule activation propagation, and warm acceptance
does not prove a particular Cron invocation ran. Production backend completion,
formal release and local installation are recorded below. The
[validation ledger](../validation.md) owns current acceptance status.

### Completed production admission and order (historical writer)

The completed controller is `infra/deploy/production_v031.py`; its predecessor
pins are now historical and it must not be rerun. The following records its trusted
`main`, protected `production`, first-attempt admission and shared graph writer
lock, not authority to repeat the upgrade:

| Existing workflow target | Confirmation | Required `production_graph_freeze` |
| --- | --- | --- |
| `production-inspect` | `INSPECT_PRODUCTION_V031` | `FREEZE_PRODUCTION_GRAPH_WRITERS` |
| `production` | `RUN_PRODUCTION_V031` | `FREEZE_PRODUCTION_GRAPH_WRITERS` |

Inspection is read-only and verifies exact serving versions, retained graph,
current policy, schema through migration 0017 and a supported old scheduled usage
model. The writer additionally requires all current source gates plus restored,
reverified `mail_api` and `trace_sink` artifacts before mutation. The default is
same-run admission; the reviewed promotion path instead requires both
`source_run` (the original successful build/check producer) and
`staging_acceptance_run` (a separately successful real semantic journey). Its
`accepted-staging-artifact/v1` chain keeps the original manifest/compiler/source/
run identities intact and checks complete runtime closure against the current
trusted main checkout. A failed deployment with green source gates remains a
failed deployment, not real-user acceptance. See
[artifact promotion](../deployment-artifact-foundation.md).

The provider order is:

1. Replace the backward-compatible private trace sink; retain exact queues and
   producer ownership, ingress, lifecycle consumer and subscriptions.
2. Install the consent-aware fetch-only API before 0018. Missing preference schema
   fails semantic processing closed; ordinary compatible mail flows remain live.
3. Install the tested private maintenance entry with empty Cron. Bracket exact
   serving API/maintenance pins, paused schedules, capture-off, preserved policy
   and retained external graph throughout the old scheduled cohort witness.
4. Observe at least 31 monotonic minutes: documented 15-minute Cron propagation,
   15-minute scheduled invocation wall limit and a one-minute margin. Missing or
   unsupported predecessor usage models stop before writes. Elapsed sleep alone
   is not the witness. Record `old_http_drain: NOT_CLAIMED`: old admitted HTTP and
   provider bytes cannot be recalled by the schedule bound.
5. Apply only additive migration 0018, verify the complete source-derived schema,
   zero enabled preferences, unchanged retained-vector count and preserved existing
   address ownership. Do not retrieve mail content or vectors for this check.
6. Activate the new maintenance at its existing five-minute cadence and verify the
   complete immutable graph, private surfaces, queues, capture settings, empty API
   Cron and unchanged policy/retained ownership again. Bounded unauthenticated,
   no-redirect public-health reads must report `status=ok`, `version=0.3.1` and
   `api_version="2"` within 120 seconds before success; propagation never authorizes
   another deployment submission.

The non-content `production-v031/v1` receipt records actual pins, source/run,
preserved address count, semantic model/default, policy/retained fingerprints and
the scheduled witness. Inspection records `schema_migration_applied: false` and
labels semantic defaults/model as **after upgrade**, not as facts about the old
live automatic-indexing runtime. Completed upgrade records the migration as
applied only after its actual checks. Aggregate non-NULL vector-count preservation
is not byte-equality evidence. A concurrent legitimate deletion can safely stop a
partial promotion; it does not authorize rollback, suppressing the check or replay.
The upgrade receipt is not emitted as success until final graph/public readback.
Any failed or ambiguous provider mutation stops with its captured coordinates and
requires exact owned reconciliation, not another blind dispatch. No sending-policy
change, resource creation, consent enablement or automatic rollback belongs to
this controller. Retained legacy vectors are not rollback permission to a
pre-consent API or background sender. A completed receipt becomes the next
reviewed predecessor; a future writer must explicitly advance the pinned epoch.

Formal five-platform CLI/Skill publication requires matching production health,
the existing outbound attestations, native profile journeys, checksums,
attestations and published-byte verification. Reviewed release promotion reuses
the original three already-tested native executables with embedded provenance,
and compiles/version-smokes only the two missing targets; it neither reruns green native
suites nor calls reused binaries a new build. Public-site replacement follows the
verified public assets. Local replacement follows matching archive/Skill source
verification, daemon stop and private backups; credentials and YOLO preferences
must not be reset. Success receipts will be added only after actual readback.


## Actual production backend completion

Inspection [40196506986](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/40196506986)
passed against the v0.3.0 predecessor. The one writer
[40196627612](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/40196627612)
at `b4c34664bfc59bd2c6611c5507f5e7b73784a93b` completed all ten recorded phases,
then failed `production_v031_health_unverified` because its checker expected
integer `2` instead of the established string `"2"`. Its workflow remains failed;
there was no deployment or 31-minute wait replay.

Named read-only completion
[40199972693](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/40199972693)
completed **SUCCESS** at source `4bd01f1fc3234aed49117923bcb6080a332f03cf` on
2026-10-25 at 21:58:36 Asia/Singapore (13:58:36 UTC). Receipt artifact
[12601077928](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/40199972693/artifacts/12601077928)
has schema `production-v031-completion/v1` and verifies the fresh schema through
0018, zero enabled semantic preferences, exact private active graph and public
health `status=ok`, `version=0.3.1`, `api_version="2"`.

| Role | Actual deployment | Actual version |
| --- | --- | --- |
| API, empty Cron | `4c7a4157-7d0a-487d-8f4e-63348c680df8` | `dd3e7d96-fde0-4ed9-adb8-ff5fcc76270f` |
| Maintenance, `*/5 * * * *` | `24fe4478-3599-4f63-9ae3-92ab3caf150c` | `45662e34-b008-42d7-a76b-ba77c09693d0` |
| Trace sink | `33b6b9dc-5a4c-4213-9eeb-bd20eb683515` | `2bc63288-c987-49f9-bee6-8bc25b35a8be` |
| Retained ingress | `3192c6ef-7b49-40e7-b244-a8d9f9759028` | `5c296407-5048-43b3-aad6-ac106676e7f2` |
| Retained lifecycle | `24026786-e338-439d-ae75-417b380a80aa` | `c17d92ad-cbc4-4ff3-a250-724f17d5bc60` |

Eleven live address records remain. Sending policy is still allowed, fingerprint
`e5c23a79ef5495ddc1dc6859f86dcd58a757f42631fa5444546cb5c537243213`;
the retained external graph fingerprint is
`f18a62c67d24c85771e34edb41a8e5b121c58564c1b003b89523ef96d9098d12`,
exactly matching the accepted pre-write inspection. No consent was enabled and
no policy, spending, contact or customer-mail test action was added.

The completion proves the original scheduled-cohort wait, ownership and embedding
checks by the admitted original controller's closed final failure and ten-phase
journal (`bd11d90660882e1da78ca2947460fa43a7466e0f7e2779d23655824c2ba96cab`).
Its proof fields are `original_controller_control_flow`, **not newly observed
monotonic seconds, a reconstructed before-count or byte-equality evidence**.
`old_http_drain` remains `NOT_CLAIMED`. An earlier read-only completion could not
retrieve logs; the final mature log reader succeeded without replaying mutations.

This completed receipt is the next reviewed production epoch. The old v0.3.1
promotion/completion pins are historical; advance a future controller's explicit
preconditions instead of rerunning them. Formal assets, public site and local
upgrade completed through their separate gates recorded below.


## Formal publication and local upgrade — complete

[Release workflow 40200242942](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/40200242942)
completed **SUCCESS** for annotated tag `v0.3.1`, source
`e8f47a046b6b297c6e0f1f339b8baf595f37441a`. The nondraft, non-prerelease
[v0.3.1 release](https://github.com/kleedaisuki/moesegfault-amail/releases/tag/v0.3.1)
was published on 2026-10-25 at 22:06:29 Asia/Singapore (14:06:29 UTC).
Three accepted native executables retain their original
`f262e8e433ffeabb7d67d0fc26c363be7e4133f8` / `40188956353` provenance; only the
two missing platforms were compiled/version-smoked. All release checksum,
attestation, published-byte and [public-site](https://amail.moesegfault.dev/)
gates passed. Current packaging provenance is distinct from original compilation,
not a claim that reused executable bytes were rebuilt.

| Verified public artifact | SHA-256 |
| --- | --- |
| Windows ZIP | `e9054f61b7ad51a58ad795ed96969c282832fd04111b12b83f4636115dc50ed9` |
| Agent Skill ZIP | `12f9432ea55223ce4cfe4dcc23b41d452a15b0ede7b8faf0234fa978480e8827` |
| SHA256SUMS | `3e7b8398cabb122a34765bf9a32337cd50f81274b76d3fd8735f14551b0a16eb` |
| Installed Windows executable | `3d952429f437d53c4cf18bd62843af71d4a01ad5e35a8d58b532e1d90c4b471f` |

The owner-requested upgrade replaced both canonical `~/.amail/bin` and the existing
compatibility PATH executable; both now report `amail 0.3.1` and match the trusted
executable hash. Both selected archives passed public-manifest and GitHub
attestation verification. Every one of the eleven global amail Skill files also
matched the verified Skill ZIP and helper-installed exact-tag source. Private
`~/.amail/backups` retains the previous binaries and global instructions.
Configuration, explicit YOLO choice and credentials were not changed. Local
verification consisted only of offline version calls at each executable path;
no logged-in mail operation or semantic consent change was needed. Installation
metadata records original native source separately from release packaging source.
The updated global Skill becomes available in the next agent session.
