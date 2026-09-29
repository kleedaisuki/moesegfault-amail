"""Read-only, aggregate-only D1 audit for the fifth hosted E2E run.

The exact alias exists only in memory. Cloudflare's D1 query endpoint uses
HTTP POST for a parameterized SELECT; this script never prints provider data.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request

from staging_prior_alias_reconcile import (
    API, DB, ISSUER, ReconcileFailure, alias, fetch, required, route_absent, rules,
)


RUN = "36589042183"
ATTEMPT = "1"
CONFIRM = "READ_FIFTH_MAIL_AGGREGATES"
SQL = """WITH exact_address AS (
    SELECT state,needs_reconcile,owner_iss,owner_sub
    FROM addresses WHERE address=?1
), matching AS (
    SELECT m.direction,m.deleted_at,m.subject=?3 AS signal,m.subject=?4 AS distractor,
           m.embedding_json IS NOT NULL AS embedded,w.state AS work_state
    FROM messages m JOIN exact_address a
      ON m.owner_iss=a.owner_iss AND m.owner_sub=a.owner_sub
    LEFT JOIN embedding_work w ON w.message_id=m.id
    WHERE m.address=?1 AND a.owner_iss=?2
)
SELECT
    (SELECT state FROM exact_address) AS address_state,
    (SELECT needs_reconcile FROM exact_address) AS needs_reconcile,
    EXISTS(SELECT 1 FROM exact_address WHERE owner_iss=?2) AS owner_expected,
    CASE WHEN EXISTS(SELECT 1 FROM exact_address WHERE owner_iss=?2) THEN
      EXISTS(SELECT 1 FROM search_generations g JOIN exact_address a
        ON g.owner_iss=a.owner_iss AND g.owner_sub=a.owner_sub
        WHERE a.owner_iss=?2)
    ELSE NULL END AS generation_present,
    (SELECT COUNT(*) FROM matching WHERE direction='inbound' AND deleted_at IS NULL) AS inbound_active,
    (SELECT COUNT(*) FROM matching WHERE direction='inbound' AND deleted_at IS NOT NULL) AS inbound_deleted,
    (SELECT COUNT(*) FROM matching WHERE direction='inbound' AND signal=1 AND deleted_at IS NULL) AS signal_active,
    (SELECT COUNT(*) FROM matching WHERE direction='inbound' AND signal=1 AND deleted_at IS NOT NULL) AS signal_deleted,
    (SELECT COUNT(*) FROM matching WHERE direction='inbound' AND distractor=1 AND deleted_at IS NULL) AS distractor_active,
    (SELECT COUNT(*) FROM matching WHERE direction='inbound' AND distractor=1 AND deleted_at IS NOT NULL) AS distractor_deleted,
    (SELECT COUNT(*) FROM matching WHERE direction='inbound' AND signal=0 AND distractor=0 AND deleted_at IS NULL) AS other_inbound_active,
    (SELECT COUNT(*) FROM matching WHERE direction='inbound' AND signal=0 AND distractor=0 AND deleted_at IS NOT NULL) AS other_inbound_deleted,
    (SELECT COUNT(*) FROM matching WHERE direction='outbound' AND deleted_at IS NULL) AS outbound_active,
    (SELECT COUNT(*) FROM matching WHERE direction='outbound' AND deleted_at IS NOT NULL) AS outbound_deleted,
    (SELECT COUNT(*) FROM matching WHERE embedded=1) AS embedding_succeeded,
    (SELECT COUNT(*) FROM matching WHERE embedded=0 AND work_state='pending') AS embedding_pending,
    (SELECT COUNT(*) FROM matching WHERE embedded=0 AND work_state='quarantined') AS embedding_quarantined,
    (SELECT COUNT(*) FROM matching WHERE embedded=0 AND work_state IS NULL) AS embedding_no_work"""
MESSAGE_COUNTS = ("inbound_active", "inbound_deleted", "outbound_active", "outbound_deleted")
FIXTURE_COUNTS = (
    "signal_active", "signal_deleted", "distractor_active", "distractor_deleted",
    "other_inbound_active", "other_inbound_deleted",
)
EMBEDDING_COUNTS = (
    "embedding_succeeded", "embedding_pending", "embedding_quarantined", "embedding_no_work",
)
COUNTS = MESSAGE_COUNTS + FIXTURE_COUNTS + EMBEDDING_COUNTS
FIELDS = {"address_state", "needs_reconcile", "owner_expected", "generation_present", *COUNTS}
STATES = {"pending", "provisioning", "active", "deleting", "retired"}


def aggregate(account: str, token: str, target: str) -> dict:
    """Read exactly one aggregate row, rejecting shape drift before output."""

    req = urllib.request.Request(
        f"{API}/accounts/{account}/d1/database/{DB}/query",
        data=json.dumps({"sql": SQL, "params": [
            target, ISSUER, *fixture_subjects(target),
        ]}).encode(),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        method="POST",
    )
    batches = fetch(req).get("result")
    if not isinstance(batches, list) or len(batches) != 1:
        raise ReconcileFailure("d1_shape_unverified")
    batch = batches[0]
    if not isinstance(batch, dict) or batch.get("success") is not True:
        raise ReconcileFailure("d1_shape_unverified")
    rows = batch.get("results")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise ReconcileFailure("d1_shape_unverified")
    row = rows[0]
    if set(row) != FIELDS or row["address_state"] not in STATES | {None}:
        raise ReconcileFailure("d1_shape_unverified")
    if row["address_state"] is None:
        if row["needs_reconcile"] is not None or row["generation_present"] is not None or row["owner_expected"] != 0:
            raise ReconcileFailure("d1_shape_unverified")
    elif type(row["needs_reconcile"]) is not int or row["needs_reconcile"] not in (0, 1):
        raise ReconcileFailure("d1_shape_unverified")
    if type(row["owner_expected"]) is not int or row["owner_expected"] not in (0, 1):
        raise ReconcileFailure("d1_shape_unverified")
    if row["owner_expected"] == 1 and (
        type(row["generation_present"]) is not int or row["generation_present"] not in (0, 1)
    ):
        raise ReconcileFailure("d1_shape_unverified")
    if row["owner_expected"] == 0 and row["generation_present"] is not None:
        raise ReconcileFailure("d1_shape_unverified")
    if any(type(row[key]) is not int or row[key] < 0 for key in COUNTS):
        raise ReconcileFailure("d1_shape_unverified")
    if sum(row[key] for key in MESSAGE_COUNTS) != sum(row[key] for key in EMBEDDING_COUNTS):
        raise ReconcileFailure("d1_shape_unverified")
    if row["inbound_active"] != sum(row[key] for key in (
        "signal_active", "distractor_active", "other_inbound_active",
    )) or row["inbound_deleted"] != sum(row[key] for key in (
        "signal_deleted", "distractor_deleted", "other_inbound_deleted",
    )):
        raise ReconcileFailure("d1_shape_unverified")
    if row["address_state"] is None and any(row[key] for key in COUNTS):
        raise ReconcileFailure("d1_shape_unverified")
    return row


def bucket(count: int) -> str:
    """Cap message cardinality so logs never expose exact larger counts."""

    return str(count) if count < 3 else "more"


def fixture_subjects(target: str) -> tuple[str, str]:
    """Reconstruct the two private exact subjects from the HMAC alias nonce."""

    match = re.fullmatch(r"e2e-([a-f0-9]{16})@mail-staging\.moesegfault\.dev", target)
    if match is None:
        raise ReconcileFailure("alias_shape_invalid")
    nonce = match.group(1)
    return f"AMAIL-E2E-{nonce}-Signal", f"AMAIL-E2E-{nonce}-Distractor"


def main() -> int:
    """Fail closed, emitting only a fixed vocabulary and capped counts."""

    route = "unverified"
    row = None
    try:
        if sys.argv != [sys.argv[0], CONFIRM, RUN, ATTEMPT]:
            raise ReconcileFailure("coordinates_invalid")
        password = required("STAGING_E2E_PASSWORD")
        route_token = required("CF_EMAIL_ROUTING_TOKEN")
        api_token = required("CLOUDFLARE_API_TOKEN")
        account = required("CLOUDFLARE_ACCOUNT_ID")
        if not 15 <= len(password) <= 128 or not re.fullmatch(r"[a-f0-9]{32}", account):
            raise ReconcileFailure("configuration_invalid")
        target = alias(password, RUN, ATTEMPT)
        try:
            route = "absent" if route_absent(rules(route_token), target) else "present"
        except Exception:
            pass
        try:
            row = aggregate(account, api_token, target)
        except Exception:
            pass
    except Exception:
        pass
    print(f"fifth_mail_route:{route}")
    print(f"fifth_mail_address:{(row['address_state'] or 'absent') if row else 'unverified'}")
    owner = "expected" if row and row["owner_expected"] == 1 else "mismatch" if row and row["address_state"] else "unverified"
    print(f"fifth_mail_owner:{owner}")
    print(f"fifth_mail_reconcile:{row['needs_reconcile'] if row else 'unverified'}")
    generation = (
        "present" if row and row["generation_present"] else
        "absent" if row and row["generation_present"] == 0 else "unverified"
    )
    print(f"fifth_mail_generation:{generation}")
    for key in COUNTS:
        print(f"fifth_mail_{key}:{bucket(row[key]) if row else 'unverified'}")
    return 0 if route == "absent" and row is not None and row["owner_expected"] == 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
