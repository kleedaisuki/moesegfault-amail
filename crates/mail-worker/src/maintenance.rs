//! Invocation-local, cooperative admission of complete maintenance work units.
//!
//! Unit admission never interrupts an admitted item's
//! projection. Statement accounting and durable journal authority remain separate.

use std::cell::Cell;

use worker::{Error, Result};

use crate::database::MaintenancePhase;

/// Five-minute schedule slots; changing the Cron schedule requires policy review.
const SLOT_MS: f64 = 300_000.0;
/// Stop admitting ordinary work with nominal five-second diagnostic headroom.
const CUTOFF_MS: f64 = 115_000.0;
/// Setup and a first complete outbound/address unit need this entry headroom.
const COMPLETE_HEADROOM_MS: f64 = 60_000.0;
/// A soft slice limits additional units, not an already admitted unit.
const SLICE_MS: f64 = 15_000.0;
/// Closed application marker; dependency error text is never classified by prose.
const DEFERRED: &str = "maintenance_deadline_deferred";

/// Rotate phase identity by the intended five-minute schedule slot, not delivery.
///
/// Duplicate or delayed delivery retains its slot's order. Eight consecutive
/// delivered slots give every phase first opportunity; arbitrary missed slots do
/// not guarantee fairness (for example, delivering only every eighth slot).
/// Invalid/nonfinite or negative timestamps defensively use the established order.
pub(crate) fn phase_order(scheduled_ms: f64) -> [MaintenancePhase; 8] {
    let start = if scheduled_ms.is_finite() && scheduled_ms >= 0.0 {
        ((scheduled_ms / SLOT_MS).floor() % 8.0) as usize
    } else {
        0
    };
    std::array::from_fn(|index| MaintenancePhase::ALL[(start + index) % 8])
}

/// One invocation's clock origin; no state survives isolate reuse.
pub(crate) struct MaintenanceTurn {
    /// Actual handler entry, never the potentially delayed scheduled timestamp.
    entered_ms: f64,
    /// Largest observed elapsed delta prevents backward wall-clock reopening.
    elapsed_ms: Cell<f64>,
}

impl MaintenanceTurn {
    /// Capture invocation entry before phase setup or database construction.
    pub(crate) fn new() -> Self {
        Self {
            entered_ms: js_sys::Date::now(),
            elapsed_ms: Cell::new(0.0),
        }
    }

    /// Reserve first-unit entitlement before setup SQL or address inventory.
    ///
    /// Entry admits the compound setup-plus-first-unit operation, not unlimited
    /// new work. Its first permit remains valid even if setup passes the global
    /// cutoff; callers must use `admit` again before each subsequent unit.
    /// Callers must enter once per scheduled phase, then reuse the returned turn.
    /// An entry denial must not claim work or construct a maintenance database.
    ///
    /// ```ignore
    /// let mut phase = turn.enter(MaintenancePhase::Outbound)?;
    /// let db = budget.database(env, MaintenancePhase::Outbound)?;
    /// // Perform bounded setup, then obtain a permit before due/claim/write.
    /// let permit = phase.admit()?;
    /// repair_complete_item(permit, &db, item).await?;
    /// ```
    pub(crate) fn enter(&self, phase: MaintenancePhase) -> Result<PhaseTurn<'_>> {
        self.enter_at(phase, js_sys::Date::now())
    }

    /// Observe a wall-clock delta monotonically; invalid clocks fail closed.
    fn observe(&self, now_ms: f64) -> f64 {
        let delta = now_ms - self.entered_ms;
        let elapsed = if delta.is_finite() {
            self.elapsed_ms.get().max(delta.max(0.0))
        } else {
            f64::INFINITY
        };
        self.elapsed_ms.set(elapsed);
        elapsed
    }

    /// Apply phase entry policy to one observation without accessing dependencies.
    fn enter_at(&self, phase: MaintenancePhase, now_ms: f64) -> Result<PhaseTurn<'_>> {
        let entered_ms = self.observe(now_ms);
        if !has_headroom(phase, entered_ms) {
            return Err(deferred());
        }
        Ok(PhaseTurn {
            turn: self,
            phase,
            entered_ms,
            first: true,
        })
    }
}

/// Serial phase admission; setup shares the first unit's entry entitlement.
pub(crate) struct PhaseTurn<'a> {
    /// Borrowing the invocation clock avoids a second independent timing origin.
    turn: &'a MaintenanceTurn,
    /// Headroom policy follows phase identity, never its rotated array position.
    phase: MaintenancePhase,
    /// Invocation-relative slice start captured before phase setup.
    entered_ms: f64,
    /// Entry reserves exactly one complete unit, even after slow setup.
    first: bool,
}

impl<'a> PhaseTurn<'a> {
    /// Borrow only the invocation, so subsequent mutable unit admission is valid.
    /// Routing setup plus first repair shares a sixty-second absolute allowance.
    pub(crate) fn routing_deadline(&self) -> ExternalDeadline<'a> {
        ExternalDeadline {
            turn: self.turn,
            cutoff_ms: (self.entered_ms + COMPLETE_HEADROOM_MS).min(CUTOFF_MS),
        }
    }

    /// Admit a whole item before its due/claim/write boundary.
    ///
    /// The first unit was entitled at phase entry; setup cannot consume that
    /// entitlement. Later units require an unexpired slice and global headroom.
    /// Pass the permit by value to the complete unit, not to individual chunks.
    pub(crate) fn admit(&mut self) -> Result<WorkPermit> {
        self.admit_at(js_sys::Date::now())
    }

    /// Consume the first entitlement or check additional-unit admission.
    fn admit_at(&mut self, now_ms: f64) -> Result<WorkPermit> {
        let elapsed = self.turn.observe(now_ms);
        if !self.first
            && (elapsed - self.entered_ms >= SLICE_MS || !has_headroom(self.phase, elapsed))
        {
            return Err(deferred());
        }
        self.first = false;
        Ok(WorkPermit { _private: () })
    }
}

/// Immutable external-operation cutoff on the invocation's clamped clock.
/// Copies retain the same origin and cutoff; they never restart an allowance.
#[derive(Clone, Copy)]
pub(crate) struct ExternalDeadline<'a> {
    /// The invocation outlives every serial routing exchange.
    turn: &'a MaintenanceTurn,
    /// Absolute elapsed milliseconds since handler entry.
    cutoff_ms: f64,
}

impl ExternalDeadline<'_> {
    /// Return remaining time; invalid or expired observations fail closed.
    pub(crate) fn remaining(&self) -> Result<std::time::Duration> {
        self.remaining_at(js_sys::Date::now())
    }

    /// Pure observation entry for deterministic cutoff and backward-clock tests.
    fn remaining_at(&self, now_ms: f64) -> Result<std::time::Duration> {
        let elapsed = self.turn.observe(now_ms);
        let remaining = self.cutoff_ms - elapsed;
        if !remaining.is_finite() || remaining <= 0.0 {
            return Err(deferred());
        }
        Ok(std::time::Duration::from_secs_f64(remaining / 1000.0))
    }

    /// Create one child absolute deadline, never a fresh clock or per-page reset.
    pub(crate) fn clipped(&self, allowance: std::time::Duration) -> Self {
        self.clipped_at(allowance, js_sys::Date::now())
    }

    /// Clip against one observation without introducing another timing origin.
    fn clipped_at(&self, allowance: std::time::Duration, now_ms: f64) -> Self {
        let elapsed = self.turn.observe(now_ms);
        Self {
            turn: self.turn,
            cutoff_ms: self
                .cutoff_ms
                .min(elapsed + allowance.as_secs_f64() * 1000.0),
        }
    }

    /// Clip one complete native exchange to ten seconds and all parent cutoffs.
    pub(crate) fn exchange_duration(&self) -> Result<std::time::Duration> {
        Ok(self.remaining()?.min(std::time::Duration::from_secs(10)))
    }
}

/// Noncloneable permission to finish one complete accepted/cleanup work unit.
///
/// This is neither durable ownership nor a statement-budget bypass. There is no
/// deadline method: journal fences and dependency failures may stop the unit,
/// but the soft slice must not truncate its successful chunk/cleanup sequence.
#[must_use = "pass the permit to the complete admitted maintenance unit"]
pub(crate) struct WorkPermit {
    /// Keep construction private to admission; do not derive Clone or Copy.
    _private: (),
}

/// Accepted projection and address setup need a complete-unit headroom reserve.
fn has_headroom(phase: MaintenancePhase, elapsed_ms: f64) -> bool {
    match phase {
        MaintenancePhase::Outbound | MaintenancePhase::Addresses => {
            elapsed_ms <= CUTOFF_MS - COMPLETE_HEADROOM_MS
        }
        _ => elapsed_ms < CUTOFF_MS,
    }
}

/// Encode only the explicit application-owned admission denial.
pub(crate) fn deferred() -> Error {
    Error::RustError(DEFERRED.into())
}

/// Recognize the closed deadline marker, not arbitrary dependency error prose.
pub(crate) fn is_deferred(error: &Error) -> bool {
    matches!(error, Error::RustError(code) if code == DEFERRED)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Supply deterministic entry times without any production clock override.
    fn new_turn(entered_ms: f64) -> MaintenanceTurn {
        MaintenanceTurn {
            entered_ms,
            elapsed_ms: Cell::new(0.0),
        }
    }

    #[test]
    fn rotation_covers_all_phases_and_keeps_identity() {
        for start in 0..8 {
            let order = phase_order(start as f64 * SLOT_MS);
            assert_eq!(order[0], MaintenancePhase::ALL[start]);
            for (offset, phase) in order.iter().enumerate() {
                assert_eq!(*phase, MaintenancePhase::ALL[(start + offset) % 8]);
            }
        }
        assert_eq!(phase_order(8.0 * SLOT_MS), MaintenancePhase::ALL);
    }

    #[test]
    fn duplicate_delay_and_missed_slots_keep_scheduled_order() {
        let scheduled = 3.0 * SLOT_MS;
        let original_order = phase_order(scheduled);
        let delayed_invocation = new_turn(scheduled + 9.0 * SLOT_MS);
        assert_eq!(delayed_invocation.observe(scheduled + 9.0 * SLOT_MS), 0.0);
        assert_eq!(phase_order(scheduled)[0], MaintenancePhase::Storage);
        assert_eq!(phase_order(scheduled), original_order);
        assert_eq!(
            phase_order(scheduled + 8.0 * SLOT_MS),
            phase_order(scheduled)
        );
        assert_eq!(phase_order(SLOT_MS - 1.0), MaintenancePhase::ALL);
        for invalid in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY, -1.0] {
            assert_eq!(phase_order(invalid), MaintenancePhase::ALL);
        }
    }

    #[test]
    fn backward_clock_cannot_restore_slice_or_global_admission() {
        let turn = new_turn(1_000.0);
        let mut phase = turn.enter_at(MaintenancePhase::Deleted, 1_000.0).unwrap();
        let _first = phase.admit_at(1_000.0).unwrap();
        assert!(phase.admit_at(16_000.0).is_err());
        assert!(phase.admit_at(2_000.0).is_err());
        assert_eq!(turn.observe(0.0), 15_000.0);
        assert!(turn.enter_at(MaintenancePhase::Search, 116_000.0).is_err());
        assert!(turn.enter_at(MaintenancePhase::Search, 1_000.0).is_err());
    }

    #[test]
    fn slow_setup_preserves_exactly_one_complete_unit() {
        for identity in [MaintenancePhase::Outbound, MaintenancePhase::Addresses] {
            let turn = new_turn(0.0);
            let mut phase = turn.enter_at(identity, 55_000.0).unwrap();
            let _first = phase.admit_at(75_000.0).unwrap();
            assert!(phase.admit_at(75_000.0).is_err());
        }
        let turn = new_turn(0.0);
        let mut phase = turn.enter_at(MaintenancePhase::Deleted, 114_000.0).unwrap();
        let _first = phase.admit_at(130_000.0).unwrap();
        assert!(phase.admit_at(130_000.0).is_err());
    }

    #[test]
    fn next_unit_requires_slice_and_complete_headroom() {
        let turn = new_turn(0.0);
        let mut phase = turn.enter_at(MaintenancePhase::Outbound, 50_000.0).unwrap();
        let _first = phase.admit_at(50_000.0).unwrap();
        let _second = phase.admit_at(55_000.0).unwrap();
        assert!(phase.admit_at(55_001.0).is_err());
        let turn = new_turn(0.0);
        let mut phase = turn.enter_at(MaintenancePhase::Deleted, 0.0).unwrap();
        let _first = phase.admit_at(0.0).unwrap();
        let _second = phase.admit_at(14_999.0).unwrap();
        assert!(phase.admit_at(15_000.0).is_err());
    }

    #[test]
    fn later_phase_entry_denies_before_setup_and_marker_is_closed() {
        let turn = new_turn(0.0);
        assert!(turn.enter_at(MaintenancePhase::Outbound, 55_001.0).is_err());
        assert!(turn
            .enter_at(MaintenancePhase::Addresses, 55_001.0)
            .is_err());
        assert!(turn.enter_at(MaintenancePhase::Storage, 114_999.0).is_ok());
        assert!(turn.enter_at(MaintenancePhase::Storage, 115_000.0).is_err());
        assert!(is_deferred(&deferred()));
        assert!(!is_deferred(&Error::RustError("dependency timeout".into())));
        assert!(!is_deferred(&Error::RustError(
            "maintenance_statement_budget_deferred".into()
        )));
    }

    #[test]
    fn ordinary_next_unit_obeys_global_cutoff_before_slice_expires() {
        let turn = new_turn(0.0);
        let mut phase = turn.enter_at(MaintenancePhase::Deleted, 110_000.0).unwrap();
        let _first = phase.admit_at(110_000.0).unwrap();
        let _second = phase.admit_at(114_999.0).unwrap();
        assert!(phase.admit_at(115_000.0).is_err());
    }

    #[test]
    fn invalid_clock_observation_fails_closed_and_cannot_reopen() {
        let turn = new_turn(0.0);
        assert!(turn.enter_at(MaintenancePhase::Deleted, f64::NAN).is_err());
        assert!(turn.enter_at(MaintenancePhase::Deleted, 0.0).is_err());
        assert_eq!(turn.observe(0.0), f64::INFINITY);
    }

    #[test]
    fn routing_deadline_borrows_invocation_not_mutable_phase() {
        let turn = new_turn(0.0);
        let mut phase = turn
            .enter_at(MaintenancePhase::Addresses, 55_000.0)
            .unwrap();
        let deadline = phase.routing_deadline();
        let _first = phase.admit_at(85_000.0).unwrap();
        assert_eq!(deadline.remaining_at(85_000.0).unwrap().as_secs(), 30);
        assert!(deadline.remaining_at(115_000.0).is_err());
        assert!(deadline.remaining_at(55_000.0).is_err());
    }

    #[test]
    fn inventory_child_cutoff_is_absolute_and_clipped_to_parent() {
        let turn = new_turn(0.0);
        let phase = turn.enter_at(MaintenancePhase::Addresses, 0.0).unwrap();
        let deadline = phase.routing_deadline();
        let inventory = deadline.clipped_at(std::time::Duration::from_secs(30), 5_000.0);
        assert_eq!(inventory.remaining_at(25_000.0).unwrap().as_secs(), 10);
        assert!(inventory.remaining_at(35_000.0).is_err());
        let last = deadline.clipped_at(std::time::Duration::from_secs(30), 50_000.0);
        assert_eq!(last.remaining_at(50_000.0).unwrap().as_secs(), 10);
        assert!(last.remaining_at(60_000.0).is_err());
        assert!(deadline.remaining_at(f64::NAN).is_err());
    }
}
