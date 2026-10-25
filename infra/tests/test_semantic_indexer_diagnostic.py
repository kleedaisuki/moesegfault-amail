"""Operational diagnostics project only closed aggregate state, without mail."""
from __future__ import annotations

from pathlib import Path
import sys
from typing import Any
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import staging_semantic_recovery as recovery


class IndexerDiagnosticTests(unittest.TestCase):
    def database(self) -> Mock:
        database = Mock()
        database.query.side_effect = [
            {"results": [{"blocked_until": 2000, "observed_at": 1000, "last_error_code": "provider_transient"}]},
            {"results": [{"enabled": 0, "state": "pending", "error_code": "none", "bucket": "due", "attempted": 0, "work_count": 2}]},
            {"results": [{"enabled": 0, "accounts": 1}]},
            {"results": [{"live_profile_sessions": 0, "sessions_with_semantics_enabled": 0}]},
        ]
        return database

    def test_closed_aggregate_projection_reports_cooldown_and_cleanup_state(self) -> None:
        database = self.database()
        result = recovery.indexer_facts(database)
        self.assertEqual(result["dependency"]["remaining_ms"], 1000)
        self.assertEqual(result["dependency"]["last_error_code"], "provider_transient")
        self.assertEqual(result["preference_counts"], [{"enabled": 0, "accounts": 1}])
        self.assertEqual(len(database.query.call_args_list), 4)
        for call in database.query.call_args_list:
            sql = call.args[0].strip()
            self.assertTrue(sql.startswith("SELECT"))
            self.assertNotIn("body_text", sql)
            self.assertNotIn("subject", sql)
            self.assertNotIn("embedding_json", sql)

    def test_unexpected_dependency_text_is_not_logged(self) -> None:
        database = self.database()
        rows: list[dict[str, Any]] = [
            {"results": [{"blocked_until": 0, "observed_at": 1000, "last_error_code": "private provider prose"}]},
            {"results": []}, {"results": []},
            {"results": [{"live_profile_sessions": 0, "sessions_with_semantics_enabled": 0}]},
        ]
        database.query.side_effect = rows
        result = recovery.indexer_facts(database)
        self.assertEqual(result["dependency"]["last_error_code"], "unrecognized")
        self.assertNotIn("private provider prose", str(result))

    def test_unexpected_aggregate_field_is_rejected_not_exported(self) -> None:
        database = self.database()
        database.query.side_effect = [
            {"results": [{"blocked_until": 0, "observed_at": 1000, "last_error_code": None}]},
            {"results": [{"enabled": 0, "state": "pending", "error_code": "none", "bucket": "due", "attempted": 0,
                          "work_count": 2, "private": "must not export"}]},
            {"results": []},
            {"results": [{"live_profile_sessions": 0, "sessions_with_semantics_enabled": 0}]},
        ]
        with self.assertRaisesRegex(ValueError, "staging_semantic_aggregate_unverified"):
            recovery.indexer_facts(database)


if __name__ == "__main__":
    unittest.main()
