//! Opt-in, bounded native microbenchmarks for synchronous Worker CPU paths.
//! These are not D1, R2, network, Wasm, or end-to-end latency measurements.

use super::*;
use std::{hint::black_box, io::Write, time::Instant};

/// Emit raw repeat durations and robust summaries without a noisy latency gate.
fn measure(name: &str, iterations: usize, mut work: impl FnMut()) {
    for _ in 0..3 {
        work();
    }
    let mut samples = Vec::with_capacity(15);
    for _ in 0..15 {
        let started = Instant::now();
        for _ in 0..iterations {
            work();
        }
        samples.push(started.elapsed().as_nanos() as f64 / iterations as f64);
    }
    let mut ordered = samples.clone();
    ordered.sort_by(f64::total_cmp);
    let median = ordered[7];
    let mut deviations: Vec<_> = ordered.iter().map(|v| (v - median).abs()).collect();
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

/// Build an owned synthetic archive before timing, including a long-tail asset.
fn fixture(asset_size: usize) -> Vec<u8> {
    let mut zip = zip::ZipWriter::new(std::io::Cursor::new(Vec::new()));
    let options = zip::write::SimpleFileOptions::default()
        .compression_method(zip::CompressionMethod::Deflated);
    zip.start_file("manifest.toml", options).unwrap();
    write!(zip, "version=1\nfrom='a@mail.example.test'\nto=['b@example.test']\nsubject='Synthetic benchmark'\n[[assets]]\npath='assets/data.bin'\ncontent_type='application/octet-stream'\ndisposition='attachment'\nfilename='data.bin'\n").unwrap();
    zip.start_file("body.txt", options).unwrap();
    zip.write_all(b"Synthetic fixture; no real mailbox data.")
        .unwrap();
    zip.start_file("assets/data.bin", options).unwrap();
    // Bounded high-compressibility input isolates inflate/allocation constants.
    zip.write_all(&vec![b'x'; asset_size]).unwrap();
    zip.finish().unwrap().into_inner()
}

/// Frozen pre-optimization reference, preserving the exact original sum order.
fn cosine_reference(left: &[f32], right: &[f32]) -> Option<f64> {
    if left.len() != 256 || right.len() != 256 || left.iter().chain(right).any(|x| !x.is_finite()) {
        return None;
    }
    let (mut dot, mut left_norm, mut right_norm) = (0.0f64, 0.0f64, 0.0f64);
    for (a, b) in left.iter().zip(right) {
        let (a, b) = (*a as f64, *b as f64);
        dot += a * b;
        left_norm += a * a;
        right_norm += b * b;
    }
    let denominator = (left_norm * right_norm).sqrt();
    if denominator <= 0.0 || !denominator.is_finite() {
        return None;
    }
    Some((dot / denominator).clamp(-1.0, 1.0))
}

/// Cached query validation must preserve score bits and reject invalid shapes.
#[test]
fn prepared_cosine_is_bit_equivalent() {
    for q in 0..8 {
        let query: Vec<_> = (0..256)
            .map(|i| ((i * 11 + q * 19) % 251) as f32 / 251.0 - 0.5)
            .collect();
        let prepared = exact_cosine::QueryCosine::new(&query).unwrap();
        for row in 0..64 {
            let mut candidate: Vec<_> = (0..256)
                .map(|i| ((i * 13 + row * 7) % 251) as f32 / 251.0 - 0.5)
                .collect();
            for coordinate in [
                1.0,
                0.0,
                f32::MIN_POSITIVE,
                f32::MAX,
                f32::NAN,
                f32::INFINITY,
            ] {
                candidate[17] = coordinate;
                assert_eq!(
                    prepared.score(&candidate).map(f64::to_bits),
                    cosine_reference(&query, &candidate).map(f64::to_bits)
                );
            }
        }
        assert_eq!(prepared.score(&query[..255]), None);
        assert_eq!(prepared.score(&vec![0.0; 256]), None);
    }
    for invalid in [vec![0.0; 256], vec![f32::NAN; 256], vec![1.0; 255]] {
        assert!(exact_cosine::QueryCosine::new(&invalid).is_none());
    }
}

/// Repeated marking must preserve active cursors, while real changes stale them.
#[test]
fn idempotent_mark_preserves_generation_and_ownership() {
    let db = rusqlite::Connection::open_in_memory().unwrap();
    db.execute_batch(include_str!("../migrations/0001_initial.sql"))
        .unwrap();
    db.execute_batch(include_str!("../migrations/0005_search_jobs.sql"))
        .unwrap();
    db.execute("INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,state,created_at) VALUES('a@mail.example.test','a','i','s',0,'active',0)", []).unwrap();
    let metadata = r#"{"attachments":[{"filename":"synthetic.txt"}],"reply_to":"b@example.test"}"#;
    let embedding = serde_json::to_string(&vec![0.25f32; 256]).unwrap();
    db.execute("INSERT INTO messages(id,address,owner_iss,owner_sub,direction,sender,recipients_json,subject,body_text,metadata_json,received_at,has_html,has_text,attachment_count,r2_key,size_bytes,embedding_json) VALUES('m','a@mail.example.test','i','s','inbound','b@example.test','[]','Synthetic',?1,?2,0,1,1,1,'synthetic',1,?3)", rusqlite::params!["x".repeat(2_200_000), metadata, embedding]).unwrap();
    // Real detail SQL preserves body flags and metadata but not search payloads.
    let detail: (String, Option<String>, i64, i64, String, String) = db
        .query_row(
            MESSAGE_DETAIL_SQL,
            rusqlite::params!["m", "i", "s"],
            |row| {
                Ok((
                    row.get("body_text")?,
                    row.get("embedding_json")?,
                    row.get("has_html")?,
                    row.get("has_text")?,
                    row.get("metadata_json")?,
                    row.get("r2_key")?,
                ))
            },
        )
        .unwrap();
    assert_eq!(
        detail,
        (
            String::new(),
            None,
            1,
            1,
            metadata.to_owned(),
            "synthetic".into()
        )
    );
    let generation = || {
        db.query_row(
            "SELECT generation FROM search_generations WHERE owner_iss='i' AND owner_sub='s'",
            [],
            |row| row.get::<_, i64>(0),
        )
        .unwrap()
    };
    assert_eq!(generation(), 1);
    assert_eq!(
        db.execute(MARK_MESSAGE_SQL, rusqlite::params![0, "m", "i", "s"])
            .unwrap(),
        0
    );
    assert_eq!(generation(), 1);
    assert_eq!(
        db.execute(MARK_MESSAGE_SQL, rusqlite::params![1, "m", "i", "s"])
            .unwrap(),
        1
    );
    assert_eq!(generation(), 2);
    assert_eq!(
        db.execute(MARK_MESSAGE_SQL, rusqlite::params![1, "m", "i", "s"])
            .unwrap(),
        0
    );
    assert_eq!(generation(), 2);
    assert_eq!(
        db.execute(MARK_MESSAGE_SQL, rusqlite::params![0, "m", "i", "foreign"])
            .unwrap(),
        0
    );
    assert_eq!(generation(), 2);
    assert_eq!(
        db.execute(MARK_MESSAGE_SQL, rusqlite::params![0, "m", "i", "s"])
            .unwrap(),
        1
    );
    assert_eq!(generation(), 3);
}

/// Exact ranking, filter reuse, ZIP expansion and the removed archive copy.
/// Run only with `cargo test -p amail-worker --release performance_microbench
/// -- --ignored --nocapture`; never treat native timings as Worker CPU limits.
#[test]
#[ignore = "opt-in hosted release performance measurement"]
fn performance_microbench() {
    assert!(!cfg!(debug_assertions), "microbench requires --release");
    let query: Vec<f32> = (0..256).map(|i| (i as f32 - 80.0) / 256.0).collect();
    let vectors: Vec<Vec<f32>> = (0..512)
        .map(|row| {
            (0..256)
                .map(|i| ((i * 13 + row * 7) % 251) as f32 / 251.0)
                .collect()
        })
        .collect();
    measure("search_cosine_512x256_baseline", 32, || {
        for vector in &vectors {
            black_box(cosine_reference(black_box(&query), black_box(vector)).unwrap());
        }
    });
    measure("search_cosine_512x256_prepared", 32, || {
        let prepared = exact_cosine::QueryCosine::new(black_box(&query)).unwrap();
        for vector in &vectors {
            black_box(prepared.score(black_box(vector)).unwrap());
        }
    });
    for keep in [21, 101] {
        let hits: Vec<_> = (0..2048)
            .map(|i| {
                (
                    ((i * 37) % 2047) as f64 / 2048.0,
                    (i % 5) as i64,
                    format!("{i:08}"),
                )
            })
            .collect();
        measure(&format!("search_topk_2048_keep_{keep}"), 8, || {
            let mut selected = Vec::with_capacity(keep);
            for candidate in &hits {
                retain_semantic(&mut selected, candidate.clone(), keep, |h| (h.0, h.1, &h.2));
            }
            black_box(selected);
        });
    }
    let text = "Unicode mail: 你好, release notes, attachments and follow-up. ".repeat(512);
    for (label, pattern, regex) in [
        ("literal", "release notes", false),
        ("regex", "release.*attachments", true),
        ("miss", "not present", false),
    ] {
        let predicate = TextPredicate::new(pattern, regex, false).ok().unwrap();
        measure(&format!("search_body_{label}_32k"), 128, || {
            black_box(predicate.matches(black_box(&text)));
        });
    }
    for size in [4096, 2 * 1024 * 1024] {
        let archive = fixture(size);
        let draft = parse_draft(&archive).unwrap();
        assert_eq!(draft.assets[0].1.len(), size);
        measure(&format!("archive_parse_asset_{size}"), 8, || {
            black_box(parse_draft(black_box(&archive)).unwrap());
        });
        // Reports the eliminated operation's cost, not a fabricated R2 speedup.
        let expanded = vec![b'x'; size];
        measure(&format!("removed_r2_archive_copy_{size}"), 64, || {
            black_box(black_box(expanded.as_slice()).to_vec());
        });
    }
}
