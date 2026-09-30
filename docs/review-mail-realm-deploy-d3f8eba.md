# Independent review: realm-safe Mail deployment wrapper, d3f8eba

Date: 2026-10-01. Scope: commit
`d3f8ebab70c463a277317db49fa8da01626803b0`, its three-file delta and the
existing isolation/binding helpers it invokes. This follows the
[api-only graph review](review-production-api-only-graph-f62a1d9.md).
Concurrent CI edits are outside this review; no CI or production implementation
was modified by the reviewer.

## Decision

**GO for hosted source-only checks of the coherent candidate. No substantive
defect found in this narrow change by inspection.** This is not a test-pass,
deployment approval, serving acceptance, contact adoption, human attestation or
public-send authorization. No local tests/builds, provider calls, deployments,
migrations or mail sends were performed. Public documentation was consulted.

## Contract assessment

| Surface | Reviewed behavior |
| --- | --- |
| Production compatibility | Omitted target still selects production, requires main and GITHUB_OUTPUT, uses the same env-free Wrangler command, three secret keys, timeout, recovery UUID and fixed production labels. No public interface is silently redirected. |
| Staging realm | Explicit target requires the exact release branch, staging confirmation, api-only topology and valid Queue ID before temporary secret creation or subprocess execution. Command always contains `--env staging`; no inferred environment or fallback exists. |
| Isolation | `check_staging.check` checks exact staging Identity, HTTP route, domain, Mail D1/R2 and ingress destination/service plus absent production official sender. `expected_bindings(queue-api)` additionally rejects extra/duplicate/renamed Mail D1/R2 entries and demands exact staging Queue source shape. |
| Credentials | Secret JSON includes only OpenRouter, Email Routing and ingress keys, with restrictive permissions under repository `.temp`. Confidential forwarding destination is not uploaded. Realm credential provenance remains the protected workflow's obligation, correctly disclosed in the document. |
| One-shot operation | One captured subprocess invocation with timeout; no automatic retry on failure or timeout. Raw stdout/stderr and caught error details do not reach normal diagnostic output. |
| Recovery pin | Exactly one matched UUID may be written on failed command as recovery metadata, but command failure still returns nonzero. Successful capture does not prove serving, bindings, capture-off or Queue acceptance. |
| Oversized result | Output-size rejection now precedes UUID extraction/output, so an oversized successful or failed response cannot emit a recovery pin. This repairs the prior ordering without relaxing production acceptance. |
| Cleanup | Secret-file path is retained before writing and unlinked through finally on success, nonzero command, rejected result or timeout. No file or provider mutation was performed during this review. |

The size check is a bounded **acceptance** condition after `subprocess.run`
captures its output; it is not a streaming memory cap. The helper's existing
capture strategy has not been converted into one. No demonstrated resource
regression was identified in this extension, and the new document appropriately
uses bounded-output acceptance rather than claiming bounded subprocess memory.

## Tests and evidence limits

`test_deploy_mail_realms.py` inspects actual constructed command arguments,
temporary secret JSON keys/values and removal, mocks only deployment execution,
and exercises production-default/staging-success, recovery-only failed exit,
missing/duplicate/malformed/oversized output, timeout and one-attempt behavior.
Negative cases require that secret creation and subprocess execution never
occur for wrong realm/branch/confirmation/topology/Queue or missing credentials.
The real staging config and binding guards are used in successful scenarios;
an explicit guard failure also verifies redaction and pre-mutation denial.

These are authored synthetic contracts, not executed results. They cannot prove
the origin of protected secrets, actual Wrangler output shape, live serving
isolation, immutable-version attachments or effective provider privacy. The
same-run Queue pin, new API recovery/version output, subsequent `queue-api`
binding pin, strict Queue ownership, independent sink/API privacy and held-state
readback must be composed correctly by the independently reviewed workflow.
The wrapper alone is deliberately not the full promotion authorization gate.

## External grounding

[Cloudflare Wrangler environments](https://developers.cloudflare.com/workers/wrangler/environments/)
describes explicit named-environment selection and non-inheritable environment
bindings/secrets. Requiring `--env staging` and distinct workflow credential
selection is consistent with that contract. Configuration isolation cannot
independently establish secret provenance or current remote attachments.

The earlier [graph review's systems-research grounding](review-production-api-only-graph-f62a1d9.md#external-grounding)
continues to apply: command success and a returned identifier are narrower than
application-observed safety. No new academic mechanism is needed for this
bounded wrapper change; separate serving/privacy/hold evidence remains the
appropriate operational remedy rather than an automatic deployment retry.
