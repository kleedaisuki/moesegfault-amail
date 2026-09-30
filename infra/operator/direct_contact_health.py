"""Refresh only adopted direct-forward configuration health, never human gates.

This trusted hosted helper has no routing mutation, email-send or mailbox-access
capability. Provider errors are fixed labels; credentials and private payloads
remain in memory. Successful recovery never changes the global send hold.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "provider"))
import ensure_role_forwarding as forwarding
from send_control import DATABASES

PIN_COLUMNS = ("apex_abuse_rule_id", "apex_postmaster_rule_id", "mail_abuse_rule_id", "mail_postmaster_rule_id")
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
RUN = re.compile(r"^[0-9]{1,24}:[0-9]{1,8}:direct-v1$")
MAX_REPLY = 512_000
POLICY_SQL = "SELECT *,unixepoch() AS observed_at FROM role_contact_policy WHERE id=1 AND version=1"
WRITE_SQL = """
INSERT INTO role_contact_health(id,contract_id,state,checked_at,expires_at,run_ref)
SELECT 1,?1,?2,?3,(CASE WHEN ?2='healthy' THEN ?3+21600 ELSE 0 END),?4
FROM role_contact_policy WHERE id=1 AND version=1 AND contract_id=?1
ON CONFLICT(id) DO UPDATE SET contract_id=excluded.contract_id,state=excluded.state,
checked_at=excluded.checked_at,expires_at=excluded.expires_at,run_ref=excluded.run_ref
WHERE excluded.checked_at>role_contact_health.checked_at
   OR (excluded.checked_at=role_contact_health.checked_at
       AND excluded.state='unverified' AND role_contact_health.state='healthy')
"""
READBACK_SQL = "SELECT contract_id,state,checked_at,expires_at,run_ref FROM role_contact_health WHERE id=1"


class HealthError(Exception):
    """Carry a fixed non-secret failure category, never remote text."""


class RejectRedirect(urllib.request.HTTPRedirectHandler):
    """Do not send either bearer credential to a redirect target."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        """Reject same-origin and cross-origin redirects alike."""
        return None


OPENER = urllib.request.build_opener(RejectRedirect)


def request_json(request: urllib.request.Request) -> dict:
    """Bound network time/response bytes and suppress provider exception bodies."""
    try:
        with OPENER.open(request, timeout=20) as response:
            if response.status != 200:
                raise HealthError("provider_unavailable")
            raw = response.read(MAX_REPLY + 1)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise HealthError("provider_unavailable") from None
    if len(raw) > MAX_REPLY:
        raise HealthError("response_invalid")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise HealthError("response_invalid") from None
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise HealthError("response_invalid")
    return payload


class RoutingClient:
    """Expose only the two reviewed GET inventories to the shared paginator."""

    def __init__(self, token: str, account: str):
        """Keep the existing routing token in memory, not diagnostics."""
        self.token = token
        self.paths = (f"/accounts/{account}/email/routing/addresses?", f"/zones/{forwarding.ZONE}/email/routing/rules?")

    def request(self, method: str, path: str, body: object = None) -> dict:
        """Reject routing writes or requests outside the fixed inventory paths."""
        if method != "GET" or body is not None or not path.startswith(self.paths):
            raise HealthError("request_invalid")
        return request_json(urllib.request.Request(forwarding.API + path,
            headers={"Authorization": "Bearer " + self.token, "Accept": "application/json"}, method="GET"))


class DatabaseClient:
    """Execute fixed scoped statements in the reviewed staging/production DB."""

    def __init__(self, account: str, token: str, target: str):
        """Select a fixed database, never an arbitrary workflow-supplied ID."""
        self.url = f"{forwarding.API}/accounts/{account}/d1/database/{DATABASES[target][0]}/query"
        self.token = token

    def query(self, sql: str, params: list | None = None) -> dict:
        """Reject malformed/non-singleton D1 batch envelopes without logging them."""
        payload = request_json(urllib.request.Request(self.url,
            data=json.dumps({"sql": sql, "params": params or []}).encode(),
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"}, method="POST"))
        batches = payload.get("result")
        if not isinstance(batches, list) or len(batches) != 1 or not isinstance(batches[0], dict) or batches[0].get("success") is not True:
            raise HealthError("database_unavailable")
        return batches[0]


def one_row(batch: dict) -> dict:
    """Require exactly one object, including on ambiguous-write readback."""
    rows = batch.get("results")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise HealthError("contract_missing")
    return rows[0]


def validate_policy(row: dict) -> None:
    """Require one versioned, distinct pin set and a database observation time."""
    if (type(row.get("version")) is not int or row["version"] != 1
        or not isinstance(row.get("contract_id"), str) or not UUID.fullmatch(row["contract_id"])
        or type(row.get("observed_at")) is not int or row["observed_at"] <= 0):
        raise HealthError("contract_invalid")
    pins = [row.get(key) for key in ("destination_id", *PIN_COLUMNS)]
    if not all(isinstance(pin, str) and IDENTIFIER.fullmatch(pin) for pin in pins) or len(set(pins[1:])) != 4:
        raise HealthError("contract_invalid")


def rule_identifier(rule: dict) -> str:
    """Accept documented id/legacy tag spelling only when they do not disagree."""
    identifier = rule.get("id", rule.get("tag"))
    if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier) or (
        "id" in rule and "tag" in rule and rule["id"] != rule["tag"]):
        raise HealthError("route_drift")
    return identifier


def snapshot(client: RoutingClient, account: str, policy: dict, destination: str) -> tuple:
    """Privately verify destination identity, exact four routes and conflicts."""
    addresses = forwarding.pages(client, f"/accounts/{account}/email/routing/addresses")
    matches = [row for row in addresses if row.get("email") == destination]
    if (len(matches) != 1 or matches[0].get("id") != policy["destination_id"]
        or not isinstance(matches[0].get("verified"), str) or not matches[0]["verified"]
        or sum(row.get("id") == policy["destination_id"] for row in addresses) != 1):
        raise HealthError("destination_drift")
    rules = forwarding.pages(client, f"/zones/{forwarding.ZONE}/email/routing/rules")
    if forwarding.audit(rules, destination) != set(forwarding.ROLES):
        raise HealthError("route_drift")
    relevant = []
    for role, column in zip(forwarding.ROLES, PIN_COLUMNS):
        rule = next(row for row in rules if role in forwarding.matched_roles(row))
        identifier = rule_identifier(rule)
        if identifier != policy[column] or sum(
            row.get("id", row.get("tag")) == identifier for row in rules) != 1:
            raise HealthError("route_drift")
        relevant.append((role, identifier))
    return (policy["destination_id"], matches[0]["verified"], tuple(relevant))


def refresh(database: DatabaseClient, client: RoutingClient, account: str, destination: str, run_ref: str) -> bool:
    """Observe twice, then commit once; never retry an ambiguous renewal write."""
    policy = one_row(database.query(POLICY_SQL))
    validate_policy(policy)
    state = "unverified"
    try:
        first = snapshot(client, account, policy, destination)
        if snapshot(client, account, policy, destination) != first:
            raise HealthError("configuration_drift")
        state = "healthy"
    except Exception:
        # Every unclassified routing outcome denies. Still write the scoped
        # invalidation when D1 is reachable instead of waiting for TTL expiry.
        state = "unverified"
    params = [policy["contract_id"], state, policy["observed_at"], run_ref]
    try:
        batch = database.query(WRITE_SQL, params)
        changes = batch.get("meta", {}).get("changes")
        if type(changes) is not int or changes != 1:
            raise HealthError("observation_not_committed")
    except HealthError:
        # One exact readback resolves an ambiguous write; it is not a retry.
        pass
    row = one_row(database.query(READBACK_SQL))
    expected = {"contract_id": params[0], "state": state, "checked_at": params[2],
        "expires_at": params[2] + 21600 if state == "healthy" else 0, "run_ref": run_ref}
    if row != expected:
        raise HealthError("observation_not_committed")
    return state == "healthy"


def main() -> int:
    """Run only in a trusted main-branch hosted context and emit fixed labels."""
    target = os.getenv("INPUT_TARGET", "production")
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    routing_token = os.getenv("CF_EMAIL_ROUTING_TOKEN", "")
    destination = os.getenv("ROLE_FORWARD_DESTINATION", "")
    run_ref = f'{os.getenv("GITHUB_RUN_ID", "")}:{os.getenv("GITHUB_RUN_ATTEMPT", "")}:direct-v1'
    if (os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("GITHUB_REF") != "refs/heads/main"
        or target not in DATABASES or not re.fullmatch(r"[0-9a-f]{32}", account)
        or not token or not routing_token or not RUN.fullmatch(run_ref)
        or len(destination) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", destination)
        or destination.rsplit("@", 1)[-1].casefold() == "moesegfault.dev"
        or destination.rsplit("@", 1)[-1].casefold().endswith(".moesegfault.dev")):
        print("direct_contact_health=configuration_invalid", file=sys.stderr)
        return 2
    try:
        healthy = refresh(DatabaseClient(account, token, target), RoutingClient(routing_token, account), account, destination, run_ref)
    except Exception:
        print("direct_contact_health=not_committed", file=sys.stderr)
        return 1
    print("direct_contact_health=" + ("healthy_recorded" if healthy else "unverified_recorded"))
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
