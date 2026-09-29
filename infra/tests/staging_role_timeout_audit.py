"""Read only aggregate evidence for the first failed staging role SMTP run.

The provider's D1 query endpoint uses POST for a parameterized SELECT. This
diagnostic never requests an arrival row, envelope, rule target, or provider
body, and emits only fixed labels. It is not a delivery or Cron acceptance.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "workers/role-monitor"))
import acceptance as role_probe
import hosted_acceptance as hosted


RUN = "36603362864"
CONFIRM = "READ_FIRST_ROLE_SMTP_AGGREGATES"
DATABASE = "272e024c-453a-461b-bea0-c37a62c89d24"
API = "https://api.cloudflare.com/client/v4"
MAX_RESPONSE = 262_144
# The first interval is the hosted job's observed lifetime. The second is a
# separate, bounded delayed-ingress check; it cannot turn a timeout into pass.
START = 1790701988000  # 2026-09-29 17:13:08 UTC
END = 1790703041000    # 2026-09-29 17:30:41 UTC
LATE_END = 1790703900000  # 2026-09-29 17:45:00 UTC

SQL = """SELECT
  SUM(CASE WHEN role='staging_probe' AND received_at>=?1 AND received_at<?2 THEN 1 ELSE 0 END) AS on_n,
  SUM(CASE WHEN role='staging_probe' AND received_at>=?1 AND received_at<?2 AND forward_state='unknown' THEN 1 ELSE 0 END) AS on_unknown,
  SUM(CASE WHEN role='staging_probe' AND received_at>=?1 AND received_at<?2 AND forward_state='accepted' THEN 1 ELSE 0 END) AS on_accepted,
  SUM(CASE WHEN role='staging_probe' AND received_at>=?1 AND received_at<?2 AND alerted_at IS NULL THEN 1 ELSE 0 END) AS on_pending,
  SUM(CASE WHEN role='staging_probe' AND received_at>=?1 AND received_at<?2 AND alerted_at IS NOT NULL THEN 1 ELSE 0 END) AS on_marked,
  SUM(CASE WHEN role='staging_probe' AND received_at>=?2 AND received_at<?3 THEN 1 ELSE 0 END) AS late_n,
  SUM(CASE WHEN role='staging_probe' AND received_at>=?2 AND received_at<?3 AND forward_state='unknown' THEN 1 ELSE 0 END) AS late_unknown,
  SUM(CASE WHEN role='staging_probe' AND received_at>=?2 AND received_at<?3 AND forward_state='accepted' THEN 1 ELSE 0 END) AS late_accepted,
  SUM(CASE WHEN role='staging_probe' AND received_at>=?2 AND received_at<?3 AND alerted_at IS NULL THEN 1 ELSE 0 END) AS late_pending,
  SUM(CASE WHEN role='staging_probe' AND received_at>=?2 AND received_at<?3 AND alerted_at IS NOT NULL THEN 1 ELSE 0 END) AS late_marked,
  (SELECT checked_at FROM role_monitor_health WHERE singleton=1) AS checked_at,
  (SELECT lease_until FROM role_monitor_health WHERE singleton=1) AS lease_until
FROM role_arrivals WHERE role='staging_probe' AND received_at>=?1 AND received_at<?3"""
COUNTS = (
    "on_n", "on_unknown", "on_accepted", "on_pending", "on_marked",
    "late_n", "late_unknown", "late_accepted", "late_pending", "late_marked",
)


class AuditError(Exception):
    """A fixed, non-sensitive failure label."""


class RejectRedirect(urllib.request.HTTPRedirectHandler):
    """Keep the D1 bearer token off any redirected origin."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        """Return a 30x error to the caller without following its Location."""

        return None


_NO_REDIRECT = urllib.request.build_opener(RejectRedirect)


def query(account: str, token: str) -> dict:
    """Retrieve exactly one bounded aggregate row from isolated staging D1."""

    request = urllib.request.Request(
        f"{API}/accounts/{account}/d1/database/{DATABASE}/query",
        data=json.dumps({"sql": SQL, "params": [START, END, LATE_END]}).encode(),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with _NO_REDIRECT.open(request, timeout=30) as response:
            status, raw = response.status, response.read(MAX_RESPONSE + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        raise AuditError("d1_unavailable") from None
    if status != 200 or len(raw) > MAX_RESPONSE:
        raise AuditError("d1_unavailable")
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise ValueError
        batches = payload.get("result")
        if not isinstance(batches, list) or len(batches) != 1 or batches[0].get("success") is not True:
            raise ValueError
        rows = batches[0].get("results")
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            raise ValueError
        row = rows[0]
    except (AttributeError, IndexError, TypeError, ValueError):
        raise AuditError("d1_shape_invalid") from None
    if set(row) != {*COUNTS, "checked_at", "lease_until"}:
        raise AuditError("d1_shape_invalid")
    # SQLite SUM on an empty table is NULL, while this SELECT still returns one row.
    for name in COUNTS:
        if row[name] is None:
            row[name] = 0
        if type(row[name]) is not int or row[name] < 0:
            raise AuditError("d1_shape_invalid")
    for prefix in ("on", "late"):
        if row[prefix + "_n"] != row[prefix + "_unknown"] + row[prefix + "_accepted"]:
            raise AuditError("d1_shape_invalid")
        if row[prefix + "_n"] != row[prefix + "_pending"] + row[prefix + "_marked"]:
            raise AuditError("d1_shape_invalid")
    if any(type(row[key]) is not int or row[key] < 0 for key in ("checked_at", "lease_until")):
        raise AuditError("d1_shape_invalid")
    return row


def bucket(count: int) -> str:
    """Suppress exact cardinalities above one; duplicates defeat attribution."""

    return "zero" if count == 0 else "one" if count == 1 else "multiple"


def state(row: dict, prefix: str, positive: str, negative: str) -> str:
    """Classify one aggregate without exposing a private row or count."""

    if row[prefix + "_n"] == 0:
        return "none"
    a, b = row[prefix + "_" + positive], row[prefix + "_" + negative]
    return positive if a and not b else negative if b and not a else "mixed"


def health(row: dict) -> tuple[str, str]:
    """Treat a later singleton overwrite as unknowable historical evidence."""

    checked, lease = row["checked_at"], row["lease_until"]
    if checked >= END:
        return "overwritten", "overwritten"
    if checked < START:
        return "no", "no"
    return "yes", "yes" if checked < lease <= checked + 30 * 60 * 1000 else "no"


def provider_state(zone: str, routing: str, account: str, token: str, expected: str) -> tuple[str, str, str]:
    """Read current route, four direct forwards, and 100%-serving version."""

    route, forwards, version = "unverified", "unverified", "unverified"
    try:
        route = role_probe.ROUTE.reconcile(zone, routing, "audit")
        role_probe.standard_rules(zone, routing)
        forwards = "four_direct"
    except Exception:
        pass
    try:
        actual, _ = hosted.active_version(account, token)
        version = "match" if actual == expected else "drift"
    except Exception:
        pass
    return route, forwards, version


def main() -> int:
    """Print only allowlisted aggregate classifications, even on failure."""

    if sys.argv != [sys.argv[0], CONFIRM, RUN]:
        print("role_timeout_audit=coordinates_invalid")
        return 1
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    routing = os.environ.get("CF_EMAIL_ROUTING_TOKEN", "")
    zone = os.environ.get("CF_ZONE_ID", "")
    expected = os.environ.get("AMAIL_STAGING_ROLE_VERSION", "").lower()
    if (not re.fullmatch(r"[a-f0-9]{32}", account) or not token or not routing
            or zone != role_probe.ZONE or not hosted.valid_uuid(expected)):
        print("role_timeout_audit=configuration_invalid")
        return 1
    route, forwards, version = provider_state(zone, routing, account, token, expected)
    print(f"role_timeout_route={route}")
    print(f"role_timeout_standard_rules={forwards}")
    print(f"role_timeout_worker_version={version}")
    try:
        row = query(account, token)
    except AuditError as error:
        print(f"role_timeout_audit={error}")
        return 1
    checked, lease = health(row)
    print(f"role_timeout_arrival={bucket(row['on_n'])}")
    print(f"role_timeout_forward={state(row, 'on', 'unknown', 'accepted')}")
    print(f"role_timeout_alert={state(row, 'on', 'pending', 'marked')}")
    print(f"role_timeout_late_arrival={bucket(row['late_n'])}")
    print(f"role_timeout_late_forward={state(row, 'late', 'unknown', 'accepted')}")
    print(f"role_timeout_late_alert={state(row, 'late', 'pending', 'marked')}")
    print(f"role_timeout_health_checked_during_probe={checked}")
    print(f"role_timeout_lease_renewed_during_probe={lease}")
    print("role_timeout_audit=read_only_snapshot")
    return 0 if route == "absent" and forwards == "four_direct" and version == "match" else 1


if __name__ == "__main__":
    raise SystemExit(main())
