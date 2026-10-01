# Accepted recovery held-policy fixture correction review

Date: 2026-10-01. Exact correction: `32f21b464b8719fa65005272a4f710f093e38f1d`, parent `25acdf1`. Scope: the two-file fixture/documentation correction, production migrations 0006/0009, shared migration loader, standalone recovery callers, existing HTTP/Cron race fixture, and hosted test discovery.

## Verdict

**GO for exact-revision hosted integration. No substantive defect found in this correction.** This is a setup repair, not evidence that the recovery assertions pass, approval to deploy, permission to unhold sending, or production release acceptance. Hosted run 36804402543 failed at the fixture INSERT with `send_held`; corrected hosted execution is still necessary.

## Evidence and reasoning

- The correction changes only `outbound-recovery-fixture.mjs` and its English validation document. No Rust source, migration, runtime configuration, provider adapter, workflow permission, or production release flag changes.
- Migration 0006 creates global `held` policy and a one-use owner-scoped admission trigger. The fixture arms the exact synthetic issuer/subject, hashes the same synthetic recipient present in its independently encoded ZIP, and resets `canary_used_by` before inserting each accepted journal. The unchanged trigger consumes the idempotency key. Migration 0009 explicitly allows this global-held path without a contact attestation, independently of trigger ordering. No production trigger is dropped or disabled by this correction.
- The post-insert joined assertion requires the global policy still to be `held`, the consumed key to equal this row's idempotency key, and the admitted journal to be `accepted`. The owner join ties the consumption to the fixture principal. It therefore detects both missing consumption and an accidental unhold instead of merely trusting successful insertion.
- The expiry update sets the deadline to database `unixepoch()`. Both production guards require a strictly greater deadline; equality is expired. The consumed grant is expired before reservations/archive setup returns and before scheduled execution. The fresh database has no competing fixture operations; current callers await seeding serially. Re-arming supports multiple synthetic rows without authorizing a live operator campaign or changing global release state.
- Admission is intentionally direct SQL reconstruction of an already accepted durable journal. It does not test HTTP recipient validation, provider acceptance, or a real send. The existing HTTP race fixture separately uses the same held-canary mechanism through actual HTTP admission and a synthetic EmailService adapter; neither fixture proves live provider behavior.
- Each standalone test owns a fresh Miniflare D1/R2 runtime with `cf: false`. Only the exact synthetic empty Cloudflare route-list GET is answered locally; every other outbound request is counted and rejected. The embedding dependency remains blocked, and no Email binding/provider send is introduced. All setup statements occur outside the scheduled invocation under test.
- The shared migration loader still applies all contiguous production migrations. The existing default package script includes `outbound-recovery.test.mjs` and `accepted-http-cron-race.test.mjs`; hosted CI builds the real Rust/Wasm then invokes that package's `pnpm test`. The correction changes neither discovery nor module/import contracts.

## Verification and limits

Static `node --check infra/tests/worker-boundary/outbound-recovery-fixture.mjs` and `git diff --check 25acdf1..32f21b4` succeeded. No project test/build, provider call, deployment, or push was performed locally. Actual D1 trigger behavior, returned row shape, and the eleven recovery assertions must be established on the exact corrected hosted revision. The previously documented full-Cron query budget and live privacy/rollout gates remain independent and unresolved by this fixture setup change.
