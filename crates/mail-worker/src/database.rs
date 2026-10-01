//! Private D1 adapter: foreground behavior is unchanged; maintenance submissions
//! consume invocation-local statement permits before a binding promise exists.

use std::{cell::RefCell, rc::Rc};

use serde::Deserialize;
use wasm_bindgen::JsValue;
use worker::{D1Database, D1PreparedStatement, D1Result, Env, Error, Result};

/// Application ceiling below the independently verified Paid D1 platform limit.
const TOTAL: usize = 800;
/// Fixed grants do not borrow from each other; 18 control tokens remain unused.
const GRANTS: [usize; 8] = [170, 380, 90, 2, 65, 65, 5, 5];

/// Closed maintenance identity; fixed grant indices do not follow rotated order.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum MaintenancePhase {
    Addresses,
    Outbound,
    Embeddings,
    Storage,
    Deleted,
    Orphans,
    Search,
    Abuse,
}

impl MaintenancePhase {
    /// Every scheduled phase must receive a distinct fixed grant exactly once.
    pub(crate) const ALL: [Self; 8] = [
        Self::Addresses,
        Self::Outbound,
        Self::Embeddings,
        Self::Storage,
        Self::Deleted,
        Self::Orphans,
        Self::Search,
        Self::Abuse,
    ];
}

/// Counters contain only application statement counts, never SQL or bound data.
#[derive(Default)]
struct Budget {
    /// All statements admitted in this invocation, including failed submissions.
    spent: usize,
    /// No phase can consume another phase's service opportunity.
    phases: [usize; 8],
}

impl Budget {
    /// Debit all batch members atomically; denial changes no counter.
    fn debit(&mut self, phase: MaintenancePhase, count: usize) -> Result<()> {
        self.ensure(phase, count)?;
        self.spent += count;
        self.phases[phase as usize] += count;
        Ok(())
    }

    /// Check an entire work item's remaining allowance without submitting SQL.
    fn ensure(&self, phase: MaintenancePhase, count: usize) -> Result<()> {
        let phase_remaining = GRANTS[phase as usize] - self.phases[phase as usize];
        if count > phase_remaining || count > TOTAL - self.spent {
            return Err(deferred());
        }
        Ok(())
    }
}

/// Invocation-owned shared state; it is never stored in an isolate-global value.
pub(crate) struct MaintenanceBudget(Rc<RefCell<Budget>>);

impl MaintenanceBudget {
    /// Start fresh for each scheduled invocation; foreground calls do not use it.
    pub(crate) fn new() -> Self {
        Self(Rc::new(RefCell::new(Budget::default())))
    }

    /// Only this constructor admits a phase-bound maintenance database handle.
    pub(crate) fn database(&self, env: &Env, phase: MaintenancePhase) -> Result<Database> {
        Ok(Database {
            inner: env.d1("MAIL_DB")?,
            admission: Some(Admission {
                budget: Rc::clone(&self.0),
                phase,
            }),
        })
    }
}

/// A private capability carried through every nested SQL call and prepared value.
#[derive(Clone)]
struct Admission {
    /// The exact invocation, shared by all eight phase handles.
    budget: Rc<RefCell<Budget>>,
    /// The phase to which every submitted statement is charged.
    phase: MaintenancePhase,
}

/// No Deref, raw handle, exec, dump or session escape hatch is exposed.
pub(crate) struct Database {
    /// Workers-rs binding; only this module may submit through it.
    inner: D1Database,
    /// None preserves established foreground API semantics and error behavior.
    admission: Option<Admission>,
}

impl Database {
    /// Foreground calls keep their existing independent per-request policy.
    pub(crate) fn foreground(env: &Env) -> Result<Self> {
        Ok(Self {
            inner: env.d1("MAIL_DB")?,
            admission: None,
        })
    }

    /// Preparing and binding are not submissions and spend no statement tokens.
    pub(crate) fn prepare<T: Into<String>>(&self, sql: T) -> Statement {
        Statement {
            inner: self.inner.prepare(sql),
            admission: self.admission.clone(),
        }
    }

    /// Reserve space for an item before external/R2 work. Serial maintenance
    /// execution makes the subsequent immediate calls the only consumer.
    pub(crate) fn ensure_remaining(&self, count: usize) -> Result<()> {
        if let Some(admission) = &self.admission {
            admission.budget.borrow().ensure(admission.phase, count)?;
        }
        Ok(())
    }

    /// A batch spends N tokens, including rollback/error/no-op members. Values
    /// from a different phase or invocation cannot bypass accounting.
    pub(crate) async fn batch(&self, statements: Vec<Statement>) -> Result<Vec<D1Result>> {
        if statements
            .iter()
            .any(|statement| !same_admission(&self.admission, &statement.admission))
        {
            return Err(Error::RustError("maintenance_batch_scope_mismatch".into()));
        }
        debit(&self.admission, statements.len())?;
        self.inner
            .batch(
                statements
                    .into_iter()
                    .map(|statement| statement.inner)
                    .collect(),
            )
            .await
    }
}

/// Non-cloneable prepared capability; each execution, including reuse, is debited.
pub(crate) struct Statement {
    /// The raw statement cannot escape this module.
    inner: D1PreparedStatement,
    /// Same invocation/phase authority as the database that prepared it.
    admission: Option<Admission>,
}

impl Statement {
    /// Preserve workers-rs binding semantics while retaining accounting authority.
    pub(crate) fn bind(self, values: &[JsValue]) -> Result<Self> {
        Ok(Self {
            inner: self.inner.bind(values)?,
            admission: self.admission,
        })
    }

    /// Debit before workers-rs constructs/submits the first-row promise.
    pub(crate) async fn first<T: for<'a> Deserialize<'a>>(
        &self,
        column: Option<&str>,
    ) -> Result<Option<T>> {
        debit(&self.admission, 1)?;
        self.inner.first(column).await
    }

    /// A submitted failure or conditional no-op is spent and never refunded.
    pub(crate) async fn run(&self) -> Result<D1Result> {
        debit(&self.admission, 1)?;
        self.inner.run().await
    }

    /// Reading no rows still submits one statement to the D1 binding.
    pub(crate) async fn all(&self) -> Result<D1Result> {
        debit(&self.admission, 1)?;
        self.inner.all().await
    }
}

/// Compare authority without comparing or retaining SQL, owners or bound values.
fn same_admission(left: &Option<Admission>, right: &Option<Admission>) -> bool {
    match (left, right) {
        (None, None) => true,
        (Some(left), Some(right)) => {
            left.phase == right.phase && Rc::ptr_eq(&left.budget, &right.budget)
        }
        _ => false,
    }
}

/// Debit before any binding method is invoked; never compensate after submission.
fn debit(admission: &Option<Admission>, count: usize) -> Result<()> {
    if let Some(admission) = admission {
        admission
            .budget
            .borrow_mut()
            .debit(admission.phase, count)?;
    }
    Ok(())
}

/// The typed application condition crosses workers-rs's fixed Error boundary
/// using one constant; it is not inferred from provider/D1 exception text.
fn deferred() -> Error {
    Error::RustError("maintenance_statement_budget_deferred".into())
}

/// Recognize only our explicit denial, never arbitrary dependency error strings.
pub(crate) fn is_deferred(error: &Error) -> bool {
    matches!(error, Error::RustError(code) if code == "maintenance_statement_budget_deferred")
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Grants fit the global ceiling; denied/repeated batches never borrow/refund.
    #[test]
    fn fixed_grants_count_each_statement_and_preserve_other_phases() {
        assert_eq!(GRANTS.iter().sum::<usize>() + 18, TOTAL);
        let mut budget = Budget::default();
        budget.debit(MaintenancePhase::Outbound, 379).unwrap();
        assert!(is_deferred(
            &budget.debit(MaintenancePhase::Outbound, 3).unwrap_err()
        ));
        assert_eq!(budget.spent, 379);
        budget.debit(MaintenancePhase::Outbound, 1).unwrap();
        assert!(budget.debit(MaintenancePhase::Outbound, 1).is_err());
        for phase in MaintenancePhase::ALL
            .into_iter()
            .filter(|phase| *phase != MaintenancePhase::Outbound)
        {
            budget.debit(phase, GRANTS[phase as usize]).unwrap();
        }
        assert_eq!(budget.spent, 782);
        assert!(budget.ensure(MaintenancePhase::Abuse, usize::MAX).is_err());
    }

    /// Independent invocations and phases are not interchangeable batch authority.
    #[test]
    fn batch_scope_cannot_mix_invocations_phases_or_foreground() {
        let budget = Rc::new(RefCell::new(Budget::default()));
        let make = |phase| {
            Some(Admission {
                budget: Rc::clone(&budget),
                phase,
            })
        };
        let first = make(MaintenancePhase::Outbound);
        assert!(same_admission(&first, &make(MaintenancePhase::Outbound)));
        assert!(!same_admission(&first, &make(MaintenancePhase::Deleted)));
        assert!(!same_admission(&first, &None));
        assert!(!same_admission(
            &first,
            &Some(Admission {
                budget: Rc::new(RefCell::new(Budget::default())),
                phase: MaintenancePhase::Outbound
            })
        ));
        assert!(same_admission(&None, &None));
    }
}
