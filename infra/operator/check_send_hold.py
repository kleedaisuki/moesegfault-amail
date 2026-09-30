"""Prove the fixed realm's global public-send hold without adopting contacts.

The query intentionally references only the established send_policy schema, so
it is safe before migration 0009. Missing schema/row, ambiguous state, provider
failure, or malformed replies block deployment. Held one-use canaries remain a
separate existing contract; this does not authorize or revoke such a grant.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

from direct_contact_health import DatabaseClient, one_row
from send_control import DATABASES

HOLD_SQL = """
SELECT (SELECT COUNT(*) FROM send_policy WHERE scope='global') AS global_rows,
(SELECT COUNT(*) FROM send_policy WHERE scope='global' AND owner_iss='*'
 AND owner_sub='*' AND state='held') AS global_held
"""


def held(row: dict) -> bool:
    """Require exactly one established global row and that exact row held."""
    return all(type(row.get(key)) is int and row[key] == 1 for key in ("global_rows", "global_held"))


def main() -> int:
    """Read only fixed target coordinates and print a non-sensitive verdict."""
    parser = argparse.ArgumentParser(description="Require global public sending held")
    parser.add_argument("--target", required=True, choices=tuple(DATABASES))
    args = parser.parse_args()
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    if not re.fullmatch(r"[0-9a-f]{32}", account) or not token:
        print("send_hold=credentials_invalid", file=sys.stderr)
        return 2
    try:
        if not held(one_row(DatabaseClient(account, token, args.target).query(HOLD_SQL))):
            raise ValueError("not_held")
    except Exception:
        print("send_hold=not_proven", file=sys.stderr)
        return 1
    print("send_hold=verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
