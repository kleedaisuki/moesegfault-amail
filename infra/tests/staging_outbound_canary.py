"""One-use staging outbound canary with independent inbox and D1 feedback oracles.

Run only on a GitHub-hosted runner after a reviewed, recipient-pinned grant. This
module cannot grant sending, change policy, or target production. It prints only
fixed stage labels; raw MIME, credentials, addresses, and IDs stay in memory or
under the caller's repository-local .temp directory.
"""

from __future__ import annotations

import argparse
from email import policy
from email.parser import BytesParser
import hashlib
import imaplib
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.request

from staging_canary_recovery import RecoveryError, hosted_material

from staging_mail_e2e import PNG, TEMP, ProbeFailure, SENDING_TAG, amail, cli_env, inside_temp


API = "https://api.cloudflare.com/client/v4"
DB = "74f35f95-42ce-482c-86e6-dffbdd35cbbe"
ISSUER = "https://identity-staging.moesegfault.dev"
SENDER_DOMAIN = "mail-staging.moesegfault.dev"
MAX_MIME = 2_000_000


def required(name: str) -> str:
    """Read a protected capability without ever reporting its value."""

    value = os.environ.get(name, "")
    if not value:
        raise ProbeFailure(f"{name.lower()}_missing")
    return value


def config() -> dict[str, str]:
    """Require one external inbox and the exact staging operator scope."""

    values = {name: required(name) for name in (
        "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN",
        "STAGING_E2E_OWNER_SUB", "AMAIL_CANARY_RECIPIENT",
        "AMAIL_CANARY_IMAP_HOST", "AMAIL_CANARY_IMAP_USER",
        "AMAIL_CANARY_IMAP_PASSWORD", "AMAIL_CANARY_AUTHSERV_ID",
    )}
    recipient = values["AMAIL_CANARY_RECIPIENT"].lower()
    if not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9.-]+\.[a-z]{2,}", recipient):
        raise ProbeFailure("canary_recipient_invalid")
    if recipient.endswith(".moesegfault.dev") or recipient.endswith("@moesegfault.dev"):
        raise ProbeFailure("canary_recipient_not_external")
    if not re.fullmatch(r"[a-z0-9.-]+", values["AMAIL_CANARY_IMAP_HOST"]):
        raise ProbeFailure("canary_imap_host_invalid")
    if not re.fullmatch(r"[a-z0-9.-]+", values["AMAIL_CANARY_AUTHSERV_ID"]):
        raise ProbeFailure("canary_authserv_invalid")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", values["STAGING_E2E_OWNER_SUB"]):
        raise ProbeFailure("canary_subject_invalid")
    if not re.fullmatch(r"[a-f0-9]{32}", values["CLOUDFLARE_ACCOUNT_ID"]):
        raise ProbeFailure("canary_account_invalid")
    values["AMAIL_CANARY_RECIPIENT"] = recipient
    return values


def d1(values: dict[str, str], sql: str, params: list[str]) -> list[dict]:
    """Run a fixed read-only statement against the staging D1 database."""

    if not sql.startswith("SELECT "):
        raise ProbeFailure("canary_query_not_read_only")
    url = f"{API}/accounts/{values['CLOUDFLARE_ACCOUNT_ID']}/d1/database/{DB}/query"
    req = urllib.request.Request(
        url, data=json.dumps({"sql": sql, "params": params}).encode(),
        headers={"Authorization": "Bearer " + values["CLOUDFLARE_API_TOKEN"],
                 "Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read(131_073)
        if len(raw) > 131_072:
            raise ValueError()
        result = json.loads(raw)
        batches = result.get("result")
        if result.get("success") is not True or not isinstance(batches, list) or len(batches) != 1:
            raise ValueError()
        batch = batches[0]
        rows = batch.get("results")
        if batch.get("success") is not True or not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ValueError()
        return rows
    except Exception:
        raise ProbeFailure("canary_d1_read_failed") from None


def one(rows: list[dict], label: str) -> dict:
    """Reject absent or duplicate control-plane state."""

    if len(rows) != 1:
        raise ProbeFailure(label)
    return rows[0]


def privacy_ready(values: dict[str, str]) -> None:
    """Verify staging Sending privacy flags without changing provider settings."""

    url = f"{API}/zones/6edff81c6ed02f412e70868076411a5e/email/sending/subdomains/{SENDING_TAG}"
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + values["CLOUDFLARE_API_TOKEN"],
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read(65_537)
        if len(raw) > 65_536:
            raise ValueError()
        result = json.loads(raw)
        row = result.get("result")
        if (result.get("success") is not True or not isinstance(row, dict) or
                row.get("name") != SENDER_DOMAIN or row.get("enabled") is not True or
                row.get("preview_enabled") is not False or
                row.get("drop_suppressed_recipients") is not False):
            raise ValueError()
    except Exception:
        raise ProbeFailure("canary_sending_privacy_not_verified") from None


def inbox_ready(values: dict[str, str]) -> None:
    """Fail before submission if the independent external inbox is unavailable."""

    try:
        with imaplib.IMAP4_SSL(values["AMAIL_CANARY_IMAP_HOST"], timeout=25) as inbox:
            if inbox.login(values["AMAIL_CANARY_IMAP_USER"], values["AMAIL_CANARY_IMAP_PASSWORD"])[0] != "OK":
                raise ValueError()
            if inbox.select("INBOX", readonly=True)[0] != "OK":
                raise ValueError()
    except Exception:
        raise ProbeFailure("canary_external_inbox_unavailable") from None


def preflight_controls(values: dict[str, str], sender: str) -> None:
    """Require a held global switch and active sender owned by this principal."""

    state = one(d1(values, "SELECT state FROM send_policy WHERE scope='global' AND owner_iss='*' AND owner_sub='*'", []), "canary_policy_shape")
    if state.get("state") != "held":
        raise ProbeFailure("canary_global_not_held")
    owned = d1(values, "SELECT state FROM addresses WHERE address=?1 AND owner_iss=?2 AND owner_sub=?3", [sender, ISSUER, values["STAGING_E2E_OWNER_SUB"]])
    if one(owned, "canary_sender_not_owned").get("state") != "active":
        raise ProbeFailure("canary_sender_not_active")


def grant_ready(values: dict[str, str], *, after: int | None = None) -> bool:
    """Check exact unused grant with at least 120 seconds remaining.

    A hosted rendezvous additionally requires the grant's D1 update timestamp
    to follow the post-login D1 server-time watermark. The standalone canary
    still fails closed on absent, wrong, used, or nearly expired grants.
    """

    grant = one(d1(values, "SELECT canary_owner_iss,canary_owner_sub,canary_recipient_sha256,canary_expires_at,canary_used_by,updated_at,unixepoch() AS now FROM send_release_gates WHERE id=1", []), "canary_grant_shape")
    digest = hashlib.sha256(values["AMAIL_CANARY_RECIPIENT"].encode()).hexdigest()
    return (grant.get("canary_owner_iss") == ISSUER and
            grant.get("canary_owner_sub") == values["STAGING_E2E_OWNER_SUB"] and
            grant.get("canary_recipient_sha256") == digest and
            grant.get("canary_used_by") is None and
            type(grant.get("canary_expires_at")) is int and
            type(grant.get("now")) is int and
            grant["canary_expires_at"] - grant["now"] >= 120 and
            (after is None or
             (type(grant.get("updated_at")) is int and grant["updated_at"] > after)))


def preflight(values: dict[str, str], sender: str) -> None:
    """Reject a held-policy violation, wrong sender, or ineligible grant."""

    preflight_controls(values, sender)
    if not grant_ready(values):
        raise ProbeFailure("canary_grant_not_ready")


def make_draft(run_dir: Path, sender: str, recipient: str, nonce: str) -> tuple[Path, str]:
    """Create a run-unique text/HTML/CID/attachment draft for native CLI packing."""

    draft = run_dir / "canary-draft"
    draft.mkdir()
    assets = draft / "assets"
    assets.mkdir()
    subject = f"AMAIL-CANARY-{nonce}"
    manifest = (
        "version = 1\n"
        f"from = {json.dumps(sender)}\n"
        f"to = [{json.dumps(recipient)}]\n"
        f"subject = {json.dumps(subject)}\n"
        "[[assets]]\npath = 'assets/pixel.png'\ncontent_type = 'image/png'\n"
        "disposition = 'inline'\ncid = 'canary-pixel'\nfilename = 'pixel.png'\n"
        "[[assets]]\npath = 'assets/proof.bin'\ncontent_type = 'application/octet-stream'\n"
        "disposition = 'attachment'\nfilename = 'proof.bin'\n"
    )
    (draft / "manifest.toml").write_text(manifest, encoding="utf-8")
    (draft / "body.txt").write_text(f"Synthetic staging canary {nonce}\n", encoding="utf-8")
    (draft / "body.html").write_text(f'<p>Synthetic staging canary {nonce}</p><img src="cid:canary-pixel">', encoding="utf-8")
    (assets / "pixel.png").write_bytes(PNG)
    (assets / "proof.bin").write_bytes(hashlib.sha256(nonce.encode()).digest())
    return draft, subject


def delivered_mime(raw: bytes, recipient: str, nonce: str, authserv: str) -> bool:
    """Check delivered content and reject ambiguous authentication claims.

    A matching Authentication-Results field is still untrusted until the
    mailbox operator establishes receiver-side provenance. This function
    must never be used to attest SPF, DKIM, or DMARC by itself.
    """

    if len(raw) > MAX_MIME:
        return False
    mail = BytesParser(policy=policy.default).parsebytes(raw)
    if mail.get("Subject") != f"AMAIL-CANARY-{nonce}":
        return False
    if f"@{SENDER_DOMAIN}" not in str(mail.get("From", "")).lower():
        return False
    if recipient not in str(mail.get("To", "")).lower():
        return False
    auth = [str(value).lower() for value in mail.get_all("Authentication-Results", [])
            if str(value).split(";", 1)[0].strip().lower() == authserv]
    # A forged same-ID field next to a genuine field is ambiguous. Even one
    # matching field is only a claim in downloaded MIME, not trusted origin.
    if len(auth) != 1 or not all((
        "dkim=pass" in auth[0], "spf=pass" in auth[0], "dmarc=pass" in auth[0],
        f"header.from={SENDER_DOMAIN}" in auth[0], f"header.d={SENDER_DOMAIN}" in auth[0],
    )):
        return False
    text = []
    html = []
    inline = []
    attached = []
    for part in mail.walk():
        if part.is_multipart():
            continue
        kind = part.get_content_type()
        payload = part.get_payload(decode=True) or b""
        if kind == "text/plain":
            text.append(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
        elif kind == "text/html":
            html.append(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
        elif kind == "image/png" and str(part.get("Content-ID", "")).strip("<>") == "canary-pixel":
            inline.append(payload)
        elif part.get_filename() == "proof.bin":
            attached.append(payload)
    expected = hashlib.sha256(nonce.encode()).digest()
    return (any(nonce in item for item in text) and
            any(nonce in item and "cid:canary-pixel" in item for item in html) and
            any(item == PNG for item in inline) and any(item == expected for item in attached))


def inbox_contains(values: dict[str, str], nonce: str) -> bool:
    """Fetch only subject-matched canary MIME from the external IMAP inbox."""

    try:
        with imaplib.IMAP4_SSL(values["AMAIL_CANARY_IMAP_HOST"], timeout=25) as inbox:
            inbox.login(values["AMAIL_CANARY_IMAP_USER"], values["AMAIL_CANARY_IMAP_PASSWORD"])
            if inbox.select("INBOX", readonly=True)[0] != "OK":
                return False
            status, data = inbox.search(None, "HEADER", "Subject", f"AMAIL-CANARY-{nonce}")
            if status != "OK" or not data or not data[0]:
                return False
            for uid in data[0].split()[-5:][::-1]:
                status, fetched = inbox.fetch(uid, "(BODY.PEEK[])")
                if status != "OK":
                    continue
                for item in fetched or []:
                    if isinstance(item, tuple) and isinstance(item[1], bytes) and delivered_mime(
                        item[1], values["AMAIL_CANARY_RECIPIENT"], nonce,
                        values["AMAIL_CANARY_AUTHSERV_ID"],
                    ):
                        return True
    except Exception:
        return False
    return False


def feedback_delivered(values: dict[str, str], key: str, message_id: str) -> bool:
    """Require one provider event and its attributed delivered outcome in D1."""

    rows = d1(values, "SELECT provider_id,state,message_id FROM send_requests WHERE owner_iss=?1 AND owner_sub=?2 AND idem_key=?3", [ISSUER, values["STAGING_E2E_OWNER_SUB"], key])
    request = one(rows, "canary_request_missing")
    if request.get("message_id") != message_id or request.get("state") not in ("accepted", "sent") or not request.get("provider_id"):
        raise ProbeFailure("canary_request_mismatch")
    events = d1(values, "SELECT count(*) AS n FROM provider_events WHERE provider_id=?1 AND local_message_id=?2 AND recipient=?3 AND kind='delivered'", [request["provider_id"], message_id, values["AMAIL_CANARY_RECIPIENT"]])
    outcome = d1(values, "SELECT kind FROM recipient_outcomes WHERE local_message_id=?1 AND recipient=?2 AND owner_iss=?3 AND owner_sub=?4", [message_id, values["AMAIL_CANARY_RECIPIENT"], ISSUER, values["STAGING_E2E_OWNER_SUB"]])
    return one(events, "canary_event_count_invalid").get("n") == 1 and len(outcome) == 1 and outcome[0].get("kind") == "delivered"


def grant_consumed_under_hold(values: dict[str, str], key: str) -> None:
    """Prove that the one-use grant, not a public unhold, admitted this key."""

    rows = d1(values, "SELECT p.state,g.canary_used_by FROM send_policy p JOIN send_release_gates g ON g.id=1 WHERE p.scope='global' AND p.owner_iss='*' AND p.owner_sub='*'", [])
    row = one(rows, "canary_post_send_policy_shape")
    if row.get("state") != "held" or row.get("canary_used_by") != key:
        raise ProbeFailure("canary_not_one_use_under_hold")


def create_run_dir(value: str) -> Path:
    """Create one fresh leaf under an existing repository `.temp` parent."""

    path = inside_temp(value, must_exist=False)
    parent = path.parent.resolve()
    if not parent.is_dir() or not (parent == TEMP or TEMP in parent.parents) or path.exists():
        raise ProbeFailure("canary_run_dir_invalid")
    try:
        path.mkdir()
    except OSError:
        raise ProbeFailure("canary_run_dir_create_failed") from None
    if path.resolve() != path:
        raise ProbeFailure("canary_run_dir_invalid")
    return path


def execute(args: argparse.Namespace) -> None:
    """Submit exactly once, then wait for independent delivery and feedback."""

    if not args.confirm_staging or os.environ.get("GITHUB_ACTIONS") != "true" or os.name != "nt":
        raise ProbeFailure("hosted_staging_confirmation_required")
    home = inside_temp(args.home)
    binary = inside_temp(args.amail)
    if not home.is_dir() or not binary.is_file():
        raise ProbeFailure("canary_paths_invalid")
    values = config()
    env = cli_env(home)
    status = amail(binary, env, "auth", "status", failure="canary_auth_failed")
    if len(status) != 1 or status[0].get("authenticated") is not True:
        raise ProbeFailure("canary_not_authenticated")
    sender = args.sender.lower()
    if not re.fullmatch(r"[a-z0-9._+-]+@mail-staging\.moesegfault\.dev", sender):
        raise ProbeFailure("canary_sender_invalid")
    privacy_ready(values)
    inbox_ready(values)
    preflight(values, sender)
    try:
        key, nonce = hosted_material()
    except RecoveryError:
        raise ProbeFailure("canary_recovery_material_invalid") from None
    run_dir = create_run_dir(args.run_dir)
    draft, _ = make_draft(run_dir, sender, values["AMAIL_CANARY_RECIPIENT"], nonce)
    archive = run_dir / "canary.zip"
    packed = amail(binary, env, "pack", str(draft), "-o", str(archive), failure="canary_pack_failed")
    if len(packed) != 1 or packed[0].get("packed") is not True:
        raise ProbeFailure("canary_pack_invalid")
    # A timeout or 5xx may mean the provider already accepted the request.
    # The dedicated protected key and GitHub run coordinates recover this exact
    # idempotency key after runner cleanup; never automatically replay it.
    sent = amail(binary, env, "send", str(archive), "--idempotency-key", key, failure="canary_send_uncertain")
    if len(sent) != 1 or sent[0].get("state") != "accepted" or not isinstance(sent[0].get("id"), str):
        raise ProbeFailure("canary_not_accepted")
    message_id = sent[0]["id"]
    print("canary_provider_accepted_not_delivered")
    grant_consumed_under_hold(values, key)
    deadline = time.monotonic() + 480
    inbox_ok = False
    event_ok = False
    while time.monotonic() < deadline:
        inbox_ok = inbox_ok or inbox_contains(values, nonce)
        event_ok = event_ok or feedback_delivered(values, key, message_id)
        if inbox_ok and event_ok:
            print("canary_external_inbox_and_feedback_verified_auth_manual_pending")
            return
        time.sleep(15)
    raise ProbeFailure("canary_inbox_or_feedback_missing")


def main() -> int:
    """Expose only fixed labels in hosted CI output."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-staging", action="store_true")
    parser.add_argument("--home", required=True)
    parser.add_argument("--amail", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--sender", required=True)
    try:
        execute(parser.parse_args())
        return 0
    except ProbeFailure as error:
        print(f"staging_outbound_canary_failed:{error}", file=sys.stderr)
        return 1
    except Exception:
        print("staging_outbound_canary_failed:unexpected_failure", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
