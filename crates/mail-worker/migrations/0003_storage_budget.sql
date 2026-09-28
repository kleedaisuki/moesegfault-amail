-- Account storage budget counts both raw MIME and agent ZIP, not only daily ingestion.
-- 账户存储额度同时计入原始 MIME 与代理 ZIP，而非仅每日摄入量。
ALTER TABLE messages ADD COLUMN storage_bytes INTEGER NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS messages_storage_owner ON messages(owner_iss,owner_sub,storage_bytes) WHERE deleted_at IS NULL;
