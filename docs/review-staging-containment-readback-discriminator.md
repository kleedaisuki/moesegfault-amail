# Review: staging containment readback discriminator

## Verdict

**GO for GitHub-hosted synthetic CI, then a separately confirmed read-only live diagnostic.** No substantive defect was found in the narrow change `5a27d20` relative to `9c0d5ab`. This is not approval of containment, privacy, production deployment, or resumed Mail API traffic.

## Scope and evidence

Reviewed `.github/workflows/ci.yml`, `infra/tests/staging_containment_readback.py`, its focused synthetic tests, and the discriminator runbook. Traced imported `fetch` and `serving_deployment` in `infra/deploy/pin_staging_mail.py`, and compared emitted fields with the unchanged `crates/mail-worker/check_observability.py` predicate.

- The target is manual and restricted to `refs/heads/codex/amail-v0.1.0`. Explicit confirmation and a lower-case UUID-shaped expected version are checked before source contracts; credentials exist only in the final probe step.
- The transport is bounded to Cloudflare control-plane GET requests for the fixed staging script: deployment, `/settings`, `/script-settings`, deployment. No login, Mail API invocation, telemetry query, settings update, or deployment is added.
- Initial deployment parsing requires exactly one valid version at numeric 100 percent (not boolean), and equality to the explicit expected version. Final equality includes both deployment ID and version ID. A changed deployment discards settings categories.
- Neither settings endpoint substitutes for the other. An endpoint failure still permits the closing deployment read and yields a nonzero, categorical failure. A failed initial/final transport or malformed response emits only a fixed unavailable result.
- Settings output has fixed keys and closed categorical values. Arbitrary response strings, bindings, tail identities, URLs, credentials, exception text and provider bodies are never interpolated. The imported transport bounds the response to 262,144 bytes and uses a 15-second timeout.
- Focused tests cover GET order, wrong expected version, changed deployment, missing/malformed fields, strict booleans versus numeric sampling, endpoint failure, output leakage, and pre-secret workflow ordering. These are source-reviewed test contracts, not observed passing execution.
- `stable100` means the expected deployment bracket and successful settings reads only. Empty settings can legitimately produce `stable100` plus `missing` categories, which the runbook explicitly does not label safe. The authoritative privacy predicate remains unchanged.

## Limits and next action

No local test, build, live request, or push was performed. Hosted CI must establish executable contracts before the separately confirmed live read. The two deployment reads cannot rule out transient intervening rollouts, same-deployment script-settings mutations, or eventual-consistency lag; the artifact appropriately makes no containment inference. Keep those limitations when interpreting the readback. Do not relax the existing privacy gate merely because source configuration or `stable100` looks reassuring.

## Primary references checked on 2026-09-30

- [Get Worker Script and Version Settings](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/script_and_version_settings/methods/get/): `/settings` and observability fields.
- [Get Worker Script Settings](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/settings/methods/get/): `/script-settings`, including script-level Logpush, observability and Tail Consumers.
- [List Worker Deployments](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/deployments/methods/list/): first entry is the latest deployment actively serving traffic; deployment versions carry traffic percentages.

These references support endpoint/schema selection, not safe defaults for absent fields or a provider privacy attestation. The review is a bounded operational diagnostic review, not a new architecture/literature assessment.
