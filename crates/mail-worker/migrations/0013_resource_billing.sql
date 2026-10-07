-- v0.2.0 resource accounting: integer CNY micros, decimal bytes, UTC calendar months.
-- Existing ownership, messages and provider journals are never rewritten.
CREATE TABLE resource_accounts (
 owner_iss TEXT NOT NULL, owner_sub TEXT NOT NULL,
 plan TEXT NOT NULL DEFAULT 'free' CHECK(plan IN ('free','lite','plus')),
 included_outbound INTEGER NOT NULL DEFAULT 100,
 included_storage_bytes INTEGER NOT NULL DEFAULT 200000000,
 included_addresses INTEGER NOT NULL DEFAULT 1,
 grandfathered_addresses INTEGER NOT NULL DEFAULT 0,
 billing_owner_id TEXT,
 authorization_id TEXT,
 overage_budget_micros INTEGER NOT NULL DEFAULT 0 CHECK(overage_budget_micros>=0),
 valid_until INTEGER,
 authority_updated_at INTEGER NOT NULL DEFAULT 0,
 accounting_tick INTEGER NOT NULL DEFAULT (unixepoch()),
 PRIMARY KEY(owner_iss,owner_sub)
);
CREATE TABLE resource_periods (
 owner_iss TEXT NOT NULL,owner_sub TEXT NOT NULL,
 period_start INTEGER NOT NULL,period_end INTEGER NOT NULL CHECK(period_end>period_start),
 included_outbound INTEGER NOT NULL DEFAULT 100,
 entitlement_outbound INTEGER NOT NULL DEFAULT 100,
 outbound_reserved INTEGER NOT NULL DEFAULT 0 CHECK(outbound_reserved>=0),
 outbound_accepted INTEGER NOT NULL DEFAULT 0 CHECK(outbound_accepted>=0),
 accrued_micros INTEGER NOT NULL DEFAULT 0 CHECK(accrued_micros>=0),
 storage_fraction REAL NOT NULL DEFAULT 0,
 address_fraction REAL NOT NULL DEFAULT 0,
 accounted_at INTEGER NOT NULL,
 PRIMARY KEY(owner_iss,owner_sub,period_start)
);
CREATE TABLE resource_send_reservations (
 owner_iss TEXT NOT NULL,owner_sub TEXT NOT NULL,idem_key TEXT NOT NULL,
 period_start INTEGER NOT NULL,units INTEGER NOT NULL CHECK(units>0),
 authorization_id TEXT,
 authorized_at INTEGER NOT NULL DEFAULT (unixepoch()),
 state TEXT NOT NULL DEFAULT 'reserved' CHECK(state IN ('reserved','accepted','released')),
 PRIMARY KEY(owner_iss,owner_sub,idem_key)
);
CREATE TABLE resource_outbox (
 event_id TEXT PRIMARY KEY,
 owner_iss TEXT NOT NULL,owner_sub TEXT NOT NULL,billing_owner_id TEXT NOT NULL,authorization_id TEXT,
 period_start INTEGER NOT NULL,period_end INTEGER NOT NULL,
 meter TEXT NOT NULL CHECK(meter IN ('outbound_recipients','storage_byte_seconds','address_seconds')),
 quantity INTEGER NOT NULL CHECK(quantity>0),amount_micros INTEGER NOT NULL CHECK(amount_micros>=0),
 authorized_at INTEGER NOT NULL,occurred_at INTEGER NOT NULL,delivered_at INTEGER
);
CREATE INDEX resource_outbox_pending ON resource_outbox(delivered_at,occurred_at);
-- The grandfather floor protects every previously registered non-retired address.
INSERT INTO resource_accounts(owner_iss,owner_sub,grandfathered_addresses)
 SELECT owner_iss,owner_sub,COUNT(*) FROM addresses WHERE state!='retired' GROUP BY owner_iss,owner_sub;
INSERT OR IGNORE INTO resource_accounts(owner_iss,owner_sub)
 SELECT owner_iss,owner_sub FROM messages GROUP BY owner_iss,owner_sub;
INSERT OR IGNORE INTO resource_accounts(owner_iss,owner_sub)
 SELECT owner_iss,owner_sub FROM send_requests GROUP BY owner_iss,owner_sub;
INSERT INTO resource_periods(owner_iss,owner_sub,period_start,period_end,accounted_at)
 SELECT owner_iss,owner_sub,unixepoch('now','start of month'),unixepoch('now','start of month','+1 month'),unixepoch() FROM resource_accounts;
-- All unresolved requests retain their provider journal. Pre-v0.2 sends are not retroactively billed.
CREATE VIEW resource_current AS
 SELECT a.owner_iss,a.owner_sub,a.plan,p.included_outbound,a.included_storage_bytes,a.included_addresses,a.grandfathered_addresses,a.billing_owner_id,a.authorization_id,a.overage_budget_micros,a.valid_until,a.authority_updated_at,a.accounting_tick,p.period_start,p.period_end,p.outbound_reserved,p.outbound_accepted,p.accrued_micros,p.accounted_at,p.storage_fraction,p.address_fraction,
 COALESCE((SELECT used_bytes FROM storage_usage s WHERE s.owner_iss=a.owner_iss AND s.owner_sub=a.owner_sub),0) AS storage_bytes,
 (SELECT COUNT(*) FROM addresses d WHERE d.owner_iss=a.owner_iss AND d.owner_sub=a.owner_sub AND d.state!='retired') AS address_count,
 COALESCE((SELECT SUM((MAX(0,q.outbound_accepted+q.outbound_reserved-q.included_outbound)-MAX(0,q.outbound_accepted-q.included_outbound))*5000) FROM resource_periods q WHERE q.owner_iss=a.owner_iss AND q.owner_sub=a.owner_sub),0) AS reserved_micros
 FROM resource_accounts a JOIN resource_periods p USING(owner_iss,owner_sub)
 WHERE p.period_start<=unixepoch() AND p.period_end>unixepoch();
-- Accrue against the old stock before any mutation; SQLite writers serialize each trigger transaction.
CREATE VIEW resource_accrual AS
 SELECT a.owner_iss,a.owner_sub,a.billing_owner_id,a.authorization_id,p.period_start,p.period_end,p.accounted_at,
 MIN(MAX(a.accounting_tick,p.accounted_at),p.period_end,COALESCE(MAX(a.valid_until,p.accounted_at),p.period_end)) AS tick,
 MAX(0,COALESCE((SELECT used_bytes FROM storage_usage s WHERE s.owner_iss=a.owner_iss AND s.owner_sub=a.owner_sub),0)-a.included_storage_bytes)*(MIN(MAX(a.accounting_tick,p.accounted_at),p.period_end,COALESCE(MAX(a.valid_until,p.accounted_at),p.period_end))-p.accounted_at) AS storage_quantity,
 MAX(0,(SELECT COUNT(*) FROM addresses d WHERE d.owner_iss=a.owner_iss AND d.owner_sub=a.owner_sub AND d.state!='retired')-MAX(a.included_addresses,a.grandfathered_addresses))*(MIN(MAX(a.accounting_tick,p.accounted_at),p.period_end,COALESCE(MAX(a.valid_until,p.accounted_at),p.period_end))-p.accounted_at) AS address_quantity,
 p.storage_fraction,p.address_fraction,a.overage_budget_micros,
 MAX(0,a.overage_budget_micros-p.accrued_micros-COALESCE((SELECT SUM((MAX(0,q.outbound_accepted+q.outbound_reserved-q.included_outbound)-MAX(0,q.outbound_accepted-q.included_outbound))*5000) FROM resource_periods q WHERE q.owner_iss=a.owner_iss AND q.owner_sub=a.owner_sub),0)) AS budget_room
 FROM resource_accounts a JOIN resource_periods p USING(owner_iss,owner_sub)
 WHERE p.accounted_at<p.period_end AND a.accounting_tick>p.accounted_at;
CREATE VIEW resource_accrual_amounts AS
 SELECT *,MIN(budget_room,CAST(storage_fraction+storage_quantity*0.001/(period_end-period_start) AS INTEGER)) AS storage_amount,
 MIN(MAX(0,budget_room-CAST(storage_fraction+storage_quantity*0.001/(period_end-period_start) AS INTEGER)),CAST(address_fraction+address_quantity*3000000.0/(period_end-period_start) AS INTEGER)) AS address_amount
 FROM resource_accrual;
CREATE TRIGGER resource_account_tick AFTER UPDATE OF accounting_tick ON resource_accounts BEGIN
 INSERT INTO resource_outbox(event_id,owner_iss,owner_sub,billing_owner_id,authorization_id,period_start,period_end,meter,quantity,amount_micros,authorized_at,occurred_at)
 SELECT 'storage:'||lower(hex(randomblob(16))),owner_iss,owner_sub,billing_owner_id,authorization_id,period_start,period_end,'storage_byte_seconds',storage_quantity,
 storage_amount,accounted_at,tick
 FROM resource_accrual_amounts WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub AND storage_quantity>0 AND storage_amount>0 AND overage_budget_micros>0 AND billing_owner_id IS NOT NULL AND authorization_id IS NOT NULL;
 INSERT INTO resource_outbox(event_id,owner_iss,owner_sub,billing_owner_id,authorization_id,period_start,period_end,meter,quantity,amount_micros,authorized_at,occurred_at)
 SELECT 'address:'||lower(hex(randomblob(16))),owner_iss,owner_sub,billing_owner_id,authorization_id,period_start,period_end,'address_seconds',address_quantity,
 address_amount,accounted_at,tick
 FROM resource_accrual_amounts WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub AND address_quantity>0 AND address_amount>0 AND overage_budget_micros>0 AND billing_owner_id IS NOT NULL AND authorization_id IS NOT NULL;
 UPDATE resource_periods SET
 accrued_micros=accrued_micros+COALESCE((SELECT storage_amount+address_amount FROM resource_accrual_amounts x WHERE x.owner_iss=resource_periods.owner_iss AND x.owner_sub=resource_periods.owner_sub AND x.period_start=resource_periods.period_start AND x.overage_budget_micros>0 AND x.billing_owner_id IS NOT NULL AND x.authorization_id IS NOT NULL),0),
 storage_fraction=COALESCE((SELECT (CASE WHEN overage_budget_micros>0 AND billing_owner_id IS NOT NULL AND authorization_id IS NOT NULL AND storage_amount=CAST(storage_fraction+storage_quantity*0.001/(period_end-period_start) AS INTEGER) THEN storage_fraction+storage_quantity*0.001/(period_end-period_start)-CAST(storage_fraction+storage_quantity*0.001/(period_end-period_start) AS INTEGER) ELSE 0 END) FROM resource_accrual_amounts x WHERE x.owner_iss=resource_periods.owner_iss AND x.owner_sub=resource_periods.owner_sub AND x.period_start=resource_periods.period_start),storage_fraction),
 address_fraction=COALESCE((SELECT (CASE WHEN overage_budget_micros>0 AND billing_owner_id IS NOT NULL AND authorization_id IS NOT NULL AND address_amount=CAST(address_fraction+address_quantity*3000000.0/(period_end-period_start) AS INTEGER) THEN address_fraction+address_quantity*3000000.0/(period_end-period_start)-CAST(address_fraction+address_quantity*3000000.0/(period_end-period_start) AS INTEGER) ELSE 0 END) FROM resource_accrual_amounts x WHERE x.owner_iss=resource_periods.owner_iss AND x.owner_sub=resource_periods.owner_sub AND x.period_start=resource_periods.period_start),address_fraction),
 accounted_at=MIN(MAX(NEW.accounting_tick,accounted_at),period_end)
 WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub AND accounted_at<period_end;
END;
-- Reserve full remaining-period stock cost, not merely the first byte's instantaneous fee.
-- This prevents a new stock allocation from immediately exhausting a human's spending limit.
CREATE VIEW resource_headroom AS
 SELECT *,accrued_micros+reserved_micros+
 MAX(0,storage_bytes-included_storage_bytes)*0.001*(period_end-unixepoch())/(period_end-period_start)+
 MAX(0,address_count-MAX(included_addresses,grandfathered_addresses))*3000000.0*(period_end-unixepoch())/(period_end-period_start) AS committed_micros
 FROM resource_current;
DROP TRIGGER storage_reservations_guard;
CREATE TRIGGER storage_reservations_guard BEFORE INSERT ON storage_reservations
 WHEN NOT EXISTS(SELECT 1 FROM storage_reservations WHERE id=NEW.id) BEGIN
 UPDATE resource_accounts SET accounting_tick=unixepoch() WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub;
 SELECT (CASE WHEN NOT EXISTS(SELECT 1 FROM resource_current WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub) THEN RAISE(ABORT,'resource_account_missing') END);
 SELECT (CASE WHEN EXISTS(SELECT 1 FROM resource_headroom WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub AND storage_bytes+NEW.bytes>included_storage_bytes AND
 (overage_budget_micros=0 OR billing_owner_id IS NULL OR authorization_id IS NULL OR committed_micros+(MAX(0,storage_bytes+NEW.bytes-included_storage_bytes)-MAX(0,storage_bytes-included_storage_bytes))*0.001*(period_end-unixepoch())/(period_end-period_start)>overage_budget_micros)) THEN RAISE(ABORT,'mailbox_full') END);
END;
CREATE TRIGGER resource_storage_release BEFORE DELETE ON storage_reservations BEGIN
 UPDATE resource_accounts SET accounting_tick=unixepoch() WHERE owner_iss=OLD.owner_iss AND owner_sub=OLD.owner_sub;
END;
CREATE TRIGGER resource_address_admit BEFORE INSERT ON addresses WHEN NEW.state!='retired' BEGIN
 UPDATE resource_accounts SET accounting_tick=unixepoch() WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub;
 SELECT (CASE WHEN (SELECT COUNT(*) FROM addresses WHERE state!='retired')>=198 THEN RAISE(ABORT,'capacity_exhausted') END);
 SELECT (CASE WHEN NOT EXISTS(SELECT 1 FROM resource_current WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub) THEN RAISE(ABORT,'resource_account_missing') END);
 SELECT (CASE WHEN EXISTS(SELECT 1 FROM resource_headroom WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub AND address_count>=MAX(included_addresses,grandfathered_addresses) AND
 (overage_budget_micros=0 OR billing_owner_id IS NULL OR authorization_id IS NULL OR committed_micros+3000000.0*(period_end-unixepoch())/(period_end-period_start)>overage_budget_micros)) THEN RAISE(ABORT,'address_limit') END);
END;
CREATE TRIGGER resource_address_retire BEFORE UPDATE OF state ON addresses WHEN OLD.state!='retired' AND NEW.state='retired' BEGIN
 UPDATE resource_accounts SET accounting_tick=unixepoch() WHERE owner_iss=OLD.owner_iss AND owner_sub=OLD.owner_sub;
END;
CREATE TRIGGER resource_address_delete BEFORE DELETE ON addresses BEGIN
 UPDATE resource_accounts SET accounting_tick=unixepoch() WHERE owner_iss=OLD.owner_iss AND owner_sub=OLD.owner_sub;
END;
CREATE TRIGGER resource_send_admit BEFORE INSERT ON resource_send_reservations BEGIN
 UPDATE resource_accounts SET accounting_tick=unixepoch() WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub;
 SELECT (CASE WHEN NOT EXISTS(SELECT 1 FROM resource_current WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub AND period_start=NEW.period_start) THEN RAISE(ABORT,'resource_account_missing') END);
 SELECT (CASE WHEN EXISTS(SELECT 1 FROM resource_headroom WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub AND
 (MAX(0,outbound_accepted+outbound_reserved+NEW.units-included_outbound)-MAX(0,outbound_accepted+outbound_reserved-included_outbound))*5000>0 AND
 (billing_owner_id IS NULL OR authorization_id IS NULL OR overage_budget_micros=0 OR committed_micros+(MAX(0,outbound_accepted+outbound_reserved+NEW.units-included_outbound)-MAX(0,outbound_accepted+outbound_reserved-included_outbound))*5000>overage_budget_micros)) THEN RAISE(ABORT,'outbound_quota_exhausted') END);
END;
CREATE TRIGGER resource_send_reserved AFTER INSERT ON resource_send_reservations BEGIN
 UPDATE resource_periods SET outbound_reserved=outbound_reserved+NEW.units WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub AND period_start=NEW.period_start;
END;
CREATE TRIGGER resource_send_finish AFTER UPDATE OF state ON resource_send_reservations WHEN OLD.state='reserved' AND NEW.state!='reserved' BEGIN
 INSERT INTO resource_outbox(event_id,owner_iss,owner_sub,billing_owner_id,authorization_id,period_start,period_end,meter,quantity,amount_micros,authorized_at,occurred_at)
 SELECT 'send:'||NEW.idem_key||':'||a.billing_owner_id,a.owner_iss,a.owner_sub,a.billing_owner_id,NEW.authorization_id,p.period_start,p.period_end,'outbound_recipients',
 MAX(0,p.outbound_accepted+NEW.units-p.included_outbound)-MAX(0,p.outbound_accepted-p.included_outbound),
 (MAX(0,p.outbound_accepted+NEW.units-p.included_outbound)-MAX(0,p.outbound_accepted-p.included_outbound))*5000,NEW.authorized_at,unixepoch()
 FROM resource_accounts a JOIN resource_periods p USING(owner_iss,owner_sub)
 WHERE a.owner_iss=NEW.owner_iss AND a.owner_sub=NEW.owner_sub AND p.period_start=NEW.period_start AND NEW.state='accepted' AND a.billing_owner_id IS NOT NULL AND MAX(0,p.outbound_accepted+NEW.units-p.included_outbound)>MAX(0,p.outbound_accepted-p.included_outbound);
 UPDATE resource_periods SET
 accrued_micros=accrued_micros+(CASE WHEN NEW.state='accepted' THEN (MAX(0,outbound_accepted+NEW.units-included_outbound)-MAX(0,outbound_accepted-included_outbound))*5000 ELSE 0 END),
 outbound_accepted=outbound_accepted+(CASE WHEN NEW.state='accepted' THEN NEW.units ELSE 0 END),outbound_reserved=outbound_reserved-NEW.units
 WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub AND period_start=NEW.period_start;
END;
-- Provider-positive acceptance atomically commits accounting with its durable journal.
CREATE TRIGGER resource_provider_accept AFTER UPDATE OF state ON send_requests WHEN NEW.state IN ('accepted','sent') BEGIN
 UPDATE resource_send_reservations SET state='accepted' WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub AND idem_key=NEW.idem_key AND state='reserved';
END;
CREATE TRIGGER resource_provider_reject AFTER UPDATE OF state ON send_requests WHEN NEW.state='rejected' BEGIN
 UPDATE resource_send_reservations SET state='released' WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub AND idem_key=NEW.idem_key AND state='reserved';
END;
CREATE TRIGGER resource_send_delete BEFORE DELETE ON send_requests WHEN OLD.state IN ('preparing','reserving','rejected') BEGIN
 UPDATE resource_send_reservations SET state='released' WHERE owner_iss=OLD.owner_iss AND owner_sub=OLD.owner_sub AND idem_key=OLD.idem_key AND state='reserved';
END;

-- Only never-submitted reservations may be removed by the application; their monthly hold is released.
CREATE TRIGGER resource_send_unreserve AFTER DELETE ON resource_send_reservations WHEN OLD.state='reserved' BEGIN
 UPDATE resource_periods SET outbound_reserved=outbound_reserved-OLD.units WHERE owner_iss=OLD.owner_iss AND owner_sub=OLD.owner_sub AND period_start=OLD.period_start;
END;
