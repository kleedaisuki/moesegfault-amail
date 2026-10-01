# Independent review: hosted native Cron complete-item liveness fixture

Date: 2026-10-01. Worktree: `.temp/cron-liveness-implementation`.

## Candidate boundary and decision

**GO for exact-SHA nondeploying GitHub-hosted execution at
`74e1db4249e168f294bf890b60f5b15f1125edf8`.** The original P1 R2 constructor
defect below is resolved. No remaining substantive fixture blocker was found.
This is a static fixture assessment, not a runtime-pass claim, production liveness
proof, or release approval.

Initially reviewed HEAD/base `cb50b35e1672e33a503e423c125016235f81386c` plus the
uncommitted candidate. The two fixture modules and fixture notes were untracked;
CI and package script were tracked modifications. Production working changes
were inspected only to derive the fixture's intended observable contracts,
not independently approved in this review. Initial snapshot SHA-256 values:

| Reviewed file | SHA-256 |
| --- | --- |
| `infra/tests/worker-boundary/maintenance-liveness-observer.mjs` | `ECB1415E8C8FB248E595260028F656B2658DCE713D313827A5AF3BF398641E4E` |
| `infra/tests/worker-boundary/maintenance-liveness.test.mjs` | `39BA3A6EC78EA50F3632117EB1CCB33001DC7717D7EF52F4A996BDA0F3FBA466` |
| `docs/mail-cron-liveness-fixture-notes-2026-10-01.md` | `A15BECACD3BA36F22272DB26BE3E1FFE004C788FE231F83EF19092495F1EB1A8` |
| `.github/workflows/ci.yml` | `EF9004458C149CAB39CC548061929101F42FC32DB0E12D1706111F94533FD30F` |
| `infra/tests/worker-boundary/package.json` | `551207A2F7EB068B9A49B52315D07018672F2043F9D4023455ED1885C69A843A` |

Final re-review covers the committed fixture `764dcbe` and one-line correction
`74e1db4`, relative to the same base. HEAD is the full SHA in the decision above;
only independent review documents remain untracked. All scoped files otherwise
retain the initial hashes; the corrected observer SHA-256 is
`1D9EEDFF26DC8B18401CA36A948FA32354A70670FBA88ADD2467B18654CB5703`.

## Evidence and independently checked contracts

### Resolved P1: Preserve R2 constructor identity before forwarding callable methods

Location: `maintenance-liveness-observer.mjs`, `bucket()` get trap (lines 74-84
of the reviewed snapshot). Confidence: high, demonstrated by source contracts.

The initial generic callable wrapper also wrapped `constructor`, returning an anonymous
arrow function rather than native `R2Bucket`. `worker-0.8.7/src/env.rs` calls
`obj.constructor().name()` when `env.bucket("MAIL_BODIES")` is acquired and rejects
the resulting name. The first accepted projection could not GET its archive and
all fixtures acquiring the bucket could fail, so that candidate could not provide
intended progress evidence. Correction `74e1db4` now returns `target.constructor`
explicitly before wrapping actual I/O methods. Independently inspected the exact
one-line fix and final current modules, and reran both syntax checks; the obligation
is now satisfied while actual R2 methods retain native receiver forwarding.

The earlier provisional progress message mistakenly described R2 forwarding as
correct before this callable-constructor case was checked. That preliminary
assessment was withdrawn immediately when the defect was found; it is not evidence
supporting the initial snapshot. The resolved finding records the corrected judgment.

- Reused the existing native D1 observer review after searching relevant document
  filenames. Inspected complete new modules, shared accepted-send fixture,
  production admission/phase dispatch and relevant projection/submission paths,
  pinned package/lockfile, module rules and CI ordering.
- The actual workers-rs binding cast in cached `worker-0.8.7/src/env.rs` checks
  `obj.constructor().name()`. D1 database and prepared proxies forward constructor;
  the final corrected R2 proxy also forwards constructor explicitly.
  Every bind result remains observed. Individual executors call the real native
  receiver; batch unwraps the exact native prepared objects and calls native batch
  once, preserving transaction semantics rather than replacing it with separate SQL.
- Cached `worker-build-0.8.5/src/main.rs` generates `scheduled(arg)` calling
  `exports.scheduled.call(this, arg, this.env, this.ctx)`. Its shim inherits
  WorkerEntrypoint. The observer constructor retains context and supplies wrapped
  environment to `super`; `await super.scheduled(event)` therefore retains the real
  Rust handler, bindings and context. `worker-0.8.7/src/schedule.rs` converts the
  native numeric scheduled timestamp and exposes `schedule()`.
- The lockfile pins Miniflare **4.20260730.0**, whose cached declaration returns
  the experimental Fetcher from `getWorker()`. Its cached serializer supports Date
  hydration. The official API example explicitly uses
  `getWorker().scheduled({ scheduledTime: new Date(1000) })` and returns an outcome
  object. The candidate follows this interface, not a numeric scheduledTime shortcut.
  Native interoperability still requires the hosted execution.
- The real-delay case awaits a native timer before each real chunk executor,
  never replaces its SQL/result, and counts a chunk only after successful native
  return. Sequential production writes imply at least **66 * 300 = 19,800 ms**;
  independent Node performance time additionally checks the lower bound. Exact
  reconstructed 4,000,000-character text plus terminal `sent` distinguishes whole
  publication from a successful-looking prefix. A 15-second per-chunk cutoff would
  fail those assertions. This proves neither remote latency nor platform lifetime.
- The cutoff jump occurs after successful chunk 40; the remaining 26 chunk writes
  and real publication batch are observable after the jump. Full readback and
  terminal state require publication. No new phase is permitted; the later retention
  row remains. Logical time injection does not simulate binding cancellation.
- The outbound setup jump happens after its real stale-reservation UPDATE and
  crosses the 15-second slice before first admission. The addresses-first jump
  consumes 56 seconds before outbound entry, exceeding the 55-second entry limit.
  It expects no outbound setup, no due CAS, no R2 call, no chunk, and both seeded
  journals accepted with due=0.
- Due IDs are captured from the real due UPDATE bind position `args[1]`; independent
  second-journal due=0 and absent message readback support the untouched-next-item
  claim. R2 GET evidence specifically requires only the first immutable ZIP; setup
  and readback use direct native handles outside observer instrumentation. This is
  evidence for current call paths, not arbitrary future claim methods or SQL shapes.
- Slot arithmetic is correct: `1680000300000 / 300000` has integer slot residue 1;
  subtracting one slot yields addresses-first. Eight consecutive slots cover all
  starts. The same Miniflare worker is reused sequentially for duplicate slot 3
  and skipped-to slot 19 (same residue 3), so the test rejects invocation-count
  rotation rather than merely proving isolated cold-start order. It does not claim
  fairness under arbitrary missed deliveries or operational isolate persistence.
- Each fixture owns fresh native D1/R2, uses the existing synthetic one-use
  held-canary insertion guard, verifies global held state and consumes/expires each
  grant before dispatch. No EMAIL or real provider binding exists. The only allowed
  external request is the exact read-only local routing inventory stub; every other
  egress increments an asserted counter and throws. No provider mutation is needed.
- Date.now replacement exists only in the observer scheduled scope and is restored
  in `finally` after awaited production work. These test modules are selected by a
  separate package script/CI step after worker-build, not imported by production
  code or configured as its deployment entrypoint. Module-global policy/evidence
  is appropriate only for this isolated, serial test protocol, not a production
  invocation-accounting design.

## Validation performed and limits

Both new modules passed `node --check`; `git diff --check` passed. No local project
tests/builds, runtime Miniflare invocations, deployment, provider calls, commits or
pushes were performed. Only this review document was written.

The next gate is hosted CI on the exact committed source, including native proxy
interoperability, wall timer behavior and all readback assertions. Current notes
honestly mark this pending. No CPU/RSS, remote D1 quota, error-path coverage,
end-to-end deadline, or general fairness claim follows from static approval.

References checked: [Miniflare scheduled-event API](https://developers.cloudflare.com/workers/testing/miniflare/core/scheduled/),
[worker-build 0.8.5 handler generation](https://github.com/cloudflare/workers-rs/blob/v0.8.5/worker-build/src/main.rs),
[scheduled runtime contract](https://developers.cloudflare.com/workers/runtime-apis/handlers/scheduled/),
and [Workers production practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/).
No new academic claim is made by this focused fixture review.
