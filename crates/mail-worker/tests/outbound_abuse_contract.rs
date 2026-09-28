//! Durable abuse-control SQL contracts. / 持久化滥用控制 SQL 契约。

use rusqlite::{params, Connection};

/// Construct the same migration sequence on native SQLite without touching remote D1.
/// 在原生 SQLite 上执行相同迁移序列，不触碰远程 D1。
fn database() -> Connection {
    let db = Connection::open_in_memory().unwrap();
    db.execute_batch(include_str!("../migrations/0001_initial.sql"))
        .unwrap();
    db.execute_batch(include_str!("../migrations/0002_reservation_lease.sql"))
        .unwrap();
    db.execute_batch(include_str!("../migrations/0006_outbound_abuse.sql"))
        .unwrap();
    db
}

/// Insert a normalized, attributed provider event; duplicate IDs are rejected by SQLite.
/// 插入已归因且已标准化的提供商事件；SQLite 拒绝重复 ID。
fn event(db: &Connection, id: &str, kind: &str, at: i64) -> rusqlite::Result<usize> {
    db.execute(
        "INSERT INTO provider_events(event_id,provider_id,local_message_id,owner_iss,owner_sub,recipient,kind,occurred_at,received_at) VALUES (?1,'provider-1','local-1','issuer','owner','user@example.net',?2,?3,?3)",
        params![id, kind, at],
    )
}

/// Public sending is held by default, not inferred from a provider acceptance test.
/// 公共发送默认停用，不从提供商接受提交的测试推断为可上线。
#[test]
fn global_launch_hold_is_explicit() {
    let db = database();
    let state: String = db
        .query_row(
            "SELECT state FROM send_policy WHERE scope='global' AND owner_iss='*' AND owner_sub='*'",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(state, "held");
    let audit: i64 = db
        .query_row(
            "SELECT count(*) FROM send_policy_audit WHERE scope='global' AND new_state='held'",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(audit, 1);
}

/// A held owner cannot create any pending send rows; a 15-minute canary grant
/// permits exactly one new idempotency key and rejects another key atomically.
/// 被停用账户不能创建待处理发件；15 分钟金丝雀授权原子地只准一个新幂等键。
#[test]
fn held_admission_is_bounded_by_one_canary_key() {
    let db = database();
    let trigger_count: i64 = db.query_row("SELECT count(*) FROM sqlite_master WHERE type='trigger' AND name='send_request_policy_guard' AND tbl_name='send_requests'", [], |r| r.get(0)).unwrap();
    assert_eq!(trigger_count, 1);
    let insert = "INSERT INTO send_requests(owner_iss,owner_sub,idem_key,payload_hash,message_id,state,created_at) VALUES('issuer','owner',?1,'hash','local','preparing',1)";
    assert!(db.execute(insert, ["first"]).is_err());
    let count: i64 = db
        .query_row("SELECT count(*) FROM send_requests", [], |r| r.get(0))
        .unwrap();
    assert_eq!(count, 0);
    db.execute("UPDATE send_release_gates SET canary_owner_iss='issuer',canary_owner_sub='owner',canary_recipient_sha256='synthetic',canary_expires_at=unixepoch()+900,case_ref='CASE_1',actor='operator' WHERE id=1", []).unwrap();
    db.execute(insert, ["first"]).unwrap();
    assert!(db.execute(insert, ["second"]).is_err());
    let used: String = db
        .query_row(
            "SELECT canary_used_by FROM send_release_gates WHERE id=1",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(used, "first");
}

/// A never-submitted new key is removable after quota failure; existing
/// provider outcomes are not eligible for this cleanup predicate.
/// 额度失败后可清除从未提交的新键；已有提供商结果不满足该清理谓词。
#[test]
fn quota_denial_does_not_accumulate_new_keys() {
    let db = database();
    db.execute("UPDATE send_release_gates SET feedback_verified=1,abuse_contact_verified=1,delivery_canary_verified=1,preview_reviewed=1 WHERE id=1", []).unwrap();
    db.execute(
        "UPDATE send_policy SET state='allowed' WHERE scope='global'",
        [],
    )
    .unwrap();
    db.execute("INSERT INTO send_requests(owner_iss,owner_sub,idem_key,payload_hash,message_id,state,created_at) VALUES('issuer','owner','key','hash','local','preparing',1)", []).unwrap();
    db.execute(
        "UPDATE send_requests SET state='reserving' WHERE idem_key='key'",
        [],
    )
    .unwrap();
    db.execute(
        "UPDATE send_requests SET state='preparing' WHERE idem_key='key' AND state='reserving'",
        [],
    )
    .unwrap();
    db.execute(
        "DELETE FROM send_requests WHERE idem_key='key' AND state='preparing' AND quota_reserved=0",
        [],
    )
    .unwrap();
    let count: i64 = db
        .query_row("SELECT count(*) FROM send_requests", [], |r| r.get(0))
        .unwrap();
    assert_eq!(count, 0);
}

/// Six legitimate updates to the same recipient fit the provisional daily
/// bucket, while an eleventh recipient attempt is rejected atomically.
/// 同一收件人的 6 次常规更新可通过临时日额度，第 11 次则原子拒绝。
#[test]
fn same_recipient_allows_updates_but_caps_eleventh_attempt() {
    let db = database();
    let reserve = "INSERT INTO daily_usage(kind,owner_iss,owner_sub,day,used) VALUES('send_recipient:hash','issuer','owner',1234,1) ON CONFLICT(kind,owner_iss,owner_sub,day) DO UPDATE SET used=used+excluded.used WHERE used+excluded.used<=10";
    for _ in 0..6 {
        assert_eq!(db.execute(reserve, []).unwrap(), 1);
    }
    for _ in 6..10 {
        assert_eq!(db.execute(reserve, []).unwrap(), 1);
    }
    assert_eq!(db.execute(reserve, []).unwrap(), 0);
    let used: i64 = db
        .query_row(
            "SELECT used FROM daily_usage WHERE kind='send_recipient:hash'",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(used, 10);
}

/// Revoking an attested external dependency immediately returns the global
/// sender to held, and the mutation is recorded in the policy audit trail.
/// 撤销已核验的外部依赖时立即全局停用，并在策略审计中留下记录。
#[test]
fn revoked_release_gate_reholds_global_send() {
    let db = database();
    db.execute("UPDATE send_release_gates SET feedback_verified=1,abuse_contact_verified=1,delivery_canary_verified=1,preview_reviewed=1,actor='operator',case_ref='CASE_1' WHERE id=1", []).unwrap();
    db.execute("UPDATE send_policy SET state='allowed',actor='operator',reason_code='launch_verified',note_ref='CASE_1' WHERE scope='global'", []).unwrap();
    db.execute("UPDATE send_release_gates SET feedback_verified=0,actor='operator',case_ref='CASE_2' WHERE id=1", []).unwrap();
    let state: String = db
        .query_row(
            "SELECT state FROM send_policy WHERE scope='global'",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(state, "held");
    let reason: String = db
        .query_row(
            "SELECT reason_code FROM send_policy_audit ORDER BY id DESC LIMIT 1",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(reason, "release_gate_revoked");
}

/// Rebuilding the request CHECK preserves pre-migration idempotency records.
/// 重建请求 CHECK 时保留迁移前的幂等记录。
#[test]
fn migration_preserves_existing_requests_and_adds_rejection() {
    let db = Connection::open_in_memory().unwrap();
    db.execute_batch(include_str!("../migrations/0001_initial.sql"))
        .unwrap();
    db.execute_batch(include_str!("../migrations/0002_reservation_lease.sql"))
        .unwrap();
    db.execute("INSERT INTO send_requests(owner_iss,owner_sub,idem_key,payload_hash,message_id,state,created_at) VALUES('iss','sub','idem','hash','local','preparing',1)", [])
        .unwrap();
    db.execute_batch(include_str!("../migrations/0006_outbound_abuse.sql"))
        .unwrap();
    db.execute("UPDATE send_requests SET state='rejected',rejection_code='recipient_suppressed' WHERE idem_key='idem'", [])
        .unwrap();
    let row: (String, String) = db
        .query_row(
            "SELECT message_id,rejection_code FROM send_requests WHERE idem_key='idem'",
            [],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .unwrap();
    assert_eq!(row, ("local".into(), "recipient_suppressed".into()));
}

/// Redelivery and stale temporary failures cannot undo delivered or complaint state.
/// 重投与过期的临时故障不能撤销已送达或投诉状态。
#[test]
fn outcomes_are_idempotent_and_monotone() {
    let db = database();
    event(&db, "e1", "delivered", 20).unwrap();
    assert!(event(&db, "e1", "delivered", 20).is_err());
    event(&db, "e2", "deferred", 30).unwrap();
    let state: String = db
        .query_row(
            "SELECT kind FROM recipient_outcomes WHERE local_message_id='local-1'",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(state, "delivered");
    event(&db, "e3", "complained", 10).unwrap();
    event(&db, "e4", "delivered", 40).unwrap();
    let state: String = db
        .query_row(
            "SELECT kind FROM recipient_outcomes WHERE local_message_id='local-1'",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(state, "complained");
    let policy: String = db
        .query_row(
            "SELECT state FROM send_policy WHERE scope='account' AND owner_iss='issuer' AND owner_sub='owner'",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(policy, "held");
    let count: i64 = db
        .query_row("SELECT count(*) FROM recipient_blocks", [], |r| r.get(0))
        .unwrap();
    assert_eq!(count, 1);
}

/// A later unique complaint must reapply a hold even after explicit human unhold.
/// 人工解除停用后，新的独立投诉仍必须重新停用账户。
#[test]
fn new_complaint_reholds_account() {
    let db = database();
    event(&db, "e1", "complained", 10).unwrap();
    db.execute(
        "UPDATE send_policy SET state='allowed' WHERE scope='account'",
        [],
    )
    .unwrap();
    event(&db, "e2", "complained", 20).unwrap();
    let state: String = db
        .query_row(
            "SELECT state FROM send_policy WHERE scope='account'",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(state, "held");
}

/// Deleting a user-visible sent message must not erase the attribution needed
/// to process a later provider complaint and hold the responsible account.
/// 删除用户可见发件不可抹除处理迟到投诉及停用责任账户所需的归因信息。
#[test]
fn deleted_message_late_complaint_still_holds_owner() {
    let db = database();
    // Seed a historical send under an allowed policy; the admission trigger must
    // not be weakened merely to construct a late-feedback fixture.
    // 在已允许的策略下建立历史发件；不能为了延迟反馈夹具而削弱准入触发器。
    db.execute("UPDATE send_release_gates SET feedback_verified=1,abuse_contact_verified=1,delivery_canary_verified=1,preview_reviewed=1 WHERE id=1", []).unwrap();
    db.execute(
        "UPDATE send_policy SET state='allowed' WHERE scope='global'",
        [],
    )
    .unwrap();
    db.execute("INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,state,created_at) VALUES('a@mail.example.test','a','issuer','owner',0,'active',0)", []).unwrap();
    db.execute("INSERT INTO messages(id,address,owner_iss,owner_sub,direction,sender,recipients_json,subject,body_text,metadata_json,received_at,has_html,has_text,attachment_count,r2_key,size_bytes) VALUES('local-1','a@mail.example.test','issuer','owner','outbound','a@mail.example.test','[]','subject','','{}',1,0,1,0,'key',1)", []).unwrap();
    db.execute("INSERT INTO send_requests(owner_iss,owner_sub,idem_key,payload_hash,message_id,provider_id,request_id,state,created_at,sender,envelope_json) VALUES('issuer','owner','idem','hash','local-1','provider-1','opaque-request-1','sent',1,'a@mail.example.test','[\"user@example.net\"]')", []).unwrap();
    db.execute("DELETE FROM messages WHERE id='local-1'", [])
        .unwrap();
    let envelope: String = db
        .query_row(
            "SELECT envelope_json FROM send_requests WHERE provider_id='provider-1'",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(envelope, "[\"user@example.net\"]");
    let request_id: String = db
        .query_row(
            "SELECT request_id FROM send_requests WHERE provider_id='provider-1'",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(request_id, "opaque-request-1");
    event(&db, "late", "complained", 30).unwrap();
    let state: String = db
        .query_row(
            "SELECT state FROM send_policy WHERE scope='account' AND owner_sub='owner'",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(state, "held");
}

/// Legacy send timestamps use milliseconds, while provider feedback uses
/// seconds; the 90-day scrub must not erase fresh events immediately.
/// 旧发件时间为毫秒、反馈为秒；90 天清理不可立即误删新事件。
#[test]
fn retention_compares_each_timestamp_in_its_own_units() {
    let db = database();
    db.execute("UPDATE send_release_gates SET feedback_verified=1,abuse_contact_verified=1,delivery_canary_verified=1,preview_reviewed=1 WHERE id=1", []).unwrap();
    db.execute(
        "UPDATE send_policy SET state='allowed' WHERE scope='global'",
        [],
    )
    .unwrap();
    let cutoff_ms = 1_790_000_000_000_i64;
    for (key, at) in [("old", cutoff_ms - 1), ("fresh", cutoff_ms + 1)] {
        db.execute("INSERT INTO send_requests(owner_iss,owner_sub,idem_key,payload_hash,message_id,state,created_at,sender,envelope_json) VALUES('issuer','owner',?1,'hash','local','sent',?2,'sender','[]')", params![key, at]).unwrap();
    }
    event(&db, "old", "deferred", cutoff_ms / 1000 - 1).unwrap();
    event(&db, "fresh", "delivered", cutoff_ms / 1000 + 1).unwrap();
    db.execute("UPDATE send_requests SET sender=NULL,envelope_json=NULL WHERE rowid IN (SELECT rowid FROM send_requests WHERE created_at<?1 AND (sender IS NOT NULL OR envelope_json IS NOT NULL) ORDER BY created_at LIMIT 100)", [cutoff_ms]).unwrap();
    db.execute("DELETE FROM provider_events WHERE rowid IN (SELECT rowid FROM provider_events WHERE received_at<?1 ORDER BY received_at LIMIT 100)", [cutoff_ms / 1000]).unwrap();
    let old_sender: Option<String> = db
        .query_row(
            "SELECT sender FROM send_requests WHERE idem_key='old'",
            [],
            |r| r.get(0),
        )
        .unwrap();
    let fresh_sender: Option<String> = db
        .query_row(
            "SELECT sender FROM send_requests WHERE idem_key='fresh'",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(old_sender, None);
    assert_eq!(fresh_sender.as_deref(), Some("sender"));
    let count: i64 = db
        .query_row("SELECT count(*) FROM provider_events", [], |r| r.get(0))
        .unwrap();
    assert_eq!(count, 1);
}
