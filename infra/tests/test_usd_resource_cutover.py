"""Exercise the real additive USD cutover, without rewriting historical CNY evidence."""
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
import unittest

import test_resource_metering as legacy

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "crates/mail-worker/migrations"


class UsdCutover(unittest.TestCase):
    """Keep quota continuity separate from non-transferable monetary denomination."""

    def setUp(self):
        """Reuse the deterministic production-schema fixture before its USD cutover."""
        self.fixture = legacy.ResourceMetering()
        self.fixture.setUp()
        self.db = self.fixture.db
        self.db.executescript((MIGRATIONS / "0014_billing_sessions.sql").read_text())

    def tearDown(self):
        """Release the in-memory connection even after an intentional migration refusal."""
        self.db.close()

    def migrate(self):
        """Mirror D1's atomic migration transaction, including failure rollback."""
        self.db.commit()
        try:
            self.db.executescript("BEGIN;\n" + (MIGRATIONS / "0015_usd_resource_billing.sql").read_text() + "\nCOMMIT;")
        except sqlite3.Error:
            self.db.rollback()
            raise

    def reserve(self, key, units):
        """Capture the explicit denomination used by the shipping Rust boundary."""
        source = (ROOT / "crates/mail-worker/src/resource.rs").read_text()
        query = re.search(r'prepare\("(INSERT INTO resource_send_reservations[^"\n]+)"\)', source).group(1)
        self.db.execute(query, ("issuer", "owner", key, units, None))

    def test_preserves_six_cny_events_and_usage_without_relabeling(self):
        self.fixture.authorize()
        self.fixture.reserve('historic', 1)
        self.fixture.state('historic', 'accepted')
        self.db.execute("UPDATE resource_accounts SET plan='lite',included_addresses=3,grandfathered_addresses=7,overage_budget_micros=0")
        self.db.execute("UPDATE resource_periods SET outbound_accepted=108,accrued_micros=22,storage_fraction=0.25,address_fraction=0.75")
        for i, amount in enumerate([3, 3, 4, 4, 4, 4]):
            self.db.execute("INSERT INTO resource_outbox(event_id,owner_iss,owner_sub,billing_owner_id,authorization_id,period_start,period_end,meter,quantity,amount_micros,authorized_at,occurred_at,delivered_at) SELECT ?,owner_iss,owner_sub,billing_owner_id,authorization_id,period_start,period_end,'address_seconds',1,?,accounted_at,accounted_at,accounted_at FROM resource_current", (str(i), amount))
        self.migrate()
        self.assertEqual(self.db.execute("SELECT currency,COUNT(*),SUM(amount_micros) FROM resource_outbox GROUP BY currency").fetchall(), [('CNY', 6, 22)])
        self.assertEqual(self.db.execute("SELECT currency,accrued_micros,storage_fraction,address_fraction FROM resource_legacy_cny_periods").fetchone(), ('CNY', 22, 0.25, 0.75))
        self.assertEqual(self.db.execute("SELECT currency,plan,grandfathered_addresses,outbound_accepted,accrued_micros,storage_fraction,address_fraction,overage_budget_micros,authorization_id FROM resource_current").fetchone(), ('USD', 'lite', 7, 108, 0, 0.0, 0.0, 0, None))
        self.assertEqual(self.db.execute("SELECT state,currency FROM resource_send_reservations").fetchone(), ('accepted', 'CNY'))
        for query in ["UPDATE resource_legacy_cny_periods SET accrued_micros=0", "DELETE FROM resource_legacy_cny_periods", "UPDATE resource_outbox SET currency='USD'", "UPDATE resource_send_reservations SET currency='USD'"]:
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(query)

    def test_guarded_refusal_is_atomic(self):
        for unsafe in ['cap', 'outbox', 'reserved']:
            with self.subTest(unsafe=unsafe):
                self.db.execute("UPDATE resource_accounts SET overage_budget_micros=1" if unsafe == 'cap' else "UPDATE resource_accounts SET overage_budget_micros=0")
                if unsafe == 'outbox':
                    self.db.execute("INSERT INTO resource_outbox(event_id,owner_iss,owner_sub,billing_owner_id,period_start,period_end,meter,quantity,amount_micros,authorized_at,occurred_at) SELECT 'pending',owner_iss,owner_sub,'payer',period_start,period_end,'address_seconds',1,1,accounted_at,accounted_at FROM resource_current")
                if unsafe == 'reserved':
                    self.fixture.reserve('unknown', 1)
                with self.assertRaisesRegex(sqlite3.IntegrityError, 'resource_usd_cutover_requires_settled_cny'):
                    self.migrate()
                self.assertNotIn('currency', [row[1] for row in self.db.execute('PRAGMA table_info(resource_accounts)')])
                self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='resource_legacy_cny_periods'").fetchone()[0], 0)
                self.db.execute("DELETE FROM resource_outbox")

    def test_unbilled_unknown_journal_survives_cutover(self):
        """Legacy uncertainty without resource liability must not prevent or become a bill."""
        self.db.execute("UPDATE send_release_gates SET canary_owner_iss='issuer',canary_owner_sub='owner',canary_expires_at=unixepoch()+600 WHERE id=1")
        self.db.execute("INSERT INTO send_requests(owner_iss,owner_sub,idem_key,payload_hash,state,created_at) VALUES('issuer','owner','legacy-unknown','hash','preparing',unixepoch())")
        self.db.execute("UPDATE send_requests SET state='unknown' WHERE idem_key='legacy-unknown'")
        before = self.db.execute('SELECT * FROM send_requests').fetchall()
        self.migrate()
        self.assertEqual(self.db.execute('SELECT * FROM send_requests').fetchall(), before)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM resource_outbox').fetchone()[0], 0)

    def test_usd_recipient_tariff_and_explicit_new_currency(self):
        self.migrate()
        self.fixture.authorize(1000)
        self.reserve('usd', 101)
        self.assertEqual(self.db.execute('SELECT reserved_micros FROM resource_current').fetchone()[0], 1000)
        self.fixture.state('usd', 'accepted')
        self.assertEqual(self.db.execute('SELECT currency,amount_micros FROM resource_outbox').fetchone(), ('USD', 1000))
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'outbound_quota_exhausted'):
            self.reserve('over-budget', 1)
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'resource_currency_invalid'):
            self.fixture.reserve('missing-currency', 1)

    def test_usd_storage_and_address_stock_prices(self):
        self.migrate()
        self.fixture.authorize(1_000_000)
        self.fixture.stock(1_200_000_000)
        for i in range(2):
            self.db.execute("INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,state,created_at) VALUES(?,'usd','issuer','owner',?,'active',unixepoch())", (f'usd{i}@example.test', i))
        start, end = self.db.execute('SELECT period_start,period_end FROM resource_current').fetchone()
        self.fixture.clock = end
        self.db.execute("UPDATE resource_accounts SET accounting_tick=?", (end,))
        elapsed = end - int(datetime(2026, 10, 7, tzinfo=timezone.utc).timestamp())
        values = dict(self.db.execute('SELECT meter,amount_micros FROM resource_outbox'))
        self.assertEqual(values['storage_byte_seconds'], int(150_000 * elapsed / (end - start)))
        self.assertEqual(values['address_seconds'], int(500_000 * elapsed / (end - start)))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM resource_outbox WHERE currency!='USD'").fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
