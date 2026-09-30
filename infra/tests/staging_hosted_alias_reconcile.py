"""Read-only reconciliation of one exact hosted staging E2E alias.

The caller supplies the GitHub Actions run ID and attempt recorded for a
completed hosted E2E run. The alias is derived privately using the same HMAC
contract as that run. No alias, provider response, D1 row, or credential is
printed. D1's HTTP POST endpoint is used only for a bound SELECT.
"""

from __future__ import annotations

import re
import sys

from staging_prior_alias_reconcile import (
    ReconcileFailure,
    alias,
    d1_row,
    required,
    route_absent,
    row_clean,
    rules,
)


CONFIRM = "READ_ONE_STAGING_ALIAS"


def coordinates(args: list[str]) -> tuple[str, str]:
    """Validate explicit GitHub run coordinates before loading secrets."""

    if len(args) != 4 or args[1] != CONFIRM:
        raise ReconcileFailure("confirmation_required")
    run, attempt = args[2:]
    if not re.fullmatch(r"[1-9][0-9]{0,19}", run) or not re.fullmatch(
        r"[1-9][0-9]{0,2}", attempt
    ):
        raise ReconcileFailure("coordinates_invalid")
    return run, attempt


def main() -> int:
    """Fail closed using only fixed route, row, and aggregate labels."""

    route_status = "unverified"
    row_status = "unverified"
    try:
        run, attempt = coordinates(sys.argv)
        password = required("STAGING_E2E_PASSWORD")
        route_token = required("CF_EMAIL_ROUTING_TOKEN")
        api_token = required("CLOUDFLARE_API_TOKEN")
        account = required("CLOUDFLARE_ACCOUNT_ID")
        if not 15 <= len(password) <= 128 or not re.fullmatch(r"[a-f0-9]{32}", account):
            raise ReconcileFailure("configuration_invalid")
        target = alias(password, run, attempt)
        try:
            route_status = "absent" if route_absent(rules(route_token), target) else "present"
        except Exception:
            pass
        try:
            row_status = "clean" if row_clean(d1_row(account, api_token, target))[0] else "not_clean"
        except Exception:
            pass
    except Exception:
        # Third-party exceptions can contain addresses and URLs. Never expose
        # even a sanitized copy: fixed gate labels are enough for this check.
        pass
    print(f"hosted_alias_route:{route_status}")
    print(f"hosted_alias_row:{row_status}")
    gate = "clean" if route_status == "absent" and row_status == "clean" else (
        "not_clean" if route_status == "present" or row_status == "not_clean" else "unverified"
    )
    print(f"hosted_alias_gate:{gate}")
    return 0 if gate == "clean" else 1


if __name__ == "__main__":
    raise SystemExit(main())
