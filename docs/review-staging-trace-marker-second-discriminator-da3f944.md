# Independent source review: second historical trace discriminator

Reviewed revisions: `da3f944` (implementation, workflow and synthetic tests) and
`fe77f43` (interpretation). Disposition: **GO for hosted synthetic CI only**.
No substantive defect was found in this bounded change. This is not permission
for a live query, a privacy pass, production rollout, or a claim about the
retained record's producer. No local test, build, dispatch, credential inspection,
retained-record access, push, or production modification was performed.

## Scope and evidence

- The new entry imports the first classifier's immutable staging service and
  exact 2026-09-30 10:42:00–10:42:37 UTC interval. It has no service/time/input
  override, marker-value filter, new request, account login or mail operation.
  It reuses the reviewed `dry=true` transport, completed query/scope echoes,
  200-row pages, 1600-row cap, count consistency and cursor progress checks.
  `first.classify` additionally rejects duplicate/missing IDs for a single-page
  result, wrong service/time, invalid required dataset/source, malformed marker
  suffixes and key-carried markers before any positive classification.
- The second discriminator validates exact `$cloudflare` object shape and its
  optional `$workers` envelope/truncation flag on every returned row, including
  nonmatching rows. Top-level truncation is checked by the first classifier.
  Missing optional flags are not claimed to prove absolute provider completeness;
  true or malformed visible flags cannot yield a positive classification.
- Carrier output is a sorted set of predeclared categories, not copied paths.
  Array leaves are counted by occurrences rather than anonymized-path identity.
  Unknown keys, URLs, marker suffixes, IDs, provider type/eventType strings and
  exceptions cannot reach the printed success or failure line. A nested wrapper
  maps to the fixed remainder instead of recursively expanding the vocabulary.
  Type absence/malformed/unknown states are separate from `mixed`; leaf count is
  separate from carrier and matched-record counts. This can discriminate the
  prior single-row catch-all without presuming multiple causes.
- Source-shape hints reuse the existing constrained event decoder and allowlist.
  They do not identify an emitter, excuse another unsafe carrier, or infer a
  platform cause. Both documents preserve this limitation and keep no-hit,
  malformed, incomplete or expired results unverified. The prior single-row
  result is interpreted correctly: an unknown top-level type is not a mixture
  of types across matching rows, and catch-all is not proof of multiple defects.
- The manual job requires workflow_dispatch, exact target, exact confirmation
  and the project branch. It has read-only repository permission, staging
  Environment, five-minute timeout and non-cancelling dedicated concurrency.
  Credentials are referenced only in the final step; its command is literal
  and does not interpolate arbitrary workflow inputs. Ordinary push/PR events
  cannot run it. Existing hosted `unittest discover -s infra/tests -v` discovers
  the new synthetic module. Source fixtures cover known context/diagnostic
  carriers, exact wrapper handling, unknown type/private-key suppression,
  multiple array leaves, inherited fail-closed checks, wrapped truncation,
  same-window query arguments, exception suppression and workflow guards.

## External schema check and limits

The current [Cloudflare telemetry query schema](https://developers.cloudflare.com/api/resources/workers/subresources/observability/subresources/telemetry/methods/query/)
uses `diagnosticsChannelEvents` under the Workers envelope and exposes an
optional boolean truncation flag. The implementation spells that carrier
correctly. Documented eventType values outside the deliberately selected subset
remain `unrecognized`; this is an explicit fixed partition, not a claim that the
provider schema contains only the selected values. The
[Workers Logs guide](https://developers.cloudflare.com/workers/observability/logs/workers-logs/)
and the REST schema use different displayed type/envelope locations; checking
both exact declared locations is defensible but does not establish which shape
the live row has. Existing research context in the remediation document remains
support for whole-retained-record inspection, not causal attribution here.

Next gate: hosted synthetic CI at the reviewed source. Only after that result
may the root make a separate decision about one same-window read-only dispatch.
The live result, provider completeness, historical serving settings and eventual
privacy remediation were outside this source review.
