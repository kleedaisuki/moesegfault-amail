//! Small native timing helper for opt-in hosted release tests, not CI gates.

use std::time::Instant;

/// Report repeat durations, median, nearest-rank p95, and median absolute deviation.
/// Each iteration includes its real production work; fixture setup is untimed.
pub(crate) fn measure(name: &str, iterations: usize, mut work: impl FnMut()) {
    for _ in 0..3 {
        work();
    }
    let mut samples = Vec::with_capacity(15);
    for _ in 0..15 {
        let start = Instant::now();
        for _ in 0..iterations {
            work();
        }
        samples.push(start.elapsed().as_nanos() as f64 / iterations as f64);
    }
    let mut ordered = samples.clone();
    ordered.sort_by(f64::total_cmp);
    let median = ordered[7];
    let mut deviations: Vec<_> = samples.iter().map(|v| (v - median).abs()).collect();
    deviations.sort_by(f64::total_cmp);
    println!(
        "PERF {}",
        serde_json::json!({
            "case": name, "iterations": iterations, "samples_ns": samples,
            "median_ns": median, "p95_ns": ordered[14], "mad_ns": deviations[7],
            "target": std::env::consts::ARCH, "profile": "release", "scope": "native_cpu"
        })
    );
}
