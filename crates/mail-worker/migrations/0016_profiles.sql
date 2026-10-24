CREATE TABLE mail_profiles (
    id TEXT PRIMARY KEY,
    owner_iss TEXT NOT NULL,
    owner_sub TEXT NOT NULL,
    name TEXT NOT NULL,
    durable INTEGER NOT NULL CHECK(durable IN (0,1)),
    is_user INTEGER NOT NULL CHECK(is_user IN (0,1)),
    terminal_id TEXT,
    session_token TEXT UNIQUE,
    session_expires_at INTEGER,
    created_at INTEGER NOT NULL,
    UNIQUE(owner_iss,owner_sub,name),
    CHECK ((terminal_id IS NULL AND session_token IS NULL AND session_expires_at IS NULL)
        OR (terminal_id IS NOT NULL AND session_token IS NOT NULL AND session_expires_at IS NOT NULL))
);
CREATE INDEX mail_profiles_expiry ON mail_profiles(session_expires_at) WHERE session_token IS NOT NULL;

-- Locks are capabilities of one immutable profile session, never of a reusable name.
CREATE TABLE mailbox_leases (
    address TEXT NOT NULL,
    address_generation TEXT NOT NULL,
    profile_id TEXT NOT NULL REFERENCES mail_profiles(id) ON DELETE CASCADE,
    session_token TEXT NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('read','write')),
    lease_token TEXT NOT NULL UNIQUE,
    acquired_at INTEGER NOT NULL,
    PRIMARY KEY(address,profile_id)
);
CREATE INDEX mailbox_leases_session ON mailbox_leases(session_token);
CREATE TRIGGER mail_profile_session_release AFTER UPDATE OF session_token ON mail_profiles
WHEN OLD.session_token IS NOT NEW.session_token
BEGIN
    DELETE FROM mailbox_leases WHERE profile_id=OLD.id;
END;

ALTER TABLE search_jobs ADD COLUMN profile_scope TEXT NOT NULL DEFAULT '';
ALTER TABLE send_requests ADD COLUMN profile_scope TEXT NOT NULL DEFAULT '';
