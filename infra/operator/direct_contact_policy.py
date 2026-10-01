"""Adopt exact direct-forward identity pins while atomically keeping sending held.

Adoption is not human coverage acceptance, configuration health, or permission
to deploy. Every adoption creates a fresh UUID; a changed operational commitment
also requires re-adoption. Supply all five IDs for the original no-routing-read
path, or omit all five to discover existing verified forwarding through GETs.
The destination secret is compared only in memory, never accepted as an input,
stored, or printed. Discovery does not renew health or accept human coverage.
"""

from __future__ import annotations

import os
import re
import sys
import uuid

from direct_contact_health import (
    DatabaseClient, HealthError, PIN_COLUMNS, RoutingClient, UUID, forwarding,
    one_row, rule_identifier, snapshot, validate_policy,
)
from send_control import CASE, DATABASES

ADOPT_SQL = """
INSERT INTO role_contact_policy(id,version,contract_id,destination_id,apex_abuse_rule_id,
apex_postmaster_rule_id,mail_abuse_rule_id,mail_postmaster_rule_id,actor,case_ref,updated_at)
SELECT 1,1,?1,?2,?3,?4,?5,?6,?7,?8,unixepoch()
WHERE (?9='NONE' AND NOT EXISTS(SELECT 1 FROM role_contact_policy))
   OR EXISTS(SELECT 1 FROM role_contact_policy WHERE id=1 AND version=1 AND contract_id=?9)
ON CONFLICT(id) DO UPDATE SET version=excluded.version,contract_id=excluded.contract_id,
destination_id=excluded.destination_id,apex_abuse_rule_id=excluded.apex_abuse_rule_id,
apex_postmaster_rule_id=excluded.apex_postmaster_rule_id,mail_abuse_rule_id=excluded.mail_abuse_rule_id,
mail_postmaster_rule_id=excluded.mail_postmaster_rule_id,actor=excluded.actor,
case_ref=excluded.case_ref,updated_at=excluded.updated_at
WHERE role_contact_policy.contract_id=?9
"""
READ_SQL = "SELECT contract_id FROM role_contact_policy WHERE id=1"


def discover_pins(client: RoutingClient, account: str, policy: dict, destination: str) -> None:
    """Resolve IDs from complete inventories and verify the exact pinned snapshot.

    Reject non-literal matchers rather than guessing whether a wildcard or
    catchall overlaps a reserved role. Only IDs enter the existing SQL path;
    provider bodies and the external destination remain in memory.
    """
    addresses = forwarding.pages(client, f"/accounts/{account}/email/routing/addresses")
    matches = [row for row in addresses if row.get("email") == destination]
    if (len(matches) != 1 or not isinstance(matches[0].get("verified"), str)
        or not matches[0]["verified"]):
        raise HealthError("destination_drift")
    rules = forwarding.pages(client, f"/zones/{forwarding.ZONE}/email/routing/rules")
    if forwarding.audit(rules, destination) != set(forwarding.ROLES):
        raise HealthError("route_drift")
    if any(not rule["matchers"] or any(
        matcher.get("type") != "literal" or matcher.get("field") != "to"
        or "*" in matcher.get("value", "")
        for matcher in rule["matchers"]) for rule in rules):
        raise HealthError("route_drift")
    policy["destination_id"] = matches[0].get("id")
    for role, column in zip(forwarding.ROLES, PIN_COLUMNS):
        policy[column] = rule_identifier(next(row for row in rules if role in forwarding.matched_roles(row)))
    validate_policy(policy)
    observed = (policy["destination_id"], matches[0]["verified"],
        tuple(zip(forwarding.ROLES, (policy[column] for column in PIN_COLUMNS))))
    if snapshot(client, account, policy, destination) != observed:
        raise HealthError("configuration_drift")


def main() -> int:
    """Require explicit trusted hosted adoption; never retry an ambiguous write."""
    target = os.getenv("INPUT_TARGET", "")
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    actor = os.getenv("GITHUB_ACTOR", "")
    case = os.getenv("INPUT_CASE_REF", "")
    expected = os.getenv("INPUT_EXPECTED_CONTACT_CONTRACT_ID", "")
    policy = {"version": 1, "contract_id": str(uuid.uuid4()), "observed_at": 1,
        "destination_id": os.getenv("INPUT_DESTINATION_ID", "")}
    policy.update({key: os.getenv("INPUT_" + key.upper(), "") for key in PIN_COLUMNS})
    supplied = sum(bool(policy[key]) for key in ("destination_id", *PIN_COLUMNS))
    if (os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("GITHUB_REF") != "refs/heads/main"
        or os.getenv("INPUT_CONFIRM") != "ADOPT_DIRECT_CONTACT_HELD" or target not in DATABASES
        or not re.fullmatch(r"[0-9a-f]{32}", account) or not token or not actor or not CASE.fullmatch(case)
        or (expected != "NONE" and not UUID.fullmatch(expected)) or supplied not in (0, 5)):
        print("direct_contact_policy=invalid_request", file=sys.stderr)
        return 2
    try:
        if supplied == 0:
            routing_token = os.getenv("CF_EMAIL_ROUTING_TOKEN", "")
            destination = os.getenv("ROLE_FORWARD_DESTINATION", "")
            if (not routing_token or len(destination) > 254
                or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", destination)
                or destination.rsplit("@", 1)[-1].casefold() == "moesegfault.dev"
                or destination.rsplit("@", 1)[-1].casefold().endswith(".moesegfault.dev")):
                raise HealthError("configuration_invalid")
            discover_pins(RoutingClient(routing_token, account), account, policy, destination)
        validate_policy(policy)
        database = DatabaseClient(account, token, target)
        params = [policy["contract_id"], policy["destination_id"], *(policy[key] for key in PIN_COLUMNS), f"github:{actor}", case, expected]
        try:
            database.query(ADOPT_SQL, params)
        except Exception:
            # Read exactly once before deciding whether an ambiguous adoption
            # committed. Repeating the write would create another contract.
            pass
        if one_row(database.query(READ_SQL)) != {"contract_id": policy["contract_id"]}:
            raise ValueError("not_committed")
    except Exception:
        print("direct_contact_policy=not_committed", file=sys.stderr)
        return 1
    print("direct_contact_policy=adopted_held")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
