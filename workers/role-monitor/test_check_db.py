"""Contract tests for isolated D1 reuse guards. / 独立 D1 复用防护的契约测试。"""

from __future__ import annotations

import unittest
import sqlite3

import check_staging_db as guard


def columns(names: set[str], primary: str) -> list[dict]:
    """Represent the provider's PRAGMA table_info rows. / 表示供应商 PRAGMA table_info 行。"""

    return [
        {"name": name, "type": "INTEGER" if name == primary else "TEXT", "pk": 1 if name == primary else 0}
        for name in names
    ]


class RoleDbGuardTests(unittest.TestCase):
    """Reject previously applied migrations with a stale schema. / 拒绝模式已过期的历史迁移。"""

    def test_reviewed_schema_passes(self) -> None:
        """The sequence snapshot and lease singleton are required. / 必须有序列快照与租约单例。"""

        self.assertTrue(
            guard.valid_schema(
                columns(guard.ARRIVAL_COLUMNS, "arrival_seq"),
                columns(guard.HEALTH_COLUMNS, "singleton"),
            )
        )

    def test_old_schema_without_sequence_is_rejected(self) -> None:
        """An applied old migration must not skip the race fix. / 已应用旧迁移不得绕过竞态修复。"""

        old = guard.ARRIVAL_COLUMNS - {"arrival_seq"}
        self.assertFalse(
            guard.valid_schema(columns(old, "id"), columns(guard.HEALTH_COLUMNS, "singleton"))
        )

    def test_missing_lease_column_is_rejected(self) -> None:
        """A partial health table cannot authorize sending. / 不完整的健康表不得授权发信。"""

        self.assertFalse(
            guard.valid_schema(
                columns(guard.ARRIVAL_COLUMNS, "arrival_seq"),
                columns(guard.HEALTH_COLUMNS - {"lease_until"}, "singleton"),
            )
        )

    def test_provider_internal_table_is_not_an_application_collision(self) -> None:
        """Ignore only Cloudflare's exact internal table, never arbitrary names."""

        db = sqlite3.connect(":memory:")
        try:
            db.execute('CREATE TABLE "_cf_KV" (k TEXT)')
            self.assertEqual(db.execute(guard.SQL).fetchall(), [])
            db.execute('CREATE TABLE "_cf_KV_other" (k TEXT)')
            self.assertEqual(db.execute(guard.SQL).fetchall(), [("_cf_KV_other",)])
            db.execute('CREATE TABLE "d1_unrelated" (k TEXT)')
            self.assertEqual(
                set(db.execute(guard.SQL).fetchall()),
                {("_cf_KV_other",), ("d1_unrelated",)},
            )
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
