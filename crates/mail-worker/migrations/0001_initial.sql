-- Mailbox ownership is keyed by immutable OIDC issuer and subject, not profile fields.
-- 邮箱所有权以不可变的 OIDC 签发者与主体为键，而不是用户资料字段。
CREATE TABLE IF NOT EXISTS addresses (
    address TEXT PRIMARY KEY,
    local_part TEXT NOT NULL,
    owner_iss TEXT NOT NULL,
    owner_sub TEXT NOT NULL,
    slot INTEGER NOT NULL CHECK (slot BETWEEN 0 AND 9),
    cf_rule_id TEXT UNIQUE,
    state TEXT NOT NULL CHECK (state IN ('pending','provisioning','active','deleting','retired')),
    needs_reconcile INTEGER NOT NULL DEFAULT 0 CHECK (needs_reconcile IN (0,1)),
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS addresses_owner ON addresses(owner_iss, owner_sub, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS addresses_active_slot ON addresses(owner_iss,owner_sub,slot) WHERE state != 'retired';

-- The R2 ZIP is immutable; status is mutable in D1. No raw content enters logs.
-- R2 ZIP 不可变；状态仅在 D1 中变更，原始内容不得进入日志。
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    address TEXT NOT NULL,
    owner_iss TEXT NOT NULL,
    owner_sub TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('inbound','outbound')),
    sender TEXT NOT NULL,
    recipients_json TEXT NOT NULL,
    subject TEXT NOT NULL,
    body_text TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    received_at INTEGER NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0 CHECK (is_read IN (0,1)),
    has_html INTEGER NOT NULL,
    has_text INTEGER NOT NULL,
    attachment_count INTEGER NOT NULL,
    r2_key TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    embedding_json TEXT,
    embedding_model TEXT,
    embedding_dimensions INTEGER,
    deleted_at INTEGER,
    FOREIGN KEY(address) REFERENCES addresses(address)
);
CREATE INDEX IF NOT EXISTS messages_owner_time ON messages(owner_iss, owner_sub, received_at DESC, id DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS messages_owner_address ON messages(owner_iss, owner_sub, address, received_at DESC) WHERE deleted_at IS NULL;

-- Long searchable bodies are segmented to stay below D1's per-row value limit.
-- 长正文分块保存，避免触及 D1 单行值限制。
CREATE TABLE IF NOT EXISTS message_text_chunks (
    message_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY(message_id,chunk_index)
);

-- Idempotency is scoped to one mailbox identity to avoid cross-account collision.
-- 幂等键按邮箱身份隔离，避免不同账户间冲突。
CREATE TABLE IF NOT EXISTS send_requests (
    owner_iss TEXT NOT NULL,
    owner_sub TEXT NOT NULL,
    idem_key TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    message_id TEXT,
    provider_id TEXT,
    quota_reserved INTEGER NOT NULL DEFAULT 0 CHECK (quota_reserved IN (0,1)),
    state TEXT NOT NULL CHECK (state IN ('preparing','reserving','submitting','unknown','accepted','sent')),
    created_at INTEGER NOT NULL,
    PRIMARY KEY(owner_iss, owner_sub, idem_key)
);

-- D1 conditional upserts make quota reservation atomic across concurrent requests.
-- D1 条件性 upsert 使并发请求的额度预留具备原子性。
CREATE TABLE IF NOT EXISTS daily_usage (
    kind TEXT NOT NULL,
    owner_iss TEXT NOT NULL,
    owner_sub TEXT NOT NULL,
    day INTEGER NOT NULL,
    used INTEGER NOT NULL CHECK (used >= 0),
    PRIMARY KEY(kind, owner_iss, owner_sub, day)
);
