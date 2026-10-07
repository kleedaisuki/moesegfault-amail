"""Grant one short-lived, recipient-pinned outbound canary while public send is held.

在公共发送停用期间授权一次短时、固定收件人的出站金丝雀测试。
"""

from __future__ import annotations

import json
import hashlib
import os
import re
import sys
import urllib.error
import urllib.request

from send_control import CASE, DATABASES

SHA256 = re.compile(r"^[0-9a-f]{64}$")
SQL = (
    "UPDATE send_release_gates SET canary_owner_iss=?1,canary_owner_sub=?2,"
    "canary_recipient_sha256=?3,canary_expires_at=unixepoch()+900,"
    "canary_used_by=NULL,actor=?4,case_ref=?5,updated_at=unixepoch() "
    "WHERE id=1 AND EXISTS(SELECT 1 FROM send_policy WHERE scope='global' "
    "AND owner_iss='*' AND owner_sub='*' AND state='held')"
)
OWNED_SQL = SQL + (
    " AND COALESCE(canary_expires_at,0)<=unixepoch()"
    " AND EXISTS(SELECT 1 FROM addresses WHERE address=?6 AND owner_iss=?1"
    " AND owner_sub=?2 AND state='active' AND needs_reconcile=0 AND cf_rule_id=?7)"
    " RETURNING id"
)


def grant_staging_owned(account: str, token: str, address: str, subject: str, case: str) -> dict:
    """Grant the current hosted run's own self-recipient once, without replacing a live slot.

    This staging-only mode is additional to the established main operator wrapper.
    The alias nonce is the protected synthetic journey's run-bound nonce, never an
    arbitrary recipient input. An ambiguous query is not replayed. Accepted send
    journals and old grant audit rows are preserved; global sending stays held.
    """
    from direct_contact_health import DatabaseClient, one_row
    import ensure_role_forwarding as forwarding
    nonce = os.getenv("AMAIL_TEST_RUN_NONCE", "")
    actor = os.getenv("GITHUB_ACTOR", "")
    routing = os.getenv("CF_EMAIL_ROUTING_TOKEN", "")
    if (os.getenv("GITHUB_ACTIONS") != "true"
            or os.getenv("GITHUB_REF") != "refs/heads/codex/v0.2.0-billing"
            or os.getenv("AMAIL_STAGING_CANARY_CONFIRM") != "RUN_STAGING_OWNED_SEND_V020"
            or not re.fullmatch(r"[a-f0-9]{16}", nonce)
            or address != f"send-{nonce}@mail-staging.moesegfault.dev"
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", actor)
            or not isinstance(subject, str) or not 1 <= len(subject) <= 256 or "\n" in subject
            or not CASE.fullmatch(case) or not routing
            or not re.fullmatch(r"[a-f0-9]{32}", account) or not token):
        raise ValueError("staging_canary_context_unverified")
    database = DatabaseClient(account, token, "staging")
    owner = one_row(database.query("SELECT owner_iss,owner_sub,state,needs_reconcile,cf_rule_id FROM addresses WHERE address=?1", [address]))
    issuer = DATABASES["staging"][1]
    rule_id = owner.get("cf_rule_id")
    if (owner.get("owner_iss") != issuer or owner.get("owner_sub") != subject
            or owner.get("state") != "active" or owner.get("needs_reconcile") != 0
            or not isinstance(rule_id, str) or not re.fullmatch(r"[a-f0-9]{1,32}", rule_id)):
        raise ValueError("staging_canary_owner_unverified")
    rules = forwarding.rules(forwarding.Client(token=routing, account=account))
    matches = [row for row in rules if any(isinstance(matcher, dict)
        and matcher.get("type") == "literal" and matcher.get("field") == "to"
        and str(matcher.get("value", "")).lower() == address for matcher in row.get("matchers", []))]
    if (len(matches) != 1 or matches[0].get("id", matches[0].get("tag")) != rule_id
            or matches[0].get("enabled") is not True or matches[0].get("source") != "api"
            or matches[0].get("matchers") != [{"type": "literal", "field": "to", "value": address}]
            or matches[0].get("actions") != [{"type": "worker", "value": ["amail-inbound-staging"]}]):
        raise ValueError("staging_canary_route_unverified")
    digest = hashlib.sha256(address.encode("ascii")).hexdigest()
    result = database.query(OWNED_SQL, [issuer, subject, digest, f"github:{actor}", case, address, rule_id])
    # D1 meta.changes includes audit-trigger writes. RETURNING identifies only
    # the guarded top-level gate row, without widening atomic slot admission.
    rows = result.get("results")
    if (not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict)
            or set(rows[0]) != {"id"} or type(rows[0]["id"]) is not int or rows[0]["id"] != 1):
        raise ValueError("staging_canary_live_slot_or_hold_changed")
    grant = one_row(database.query("SELECT canary_owner_iss,canary_owner_sub,canary_recipient_sha256,"
        "canary_used_by,case_ref,actor,canary_expires_at>unixepoch() AS live,"
        "(SELECT COUNT(*) FROM send_policy WHERE scope='global' AND owner_iss='*' AND owner_sub='*' AND state='held') AS held "
        "FROM send_release_gates WHERE id=1"))
    if (grant.get("canary_owner_iss") != issuer or grant.get("canary_owner_sub") != subject
            or grant.get("canary_recipient_sha256") != digest or grant.get("canary_used_by") is not None
            or grant.get("case_ref") != case or grant.get("actor") != f"github:{actor}"
            or grant.get("live") != 1 or grant.get("held") != 1):
        raise ValueError("staging_canary_readback_unverified")
    return grant


def main() -> int:
    """Record an auditable one-use grant without putting a raw test inbox in Actions. / 审计一次性授权，不把原始测试收件箱写入 Actions。"""
    target = os.getenv("INPUT_TARGET", "")
    subject = os.getenv("INPUT_OWNER_SUB", "").strip()
    digest = os.getenv("INPUT_RECIPIENT_SHA256", "").strip()
    case = os.getenv("INPUT_CASE_REF", "").strip()
    actor = os.getenv("GITHUB_ACTOR", "").strip()
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    if target not in DATABASES or not subject or len(subject) > 256 or "\n" in subject or not SHA256.fullmatch(digest) or not CASE.fullmatch(case) or not actor or not account or not token:
        print("canary_grant=invalid_request", file=sys.stderr)
        return 2
    database, issuer = DATABASES[target]
    body = json.dumps({"sql": SQL, "params": [issuer, subject, digest, f"github:{actor}", case]}).encode()
    request = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{account}/d1/database/{database}/query",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.load(response)
    except (urllib.error.URLError, ValueError):
        print("canary_grant=provider_failure", file=sys.stderr)
        return 1
    if not result.get("success") or not result.get("result") or not result["result"][0].get("success") or not result["result"][0].get("meta", {}).get("changes"):
        print("canary_grant=query_failed", file=sys.stderr)
        return 1
    print(f"canary_grant=recorded target={target} expires_in_seconds=900 case={case}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
