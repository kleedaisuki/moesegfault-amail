"""Exercise the isolated role-monitor SQL contract on hosted CI. / 在托管 CI 上验证独立角色监控 SQL 契约。"""

from __future__ import annotations

import pathlib
import sqlite3
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SQL = ROOT / "workers" / "role-monitor" / "migrations" / "0001_role_monitor.sql"


class RoleMonitorSchemaTests(unittest.TestCase):
    """Check fail-closed lease defaults and content-free arrival storage. / 检查失效租约默认值与无正文存储。"""

    def setUp(self) -> None:
        """Create a fresh in-memory database for each invariant. / 为每个不变量创建全新内存数据库。"""

        self.db = sqlite3.connect(":memory:")
        self.db.executescript(SQL.read_text(encoding="utf-8"))

    def tearDown(self) -> None:
        """Close the test database. / 关闭测试数据库。"""

        self.db.close()

    def test_lease_initially_denies_and_is_singleton(self) -> None:
        """Only Cron may set a positive lease after explicit checks. / 只有经过检查的 Cron 才能设置正租约。"""

        self.assertEqual(
            self.db.execute(
                "SELECT singleton,lease_until,checked_at FROM role_monitor_health"
            ).fetchall(),
            [(1, 0, 0)],
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO role_monitor_health(singleton,lease_until,checked_at) VALUES(2,1,1)"
            )

    def test_arrivals_keep_no_report_content(self) -> None:
        """The durable schema cannot store sender, MIME, subject or destination. / 持久模式不能储存发件人、MIME、主题或目的地。"""

        columns = {
            row[1] for row in self.db.execute("PRAGMA table_info(role_arrivals)")
        }
        self.assertEqual(
            columns,
            {"arrival_seq", "id", "role", "received_at", "forward_state", "forward_updated_at", "alerted_at"},
        )
        self.db.execute(
            "INSERT INTO role_arrivals(id,role,received_at) VALUES('opaque','apex_abuse',1000)"
        )
        self.assertEqual(
            self.db.execute(
                "SELECT forward_state,alerted_at FROM role_arrivals WHERE id='opaque'"
            ).fetchone(),
            ("unknown", None),
        )

    def test_delayed_insert_is_not_falsely_marked_alerted(self) -> None:
        """Immutable sequence snapshots avoid the D1 select/update race. / 不可变序列快照避免 D1 查询与更新竞争。"""

        self.db.execute(
            "INSERT INTO role_arrivals(id,role,received_at) VALUES('first','apex_abuse',1000)"
        )
        cutoff = 2000
        snapshot = self.db.execute(
            "SELECT MAX(arrival_seq) FROM role_arrivals WHERE alerted_at IS NULL AND received_at<?",
            (cutoff,),
        ).fetchone()[0]
        self.db.execute(
            "INSERT INTO role_arrivals(id,role,received_at) VALUES('late','apex_abuse',1000)"
        )
        self.db.execute(
            "UPDATE role_arrivals SET alerted_at=3000 WHERE alerted_at IS NULL AND received_at<? AND arrival_seq<=?",
            (cutoff, snapshot),
        )
        self.assertEqual(
            self.db.execute("SELECT id,alerted_at FROM role_arrivals ORDER BY arrival_seq").fetchall(),
            [("first", 3000), ("late", None)],
        )


if __name__ == "__main__":
    unittest.main()
