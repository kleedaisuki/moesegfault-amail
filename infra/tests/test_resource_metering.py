"""Run production resource triggers against deterministic SQLite; no mail/provider access."""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ResourceMetering(unittest.TestCase):
    """Assert tariff, consent, concurrency serialization and immutable retry boundaries."""

    def setUp(self):
        """Install the actual schema with a controlled UTC billing clock."""
        self.clock = int(datetime(2026, 10, 7, tzinfo=timezone.utc).timestamp())
        self.db = sqlite3.connect(":memory:")
        self.db.create_function("unixepoch", -1, self.unixepoch)
        for file in sorted((ROOT / "crates/mail-worker/migrations").glob("*.sql")):
            if file.name[:4] <= "0013":
                self.db.executescript(file.read_text(encoding="utf-8"))
        self.db.execute("INSERT INTO resource_accounts(owner_iss,owner_sub) VALUES('issuer','owner')")
        self.db.execute("INSERT INTO resource_periods(owner_iss,owner_sub,period_start,period_end,accounted_at) VALUES('issuer','owner',unixepoch('now','start of month'),unixepoch('now','start of month','+1 month'),unixepoch())")

    def unixepoch(self, *args):
        """Implement only SQLite UTC date forms used by production migrations."""
        date = datetime.fromtimestamp(self.clock, timezone.utc)
        for arg in args:
            if arg == "start of month":
                date = date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            elif arg == "+1 month":
                date = date.replace(year=date.year + (date.month == 12), month=date.month % 12 + 1)
            elif arg not in ("now",):
                raise ValueError(arg)
        return int(date.timestamp())

    def authorize(self, budget=10_000_000):
        """Explicit human authorization is a fixture, never synthesized by a paid plan."""
        self.db.execute("UPDATE resource_accounts SET billing_owner_id='opaque-owner',authorization_id='human-consent',overage_budget_micros=?", (budget,))

    def reserve(self, key, units):
        """Mirror the application's atomic INSERT SELECT, including exact replay no-op."""
        self.db.execute("INSERT INTO resource_send_reservations(owner_iss,owner_sub,idem_key,period_start,units,authorization_id) SELECT 'issuer','owner',?,period_start,?,authorization_id FROM resource_current WHERE NOT EXISTS(SELECT 1 FROM resource_send_reservations WHERE idem_key=?)", (key, units, key))

    def state(self, key, state):
        """Exercise the same trigger transition invoked by the provider journal."""
        self.db.execute("UPDATE resource_send_reservations SET state=? WHERE idem_key=?", (state, key))

    def stock(self, size):
        """Allocate a real retained-byte reservation through production admission."""
        self.db.execute("INSERT INTO storage_reservations(id,owner_iss,owner_sub,bytes,state,created_at) VALUES('archive','issuer','owner',?,'indexed',unixepoch())", (size,))

    def test_free_is_monthly_recipients_not_submission_count(self):
        self.reserve("first", 100)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "outbound_quota_exhausted"):
            self.reserve("excess", 1)
        self.reserve("first", 100)
        self.assertEqual(self.db.execute("SELECT outbound_reserved FROM resource_current").fetchone()[0], 100)
        self.state("first", "released")
        self.reserve("new", 100)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM resource_outbox").fetchone()[0], 0)

    def test_reversed_acceptance_order_cannot_free_an_unfunded_hold(self):
        self.authorize(5_000)
        self.reserve("original-free", 100)
        self.reserve("original-excess", 1)
        self.state("original-excess", "accepted")
        # Shared outstanding holding, not per-request free slots, preserves the cap.
        self.assertEqual(self.db.execute("SELECT reserved_micros FROM resource_current").fetchone()[0], 5_000)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "outbound_quota_exhausted"):
            self.reserve("concurrent", 1)
        self.state("original-free", "accepted")
        self.state("original-free", "accepted")
        self.assertEqual(self.db.execute("SELECT SUM(amount_micros),COUNT(*) FROM resource_outbox").fetchone(), (5_000, 1))
        self.assertEqual(self.db.execute("SELECT outbound_accepted,outbound_reserved FROM resource_current").fetchone(), (101, 0))

    def test_unknown_reservation_stays_held_and_old_consent_is_retained(self):
        self.authorize(5_000)
        self.reserve("unknown", 101)
        original_time = self.clock
        self.db.execute("UPDATE resource_accounts SET authorization_id='new-consent',overage_budget_micros=0")
        self.clock += 60
        self.state("unknown", "accepted")
        self.assertEqual(self.db.execute("SELECT authorization_id,authorized_at,occurred_at,amount_micros FROM resource_outbox").fetchone(), ("human-consent", original_time, self.clock, 5_000))

    def test_storage_free_limit_is_decimal_and_has_no_mail_count(self):
        self.stock(200_000_000)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "mailbox_full"):
            self.db.execute("INSERT INTO storage_reservations VALUES('one-byte','issuer','owner',1,'indexed',unixepoch())")
        self.db.execute("DELETE FROM storage_reservations")
        for index in range(250):
            self.db.execute("INSERT INTO storage_reservations VALUES(?,'issuer','owner',1,'indexed',unixepoch())", (str(index),))
        self.assertEqual(self.db.execute("SELECT used_bytes FROM storage_usage").fetchone()[0], 250)

    def test_stock_tariff_integrates_old_bytes_before_delete(self):
        self.authorize()
        self.stock(1_200_000_000)
        start = self.clock
        self.clock += 86_400
        self.db.execute("DELETE FROM storage_reservations WHERE id='archive'")
        event = self.db.execute("SELECT quantity,amount_micros,authorized_at FROM resource_outbox").fetchone()
        self.assertEqual(event, (1_000_000_000 * 86_400, 1_000_000 // 31, start))
        self.clock += 86_400
        self.db.execute("UPDATE resource_accounts SET accounting_tick=unixepoch()")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM resource_outbox").fetchone()[0], 1)

    def test_tiny_stock_observations_do_not_round_each_event_to_cents(self):
        self.authorize()
        self.stock(1_200_000_000)
        for _ in range(100):
            self.clock += 1
            self.db.execute("UPDATE resource_accounts SET accounting_tick=unixepoch()")
        self.assertEqual(self.db.execute("SELECT SUM(amount_micros) FROM resource_outbox").fetchone()[0], int(100 * 1_000_000 / (31 * 86_400)))

    def test_human_lowered_budget_does_not_accrue_unapproved_debt(self):
        self.authorize()
        self.stock(1_200_000_000)
        self.db.execute("UPDATE resource_accounts SET overage_budget_micros=1")
        self.clock += 86_400
        self.db.execute("UPDATE resource_accounts SET accounting_tick=unixepoch()")
        self.assertEqual(self.db.execute("SELECT accrued_micros FROM resource_current").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT used_bytes FROM storage_usage").fetchone()[0], 1_200_000_000)

    def test_address_growth_uses_full_remaining_period_budget(self):
        query = "INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,state,created_at) VALUES(?,'fixture','issuer','owner',?,'active',unixepoch())"
        self.db.execute(query, ("first@example.invalid", 0))
        with self.assertRaisesRegex(sqlite3.IntegrityError, "address_limit"):
            self.db.execute(query, ("second@example.invalid", 1))
        self.authorize(1)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "address_limit"):
            self.db.execute(query, ("second@example.invalid", 1))
        self.authorize()
        self.db.execute(query, ("second@example.invalid", 1))
        self.clock += 86_400
        self.db.execute("UPDATE addresses SET state='retired' WHERE slot=1")
        self.assertEqual(self.db.execute("SELECT meter,quantity,amount_micros FROM resource_outbox").fetchone(), ("address_seconds", 86_400, 3_000_000 // 31))

    def test_paid_plan_is_not_variable_spending_consent(self):
        self.db.execute("UPDATE resource_accounts SET plan='plus',included_storage_bytes=10000000000,included_addresses=5,included_outbound=5000")
        self.stock(10_000_000_000)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "mailbox_full"):
            self.db.execute("INSERT INTO storage_reservations VALUES('extra','issuer','owner',1,'indexed',unixepoch())")


if __name__ == "__main__":
    unittest.main()
