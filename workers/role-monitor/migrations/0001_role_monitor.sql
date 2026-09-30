-- 中文：系统角色邮件只保存最少到达元数据，不保存发件人、主题、正文或目的地。
-- English: Role mail stores minimal arrival metadata, never sender, subject, body, or destination.
CREATE TABLE IF NOT EXISTS role_arrivals (
    arrival_seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL CHECK (role IN ('apex_abuse','apex_postmaster','mail_abuse','mail_postmaster','staging_probe')),
    received_at INTEGER NOT NULL CHECK (received_at > 0),
    forward_state TEXT NOT NULL DEFAULT 'unknown' CHECK (forward_state IN ('unknown','accepted')),
    forward_updated_at INTEGER,
    alerted_at INTEGER
);
CREATE INDEX IF NOT EXISTS role_arrivals_unalerted ON role_arrivals(alerted_at, received_at);
CREATE INDEX IF NOT EXISTS role_arrivals_forward ON role_arrivals(forward_state, received_at);

-- 中文：故意初始为失效租约；只有经过规则与告警健康检查的 Cron 才能续租。
-- English: The lease starts invalid and only a healthy audited Cron may renew it.
CREATE TABLE IF NOT EXISTS role_monitor_health (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    lease_until INTEGER NOT NULL DEFAULT 0,
    checked_at INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO role_monitor_health(singleton, lease_until, checked_at) VALUES (1, 0, 0);
