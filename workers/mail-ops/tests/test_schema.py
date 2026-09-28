"""Verify D1-compatible SQLite state/audit constraints without report content.

中文：验证运营工单的 SQLite 状态与审计约束，不使用真实邮件。
English: Verify case state/audit constraints using synthetic rows only.
"""

from pathlib import Path
import sqlite3
import unittest


SCHEMA = (Path(__file__).resolve().parents[1] / "migrations" / "0001_cases.sql").read_text(
    encoding="utf-8"
)


class SchemaContract(unittest.TestCase):
    """Status transitions must produce atomic action records.

    中文：状态变更必须原子地产生操作审计。
    """

    def test_receipt_review_reopen_and_close(self):
        """A case transition cannot silently miss an audit action.

        中文：工单状态变化不能遗漏审计动作。
        """

        db = sqlite3.connect(":memory:")
        db.executescript(SCHEMA)
        db.execute(
            "INSERT INTO cases(id,route,object_key,state,size_bytes) VALUES(?,?,?,?,?)",
            ("synthetic", "abuse", "reports/synthetic.eml", "receiving", 123),
        )
        for state, actor in [
            ("failed", "system"), ("open", "system"), ("reviewed", "operator-1"),
            ("open", "operator-1"), ("closed", "operator-1"),
            ("expiring", "system"),
        ]:
            db.execute(
                "UPDATE cases SET state=?,last_actor_sub=? WHERE id='synthetic'",
                (state, actor),
            )
        actions = [row[0] for row in db.execute(
            "SELECT action FROM case_audit WHERE case_id='synthetic' ORDER BY id"
        )]
        self.assertEqual(actions, ["received", "reviewed", "reopened", "closed"])

    def test_invalid_role_or_state_is_rejected(self):
        """The dedicated DB cannot accidentally store a user alias.

        中文：专属数据库不能误存用户邮箱地址作为角色。
        """

        db = sqlite3.connect(":memory:")
        db.executescript(SCHEMA)
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO cases(id,route,object_key,state,size_bytes) VALUES(?,?,?,?,?)",
                ("synthetic", "alice@mail.moesegfault.dev", "reports/synthetic.eml", "open", 123),
            )


if __name__ == "__main__":
    unittest.main()
