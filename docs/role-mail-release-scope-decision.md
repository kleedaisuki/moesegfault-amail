# Proposal: v0.1.0 operational role mail uses direct forwarding, not a new operations platform

Date: 2026-10-01. Status: **product decision proposal; not implementation,
acceptance, an attestation, or permission to enable sending**. This assessment
changes no source, workflow, provider state, address, credential, or release gate.
The confidential destination is intentionally absent from this document.

## Recommendation

Choose **A: four exact provider-managed direct forwards to the owner-selected
confidential external mailbox, with bounded machine configuration checks and an
explicitly owned review/response process** for v0.1.0. Do not require the new
role Email Worker, D1 arrival outbox, digest, Cron lease, or `api-role` trace
topology merely because they have been implemented.

This is conditional, not a declaration that forwarding alone is sufficient:
someone must actually review **Inbox and Junk** and act on reports. The user's
choice settles the delivery mechanism and defers the notification/agent
operations center. It does **not** establish a continuing response commitment.
If no accountable owner or authorized substitute accepts that obligation,
public sending stays held. Option B cannot fix that missing ownership either.

Adopting A also requires a reviewed change to the current internal send-policy
contract, which hard-requires the role Worker's lease. Until that change is
implemented, tested and deployed, the existing fail-closed policy remains in
force. Do not set a boolean, write a fake lease, ignore failed checks, or call a
failed role acceptance run successful.

## Evidence and scope authority

| Evidence type | Established fact | What it does not establish |
| --- | --- | --- |
| Explicit user choice | The user rejected a ticket/admin page and chose one confidential external mailbox now, reserving notification and agent operations centers for later. Standard role names should remain supported. | Unattended per-arrival alerts, mailbox API access, report-content model processing, or a 24/7 operator commitment were not authorized or promised. |
| Product scope | User mail is AI-agent workflow transactional notifications and related replies; the original CLI/ZIP, search, telemetry, Identity and release-site requirements remain complete release requirements. See [outbound policy](outbound-policy.md). | Transactional labeling does not make spam, compromised accounts or complaints impossible. |
| Actual forwarding evidence | Four controlled standard-role messages were provider-recorded as forwarded/delivered and owner-confirmed in Junk. The owner subsequently confirmed adding the official sender to safe senders. See [role-mail history](role-mail-monitoring.md). | Arbitrary reporter Inbox placement, future receipt, timely attention, or the safe-sender configuration's effectiveness for unknown senders. |
| Current bounded control-plane evidence | [36757470446](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36757470446), `cd64c14`: Addresses/Rules accessible, private destination verified, `four_direct`, disposable route absent. See [token discriminator](staging-role-token-permission-discriminator.md). | Its aggregate is inconclusive because the role serving pin drifted. That drift prevents accepting role-Worker health; it does not negate separately established direct-forward/destination facts. The four-direct result is current structural evidence, not historical rule-ID immutability. |
| Prior engineering proposal | [role-mail-monitoring.md](role-mail-monitoring.md) recommends a Worker **if unattended per-arrival alerts are needed** and correctly rejects sampled analytics as a complete arrival feed. | A conditional architecture proposal is not a user requirement, provider mandate, or evidence that a custom Worker is intrinsically safer. |

The old release-gap documents currently require Worker/lease acceptance. This
proposal does not silently supersede them. The release owner must explicitly
adopt the new operational contract and reconcile those documents and code.

## What external standards and provider practice actually require

1. [RFC 5321 section 4.5.1](https://www.rfc-editor.org/rfc/rfc5321.html#section-4.5.1)
   requires case-insensitive `postmaster` support on domains served by an SMTP
   receiver, including the bare Postmaster recipient form. It calls for reasonable
   effort to accept that mail, with narrowly tailored security exceptions.
   Cloudflare operates the SMTP receiver here; amail still owns working role
   routes. Do not infer mixed-case or bare-recipient acceptance from lowercase
   canaries if that behavior has not been checked or established by the provider.
2. [RFC 2142 sections 1, 2 and 4](https://www.rfc-editor.org/rfc/rfc2142.html)
   defines appropriate organizational role contacts, including apex `abuse`, and
   case-insensitive role names. Subdomain abuse aliases are encouraged; retaining
   all four existing apex/mail-subdomain addresses is sensible and compatible.
   It does not prescribe a ticket UI, an Email Worker, a queue or automatic triage.
3. [Cloudflare customer abuse-report obligations](https://developers.cloudflare.com/fundamentals/reference/report-abuse/abuse-report-obligations/)
   call for an actively managed abuse contact and responses to Cloudflare abuse
   notifications within **24 hours**. This page concerns Cloudflare's Trust &
   Safety reports, not an SLA for every mail complaint; nonetheless a
   business-day-only assumption is insufficient for that channel.
4. [Cloudflare's Email Service FAQ](https://developers.cloudflare.com/email-service/reference/faq/)
   limits Sending to transactional use. Its
   [suppression documentation](https://developers.cloudflare.com/email-service/concepts/suppressions/)
   describes provider-validated complaint suppression, but that is distinct from
   direct role-mail reports and amail account-level intervention. Native outbound
   lifecycle feedback and the tested stop/block path remain required.

**Inference:** these primary sources justify working, monitored contacts and
effective intervention. They do not establish a requirement for a bespoke
per-arrival machine alarm. An accountable external-mailbox process can satisfy
the operational obligation; an unmonitored mailbox cannot. No additional
academic automation hypothesis is needed to change that normative conclusion.

## Why A is a coherent complete product, not an MVP shortcut

The complete user journey is native login, agent-managed addresses, ZIP-authored
sending and retrieval, combined metadata/body/semantic search, privacy-safe
diagnostics, safe abuse containment and a truthful release/install experience.
Removing an unrequested administration product does not remove those outcomes.

| Trade-off | A: direct forwards + owner process | B: role Worker + outbox/digest/lease |
| --- | --- | --- |
| Role-mail delivery dependency | Provider routing and external mailbox | The same dependencies plus Worker runtime, D1, application forwarding and deployment correctness |
| Unknown reporter lands in Junk | Owner must review Junk | Original may still land in Junk; digest can prompt review but cannot prove attention |
| Per-arrival machine notice | Not promised | Available after real handler/outbox/digest acceptance; cannot detect messages rejected before invocation |
| Configuration failures | Bounded independent rule/destination checks can detect them | Cron audit and lease can detect them, but successful renewal still does not prove mailbox attention |
| Confidential content duplication | No new application copy, mailbox-access integration or model transfer | Content-free arrival ledger, but more capabilities and original-context privacy surfaces to verify |
| Operational ownership | Required | Still required; automation does not respond to valid reports on its own |
| User fit | Matches the explicitly selected present mechanism | Appropriate later if unattended alarms/agent processing become an explicit supported outcome |

At current evidence, B introduces a new critical-path component before proving
that the missing user-valued outcome is unattended notification. Complexity is
not evidence of safety. Conversely, choosing A while concealing its human
attention dependency would be wishful relaxation. That dependency must be
visible before enabling public sending.

## Concrete v0.1.0 gate for A

### Required operational outcomes

| Gate | Acceptance evidence | Current disposition |
| --- | --- | --- |
| Four protected standard addresses | Exact enabled provider-owned literal direct forwards at apex and mail subdomain; one verified private destination; no overlap with user aliases, no temporary test route left behind. | Current bounded readback and earlier four-message receipt exist. Reuse these facts; no new four-message replay merely to produce a green role-Worker aggregate. |
| Role-name compatibility | Confirm case-insensitive role handling and provider Postmaster behavior separately if existing evidence does not cover them. | Lowercase receipts alone do not close this detail. An incremental transport/protocol check can be scoped without redoing the full journey. |
| Accountable monitoring | Explicit owner or substitute accepts Inbox **and Junk** review often enough to handle Cloudflare notices within 24 hours; absence/unavailability means sending is held or covered by an authorized substitute. | Confidential mailbox selection does not settle this commitment. Ask only this unresolved ownership question, not which mailbox or whether to build an admin UI. |
| Safe handling and intervention | From a controlled report, attribute a known test sender using protected headers/provider ID, apply and verify account/recipient hold, record an opaque audit reference, and use a separate official response path if a reply is needed. | Reuse an already accepted drill if one exists; otherwise this bounded deployed drill remains required. Never reply directly from the private forwarding mailbox, which would reveal its address. |
| Continuing machine configuration checks | Check exact route shape/ownership and verified-destination equality with restricted read credentials, bounded pagination, no redirects and fixed public labels. Failed, unreadable or stale checks deny new public sends. | Current GET probe demonstrates the read capabilities, not scheduled continuing coverage. Adapt a bounded check without routing mail through a new application component. |
| Automatic feedback and emergency stop | Existing outbound provider feedback/suppression, local attribution/holds, account/global stop and idempotency contracts pass deployed evidence. | Unchanged release requirements; direct-mailbox choice is not a fallback for outbound Queue/event acceptance. |
| Truthful description | Internal runbook explains manual review, Junk coverage, protected contact values and limits; public material exposes role addresses, not the private destination, and promises neither guaranteed Inbox placement nor automatic report handling. | Update only after the chosen contract is adopted. |

For a concrete machine-check product contract, use an hourly target and reject a
configuration-health attestation older than six hours, with immediate failure
invalidating it. These are proposed conservative operating defaults, **not**
provider guarantees or a substitute for mailbox review. They allow several
missed scheduled executions without treating an unbounded stale check as healthy.
The engineering owner can choose the existing hosted/control-plane mechanism;
no new web frontend, mail-body store, external mailbox OAuth integration or
per-message role Worker is required for this check. A scheduler's own outage
must cause freshness expiry, not an eternal success bit.

**The observed Junk placement is a real acceptance constraint, not cosmetic.**
Safe-listing `mail@moesegfault.dev` concerns that official sender; arbitrary
complainants retain their own sender identities when forwarded and are not
thereby made safe. Cloudflare documents that forwarding rewrites the envelope
sender but leaves the `From:` header intact in its
[Postmaster reference](https://developers.cloudflare.com/email-service/reference/postmaster/#sender-rewriting).
Microsoft's [Outlook.com Junk guidance](https://support.microsoft.com/en-us/outlook/mail-goes-to-the-junk-folder-by-mistake)
describes Not Junk/safe-sender actions for selected senders and automatic Junk
deletion. Therefore the chosen operator must be able to inspect and recover
reports in Junk **before** deletion, safely examine protected message headers,
and take a tested hold/block/response action. A future authorized agent could
perform this review, but no existing mailbox access, folder coverage or renewal
permission is assumed here. Do not disable spam filtering globally, safe-list
all strangers, or expose the mailbox credentials to create an apparent pass.

Human attention is not machine-provable from route configuration. Do not
manufacture a `mailbox_reviewed` signal from delivered events or interpret
configuration freshness as lossless report detection. Periodic receipt drills
and owner review provide complementary evidence; choose their continuing
cadence in the operating commitment, and do not continuously flood role
addresses with synthetic mail.

### Stop conditions

Keep or return global public sending to held when the owner cannot cover the
review obligation, destination becomes unverified, a protected route drifts,
configuration checks fail/expire, a confirmed report cannot be acted upon,
feedback handling fails, or an incident merits containment. Receiving, retrieval
and search should remain usable. A single untrusted report must not by itself
automatically disclose data, hold an unrelated principal or execute instructions.

## Necessary implementation-contract reconciliation (assigned to engineering)

Current `crates/mail-worker/src/lib.rs::check_send_policy` computes public
readiness from global allowed + four release attestations +
`role_monitor_healthy`, which reads `ROLE_MONITOR.role_monitor_health`. Both
`infra/deploy/check_production_role_graph.py` and production rollout documents
assume that component. Therefore A is **not** enabled by documentation alone.

The engineering owner must express the adopted operational-contact contract
explicitly and fail closed on missing/unknown policy or evidence. Separate
direct-forward configuration freshness from Worker arrival/digest health;
never fabricate one mode's lease from another mode's checks. Preserve the
external CLI/ZIP/API, `send_held` behavior, account holds, native outbound
feedback, privacy and one-use canary semantics. Test expiry/equality, missing
state, unavailable provider/D1, route/destination drift, scheduler failure,
conflicting/stale attestations and emergency hold on GitHub Actions, then verify
the deployed mode and actual intervention path while sending remains held.

Use the strict **api-only** trace graph for a release that does not include the
role producer. Do not loosen topology allowlists to accept arbitrary producers,
leave a role D1/Email capability attached to Mail solely because old config has
it, or ship an active unused operations component by accident. Reconcile
production deployment guards, attestations and release-gap maps together. Any
existing staging role resource must be inventoried and safely made dormant or
retired through its own reviewed transition; preserve historical failures and
necessary audit evidence. No live cleanup is authorized by this proposal.

The Mail API's privacy/tracing acceptance, independent external outbound oracle,
multi-principal isolation, quotas/reserved names, real production cutover and
release publication remain separate blockers. Adopting A closes no such gate.

## What is settled, and the one consequential clarification

**Already settled by the user:** keep standard roles; forward to the selected
private mailbox; no ticket/admin page now; notification/agent operations center
later; official messages use `mail@moesegfault.dev`; destination remains secret.
Do not ask these questions again.

**Still needs explicit confirmation before public send:** who will review Inbox
and Junk and handle Cloudflare abuse notices within 24 hours, including periods
when the owner is busy or away? Suggested single question:

> Until the later agent operations center exists, can you or a designated
> substitute cover Inbox and Junk review and respond to Cloudflare abuse
> notices within 24 hours? If coverage is unavailable, sending stays paused;
> there is no new admin page to maintain.

Do not presume the answer from a private mailbox address or the owner having
confirmed four receipts. If the owner does not accept manual coverage, do not
silently force B: first agree the needed unattended outcome and an authorized
actor capable of responding. B's accepted intake/digest alone remains
insufficient for autonomous complaint resolution.

## Decision-record handling

If adopted, add a dated supersession note to the existing role-monitor proposal,
release-gap map and operational runbook, preserving failed historical evidence.
The postponed Worker can remain a separately scoped future design, but must not
be advertised as deployed, required or accepted. Record owner commitment and
receipt/intervention outcomes using opaque references, never the confidential
destination or raw complaint content. This document is a proposal until the
release owner explicitly records adoption and engineering reconciles the
enforced contract.
