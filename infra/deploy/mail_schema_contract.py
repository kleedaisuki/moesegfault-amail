"""Verify the promoted Mail schema, including 0010, without mutating remote D1.

Expected structure comes from the complete checked-in migration chain, not from
a provider response or a caller-supplied SQL file. A migration-name row alone is
not schema evidence. This module is suitable for hosted synthetic tests; callers
must independently authorize remote reads and freeze realm writers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "crates/mail-worker/migrations"
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z_0-9]*\Z")
SCHEMA_SQL = ("SELECT type,name,tbl_name,sql FROM sqlite_master "
              "WHERE name NOT GLOB 'sqlite_*' AND name NOT IN ('d1_migrations','_cf_KV') "
              "ORDER BY type,name")
TOKEN = re.compile(r"--[^\n]*|/\*[\s\S]*?\*/|'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|"
                   r"`(?:``|[^`])*`|\[[^\]]*\]|[A-Za-z_][A-Za-z_0-9]*|[0-9]+|[^\s]")


@dataclass(frozen=True)
class SchemaContract:
    """Source-derived objects, table columns and indexes with migration provenance."""

    objects: dict[str, tuple[str, str, tuple[str, ...]]]
    columns: dict[str, list[dict]]
    indexes: dict[str, list[dict]]
    index_columns: dict[str, list[dict]]
    migrations: tuple[str, ...]


def sql_tokens(sql: str) -> tuple[str, ...]:
    """Ignore SQL layout/comments, preserving literals and conservative quoting.

    SQLite adds identifier quotes when renaming a table. Unquote only simple
    identifiers; quoted literals, expressions, predicates and defaults remain
    exact. Do not lower-case string literals or normalize whitespace inside them.
    """
    if not isinstance(sql, str) or len(sql) > 131072:
        raise ValueError("schema_sql_unverified")
    tokens = []
    for part in TOKEN.findall(sql):
        if part.startswith(("--", "/*")):
            continue
        if part.startswith(("\"", "`", "[")) and IDENTIFIER.fullmatch(part[1:-1]):
            part = part[1:-1]
        tokens.append(part if part.startswith("'") else part.casefold())
    if tokens[-1:] == [";"]:
        tokens.pop()
    return tuple(tokens)


def pragma(kind: str, name: str) -> str:
    """Construct only fixed read-only PRAGMAs for source-owned identifiers."""
    if kind not in ("table_xinfo", "index_list", "index_xinfo") or not IDENTIFIER.fullmatch(name):
        raise ValueError("schema_identifier_unverified")
    return f"PRAGMA {kind}('{name}')"


def rows(connection: sqlite3.Connection, sql: str) -> list[dict]:
    """Read a private in-memory reference without printing SQL or result rows."""
    return [dict(row) for row in connection.execute(sql).fetchall()]


def expected_schema(migration_count: int | None = None) -> SchemaContract:
    """Compile the reviewed migration chain into a disposable in-memory reference.

    This is not a Mail runtime/build or provider write. It is performed only by
    the hosted verifier/tests. The reference contains migration defaults and no
    user data; the remote database is never opened through sqlite3.
    """
    files = sorted(MIGRATIONS.glob("*.sql"))
    names = tuple(file.name for file in files)
    if ("0010_accepted_projection.sql" not in names or len(names) > 100
            or any(not re.fullmatch(r"[0-9]{4}_[a-z_]+\.sql", name) for name in names)
            or [int(name[:4]) for name in names] != list(range(1, len(names) + 1))):
        raise ValueError("migration_chain_unverified")
    if migration_count is not None:
        if type(migration_count) is not int or not 1 <= migration_count <= len(files):
            raise ValueError("migration_prefix_unverified")
        files, names = files[:migration_count], names[:migration_count]
    with sqlite3.connect(":memory:") as connection:
        connection.row_factory = sqlite3.Row
        for file in files:
            connection.executescript(file.read_text(encoding="utf-8"))
        objects = {row["name"]: (row["type"], row["tbl_name"], sql_tokens(row["sql"]))
                   for row in rows(connection, SCHEMA_SQL)}
        tables = [name for name, (kind, _, _) in objects.items() if kind == "table"]
        columns = {name: rows(connection, pragma("table_xinfo", name)) for name in tables}
        indexes = {name: rows(connection, pragma("index_list", name)) for name in tables}
        index_columns = {row["name"]: rows(connection, pragma("index_xinfo", row["name"]))
                         for values in indexes.values() for row in values}
    return SchemaContract(objects, columns, indexes, index_columns, names)


def verify_recorded_schema(read: Callable[[str], list[dict]]) -> int:
    """Inspect an exact source migration prefix before separately authorized DDL.

    At least migration 0006's held policy/grant schema must already exist. The
    prefix must be uninterrupted and its entire resulting structure must match;
    reading a migration-name row never makes an unknown structure acceptable.
    This prefix check cannot admit a fenced runtime: that always requires the
    complete ``verify_schema`` contract after migrations.
    """
    complete = expected_schema()
    recorded = read("SELECT name FROM d1_migrations ORDER BY id")
    if (not isinstance(recorded, list) or not 6 <= len(recorded) <= len(complete.migrations)
            or recorded != [{"name": name} for name in complete.migrations[:len(recorded)]]):
        raise ValueError("bootstrap_schema_prefix_unverified")
    verify_schema(read, expected_schema(len(recorded)))
    return len(recorded)


def keyed(values: list[dict], key: str) -> dict[str, dict]:
    """Reject duplicate/unknown records instead of silently overwriting them."""
    if not isinstance(values, list) or len(values) > 1000:
        raise ValueError("schema_rows_unverified")
    result = {}
    for value in values:
        if not isinstance(value, dict) or not isinstance(value.get(key), str) or value[key] in result:
            raise ValueError("schema_rows_unverified")
        result[value[key]] = value
    return result


def verify_schema(read: Callable[[str], list[dict]], contract: SchemaContract | None = None) -> None:
    """Require exact objects, columns/defaults, index uniqueness/order and migrations.

    ``read`` must be a bounded private remote SELECT/PRAGMA reader for the exact
    authorized realm. A supplied contract is an internal synthetic-test seam,
    never a command-line/operator override. Verification neither drains old work
    nor authorizes runtime deployment, Cron, sending or retained-record privacy.
    """
    expected = contract or expected_schema()
    actual = keyed(read(SCHEMA_SQL), "name")
    if set(actual) != set(expected.objects):
        raise ValueError("schema_objects_unverified")
    for name, (kind, table, tokens) in expected.objects.items():
        row = actual[name]
        if (set(row) != {"type", "name", "tbl_name", "sql"} or row["type"] != kind
                or row["tbl_name"] != table or sql_tokens(row["sql"]) != tokens):
            raise ValueError("schema_object_drift")
    for name, expected_columns in expected.columns.items():
        if read(pragma("table_xinfo", name)) != expected_columns:
            raise ValueError("schema_columns_unverified")
        # PRAGMA index_list sequence is engine bookkeeping, not index semantics.
        indexes = keyed(read(pragma("index_list", name)), "name")
        baseline = keyed(expected.indexes[name], "name")
        strip_seq = lambda value: {key: item for key, item in value.items() if key != "seq"}
        if ({key: strip_seq(value) for key, value in indexes.items()}
                != {key: strip_seq(value) for key, value in baseline.items()}):
            raise ValueError("schema_indexes_unverified")
    for name, columns in expected.index_columns.items():
        if read(pragma("index_xinfo", name)) != columns:
            raise ValueError("schema_index_columns_unverified")
    migrations = read("SELECT name FROM d1_migrations ORDER BY id")
    if migrations != [{"name": name} for name in expected.migrations]:
        raise ValueError("schema_migration_provenance_unverified")
