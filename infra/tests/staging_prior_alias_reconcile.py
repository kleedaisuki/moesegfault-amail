"""Read-only reconciliation of exactly two historical staging E2E aliases.

The aliases are reconstructed in memory from the protected synthetic password
and fixed GitHub run coordinates. Never print an alias, rule, D1 row, token, or
provider response. A D1 query uses POST only as Cloudflare's read-only SQL API.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sys
import urllib.request


API = "https://api.cloudflare.com/client/v4"
ZONE = "6edff81c6ed02f412e70868076411a5e"
DB = "74f35f95-42ce-482c-86e6-dffbdd35cbbe"
DOMAIN = "mail-staging.moesegfault.dev"
ISSUER = "https://identity-staging.moesegfault.dev"
RUNS = (("first", "36524101354", "1"), ("second", "36533465672", "1"))
SQL = "SELECT state,cf_rule_id,needs_reconcile,owner_iss,owner_sub FROM addresses WHERE address=?1"
MAX_BYTES = 262_144


class ReconcileFailure(Exception):
    """A fixed diagnostic label, never raw third-party text."""


def required(name: str) -> str:
    """Read a secret without including its value in a failure."""

    value = os.environ.get(name, "")
    if not value:
        raise ReconcileFailure("configuration_missing")
    return value


def alias(password: str, run: str, attempt: str) -> str:
    """Mirror the hosted native E2E's v1 private HMAC derivation."""

    message = f"amail-staging-e2e/v1:{run}:{attempt}".encode("ascii")
    nonce = hmac.new(password.encode("utf-8"), message, hashlib.sha256).hexdigest()[:16]
    return f"e2e-{nonce}@{DOMAIN}"


def fetch(req: urllib.request.Request) -> dict:
    """Bound and parse a Cloudflare control-plane response without logging it."""

    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            raw = response.read(MAX_BYTES + 1)
            if response.status != 200 or len(raw) > MAX_BYTES:
                raise ValueError()
        value = json.loads(raw)
        if not isinstance(value, dict) or value.get("success") is not True:
            raise ValueError()
        return value
    except Exception:
        raise ReconcileFailure("control_plane_read_unverified") from None


def rules(token: str) -> list[dict]:
    """Exhaust bounded Routing Rules pages, rejecting incomplete inventories."""

    found: list[dict] = []
    total_count: int | None = None
    for page in range(1, 201):
        req = urllib.request.Request(
            f"{API}/zones/{ZONE}/email/routing/rules?per_page=50&page={page}",
            headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
            method="GET",
        )
        result = fetch(req)
        batch = result.get("result")
        info = result.get("result_info")
        if not isinstance(batch, list) or not all(isinstance(row, dict) for row in batch):
            raise ReconcileFailure("routing_inventory_unverified")
        if not isinstance(info, dict):
            raise ReconcileFailure("routing_inventory_unverified")
        per_page = info.get("per_page")
        count = info.get("count")
        available = info.get("total_count")
        if (type(info.get("page")) is not int or info["page"] != page or
                type(per_page) is not int or per_page != 50 or
                type(count) is not int or count != len(batch) or
                type(available) is not int or available < 0 or available > 10_000 or
                total_count is not None and total_count != available):
            raise ReconcileFailure("routing_inventory_unverified")
        total_count = available
        total_pages = max(1, (available + 49) // 50)
        reported = info.get("total_pages")
        if reported is not None and (type(reported) is not int or
                                     reported != total_pages and not (available == 0 and reported == 0)):
            raise ReconcileFailure("routing_inventory_unverified")
        expected_count = min(50, max(0, available - (page - 1) * 50))
        if page > total_pages or count != expected_count:
            raise ReconcileFailure("routing_inventory_unverified")
        found.extend(batch)
        if page == total_pages:
            return found
    raise ReconcileFailure("routing_inventory_unverified")


def route_absent(inventory: list[dict], target: str) -> bool:
    """Check exact literal-to route absence, not wildcard delivery behavior."""

    for rule in inventory:
        matchers = rule.get("matchers")
        if not isinstance(matchers, list):
            raise ReconcileFailure("routing_inventory_unverified")
        for matcher in matchers:
            if not isinstance(matcher, dict):
                raise ReconcileFailure("routing_inventory_unverified")
            kind, field, value = (matcher.get("type"), matcher.get("field"),
                                  matcher.get("value"))
            if not isinstance(kind, str) or field is not None and not isinstance(field, str):
                raise ReconcileFailure("routing_inventory_unverified")
            if value is not None and not isinstance(value, str):
                raise ReconcileFailure("routing_inventory_unverified")
            if kind == "literal" and field == "to" and value and value.lower() == target:
                return False
    return True


def d1_row(account: str, token: str, target: str) -> list[dict]:
    """Execute one parameterized fixed SELECT against staging D1."""

    if not SQL.startswith("SELECT "):
        raise ReconcileFailure("read_only_query_invalid")
    req = urllib.request.Request(
        f"{API}/accounts/{account}/d1/database/{DB}/query",
        data=json.dumps({"sql": SQL, "params": [target]}).encode(),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        method="POST",
    )
    result = fetch(req).get("result")
    if not isinstance(result, list) or len(result) != 1:
        raise ReconcileFailure("d1_read_unverified")
    batch = result[0]
    if not isinstance(batch, dict) or batch.get("success") is not True:
        raise ReconcileFailure("d1_read_unverified")
    rows = batch.get("results")
    if not isinstance(rows, list) or len(rows) > 1 or not all(isinstance(row, dict) for row in rows):
        raise ReconcileFailure("d1_read_unverified")
    return rows


def row_clean(rows: list[dict]) -> tuple[bool, str | None]:
    """Require a reconciled retired tombstone or an established absent row."""

    if not rows:
        return True, None
    row = rows[0]
    if set(row) != {"state", "cf_rule_id", "needs_reconcile", "owner_iss", "owner_sub"}:
        raise ReconcileFailure("d1_shape_unverified")
    owner = row["owner_sub"]
    if not isinstance(owner, str) or not 1 <= len(owner) <= 256 or any(
        ord(char) < 33 or ord(char) > 126 for char in owner
    ):
        raise ReconcileFailure("d1_shape_unverified")
    clean = (row["state"] == "retired" and row["cf_rule_id"] is None and
             type(row["needs_reconcile"]) is int and row["needs_reconcile"] == 0 and
             row["owner_iss"] == ISSUER)
    return clean, owner


def main() -> int:
    """Report only fixed per-run and overall gate labels."""

    if len(sys.argv) != 2 or sys.argv[1] != "READ_PRIOR_STAGING_ALIASES":
        print("prior_alias_gate:confirmation_required")
        return 1
    status = {label: "unverified" for label, _, _ in RUNS}
    try:
        password = required("STAGING_E2E_PASSWORD")
        route_token = required("CF_EMAIL_ROUTING_TOKEN")
        api_token = required("CLOUDFLARE_API_TOKEN")
        account = required("CLOUDFLARE_ACCOUNT_ID")
        if (not 15 <= len(password) <= 128 or
                not re.fullmatch(r"[a-f0-9]{32}", account)):
            raise ReconcileFailure("configuration_invalid")
        inventory = rules(route_token)
        owners: list[str] = []
        for label, run, attempt in RUNS:
            target = alias(password, run, attempt)
            try:
                no_route = route_absent(inventory, target)
                no_owned_row, owner = row_clean(d1_row(account, api_token, target))
                status[label] = "clean" if no_route and no_owned_row else "not_clean"
                if owner is not None:
                    owners.append(owner)
            except ReconcileFailure:
                status[label] = "unverified"
        if len(set(owners)) > 1:
            for label in status:
                status[label] = "not_clean"
    except ReconcileFailure:
        pass
    except Exception:
        pass
    for label, _, _ in RUNS:
        print(f"prior_alias_{label}:{status[label]}")
    gate = "clean" if all(value == "clean" for value in status.values()) else (
        "not_clean" if "not_clean" in status.values() else "unverified"
    )
    print(f"prior_alias_gate:{gate}")
    return 0 if gate == "clean" else 1


if __name__ == "__main__":
    raise SystemExit(main())
