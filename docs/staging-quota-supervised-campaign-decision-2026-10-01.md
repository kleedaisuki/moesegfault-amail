# One supervised quota campaign, not a prerequisite operations platform

Date: 2026-10-01. Status: **recommended decision for review; not live GO**.
Scope: one already verified synthetic staging account, reserved-name checks,
ten concurrent owned aliases, exact eleventh rejection, no SMTP and no sending.
Production release, complaint handling and unattended operation gates do not
change. No provider operation, authentication, workflow dispatch, local project
test/build, secret access, deployment or push was performed for this decision.

## Decision

**Choose one explicitly supervised experiment using the existing encrypted D1
escrow, immutable artifact, same-process serial cleanup and a separate complete
read-only finalizer. Do not require a general autonomous 24-hour Agent intake
service, scheduled watchdog, issue-ACK protocol or operator mailbox first.**

Twenty-four hours is a response/escalation objective for an interrupted
experiment, not an inherent property of address quota or a requirement that
the handler be autonomous. A staffed experiment with an actual primary
supervisor and an acknowledged exception handoff can satisfy accountability
without proving future unattended service. An interactive turn alone, an
unread task or an untested notification is not that handoff.

However, **finally + an expiring artifact + an assertion that someone will
clean up is insufficient**. A runner can be killed; present cross-run recovery
cannot retire an active resource; and a retired alias cannot be reused. Keep
durable evidence and an explicitly reviewable exception path. Do not discard
already implemented D1 merely to make the diagram smaller.

This recommendation revises the *proposed* autonomous-intake prerequisite in
`staging-quota-accountable-agent-recovery-path-2026-10-01.md` (local architecture
commit `ec906fe`; not present on the inspected main ref). It does not silently
alter any source guard or claim the existing live NO-GO has been lifted.

## Source-derived facts and four-layer analysis

Inspected feature checkout `add03b69f3c30ba6b9a39ac4658e3cf4358d7126`;
documentation worktree base is main
`89ce49f0166307ea6fcd7657459dd6b2e9726257`. Reused the hosted acceptance design,
D1 escrow design, cleanup batching decision and independent recovery/terminal
reviews. These are source observations, not new hosted/live pass evidence.

### 1. Data: resource identity, desired state and evidence are different

- The immutable v2 manifest authenticates the complete baseline, all possible
  test resources (including unexpected reserved/eleventh allocations), owner,
  service revisions and original invocation. It records **intent**, not an
  exactly-once request history.
- D1 escrow already supplies complete authenticated retained ciphertext,
  one outstanding campaign and conditional arm/receipt transitions. Reuse it;
  retain terminal ciphertext for this bounded campaign rather than purge parts.
- Worker `add_address` rejects a `retired` row permanently. Cleanup restores
  allocatable capacity and provider baseline, not byte-for-byte D1 absence:
  exact clean retired tombstones are intentional permanent residue.
- Quota acceptance and resource cleanup are separate results. A rejected or
  ambiguous campaign can subsequently have verified cleanup without passing
  quota; successful quota responses with unknown cleanup are not acceptance.

### 2. Special cases: make operator identity ordinary, not autonomous-only

The useful distinction is **supervised versus unattended**, not human versus
Agent. For one scheduled experiment, its identified supervisor already watches
the one run and records a terminal disposition. A production watchdog is needed
when experiments or service operations continue without that watch.

Keep the genuine hard-kill exceptional state: `hosted.campaign` owns DELETE
capability only inside its own `finally`; public `hosted.recover` and the outer
wrapper supply no address mutation capability. `active/pending/provisioning`
residue therefore requires restricted intervention, whereas observed
`deleting`/unsettled `retired` may settle through read-only polling and Cron.
An autonomous ACK does not resolve this resource-state ambiguity.

### 3. Complexity: six admission gates, no extra distributed control plane

Keep the existing roughly 80-minute hosted job bound and serial one-DELETE/
settlement policy. The unfavorable ten-alias retirement waiting allowances can
sum to 60 minutes, plus transport overhead; this is not a measured runtime or
a hard total guarantee. Batch cleanup, partial purge, a general issue protocol
and multiple schedulers are unnecessary for this one quota assertion.

The exact inspected wrapper still uses artifact-only prepare/campaign:
`execute` does not call escrow `put/attach/arm`, and the D1-only retained
finalizer is dormant. Native synthetic D1 proof does not prove these missing
call sites. Integrate and host-test the small existing lifecycle instead of
substituting a paperwork gate or building an operations platform around it.

### 4. Destructive analysis: bounded does not mean reversible

Ten accepted names produce permanent tombstones after retirement. A defective
eleventh/reserved rejection can allocate an extra resource; cleanup must cover
the full authenticated resource plan, not only ten acknowledged successes.
Rule capacity is shared with other activity; even staging can affect a shared
zone. Unexpected inbound mail is possible once a literal route exists, despite
the experiment submitting no SMTP and keeping outbound held. Preserve effective
privacy, complete inventory and storage-absence checks.

No database restore, broad provider deletion, alias reuse, fresh nonce campaign,
source-pin substitution or invocation of private cleanup is an acceptable
shortcut after interruption. A hard kill can leave active routes and capacity
occupied; retention is evidence preservation, not resource cleanup.

## Concrete GO / NO-GO gates for the recommended path

All six must be observed for the **exact** dispatch. Unknown is NO-GO.

| Gate | Minimum evidence; no general service required |
| --- | --- |
| 1. Source and invocation | Independently reviewed integration; exact successful hosted source/cipher checks and CI-built binary; manual attempt 1, protected staging execution, unchanged explicit confirmation and no replay/add on recovery. |
| 2. Environment and privacy | Fresh normal synthetic-A PKCE with issuer/contact/subject binding; exact current Mail/Identity/Login versions and staging bindings; effective capture-off independently proved; sending held, no SMTP capability. The unresolved live Issues setting is **not** waived. |
| 3. Baseline and capacity | Empty selected owner without deleting unrelated data; complete stable global/provider/R2 baseline; application non-retired count <=187, existing conservative provider headroom; all reserved/resource baselines; actual cross-repository writer freeze plus repeated pin checks. |
| 4. Durable admission | Exact native schema and provider contract already proved; integrated real manifest `put -> sealed -> artifact readback/attach -> arm`; known conditional changes=1 and complete authenticated readback before first alias; retained key; no outstanding unresolved campaign. Artifact and D1 have identical envelope bytes. |
| 5. Supervision and exception ownership | A specific capable supervisor has acknowledged this single campaign and watches through its final disposition; an acknowledged continuation/handoff for a failed or lost supervisor is recorded before arm. Document the actual watch window, original run and fixed failure action without private addresses. Same-day restricted intervention is the target; 24 hours remains escalation, never expiry. |
| 6. Recovery competence | Hosted fixtures/real-cipher checks exercise ordinary finalization and killed-run classifications; exact D1-only finalizer is dispatchable without add/DELETE and retains every chunk. A pre-reviewed restricted intervention procedure and an authorized capable handler exist for live ambiguous rows; otherwise a known worst-case branch has no recovery owner and dispatch remains NO-GO. |

Gate 5 does **not** ask the busy product owner to inspect a mailbox daily or
require an autonomous scheduler. The project maintainer/Agent can supervise the
finite event if it actually accepts and executes that task; claiming indefinite
background coverage without a platform/handler is forbidden. If no exception
handoff can be accepted, do not start merely because the happy path is likely.

Gate 6 is a narrow resource-operation contract, not a demand to finish the
future Agent operations center. It cannot be discharged with a generic promise
of manual DELETE. The missing procedure is concretely specified below.

## Exception procedure: separate a new retirement decision from request replay

Keep current `recover` observation-only. First classify exact original manifest,
completed original invocation, current source/service/owner, full baseline and
current resource state. Do not race a still-running campaign or provider writer.

| Observed state | Disposition |
| --- | --- |
| No live/unsettled campaign resources; complete exact baseline preserved | Fresh native teardown and complete D1 retained-ciphertext finalizer; record cleanup separately from the quota result. |
| Exact `deleting` / pending retired tombstone, no foreign drift | One bounded read-only settlement and complete postcheck; no second DELETE. |
| Exact newly created active/pending/provisioning resource | Fixed `recovery_manual_intervention_required`; preserve evidence, stop new campaigns, notify/hand off to the acknowledged restricted handler. No existing automatic mutation path is granted. |
| Foreign row/rule, baseline drift, unknown saved ID or historical/current identity | Preserve evidence and escalate; do not delete any inferred resource. |

For the third row, the restricted handler must review a **new intention to
retire this same permanently non-reusable, verified owned address**, not assert
that the historical DELETE was unattempted. Review exact owner/resource birth,
complete matching rule/saved-ID ownership, service freeze and provisioning/Cron
interactions before authorizing one normal owner-scoped retirement. No direct
SQL rewrite, provider wildcard, private-function override or campaign restart.
Record scope and decision before submitting it; after any ambiguous response,
return to read-only observation and retain the incident rather than loop.

This is a concrete candidate restricted runbook, **not an authorization to use
it now**. It needs an independent source/contract review and hosted fixtures
for the pretransition/late-old-request race and exact provider rule scope before
gate 6 is satisfied. If that review finds the operation unsafe under permitted
concurrency, add the smallest server-enforced conditional/idempotent retirement
contract; do not compensate by deploying an autonomous intake system.

Source rationale: `delete_address` is owner-scoped and converges toward terminal
`retired`; `platform::delete_rule` accepts provider 404, and `add_address` prevents
reuse of a retired name. These remove the ordinary resource-reuse/ABA concern
for a correctly scoped **desired-state** retirement. They do not establish an
exactly-once external request contract, prove saved-ID safety under arbitrary
drift or independently validate the currently deployed version. Respect the
present stricter no-replay boundary until this narrow alternative is reviewed.

## Execute the smallest integration, then stop expanding prerequisites

1. Record/adopt this supervised policy explicitly in the acceptance design;
   keep the autonomous-intake proposal as the future unattended path.
2. Finish only escrow prepare/attach/arm and retained-ciphertext finalizer
   workflow integration, including the six gates and exact source checks.
   Independently review the bounded restricted retirement runbook. Run its
   synthetic/crash/cipher checks in hosted CI, never on the development machine.
3. Resolve the **existing** live privacy/readback blocker and obtain current
   source/service/baseline evidence. Register the actual supervisor/handoff.
4. Dispatch **one** campaign. Follow it to complete success+cleanup or a retained
   explicit exception case. An exception stops acceptance and new campaigns;
   it does not spawn a replacement campaign or a silent retry.
5. Execute a distinct complete read-only retained-ciphertext finalization after
   the original finishes. Publish only fixed result codes/public run coordinates.
   Preserve ciphertext/key and clean retired tombstones; no reclamation project.

Current result: **NO-GO for immediate live dispatch**, but not because a full
autonomous intake platform is missing. Integration, effective privacy and the
specific supervised exception contract are the actionable remaining gates.
This pass advances quota/reserved acceptance only; it proves neither B isolation,
outbound deliverability, public operational readiness nor the v0.1.0 release.

## External evidence and limits of the inference

- [AWS game-day practice](https://aws.amazon.com/blogs/architecture/build-your-own-game-day-to-support-operational-resilience/)
  maps people, process and technology, observes responses and records lessons
  in controlled environments. It supports a staffed experiment as a legitimate
  engineering mode; it does not certify this campaign or replace recovery.
- [Google SRE emergency-response experience](https://sre.google/sre-book/emergency-response/)
  shows even reviewed tests exposing dependencies and flawed rollback, and
  emphasizes tested response procedures and backup access. The inference here
  is to keep explicit supervision and a narrow recovery drill, not demand a
  finished autonomous production operator before every bounded test.
- [GitHub cancellation semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-cancellation)
  include process-tree killing and forced termination. `finally`/`always()` is
  best effort, not durable cleanup. [Immutable Actions artifacts](https://github.com/actions/upload-artifact)
  are useful evidence but have retention limits; the existing independent D1
  copy avoids making recovery depend on rescuing an expiring artifact in time.
- [AWS idempotent-API guidance](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/)
  distinguishes lost responses, explicit request identity and late arrivals.
  Do not infer old attempt history or promise exactly-once retries from intent.
  The source-derived convergent-retirement alternative above still needs its
  particular resource identity/concurrency review; AWS does not prove it safe.
- [RIFL, SOSP 2015](https://sigops.org/s/conferences/sosp/2015/current/2015-Monterey/printable/126-lee.pdf)
  associates durable completion records with mutation to provide exactly-once
  RPC semantics. A manifest and intake ACK are not such records. This is a
  foundational academic mechanism, not new evidence that every desired-state
  cleanup requires RIFL or that the inspected Mail service implements it.
- [Cloudflare's current limits](https://developers.cloudflare.com/email-service/platform/limits/)
  retain 200 rules per domain. Existing conservative application/provider
  admission remains unchanged; supervision cannot manufacture capacity.

The external sources support the distinction between experiment response and
unattended operations, and between durable intent and request completion.
The six gates and selected integration are this note's engineering judgment,
not a provider guarantee or a measured risk probability.
