# Offline staging live-tail observer: independent review

Status: static review and source-level recheck, 2026-09-29. This review inspected the untracked parser, synthetic tests, prototype note, the address-add incident contingency, and `crates/mail-worker/src/trace.rs`/the address-add call path. It did not run tests or connect to Cloudflare. The observer remains offline-only and is not an authorization to dispatch E2E.

## Findings

1. **Run attribution: resolved in the parser; future runner remains ungated.** The first draft accepted any coherent `addresses_add` chain, so a different caller's sole request could masquerade as the approved E2E. The revised `finish(clean_end=..., expected_request_id=...)` requires a valid, privately obtained server request ID and `_label` compares it with the root before positive classification. Absent or mismatched IDs now yield fixed `UNVERIFIED` reasons. The prototype note correctly says the existing harness does **not** yet supply this binding; operational integration must extract it from the authorized CLI response or failure correlation header/stderr in memory, without publishing it.
2. **Producer-impossible event shapes: resolved at source level.** The first draft accepted a missing `duration_ms_bucket`, `response_bytes_bucket` on `mail_api` events, and root outcome/error-code combinations impossible under `trace.rs::exit`. The revised validator rejects these and the synthetic suite contains hostile fixtures. This recheck is static only; tests remain unrun.

## Positive boundaries and limits

The module has no network/subprocess/write path. It bounds frame bytes, aggregate bytes, frame/event count, and observation time; retains only validated projections; suppresses raw input and exception text in its own return strings; and fails closed on visible malformed, sampled, warning, loss, and unclean-end signals. Cloudflare's real-time logs documentation says sampling can drop messages and warnings appear, but the parser alone cannot detect silent loss or establish an operational readiness gate. Its strict `scriptName` requirement rejects the documented `null` example, reducing availability rather than falsely accepting a source. The final runner's transport, server-side POST filtering, privacy preflight, cleanup and run-correlation behavior are unimplemented and therefore unverified.

Source: [Cloudflare Real-time logs](https://developers.cloudflare.com/workers/observability/logs/real-time-logs/).
