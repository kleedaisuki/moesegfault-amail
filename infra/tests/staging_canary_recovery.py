"""Derive and reconcile one hosted outbound attempt without replaying mail.

Usage in a restricted operator session: set the dedicated recovery key,
staging D1 read token/account and immutable owner subject privately, then run
`python infra/tests/staging_canary_recovery.py <run-id> <attempt>`. This command
only reads the exact staging request and grant; it never prints identifiers,
mail content, recipient, or provider response and never sends or grants mail.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import re
import sys
import uuid
from typing import Callable


class RecoveryError(Exception):
    """A fixed, public-safe denial label."""


def material(run_id: str, attempt: str, secret: str) -> tuple[str, str]:
    """Return a run-bound idempotency UUID and independent subject nonce.

    The 256-bit key is a repository Secret, never a workflow input. Domain
    separation prevents the nonce from revealing the idempotency key.
    """

    if (not re.fullmatch(r"[1-9][0-9]{0,19}", run_id) or
            not re.fullmatch(r"[1-9][0-9]{0,2}", attempt)):
        raise RecoveryError("run_coordinates_invalid")
    if not re.fullmatch(r"[a-f0-9]{64}", secret):
        raise RecoveryError("recovery_key_invalid")
    key = bytes.fromhex(secret)
    base = f"amail-staging-outbound/v1:{run_id}:{attempt}:".encode("ascii")
    idem = hmac.new(key, base + b"idempotency", hashlib.sha256).digest()
    nonce = hmac.new(key, base + b"subject-nonce", hashlib.sha256).hexdigest()[:32]
    return str(uuid.UUID(bytes=idem[:16], version=4)), nonce


def hosted_material() -> tuple[str, str]:
    """Derive material only on the confirmed hosted GitHub runner."""

    if os.environ.get("GITHUB_ACTIONS") != "true" or os.name != "nt":
        raise RecoveryError("hosted_windows_required")
    return material(
        os.environ.get("GITHUB_RUN_ID", ""),
        os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        os.environ.get("AMAIL_STAGING_CANARY_RECOVERY_KEY", ""),
    )


def inspect(
    run_id: str, attempt: str,
    *, read_d1: Callable[[dict[str, str], str, list[str]], list[dict]] | None = None,
) -> str:
    """Read exact staging D1 state; do not infer delivery from acceptance.

    An optional read callback lets offline contracts supply bounded D1 rows
    without depending on the test runner's Python module import alias.
    Production always uses the fixed staging D1 reader.
    """

    from staging_outbound_canary import ISSUER, d1, one
    read = d1 if read_d1 is None else read_d1

    key, _ = material(run_id, attempt, os.environ.get("AMAIL_STAGING_CANARY_RECOVERY_KEY", ""))
    owner = os.environ.get("STAGING_E2E_OWNER_SUB", "")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if (not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", owner) or
            not re.fullmatch(r"[a-f0-9]{32}", account) or not token):
        raise RecoveryError("read_capability_invalid")
    values = {"CLOUDFLARE_ACCOUNT_ID": account, "CLOUDFLARE_API_TOKEN": token}
    policy = one(read(values, "SELECT state FROM send_policy WHERE scope='global' AND owner_iss='*' AND owner_sub='*'", []), "canary_policy_shape")
    if policy.get("state") != "held":
        raise RecoveryError("global_not_held")
    rows = read(values, "SELECT state,provider_id,message_id FROM send_requests WHERE owner_iss=?1 AND owner_sub=?2 AND idem_key=?3", [ISSUER, owner, key])
    grant = one(read(values, "SELECT canary_used_by FROM send_release_gates WHERE id=1", []), "canary_grant_shape")
    if len(rows) > 1:
        raise RecoveryError("request_shape_invalid")
    if not rows:
        return "request_absent_grant_consumed" if grant.get("canary_used_by") == key else "request_absent_grant_not_consumed"
    row = rows[0]
    state = row.get("state")
    if state not in ("preparing", "reserving", "submitting", "unknown", "rejected", "accepted", "sent"):
        raise RecoveryError("request_state_unclassified")
    consumed = "grant_consumed" if grant.get("canary_used_by") == key else "grant_not_consumed"
    provider = "provider_id_present" if row.get("provider_id") else "provider_id_absent"
    feedback = "delivered_event_absent"
    if row.get("provider_id") and row.get("message_id"):
        events = one(read(values, "SELECT count(*) AS n FROM provider_events WHERE provider_id=?1 AND local_message_id=?2 AND kind='delivered'", [row["provider_id"], row["message_id"]]), "canary_event_shape")
        if type(events.get("n")) is not int:
            raise RecoveryError("event_count_invalid")
        feedback = "delivered_event_present" if events["n"] > 0 else feedback
    return f"request_{state}_{consumed}_{provider}_{feedback}"


def main() -> int:
    """Expose only a closed status; never output a recomputed key or raw D1 row."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    parser.add_argument("attempt")
    args = parser.parse_args()
    try:
        status = inspect(args.run_id, args.attempt)
    except Exception:
        print("staging_outbound_recovery:unverified", file=sys.stderr)
        return 1
    print("staging_outbound_recovery:" + status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
