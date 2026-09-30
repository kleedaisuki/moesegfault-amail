-- Reservations are inserted before R2 writes so crashes cannot create untracked objects.
-- R2 写入前先预留额度，确保崩溃不会生成无法追踪的对象。
CREATE TABLE IF NOT EXISTS storage_usage (
    owner_iss TEXT NOT NULL,
    owner_sub TEXT NOT NULL,
    used_bytes INTEGER NOT NULL DEFAULT 0 CHECK (used_bytes >= 0),
    PRIMARY KEY(owner_iss,owner_sub)
);

CREATE TABLE IF NOT EXISTS storage_reservations (
    id TEXT PRIMARY KEY,
    owner_iss TEXT NOT NULL,
    owner_sub TEXT NOT NULL,
    bytes INTEGER NOT NULL CHECK (bytes >= 0),
    state TEXT NOT NULL CHECK (state IN ('reserved','indexed')),
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS storage_reservations_pending ON storage_reservations(state,created_at);

-- SQLite serializes writers, so this trigger checks the account cap in the same INSERT transaction.
-- SQLite 串行化写者；此触发器在同一 INSERT 事务内检查账户额度。
CREATE TRIGGER storage_reservations_guard BEFORE INSERT ON storage_reservations
BEGIN
    -- Cloudflare D1's remote splitter requires CASE to be parenthesized inside a trigger.
    -- Cloudflare D1 远端语句拆分器要求触发器内的 CASE 加括号。
    SELECT (CASE WHEN NOT EXISTS(SELECT 1 FROM storage_reservations WHERE id=NEW.id)
        AND COALESCE((SELECT used_bytes FROM storage_usage
        WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub),0) + NEW.bytes > 1073741824
        THEN RAISE(ABORT,'mailbox_full') END);
END;

CREATE TRIGGER storage_reservations_add AFTER INSERT ON storage_reservations
BEGIN
    INSERT INTO storage_usage(owner_iss,owner_sub,used_bytes)
    VALUES(NEW.owner_iss,NEW.owner_sub,NEW.bytes)
    ON CONFLICT(owner_iss,owner_sub) DO UPDATE SET used_bytes=used_bytes+excluded.used_bytes;
END;

CREATE TRIGGER storage_reservations_release AFTER DELETE ON storage_reservations
BEGIN
    UPDATE storage_usage SET used_bytes=used_bytes-OLD.bytes
    WHERE owner_iss=OLD.owner_iss AND owner_sub=OLD.owner_sub;
END;

-- Backfill messages created before this migration without changing their external IDs.
-- 回填本迁移前创建的邮件，保持外部 ID 不变。
INSERT OR IGNORE INTO storage_reservations(id,owner_iss,owner_sub,bytes,state,created_at)
SELECT id,owner_iss,owner_sub,storage_bytes,'indexed',received_at
FROM messages WHERE deleted_at IS NULL;
