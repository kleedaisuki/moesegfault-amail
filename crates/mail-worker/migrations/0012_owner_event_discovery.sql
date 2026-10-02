-- Bounded owner journal reads need deterministic ties, with indexed kind/message
-- exploration. Preserve all event rows and existing lifecycle/retention behavior.
CREATE INDEX provider_events_owner_order
ON provider_events(owner_iss,owner_sub,received_at,event_id);
CREATE INDEX provider_events_owner_kind_order
ON provider_events(owner_iss,owner_sub,kind,received_at,event_id);
CREATE INDEX provider_events_owner_message_order
ON provider_events(owner_iss,owner_sub,local_message_id,received_at,event_id);
