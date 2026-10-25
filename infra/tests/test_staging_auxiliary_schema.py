"""Retained staging escrow schemas are exact contracts, not prefix exemptions."""
from __future__ import annotations

from pathlib import Path
import sqlite3
import sys
from typing import Any
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import mail_schema_contract as schema


class AuxiliarySchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.addCleanup(self.connection.close)
        files = sorted(schema.MIGRATIONS.glob("*.sql"))
        for path in files:
            self.connection.executescript(path.read_text(encoding="utf-8"))
        self.connection.execute("CREATE TABLE d1_migrations(id INTEGER PRIMARY KEY,name TEXT)")
        self.connection.executemany("INSERT INTO d1_migrations(name) VALUES(?)", [(path.name,) for path in files])

    def read(self, sql: str) -> list[dict[str, Any]]:
        return schema.rows(self.connection, sql)

    def add_auxiliary(self) -> None:
        source = (ROOT / "infra/deploy/staging-acceptance-migrations/0001_quota_escrow.sql").read_text(encoding="utf-8")
        self.connection.executescript(source)
        self.connection.executescript(source.replace("staging_acceptance_", "staging_d1_probe_"))

    def test_default_production_contract_stays_mail_only(self) -> None:
        contract = schema.expected_schema()
        self.assertEqual(len(contract.objects), 133)
        schema.verify_schema(self.read, contract)
        self.add_auxiliary()
        with self.assertRaisesRegex(ValueError, "schema_objects_unverified"):
            schema.verify_schema(self.read, contract)

    def test_staging_validates_both_exact_historical_namespaces(self) -> None:
        self.add_auxiliary()
        contract = schema.expected_schema(staging_auxiliary=True)
        self.assertEqual(len(contract.objects), 163)
        self.assertEqual(len(contract.migrations), 18)
        schema.verify_schema(self.read, contract)

    def test_mutated_auxiliary_trigger_is_not_admitted(self) -> None:
        self.add_auxiliary()
        self.connection.executescript("""DROP TRIGGER staging_d1_probe_chunks_immutable;
            CREATE TRIGGER staging_d1_probe_chunks_immutable BEFORE UPDATE ON staging_d1_probe_escrow_chunks
            BEGIN SELECT 1; END;""")
        with self.assertRaisesRegex(ValueError, "schema_object_drift"):
            schema.verify_schema(self.read, schema.expected_schema(staging_auxiliary=True))

    def test_unreviewed_prefixed_table_is_not_admitted(self) -> None:
        self.add_auxiliary()
        self.connection.execute("CREATE TABLE staging_d1_probe_unexpected(x TEXT)")
        with self.assertRaisesRegex(ValueError, "schema_objects_unverified"):
            schema.verify_schema(self.read, schema.expected_schema(staging_auxiliary=True))


if __name__ == "__main__":
    unittest.main()
