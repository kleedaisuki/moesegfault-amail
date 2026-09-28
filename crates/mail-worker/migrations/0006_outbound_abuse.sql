-- A missing global row or a D1 read failure must stop outbound submission.
-- 全局记录缺失或 D1 读取失败时，必须停止出站提交。
CREATE TABLE send_policy (
    scope TEXT NOT NULL CHECK (scope IN ('global','account')),
    owner_iss TEXT NOT NULL,
    owner_sub TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('allowed','held')),
    reason_code TEXT NOT NULL,
    actor TEXT NOT NULL,
    note_ref TEXT,
    updated_at INTEGER NOT NULL, -- Unix seconds; unlike legacy send_requests.created_at (milliseconds).
    PRIMARY KEY(scope,owner_iss,owner_sub),
    CHECK ((scope='global' AND owner_iss='*' AND owner_sub='*') OR
           (scope='account' AND owner_iss!='*' AND owner_sub!='*'))
);
-- Public sending starts held until provider policy and abuse operations are approved.
-- 公共发送初始保持停用，直至提供商策略及滥用处理流程获得批准。
-- An append-only audit record makes operator reversals and automatic holds reviewable.
-- 追加式审计记录使人工解除和自动停用均可追溯。
CREATE TABLE send_policy_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    owner_iss TEXT NOT NULL,
    owner_sub TEXT NOT NULL,
    old_state TEXT,
    new_state TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    actor TEXT NOT NULL,
    note_ref TEXT,
    changed_at INTEGER NOT NULL -- Unix seconds.
);
CREATE TRIGGER send_policy_audit_insert AFTER INSERT ON send_policy BEGIN
    INSERT INTO send_policy_audit(scope,owner_iss,owner_sub,old_state,new_state,reason_code,actor,note_ref,changed_at)
    VALUES(NEW.scope,NEW.owner_iss,NEW.owner_sub,NULL,NEW.state,NEW.reason_code,NEW.actor,NEW.note_ref,NEW.updated_at);
END;
CREATE TRIGGER send_policy_audit_update AFTER UPDATE ON send_policy BEGIN
    INSERT INTO send_policy_audit(scope,owner_iss,owner_sub,old_state,new_state,reason_code,actor,note_ref,changed_at)
    VALUES(NEW.scope,NEW.owner_iss,NEW.owner_sub,OLD.state,NEW.state,NEW.reason_code,NEW.actor,NEW.note_ref,NEW.updated_at);
END;
INSERT INTO send_policy(scope,owner_iss,owner_sub,state,reason_code,actor,updated_at)
VALUES ('global','*','*','held','launch_review','migration',unixepoch());

-- An operator must verify each external release condition before the global
-- switch may be enabled. These are audit attestations, not automatic canaries.
-- 操作员须先核验每项外部上线条件才可启用全局开关；这些是审计确认而非自动测试。
CREATE TABLE send_release_gates (
    id INTEGER PRIMARY KEY CHECK (id=1),
    feedback_verified INTEGER NOT NULL DEFAULT 0 CHECK (feedback_verified IN (0,1)),
    abuse_contact_verified INTEGER NOT NULL DEFAULT 0 CHECK (abuse_contact_verified IN (0,1)),
    delivery_canary_verified INTEGER NOT NULL DEFAULT 0 CHECK (delivery_canary_verified IN (0,1)),
    preview_reviewed INTEGER NOT NULL DEFAULT 0 CHECK (preview_reviewed IN (0,1)),
    canary_owner_iss TEXT,
    canary_owner_sub TEXT,
    canary_recipient_sha256 TEXT,
    canary_expires_at INTEGER, -- Unix seconds.
    canary_used_by TEXT,
    actor TEXT NOT NULL,
    case_ref TEXT NOT NULL,
    updated_at INTEGER NOT NULL -- Unix seconds.
);
INSERT INTO send_release_gates(id,actor,case_ref,updated_at)
VALUES(1,'migration','launch_review',unixepoch());
CREATE TABLE send_release_gate_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feedback_verified INTEGER NOT NULL,
    abuse_contact_verified INTEGER NOT NULL,
    delivery_canary_verified INTEGER NOT NULL,
    preview_reviewed INTEGER NOT NULL,
    canary_owner_iss TEXT,
    canary_owner_sub TEXT,
    canary_recipient_sha256 TEXT,
    canary_expires_at INTEGER,
    canary_used_by TEXT,
    actor TEXT NOT NULL,
    case_ref TEXT NOT NULL,
    changed_at INTEGER NOT NULL -- Unix seconds.
);
CREATE TRIGGER send_release_gate_audit_update AFTER UPDATE ON send_release_gates BEGIN
    INSERT INTO send_release_gate_audit(feedback_verified,abuse_contact_verified,delivery_canary_verified,preview_reviewed,canary_owner_iss,canary_owner_sub,canary_recipient_sha256,canary_expires_at,canary_used_by,actor,case_ref,changed_at)
    VALUES(NEW.feedback_verified,NEW.abuse_contact_verified,NEW.delivery_canary_verified,NEW.preview_reviewed,NEW.canary_owner_iss,NEW.canary_owner_sub,NEW.canary_recipient_sha256,NEW.canary_expires_at,NEW.canary_used_by,NEW.actor,NEW.case_ref,NEW.updated_at);
END;
CREATE TRIGGER send_release_gate_revoked AFTER UPDATE ON send_release_gates
WHEN NEW.feedback_verified=0 OR NEW.abuse_contact_verified=0 OR
     NEW.delivery_canary_verified=0 OR NEW.preview_reviewed=0 BEGIN
    UPDATE send_policy SET state='held',reason_code='release_gate_revoked',
        actor=NEW.actor,note_ref=NEW.case_ref,updated_at=NEW.updated_at
    WHERE scope='global' AND owner_iss='*' AND owner_sub='*' AND state!='held';
END;

-- Account-local do-not-contact entries never appear in public search or telemetry.
-- 账户级禁止联系记录绝不进入公开检索或遥测。
CREATE TABLE recipient_blocks (
    owner_iss TEXT NOT NULL,
    owner_sub TEXT NOT NULL,
    recipient TEXT NOT NULL,
    provenance TEXT NOT NULL CHECK (provenance IN ('complaint','direct_report','operator')),
    note_ref TEXT,
    created_at INTEGER NOT NULL, -- Legacy Worker Unix milliseconds.
    PRIMARY KEY(owner_iss,owner_sub,recipient)
);

-- The provider ID lookup is used only by restricted lifecycle processing.
-- 提供商 ID 索引仅供受限生命周期处理使用。
-- SQLite cannot widen an existing CHECK in place; preserve every request while
-- introducing a terminal rejected state for definitive provider refusals.
-- SQLite 无法原地扩展 CHECK；保留全部请求并引入确定性拒绝的终态。
CREATE TABLE send_requests_v2 (
    owner_iss TEXT NOT NULL,
    owner_sub TEXT NOT NULL,
    idem_key TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    message_id TEXT,
    provider_id TEXT,
    quota_reserved INTEGER NOT NULL DEFAULT 0 CHECK (quota_reserved IN (0,1)),
    state TEXT NOT NULL CHECK (state IN ('preparing','reserving','submitting','unknown','accepted','sent','rejected')),
    created_at INTEGER NOT NULL,
    reservation_started_at INTEGER,
    rejection_code TEXT,
    request_id TEXT,
    sender TEXT,
    envelope_json TEXT,
    PRIMARY KEY(owner_iss,owner_sub,idem_key)
);
INSERT INTO send_requests_v2(owner_iss,owner_sub,idem_key,payload_hash,message_id,provider_id,quota_reserved,state,created_at,reservation_started_at)
SELECT owner_iss,owner_sub,idem_key,payload_hash,message_id,provider_id,quota_reserved,state,created_at,reservation_started_at
FROM send_requests;
DROP TABLE send_requests;
ALTER TABLE send_requests_v2 RENAME TO send_requests;
CREATE INDEX send_requests_provider ON send_requests(provider_id) WHERE provider_id IS NOT NULL;
CREATE INDEX send_requests_envelope_expiry ON send_requests(created_at)
WHERE sender IS NOT NULL OR envelope_json IS NOT NULL;
-- Best-effort backfill of previously indexed sends; cron repairs accepted sends
-- whose message row was not yet visible at migration time.
-- 尽力回填先前已索引的发件；迁移时尚不可见的已接受邮件由定时任务修复。
UPDATE send_requests SET
    sender=(SELECT sender FROM messages WHERE id=send_requests.message_id),
    envelope_json=(SELECT json_extract(metadata_json,'$.envelope_recipients') FROM messages WHERE id=send_requests.message_id)
WHERE provider_id IS NOT NULL AND message_id IS NOT NULL
  AND created_at>=unixepoch()*1000-90*86400000;

-- A policy change racing a fresh send cannot leave unlimited pending keys.
-- 策略变化与新发件并发时，不能留下无限增长的待处理幂等键。
CREATE TRIGGER send_request_policy_guard BEFORE INSERT ON send_requests BEGIN
    UPDATE send_release_gates SET canary_used_by=NEW.idem_key,updated_at=unixepoch()
    WHERE id=1 AND canary_owner_iss=NEW.owner_iss
      AND canary_owner_sub=NEW.owner_sub AND canary_expires_at>unixepoch()
      AND canary_used_by IS NULL
      AND EXISTS(SELECT 1 FROM send_policy p WHERE p.scope='global'
          AND p.owner_iss='*' AND p.owner_sub='*' AND p.state='held')
      AND NOT EXISTS(SELECT 1 FROM send_policy p WHERE p.scope='account'
          AND p.owner_iss=NEW.owner_iss AND p.owner_sub=NEW.owner_sub AND p.state='held');
    SELECT CASE WHEN NOT EXISTS(
        SELECT 1 FROM send_policy p JOIN send_release_gates g ON g.id=1
        WHERE p.scope='global' AND p.owner_iss='*' AND p.owner_sub='*'
          AND p.state='allowed' AND g.feedback_verified=1
          AND g.abuse_contact_verified=1 AND g.delivery_canary_verified=1
          AND g.preview_reviewed=1
    ) AND NOT EXISTS(
        SELECT 1 FROM send_release_gates g WHERE g.id=1
          AND g.canary_owner_iss=NEW.owner_iss AND g.canary_owner_sub=NEW.owner_sub
          AND g.canary_expires_at>unixepoch() AND g.canary_used_by=NEW.idem_key
    ) OR EXISTS(
        SELECT 1 FROM send_policy p WHERE p.scope='account'
          AND p.owner_iss=NEW.owner_iss AND p.owner_sub=NEW.owner_sub
          AND p.state='held'
    ) THEN RAISE(ABORT,'send_held') END;
END;

-- One provider event is one atomic risk transition; never retain subject or SMTP text.
-- 单条提供商事件对应一次原子风险状态变化；不保存标题或 SMTP 原文。
CREATE TABLE provider_events (
    event_id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    local_message_id TEXT NOT NULL,
    owner_iss TEXT NOT NULL,
    owner_sub TEXT NOT NULL,
    recipient TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('deferred','delivered','bounced','failed','rejected','complained')),
    occurred_at INTEGER NOT NULL, -- Unix seconds from provider metadata.
    received_at INTEGER NOT NULL -- Unix seconds from the Queue consumer.
);
CREATE INDEX provider_events_owner_time ON provider_events(owner_iss,owner_sub,received_at);
CREATE INDEX provider_events_expiry ON provider_events(received_at);

-- A complaint outranks all other outcomes; a late deferred event cannot regress delivery.
-- 投诉优先于所有状态；迟到的延迟事件不能使投递状态倒退。
CREATE TABLE recipient_outcomes (
    local_message_id TEXT NOT NULL,
    recipient TEXT NOT NULL,
    owner_iss TEXT NOT NULL,
    owner_sub TEXT NOT NULL,
    kind TEXT NOT NULL,
    risk_rank INTEGER NOT NULL CHECK (risk_rank BETWEEN 1 AND 4),
    occurred_at INTEGER NOT NULL, -- Unix seconds.
    event_id TEXT NOT NULL,
    PRIMARY KEY(local_message_id,recipient)
);
CREATE INDEX recipient_outcomes_expiry ON recipient_outcomes(occurred_at);

CREATE TRIGGER provider_event_outcome AFTER INSERT ON provider_events BEGIN
    INSERT INTO recipient_outcomes(local_message_id,recipient,owner_iss,owner_sub,kind,risk_rank,occurred_at,event_id)
    VALUES (NEW.local_message_id,NEW.recipient,NEW.owner_iss,NEW.owner_sub,NEW.kind,
        CASE NEW.kind WHEN 'deferred' THEN 1 WHEN 'delivered' THEN 2
            WHEN 'complained' THEN 4 ELSE 3 END, NEW.occurred_at,NEW.event_id)
    ON CONFLICT(local_message_id,recipient) DO UPDATE SET
        kind=excluded.kind,
        risk_rank=excluded.risk_rank,
        occurred_at=excluded.occurred_at,
        event_id=excluded.event_id
    WHERE excluded.risk_rank > recipient_outcomes.risk_rank OR
        (excluded.risk_rank = recipient_outcomes.risk_rank AND
         excluded.occurred_at > recipient_outcomes.occurred_at);
END;

-- Feedback-loop complaints immediately hold the account and block that recipient.
-- 反馈循环投诉立即停用该账户发送并阻止继续联系该收件人。
CREATE TRIGGER provider_event_complaint AFTER INSERT ON provider_events
WHEN NEW.kind='complained' BEGIN
    INSERT INTO send_policy(scope,owner_iss,owner_sub,state,reason_code,actor,note_ref,updated_at)
    VALUES ('account',NEW.owner_iss,NEW.owner_sub,'held','provider_complaint','provider_event',NEW.event_id,NEW.received_at)
    ON CONFLICT(scope,owner_iss,owner_sub) DO UPDATE SET
        state='held',reason_code='provider_complaint',actor='provider_event',
        note_ref=NEW.event_id,updated_at=NEW.received_at;
    INSERT OR IGNORE INTO recipient_blocks(owner_iss,owner_sub,recipient,provenance,note_ref,created_at)
    VALUES (NEW.owner_iss,NEW.owner_sub,NEW.recipient,'complaint',NEW.event_id,NEW.received_at);
END;
