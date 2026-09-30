# Independent review: staging Worker resource discriminator

Reviewed source commit: `284420734c5be46ec1ef9b7b4453fc2fcb5a17d9`.
Review date: 2026-09-30. Decision: **GO for GitHub-hosted synthetic CI**.
No substantive defect found within the bounded diagnostic scope. This is not a
containment/privacy attestation or permission to deploy a trace sink.

## Scope and evidence

Inspected the new reader, its synthetic tests, the manual workflow diff, the
unchanged shared `serving_deployment` parser, and the effective-readback ADR
`d90913c`. Current worktree has no subsequent changes to those reviewed files.
No local tests, build, live Cloudflare call, Mail request, deployment, or push
was performed. Runtime and hosted test success remain unproven.

- The manual job requires workflow_dispatch, the exact target, the release
  branch, staging Environment, distinct case-sensitive confirmation, and a
  lowercase UUID expected version. Synthetic tests precede the only
  credential-bearing step. Secrets remain existing repository-level names.
- A valid normal execution performs exactly deployment, script settings,
  non-versioned script-settings, exact-name Worker resource, deployment GETs.
  Invalid initial serving state fails before representation reads. Representation
  failures do not skip the final bracket. Both deployment UUID and version UUID
  must remain identical, with one 100% version and typed numeric percentage.
- The Worker response requires the exact staging name and a nonempty string ID.
  Invalid identity emits only unavailable/mismatch/invalid categories and never
  settings categories. The shared serving parser is read-only; the existing
  containment checker and serving-pin acceptance logic are unchanged.
- HTTP requests use fixed paths, GET, a 15-second timeout, a 262,144-byte response
  bound, no redirect traversal, HTTP 200, literal success=true, and object result.
  Exception/provider bodies, raw JSON, URLs, identifiers and unknown fields are
  not emitted or persisted by the diagnostic.
- Type bins preserve missing versus null and Boolean versus numeric values.
  Every tail/destination member is validated before aggregate categorization.
  Explicit capture flags, Issues, exports, sampling and containers are separate.
  No missing value, zero sampling, malformed collection or successful transport
  is rewritten as disabled capture. stable100 describes successful bracketed
  representation reads, not safe settings.

## External contract verification

The current official [Get Worker API](https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/methods/get/)
was independently retrieved. It documents the exact REST path
`/accounts/{account_id}/workers/workers/{worker_id}`, accepts name or immutable ID,
and permits Workers Scripts Read/Write or Workers Tail Read. The resource has
top-level identity and observability, with optional capture children and Issues.
The [pinned official Python Worker model](https://github.com/cloudflare/cloudflare-python/blob/c9dd8956de93575640e06ea28e802951175099a0/src/cloudflare/types/workers/beta/worker.py)
agrees with the inspected fields. This resource is not a selected-version
snapshot; previews_base_config must not replace its top-level observability.
The implementation does not make that substitution.

## Remaining gates and interpretation limits

Run hosted synthetic CI first, then separately authorize the exact read-only
manual diagnostic under the operator settings/deployment freeze. A changed or
unreadable final deployment discards categories. Unavailable Beta resource or
ambiguous children remain UNVERIFIED, not absent/off. Even a stable bracket
cannot exclude a concurrent non-versioned settings edit. Any later acceptance
policy or settings correction needs its own source review and evidence; this
review does not authorize weakening the existing containment gate.
