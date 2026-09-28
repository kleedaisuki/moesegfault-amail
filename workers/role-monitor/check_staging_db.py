"""Reject accidental reuse of a non-role D1 database before migration. / 迁移前拒绝复用非角色 D1 数据库。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


SQL = (
    "SELECT name FROM sqlite_master WHERE type='table' "
    "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'd1_%'"
)
ALLOWED = {"role_arrivals", "role_monitor_health"}
ARRIVAL_COLUMNS = {
    "arrival_seq", "id", "role", "received_at", "forward_state", "forward_updated_at", "alerted_at"
}
HEALTH_COLUMNS = {"singleton", "lease_until", "checked_at"}


def query(target: str, sql: str) -> list[dict]:
    """Read one bounded Wrangler JSON result without printing private data. / 读取有界 Wrangler JSON 结果且不打印私有数据。"""

    command = ["wrangler", "d1", "execute", "ROLE_MONITOR", "--remote", "--command", sql, "--json"]
    if target == "staging":
        command.extend(["--env", "staging"])
    result = subprocess.run(
        command,
        cwd="workers/role-monitor",
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if result.returncode or len(result.stdout) > 262_144:
        raise ValueError("Role D1 inventory unavailable")
    try:
        data = json.loads(result.stdout)
        rows = data[0]["results"]
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise TypeError
        return rows
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise ValueError("Role D1 inventory shape invalid") from error


def valid_schema(arrivals: list[dict], health: list[dict]) -> bool:
    """Require the reviewed sequence snapshot schema before reusing a migrated D1. / 复用已迁移 D1 前必须具备经过审查的序列快照模式。"""

    arrival_names = {row.get("name") for row in arrivals}
    health_names = {row.get("name") for row in health}
    arrival_seq = next((row for row in arrivals if row.get("name") == "arrival_seq"), {})
    health_pk = next((row for row in health if row.get("name") == "singleton"), {})
    return (
        arrival_names == ARRIVAL_COLUMNS
        and health_names == HEALTH_COLUMNS
        and arrival_seq.get("type") == "INTEGER"
        and arrival_seq.get("pk") == 1
        and health_pk.get("type") == "INTEGER"
        and health_pk.get("pk") == 1
    )


def main() -> int:
    """Inspect one explicit isolated binding and output non-sensitive status. / 检查一个显式独立绑定并输出无敏感信息的状态。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=("staging", "production"), default="staging")
    target = parser.parse_args().env

    try:
        names = {row["name"] for row in query(target, SQL)}
        if names == ALLOWED and not valid_schema(
            query(target, "PRAGMA table_info(role_arrivals)"),
            query(target, "PRAGMA table_info(role_monitor_health)"),
        ):
            print("Role D1 schema does not match reviewed sequence snapshot", file=sys.stderr)
            return 1
    except (KeyError, TypeError, ValueError):
        print("Role D1 inventory unavailable or malformed", file=sys.stderr)
        return 1
    if not names.issubset(ALLOWED):
        print("Role D1 contains unrelated tables; refusing migration", file=sys.stderr)
        return 1
    if names and names != ALLOWED:
        print("Role D1 is partially migrated; review required", file=sys.stderr)
        return 1
    print("Role D1 is empty or contains only the role-monitor schema")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
