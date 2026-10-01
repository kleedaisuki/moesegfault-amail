# PR 73 provider domain schema review

Date: 2026-10-02 (Asia/Singapore)
Reviewer: independent provider_schema_review agent
Decision: GO for bounded source correction; no substantive defect found.

## Immutable scope

- PR: https://github.com/kleedaisuki/moesegfault-amail/pull/73
- Head: `e8607b6bbc2b376c39077b83b9dd9bf2bf47f56a`
- Base: `bfb02765c622bced2ad2b8a10f6717cce79c6199`
- Examined the four-file diff, domain reader and callers, production host absence and held-state pipeline, closed error diagnostics, and hosted test logs. No production edits, provider requests, local runtime tests, or edits to the old opaque-domain draft were performed.

## Findings

No necessary corrections identified within this change.

The authoritative [Cloudflare List Worker Domains schema](https://developers.cloudflare.com/api/resources/workers/subresources/domains/methods/list/) identifies `result[].id` as an immutable string without an encoding restriction; `cert_id`, unlike domain ID, explicitly has UUID format. Removing the unrelated account-ID 32-hex assumption matches that contract. The 1..256 character and Unicode whitespace/control/format/surrogate exclusions are explicitly local bounded-inventory policy, not a provider-format assertion.

`worker_domain_rows` preserves the original row objects and original ID strings, uses exact string uniqueness without case folding or Unicode normalization, and does not interpolate the ID into a request path. The existing envelope, array bound, service validation, duplicate rejection and optional completeness/count/page validation remain intact. UUID-shaped and nonhex IDs no longer spuriously reject a complete inventory. Case-distinct IDs remain distinct.

`unattached_route` validates every supplied domain hostname before using absence as evidence. Case and one terminal root dot are normalized only in temporary comparison strings; original hostnames and IDs remain unchanged. Missing or malformed hosts fail closed with a fixed reason, including empty labels, leading whitespace, invalid label endpoints and overlong labels. Existing attachment by target hostname or exact API service still refuses admission.

The trace sink service-only surface check remains unchanged apart from corrected ID acceptance. The production inspection still proceeds through script/resource caller checks, route checks, schema verification, global hold/grant/journal/reservation checks and empty address/message/store checks. There is no new bypass, provider write, raw response persistence, or dynamic provider-derived diagnostic prose. Retaining the old ID_UUID enum for diagnostic compatibility is harmless; it no longer controls domain acceptance.

## Hosted evidence actually inspected

- Held production synthetic contracts run [36889771308](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36889771308): exact head matches the review; completed success. Logs show 6 schema and 20 bootstrap tests passed, including opaque ID preservation, duplicate/completeness rejection, malformed-host refusal, case/root-dot attachment refusal, and single bounded no-redirect domain read.
- CI infrastructure job [110462148597](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36889771832/job/110462148597): completed success; logs confirm the new domain cases ran through infrastructure discovery and existing 21 observability privacy/isolation tests passed.
- Workflow syntax run 36889771353 completed success. `git diff bfb0276 e8607b6 --check` passed.

## Acceptance limits

This review accepts source schema behavior and synthetic regression evidence only. No current provider inventory was read. Historical `custom_domain_id_format` rejection does not prove an unattached domain, an empty/held production store, a fresh storage epoch, safe activation, or authorization for a write. A new separately controlled actual inspection remains necessary for those facts. No user login journey is covered, and the user's production account being absent from staging is not a demonstrated production authentication bug.
