-- Temporary mailbox names may be reused only after route retirement and complete purge.
ALTER TABLE addresses ADD COLUMN kind TEXT NOT NULL DEFAULT 'mail' CHECK(kind IN ('mail','tmpaddr'));
ALTER TABLE addresses ADD COLUMN generation TEXT NOT NULL DEFAULT '';
ALTER TABLE addresses ADD COLUMN expires_at INTEGER;
ALTER TABLE addresses ADD COLUMN released_at INTEGER;
ALTER TABLE addresses ADD COLUMN cooldown_until INTEGER;
ALTER TABLE addresses ADD COLUMN purged_at INTEGER;
ALTER TABLE messages ADD COLUMN mailbox_generation TEXT NOT NULL DEFAULT '';
ALTER TABLE send_requests ADD COLUMN mailbox_generation TEXT NOT NULL DEFAULT '';
ALTER TABLE send_requests ADD COLUMN content_purged_at INTEGER;
DROP INDEX addresses_active_slot;
CREATE UNIQUE INDEX addresses_active_slot ON addresses(owner_iss,owner_sub,kind,slot) WHERE state!='retired';
CREATE INDEX addresses_temporary_due ON addresses(expires_at,address) WHERE kind='tmpaddr' AND released_at IS NULL;
CREATE INDEX messages_mailbox_generation ON messages(address,mailbox_generation,id);
CREATE TRIGGER tmpaddr_lifetime_insert BEFORE INSERT ON addresses WHEN NEW.kind='tmpaddr' BEGIN
 SELECT RAISE(ABORT,'tmpaddr_lifetime_invalid') WHERE length(NEW.generation)!=36 OR NEW.expires_at IS NULL OR NEW.expires_at<=NEW.created_at OR NEW.expires_at>NEW.created_at+21600000;
END;
CREATE TRIGGER tmpaddr_lifetime_immutable BEFORE UPDATE OF generation,kind,expires_at ON addresses BEGIN
 SELECT RAISE(ABORT,'mailbox_lifetime_immutable') WHERE OLD.generation!=NEW.generation OR OLD.kind!=NEW.kind OR OLD.expires_at IS NOT NEW.expires_at;
END;
CREATE TRIGGER tmpaddr_message_fence BEFORE INSERT ON messages
 WHEN NEW.mailbox_generation!='' OR EXISTS(SELECT 1 FROM addresses WHERE address=NEW.address AND kind='tmpaddr') BEGIN
 SELECT RAISE(ABORT,'mailbox_generation_expired') WHERE NOT EXISTS(
 SELECT 1 FROM addresses a WHERE a.address=NEW.address AND a.kind='tmpaddr' AND a.owner_iss=NEW.owner_iss AND a.owner_sub=NEW.owner_sub
 AND a.state='active' AND a.released_at IS NULL AND a.expires_at>CAST(unixepoch('subsec')*1000 AS INTEGER) AND a.generation=NEW.mailbox_generation);
END;
CREATE TRIGGER tmpaddr_release AFTER UPDATE OF state ON addresses
 WHEN NEW.kind='tmpaddr' AND NEW.state IN ('deleting','retired') AND OLD.released_at IS NULL BEGIN
 UPDATE addresses SET released_at=MIN(CAST(unixepoch('subsec')*1000 AS INTEGER),expires_at),cooldown_until=MIN(CAST(unixepoch('subsec')*1000 AS INTEGER),expires_at)+3600000 WHERE address=NEW.address AND generation=NEW.generation;
 UPDATE messages SET deleted_at=COALESCE(deleted_at,CAST(unixepoch('subsec')*1000 AS INTEGER)),body_text='',subject='',metadata_json='{}',recipients_json='[]',embedding_json=NULL WHERE address=NEW.address AND mailbox_generation=NEW.generation;
 UPDATE search_jobs SET state='stale',request_json='{}',state_json='{}',version=version+1,lease_started_at=NULL WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub;
END;
CREATE TRIGGER tmpaddr_release_cleanup AFTER DELETE ON messages
 WHEN OLD.mailbox_generation!='' BEGIN
 DELETE FROM provider_events WHERE local_message_id=OLD.id;
 DELETE FROM recipient_outcomes WHERE local_message_id=OLD.id;
 DELETE FROM message_text_chunks WHERE message_id=OLD.id;
END;

DROP VIEW resource_current;
CREATE VIEW resource_current AS
 SELECT a.owner_iss,a.owner_sub,a.currency,a.plan,p.included_outbound,a.included_storage_bytes,a.included_addresses,a.grandfathered_addresses,a.billing_owner_id,a.authorization_id,a.origin_traceparent,a.overage_budget_micros,a.valid_until,a.authority_updated_at,a.accounting_tick,p.period_start,p.period_end,p.outbound_reserved,p.outbound_accepted,p.accrued_micros,p.accounted_at,p.storage_fraction,p.address_fraction,
 COALESCE((SELECT used_bytes FROM storage_usage s WHERE s.owner_iss=a.owner_iss AND s.owner_sub=a.owner_sub),0) AS storage_bytes,
 (SELECT COUNT(*) FROM addresses d WHERE d.owner_iss=a.owner_iss AND d.owner_sub=a.owner_sub AND d.state!='retired' AND d.kind='mail') AS address_count,
 COALESCE((SELECT SUM((MAX(0,q.outbound_accepted+q.outbound_reserved-q.included_outbound)-MAX(0,q.outbound_accepted-q.included_outbound))*1000) FROM resource_periods q WHERE q.owner_iss=a.owner_iss AND q.owner_sub=a.owner_sub),0) AS reserved_micros
 FROM resource_accounts a JOIN resource_periods p USING(owner_iss,owner_sub)
 WHERE p.period_start<=unixepoch() AND p.period_end>unixepoch();

DROP VIEW resource_accrual;
CREATE VIEW resource_accrual AS
 SELECT a.owner_iss,a.owner_sub,a.billing_owner_id,a.authorization_id,a.origin_traceparent,p.period_start,p.period_end,p.accounted_at,
 MIN(MAX(a.accounting_tick,p.accounted_at),p.period_end,COALESCE(MAX(a.valid_until,p.accounted_at),p.period_end)) AS tick,
 MAX(0,COALESCE((SELECT used_bytes FROM storage_usage s WHERE s.owner_iss=a.owner_iss AND s.owner_sub=a.owner_sub),0)-a.included_storage_bytes)*(MIN(MAX(a.accounting_tick,p.accounted_at),p.period_end,COALESCE(MAX(a.valid_until,p.accounted_at),p.period_end))-p.accounted_at) AS storage_quantity,
 MAX(0,(SELECT COUNT(*) FROM addresses d WHERE d.owner_iss=a.owner_iss AND d.owner_sub=a.owner_sub AND d.state!='retired' AND d.kind='mail')-MAX(a.included_addresses,a.grandfathered_addresses))*(MIN(MAX(a.accounting_tick,p.accounted_at),p.period_end,COALESCE(MAX(a.valid_until,p.accounted_at),p.period_end))-p.accounted_at) AS address_quantity,
 p.storage_fraction,p.address_fraction,a.overage_budget_micros,
 MAX(0,a.overage_budget_micros-p.accrued_micros-COALESCE((SELECT SUM((MAX(0,q.outbound_accepted+q.outbound_reserved-q.included_outbound)-MAX(0,q.outbound_accepted-q.included_outbound))*1000) FROM resource_periods q WHERE q.owner_iss=a.owner_iss AND q.owner_sub=a.owner_sub),0)) AS budget_room
 FROM resource_accounts a JOIN resource_periods p USING(owner_iss,owner_sub)
 WHERE p.accounted_at<p.period_end AND a.accounting_tick>p.accounted_at;

DROP TRIGGER resource_address_admit;
CREATE TRIGGER resource_address_admit BEFORE INSERT ON addresses WHEN NEW.state!='retired' BEGIN
 UPDATE resource_accounts SET accounting_tick=unixepoch() WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub;
 SELECT (CASE WHEN (SELECT COUNT(*) FROM addresses WHERE state!='retired' AND kind=NEW.kind)>=198 THEN RAISE(ABORT,'capacity_exhausted') END);
 SELECT (CASE WHEN NOT EXISTS(SELECT 1 FROM resource_current WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub) THEN RAISE(ABORT,'resource_account_missing') END);
 SELECT (CASE WHEN NEW.kind='mail' AND EXISTS(SELECT 1 FROM resource_headroom WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub AND address_count>=MAX(included_addresses,grandfathered_addresses) AND
 (overage_budget_micros=0 OR billing_owner_id IS NULL OR authorization_id IS NULL OR committed_micros+500000.0*(period_end-unixepoch())/(period_end-period_start)>overage_budget_micros)) THEN RAISE(ABORT,'address_limit') END);
 SELECT RAISE(ABORT,'tmpaddr_limit') WHERE NEW.kind='tmpaddr' AND
 (SELECT COUNT(*) FROM addresses d WHERE d.owner_iss=NEW.owner_iss AND d.owner_sub=NEW.owner_sub AND d.kind='tmpaddr' AND d.state!='retired') >=
 (SELECT CASE plan WHEN 'plus' THEN 10 WHEN 'lite' THEN 6 ELSE 3 END FROM resource_accounts WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub);
END;
ALTER TABLE send_requests ADD COLUMN mailbox_address TEXT;
CREATE INDEX send_requests_tmpaddr_cleanup ON send_requests(mailbox_address,mailbox_generation,content_purged_at);
CREATE TRIGGER tmpaddr_send_purge_fence BEFORE UPDATE OF sender,envelope_json ON send_requests
 WHEN OLD.content_purged_at IS NOT NULL AND (NEW.sender IS NOT NULL OR NEW.envelope_json IS NOT NULL) BEGIN
 SELECT RAISE(ABORT,'mailbox_generation_expired');
END;
CREATE TRIGGER tmpaddr_retired_delete BEFORE DELETE ON addresses WHEN OLD.kind='tmpaddr' BEGIN
 SELECT RAISE(ABORT,'tmpaddr_reuse_not_ready') WHERE OLD.state!='retired' OR OLD.cf_rule_id IS NOT NULL OR OLD.needs_reconcile!=0 OR OLD.purged_at IS NULL OR OLD.cooldown_until IS NULL OR OLD.cooldown_until>CAST(unixepoch('subsec')*1000 AS INTEGER)
 OR EXISTS(SELECT 1 FROM messages m WHERE m.address=OLD.address)
 OR EXISTS(SELECT 1 FROM send_requests s WHERE s.mailbox_address=OLD.address AND s.mailbox_generation=OLD.generation AND s.content_purged_at IS NULL);
END;
ALTER TABLE storage_reservations ADD COLUMN mailbox_address TEXT;
ALTER TABLE storage_reservations ADD COLUMN mailbox_generation TEXT NOT NULL DEFAULT '';
ALTER TABLE storage_reservations ADD COLUMN tmpaddr_purged_at INTEGER;
CREATE INDEX storage_reservations_tmpaddr_cleanup ON storage_reservations(mailbox_address,mailbox_generation,tmpaddr_purged_at);
CREATE TRIGGER tmpaddr_purged_reservation_release AFTER UPDATE OF tmpaddr_purged_at ON storage_reservations
 WHEN OLD.tmpaddr_purged_at IS NULL AND NEW.tmpaddr_purged_at IS NOT NULL AND NEW.mailbox_generation!='' BEGIN
 UPDATE resource_accounts SET accounting_tick=unixepoch() WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub;
 UPDATE storage_usage SET used_bytes=used_bytes-NEW.bytes WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub;
 UPDATE storage_reservations SET bytes=0 WHERE id=NEW.id;
END;
CREATE TRIGGER tmpaddr_retired_storage_guard BEFORE DELETE ON addresses WHEN OLD.kind='tmpaddr' BEGIN
 SELECT RAISE(ABORT,'tmpaddr_reuse_not_ready') WHERE EXISTS(SELECT 1 FROM storage_reservations r WHERE r.mailbox_address=OLD.address AND r.mailbox_generation=OLD.generation);
END;
