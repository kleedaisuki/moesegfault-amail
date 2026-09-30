"""Revoke contact acceptance/configuration before reviewed routing mutations.

This production-only trusted hosted barrier requires migration 0009. It has no
routing bearer or provider mutation capability. Workflows must serialize it,
adoption, attestations and health checks with the shared non-canceling lock.
"""

from __future__ import annotations

import os
import re
import sys

from direct_contact_health import DatabaseClient, HealthError, SCHEMA_SQL, one_row
from send_control import CASE

INVALIDATE_SQL = """
UPDATE send_release_gates SET abuse_contact_verified=0,abuse_contact_contract_id=NULL,
actor=?1,case_ref=?2,updated_at=unixepoch() WHERE id=1
"""
TRIGGER_SQL = "SELECT COUNT(*) AS revoke_trigger FROM sqlite_master WHERE type='trigger' AND name='send_release_contact_revoked'"
READBACK_SQL = """
SELECT (SELECT COUNT(*) FROM send_policy WHERE scope='global') AS global_rows,
(SELECT COUNT(*) FROM send_policy WHERE scope='global' AND owner_iss='*'
 AND owner_sub='*' AND state='held') AS global_held,
(SELECT COUNT(*) FROM role_contact_health) AS health_rows,
(SELECT COUNT(*) FROM send_release_gates WHERE id=1 AND abuse_contact_verified=0
 AND abuse_contact_contract_id IS NULL AND actor=?1 AND case_ref=?2) AS contact_revoked
"""


def invalidate(database: DatabaseClient, actor: str, case: str) -> None:
    """Require acknowledged atomic revocation plus exact readback; never retry."""
    if one_row(database.query(SCHEMA_SQL)) != {"contact_tables": 4, "contact_views": 1, "contact_columns": 1}:
        raise HealthError("schema_invalid")
    row = one_row(database.query(TRIGGER_SQL))
    if type(row.get("revoke_trigger")) is not int or row["revoke_trigger"] != 1:
        raise HealthError("schema_invalid")
    params = [actor, case]
    acknowledged = False
    try:
        meta = database.query(INVALIDATE_SQL, params).get("meta")
        acknowledged = isinstance(meta, dict) and type(meta.get("changes")) is int and meta["changes"] == 1
    except Exception:
        # Read once for conservative recovery evidence. Even an already-safe
        # readback cannot turn an unacknowledged mutation into permission to
        # proceed with a routing write; an operator may explicitly rerun.
        acknowledged = False
    row = one_row(database.query(READBACK_SQL, params))
    expected = {"global_rows": 1, "global_held": 1, "health_rows": 0, "contact_revoked": 1}
    if not acknowledged or row != expected or not all(type(value) is int for value in row.values()):
        raise HealthError("invalidation_not_proven")


def main() -> int:
    """Accept only main-branch production coordinates and an opaque case."""
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    actor = os.getenv("GITHUB_ACTOR", "")
    case = os.getenv("INPUT_CASE_REF", "")
    if (os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("GITHUB_REF") != "refs/heads/main"
        or os.getenv("INPUT_TARGET", "production") != "production"
        or not re.fullmatch(r"[0-9a-f]{32}", account) or not token or not actor or not CASE.fullmatch(case)):
        print("direct_contact_invalidate=invalid_request", file=sys.stderr)
        return 2
    try:
        invalidate(DatabaseClient(account, token, "production"), f"github:{actor}", case)
    except Exception:
        print("direct_contact_invalidate=not_proven", file=sys.stderr)
        return 1
    print("direct_contact_invalidate=held_verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
