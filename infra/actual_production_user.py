"""Run two owned production users through normal Identity UI and amail commands.

This is an execution helper, not a test framework. Mail bodies, credentials,
OAuth URLs and private verification objects are never printed. Registration
uses the existing private synthetic-contact inbox, then closes its exact route.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import tomllib
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "infra" / "tests"))
import staging_identity_cdp as identity
import staging_second_principal as inbox


@dataclass(frozen=True)
class NativeProduction:
    """Pin only the actual coordinates used by the native browser adapter."""

    name: str = "production"
    issuer: str = "https://identity.moesegfault.dev"
    login_origin: str = "https://login.moesegfault.dev"
    account_origin: str = "https://account.moesegfault.dev"
    client_id: str = "amail-cli"
    mail_api: str = "https://mail.moesegfault.dev"


REALM = NativeProduction()
RUN = ROOT / ".temp" / "actual-production-users"
BINARY = ROOT / ".temp" / "production-cli" / "amail.exe"


def require(condition: bool, label: str) -> None:
    """Report a source-owned status label without private response material."""
    if not condition:
        raise identity.ProbeError(label)


def marker(label: str) -> None:
    """Record tangible successful user steps without mail or identity data."""
    print(label, flush=True)


def credential(actor: str) -> tuple[str, str, str]:
    """Load only dedicated actor secrets, never a developer account."""
    user = os.environ.pop(f"PRODUCTION_ACTOR_{actor}_USERNAME", "")
    password = os.environ.pop(f"PRODUCTION_ACTOR_{actor}_PASSWORD", "")
    require(bool(re.fullmatch(r"amail_prod_[a-f0-9]{14}", user)) and len(password) >= 32,
            "dedicated_actor_credentials_missing")
    contact = "amail-e2e@moesegfault.dev" if actor == "A" else "amail-e2e-isolation@moesegfault.dev"
    return user, password, contact


def register(actor: str, material: tuple[str, str, str]) -> None:
    """Create and verify an owned production principal on first-party pages."""
    username, password, contact = material
    account, token = os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"]
    baseline = inbox.object_inventory(account, token)
    require(identity.route(address=contact) == "absent", "verification_route_already_open")
    browser = None
    fresh: set[str] = set()
    try:
        # Complete local browser startup before opening any verification route.
        browser = identity.Browser(RUN / actor / "registration", realm=REALM)
        marker(f"actor_{actor.lower()}_owned_browser_started")
        require(identity.route("--apply", contact) == "created", "verification_route_creation_failed")
        time.sleep(60)
        require(identity.route(address=contact) == "enabled", "verification_route_not_settled")
        browser.navigate(REALM.login_origin + "/register")
        browser.wait_dom('input[name="display_name"]')
        browser.require_login_origin()
        for field, value in {"display_name": "amail production researcher " + actor,
                             "username": username, "email": contact, "password": password,
                             "password_confirm": password}.items():
            browser.fill(f'input[name="{field}"]', value)
        browser.click('button[name="method"][value="password"]')
        status, _ = browser.response(lambda path: path == identity.REGISTRATION, timeout=60)
        require(status == 201, f"actor_{actor.lower()}_registration_http_{status}")
        marker(f"actor_{actor.lower()}_production_registration_created")
        browser.wait_dom('form.verification-card input[name="code"]')
        status, _ = browser.response(lambda path: bool(identity.VERIFICATION_START.fullmatch(path)), timeout=60)
        require(status == 201, "verification_start_failed")
        # The inbox has an exact allowlist, private storage and a short lifecycle.
        # Only this newly received contact-bound OTP is used, in process memory.
        inbox.ADDRESS = contact
        code = inbox.guarded_code(account, token, baseline, time.monotonic())
        fresh = inbox.object_inventory(account, token) - baseline
        require(len(fresh) == 1, "verification_object_ambiguous")
        require(identity.route("--remove", contact) == "removed"
                and identity.route(address=contact) == "absent", "verification_route_close_failed")
        browser.fill('form.verification-card input[name="code"]', code)
        browser.click('form.verification-card button[type="submit"]')
        status, request = browser.response(lambda path: bool(identity.VERIFICATION_DONE.fullmatch(path)), timeout=60)
        require(status == 200 and browser.response_body(request).get("verification_state") == "verified",
                "production_contact_verification_failed")
        marker(f"actor_{actor.lower()}_production_contact_verified")
    finally:
        if identity.route(address=contact) == "enabled":
            identity.route("--remove", contact)
        require(identity.route(address=contact) == "absent", "verification_route_cleanup_required")
        browser_failed = False
        if browser:
            try:
                browser.close()
            except Exception:
                browser_failed = True
        # Only a provenance-checked fresh object may be deleted; never baseline mail.
        for key in fresh:
            inbox.request("DELETE", f"/accounts/{account}/r2/buckets/{inbox.BUCKET}/objects/{key}", token)
        require(not (inbox.object_inventory(account, token) - baseline), "verification_object_cleanup_required")
        require(not browser_failed, "registration_browser_teardown_failed")


def cli(environment: dict[str, str], *args: str, allow_failure: bool = False) -> list[dict]:
    """Execute the public CLI and retain its JSONL response only in memory."""
    result = subprocess.run([str(BINARY), *args], env=environment, capture_output=True,
                            text=True, encoding="utf-8", timeout=950, check=False)
    if allow_failure:
        require(result.returncode != 0 and not result.stdout.strip()
                and "HTTP 404" in result.stderr and "code=not_found" in result.stderr,
                "cross_account_denial_not_404")
        return []
    if result.returncode:
        code = re.search(r"code=([a-z_]+)", result.stderr)
        request = re.search(r"request_id=([a-f0-9-]{1,64})", result.stderr)
        label = "amail_" + args[0] + "_failed"
        if code:
            label += ":" + code.group(1)
        if request:
            marker("opaque_request_id=" + request.group(1))
        raise identity.ProbeError(label)
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def login(actor: str, material: tuple[str, str, str]) -> tuple[dict[str, str], str]:
    """Use actual native PKCE and a fresh encrypted CLI session for one actor."""
    directory = RUN / actor
    directory.mkdir(parents=True, exist_ok=True)
    identity.native_login(directory, BINARY, material[2], realm=REALM, credentials=material)
    homes = list(directory.glob("amail-home-*"))
    require(len(homes) == 1, "actor_home_ambiguous")
    environment = identity.browser_environment()
    environment.update(AMAIL_HOME=str(homes[0]), AMAIL_ISSUER=REALM.issuer,
                       AMAIL_CLIENT_ID=REALM.client_id, AMAIL_API_BASE=REALM.mail_api,
                       AMAIL_REDIRECT_URI="http://127.0.0.1/callback")
    local = "journey-" + actor.lower() + "-" + hashlib.sha256(material[0].encode()).hexdigest()[:8]
    address = local + "@mail.moesegfault.dev"
    owned = cli(environment, "address", "list")
    if not any(row.get("address") == address for row in owned):
        cli(environment, "address", "add", local)
    owned = cli(environment, "address", "list")
    require(any(row.get("address") == address and row.get("state") == "active" for row in owned),
            "production_user_address_not_active")
    marker(f"actor_{actor.lower()}_production_login_and_address_active")
    return environment, address


def draft(actor: str, sender: str, recipient: str, environment: dict[str, str]) -> tuple[Path, str, bytes, str, str]:
    """Author TEXT, HTML and an attachment, then let amail pack the ZIP."""
    directory = RUN / actor / "draft"
    (directory / "assets").mkdir(parents=True)
    subject = "Research Notification " + os.environ["GITHUB_RUN_ID"] + " " + actor
    text = "Research note: simple invariants make mail delivery reproducible.\n"
    html = '<html><body><h1>Research note</h1><p>Simple invariants make mail delivery reproducible.</p></body></html>'
    attachment = b"Claim,Evidence\nNative authorization,PKCE\nDelivery,Received archive\n"
    filename, phrase = "research.csv", "simple invariants"
    if actor == "B":
        source = ROOT / "infra" / "user-drafts" / "reply"
        text = (source / "body.txt").read_text(encoding="utf-8")
        html = (source / "body.html").read_text(encoding="utf-8")
        attachment = (source / "comparison-card.txt").read_bytes()
        filename, phrase = "comparison-card.txt", "independent user b"
    (directory / "manifest.toml").write_text(
        f'version = 1\nfrom = "{sender}"\nto = ["{recipient}"]\nsubject = "{subject}"\n'
        f'[[assets]]\npath = "assets/{filename}"\ncontent_type = "text/plain"\n'
        f'disposition = "attachment"\nfilename = "{filename}"\n', encoding="utf-8")
    (directory / "body.txt").write_text(text, encoding="utf-8")
    (directory / "body.html").write_text(html, encoding="utf-8")
    (directory / "assets" / filename).write_bytes(attachment)
    archive = RUN / actor / "draft.zip"
    cli(environment, "pack", str(directory), "-o", str(archive))
    marker(f"actor_{actor.lower()}_text_html_attachment_packed")
    return archive, subject, attachment, filename, phrase


def receive(actor: str, environment: dict[str, str], subject: str, attachment: bytes,
            filename: str, phrase: str) -> dict:
    """Require actual inbound delivery and inspect the retrieved safe archive."""
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        rows = cli(environment, "search", "--title", subject)
        inbound = [row for row in rows if row.get("direction") == "inbound"]
        if inbound:
            require(len(inbound) == 1, "received_delivery_ambiguous")
            message = inbound[0]
            break
        time.sleep(10)
    else:
        raise identity.ProbeError("production_received_delivery_timeout")
    directory = RUN / actor / "received"
    before = cli(environment, "get", message["id"])[0]
    cli(environment, "read", message["id"], "-o", str(directory), "--unpack")
    after = cli(environment, "get", message["id"])[0]
    require(before["read"] == after["read"], "archive_read_changed_read_state")
    require(phrase in (directory / "body.txt").read_text(encoding="utf-8").lower(),
            "received_text_body_changed")
    require(phrase in (directory / "body.html").read_text(encoding="utf-8").lower(),
            "received_html_body_missing")
    manifest = tomllib.loads((directory / "manifest.toml").read_text(encoding="utf-8"))
    files = [asset for asset in manifest.get("assets", []) if asset.get("filename") == filename]
    require(len(files) == 1 and (directory / files[0]["path"]).read_bytes() == attachment,
            "received_attachment_changed")
    marker(f"actor_{actor.lower()}_actual_received_archive_text_html_attachment_verified")
    return message


def explore(actor: str, environment: dict[str, str], address: str, message: dict,
            filename: str, phrase: str) -> None:
    """Exercise real combined filters, semantic indexing, export and read state."""
    ident, subject = message["id"], message["subject"]
    now = datetime.now(timezone.utc)
    after = (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    before = (now + timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    predicates = ["--mailbox", address, "--title", subject, "--after", after, "--before", before,
                  "--body", phrase, "--meta", "attachment_name=" + filename]
    require(any(row.get("id") == ident for row in cli(environment, "search", *predicates)),
            "combined_search_missing_delivery")
    require(any(row.get("id") == ident for row in cli(environment, "search", "--title", "^Research Notification", "--regex", "--case-sensitive")),
            "regex_case_search_missing_delivery")
    cli(environment, "mark", ident, "--read")
    require(any(row.get("id") == ident for row in cli(environment, "search", "--title", subject, "--read")),
            "explicit_read_state_missing")
    cli(environment, "mark", ident, "--unread")
    require(any(row.get("id") == ident for row in cli(environment, "search", "--title", subject, "--unread")),
            "explicit_unread_state_missing")
    cli(environment, "sync", "--all", "--out-dir", str(RUN / actor / "export"))
    marker(f"actor_{actor.lower()}_combined_filters_regex_case_readstate_export_verified")
    deadline = time.monotonic() + 420
    while time.monotonic() < deadline:
        rows = cli(environment, "search", "--semantic", "reproducible delivery through simple invariants")
        if any(row.get("id") == ident for row in rows):
            marker(f"actor_{actor.lower()}_automatic_index_and_semantic_search_verified")
            return
        time.sleep(30)
    raise identity.ProbeError("automatic_semantic_index_not_ready")


def main() -> int:
    """Run exactly the dispatched normal-user phase, without implicit retries."""
    try:
        require(os.environ.get("USER_JOURNEY_CONFIRM") == "RUN_OWNED_PRODUCTION_USERS",
                "production_execution_unconfirmed")
        materials = {actor: credential(actor) for actor in ("A", "B")}
        RUN.mkdir(parents=True, exist_ok=False)
        require(BINARY.is_file(), "release_candidate_binary_missing")
        marker("owned_synthetic_mail_automatic_openrouter_indexing_disclosed_and_authorized")
        if os.environ.get("USER_JOURNEY_PHASE") == "register":
            for actor, material in materials.items():
                register(actor, material)
            return 0
        sessions = {actor: login(actor, material) for actor, material in materials.items()}
        time.sleep(60)
        delivered = {}
        for sender, recipient in (("A", "B"), ("B", "A")):
            environment, address = sessions[sender]
            other_environment, other_address = sessions[recipient]
            archive, subject, attachment, filename, phrase = draft(sender, address, other_address, environment)
            cli(environment, "send", str(archive), "--idempotency-key", str(uuid.uuid4()))
            marker(f"actor_{sender.lower()}_normal_send_accepted")
            received = receive(recipient, other_environment, subject, attachment, filename, phrase)
            cli(environment, "get", received["id"], allow_failure=True)
            require(cli(other_environment, "get", received["id"])[0]["id"] == received["id"],
                    "owner_message_disappeared_after_foreign_denial")
            marker(f"actor_{sender.lower()}_cross_account_get_denied")
            delivered[recipient] = received, filename, phrase
        for actor, (message, filename, phrase) in delivered.items():
            environment, address = sessions[actor]
            explore(actor, environment, address, message, filename, phrase)
            cli(environment, "delete", message["id"])
            cli(environment, "get", message["id"], allow_failure=True)
            marker(f"actor_{actor.lower()}_owned_delivery_deleted_and_absence_verified")
        marker("actual_production_two_user_journey_complete")
        return 0
    except (identity.ProbeError, inbox.ProvisionFailure) as error:
        label = str(error)
        print("actual_production_user_failed:" + (label if re.fullmatch(r"[a-z0-9_:]{1,150}", label) else "private_failure"), file=sys.stderr)
        return 1
    except Exception:
        print("actual_production_user_failed:unexpected_private_failure", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
