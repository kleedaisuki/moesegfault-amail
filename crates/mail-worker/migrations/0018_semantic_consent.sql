-- Existing vectors remain private stored projections, not consent to retransmit.
-- No row is the default-off preference, including every pre-migration account.
CREATE TABLE semantic_preferences (
    owner_iss TEXT NOT NULL,
    owner_sub TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
    generation INTEGER NOT NULL DEFAULT 0 CHECK(generation >= 0),
    PRIMARY KEY(owner_iss,owner_sub)
);
ALTER TABLE embedding_work ADD COLUMN consent_generation INTEGER NOT NULL DEFAULT 0;
ALTER TABLE embedding_work ADD COLUMN consent_lease_token TEXT;
ALTER TABLE messages ADD COLUMN embedding_consent_generation INTEGER;

-- Revoke pre-consent claims without changing their vectors or retry evidence.
UPDATE embedding_work SET lease_until=0,lease_token=NULL,consent_lease_token=NULL;

-- Existing query jobs may contain a Qwen vector. Invalidate their continuation
-- epoch without deleting retained document vectors or transmitting any content.
INSERT INTO search_generations(owner_iss,owner_sub,generation)
    SELECT owner_iss,owner_sub,1 FROM search_jobs WHERE 1 GROUP BY owner_iss,owner_sub
    ON CONFLICT(owner_iss,owner_sub) DO UPDATE SET generation=generation+1;

-- Older Workers set only lease_token. The matching mirror is deliberately a
-- capability check, so an old overlapping deployment cannot acquire new work.
CREATE TRIGGER embedding_claim_consent BEFORE UPDATE OF lease_token ON embedding_work
WHEN NEW.lease_token IS NOT NULL AND (
    NEW.consent_lease_token IS NOT NEW.lease_token OR NOT EXISTS (
        SELECT 1 FROM semantic_preferences p WHERE p.owner_iss=NEW.owner_iss
        AND p.owner_sub=NEW.owner_sub AND p.enabled=1 AND p.generation=NEW.consent_generation
    )
) BEGIN
    SELECT RAISE(IGNORE);
END;

DROP TRIGGER messages_embedding_insert;
CREATE TRIGGER messages_embedding_insert AFTER INSERT ON messages
WHEN NEW.deleted_at IS NULL AND NEW.embedding_json IS NULL BEGIN
    INSERT OR IGNORE INTO embedding_owner_schedule(owner_iss,owner_sub)
    VALUES(NEW.owner_iss,NEW.owner_sub);
    INSERT INTO embedding_work(message_id,owner_iss,owner_sub,received_at,consent_generation)
    VALUES(NEW.id,NEW.owner_iss,NEW.owner_sub,NEW.received_at,
        COALESCE((SELECT generation FROM semantic_preferences
            WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub),0));
END;

DROP TRIGGER messages_embedding_finished;
CREATE TRIGGER messages_embedding_finished AFTER UPDATE OF embedding_json,deleted_at ON messages
BEGIN
    DELETE FROM embedding_work WHERE message_id=NEW.id AND (
        NEW.deleted_at IS NOT NULL OR (NEW.embedding_json IS NOT NULL
            AND NEW.embedding_consent_generation=consent_generation)
    );
END;

DROP TRIGGER messages_outbound_projection_requeue;
CREATE TRIGGER messages_outbound_projection_requeue AFTER UPDATE OF body_text ON messages
WHEN NEW.deleted_at IS NULL AND NEW.direction='outbound'
    AND EXISTS (SELECT 1 FROM send_requests s WHERE s.message_id=NEW.id
        AND s.owner_iss=NEW.owner_iss AND s.owner_sub=NEW.owner_sub AND s.state='accepted')
BEGIN
    DELETE FROM embedding_work WHERE message_id=NEW.id;
    INSERT OR IGNORE INTO embedding_owner_schedule(owner_iss,owner_sub)
    VALUES(NEW.owner_iss,NEW.owner_sub);
    INSERT INTO embedding_work(message_id,owner_iss,owner_sub,received_at,consent_generation)
    VALUES(NEW.id,NEW.owner_iss,NEW.owner_sub,NEW.received_at,
        COALESCE((SELECT generation FROM semantic_preferences
            WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub),0));
END;

-- One transition is one database transaction: disable cancels claims; each
-- enable (not each repeated command) replaces the ledger for a complete rebuild.
CREATE TRIGGER semantic_preferences_insert AFTER INSERT ON semantic_preferences BEGIN
    UPDATE embedding_work SET lease_until=0,lease_token=NULL,consent_lease_token=NULL
        WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub;
    DELETE FROM embedding_work WHERE NEW.enabled=1
        AND owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub;
    INSERT OR IGNORE INTO embedding_owner_schedule(owner_iss,owner_sub)
        SELECT NEW.owner_iss,NEW.owner_sub WHERE NEW.enabled=1;
    INSERT INTO embedding_work(message_id,owner_iss,owner_sub,received_at,consent_generation)
        SELECT id,owner_iss,owner_sub,received_at,NEW.generation FROM messages
        WHERE NEW.enabled=1 AND owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub
        AND deleted_at IS NULL AND NOT EXISTS(SELECT 1 FROM addresses a
            WHERE a.address=messages.address AND a.kind='tmpaddr'
            AND (a.generation!=messages.mailbox_generation OR a.released_at IS NOT NULL
                OR a.expires_at<=CAST(unixepoch('subsec')*1000 AS INTEGER) OR a.state!='active'));
    INSERT INTO search_generations(owner_iss,owner_sub,generation)
        SELECT NEW.owner_iss,NEW.owner_sub,1 WHERE NEW.enabled=1
        ON CONFLICT(owner_iss,owner_sub) DO UPDATE SET generation=generation+1;
END;

CREATE TRIGGER semantic_preferences_transition AFTER UPDATE OF enabled ON semantic_preferences
WHEN OLD.enabled!=NEW.enabled BEGIN
    UPDATE embedding_work SET lease_until=0,lease_token=NULL,consent_lease_token=NULL
        WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub;
    DELETE FROM embedding_work WHERE NEW.enabled=1
        AND owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub;
    INSERT OR IGNORE INTO embedding_owner_schedule(owner_iss,owner_sub)
        SELECT NEW.owner_iss,NEW.owner_sub WHERE NEW.enabled=1;
    INSERT INTO embedding_work(message_id,owner_iss,owner_sub,received_at,consent_generation)
        SELECT id,owner_iss,owner_sub,received_at,NEW.generation FROM messages
        WHERE NEW.enabled=1 AND owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub
        AND deleted_at IS NULL AND NOT EXISTS(SELECT 1 FROM addresses a
            WHERE a.address=messages.address AND a.kind='tmpaddr'
            AND (a.generation!=messages.mailbox_generation OR a.released_at IS NOT NULL
                OR a.expires_at<=CAST(unixepoch('subsec')*1000 AS INTEGER) OR a.state!='active'));
    INSERT INTO search_generations(owner_iss,owner_sub,generation)
        VALUES(NEW.owner_iss,NEW.owner_sub,1)
        ON CONFLICT(owner_iss,owner_sub) DO UPDATE SET generation=generation+1;
END;
