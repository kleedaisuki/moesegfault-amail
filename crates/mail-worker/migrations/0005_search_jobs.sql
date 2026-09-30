-- Increment once per message mutation so a continued scan cannot mix search epochs.
-- 每次邮件变更递增一次，使续扫不会混合不同检索代际。
CREATE TABLE IF NOT EXISTS search_generations (
    owner_iss TEXT NOT NULL,
    owner_sub TEXT NOT NULL,
    generation INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(owner_iss,owner_sub)
);
INSERT OR IGNORE INTO search_generations(owner_iss,owner_sub,generation)
SELECT owner_iss,owner_sub,0 FROM messages GROUP BY owner_iss,owner_sub;

CREATE TRIGGER IF NOT EXISTS messages_search_insert AFTER INSERT ON messages BEGIN
    INSERT INTO search_generations(owner_iss,owner_sub,generation) VALUES(NEW.owner_iss,NEW.owner_sub,1)
    ON CONFLICT(owner_iss,owner_sub) DO UPDATE SET generation=generation+1;
END;
CREATE TRIGGER IF NOT EXISTS messages_search_update AFTER UPDATE ON messages BEGIN
    INSERT INTO search_generations(owner_iss,owner_sub,generation) VALUES(NEW.owner_iss,NEW.owner_sub,1)
    ON CONFLICT(owner_iss,owner_sub) DO UPDATE SET generation=generation+1;
END;
CREATE TRIGGER IF NOT EXISTS messages_search_delete AFTER DELETE ON messages BEGIN
    INSERT INTO search_generations(owner_iss,owner_sub,generation) VALUES(OLD.owner_iss,OLD.owner_sub,1)
    ON CONFLICT(owner_iss,owner_sub) DO UPDATE SET generation=generation+1;
END;

-- The checkpoint contains filters and a query vector, never body or ZIP bytes.
-- 检查点保存筛选条件与查询向量，绝不保存正文或 ZIP 字节。
CREATE TABLE IF NOT EXISTS search_jobs (
    id TEXT PRIMARY KEY,
    owner_iss TEXT NOT NULL,
    owner_sub TEXT NOT NULL,
    request_json TEXT NOT NULL,
    state_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('preparing','running','advancing','done','stale','expired')),
    version INTEGER NOT NULL DEFAULT 0,
    lease_started_at INTEGER,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS search_jobs_owner ON search_jobs(owner_iss,owner_sub,state,expires_at);
CREATE INDEX IF NOT EXISTS search_jobs_expiry ON search_jobs(expires_at);
