# Cron complete-unit admission policy

Date: 2026-10-01. Scope: `crates/mail-worker/src/maintenance.rs` only.
Status: implemented source and deterministic policy tests; not locally built,
executed, deployed, or release-approved. Scheduler integration is owned separately.

## Reused decisions

The root workspace design
`.temp/cron-liveness-deadline-design/docs/mail-cron-liveness-deadline-design-2026-10-01.md`
and [maintenance budget ADR](mail-cron-budget-architecture-decision-2026-10-01.md)
define complete-item admission rather than chunk cancellation. The existing
`database::MaintenancePhase::ALL` owns phase identity and fixed statement grants;
this policy imports that identity without changing the database adapter.

## API and caller contract

`MaintenanceTurn::new()` captures actual invocation entry using `Date.now()`.
Call `turn.enter(phase)` **before** database construction, claims, setup SQL, or
inventory. Entry admits one compound bounded-setup-plus-first-complete-unit
operation. Reuse that `PhaseTurn` for the entire phase; call `admit()` before each
item's due/claim/write boundary and move its noncloneable `WorkPermit` to the
complete accepted/cleanup operation. Do not obtain another phase entry to reset
the slice or first-unit entitlement.

| Boundary | Ordinary phases | Outbound / Addresses |
| --- | --- | --- |
| Phase entry | Observed elapsed < 115 s | Observed elapsed <= 55 s (60 s before cutoff) |
| First unit after setup | Entry entitlement; no new time rejection | Entry entitlement; no new time rejection |
| Subsequent unit | Slice elapsed < 15 s and global < 115 s | Slice elapsed < 15 s and global <= 55 s |

The first unit may start after slow setup crosses 15 s or even 115 s. This is an
explicit consequence of having already admitted the compound operation at entry,
not permission to admit unlimited new work. Without this entitlement, address
inventory or accepted setup can consume every slice without repairing anything.
The first successful `admit()` consumes that entitlement exactly once. Additional
units recheck both clocks. No time check exists on `WorkPermit`, no `Clone`/`Copy`
is implemented, and no dependency cancellation or per-chunk cutoff is added.
Existing statement budgets, journal leases, fences, and dependency errors remain
authoritative. The policy does not guarantee a hard 120 s completion bound.

## Timing and fairness

Observed elapsed is the maximum of prior observations and nonnegative wall-clock
deltas from actual handler entry. `Cell<f64>` allows the serial phase to borrow
the invocation without reference counting or an independent clock origin. A
nonfinite clock delta fails closed for new admission. Clamping cannot compensate
for arbitrary wall-clock behavior; it specifically prevents backward observations
from restoring elapsed headroom. It is neither CPU accounting nor preemption.

Rotation uses `floor(scheduled_ms / 300000) mod 8`. Delayed and duplicate delivery
retain the intended slot's order; entry elapsed is unrelated to scheduled time.
Negative/nonfinite scheduled timestamps fall back to the established array order.
The formula is tied explicitly to the existing five-minute Cron. Eight consecutive
delivered slots provide all eight first opportunities, but missing all except
one slot class modulo eight preserves one first phase forever. There is no durable
scheduler claim or arbitrary-missed-slot fairness guarantee.

## Evidence and verification boundary

Eight pure Rust policy tests supply private clock observations: rotation and
identity preservation; duplicate/delay/missed-slot behavior and invalid scheduled
timestamps; backward clamping; first entitlement after slow setup; subsequent
slice/headroom boundaries; later phase denial and closed error recognition;
ordinary global denial before slice expiry; invalid clock fail-closed behavior.
No exported production clock override, environment knob, or new dependency exists.

Only direct `rustfmt --edition 2021` and formatting/static source review were
performed for this assignment. No project tests or builds were run, as requested;
the tests are authored evidence targets, not reported passing results. Integration
must wire the module and move permits into whole units, never individual statements.

Official platform references retrieved on 2026-10-01:

- [Performance and timers](https://developers.cloudflare.com/workers/runtime-apis/performance/):
  deployed timer observations do not measure or preempt synchronous CPU work.
- [Scheduled handler](https://developers.cloudflare.com/workers/runtime-apis/handlers/scheduled/):
  use the supplied intended scheduled timestamp for slot identity.
- [Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/):
  invocation-local state and explicit awaited operation boundaries remain intact.

No fresh academic machinery is warranted for this bounded policy change. Its
counterexamples and guarantee are supplied by the existing reviewed design;
complete-item feasibility still needs the separately planned hosted evidence.
