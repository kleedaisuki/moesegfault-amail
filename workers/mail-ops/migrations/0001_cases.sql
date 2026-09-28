-- 中文：运营邮件与用户邮箱完全独立；此迁移仅可用于专属 OPS_DB。
-- English: Operator intake is isolated from user mail; apply only to dedicated OPS_DB.
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    route TEXT NOT NULL CHECK (route IN ('abuse', 'postmaster')),
    object_key TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL CHECK (state IN ('receiving', 'failed', 'open', 'reviewed', 'closed', 'expiring')),
    alert_state TEXT NOT NULL DEFAULT 'pending' CHECK (alert_state IN ('pending', 'sent')),
    last_actor_sub TEXT NOT NULL DEFAULT 'system',
    size_bytes INTEGER NOT NULL CHECK (size_bytes BETWEEN 0 AND 26214400),
    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
    updated_at INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS cases_queue ON cases(state, created_at, id);
CREATE INDEX IF NOT EXISTS cases_alert ON cases(alert_state, state, created_at);

-- 中文：有界遍历 R2，清理极少数跨存储失败留下的无索引原文。
-- English: Bounded R2 walk retires orphan raw objects after cross-store failures.
CREATE TABLE IF NOT EXISTS gc_cursor (
    id INTEGER PRIMARY KEY CHECK (id=1),
    cursor TEXT
);
INSERT OR IGNORE INTO gc_cursor(id,cursor) VALUES(1,NULL);

-- 中文：只记录主体 ID 和动作，不把投诉正文、地址或自由文本复制进索引。
-- English: Audit principal IDs and actions only, not report bodies, addresses, or free text.
CREATE TABLE IF NOT EXISTS case_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL REFERENCES cases(id),
    actor_sub TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('received', 'reviewed', 'reopened', 'closed', 'expired')),
    occurred_at INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS case_audit_case ON case_audit(case_id, occurred_at);

-- 中文：状态和审计在同一 D1 事务中提交，避免“已结案但无审计”的分裂状态。
-- English: State and audit commit in one D1 transaction; no unaudited closure.
CREATE TRIGGER IF NOT EXISTS cases_received AFTER UPDATE OF state ON cases
WHEN OLD.state IN ('receiving','failed') AND NEW.state='open'
BEGIN
    INSERT INTO case_audit(case_id,actor_sub,action)
    VALUES(NEW.id,NEW.last_actor_sub,'received');
END;
CREATE TRIGGER IF NOT EXISTS cases_reopened AFTER UPDATE OF state ON cases
WHEN OLD.state NOT IN ('receiving','failed') AND NEW.state='open'
BEGIN
    INSERT INTO case_audit(case_id,actor_sub,action)
    VALUES(NEW.id,NEW.last_actor_sub,'reopened');
END;
CREATE TRIGGER IF NOT EXISTS cases_reviewed AFTER UPDATE OF state ON cases
WHEN OLD.state!=NEW.state AND NEW.state='reviewed'
BEGIN
    INSERT INTO case_audit(case_id,actor_sub,action)
    VALUES(NEW.id,NEW.last_actor_sub,'reviewed');
END;
CREATE TRIGGER IF NOT EXISTS cases_closed AFTER UPDATE OF state ON cases
WHEN OLD.state!=NEW.state AND NEW.state='closed'
BEGIN
    INSERT INTO case_audit(case_id,actor_sub,action)
    VALUES(NEW.id,NEW.last_actor_sub,'closed');
END;
