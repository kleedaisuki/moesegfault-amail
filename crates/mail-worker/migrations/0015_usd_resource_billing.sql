-- Fixed USD tariff cutover, not currency conversion. D1 applies this migration atomically.
-- Refuse unresolved CNY liabilities rather than reinterpret historical money or consent.
CREATE TABLE resource_usd_cutover_guard (
 ready INTEGER NOT NULL CONSTRAINT resource_usd_cutover_requires_settled_cny CHECK(ready=1)
);
INSERT INTO resource_usd_cutover_guard(ready)
 SELECT CASE WHEN EXISTS(SELECT 1 FROM resource_accounts WHERE overage_budget_micros!=0)
 OR EXISTS(SELECT 1 FROM resource_outbox WHERE delivered_at IS NULL)
 OR EXISTS(SELECT 1 FROM resource_send_reservations WHERE state='reserved')
 THEN 0 ELSE 1 END;
DROP TABLE resource_usd_cutover_guard;
-- This immutable archive retains every historical period's denomination and fractional liability.
CREATE TABLE resource_legacy_cny_periods (
 owner_iss TEXT NOT NULL,owner_sub TEXT NOT NULL,period_start INTEGER NOT NULL,
 period_end INTEGER NOT NULL,currency TEXT NOT NULL DEFAULT 'CNY' CHECK(currency='CNY'),
 accrued_micros INTEGER NOT NULL,storage_fraction REAL NOT NULL,address_fraction REAL NOT NULL,
 accounted_at INTEGER NOT NULL,cutover_at INTEGER NOT NULL,
 PRIMARY KEY(owner_iss,owner_sub,period_start)
);
INSERT INTO resource_legacy_cny_periods
 SELECT owner_iss,owner_sub,period_start,period_end,'CNY',accrued_micros,
 storage_fraction,address_fraction,accounted_at,unixepoch() FROM resource_periods;
CREATE TRIGGER resource_legacy_cny_no_update BEFORE UPDATE ON resource_legacy_cny_periods BEGIN
 SELECT RAISE(ABORT,'legacy_currency_archive_immutable');
END;
CREATE TRIGGER resource_legacy_cny_no_delete BEFORE DELETE ON resource_legacy_cny_periods BEGIN
 SELECT RAISE(ABORT,'legacy_currency_archive_immutable');
END;
CREATE TRIGGER resource_legacy_cny_no_insert BEFORE INSERT ON resource_legacy_cny_periods BEGIN
 SELECT RAISE(ABORT,'legacy_currency_archive_immutable');
END;
ALTER TABLE resource_accounts ADD COLUMN currency TEXT NOT NULL DEFAULT 'USD' CHECK(currency='USD');
ALTER TABLE resource_outbox ADD COLUMN currency TEXT NOT NULL DEFAULT 'CNY' CHECK(currency IN ('CNY','USD'));
ALTER TABLE resource_send_reservations ADD COLUMN currency TEXT NOT NULL DEFAULT 'CNY' CHECK(currency IN ('CNY','USD'));
-- Do not reset quota counters, paid grants, grandfather floors, addresses, or provider journals.
-- No CNY consent or fractional carry grants USD spend. Start elapsed USD stock time now.
UPDATE resource_periods SET accrued_micros=0,storage_fraction=0,address_fraction=0,
 accounted_at=MIN(period_end,MAX(accounted_at,unixepoch()));
UPDATE resource_accounts SET authorization_id=NULL,origin_traceparent=NULL,overage_budget_micros=0;
DROP VIEW resource_current;
CREATE VIEW resource_current AS
 SELECT a.owner_iss,a.owner_sub,a.currency,a.plan,p.included_outbound,a.included_storage_bytes,a.included_addresses,a.grandfathered_addresses,a.billing_owner_id,a.authorization_id,a.origin_traceparent,a.overage_budget_micros,a.valid_until,a.authority_updated_at,a.accounting_tick,p.period_start,p.period_end,p.outbound_reserved,p.outbound_accepted,p.accrued_micros,p.accounted_at,p.storage_fraction,p.address_fraction,
 COALESCE((SELECT used_bytes FROM storage_usage s WHERE s.owner_iss=a.owner_iss AND s.owner_sub=a.owner_sub),0) AS storage_bytes,
 (SELECT COUNT(*) FROM addresses d WHERE d.owner_iss=a.owner_iss AND d.owner_sub=a.owner_sub AND d.state!='retired') AS address_count,
 COALESCE((SELECT SUM((MAX(0,q.outbound_accepted+q.outbound_reserved-q.included_outbound)-MAX(0,q.outbound_accepted-q.included_outbound))*1000) FROM resource_periods q WHERE q.owner_iss=a.owner_iss AND q.owner_sub=a.owner_sub),0) AS reserved_micros
 FROM resource_accounts a JOIN resource_periods p USING(owner_iss,owner_sub)
 WHERE p.period_start<=unixepoch() AND p.period_end>unixepoch();

DROP VIEW resource_accrual;
CREATE VIEW resource_accrual AS
 SELECT a.owner_iss,a.owner_sub,a.billing_owner_id,a.authorization_id,a.origin_traceparent,p.period_start,p.period_end,p.accounted_at,
 MIN(MAX(a.accounting_tick,p.accounted_at),p.period_end,COALESCE(MAX(a.valid_until,p.accounted_at),p.period_end)) AS tick,
 MAX(0,COALESCE((SELECT used_bytes FROM storage_usage s WHERE s.owner_iss=a.owner_iss AND s.owner_sub=a.owner_sub),0)-a.included_storage_bytes)*(MIN(MAX(a.accounting_tick,p.accounted_at),p.period_end,COALESCE(MAX(a.valid_until,p.accounted_at),p.period_end))-p.accounted_at) AS storage_quantity,
 MAX(0,(SELECT COUNT(*) FROM addresses d WHERE d.owner_iss=a.owner_iss AND d.owner_sub=a.owner_sub AND d.state!='retired')-MAX(a.included_addresses,a.grandfathered_addresses))*(MIN(MAX(a.accounting_tick,p.accounted_at),p.period_end,COALESCE(MAX(a.valid_until,p.accounted_at),p.period_end))-p.accounted_at) AS address_quantity,
 p.storage_fraction,p.address_fraction,a.overage_budget_micros,
 MAX(0,a.overage_budget_micros-p.accrued_micros-COALESCE((SELECT SUM((MAX(0,q.outbound_accepted+q.outbound_reserved-q.included_outbound)-MAX(0,q.outbound_accepted-q.included_outbound))*1000) FROM resource_periods q WHERE q.owner_iss=a.owner_iss AND q.owner_sub=a.owner_sub),0)) AS budget_room
 FROM resource_accounts a JOIN resource_periods p USING(owner_iss,owner_sub)
 WHERE p.accounted_at<p.period_end AND a.accounting_tick>p.accounted_at;

DROP VIEW resource_accrual_amounts;
CREATE VIEW resource_accrual_amounts AS
 SELECT *,MIN(budget_room,CAST(storage_fraction+storage_quantity*0.00015/(period_end-period_start) AS INTEGER)) AS storage_amount,
 MIN(MAX(0,budget_room-CAST(storage_fraction+storage_quantity*0.00015/(period_end-period_start) AS INTEGER)),CAST(address_fraction+address_quantity*500000.0/(period_end-period_start) AS INTEGER)) AS address_amount
 FROM resource_accrual;

DROP TRIGGER resource_account_tick;
CREATE TRIGGER resource_account_tick AFTER UPDATE OF accounting_tick ON resource_accounts BEGIN
 INSERT INTO resource_outbox(event_id,owner_iss,owner_sub,billing_owner_id,authorization_id,origin_traceparent,period_start,period_end,meter,quantity,amount_micros,authorized_at,occurred_at,currency)
 SELECT 'storage:'||lower(hex(randomblob(16))),owner_iss,owner_sub,billing_owner_id,authorization_id,origin_traceparent,period_start,period_end,'storage_byte_seconds',storage_quantity,
 storage_amount,accounted_at,tick,'USD'
 FROM resource_accrual_amounts WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub AND storage_quantity>0 AND storage_amount>0 AND overage_budget_micros>0 AND billing_owner_id IS NOT NULL AND authorization_id IS NOT NULL;
 INSERT INTO resource_outbox(event_id,owner_iss,owner_sub,billing_owner_id,authorization_id,origin_traceparent,period_start,period_end,meter,quantity,amount_micros,authorized_at,occurred_at,currency)
 SELECT 'address:'||lower(hex(randomblob(16))),owner_iss,owner_sub,billing_owner_id,authorization_id,origin_traceparent,period_start,period_end,'address_seconds',address_quantity,
 address_amount,accounted_at,tick,'USD'
 FROM resource_accrual_amounts WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub AND address_quantity>0 AND address_amount>0 AND overage_budget_micros>0 AND billing_owner_id IS NOT NULL AND authorization_id IS NOT NULL;
 UPDATE resource_periods SET
 accrued_micros=accrued_micros+COALESCE((SELECT storage_amount+address_amount FROM resource_accrual_amounts x WHERE x.owner_iss=resource_periods.owner_iss AND x.owner_sub=resource_periods.owner_sub AND x.period_start=resource_periods.period_start AND x.overage_budget_micros>0 AND x.billing_owner_id IS NOT NULL AND x.authorization_id IS NOT NULL),0),
 storage_fraction=COALESCE((SELECT (CASE WHEN overage_budget_micros>0 AND billing_owner_id IS NOT NULL AND authorization_id IS NOT NULL AND storage_amount=CAST(storage_fraction+storage_quantity*0.00015/(period_end-period_start) AS INTEGER) THEN storage_fraction+storage_quantity*0.00015/(period_end-period_start)-CAST(storage_fraction+storage_quantity*0.00015/(period_end-period_start) AS INTEGER) ELSE 0 END) FROM resource_accrual_amounts x WHERE x.owner_iss=resource_periods.owner_iss AND x.owner_sub=resource_periods.owner_sub AND x.period_start=resource_periods.period_start),storage_fraction),
 address_fraction=COALESCE((SELECT (CASE WHEN overage_budget_micros>0 AND billing_owner_id IS NOT NULL AND authorization_id IS NOT NULL AND address_amount=CAST(address_fraction+address_quantity*500000.0/(period_end-period_start) AS INTEGER) THEN address_fraction+address_quantity*500000.0/(period_end-period_start)-CAST(address_fraction+address_quantity*500000.0/(period_end-period_start) AS INTEGER) ELSE 0 END) FROM resource_accrual_amounts x WHERE x.owner_iss=resource_periods.owner_iss AND x.owner_sub=resource_periods.owner_sub AND x.period_start=resource_periods.period_start),address_fraction),
 accounted_at=MIN(MAX(NEW.accounting_tick,accounted_at),period_end)
 WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub AND accounted_at<period_end;
END;

DROP VIEW resource_headroom;
CREATE VIEW resource_headroom AS
 SELECT *,accrued_micros+reserved_micros+
 MAX(0,storage_bytes-included_storage_bytes)*0.00015*(period_end-unixepoch())/(period_end-period_start)+
 MAX(0,address_count-MAX(included_addresses,grandfathered_addresses))*500000.0*(period_end-unixepoch())/(period_end-period_start) AS committed_micros
 FROM resource_current;

DROP TRIGGER storage_reservations_guard;
CREATE TRIGGER storage_reservations_guard BEFORE INSERT ON storage_reservations
 WHEN NOT EXISTS(SELECT 1 FROM storage_reservations WHERE id=NEW.id) BEGIN
 UPDATE resource_accounts SET accounting_tick=unixepoch() WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub;
 SELECT (CASE WHEN NOT EXISTS(SELECT 1 FROM resource_current WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub) THEN RAISE(ABORT,'resource_account_missing') END);
 SELECT (CASE WHEN EXISTS(SELECT 1 FROM resource_headroom WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub AND storage_bytes+NEW.bytes>included_storage_bytes AND
 (overage_budget_micros=0 OR billing_owner_id IS NULL OR authorization_id IS NULL OR committed_micros+(MAX(0,storage_bytes+NEW.bytes-included_storage_bytes)-MAX(0,storage_bytes-included_storage_bytes))*0.00015*(period_end-unixepoch())/(period_end-period_start)>overage_budget_micros)) THEN RAISE(ABORT,'mailbox_full') END);
END;

DROP TRIGGER resource_address_admit;
CREATE TRIGGER resource_address_admit BEFORE INSERT ON addresses WHEN NEW.state!='retired' BEGIN
 UPDATE resource_accounts SET accounting_tick=unixepoch() WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub;
 SELECT (CASE WHEN (SELECT COUNT(*) FROM addresses WHERE state!='retired')>=198 THEN RAISE(ABORT,'capacity_exhausted') END);
 SELECT (CASE WHEN NOT EXISTS(SELECT 1 FROM resource_current WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub) THEN RAISE(ABORT,'resource_account_missing') END);
 SELECT (CASE WHEN EXISTS(SELECT 1 FROM resource_headroom WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub AND address_count>=MAX(included_addresses,grandfathered_addresses) AND
 (overage_budget_micros=0 OR billing_owner_id IS NULL OR authorization_id IS NULL OR committed_micros+500000.0*(period_end-unixepoch())/(period_end-period_start)>overage_budget_micros)) THEN RAISE(ABORT,'address_limit') END);
END;

DROP TRIGGER resource_send_admit;
CREATE TRIGGER resource_send_admit BEFORE INSERT ON resource_send_reservations BEGIN
 SELECT RAISE(ABORT,'resource_currency_invalid') WHERE NEW.currency!='USD';
 UPDATE resource_accounts SET accounting_tick=unixepoch() WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub;
 SELECT (CASE WHEN NOT EXISTS(SELECT 1 FROM resource_current WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub AND period_start=NEW.period_start) THEN RAISE(ABORT,'resource_account_missing') END);
 SELECT (CASE WHEN EXISTS(SELECT 1 FROM resource_headroom WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub AND
 (MAX(0,outbound_accepted+outbound_reserved+NEW.units-included_outbound)-MAX(0,outbound_accepted+outbound_reserved-included_outbound))*1000>0 AND
 (billing_owner_id IS NULL OR authorization_id IS NULL OR overage_budget_micros=0 OR committed_micros+(MAX(0,outbound_accepted+outbound_reserved+NEW.units-included_outbound)-MAX(0,outbound_accepted+outbound_reserved-included_outbound))*1000>overage_budget_micros)) THEN RAISE(ABORT,'outbound_quota_exhausted') END);
END;

DROP TRIGGER resource_send_finish;
CREATE TRIGGER resource_send_finish AFTER UPDATE OF state ON resource_send_reservations WHEN OLD.state='reserved' AND NEW.state!='reserved' BEGIN
 INSERT INTO resource_outbox(event_id,owner_iss,owner_sub,billing_owner_id,authorization_id,origin_traceparent,period_start,period_end,meter,quantity,amount_micros,authorized_at,occurred_at,currency)
 SELECT 'send:'||NEW.idem_key||':'||a.billing_owner_id,a.owner_iss,a.owner_sub,a.billing_owner_id,NEW.authorization_id,NEW.origin_traceparent,p.period_start,p.period_end,'outbound_recipients',
 MAX(0,p.outbound_accepted+NEW.units-p.included_outbound)-MAX(0,p.outbound_accepted-p.included_outbound),
 (MAX(0,p.outbound_accepted+NEW.units-p.included_outbound)-MAX(0,p.outbound_accepted-p.included_outbound))*1000,NEW.authorized_at,unixepoch(),'USD'
 FROM resource_accounts a JOIN resource_periods p USING(owner_iss,owner_sub)
 WHERE a.owner_iss=NEW.owner_iss AND a.owner_sub=NEW.owner_sub AND p.period_start=NEW.period_start AND NEW.state='accepted' AND a.billing_owner_id IS NOT NULL AND MAX(0,p.outbound_accepted+NEW.units-p.included_outbound)>MAX(0,p.outbound_accepted-p.included_outbound);
 UPDATE resource_periods SET
 accrued_micros=accrued_micros+(CASE WHEN NEW.state='accepted' THEN (MAX(0,outbound_accepted+NEW.units-included_outbound)-MAX(0,outbound_accepted-included_outbound))*1000 ELSE 0 END),
 outbound_accepted=outbound_accepted+(CASE WHEN NEW.state='accepted' THEN NEW.units ELSE 0 END),outbound_reserved=outbound_reserved-NEW.units
 WHERE owner_iss=NEW.owner_iss AND owner_sub=NEW.owner_sub AND period_start=NEW.period_start;
END;

-- Retry delivery acknowledgements may change; recorded denomination never may.
CREATE TRIGGER resource_outbox_currency_immutable BEFORE UPDATE OF currency ON resource_outbox
 WHEN NEW.currency!=OLD.currency BEGIN
 SELECT RAISE(ABORT,'resource_currency_immutable');
END;
CREATE TRIGGER resource_send_currency_immutable BEFORE UPDATE OF currency ON resource_send_reservations
 WHEN NEW.currency!=OLD.currency BEGIN
 SELECT RAISE(ABORT,'resource_currency_immutable');
END;
