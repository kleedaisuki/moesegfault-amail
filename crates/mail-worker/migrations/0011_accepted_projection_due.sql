-- Retry authority belongs to the send journal, never to an isolate's memory.
-- Existing accepted rows start due immediately; provider acceptance is unchanged.
ALTER TABLE send_requests ADD COLUMN index_next_attempt_at INTEGER NOT NULL DEFAULT 0;
-- Every finite failed/poison turn moves behind still-unattempted accepted work.
CREATE INDEX send_requests_index_due
ON send_requests(state,index_next_attempt_at,created_at,message_id)
WHERE state='accepted' AND message_id IS NOT NULL AND provider_id IS NOT NULL;
