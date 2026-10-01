"""Hosted-only exact schema regression fixtures; no provider access or project build."""

from copy import deepcopy
from pathlib import Path
import sqlite3
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import mail_schema_contract as schema


class SchemaTests(unittest.TestCase):
    """Check exact promoted schema and material malformed/partial provider readbacks."""

    def setUp(self):
        """Compile source migrations into independent hosted in-memory expected state."""
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        for file in sorted(schema.MIGRATIONS.glob("*.sql")):
            self.connection.executescript(file.read_text(encoding="utf-8"))
        self.connection.execute("CREATE TABLE d1_migrations(id INTEGER PRIMARY KEY, name TEXT)")
        self.connection.executemany("INSERT INTO d1_migrations(name) VALUES(?)",
                                    [(file.name,) for file in sorted(schema.MIGRATIONS.glob("*.sql"))])
        self.addCleanup(self.connection.close)

    def read(self, sql):
        """Supply private provider-shaped rows without remote transport."""
        return schema.rows(self.connection, sql)

    def test_complete_source_schema(self):
        """Exact migration names, objects, columns, indexes and dependencies pass."""
        schema.verify_schema(self.read)

    def test_exact_recorded_prefix_before_separate_migration(self):
        """A complete held-schema prefix may be inspected but never substitutes for 0010."""
        files = sorted(schema.MIGRATIONS.glob("*.sql"))[:6]
        with sqlite3.connect(":memory:") as connection:
            connection.row_factory = sqlite3.Row
            for file in files:
                connection.executescript(file.read_text(encoding="utf-8"))
            connection.execute("CREATE TABLE d1_migrations(id INTEGER PRIMARY KEY,name TEXT)")
            connection.executemany("INSERT INTO d1_migrations(name) VALUES(?)", [(file.name,) for file in files])
            read = lambda sql: schema.rows(connection, sql)
            self.assertEqual(schema.verify_recorded_schema(read), 6)
            with self.assertRaises(ValueError):
                schema.verify_schema(read)
            connection.execute("DELETE FROM d1_migrations WHERE id=6")
            with self.assertRaises(ValueError):
                schema.verify_recorded_schema(read)

    def test_comments_case_and_rename_identifier_quotes(self):
        """Layout is immaterial while literal whitespace and case stay material."""
        self.assertEqual(schema.sql_tokens('CREATE TABLE "send_requests" (x TEXT); -- ignored'),
                         schema.sql_tokens("create table send_requests (x text)"))
        self.assertNotEqual(schema.sql_tokens("WHEN s.state='accepted'"),
                            schema.sql_tokens("WHEN s.state='Accepted'"))
        self.assertNotEqual(schema.sql_tokens("DEFAULT ' a '"), schema.sql_tokens("DEFAULT 'a'"))

    def test_index_uniqueness_and_missing_dependency_fail(self):
        """A same-named unique index or removed embedding trigger is not 0010."""
        for sql in ("DROP INDEX send_requests_message_state; CREATE UNIQUE INDEX "
                    "send_requests_message_state ON send_requests(message_id,state)",
                    "DROP TRIGGER messages_embedding_finished"):
            with self.subTest(sql=sql):
                self.connection.execute("SAVEPOINT altered")
                # executescript commits pending savepoints; execute each statement instead.
                for statement in sql.split(";"):
                    self.connection.execute(statement)
                with self.assertRaises(ValueError):
                    schema.verify_schema(self.read)
                self.connection.execute("ROLLBACK TO altered")
                self.connection.execute("RELEASE altered")

    def test_column_default_and_trigger_predicate_fail(self):
        """Wrong leases/defaults or trigger scope never pass via a migration-name row."""
        def altered(sql):
            values = deepcopy(self.read(sql))
            if sql == schema.pragma("table_xinfo", "send_requests"):
                next(row for row in values if row["name"] == "index_projection_lease_until")["dflt_value"] = "1"
            return values
        with self.assertRaises(ValueError):
            schema.verify_schema(altered)
        def bad_trigger(sql):
            values = deepcopy(self.read(sql))
            if sql == schema.SCHEMA_SQL:
                row = next(row for row in values if row["name"] == "messages_outbound_projection_requeue")
                row["sql"] = row["sql"].replace("s.state='accepted'", "s.state='sent'")
            return values
        with self.assertRaises(ValueError):
            schema.verify_schema(bad_trigger)

    def test_extra_duplicate_object_and_migration_fail(self):
        """Unknown views, duplicate provider rows and missing provenance fail closed."""
        self.connection.execute("CREATE VIEW accidental_view AS SELECT 1")
        with self.assertRaises(ValueError):
            schema.verify_schema(self.read)
        self.connection.execute("DROP VIEW accidental_view")
        def duplicate(sql):
            values = self.read(sql)
            return values + values[:1] if sql == schema.SCHEMA_SQL else values
        with self.assertRaises(ValueError):
            schema.verify_schema(duplicate)
        self.connection.execute("DELETE FROM d1_migrations WHERE name='0010_accepted_projection.sql'")
        with self.assertRaises(ValueError):
            schema.verify_schema(self.read)


if __name__ == "__main__":
    unittest.main()
