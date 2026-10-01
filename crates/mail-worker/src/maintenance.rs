//! Invocation-local, cooperative admission of complete maintenance work units.
//!
//! Unit admission never interrupts an admitted item's
//! projection. Statement accounting and durable journal authority remain separate.

use std::cell::Cell;

use worker::{Error, Result};

use crate::database::MaintenancePhase;
use crate::trace::DiagnosticCode;

/// One phase's terminal result; successful no-ops retain a slot without wire data.
#[derive(Clone, Copy)]
enum PhaseOutcome {
    Complete,
    BudgetDeferred,
    DeadlineDeferred,
    Failed,
}

/// Reviewed nested conditions, retaining presence rather than item identity/count.
#[derive(Clone, Copy)]
pub(crate) enum DeepCondition {
    AddressBatchFull,
    CommittedRouteDisabled,
    ProvisioningRouteDisabled,
    DocumentQuarantined,
    ProviderCooldown,
}

impl DeepCondition {
    /// Stable private slots and existing wire vocabulary are deliberately explicit.
    fn entry(self) -> (usize, DiagnosticCode) {
        match self {
            Self::AddressBatchFull => (0, DiagnosticCode::AddressReconciliationBatchFull),
            Self::CommittedRouteDisabled => (1, DiagnosticCode::NonEnabledCommittedRoutingRule),
            Self::ProvisioningRouteDisabled => {
                (2, DiagnosticCode::NonEnabledProvisioningRoutingRule)
            }
            Self::DocumentQuarantined => (3, DiagnosticCode::SemanticDocumentQuarantined),
            Self::ProviderCooldown => (4, DiagnosticCode::SemanticProviderCooldown),
        }
    }
}

/// Invocation-owned fixed facts; no dependency access, private data or public fields.
///
/// Finish each phase once, note reviewed nested conditions after their original
/// durable boundary, then consume this value once at scheduled invocation exit.
pub(crate) struct MaintenanceDiagnostics {
    /// Unfinished phases are neither successes nor invented failures.
    phases: [Option<PhaseOutcome>; 8],
    /// Repetition never retains frequency or grows the buffer.
    deep: [bool; 5],
}

impl MaintenanceDiagnostics {
    /// Create eight terminal slots and five presence bits without binding access.
    pub(crate) fn new() -> Self {
        Self {
            phases: [None; 8],
            deep: [false; 5],
        }
    }

    /// Retain only the first result and classify exact application-owned markers.
    pub(crate) fn finish(&mut self, phase: MaintenancePhase, result: &Result<()>) {
        let slot = &mut self.phases[phase_slot(phase)];
        debug_assert!(slot.is_none(), "maintenance phase finished twice");
        if slot.is_some() {
            return;
        }
        *slot = Some(match result {
            Ok(()) => PhaseOutcome::Complete,
            Err(error) if crate::database::is_deferred(error) => PhaseOutcome::BudgetDeferred,
            Err(error) if is_deferred(error) => PhaseOutcome::DeadlineDeferred,
            Err(_) => PhaseOutcome::Failed,
        });
    }

    /// Note a closed deep condition synchronously; never await or spend SQL grants.
    pub(crate) fn note(&mut self, condition: DeepCondition) {
        self.deep[condition.entry().0] = true;
    }

    /// Consume once into at most eight terminal failures and five deep conditions.
    pub(crate) fn into_codes(self) -> Vec<DiagnosticCode> {
        let mut codes = Vec::with_capacity(13);
        for phase in MaintenancePhase::ALL {
            let code = match self.phases[phase_slot(phase)] {
                None | Some(PhaseOutcome::Complete) => continue,
                Some(PhaseOutcome::BudgetDeferred) => DiagnosticCode::MaintenanceBudgetDeferred,
                Some(PhaseOutcome::DeadlineDeferred) => DiagnosticCode::MaintenanceDeadlineDeferred,
                Some(PhaseOutcome::Failed) => phase_failure(phase),
            };
            codes.push(code);
        }
        for condition in [
            DeepCondition::AddressBatchFull,
            DeepCondition::CommittedRouteDisabled,
            DeepCondition::ProvisioningRouteDisabled,
            DeepCondition::DocumentQuarantined,
            DeepCondition::ProviderCooldown,
        ] {
            let (slot, code) = condition.entry();
            if self.deep[slot] {
                codes.push(code);
            }
        }
        codes
    }
}

/// Identity indices never depend on enum discriminants or rotated dispatch order.
fn phase_slot(phase: MaintenancePhase) -> usize {
    match phase {
        MaintenancePhase::Addresses => 0,
        MaintenancePhase::Outbound => 1,
        MaintenancePhase::Embeddings => 2,
        MaintenancePhase::Storage => 3,
        MaintenancePhase::Deleted => 4,
        MaintenancePhase::Orphans => 5,
        MaintenancePhase::Search => 6,
        MaintenancePhase::Abuse => 7,
    }
}

/// Preserve existing failure vocabulary; phase identity remains internal only.
fn phase_failure(phase: MaintenancePhase) -> DiagnosticCode {
    match phase {
        MaintenancePhase::Addresses => DiagnosticCode::RoutingReconciliationFailed,
        MaintenancePhase::Outbound => DiagnosticCode::OutboundReconciliationFailed,
        MaintenancePhase::Embeddings => DiagnosticCode::SemanticIndexRetryFailed,
        MaintenancePhase::Storage => DiagnosticCode::StorageLedgerReconciliationFailed,
        MaintenancePhase::Deleted => DiagnosticCode::DeletedMessageCleanupFailed,
        MaintenancePhase::Orphans => DiagnosticCode::OrphanObjectCleanupFailed,
        MaintenancePhase::Search => DiagnosticCode::SearchJobCleanupFailed,
        MaintenancePhase::Abuse => DiagnosticCode::AbuseDataCleanupFailed,
    }
}

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

    /// Capture one ten-second diagnostic tail after all business phases return.
    ///
    /// This is a local waiting allowance, not new business admission or a Queue
    /// cancellation promise. Admitted durable work may already exceed CUTOFF_MS.
    pub(crate) fn diagnostic_deadline(&self) -> ExternalDeadline<'_> {
        self.diagnostic_deadline_at(js_sys::Date::now())
    }

    /// Keep the same invocation clock and immutable cutoff through serialization.
    fn diagnostic_deadline_at(&self, now_ms: f64) -> ExternalDeadline<'_> {
        ExternalDeadline {
            turn: self,
            cutoff_ms: self.observe(now_ms) + 10_000.0,
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

    /// Share the outbound setup-plus-first-item allowance with retained reads.
    /// This deadline never applies to an admitted successful SQL projector.
    pub(crate) fn archive_deadline(&self) -> ExternalDeadline<'a> {
        self.routing_deadline()
    }

    /// Bound Cron embedding exchanges by the original invocation cutoff.
    /// Each exchange is separately clipped to ten seconds, without changing the
    /// foreground embedding policy or interrupting successful fenced persistence.
    pub(crate) fn embedding_deadline(&self) -> ExternalDeadline<'a> {
        ExternalDeadline {
            turn: self.turn,
            cutoff_ms: CUTOFF_MS,
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
    /// The invocation outlives every serial external/local waiting operation.
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

    /// Eight phase failures and repeated deep facts have exactly thirteen codes.
    #[test]
    fn diagnostics_are_fixed_presence_only_and_rotation_independent() {
        let mut diagnostics = MaintenanceDiagnostics::new();
        for phase in phase_order(3.0 * SLOT_MS) {
            diagnostics.finish(phase, &Err(Error::RustError("synthetic failure".into())));
        }
        for _ in 0..30 {
            for condition in [
                DeepCondition::AddressBatchFull,
                DeepCondition::CommittedRouteDisabled,
                DeepCondition::ProvisioningRouteDisabled,
                DeepCondition::DocumentQuarantined,
                DeepCondition::ProviderCooldown,
            ] {
                diagnostics.note(condition);
            }
        }
        let codes = diagnostics.into_codes();
        assert_eq!(codes.len(), 13);
        assert_eq!(&codes[..8], &MaintenancePhase::ALL.map(phase_failure));
        assert_eq!(
            codes
                .iter()
                .filter(|code| **code == DiagnosticCode::SemanticProviderCooldown)
                .count(),
            1
        );
    }

    /// Success and unvisited slots emit nothing; exact deferrals are not prose.
    #[test]
    fn diagnostics_preserve_closed_classification_and_separate_phase_deferrals() {
        let mut empty = MaintenanceDiagnostics::new();
        for phase in MaintenancePhase::ALL {
            empty.finish(phase, &Ok(()));
        }
        assert!(empty.into_codes().is_empty());
        assert!(MaintenanceDiagnostics::new().into_codes().is_empty());
        let mut diagnostics = MaintenanceDiagnostics::new();
        for phase in [MaintenancePhase::Addresses, MaintenancePhase::Outbound] {
            diagnostics.finish(
                phase,
                &Err(Error::RustError(
                    "maintenance_statement_budget_deferred".into(),
                )),
            );
        }
        diagnostics.finish(MaintenancePhase::Embeddings, &Err(deferred()));
        diagnostics.finish(
            MaintenancePhase::Storage,
            &Err(Error::RustError("dependency timeout".into())),
        );
        assert_eq!(
            diagnostics.into_codes(),
            vec![
                DiagnosticCode::MaintenanceBudgetDeferred,
                DiagnosticCode::MaintenanceBudgetDeferred,
                DiagnosticCode::MaintenanceDeadlineDeferred,
                DiagnosticCode::StorageLedgerReconciliationFailed
            ]
        );
    }

    /// Duplicate phase completion is a programming error, not a second event.
    #[test]
    #[cfg(debug_assertions)]
    #[should_panic(expected = "maintenance phase finished twice")]
    fn diagnostics_expose_duplicate_finish() {
        let mut diagnostics = MaintenanceDiagnostics::new();
        diagnostics.finish(MaintenancePhase::Abuse, &Ok(()));
        diagnostics.finish(MaintenancePhase::Abuse, &Err(deferred()));
    }

    /// Supply deterministic entry times without any production clock override.
    fn new_turn(entered_ms: f64) -> MaintenanceTurn {
        MaintenanceTurn {
            entered_ms,
            elapsed_ms: Cell::new(0.0),
        }
    }

    /// Business overrun does not reopen admission or restart the final tail.
    #[test]
    fn diagnostic_tail_is_absolute_and_distinct_from_business_admission() {
        let turn = new_turn(0.0);
        let deadline = turn.diagnostic_deadline_at(200_000.0);
        assert!(turn.enter_at(MaintenancePhase::Abuse, 200_000.0).is_err());
        assert_eq!(deadline.remaining_at(200_000.0).unwrap().as_secs(), 10);
        assert_eq!(deadline.remaining_at(203_000.0).unwrap().as_secs(), 7);
        assert_eq!(deadline.remaining_at(201_000.0).unwrap().as_secs(), 7);
        assert!(deadline.remaining_at(210_000.0).is_err());
        assert!(deadline.remaining_at(200_000.0).is_err());
        assert!(deadline.remaining_at(f64::NAN).is_err());
        assert!(turn.diagnostic_deadline_at(0.0).remaining_at(0.0).is_err());
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
