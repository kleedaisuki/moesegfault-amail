-- Accepted projections are unpublished until their journal atomically reaches sent.
-- Keep lookup nonunique to avoid invalidating legacy journals during migration.
CREATE INDEX send_requests_message_state ON send_requests(message_id,state);

-- A 20-minute projection lease outlives the platform's 15-minute invocation.
-- Every chunk/finalization checks the opaque token; an expired writer cannot
-- publish after another projector claims the accepted journal.
ALTER TABLE send_requests ADD COLUMN index_projection_token TEXT;
ALTER TABLE send_requests ADD COLUMN index_projection_lease_until INTEGER NOT NULL DEFAULT 0;
