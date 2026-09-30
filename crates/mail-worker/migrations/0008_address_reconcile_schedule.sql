-- Rotate bounded address reconciliation scans without losing the durable state journal.
-- A rule that is disabled or whose status is unknown must remain provisioning,
-- but repeated scans of that row must not starve later deletion work.
ALTER TABLE addresses ADD COLUMN next_reconcile_at INTEGER NOT NULL DEFAULT 0;
-- Preserve urgency for pre-migration deletions rather than relying on age.
UPDATE addresses SET next_reconcile_at=-1
    WHERE state='deleting' OR (state='retired' AND needs_reconcile=1);
CREATE INDEX IF NOT EXISTS addresses_reconcile_due
    ON addresses(next_reconcile_at, created_at, address);
