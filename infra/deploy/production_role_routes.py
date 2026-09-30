"""Exact mixed production role-route shapes for bounded cutover/recovery planning.

This module does not issue a PUT. The future cutover runner must first accept
production whole-record Cron privacy and per-rule external delivery evidence,
privately preserve snapshots, and call this predicate before and after one rule
mutation. Role order is fixed; no caller-supplied recipient or Worker is accepted.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "provider"))
import ensure_role_forwarding as forwards
WORKER = "amail-role-monitor"


def snapshot(rows: list[dict], destination: str, switched: int) -> dict[str, dict]:
    """Reject duplicates, unrelated matchers, altered literals or mixed action bundles."""
    if type(switched) is not int or not 0 <= switched <= 4 or not destination:
        raise ValueError("role_transition_unreviewed")
    result = {}
    for row in rows:
        matches = forwards.matched_roles(row)
        for role in matches:
            expected = {"enabled": True, "source": "api",
                        "matchers": [{"type": "literal", "field": "to", "value": role}],
                        "actions": [{"type": "worker", "value": [WORKER]}] if forwards.ROLES.index(role) < switched
                        else [{"type": "forward", "value": [destination]}]}
            identity = row.get("id", row.get("tag"))
            if (role in result or not isinstance(identity, str) or not identity
                    or any(row.get(key) != value for key, value in expected.items())):
                raise ValueError("role_transition_conflict")
            result[role] = deepcopy(row)
    if set(result) != set(forwards.ROLES) or len({row.get("id", row.get("tag")) for row in result.values()}) != 4:
        raise ValueError("role_transition_incomplete")
    return result


def one_step(before: dict[str, dict], after: dict[str, dict], index: int, *, original: dict[str, dict] | None = None) -> bool:
    """Prove only one reserved action changed, retaining every full original shape.

    A snapshot after an ambiguous mutation is compared against both pre- and
    expected post-state. Neither an exception nor an unchanged state authorizes
    replaying SMTP or PUT. Restoration retains the role Queue producer.
    """
    if type(index) is not int or not 0 <= index < 4 or set(before) != set(forwards.ROLES) or set(after) != set(before):
        return False
    alias = forwards.ROLES[index]
    expected = deepcopy(before)
    if original is None:
        expected[alias]["actions"] = [{"type": "worker", "value": [WORKER]}]
    else:
        # A restored full privately stored original must be supplied separately;
        # do not guess the confidential destination from the active Worker rule.
        if set(original) != set(before) or not isinstance(original.get(alias), dict):
            return False
        expected[alias] = deepcopy(original[alias])
    return after == expected
