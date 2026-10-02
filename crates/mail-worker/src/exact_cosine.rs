//! Exact persisted-vector cosine with one validated query norm per scan batch.

/// A borrowed 256-coordinate query whose finite, positive norm is established.
/// Construction does not normalize or round stored coordinates; scoring retains
/// the historical f64 sum order and denominator, including near-tie score bits.
pub(crate) struct QueryCosine<'a> {
    coordinates: &'a [f32],
    squared_norm: f64,
}

impl<'a> QueryCosine<'a> {
    /// Reject malformed queries before examining candidates; do not persist state.
    pub(crate) fn new(coordinates: &'a [f32]) -> Option<Self> {
        if coordinates.len() != 256 || coordinates.iter().any(|x| !x.is_finite()) {
            return None;
        }
        let mut squared_norm = 0.0;
        for coordinate in coordinates {
            let value = *coordinate as f64;
            squared_norm += value * value;
        }
        if squared_norm <= 0.0 || !squared_norm.is_finite() {
            return None;
        }
        Some(Self {
            coordinates,
            squared_norm,
        })
    }

    /// Score every coordinate with the unchanged exact f64 arithmetic contract.
    pub(crate) fn score(&self, candidate: &[f32]) -> Option<f64> {
        if candidate.len() != 256 || candidate.iter().any(|x| !x.is_finite()) {
            return None;
        }
        let mut dot = 0.0;
        let mut candidate_norm = 0.0;
        for (query, candidate) in self.coordinates.iter().zip(candidate) {
            let a = *query as f64;
            let b = *candidate as f64;
            dot += a * b;
            candidate_norm += b * b;
        }
        let denominator = (self.squared_norm * candidate_norm).sqrt();
        if denominator <= 0.0 || !denominator.is_finite() {
            return None;
        }
        Some((dot / denominator).clamp(-1.0, 1.0))
    }
}
