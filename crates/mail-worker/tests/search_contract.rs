//! Independent search ordering contracts. / 独立的检索排序契约。
//!
//! These tests run on the GitHub-hosted native Worker test job. They exercise
//! the pure helpers used by the deployed search path, not Cloudflare D1 itself.
//! 这些测试在 GitHub 托管的原生 Worker 测试任务上运行，验证实际搜索路径使用的纯函数；不冒充 D1 集成测试。

use amail_worker::{retain_semantic, search_budget_exceeded, search_keyset_before, semantic_rank};
use std::cmp::Ordering;

/// Small synthetic hit with a precisely specified expected order. / 具有精确预期顺序的小型合成命中。
#[derive(Clone, Debug)]
struct Hit {
    id: &'static str,
    time: i64,
    score: f64,
}

/// Extract the same three-field rank key the Worker uses. / 提取 Worker 使用的三字段排序键。
fn rank(hit: &Hit) -> (f64, i64, &str) {
    (hit.score, hit.time, hit.id)
}

/// A tie on score and time must still have a strict, stable ID order. / 同分同时间仍须按 ID 给出稳定严格顺序。
#[test]
fn semantic_rank_resolves_near_ties_and_ids() {
    assert_eq!(
        semantic_rank((0.9000000000000001, 1, "a"), (0.9, 99, "z")),
        Ordering::Less
    );
    assert_eq!(
        semantic_rank((0.9, 20, "a"), (0.9, 19, "z")),
        Ordering::Less
    );
    assert_eq!(
        semantic_rank((0.9, 20, "z"), (0.9, 20, "a")),
        Ordering::Less
    );
    assert_eq!(
        semantic_rank((0.9, 20, "a"), (0.9, 20, "a")),
        Ordering::Equal
    );
}

/// Keyset pagination must not duplicate or skip equal-timestamp rows. / 键集分页不得重复或漏掉同时间记录。
#[test]
fn time_id_keyset_pages_cover_every_row_once() {
    let rows = [(9, "z"), (9, "m"), (9, "a"), (8, "q"), (8, "a"), (7, "z")];
    let mut seen = Vec::new();
    let mut marker = None;
    loop {
        let page: Vec<_> = rows
            .iter()
            .copied()
            .filter(|row| marker.is_none_or(|m| search_keyset_before(*row, m)))
            .take(2)
            .collect();
        if page.is_empty() {
            break;
        }
        marker = page.last().copied();
        seen.extend(page);
    }
    assert_eq!(seen, rows);
    assert!(!search_keyset_before((9, "m"), (9, "m")));
    assert!(!search_keyset_before((9, "z"), (9, "m")));
}

/// The best late-arriving hit must displace an earlier top-K item; later pages remain exact.
/// 晚到的最优命中必须替换此前 top-K 条目，后续页也须保持精确。
#[test]
fn semantic_topk_and_cursor_have_no_duplicate_or_gap() {
    let arrival = [
        Hit {
            id: "c",
            time: 5,
            score: 0.80,
        },
        Hit {
            id: "a",
            time: 5,
            score: 0.90,
        },
        Hit {
            id: "e",
            time: 2,
            score: 0.70,
        },
        Hit {
            id: "f",
            time: 1,
            score: 0.60,
        },
        Hit {
            id: "d",
            time: 4,
            score: 0.80,
        },
        Hit {
            id: "b",
            time: 6,
            score: 0.90,
        },
        Hit {
            id: "late",
            time: 0,
            score: 0.95,
        },
    ];
    let mut observed = Vec::new();
    let mut marker: Option<(f64, i64, &'static str)> = None;
    loop {
        let mut selected = Vec::new();
        for hit in &arrival {
            if marker.is_some_and(|m| semantic_rank(rank(hit), m) != Ordering::Greater) {
                continue;
            }
            retain_semantic(&mut selected, hit.clone(), 3, rank);
        }
        selected.sort_by(|a, b| semantic_rank(rank(a), rank(b)));
        let page: Vec<_> = selected.into_iter().take(2).collect();
        if page.is_empty() {
            break;
        }
        marker = page.last().map(|hit| (hit.score, hit.time, hit.id));
        observed.extend(page.into_iter().map(|hit| hit.id));
    }
    assert_eq!(observed, ["late", "b", "a", "c", "d", "e", "f"]);
}

/// A selective old match remains reachable past the former 2,000-row account cap.
/// 选择性条件的旧记录即使排在原 2000 条账号上限之后仍可到达。
#[test]
fn keyset_reaches_selective_older_match() {
    let rows: Vec<_> = (0..2_501)
        .rev()
        .map(|time| (time, format!("id-{time:04}")))
        .collect();
    let mut marker: Option<(i64, String)> = None;
    let mut matched = Vec::new();
    let mut pages = 0;
    loop {
        let page: Vec<_> = rows
            .iter()
            .filter(|(time, id)| {
                marker.as_ref().is_none_or(|(last_time, last_id)| {
                    search_keyset_before((*time, id.as_str()), (*last_time, last_id.as_str()))
                })
            })
            .take(200)
            .collect();
        if page.is_empty() {
            break;
        }
        pages += 1;
        matched.extend(
            page.iter()
                .filter(|(time, _)| *time == 0)
                .map(|(_, id)| id.clone()),
        );
        marker = page.last().map(|(time, id)| (*time, id.clone()));
    }
    assert_eq!(pages, 13);
    assert_eq!(matched, ["id-0000"]);
}

/// Budget boundaries must be explicit, never silently return partial results.
/// 预算边界必须明确，不能悄然返回不完整结果。
#[test]
fn search_budget_has_exact_boundaries() {
    const TRANSFER: usize = 32 * 1024 * 1024;
    const BODY: usize = 64 * 1024 * 1024;
    assert!(!search_budget_exceeded(399, TRANSFER, BODY));
    assert!(search_budget_exceeded(400, 0, 0));
    assert!(search_budget_exceeded(0, TRANSFER + 1, 0));
    assert!(search_budget_exceeded(0, 0, BODY + 1));
}
