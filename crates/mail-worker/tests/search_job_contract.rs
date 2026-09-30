//! SQLite fixture checks for the durable search-job schema. / 持久检索任务结构的 SQLite 夹具验证。
//!
//! These run in GitHub-hosted CI against the checked-in migration. The queries
//! model the Worker's versioned D1 predicates; they are **not** a deployed D1
//! or HTTP test and cannot prove Cloudflare execution/consistency.
//! 本测试在 GitHub CI 使用仓库迁移；谓词模拟 Worker 的版本化 D1 操作，**不**代表真实部署验证。

use rusqlite::{params, Connection, OptionalExtension};

/// Load only the base mailbox schema and the actual search-job migration.
/// 载入基础邮箱结构及真实的检索任务迁移。
fn db() -> Connection {
    let db = Connection::open_in_memory().unwrap();
    db.execute_batch(include_str!("../migrations/0001_initial.sql"))
        .unwrap();
    db.execute_batch(include_str!("../migrations/0005_search_jobs.sql"))
        .unwrap();
    db
}

/// Insert synthetic job state without any mail body or account identifier.
/// 插入无邮件正文、无真实账户标识的合成任务状态。
fn job(db: &Connection, id: &str, owner: &str, state: &str, version: i64, now: i64) {
    db.execute(
        "INSERT INTO search_jobs(id,owner_iss,owner_sub,request_json,state_json,state,version,created_at,expires_at) VALUES(?1,'test-issuer',?2,'{}','{}',?3,?4,?5,?6)",
        params![id, owner, state, version, now, now + 86_400_000],
    )
    .unwrap();
}

/// Two pollers that saw the same version cannot both acquire an advancement lease.
/// 同时读到旧版本的两个轮询者不能都取得续扫租约。
#[test]
fn stale_parallel_claim_has_one_winner() {
    let db = db();
    job(&db, "job", "alice", "running", 0, 1_000);
    let claim = "UPDATE search_jobs SET state='advancing',version=version+1,lease_started_at=?1 WHERE id=?2 AND owner_iss='test-issuer' AND owner_sub=?3 AND state='running' AND version=?4";
    // Both pollers read version 0 before either write; SQLite serializes their CAS writes.
    // 两个轮询者先读到版本 0，SQLite 串行化后续 CAS 写入。
    let first = db
        .execute(claim, params![1_001_i64, "job", "alice", 0])
        .unwrap();
    let second = db
        .execute(claim, params![1_001_i64, "job", "alice", 0])
        .unwrap();
    assert_eq!((first, second), (1, 0));
    let state: (String, i64) = db
        .query_row(
            "SELECT state,version FROM search_jobs WHERE id='job'",
            [],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .unwrap();
    assert_eq!(state, ("advancing".into(), 1));
}

/// A fresh lease cannot be stolen, while an expired lease can be recovered once.
/// 未超时租约不可窃取，超时租约只能被接管一次。
#[test]
fn lease_recovery_respects_timeout_and_version() {
    let db = db();
    job(&db, "job", "alice", "advancing", 5, 1_000);
    db.execute(
        "UPDATE search_jobs SET lease_started_at=1000 WHERE id='job'",
        [],
    )
    .unwrap();
    let recover = "UPDATE search_jobs SET state='running',version=version+1,lease_started_at=NULL WHERE id=?1 AND owner_iss='test-issuer' AND owner_sub='alice' AND state='advancing' AND version=?2 AND lease_started_at<?3";
    assert_eq!(db.execute(recover, params!["job", 5, 999_i64]).unwrap(), 0);
    assert_eq!(
        db.execute(recover, params!["job", 5, 1_001_i64]).unwrap(),
        1
    );
    assert_eq!(
        db.execute(recover, params!["job", 5, 1_001_i64]).unwrap(),
        0
    );
    let state: (String, i64) = db
        .query_row(
            "SELECT state,version FROM search_jobs WHERE id='job'",
            [],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .unwrap();
    assert_eq!(state, ("running".into(), 6));
}

/// Job lookup and mutation must be scoped to the immutable owner tuple.
/// 任务读取和修改必须按不可变所有者二元组隔离。
#[test]
fn owner_isolation_applies_to_read_and_claim() {
    let db = db();
    job(&db, "job", "alice", "running", 0, 1_000);
    let invisible: Option<String> = db
        .query_row(
            "SELECT state FROM search_jobs WHERE id='job' AND owner_iss='test-issuer' AND owner_sub='bob'",
            [],
            |r| r.get(0),
        )
        .optional()
        .unwrap();
    assert_eq!(invisible, None);
    assert_eq!(
        db.execute(
            "UPDATE search_jobs SET state='advancing',version=version+1 WHERE id='job' AND owner_iss='test-issuer' AND owner_sub='bob' AND state='running' AND version=0",
            [],
        )
        .unwrap(),
        0
    );
}

/// The persisted 24-hour deadline has an exact inclusive expiry boundary.
/// 持久化的 24 小时截止时间具有明确的含端点过期边界。
#[test]
fn expiry_boundary_and_completed_replay_are_stable() {
    let db = db();
    job(&db, "job", "alice", "done", 3, 1_000);
    let expiry: i64 = db
        .query_row(
            "SELECT expires_at FROM search_jobs WHERE id='job'",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(expiry, 1_000 + 86_400_000);
    let expired_at = |clock: i64| -> bool {
        db.query_row(
            "SELECT 1 FROM search_jobs WHERE id='job' AND expires_at<=?1",
            [clock],
            |_| Ok(()),
        )
        .optional()
        .unwrap()
        .is_some()
    };
    assert!(!expired_at(expiry - 1));
    assert!(expired_at(expiry));

    let checkpoint =
        r#"{"generation":0,"high_water":1001,"marker":null,"hits":[{"id":"synthetic"}]}"#;
    db.execute(
        "UPDATE search_jobs SET state_json=?1 WHERE id='job'",
        [checkpoint],
    )
    .unwrap();
    let load = || -> String {
        db.query_row(
            "SELECT state_json FROM search_jobs WHERE id='job' AND owner_iss='test-issuer' AND owner_sub='alice' AND state='done' AND COALESCE((SELECT generation FROM search_generations WHERE owner_iss='test-issuer' AND owner_sub='alice'),0)=0",
            [],
            |r| r.get(0),
        )
        .unwrap()
    };
    assert_eq!(load(), checkpoint);
    assert_eq!(load(), checkpoint);
}

/// Stale jobs still consume the total quota until expiry; otherwise callers can fill D1 forever.
/// 陈旧任务在过期前仍计入总额度，防止调用者无限填充 D1。
#[test]
fn stale_jobs_count_toward_total_quota_until_expired() {
    let db = db();
    for index in 0..256 {
        job(&db, &format!("old-{index}"), "alice", "stale", 0, 1_000);
    }
    let guarded = "INSERT INTO search_jobs(id,owner_iss,owner_sub,request_json,state_json,state,created_at,expires_at) SELECT ?1,'test-issuer',?2,'{}','{}','running',?3,?4 WHERE (SELECT COUNT(*) FROM search_jobs WHERE owner_iss='test-issuer' AND owner_sub=?2 AND state IN ('preparing','running','advancing') AND expires_at>?3)<5 AND (SELECT COUNT(*) FROM search_jobs WHERE owner_iss='test-issuer' AND owner_sub=?2 AND state IN ('preparing','running','advancing','done','stale') AND expires_at>?3)<256";
    assert_eq!(
        db.execute(guarded, params!["new", "alice", 1_000_i64, 87_401_000_i64])
            .unwrap(),
        0
    );
    assert_eq!(
        db.execute(guarded, params!["other", "bob", 1_000_i64, 87_401_000_i64])
            .unwrap(),
        1
    );
    db.execute("UPDATE search_jobs SET expires_at=999 WHERE id='old-0'", [])
        .unwrap();
    assert_eq!(
        db.execute(guarded, params!["new", "alice", 1_000_i64, 87_401_000_i64])
            .unwrap(),
        1
    );
}

/// Semantic preparations consume active slots before the embedding provider is called.
/// 语义查询在调用向量供应商之前占用活跃槽，超时预备态可以清理。
#[test]
fn preparing_jobs_reserve_slots_and_timeout_cleanup() {
    let db = db();
    for index in 0..5 {
        job(
            &db,
            &format!("prepare-{index}"),
            "alice",
            "preparing",
            0,
            1_000,
        );
    }
    let guarded = "INSERT INTO search_jobs(id,owner_iss,owner_sub,request_json,state_json,state,created_at,expires_at) SELECT ?1,'test-issuer','alice','{}','{}','preparing',?2,?3 WHERE (SELECT COUNT(*) FROM search_jobs WHERE owner_iss='test-issuer' AND owner_sub='alice' AND state IN ('preparing','running','advancing') AND expires_at>?2)<5 AND (SELECT COUNT(*) FROM search_jobs WHERE owner_iss='test-issuer' AND owner_sub='alice' AND state IN ('preparing','running','advancing','done','stale') AND expires_at>?2)<256";
    assert_eq!(
        db.execute(guarded, params!["sixth", 1_000_i64, 86_401_000_i64])
            .unwrap(),
        0
    );
    let cleanup = "DELETE FROM search_jobs WHERE state='preparing' AND created_at<?1";
    assert_eq!(db.execute(cleanup, [1_000_i64]).unwrap(), 0);
    assert_eq!(db.execute(cleanup, [1_001_i64]).unwrap(), 5);
    assert_eq!(
        db.execute(guarded, params!["sixth", 1_001_i64, 86_401_001_i64])
            .unwrap(),
        1
    );
}

/// Cleanup removes query/vector data at 24 hours and tombstones after 48 hours.
/// 清理在 24 小时擦除查询和向量，48 小时后移除墓碑。
#[test]
fn expiry_scrubs_sensitive_state_then_removes_tombstone() {
    let db = db();
    job(&db, "job", "alice", "done", 3, 1_000);
    db.execute(
        "UPDATE search_jobs SET request_json=?1,state_json=?2 WHERE id='job'",
        params![
            r#"{"semantic":"synthetic_query"}"#,
            r#"{"query_vector":"synthetic_vector"}"#
        ],
    )
    .unwrap();
    let expiry = 1_000 + 86_400_000_i64;
    let scrub = "UPDATE search_jobs SET state='expired',request_json='{}',state_json='{}' WHERE expires_at<=?1 AND state!='expired'";
    assert_eq!(db.execute(scrub, [expiry - 1]).unwrap(), 0);
    assert_eq!(db.execute(scrub, [expiry]).unwrap(), 1);
    let scrubbed: (String, String, String) = db
        .query_row(
            "SELECT state,request_json,state_json FROM search_jobs WHERE id='job'",
            [],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
        )
        .unwrap();
    assert_eq!(scrubbed, ("expired".into(), "{}".into(), "{}".into()));

    let remove = "DELETE FROM search_jobs WHERE state='expired' AND expires_at<?1";
    // Worker binds `now - JOB_TTL_MS`, not `now`; these cutoffs correspond to
    // clock times exactly 48 hours and 48 hours + 1 ms after creation.
    // Worker 绑定 `now - JOB_TTL_MS`；这两个阈值对应创建后恰好 48 小时及再过 1 毫秒。
    assert_eq!(db.execute(remove, [expiry]).unwrap(), 0);
    assert_eq!(db.execute(remove, [expiry + 1]).unwrap(), 1);
}

/// Every mutation bumps the owner's generation, invalidating older search snapshots.
/// 每次邮件变更递增所有者代际，使旧检索快照失效。
#[test]
fn message_mutations_advance_only_owners_generation() {
    let db = db();
    db.execute("INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,state,created_at) VALUES('a@mail.moesegfault.dev','a','test-issuer','alice',0,'active',1)", []).unwrap();
    db.execute("INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,state,created_at) VALUES('b@mail.moesegfault.dev','b','test-issuer','bob',0,'active',1)", []).unwrap();
    db.execute("INSERT INTO messages(id,address,owner_iss,owner_sub,direction,sender,recipients_json,subject,body_text,metadata_json,received_at,is_read,has_html,has_text,attachment_count,r2_key,size_bytes) VALUES('m','a@mail.moesegfault.dev','test-issuer','alice','inbound','sender@example.org','[]','synthetic','','{}',1,0,0,1,0,'k',1)", []).unwrap();
    let generation = |owner: &str| -> Option<i64> {
        db.query_row(
            "SELECT generation FROM search_generations WHERE owner_iss='test-issuer' AND owner_sub=?1",
            [owner],
            |r| r.get(0),
        )
        .optional()
        .unwrap()
    };
    assert_eq!(generation("alice"), Some(1));
    assert_eq!(generation("bob"), None);
    db.execute("UPDATE messages SET is_read=1 WHERE id='m'", [])
        .unwrap();
    assert_eq!(generation("alice"), Some(2));
    db.execute("DELETE FROM messages WHERE id='m'", []).unwrap();
    assert_eq!(generation("alice"), Some(3));
    assert_eq!(generation("bob"), None);
}

/// An origin is readable only through its immutable owner tuple and before its deadline.
/// The handler separately validates its typed state and cursor MAC after this lookup.
#[test]
fn semantic_origin_lookup_is_owner_scoped_and_expires_at_boundary() {
    let db = db();
    job(&db, "origin", "alice", "done", 1, 1_000);
    db.execute(
        "UPDATE search_jobs SET state_json=?1 WHERE id='origin'",
        [r#"{"is_origin":true,"origin_job_id":"origin","query_vector":[1,0],"cursor_key":"private"}"#],
    )
    .unwrap();
    let lookup = |issuer: &str, owner: &str, now: i64| -> Option<String> {
        db.query_row(
            "SELECT state_json FROM search_jobs WHERE id='origin' AND owner_iss=?1 AND owner_sub=?2 AND state='done' AND expires_at>?3",
            params![issuer, owner, now],
            |row| row.get(0),
        )
        .optional()
        .unwrap()
    };
    assert!(lookup("test-issuer", "alice", 86_400_999).is_some());
    assert_eq!(lookup("test-issuer", "alice", 86_401_000), None);
    assert_eq!(lookup("test-issuer", "bob", 86_400_999), None);
    assert_eq!(lookup("other-issuer", "alice", 86_400_999), None);
    assert_eq!(lookup("test-issuer", "missing", 86_400_999), None);
    db.execute("UPDATE search_jobs SET state='expired',request_json='{}',state_json='{}' WHERE id='origin'", []).unwrap();
    assert_eq!(lookup("test-issuer", "alice", 86_400_999), None);
}

/// Publication must atomically retain the generation, lease, and live owner-scoped origin.
/// This is the Worker's conditional v5 completion SQL, with synthetic JSON and timestamps.
#[test]
fn semantic_continuation_publication_requires_live_origin_and_current_generation() {
    let db = db();
    let completion = "UPDATE search_jobs SET state='done',state_json=?1,version=version+1,lease_started_at=NULL WHERE id=?2 AND owner_iss=?3 AND owner_sub=?4 AND state='advancing' AND version=?5 AND COALESCE((SELECT generation FROM search_generations WHERE owner_iss=?3 AND owner_sub=?4),0)=?6 AND search_jobs.expires_at>?7 AND EXISTS (SELECT 1 FROM search_jobs origin WHERE origin.id=?8 AND origin.owner_iss=?3 AND origin.owner_sub=?4 AND origin.state='done' AND origin.expires_at>?7)";
    let publish = |page: &str, owner: &str, origin: &str, now: i64| {
        db.execute(
            completion,
            params![
                r#"{"query_vector":null,"origin_job_id":"origin"}"#,
                page,
                "test-issuer",
                owner,
                0,
                0,
                now,
                origin
            ],
        )
        .unwrap()
    };

    job(&db, "origin", "alice", "done", 1, 1_000);
    job(&db, "page", "alice", "advancing", 0, 1_000);
    job(&db, "foreign", "bob", "done", 1, 1_000);
    assert_eq!(publish("page", "alice", "foreign", 1_001), 0);
    assert_eq!(publish("page", "bob", "origin", 1_001), 0);
    assert_eq!(publish("page", "alice", "origin", 86_401_000), 0);
    db.execute(
        "UPDATE search_jobs SET state='expired',state_json='{}' WHERE id='origin'",
        [],
    )
    .unwrap();
    assert_eq!(publish("page", "alice", "origin", 1_001), 0);
    db.execute("UPDATE search_jobs SET state='done' WHERE id='origin'", [])
        .unwrap();
    db.execute("INSERT INTO search_generations(owner_iss,owner_sub,generation) VALUES('test-issuer','alice',1)", []).unwrap();
    assert_eq!(publish("page", "alice", "origin", 1_001), 0);
    db.execute("UPDATE search_generations SET generation=0 WHERE owner_iss='test-issuer' AND owner_sub='alice'", []).unwrap();
    assert_eq!(publish("page", "alice", "origin", 1_001), 1);
    assert_eq!(publish("page", "alice", "origin", 1_001), 0);
    let published: (String, i64, Option<i64>) = db
        .query_row(
            "SELECT state,version,lease_started_at FROM search_jobs WHERE id='page'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .unwrap();
    assert_eq!(published, ("done".into(), 1, None));
}

/// A first-page origin cannot publish a cursor once its own TTL has elapsed.
/// The deadline is checked by the completion CAS, not just when the lease starts.
#[test]
fn first_page_origin_completion_rechecks_its_own_expiry() {
    let db = db();
    let completion = "UPDATE search_jobs SET state='done',state_json=?1,version=version+1,lease_started_at=NULL WHERE id=?2 AND owner_iss=?3 AND owner_sub=?4 AND state='advancing' AND version=?5 AND COALESCE((SELECT generation FROM search_generations WHERE owner_iss=?3 AND owner_sub=?4),0)=?6 AND search_jobs.expires_at>?7";
    job(&db, "origin", "alice", "advancing", 4, 1_000);
    job(&db, "fresh-origin", "alice", "advancing", 4, 1_000);
    db.execute(
        "UPDATE search_jobs SET lease_started_at=1001 WHERE id='origin'",
        [],
    )
    .unwrap();
    let publish = |id: &str, owner: &str, version: i64, generation: i64, now: i64| {
        db.execute(
            completion,
            params![
                r#"{"is_origin":true,"query_vector":[1,0],"cursor_key":"private"}"#,
                id,
                "test-issuer",
                owner,
                version,
                generation,
                now,
            ],
        )
        .unwrap()
    };
    let expiry = 86_401_000_i64;
    assert_eq!(publish("origin", "bob", 4, 0, expiry - 1), 0);
    assert_eq!(publish("origin", "alice", 3, 0, expiry - 1), 0);
    assert_eq!(publish("origin", "alice", 4, 1, expiry - 1), 0);
    assert_eq!(publish("origin", "alice", 4, 0, expiry), 0);
    let still_claimed: (String, i64, Option<i64>) = db
        .query_row(
            "SELECT state,version,lease_started_at FROM search_jobs WHERE id='origin'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .unwrap();
    assert_eq!(still_claimed, ("advancing".into(), 4, Some(1_001)));
    assert_eq!(publish("fresh-origin", "alice", 4, 0, expiry - 1), 1);
    assert_eq!(publish("fresh-origin", "alice", 4, 0, expiry - 1), 0);
    let done: (String, i64, Option<i64>) = db
        .query_row(
            "SELECT state,version,lease_started_at FROM search_jobs WHERE id='fresh-origin'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .unwrap();
    assert_eq!(done, ("done".into(), 5, None));
}

/// A stale completed origin loses its private vector and MAC only under its owner/version CAS.
#[test]
fn completed_origin_scrub_is_owner_and_version_scoped() {
    let db = db();
    job(&db, "origin", "alice", "done", 7, 1_000);
    let request = r#"{"semantic":"private query"}"#;
    let state = r#"{"query_vector":[1,0],"cursor_key":"private"}"#;
    db.execute(
        "UPDATE search_jobs SET request_json=?1,state_json=?2 WHERE id='origin'",
        params![request, state],
    )
    .unwrap();
    let scrub = |issuer: &str, owner: &str, version: i64| {
        db.execute(
            "UPDATE search_jobs SET state='stale',request_json='{}',state_json='{}',version=version+1 WHERE id=?1 AND state='done' AND version=?2 AND owner_iss=?3 AND owner_sub=?4",
            params!["origin", version, issuer, owner],
        )
        .unwrap()
    };
    assert_eq!(scrub("test-issuer", "bob", 7), 0);
    assert_eq!(scrub("other-issuer", "alice", 7), 0);
    assert_eq!(scrub("test-issuer", "alice", 6), 0);
    let saved: (String, String, String, i64) = db
        .query_row(
            "SELECT state,request_json,state_json,version FROM search_jobs WHERE id='origin'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .unwrap();
    assert_eq!(saved, ("done".into(), request.into(), state.into(), 7));
    // The handler calls this CAS after detecting that the account generation changed.
    db.execute(
        "INSERT INTO search_generations(owner_iss,owner_sub,generation) VALUES('test-issuer','alice',1)",
        [],
    )
    .unwrap();
    assert_eq!(scrub("test-issuer", "alice", 7), 1);
    assert_eq!(scrub("test-issuer", "alice", 7), 0);
    let cleared: (String, String, String, i64) = db
        .query_row(
            "SELECT state,request_json,state_json,version FROM search_jobs WHERE id='origin'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .unwrap();
    assert_eq!(cleared, ("stale".into(), "{}".into(), "{}".into(), 8));
}

/// A terminal cursor failure clears the leased page copy only for its owner and lease version.
#[test]
fn terminal_page_release_scrubs_copy_with_owner_and_version_cas() {
    let db = db();
    job(&db, "page", "alice", "advancing", 9, 1_000);
    let request = r#"{"semantic":"private query","cursor":"opaque"}"#;
    let state = r#"{"origin_job_id":"origin","query_vector":[1,0]}"#;
    db.execute(
        "UPDATE search_jobs SET request_json=?1,state_json=?2,lease_started_at=1001 WHERE id='page'",
        params![request, state],
    )
    .unwrap();
    let release = |issuer: &str, owner: &str, version: i64| {
        db.execute(
            "UPDATE search_jobs SET state='stale',request_json='{}',state_json='{}',version=version+1,lease_started_at=NULL WHERE id=?1 AND state='advancing' AND version=?2 AND owner_iss=?3 AND owner_sub=?4",
            params!["page", version, issuer, owner],
        )
        .unwrap()
    };
    assert_eq!(release("test-issuer", "bob", 9), 0);
    assert_eq!(release("other-issuer", "alice", 9), 0);
    assert_eq!(release("test-issuer", "alice", 8), 0);
    let retained: (String, String, String, i64, Option<i64>) = db
        .query_row(
            "SELECT state,request_json,state_json,version,lease_started_at FROM search_jobs WHERE id='page'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?, row.get(4)?)),
        )
        .unwrap();
    assert_eq!(
        retained,
        (
            "advancing".into(),
            request.into(),
            state.into(),
            9,
            Some(1_001)
        )
    );
    assert_eq!(release("test-issuer", "alice", 9), 1);
    assert_eq!(release("test-issuer", "alice", 9), 0);
    let cleared: (String, String, String, i64, Option<i64>) = db
        .query_row(
            "SELECT state,request_json,state_json,version,lease_started_at FROM search_jobs WHERE id='page'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?, row.get(4)?)),
        )
        .unwrap();
    assert_eq!(
        cleared,
        ("stale".into(), "{}".into(), "{}".into(), 10, None)
    );
}

/// Only a first page with another page retains the query vector and private cursor key.
/// Later page jobs clear their temporary vector; expiry scrubs even the retained origin.
#[test]
fn completed_origin_retention_and_page_copy_scrub_follow_cursor_lifecycle() {
    let db = db();
    for id in ["multi-origin", "single-origin", "page-copy"] {
        job(&db, id, "alice", "advancing", 0, 1_000);
    }
    let completed = |id: &str, is_origin: bool, has_more: bool| {
        let retain_origin = is_origin && has_more;
        let state = serde_json::json!({
            "is_origin": is_origin,
            "query_vector": retain_origin.then_some(vec![1.0_f32, 0.0]),
            "cursor_key": retain_origin.then_some("private"),
        });
        db.execute(
            "UPDATE search_jobs SET state='done',state_json=?1,version=version+1 WHERE id=?2 AND state='advancing' AND version=0",
            params![state.to_string(), id],
        ).unwrap();
        if !retain_origin && id != "page-copy" {
            // The fast first-page POST never exposed its transient job ID.
            db.execute("DELETE FROM search_jobs WHERE id=?1", [id])
                .unwrap();
        }
    };
    completed("multi-origin", true, true);
    completed("single-origin", true, false);
    completed("page-copy", false, true);
    let read = |id: &str| -> Option<serde_json::Value> {
        db.query_row(
            "SELECT state_json FROM search_jobs WHERE id=?1",
            [id],
            |r| r.get::<_, String>(0),
        )
        .optional()
        .unwrap()
        .map(|json| serde_json::from_str(&json).unwrap())
    };
    assert_eq!(read("single-origin"), None);
    assert_eq!(
        read("multi-origin").unwrap()["query_vector"],
        serde_json::json!([1.0, 0.0])
    );
    let copy = read("page-copy").unwrap();
    assert!(copy["query_vector"].is_null());
    assert!(copy["cursor_key"].is_null());
    assert_eq!(db.execute(
        "UPDATE search_jobs SET state='expired',request_json='{}',state_json='{}' WHERE expires_at<=?1 AND state!='expired'",
        [86_401_000_i64],
    ).unwrap(), 2);
    assert_eq!(read("multi-origin"), Some(serde_json::json!({})));
    assert_eq!(read("page-copy"), Some(serde_json::json!({})));
}
