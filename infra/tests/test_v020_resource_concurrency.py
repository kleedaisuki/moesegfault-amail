"""Independent multi-connection SQLite contention test for the production quota SQL."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
from threading import Barrier
import unittest


ROOT = Path(__file__).resolve().parents[2]


class ResourceConcurrencyTests(unittest.TestCase):
    """Prove the final Free send unit cannot be independently won by two writers."""

    def test_two_connections_contend_for_one_remaining_recipient(self):
        """Serialized guard and counter commit admit exactly one reservation, not two."""
        temp = ROOT / ".temp"
        temp.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="v020-resource-race-", dir=temp) as directory:
            filename = str(Path(directory) / "mail.sqlite")
            with closing(sqlite3.connect(filename)) as db:
                for file in sorted((ROOT / "crates/mail-worker/migrations").glob("*.sql")):
                    db.executescript(file.read_text(encoding="utf-8"))
                db.execute("INSERT INTO resource_accounts(owner_iss,owner_sub) VALUES('synthetic','owner')")
                db.execute("INSERT INTO resource_periods(owner_iss,owner_sub,period_start,period_end,accounted_at) "
                           "VALUES('synthetic','owner',unixepoch('now','start of month'),"
                           "unixepoch('now','start of month','+1 month'),unixepoch())")
                period = db.execute("SELECT period_start FROM resource_periods").fetchone()[0]
                db.execute("INSERT INTO resource_send_reservations(owner_iss,owner_sub,idem_key,period_start,units,currency) "
                           "VALUES('synthetic','owner','initial',?,99,'USD')", (period,))
                db.commit()
            barrier = Barrier(2)

            def reserve(key):
                """Each contender owns a real independent connection and transaction."""
                with closing(sqlite3.connect(filename, timeout=10)) as db:
                    barrier.wait(timeout=10)
                    try:
                        db.execute("INSERT INTO resource_send_reservations(owner_iss,owner_sub,idem_key,period_start,units,currency) "
                                   "VALUES('synthetic','owner',?,?,1,'USD')", (key, period))
                        db.commit()
                        return "accepted"
                    except sqlite3.IntegrityError as error:
                        self.assertEqual(str(error), "outbound_quota_exhausted")
                        return "quota_rejected"

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(reserve, ("race-a", "race-b")))
            self.assertCountEqual(results, ["accepted", "quota_rejected"])
            with closing(sqlite3.connect(filename)) as db:
                self.assertEqual(db.execute("SELECT outbound_reserved,outbound_accepted,accrued_micros "
                                            "FROM resource_periods").fetchone(), (100, 0, 0))
                self.assertEqual(db.execute("SELECT SUM(units),COUNT(*) FROM resource_send_reservations")
                                 .fetchone(), (100, 2))
                self.assertEqual(db.execute("SELECT COUNT(*) FROM resource_outbox").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
