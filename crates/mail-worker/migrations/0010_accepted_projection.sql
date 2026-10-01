-- Accepted projections are unpublished until their journal atomically reaches sent.
-- Keep lookup nonunique to avoid invalidating legacy journals during migration.
CREATE INDEX send_requests_message_state ON send_requests(message_id,state);

-- A 20-minute projection lease is a finite retry window, not an HTTP lifetime cap.
-- Every chunk/finalization checks the opaque token; an older writer cannot
-- publish after another projector claims the accepted journal, even if still alive.
ALTER TABLE send_requests ADD COLUMN index_projection_token TEXT;
ALTER TABLE send_requests ADD COLUMN index_projection_lease_until INTEGER NOT NULL DEFAULT 0;

-- Repairing a legacy accepted body invalidates its former semantic projection.
-- Recreate work in the publication transaction, revoking any old embedding
-- lease so a response already in flight cannot commit a stale vector later.
-- New messages still use migration 0007's INSERT trigger; tombstones stay empty.
CREATE TRIGGER messages_outbound_projection_requeue AFTER UPDATE OF body_text ON messages
WHEN NEW.deleted_at IS NULL AND NEW.direction='outbound'
    AND EXISTS (SELECT 1 FROM send_requests s WHERE s.message_id=NEW.id
        AND s.owner_iss=NEW.owner_iss AND s.owner_sub=NEW.owner_sub AND s.state='accepted')
BEGIN
    DELETE FROM embedding_work WHERE message_id=NEW.id;
    INSERT OR IGNORE INTO embedding_owner_schedule(owner_iss,owner_sub)
    VALUES(NEW.owner_iss,NEW.owner_sub);
    INSERT INTO embedding_work(message_id,owner_iss,owner_sub,received_at)
    VALUES(NEW.id,NEW.owner_iss,NEW.owner_sub,NEW.received_at);
END;
