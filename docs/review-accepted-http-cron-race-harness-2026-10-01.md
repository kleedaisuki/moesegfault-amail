# Review: provider-free accepted HTTP/Cron race harness

Date: 2026-10-01. Reviewed test-only commits `9f9e7b645090b3267a28ec9762ab9d8891a0bff3` and `af145a47c3946f5b779a46fce91ea61c7109da7b` in `.temp/outbound-recovery-validation`.

## Decision

**GO for focused hosted integration; not a runtime pass or deployment approval.** No demonstrated substantive defect blocks executing these two regression cases on the actual hosted built Worker. The existing source is expected to fail their convergence assertions; that is useful regression sensitivity, not a reason to weaken those assertions. No local project build/test, provider call, deployment, push, or production edit occurred during this review.

## Evidence and mechanism

- `accepted-race-entry.mjs` subclasses the imported default built class, without replacing the production shim or copying a Rust handler. The actually installed bundler is worker-build0.8.5; its [versioned shim](https://github.com/cloudflare/workers-rs/blob/v0.8.5/worker-build/src/js/shim.js) exports a proxied WorkerEntrypoint class and forwards constructor arguments through Reflect.construct. This supports the subclass approach in source, but the proxy/host-class combination still requires hosted smoke execution. The research note quotes0.8.7 shim; matching0.8.5 was checked independently here.
- Native D1 constructor identity is preserved. Nonintercepted methods are bound to their native targets, `.bind` returns a rewrapped native statement, and the exact acceptance UPDATE is executed by native `.run()` before signaling the barrier. No SQL result/meta is fabricated. Runtime assertions independently read the native D1 accepted/provider row, original R2 archive and zero projection rows before Cron, detecting a missing or misplaced hook.
- The full normalized acceptance SQL matches current Rust `send_message`, including owner/idempotency and `state='submitting'` guards. It does not match Cron's sent transition. Any future refactor that removes the hook fails finite barrier acquisition rather than silently passing.
- Resolved workers-rs0.8.7 [SendEmail EnvBinding](https://github.com/cloudflare/workers-rs/blob/v0.8.7/worker/src/email.rs) permits the plain synthetic binding; [generated bindings](https://github.com/cloudflare/workers-rs/blob/v0.8.7/worker/src/bindings/email.rs) map `send_with_builder` to JS `.send(builder)` and provider result to `.messageId`. Cloudflare's [Workers sending API](https://developers.cloudflare.com/email-service/api/send-emails/workers-api/) documents that builder/result shape. The stub tests this conversion, not provider validation or MIME transport.
- [Pinned Miniflare core schema](https://github.com/cloudflare/workers-sdk/blob/miniflare%404.20260730.0/packages/miniflare/src/plugins/core/index.ts) supports serviceBindings and outboundService. Node-controlled service callbacks are the barrier channel, not a claim that global fetch can intercept EmailService.
- Real Rust/Wasm request handling, local SQLite/D1 migrations, R2 storage, RSA token verification and owner DELETE remain active. Discovery/JWKS are synthetic allowlisted responses, not a real Identity integration. Normal held-send admission uses a narrow synthetic one-recipient canary rather than globally enabling public send. Embedding is paused and no provider credentials are present.
- The independently encoded Stored ZIP has valid CRC32/local/central/end records. `af145a4` replaces placeholder journal hash with SHA256 of those actual bytes and leaves reservation bytes consistent with the archive, restoring the admission invariant.
- Both tests hold HTTP immediately after durable accepted state and before HTTP projection begins. Cron runs to completion; the second case then executes real public authorized DELETE and real scheduled GC. Resume and same-key replay require stable202/message ID and exactly one synthetic provider invocation. Exact chunk reconstruction protects the nondelete case; physical row/chunk/reservation/work absence and zero used bytes protect delete nonresurrection.

## Nonblocking strengthening recommendations

1. In `accepted-http-cron-race.test.mjs` outboundService, method assertion currently precedes `unexpected++`. A forbidden POST can throw, be handled by Cron, and escape the final unexpected counter. It remains provider-free because the callback never forwards the request, but final zero does not prove no forbidden attempt. Combine method/path allowlisting; count every rejected request before throwing. Do the same for control channel method mismatch if retaining an exhaustive attempt counter.
2. The nondelete path does not assert reservation/usage or quota counters unchanged across resumed HTTP and replay. Add independently expected indexed ZIP charge, snapshot quota counts, repeat Cron once and compare stable storage/quota values. Current assertions establish single message/content/provider invocation, not the entire no-double-charge claim in the design note.
3. Optional stronger postresume delete assertion: recheck R2 archive absence and terminal journal state, not only D1 absence, to catch future archive-only resurrection. Current Rust writes R2 before the selected barrier, so no present executable archive-resurrection path was found.

These are bounded coverage improvements, not reasons to demand live provider integration for the synthetic harness.

## Integration requirements and limits

Run `node --test accepted-http-cron-race.test.mjs` separately after actual worker-build on GitHub Actions with the repository-locked Node/Miniflare setup, finite job timeout and no provider secrets. The test intentionally is not in the default package suite yet. Retain baseline and repaired-artifact results to distinguish product failures from subclass/proxy contract failures. A barrier timeout or builder/native binding failure is harness admission failure, not the product race verdict.

The test covers Cron winning before any future HTTP projection lease is acquired. It does not cover lease expiry and stale token fencing while HTTP already holds an active lease. It does not prove production D1 replication, Paid/Free limits, actual provider delivery, MIME/assets, unknown provider outcomes, or universal exactly-once delivery. Existing deployment/privacy/operational gates remain unchanged.

Reviewed design note: `.temp/email-service-harness/docs/email-service-provider-free-race-harness-2026-10-01.md` at investigation commit `a723eb7`; candidate documentation: `docs/outbound-recovery-adversarial-validation-2026-10-01.md`.

## Follow-up: b6623bd

Independently reviewed exact test-only diff `b6623bda7e24f2a08c22f7c527123e4a9f052e7b` on2026-10-01. **GO for focused hosted integration remains unchanged.** No local project execution was performed.

- Recommendation1 is resolved: both channels now validate method and exact URL together, increment the shared unexpected counter before throwing, and never forward rejected requests. This closes the caught-nonGET attempt accounting gap.
- Recommendation2's storage stability and repeated-maintenance portions are resolved: native reservation and usage rows are captured after Cron projection (or after delete/GC), then compared after HTTP resume, same-key replay and another real scheduled invocation. Ordered queries make comparisons deterministic. These snapshots prove storage does not change from its established pre-resume baseline; they do not independently validate the initial expected charge or outbound quota counters. Those remain optional coverage extensions, not a newly asserted guarantee.
- Recommendation3 remains optional; no production archive-resurrection write was found after the current selected barrier.

The strengthened assertions preserve the original actual-commit barrier and provider-free scope; they do not simulate a successful projection or relax202/single-send/nonresurrection requirements.

## Follow-up: 91ee30c active-lease interleaving

Independently reviewed exact diff `91ee30c3ab46f42edf79f691d7e5ec9ffce08ecd` and its SQL match against `.temp/accepted-recovery-integrity/crates/mail-worker/src/accepted.rs`. **GO for focused hosted integration remains.** No local project execution occurred.

The optional adapter matches the actual normalized projection claim prefix, runs native D1 first, and pauses only after success/changes1. The first accepted barrier returns immediately in this mode; the first claim barrier pauses real HTTP. Native queries assert accepted state, a nonempty token, future expiry and zero projection before immediate Cron. Cron must retain the original token, not claim or publish. Expiring only the persisted deadline then requires a second successful claim and real Cron publication before authorized DELETE/real GC and old HTTP resume. This is a meaningful active-lease deferral and expired-lease takeover regression, without replacing production claim logic or SQL results.

Updated coverage boundary: the earlier unimplemented active-lease fixture gap now has an implemented but unexecuted hosted case. It simulates eligibility by modifying the persisted deadline, not advancing real20-minute wall time. `claims==2` establishes another successful CAS but does not independently inspect whether the replacement token differs. More importantly, old HTTP resumes after the new projector has terminalized state to sent and GC has run: this verifies no resurrection by an actually paused stale HTTP invocation, but cannot isolate token fencing from the separate terminal-state guard while the new owner remains accepted and actively publishing. A future second-claim pause/token comparison and old-writer resume before terminalization would discriminate that narrower live-stale-token property. This is an optional coverage extension, not a blocker to executing the present intended schedule.

The lease case requires migration0010 and is not an unchanged baseline test against the historical nine-migration Worker. The original two acceptance-only tests remain baseline-compatible through separate name selection.
