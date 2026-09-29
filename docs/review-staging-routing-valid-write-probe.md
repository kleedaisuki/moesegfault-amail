# Independent review: staging Routing Rules valid Write probe

Status: **not approved for live dispatch** (2026-09-29). Reviewed the proposed manual GitHub Actions probe/recovery/audit targets, `infra/provider/probe_routing_effective_write.py`, its synthetic tests, and the intended one-use contract in `docs/staging-routing-valid-write-self-test.md`. No provider mutation or local test execution was performed for this review.

## Blocking findings under correction

1. **Delete after mismatched POST/list IDs.** A successful POST can return provider rule ID B while the complete-list readback contains an otherwise exact-shape candidate with ID A. `probe()` labels this `create_readback_unverified`, but its unconditional `finally` calls `cleanup()`, which uses the shape-matched A and deletes it after GET-by-ID. That violates the design's rule that an ID mismatch freezes cleanup rather than guessing ownership. The synthetic `test_created_response_id_must_match_list_id` currently supplies this path and permits the DELETE. Retain the POST ID and forbid automatic deletion when a candidate's ID differs; the test must assert no DELETE. An ambiguous POST without a trustworthy ID may use the separately documented exact-shape recovery policy, not the successful-but-contradictory path.

2. **Incomplete inventory detection across pages.** `inventory()` validates page/count/total metadata, but does not reject duplicate rule IDs. A moving or malformed paginated listing can repeat a rule while omitting another and still satisfy every current count check, so the target may falsely appear absent. Validate bounded provider IDs and uniqueness over the full inventory; the current two-page fixture repeats the same foreign ID 50 times and should instead use distinct IDs. A quiet mutation window remains necessary because ID uniqueness cannot make Cloudflare pagination atomic.

These are demonstrated source paths, not evidence that Cloudflare has produced the bad responses in staging. Both matter because the probe has write/delete authority over a zone shared with production mail rules. No live probe, recovery, or production promotion should use this revision.

## Resolved during review

The first draft lacked POST/list ID comparison, GET-by-ID ID comparison, validation of foreign action shapes, a once-per-rule capacity count, and a matching rule-name literal; these were corrected. Timeout and malformed 2xx POST replies are now labeled uncertain rather than rejected. An ambiguous DELETE is read back without automatic replay. The probe reports delayed audit as pending, and separate manual recovery/read-only audit targets exist. Synthetic tests now exercise these cases, though they have not yet run in hosted CI.

## Scope and external contract

Cloudflare's [Create routing rule API](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/create/) documents the disabled-rule field, literal matcher, Worker action, `api` source and returned rule ID; these align with the proposed valid request. The GitHub job tests only its current secret's control-plane capability at that moment. It cannot establish the deployed Mail Worker's effective token, enabled-rule delivery, historical address-add cause, SMTP, or absence of a delayed provider reappearance. The design's separately dispatched delayed audit remains a required postcondition even if the initial probe job is green.
