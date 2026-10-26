-- Consent controls admission, not the lifetime of a compatible document vector.
-- Publishers already validate vector coordinates; search still rejects corruption.
CREATE VIEW semantic_compatible_embeddings AS
SELECT id AS message_id FROM messages
WHERE embedding_json IS NOT NULL AND embedding_model='voyageai/voyage-4'
    AND embedding_dimensions=256 AND embedding_input_version=1;

-- Fence every pre-migration result, then retain only genuinely unfinished work.
-- Retry/quarantine history survives; enabling is not a provider-retry override.
UPDATE embedding_work SET lease_until=0,lease_token=NULL,consent_lease_token=NULL,
    consent_generation=COALESCE((SELECT p.generation FROM semantic_preferences p
        WHERE p.owner_iss=embedding_work.owner_iss AND p.owner_sub=embedding_work.owner_sub),0);
DELETE FROM embedding_work WHERE EXISTS(
    SELECT 1 FROM semantic_compatible_embeddings c WHERE c.message_id=embedding_work.message_id);
INSERT INTO embedding_work(message_id,owner_iss,owner_sub,received_at,consent_generation)
    SELECT m.id,m.owner_iss,m.owner_sub,m.received_at,p.generation FROM messages m
    JOIN semantic_preferences p ON p.owner_iss=m.owner_iss AND p.owner_sub=m.owner_sub AND p.enabled=1
    WHERE m.deleted_at IS NULL
    AND NOT EXISTS(SELECT 1 FROM semantic_compatible_embeddings c WHERE c.message_id=m.id)
    AND NOT EXISTS(SELECT 1 FROM embedding_work w WHERE w.message_id=m.id)
    AND NOT EXISTS(SELECT 1 FROM addresses a WHERE a.address=m.address AND a.kind='tmpaddr'
        AND (a.generation!=m.mailbox_generation OR a.released_at IS NOT NULL
            OR a.expires_at<=CAST(unixepoch('subsec')*1000 AS INTEGER) OR a.state!='active'));
DELETE FROM embedding_owner_schedule WHERE NOT EXISTS(
    SELECT 1 FROM embedding_work w WHERE w.owner_iss=embedding_owner_schedule.owner_iss
        AND w.owner_sub=embedding_owner_schedule.owner_sub);
INSERT INTO embedding_owner_schedule(owner_iss,owner_sub)
    SELECT w.owner_iss,w.owner_sub FROM embedding_work w
    WHERE NOT EXISTS(SELECT 1 FROM embedding_owner_schedule o
        WHERE o.owner_iss=w.owner_iss AND o.owner_sub=w.owner_sub)
    GROUP BY w.owner_iss,w.owner_sub;

DROP TRIGGER embedding_claim_consent;
CREATE TRIGGER embedding_claim_consent BEFORE UPDATE OF lease_token ON embedding_work
WHEN NEW.lease_token IS NOT NULL AND (
    NEW.consent_lease_token IS NOT NEW.lease_token OR NOT EXISTS (
        SELECT 1 FROM semantic_preferences p WHERE p.owner_iss=NEW.owner_iss
        AND p.owner_sub=NEW.owner_sub AND p.enabled=1 AND p.generation=NEW.consent_generation
    ) OR EXISTS(SELECT 1 FROM semantic_compatible_embeddings c WHERE c.message_id=NEW.message_id)
) BEGIN
    -- This also rejects overlapping v0.3.1 Workers, which know only consent fences.
    SELECT RAISE(IGNORE);
END;

DROP TRIGGER messages_embedding_insert;
CREATE TRIGGER messages_embedding_insert AFTER INSERT ON messages
WHEN NEW.deleted_at IS NULL
    AND NOT EXISTS(SELECT 1 FROM semantic_compatible_embeddings c WHERE c.message_id=NEW.id)
BEGIN
    INSERT INTO embedding_work(message_id,owner_iss,owner_sub,received_at,consent_generation)
        VALUES(NEW.id,NEW.owner_iss,NEW.owner_sub,NEW.received_at,
            COALESCE((SELECT generation FROM semantic_preferences
                WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub),0));
    INSERT INTO embedding_owner_schedule(owner_iss,owner_sub)
        SELECT NEW.owner_iss,NEW.owner_sub WHERE NOT EXISTS(
            SELECT 1 FROM embedding_owner_schedule o
            WHERE o.owner_iss=NEW.owner_iss AND o.owner_sub=NEW.owner_sub);
END;

DROP TRIGGER messages_embedding_finished;
CREATE TRIGGER messages_embedding_finished AFTER UPDATE OF embedding_json,deleted_at ON messages
BEGIN
    DELETE FROM embedding_work WHERE message_id=NEW.id AND (
        NEW.deleted_at IS NOT NULL OR EXISTS(
            SELECT 1 FROM semantic_compatible_embeddings c WHERE c.message_id=NEW.id)
    );
END;

DROP TRIGGER messages_outbound_projection_requeue;
CREATE TRIGGER messages_outbound_projection_requeue AFTER UPDATE OF body_text ON messages
WHEN NEW.deleted_at IS NULL AND NEW.direction='outbound'
    AND EXISTS(SELECT 1 FROM send_requests s WHERE s.message_id=NEW.id
        AND s.owner_iss=NEW.owner_iss AND s.owner_sub=NEW.owner_sub AND s.state='accepted')
BEGIN
    -- Accepted projection repair clears obsolete vector metadata atomically.
    DELETE FROM embedding_work WHERE message_id=NEW.id;
    INSERT INTO embedding_work(message_id,owner_iss,owner_sub,received_at,consent_generation)
        SELECT NEW.id,NEW.owner_iss,NEW.owner_sub,NEW.received_at,
            COALESCE((SELECT generation FROM semantic_preferences
                WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub),0)
        WHERE NOT EXISTS(SELECT 1 FROM semantic_compatible_embeddings c WHERE c.message_id=NEW.id);
    INSERT INTO embedding_owner_schedule(owner_iss,owner_sub)
        SELECT NEW.owner_iss,NEW.owner_sub
        WHERE EXISTS(SELECT 1 FROM embedding_work w WHERE w.message_id=NEW.id)
        AND NOT EXISTS(SELECT 1 FROM embedding_owner_schedule o
            WHERE o.owner_iss=NEW.owner_iss AND o.owner_sub=NEW.owner_sub);
END;

DROP TRIGGER semantic_preferences_insert;
CREATE TRIGGER semantic_preferences_insert AFTER INSERT ON semantic_preferences BEGIN
    UPDATE embedding_work SET lease_until=0,lease_token=NULL,consent_lease_token=NULL,
        consent_generation=NEW.generation
        WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub;
    DELETE FROM embedding_work WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub
        AND EXISTS(SELECT 1 FROM semantic_compatible_embeddings c WHERE c.message_id=embedding_work.message_id);
    INSERT INTO embedding_work(message_id,owner_iss,owner_sub,received_at,consent_generation)
        SELECT id,owner_iss,owner_sub,received_at,NEW.generation FROM messages
        WHERE NEW.enabled=1 AND owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub
        AND deleted_at IS NULL
        AND NOT EXISTS(SELECT 1 FROM semantic_compatible_embeddings c WHERE c.message_id=messages.id)
        AND NOT EXISTS(SELECT 1 FROM embedding_work w WHERE w.message_id=messages.id)
        AND NOT EXISTS(SELECT 1 FROM addresses a WHERE a.address=messages.address AND a.kind='tmpaddr'
            AND (a.generation!=messages.mailbox_generation OR a.released_at IS NOT NULL
                OR a.expires_at<=CAST(unixepoch('subsec')*1000 AS INTEGER) OR a.state!='active'));
    INSERT INTO embedding_owner_schedule(owner_iss,owner_sub)
        SELECT NEW.owner_iss,NEW.owner_sub WHERE NEW.enabled=1
        AND EXISTS(SELECT 1 FROM embedding_work w
            WHERE w.owner_iss=NEW.owner_iss AND w.owner_sub=NEW.owner_sub)
        AND NOT EXISTS(SELECT 1 FROM embedding_owner_schedule o
            WHERE o.owner_iss=NEW.owner_iss AND o.owner_sub=NEW.owner_sub);
    INSERT INTO search_generations(owner_iss,owner_sub,generation)
        SELECT NEW.owner_iss,NEW.owner_sub,1 WHERE NEW.enabled=1
        ON CONFLICT(owner_iss,owner_sub) DO UPDATE SET generation=generation+1;
END;

DROP TRIGGER semantic_preferences_transition;
CREATE TRIGGER semantic_preferences_transition AFTER UPDATE OF enabled ON semantic_preferences
WHEN OLD.enabled!=NEW.enabled BEGIN
    UPDATE embedding_work SET lease_until=0,lease_token=NULL,consent_lease_token=NULL,
        consent_generation=NEW.generation
        WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub;
    DELETE FROM embedding_work WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub
        AND EXISTS(SELECT 1 FROM semantic_compatible_embeddings c WHERE c.message_id=embedding_work.message_id);
    INSERT INTO embedding_work(message_id,owner_iss,owner_sub,received_at,consent_generation)
        SELECT id,owner_iss,owner_sub,received_at,NEW.generation FROM messages
        WHERE NEW.enabled=1 AND owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub
        AND deleted_at IS NULL
        AND NOT EXISTS(SELECT 1 FROM semantic_compatible_embeddings c WHERE c.message_id=messages.id)
        AND NOT EXISTS(SELECT 1 FROM embedding_work w WHERE w.message_id=messages.id)
        AND NOT EXISTS(SELECT 1 FROM addresses a WHERE a.address=messages.address AND a.kind='tmpaddr'
            AND (a.generation!=messages.mailbox_generation OR a.released_at IS NOT NULL
                OR a.expires_at<=CAST(unixepoch('subsec')*1000 AS INTEGER) OR a.state!='active'));
    INSERT INTO embedding_owner_schedule(owner_iss,owner_sub)
        SELECT NEW.owner_iss,NEW.owner_sub WHERE NEW.enabled=1
        AND EXISTS(SELECT 1 FROM embedding_work w
            WHERE w.owner_iss=NEW.owner_iss AND w.owner_sub=NEW.owner_sub)
        AND NOT EXISTS(SELECT 1 FROM embedding_owner_schedule o
            WHERE o.owner_iss=NEW.owner_iss AND o.owner_sub=NEW.owner_sub);
    INSERT INTO search_generations(owner_iss,owner_sub,generation)
        VALUES(NEW.owner_iss,NEW.owner_sub,1)
        ON CONFLICT(owner_iss,owner_sub) DO UPDATE SET generation=generation+1;
END;
