# Independent review: staging Routing Rules valid Write probe

Status: **source review passed, subject to hosted CI and operational gates; no live dispatch yet** (2026-09-29). Reviewed the proposed manual GitHub Actions probe/recovery/audit targets, `infra/provider/probe_routing_effective_write.py`, its synthetic tests, and the intended one-use contract in `docs/staging-routing-valid-write-self-test.md`. No provider mutation or local test execution was performed for this review.

## Blocking findings and correction status

1. **POST/list ID contradiction — corrected.** A successful POST can return provider rule ID B while readback contains an otherwise exact-shape candidate with ID A. The first draft deleted A in `finally`. The revision carries B through cleanup and freezes on any mismatch, including when the first readback fails but a later cleanup listing finds A. Synthetic tests assert no DELETE.

2. **Incomplete inventory across pages — corrected.** A moving or malformed listing could repeat one rule and omit another while preserving page/count/total metadata. The revision validates bounded IDs and rejects duplicates across the complete inventory; the multi-page synthetic fixtures now distinguish unique and repeated IDs. A quiet mutation window remains necessary because uniqueness cannot make provider pagination atomic.

3. **Explicit POST denial followed by failed readback — corrected.** The prior code could receive 403, fail the first inventory read, then delete a later exact-shape candidate in `finally`. The revision freezes automatic deletion immediately for explicit 4xx or `success=false` provider responses before any readback; the synthetic failure test asserts zero DELETE even when that readback fails. It preserves the bounded denial status and requires separate investigation of a conflicting candidate.

These were demonstrated source paths, not evidence that Cloudflare has produced those responses in staging. They matter because the probe has write/delete authority over a zone shared with production mail rules. The corrected source has no remaining substantive finding in this review; hosted CI and the documented quiet-window/recovery/audit gates are still prerequisites to a live probe.

## Resolved during review

The first draft lacked POST/list ID comparison, GET-by-ID ID comparison, validation of foreign action shapes, a once-per-rule capacity count, and a matching rule-name literal; these were corrected. Timeout and malformed 2xx POST replies are now labeled uncertain rather than rejected. An ambiguous DELETE is read back without automatic replay. The probe reports delayed audit as pending, and separate manual recovery/read-only audit targets exist. Synthetic tests now exercise these cases, though they have not yet run in hosted CI.

## Operational residual

Recovery derives the original alias from `STAGING_E2E_PASSWORD` and the original GitHub run ID/attempt. Freeze rotation of that protected password and changes to the derivation logic until recovery and delayed audit are complete, or the candidate may become undiscoverable. The alias-and-shape recovery target cannot itself know that an earlier POST returned a *contradictory* ID because the ID is intentionally not logged; do not dispatch alias-only recovery after `create_id_mismatch`, a denial conflict, or any known contradictory provider state without separate ID-proven operator evidence. This is a documented procedural constraint, not an executable guarantee.

The three manual jobs share the staging native-mail acceptance concurrency group, but GitHub workflow-level concurrency and out-of-band Cloudflare mutations are not an atomic lock. Before dispatch, exclude pending branch deploys and concurrent route edits, keep the one project-level routing token stable, and confirm the recovery target is available. A green create/cleanup job explicitly leaves `routing_write_audit=pending`; the separate delayed read-only audit must prove exact absence before calling the control-plane check complete. The protected HMAC secret must not be exposed in logs or artifacts. The request layer now refuses redirects, avoiding bearer forwarding outside the fixed Cloudflare API origin.

## Scope and external contract

Cloudflare's [Create routing rule API](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/create/) documents the disabled-rule field, literal matcher, Worker action, `api` source and returned rule ID; these align with the proposed valid request. The GitHub job tests only its current secret's control-plane capability at that moment. It cannot establish the deployed Mail Worker's effective token, enabled-rule delivery, historical address-add cause, SMTP, or absence of a delayed provider reappearance. The design's separately dispatched delayed audit remains a required postcondition even if the initial probe job is green.
