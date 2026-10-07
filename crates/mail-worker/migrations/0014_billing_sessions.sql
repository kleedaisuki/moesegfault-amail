-- Browser consent is correlated to immutable mailbox ownership without changing
-- Identity's deployed pairwise subject sector or copying browser credentials.
CREATE TABLE billing_sessions (
    id TEXT NOT NULL,
    owner_iss TEXT NOT NULL,
    owner_sub TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('subscribe','manage')),
    requested_plan TEXT NOT NULL CHECK(requested_plan IN ('free','lite','plus')),
    remote_id TEXT,
    authorization_url TEXT,
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK(state IN ('pending','completed','cancelled','expired','failed')),
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    PRIMARY KEY(owner_iss,owner_sub,id)
);
CREATE INDEX billing_sessions_expiry ON billing_sessions(expires_at);

-- Failed/ambiguous service delivery retains the same immutable event and moves
-- its next retry behind ready peers; never delete usage to make a sweep green.
ALTER TABLE resource_outbox ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE resource_outbox ADD COLUMN next_attempt_at INTEGER NOT NULL DEFAULT 0;
CREATE INDEX resource_outbox_due ON resource_outbox(next_attempt_at,occurred_at)
    WHERE delivered_at IS NULL;
