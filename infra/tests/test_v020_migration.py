"""Exercise real upgrade SQL against a pre-v0.2 owned mailbox, without providers."""

from pathlib import Path
import sqlite3
import unittest


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "crates/mail-worker/migrations"
ISSUER = "https://identity-staging.moesegfault.dev"
SUBJECT = "synthetic-grandfather-owner"


class UpgradePreservationTests(unittest.TestCase):
    """Derive preservation expectations from owner requirements, not new SQL."""

    def setUp(self):
        """Build the exact previous schema and an account above Free's address count."""
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.files = sorted(MIGRATIONS.glob("*.sql"))
        for migration in self.files:
            if migration.name[:4] <= "0012":
                self.db.executescript(migration.read_text(encoding="utf-8"))
        for slot in range(10):
            self.db.execute(
                "INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,"
                "cf_rule_id,state,created_at) VALUES(?,?,?,?,?,?,'active',?)",
                (f"fixture-{slot}@mail-staging.moesegfault.dev", f"fixture-{slot}",
                 ISSUER, SUBJECT, slot, f"synthetic-rule-{slot}", 1_790_000_000 + slot),
            )
        self.db.execute(
            "INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,"
            "state,created_at) VALUES('retired@mail-staging.moesegfault.dev',"
            "'retired',?,?,0,'retired',1790000000)", (ISSUER, SUBJECT),
        )
        self.db.execute(
            "INSERT INTO messages(id,address,owner_iss,owner_sub,direction,sender,"
            "recipients_json,subject,body_text,metadata_json,received_at,has_html,"
            "has_text,attachment_count,r2_key,size_bytes,storage_bytes) "
            "VALUES('synthetic-message',?,?,?,'inbound','fixture@example.invalid',"
            "'[]','fixture','fixture','{}',1790000000,0,1,0,'synthetic/r2',123,234)",
            ("fixture-0@mail-staging.moesegfault.dev", ISSUER, SUBJECT),
        )
        self.db.execute(
            "INSERT INTO storage_reservations(id,owner_iss,owner_sub,bytes,state,created_at) "
            "VALUES('synthetic-message',?,?,234,'indexed',1790000000)",
            (ISSUER, SUBJECT),
        )
        # Local-only scoped fixture grant exercises the real send guard unchanged.
        self.db.execute(
            "UPDATE send_release_gates SET canary_owner_iss=?,canary_owner_sub=?,"
            "canary_expires_at=unixepoch()+600 WHERE id=1", (ISSUER, SUBJECT),
        )
        self.db.execute(
            "INSERT INTO send_requests(owner_iss,owner_sub,idem_key,payload_hash,"
            "state,created_at) VALUES(?,?,'synthetic-unknown','synthetic-hash',"
            "'unknown',1790000000000)", (ISSUER, SUBJECT),
        )
        self.db.commit()

    def snapshot(self, table):
        """Retain every legacy column so loss of private ownership cannot be masked."""
        columns = [row[1] for row in self.db.execute(f"PRAGMA table_info({table})")]
        return columns, list(self.db.execute(f"SELECT {','.join(columns)} FROM {table} ORDER BY 1"))

    def upgrade(self):
        """Apply only additive new release migrations, exactly once and in order."""
        for migration in self.files:
            if migration.name[:4] > "0012":
                self.db.executescript(migration.read_text(encoding="utf-8"))

    def test_upgrade_preserves_all_registered_addresses_and_mail(self):
        """Free migration must not retire aliases, purge mail, or reset unknown sends."""
        tables = ("addresses", "messages", "storage_reservations", "storage_usage", "send_requests")
        before = {table: self.snapshot(table) for table in tables}
        self.upgrade()
        for table, (columns, expected) in before.items():
            with self.subTest(table=table):
                actual = list(self.db.execute(f"SELECT {','.join(columns)} FROM {table} ORDER BY 1"))
                self.assertEqual(actual, expected)
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(self.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_existing_owner_becomes_free_without_paying_for_registered_addresses(self):
        """The ten live aliases are grandfathered; retired history is not billable stock."""
        self.upgrade()
        row = self.db.execute(
            "SELECT plan,included_outbound,included_storage_bytes,included_addresses,"
            "grandfathered_addresses,overage_budget_micros,billing_owner_id "
            "FROM resource_accounts WHERE owner_iss=? AND owner_sub=?", (ISSUER, SUBJECT),
        ).fetchone()
        self.assertEqual(row, ("free", 100, 200_000_000, 1, 10, 0, None))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM resource_outbox").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM resource_send_reservations").fetchone()[0], 0)

    def test_new_account_defaults_do_not_grant_financial_consent(self):
        """A new immutable owner tuple gets community entitlements, never an implicit payer."""
        self.upgrade()
        self.db.execute("INSERT INTO resource_accounts(owner_iss,owner_sub) VALUES(?,'new-owner')", (ISSUER,))
        self.assertEqual(self.db.execute(
            "SELECT plan,included_outbound,included_storage_bytes,included_addresses,"
            "grandfathered_addresses,overage_budget_micros,billing_owner_id "
            "FROM resource_accounts WHERE owner_sub='new-owner'",
        ).fetchone(), ("free", 100, 200_000_000, 1, 0, 0, None))

    def test_acceptance_trigger_changes_are_not_direct_row_identity(self):
        """One real accepted journal transition also commits its reserved usage rows."""
        self.upgrade()
        self.db.execute("UPDATE send_requests SET state='submitting' WHERE idem_key='synthetic-unknown'")
        self.db.execute(
            "INSERT INTO resource_send_reservations(owner_iss,owner_sub,idem_key,period_start,units,currency) "
            "SELECT owner_iss,owner_sub,'synthetic-unknown',period_start,1,'USD' FROM resource_current "
            "WHERE owner_iss=? AND owner_sub=?", (ISSUER, SUBJECT),
        )
        before = self.db.total_changes
        self.db.execute(
            "UPDATE send_requests SET state='accepted',provider_id=?1,sender=?2,envelope_json=?3,"
            "request_id=?4 WHERE owner_iss=?5 AND owner_sub=?6 AND idem_key=?7 AND state='submitting'",
            ("synthetic-provider", "fixture@example.invalid", "[]", "synthetic-request", ISSUER, SUBJECT,
             "synthetic-unknown"),
        )
        self.assertEqual(self.db.execute("SELECT changes()").fetchone()[0], 1)
        self.assertGreater(self.db.total_changes - before, 1)
        self.assertEqual(self.db.execute("SELECT state FROM resource_send_reservations").fetchone()[0], "accepted")
        self.assertEqual(self.db.execute("SELECT outbound_reserved,outbound_accepted FROM resource_periods")
                         .fetchone(), (0, 1))


if __name__ == "__main__":
    unittest.main()
