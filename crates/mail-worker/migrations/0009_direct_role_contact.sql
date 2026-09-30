-- Direct-forward-only contact gate. No route observation is a human review,
-- and no historical ROLE_MONITOR lease is imported into MAIL_DB.
ALTER TABLE send_release_gates ADD COLUMN abuse_contact_contract_id TEXT;
ALTER TABLE send_release_gate_audit ADD COLUMN abuse_contact_contract_id TEXT;
DROP TRIGGER send_release_gate_audit_update;
CREATE TRIGGER send_release_gate_audit_update AFTER UPDATE ON send_release_gates BEGIN
    INSERT INTO send_release_gate_audit(feedback_verified,abuse_contact_verified,delivery_canary_verified,preview_reviewed,canary_owner_iss,canary_owner_sub,canary_recipient_sha256,canary_expires_at,canary_used_by,actor,case_ref,changed_at,abuse_contact_contract_id)
    VALUES(NEW.feedback_verified,NEW.abuse_contact_verified,NEW.delivery_canary_verified,NEW.preview_reviewed,NEW.canary_owner_iss,NEW.canary_owner_sub,NEW.canary_recipient_sha256,NEW.canary_expires_at,NEW.canary_used_by,NEW.actor,NEW.case_ref,NEW.updated_at,NEW.abuse_contact_contract_id);
END;

-- Pin identifiers, never the private destination address or an address hash.
-- Fixed columns make missing/extra/duplicate role associations unrepresentable.
CREATE TABLE role_contact_policy (
    id INTEGER PRIMARY KEY CHECK (id=1),
    version INTEGER NOT NULL CHECK (version=1),
    contract_id TEXT NOT NULL UNIQUE CHECK (length(contract_id)=36),
    destination_id TEXT NOT NULL CHECK (length(destination_id) BETWEEN 1 AND 128),
    apex_abuse_rule_id TEXT NOT NULL CHECK (length(apex_abuse_rule_id) BETWEEN 1 AND 128),
    apex_postmaster_rule_id TEXT NOT NULL CHECK (length(apex_postmaster_rule_id) BETWEEN 1 AND 128),
    mail_abuse_rule_id TEXT NOT NULL CHECK (length(mail_abuse_rule_id) BETWEEN 1 AND 128),
    mail_postmaster_rule_id TEXT NOT NULL CHECK (length(mail_postmaster_rule_id) BETWEEN 1 AND 128),
    actor TEXT NOT NULL,
    case_ref TEXT NOT NULL,
    updated_at INTEGER NOT NULL,
    CHECK (apex_abuse_rule_id!=apex_postmaster_rule_id AND apex_abuse_rule_id!=mail_abuse_rule_id
       AND apex_abuse_rule_id!=mail_postmaster_rule_id AND apex_postmaster_rule_id!=mail_abuse_rule_id
       AND apex_postmaster_rule_id!=mail_postmaster_rule_id AND mail_abuse_rule_id!=mail_postmaster_rule_id)
);
-- Keep the compact adoption ledger permanently: discarded contracts cannot be reused.
CREATE TABLE role_contact_policy_audit (
    contract_id TEXT PRIMARY KEY, version INTEGER NOT NULL, actor TEXT NOT NULL,
    case_ref TEXT NOT NULL, changed_at INTEGER NOT NULL
);
CREATE TRIGGER role_contact_policy_new BEFORE INSERT ON role_contact_policy BEGIN
    SELECT (CASE WHEN EXISTS(SELECT 1 FROM role_contact_policy_audit WHERE contract_id=NEW.contract_id)
        THEN RAISE(ABORT,'contact_contract_reused') END);
END;
CREATE TRIGGER role_contact_policy_replace BEFORE UPDATE ON role_contact_policy BEGIN
    SELECT (CASE WHEN OLD.contract_id=NEW.contract_id OR EXISTS(
        SELECT 1 FROM role_contact_policy_audit WHERE contract_id=NEW.contract_id)
        THEN RAISE(ABORT,'contact_contract_reused') END);
END;
CREATE TABLE role_contact_health (
    id INTEGER PRIMARY KEY CHECK (id=1),
    contract_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('healthy','unverified')),
    checked_at INTEGER NOT NULL CHECK (typeof(checked_at)='integer' AND checked_at>0),
    expires_at INTEGER NOT NULL CHECK (typeof(expires_at)='integer'),
    run_ref TEXT NOT NULL CHECK (length(run_ref) BETWEEN 3 AND 128),
    CHECK ((state='healthy' AND expires_at=checked_at+21600) OR (state='unverified' AND expires_at=0))
);
CREATE TRIGGER role_contact_health_insert_guard BEFORE INSERT ON role_contact_health BEGIN
    SELECT (CASE WHEN NEW.checked_at>unixepoch() OR NOT EXISTS(
        SELECT 1 FROM role_contact_policy WHERE id=1 AND version=1 AND contract_id=NEW.contract_id)
        THEN RAISE(ABORT,'contact_observation_invalid') END);
END;
CREATE TRIGGER role_contact_health_update_guard BEFORE UPDATE ON role_contact_health BEGIN
    SELECT (CASE WHEN NEW.checked_at>unixepoch() OR NEW.checked_at<OLD.checked_at
        OR (NEW.checked_at=OLD.checked_at AND NOT (OLD.state='healthy' AND NEW.state='unverified')) OR NOT EXISTS(
        SELECT 1 FROM role_contact_policy WHERE id=1 AND version=1 AND contract_id=NEW.contract_id)
        THEN RAISE(ABORT,'contact_observation_invalid') END);
END;
CREATE TABLE role_contact_health_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id TEXT NOT NULL,
    state TEXT NOT NULL, checked_at INTEGER NOT NULL, run_ref TEXT NOT NULL
);
CREATE TRIGGER role_contact_health_audit_insert AFTER INSERT ON role_contact_health BEGIN
    INSERT INTO role_contact_health_audit(contract_id,state,checked_at,run_ref)
        VALUES(NEW.contract_id,NEW.state,NEW.checked_at,NEW.run_ref);
    DELETE FROM role_contact_health_audit WHERE id NOT IN
        (SELECT id FROM role_contact_health_audit ORDER BY id DESC LIMIT 256);
END;
CREATE TRIGGER role_contact_health_audit_update AFTER UPDATE ON role_contact_health
WHEN OLD.state!=NEW.state OR OLD.contract_id!=NEW.contract_id BEGIN
    INSERT INTO role_contact_health_audit(contract_id,state,checked_at,run_ref)
        VALUES(NEW.contract_id,NEW.state,NEW.checked_at,NEW.run_ref);
    DELETE FROM role_contact_health_audit WHERE id NOT IN
        (SELECT id FROM role_contact_health_audit ORDER BY id DESC LIMIT 256);
END;
CREATE TRIGGER role_contact_health_failed_insert AFTER INSERT ON role_contact_health
WHEN NEW.state='unverified' BEGIN
    UPDATE send_policy SET state='held',reason_code='contact_health_failed',actor='contact_checker',
        note_ref=NEW.run_ref,updated_at=unixepoch()
    WHERE scope='global' AND owner_iss='*' AND owner_sub='*' AND state!='held';
END;
CREATE TRIGGER role_contact_health_failed_update AFTER UPDATE ON role_contact_health
WHEN NEW.state='unverified' BEGIN
    UPDATE send_policy SET state='held',reason_code='contact_health_failed',actor='contact_checker',
        note_ref=NEW.run_ref,updated_at=unixepoch()
    WHERE scope='global' AND owner_iss='*' AND owner_sub='*' AND state!='held';
END;
CREATE TRIGGER role_contact_policy_adopted AFTER INSERT ON role_contact_policy BEGIN
    INSERT INTO role_contact_policy_audit VALUES(NEW.contract_id,NEW.version,NEW.actor,NEW.case_ref,NEW.updated_at);
    DELETE FROM role_contact_health;
    UPDATE send_release_gates SET abuse_contact_verified=0,abuse_contact_contract_id=NULL,
        actor=NEW.actor,case_ref=NEW.case_ref,updated_at=unixepoch() WHERE id=1;
    UPDATE send_policy SET state='held',reason_code='contact_contract_changed',actor=NEW.actor,
        note_ref=NEW.case_ref,updated_at=unixepoch() WHERE scope='global' AND owner_iss='*' AND owner_sub='*' AND state!='held';
END;
CREATE TRIGGER role_contact_policy_changed AFTER UPDATE ON role_contact_policy BEGIN
    INSERT INTO role_contact_policy_audit VALUES(NEW.contract_id,NEW.version,NEW.actor,NEW.case_ref,NEW.updated_at);
    DELETE FROM role_contact_health;
    UPDATE send_release_gates SET abuse_contact_verified=0,abuse_contact_contract_id=NULL,
        actor=NEW.actor,case_ref=NEW.case_ref,updated_at=unixepoch() WHERE id=1;
    UPDATE send_policy SET state='held',reason_code='contact_contract_changed',actor=NEW.actor,
        note_ref=NEW.case_ref,updated_at=unixepoch() WHERE scope='global' AND owner_iss='*' AND owner_sub='*' AND state!='held';
END;
CREATE TRIGGER role_contact_policy_removed AFTER DELETE ON role_contact_policy BEGIN
    DELETE FROM role_contact_health;
    UPDATE send_release_gates SET abuse_contact_verified=0,abuse_contact_contract_id=NULL,
        actor=OLD.actor,case_ref=OLD.case_ref,updated_at=unixepoch() WHERE id=1;
    UPDATE send_policy SET state='held',reason_code='contact_contract_removed',actor=OLD.actor,
        note_ref=OLD.case_ref,updated_at=unixepoch() WHERE scope='global' AND owner_iss='*' AND owner_sub='*' AND state!='held';
END;
-- One database-time predicate is shared by API prechecks, operators, release
-- checks and SQL admission. Equality at expiry is expired, not a grace period.
CREATE VIEW direct_role_contact_ready AS
SELECT p.contract_id FROM role_contact_policy p
JOIN role_contact_health h ON h.id=1 AND h.contract_id=p.contract_id
JOIN send_release_gates g ON g.id=1 AND g.abuse_contact_contract_id=p.contract_id
WHERE p.id=1 AND p.version=1 AND g.abuse_contact_verified=1
  AND h.state='healthy' AND h.checked_at>0 AND h.checked_at<=unixepoch()
  AND unixepoch()<h.expires_at AND h.expires_at=h.checked_at+21600;
-- Every global unhold, including direct SQL and allowed-to-allowed edits,
-- rechecks the same database-time gate. Holds/account edits are unconditional.
CREATE TRIGGER send_policy_direct_allow_insert BEFORE INSERT ON send_policy
WHEN NEW.scope='global' AND NEW.state='allowed' BEGIN
    SELECT (CASE WHEN NOT EXISTS(SELECT 1 FROM send_release_gates WHERE id=1
        AND feedback_verified=1 AND abuse_contact_verified=1
        AND delivery_canary_verified=1 AND preview_reviewed=1)
        OR NOT EXISTS(SELECT 1 FROM direct_role_contact_ready)
        THEN RAISE(ABORT,'send_held') END);
END;
CREATE TRIGGER send_policy_direct_allow_update BEFORE UPDATE ON send_policy
WHEN NEW.scope='global' AND NEW.state='allowed' BEGIN
    SELECT (CASE WHEN NOT EXISTS(SELECT 1 FROM send_release_gates WHERE id=1
        AND feedback_verified=1 AND abuse_contact_verified=1
        AND delivery_canary_verified=1 AND preview_reviewed=1)
        OR NOT EXISTS(SELECT 1 FROM direct_role_contact_ready)
        THEN RAISE(ABORT,'send_held') END);
END;
CREATE TRIGGER send_release_contact_attestation_guard BEFORE UPDATE ON send_release_gates
WHEN NEW.abuse_contact_verified=1 BEGIN
    SELECT (CASE WHEN NOT EXISTS(SELECT 1 FROM role_contact_policy WHERE id=1 AND version=1
        AND contract_id=NEW.abuse_contact_contract_id)
        THEN RAISE(ABORT,'contact_attestation_mismatch') END);
END;
-- Explicit contact revocation also invalidates configuration observations, even
-- on repeated revoke while the human flag is already zero. Other gate/canary
-- updates do not clear contact health; verification never renews it.
CREATE TRIGGER send_release_contact_revoked AFTER UPDATE OF abuse_contact_verified,abuse_contact_contract_id ON send_release_gates
WHEN NEW.abuse_contact_verified=0 BEGIN
    DELETE FROM role_contact_health;
    UPDATE send_policy SET state='held',reason_code='contact_attestation_revoked',actor=NEW.actor,
        note_ref=NEW.case_ref,updated_at=unixepoch()
    WHERE scope='global' AND owner_iss='*' AND owner_sub='*' AND state!='held';
END;
CREATE TRIGGER send_request_direct_contact_guard BEFORE INSERT ON send_requests BEGIN
    -- A held canary is checked/consumed by the existing guard. Do not depend on
    -- trigger order, or let an allowed-but-expired contact fall back to a canary.
    SELECT (CASE WHEN NOT EXISTS(SELECT 1 FROM send_policy WHERE scope='global'
        AND owner_iss='*' AND owner_sub='*' AND state='held')
        AND NOT EXISTS(SELECT 1 FROM direct_role_contact_ready)
        THEN RAISE(ABORT,'send_held') END);
END;
-- Enforce held-state canaries even if a previously consumed key remains present.
CREATE TRIGGER send_request_allowed_canary_guard BEFORE INSERT ON send_requests BEGIN
    SELECT (CASE WHEN NOT EXISTS(SELECT 1 FROM send_policy WHERE scope='global'
        AND owner_iss='*' AND owner_sub='*' AND state='held')
        AND NOT EXISTS(SELECT 1 FROM send_policy p JOIN send_release_gates g ON g.id=1
        WHERE p.scope='global' AND p.owner_iss='*' AND p.owner_sub='*' AND p.state='allowed'
          AND g.feedback_verified=1 AND g.abuse_contact_verified=1
          AND g.delivery_canary_verified=1 AND g.preview_reviewed=1)
        THEN RAISE(ABORT,'send_held') END);
END;
-- Migration authorizes nothing; the pending Inbox/Junk and 24h coverage
-- commitment must be explicitly attested against a later adopted contract.
UPDATE send_release_gates SET abuse_contact_verified=0,abuse_contact_contract_id=NULL,
    actor='migration',case_ref='direct_contact_adoption_pending',updated_at=unixepoch() WHERE id=1;
UPDATE send_policy SET state='held',reason_code='direct_contact_adoption_pending',actor='migration',
    note_ref='direct_contact_adoption_pending',updated_at=unixepoch()
WHERE scope='global' AND owner_iss='*' AND owner_sub='*' AND state!='held';
