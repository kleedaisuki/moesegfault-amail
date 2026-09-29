-- D1 is the authoritative automatic-indexing work ledger. No mail content is copied here.
-- Inserts cover inbound delivery and outbound reconciliation atomically with the message.
ALTER TABLE messages ADD COLUMN embedding_input_version INTEGER;
ALTER TABLE messages ADD COLUMN embedding_truncated INTEGER CHECK(embedding_truncated IN (0,1));
-- Preserve known-compatible vectors; malformed or unknown legacy projections
-- become missing work instead of permanently incompatible search rows.
UPDATE messages SET embedding_json=NULL,embedding_model=NULL,embedding_dimensions=NULL
WHERE embedding_json IS NOT NULL AND (
    COALESCE(embedding_model,'')!='qwen/qwen3-embedding-8b'
    OR COALESCE(embedding_dimensions,0)!=256
    OR CASE WHEN json_valid(embedding_json)=1 THEN
        CASE WHEN json_type(embedding_json)='array' AND json_array_length(embedding_json)=256
             THEN EXISTS (SELECT 1 FROM json_each(embedding_json)
                          WHERE type NOT IN ('integer','real') OR ABS(value)>1.0001)
             ELSE 1 END
       ELSE 1 END
);
-- Earlier document calls used the same UTF-8 prefix and configured model.
UPDATE messages SET embedding_input_version=1
WHERE embedding_json IS NOT NULL AND embedding_model='qwen/qwen3-embedding-8b' AND embedding_dimensions=256;

CREATE TABLE embedding_work (
    message_id TEXT PRIMARY KEY,
    owner_iss TEXT NOT NULL,
    owner_sub TEXT NOT NULL,
    received_at INTEGER NOT NULL,
    input_version INTEGER NOT NULL DEFAULT 1 CHECK(input_version = 1),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
    next_attempt_at INTEGER NOT NULL DEFAULT 0,
    lease_until INTEGER NOT NULL DEFAULT 0,
    lease_token TEXT,
    state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','quarantined')),
    last_error_code TEXT
);
CREATE INDEX embedding_work_due ON embedding_work(state,next_attempt_at,lease_until,received_at,message_id);
CREATE INDEX embedding_work_owner_due ON embedding_work(owner_iss,owner_sub,state,next_attempt_at,received_at,message_id);

-- Last-served order keeps a large backlog across 20+ accounts from hiding a
-- newly active account. Identity keys are not email addresses or content.
CREATE TABLE embedding_owner_schedule (
    owner_iss TEXT NOT NULL,
    owner_sub TEXT NOT NULL,
    last_served_at INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(owner_iss,owner_sub)
);

-- A shared circuit prevents a broken provider credential/route from burning one call per message.
CREATE TABLE embedding_dependency (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    blocked_until INTEGER NOT NULL DEFAULT 0,
    last_error_code TEXT
);
INSERT INTO embedding_dependency(id) VALUES(1);

CREATE TRIGGER messages_embedding_insert AFTER INSERT ON messages
WHEN NEW.deleted_at IS NULL AND NEW.embedding_json IS NULL BEGIN
    INSERT OR IGNORE INTO embedding_owner_schedule(owner_iss,owner_sub)
    VALUES(NEW.owner_iss,NEW.owner_sub);
    INSERT INTO embedding_work(message_id,owner_iss,owner_sub,received_at)
    VALUES(NEW.id,NEW.owner_iss,NEW.owner_sub,NEW.received_at);
END;

CREATE TRIGGER messages_embedding_finished AFTER UPDATE OF embedding_json,deleted_at ON messages
WHEN NEW.embedding_json IS NOT NULL OR NEW.deleted_at IS NOT NULL BEGIN
    DELETE FROM embedding_work WHERE message_id=NEW.id;
END;

CREATE TRIGGER messages_embedding_delete AFTER DELETE ON messages BEGIN
    DELETE FROM embedding_work WHERE message_id=OLD.id;
END;

CREATE TRIGGER embedding_work_owner_cleanup AFTER DELETE ON embedding_work BEGIN
    DELETE FROM embedding_owner_schedule
    WHERE owner_iss=OLD.owner_iss AND owner_sub=OLD.owner_sub
      AND NOT EXISTS (SELECT 1 FROM embedding_work WHERE owner_iss=OLD.owner_iss AND owner_sub=OLD.owner_sub);
END;

-- Existing valid vectors keep their representation; only missing vectors need transfer.
INSERT OR IGNORE INTO embedding_work(message_id,owner_iss,owner_sub,received_at)
SELECT id,owner_iss,owner_sub,received_at FROM messages
WHERE deleted_at IS NULL AND embedding_json IS NULL;
INSERT OR IGNORE INTO embedding_owner_schedule(owner_iss,owner_sub)
SELECT owner_iss,owner_sub FROM embedding_work GROUP BY owner_iss,owner_sub;
