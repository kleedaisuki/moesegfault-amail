# Mail lifecycle predecessor: minimal trustworthy receipt and recovery invariants

Date: 2026-10-01. Status: bounded source guard implementation awaiting hosted
acceptance, no provider operation or rollout
authorization. Base is accepted PR55 head `f099d77`; that head remains unchanged.
The preserved dirty split prototype is evidence, not a trusted predecessor.

## Separate three facts instead of growing a generic control plane

1. **Provenance:** a fixed protected main workflow/job actually emitted an
   immutable bounded artifact after its complete graph readback. A JSON record
   with correct-looking UUIDs, source or admission strings is not authority.
2. **Current graph:** exact version AND deployment IDs, Queue/DLQ/resource
   identities, public capability/privacy invariants, complete script-level
   schedules, forwarding/ingress and sending hold still match the predecessor
   under a single realm-wide non-cancelling writer lock. Failed reads are errors.
3. **Old-work end:** independent evidence that old unfenced invocations cannot
   still write. Empty schedules, elapsed 30 minutes, deployment version changes,
   zero journals, missing native rows and client timeouts do not establish this.

Do not conflate a successful graph readback receipt with old-work completion.
The repository currently has no executable provider-supported old-work-end
verifier. This continuation must not manufacture one by accepting an environment
string or operator-authored `provider-attested-old-work-end` label. An activation
path remains explicitly non-admitting until its independently reviewed verifier
is implemented. A typed missing-proof failure is more useful than false safety.

## Implemented slice and deliberately missing integration

`mail_lifecycle_receipt.py` implements the fixed-origin loader, bounded ZIP/unique
JSON/schema admission and immutable receipt storage. `mail_lifecycle_guard.py`
reuses the existing complete split graph bracket, compares exact deployment IDs
as well as versions, derives stop/pause/hold plans from `mail_split_transition`,
and classifies one successful full recovery read without any retry permission.
Activation and code replacement/rollback fail with distinct missing-verifier
reasons before provider reads; unknown drain cannot become a successful proof.

The fixed receipt producer path is `.github/workflows/mail-lifecycle.yml`, which
**does not exist yet**. No new broad deployment workflow/input lane or provider
writer is introduced by this slice. The existing bootstrap inspection artifact
is explicitly refused as a lifecycle producer. No real receipt is currently
admitted, no ordinary deployment is falsely declared integrated and no schema
field/class by itself proves external execution. Future integration must implement
the reviewed protected producer and call these guards before any writer, not
bypass them by instantiating a validated JSON object.

Hosted tests exercise real parser/guard functions with inert original-run
metadata and fixed-provider-shaped graphs. They establish source behavior, not
an actually emitted predecessor, deployed pause, drain or rollback.

First scoped hosted run 36879863684 at source `153abea` executed 1085
infrastructure tests in 9.231 seconds. New lifecycle contracts passed; one
pre-existing quota artifact tamper fixture failed because replacing a random
authenticated blob's last byte with constant `x` can leave the blob unchanged
(one of 256 possible byte values). The source-only correction XORs the byte
with 1 and asserts actual inequality, preserving the durability refusal contract
without changing cryptography, runtime or mail operations. This is a deterministic
fixture repair, not rerunning or weakening a failed safety check.

## Concrete completion path: fresh first, cooperative established graphs next

1. **First production/fresh isolated scope:** implement a protected bootstrap
   producer tying positive resource/provisioning provenance and a complete
   successful no-predecessor/no-writer capability check to the exact source/run
   and held initial graph. Use the existing bootstrap/schema/hold readers and
   project-managed credentials. Current empty rows/script inventory alone must
   not certify history; failed reads must never qualify. If scope resources are
   genuinely newly isolated, old invocations cannot have bindings to them, but
   separately evaluate shared external routing/provider side effects too. No
   source-only type label or read-only inspection receipt waives that boundary.
2. **Emit the first lifecycle receipt:** only after actual complete immutable
   capability/privacy/resource/Queue/schedule/readback. Record binary source and
   successful artifact admission separately from orchestration source in the
   next schema. No manual hash Secret is needed; use actual producer identity.
3. **Subsequent scheduled-only lineage:** maintain closed handler/caller surfaces,
   successful protected version/deployment lineage, actual execution model and
   the exact acknowledged stop barrier. Source-approved bounded-Cron analysis
   can use documented propagation/lifetime guarantees only with those positive
   premises; it is not a generic 30-minute proof. Deprecated Bundled has no Cron
   wall-time bound. Mixed legacy HTTP cannot inherit a Cron-only proof.
4. **Cooperative established writers:** reuse existing accepted projection
   lease/token fencing and immutable external-write intents before designing a
   new epoch mechanism. Inventory which D1 and external/R2 effects actually
   cooperate, then derive a scoped proof rather than assume one token fences all
   cleanup phases. A check before an awaited external write is not atomic
   fencing; immutable object identities/intents and late-result recovery matter.
   Old noncooperative HTTP still needs independent termination or a genuinely
   isolated scope; the next investigation is a source call-graph/fence coverage
   audit, not a provider mail-debug campaign or new generic business DB registry.
5. **Enable admitted active/rollback:** add a separately reviewed executable
   verifier backed by the bootstrap/cooperative evidence, update the versioned
   receipt schema, exercise trigger writes/readback/ambiguous recovery on an
   explicitly authorized isolated graph, then independently admit production.

This keeps a concrete route to completion while refusing to disguise missing
proof as elapsed time, a successful workflow or a forever-safe default.

## Receipt admission

Use one immutable GitHub Actions artifact per successful lifecycle run/realm,
not a new database/coordinator/Secret. A source-owned loader validates:

* exact repository, fixed lifecycle workflow path, successful completed main
  `workflow_dispatch`, first attempt, exact successful protected realm job;
* complete bounded job/artifact inventories; a unique nonexpired artifact chosen
  by its fixed run/realm name and immutable artifact ID;
* single expected JSON member, safe regular-file ZIP metadata, bounded compressed
  and expanded data, unique JSON keys and a closed versioned schema;
* original orchestration SHA/run/attempt, realm, selected state, predecessor
  coordinate, exact API/maintenance/sink version+deployment pairs, same-realm
  D1/R2 and Queue/DLQ, explicit complete API/maintenance schedules and held-send
  graph verdict. Resource IDs are operational data, not secrets;
* a distinct drain verdict. Current source can retain `UNVERIFIED`, not upgrade
  it based on absence or inherit a stale barrier across a changed writer graph.

The record's orchestration SHA must not be presented as the source of already
deployed binaries. Binary replacement separately consumes PR55's current exact
same-run full-gate artifact; receipt adoption does not admit an old arbitrary
artifact for code deployment. Artifact content/digests are calculated by the
platform/loader, not new manual hash Secrets or user hash-entry ceremonies.

## Closed operations and failure semantics

| Operation | Mandatory evidence | Result / refusal |
| --- | --- | --- |
| Pin an explicitly selected paused graph | Full exact graph bracket, both complete schedule sets empty, send held | Paused receipt with old-work end still UNVERIFIED |
| Inspect/reconcile a predecessor | Trusted receipt + successful exact fresh graph bracket | Match result only; failed read cannot become absent or paused |
| Stop/pause | Trusted exact predecessor; fixed selected script; exact schedules/version/deployment; source-approved empty successor | At most one trigger write; successful readback enters old/new-draining, not active/old-work-ended |
| Hold | Draining predecessor + exact both-empty graph | Paused with unchanged UNVERIFIED drain; no implicit activation |
| Activate | Paused predecessor + independently implemented old-work-end verifier + reviewed desired cadence + exact current graph | Current missing verifier fails before any write; no self-asserted label bypass |
| Normal replacement / rollback | Stable predecessor, exact target owner/artifact, schedule preservation and separately established compatibility/drain where required | Never restore API Cron or legacy state; no schema/data/Queue rollback |

An ambiguous write, transport timeout, failed post-readback, mismatched version
or changed deployment gets a **recovery-only** record, never a successful
successor receipt. A subsequent separately authorized recovery reads the exact
expected predecessor/successor once under the same lock; it does not replay the
write. Unrecognized intermediate graph stays unresolved; do not overwrite drift,
clear claims or purge Queues to make evidence green. Successful settings PUT and
single-100 deployment are not proof of global propagation or invocation drain.

Keep the original pure `mail_split_transition` enum/edge table and adapters.
The new trusted boundary must consume admitted receipts rather than broadening
its legacy `admission` string into an environment-controlled authority. Existing
normal external CLI/HTTP/ZIP/Identity contracts are untouched.

## Standalone staging Identity inbox

`deploy-identity-test-inbox.yml` still builds independently with floating stable;
it is outside PR55's nine ordinary `ci.yml` artifact consumers. It cannot use
the isolated tracing canary's ancestor exemption as general deployment admission.
Prefer either routing its existing workflow identity through strict exact-source
full CI artifact admission, or an explicitly retired research-only workflow that
preserves established route safety and user workflows. Root must coordinate this
choice before removal or input-contract changes. No account/route operation is
part of deciding its source lifecycle.

## Verification and external grounding

Hosted synthetic tests should distinguish wrong workflow/job/repository/source,
reruns, expired/duplicate/truncated artifacts, hostile ZIP/JSON types and complete
graphs from failed/malformed reads. Discriminating state tests should assert
pause versus drain, missing proof before activation, trigger preservation on
rollback, no retry after ambiguous writes and no success receipt on failed
readback. All runtime tests run on GitHub Actions; local work is static only.

Use mature immutable artifact, protected environment and concurrency mechanisms
rather than a new signing/lease service. Future formal policy verification or
granular CI runtime enforcement is complementary research, not a substitute for
accurate predecessor/proof boundaries or current platform writer serialization.

Primary references:

* https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments
* https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-what-your-workflow-does/storing-and-sharing-data-from-a-workflow
* https://developers.cloudflare.com/workers/configuration/cron-triggers/
* https://developers.cloudflare.com/workers/platform/limits/
* https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/schedules/methods/update/
* https://developers.cloudflare.com/workers/versions-and-deployments/rollbacks/

Prior repository reasoning reused: `mail-scheduled-only-product-split-design-2026-10-01.md`,
`accepted-projection-cutover-contract-2026-10-01.md`, `check_mail_split_graph.py`,
`check_mail_maintenance.py`, `mail_split_transition.py`, and the preserved dirty
`mail_split_record.py` / `mail_split_release.py` draft under
`.temp/scheduled-only-product-split-impl`.
