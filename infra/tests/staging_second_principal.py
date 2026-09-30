"""Provision only the reviewed second staging Identity principal on hosted Windows.

The repository-level B credential must already be protected in GitHub Secrets.
This one-shot script refuses any pre-existing B contact; a partial registration
requires same-account recovery rather than another dispatch.
"""

from __future__ import annotations

from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[2]
TEMP = (ROOT / ".temp").resolve()
ADDRESS = "amail-e2e-isolation@moesegfault.dev"
FIRST = "amail-e2e@moesegfault.dev"
BUCKET = "amail-identity-test-inbox-staging"
DB = "c4042bd4-bb4a-4cf7-aa7f-04cf1a5d6ad9"
API = "https://api.cloudflare.com/client/v4"
KEY = re.compile(r"verification/[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\.eml\Z")


class ProvisionFailure(Exception):
    """A fixed source-owned, non-sensitive failure label."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Do not forward the Cloudflare bearer capability to another origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Reject all redirects, including same-origin redirects."""

        return None


OPENER = urllib.request.build_opener(NoRedirect())


def require(condition: bool, label: str) -> None:
    """Fail without emitting any sensitive provider or message material."""

    if not condition:
        raise ProvisionFailure(label)


def request(method: str, path: str, token: str, data: bytes | None = None,
            limit: int = 65_536) -> bytes:
    """Perform one bounded Cloudflare API request with no redirect/retry."""

    req = urllib.request.Request(
        API + path, data=data, method=method,
        headers={"Authorization": "Bearer " + token, "Accept": "*/*",
                 **({"Content-Type": "application/json"} if data is not None else {})},
    )
    try:
        with OPENER.open(req, timeout=25) as response:
            raw = response.read(limit + 1)
            require(response.status in (200, 204) and len(raw) <= limit, "cloudflare_response_invalid")
            return raw
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        raise ProvisionFailure("cloudflare_request_failed") from None


def json_result(raw: bytes) -> object:
    """Require a successful Cloudflare envelope without logging its contents."""

    try:
        value = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise ProvisionFailure("cloudflare_json_invalid") from None
    require(isinstance(value, dict) and value.get("success") is True,
            "cloudflare_envelope_invalid")
    return value


def identity_contacts(account: str, token: str) -> dict[str, tuple[str, str, str, str]]:
    """Read A/B contact, username ownership and pairwise subjects in memory."""

    sql = (
        "SELECT i.normalized_value AS contact,i.verification_state AS state,"
        "i.principal_id AS principal,s.pairwise_subject AS subject,"
        "(SELECT u.normalized_value FROM identifiers u WHERE u.principal_id=i.principal_id "
        "AND u.kind='username') AS username "
        "FROM identifiers i LEFT JOIN oauth_clients c ON c.client_id='amail-cli-staging' "
        "LEFT JOIN pairwise_subjects s ON s.principal_id=i.principal_id "
        "AND s.sector_identifier=c.sector_identifier "
        "WHERE i.kind='email' AND i.normalized_value IN (?1,?2)"
    )
    body = json.dumps({"sql": sql, "params": [FIRST, ADDRESS]}).encode()
    value = json_result(request("POST", f"/accounts/{account}/d1/database/{DB}/query", token, body))
    batches = value.get("result")
    require(isinstance(batches, list) and len(batches) == 1 and
            isinstance(batches[0], dict) and batches[0].get("success") is True,
            "identity_readback_invalid")
    rows = batches[0].get("results")
    require(isinstance(rows, list) and len(rows) <= 2, "identity_readback_invalid")
    contacts: dict[str, tuple[str, str, str, str]] = {}
    for row in rows:
        require(isinstance(row, dict) and row.get("contact") in (FIRST, ADDRESS)
                and row["contact"] not in contacts and
                row.get("state") in ("unverified", "pending", "verified")
                and isinstance(row.get("principal"), str)
                and isinstance(row.get("username"), str)
                and re.fullmatch(r"[a-z0-9_]{3,32}", row["username"]),
                "identity_readback_invalid")
        contacts[row["contact"]] = (
            row["principal"], row.get("subject") or "", row["state"], row["username"]
        )
    return contacts


def object_inventory(account: str, token: str) -> set[str]:
    """List UUID-keyed MIME by strict keyset order until an explicit empty page.

    REST ``result_info`` is optional; a short page does not prove completion.
    Always request the next lexicographic slice after the last validated key.
    """

    keys: set[str] = set()
    last: str | None = None
    for _ in range(20):
        query = "?prefix=verification/&per_page=100"
        if last is not None:
            query += "&start_after=" + urllib.parse.quote(last, safe="")
        raw = request("GET", f"/accounts/{account}/r2/buckets/{BUCKET}/objects{query}", token,
                      limit=262_144)
        value = json_result(raw)
        batch = value.get("result")
        require(isinstance(batch, list), "r2_result_invalid")
        require(len(batch) <= 100, "r2_page_size_invalid")
        info = value.get("result_info")
        if "result_info" in value:
            require(isinstance(info, dict), "r2_result_info_invalid")
            if "is_truncated" in info:
                require(type(info["is_truncated"]) is bool, "r2_result_info_invalid")
        if not batch:
            require(not (isinstance(info, dict) and info.get("is_truncated") is True),
                    "r2_empty_page_truncated")
            return keys
        for item in batch:
            require(isinstance(item, dict), "r2_object_entry_invalid")
            key = item.get("key")
            require(isinstance(key, str) and KEY.fullmatch(key) is not None,
                    "r2_object_key_invalid")
            require(key not in keys, "r2_duplicate_key")
            require(last is None or key > last, "r2_key_order_invalid")
            keys.add(key)
            require(len(keys) <= 1000, "r2_inventory_too_large")
            last = key
    raise ProvisionFailure("r2_page_limit")


def verification_code(raw: bytes) -> str:
    """Extract only one code from a single exact-recipient Identity text part."""

    require(0 < len(raw) <= 65_536, "verification_mime_size")
    try:
        message = BytesParser(policy=policy.default).parsebytes(raw)
        sender = message["From"]
        recipient = message["To"]
        date = message["Date"]
        senders = getaddresses([str(sender)]) if sender is not None else []
        recipients = getaddresses([str(recipient)]) if recipient is not None else []
        require(len(senders) == 1 and senders[0][1].lower() == "identity@moesegfault.dev"
                and len(recipients) == 1 and recipients[0][1].lower() == ADDRESS
                and date is not None, "verification_provenance_invalid")
        timestamp = parsedate_to_datetime(str(date))
        require(timestamp.tzinfo is not None and
                abs((datetime.now(timezone.utc) - timestamp).total_seconds()) <= 600,
                "verification_time_invalid")
        parts = [p for p in message.walk() if p.get_content_type() == "text/plain"
                 and p.get_content_disposition() != "attachment"]
        require(len(parts) == 1, "verification_text_ambiguous")
        body = parts[0].get_content()
        match = re.findall(r"Verification code: ([0-9]{8})(?![0-9])", body)
        require(len(match) == 1 and f"Address: {ADDRESS}" in body,
                "verification_code_ambiguous")
        return match[0]
    except (UnicodeError, ValueError, TypeError, KeyError):
        raise ProvisionFailure("verification_mime_invalid") from None


def guarded_code(account: str, token: str, baseline: set[str], started: float) -> str:
    """Poll one new private object; never return an unvetted or stale OTP."""

    deadline = min(started + 8 * 60, time.monotonic() + 150)
    while time.monotonic() < deadline:
        new = object_inventory(account, token) - baseline
        require(len(new) <= 1, "verification_delivery_ambiguous")
        if new:
            key = next(iter(new))
            raw = request("GET", f"/accounts/{account}/r2/buckets/{BUCKET}/objects/{key}",
                          token, limit=65_536)
            return verification_code(raw)
        time.sleep(5)
    raise ProvisionFailure("verification_delivery_timeout")


def recover_contact(run_dir: Path, username: str, password: str,
                    account: str, token: str, baseline: set[str]) -> None:
    """Verify the existing B contact through first-party Login and Account UI."""

    from staging_identity_cdp import (
        ACCOUNT_ORIGIN, LOGIN_ORIGIN, PASSWORD_AUTH, VERIFICATION_DONE, VERIFICATION_START,
        Browser, route,
    )

    browser = Browser(run_dir / "recovery-browser")
    try:
        time.sleep(60)
        require(route(address=ADDRESS) == "enabled", "exact_route_changed_during_settle")
        browser.navigate(LOGIN_ORIGIN + "/login")
        browser.wait_dom('form.auth-form input[name="login"]')
        browser.require_login_origin()
        browser.fill('form.auth-form input[name="login"]', username)
        browser.fill('form.auth-form input[name="password"]', password)
        browser.click('form.auth-form button[type="submit"]')
        status, _ = browser.response(lambda path: path == PASSWORD_AUTH)
        require(status == 200, "existing_account_login_failed")
        browser.navigate(ACCOUNT_ORIGIN + "/profile")
        browser.wait_dom(".entity-list .entity-row", timeout=60)
        browser.require_account_origin()
        # Select one exact private contact row; never click a neighboring user's
        # contact or a generic first button without checking the destination.
        expression = (
            "(()=>{const r=[...document.querySelectorAll('.entity-list .entity-row')]"
            ".filter(e=>e.querySelector('strong')?.textContent?.trim()==="
            + json.dumps(ADDRESS)
            + ");if(r.length!==1)return false;const b=r[0].querySelector('.row-actions button');"
              "if(!b)return false;b.click();return true})()"
        )
        require(browser.evaluate(expression) is True, "existing_contact_row_missing")
        started_status, _ = browser.response(
            lambda path: bool(VERIFICATION_START.fullmatch(path)), timeout=45
        )
        require(started_status == 201, "recovery_verification_start_failed")
        browser.wait_dom('.verification-form input[name="code"]')
        started = time.monotonic()
        code = guarded_code(account, token, baseline, started)
        require(route("--remove", ADDRESS) in ("removed", "absent")
                and route(address=ADDRESS) == "absent", "exact_route_cleanup_failed")
        browser.require_account_origin()
        browser.fill('.verification-form input[name="code"]', code)
        browser.click('.verification-form button[type="submit"]')
        completed, request_id = browser.response(
            lambda path: bool(VERIFICATION_DONE.fullmatch(path)), timeout=45
        )
        require(completed == 200 and
                browser.response_body(request_id).get("verification_state") == "verified",
                "recovery_verification_completion_failed")
    finally:
        try:
            browser.close()
        except Exception:
            raise ProvisionFailure("recovery_browser_teardown_failed") from None


def preflight_contacts(mode: str, contacts: dict[str, tuple[str, str, str, str]],
                       username: str) -> None:
    """Make create-only and same-account recovery mutually exclusive."""

    require(FIRST in contacts and contacts[FIRST][0] and contacts[FIRST][1]
            and contacts[FIRST][2] == "verified", "identity_contact_preflight_failed")
    if mode == "provision":
        require(ADDRESS not in contacts, "identity_contact_preflight_failed")
        return
    require(ADDRESS in contacts and contacts[ADDRESS][2] in ("unverified", "pending")
            and contacts[ADDRESS][3] == username
            and contacts[ADDRESS][0] != contacts[FIRST][0],
            "recovery_contact_preflight_failed")


def inspect_state(username: str, password: str) -> tuple[str, str, dict, set[str]]:
    """Read deployed inbox, both routes, Identity contacts and private R2 only."""

    from staging_identity_cdp import decoded_credential, route

    decoded_credential({"username": username, "password": password, "address": ADDRESS})
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    route_token = os.environ.get("CF_EMAIL_ROUTING_TOKEN", "")
    require(re.fullmatch(r"[a-f0-9]{32}", account) is not None and bool(token and route_token),
            "provider_credentials_missing")
    config = ROOT / "workers" / "identity-test-inbox" / "check_config.py"
    try:
        deployed = subprocess.run(
            [sys.executable, str(config), "--live", "--deployed"],
            capture_output=True, timeout=90, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ProvisionFailure("private_inbox_deployment_unverified") from None
    require(deployed.returncode == 0, "private_inbox_deployment_unverified")
    require(route(address=ADDRESS) == "absent" and route(address=FIRST) == "absent",
            "verification_route_preexisting")
    try:
        contacts = identity_contacts(account, token)
    except ProvisionFailure as error:
        if str(error).startswith("cloudflare_"):
            raise ProvisionFailure("identity_d1_read_failed") from None
        raise
    try:
        baseline = object_inventory(account, token)
    except ProvisionFailure as error:
        if str(error).startswith("cloudflare_"):
            raise ProvisionFailure("private_r2_list_failed") from None
        raise
    require(len(baseline) <= 1000, "r2_inventory_too_large")
    return account, token, contacts, baseline


def classify_contact(contacts: dict[str, tuple[str, str, str, str]], username: str) -> str:
    """Classify B with fixed labels only; never return any Identity identifier."""

    require(FIRST in contacts and contacts[FIRST][0] and contacts[FIRST][1]
            and contacts[FIRST][2] == "verified", "identity_contact_preflight_failed")
    if ADDRESS not in contacts:
        return "absent"
    b = contacts[ADDRESS]
    require(b[0] != contacts[FIRST][0] and b[3] == username,
            "second_contact_owner_mismatch")
    if b[2] in ("unverified", "pending"):
        return "pending_same_account"
    require(b[2] == "verified", "second_contact_state_invalid")
    return "verified_same_account"


def read_only_preflight() -> None:
    """Check current token capabilities and B state before any one-shot change."""

    require(os.environ.get("AMAIL_SECOND_PRINCIPAL_MODE") == "preflight"
            and os.environ.get("AMAIL_SECOND_PRINCIPAL_CONFIRM") ==
            "READ_STAGING_SECOND_PRINCIPAL_PREFLIGHT", "explicit_confirmation_required")
    username = os.environ.pop("STAGING_E2E_B_USERNAME", "")
    password = os.environ.pop("STAGING_E2E_B_PASSWORD", "")
    _, _, contacts, _ = inspect_state(username, password)
    print("staging_second_principal_preflight_" + classify_contact(contacts, username))


def execute() -> None:
    """Provision B exactly once and attest its distinct native principal."""

    require(os.name == "nt", "windows_runner_required")
    mode = os.environ.get("AMAIL_SECOND_PRINCIPAL_MODE", "provision")
    require(mode in ("provision", "recover"), "principal_mode_invalid")
    expected_confirm = ("RUN_STAGING_SECOND_PRINCIPAL_PROVISION" if mode == "provision"
                        else "RUN_STAGING_SECOND_PRINCIPAL_RECOVER")
    require(os.environ.get("AMAIL_SECOND_PRINCIPAL_CONFIRM") == expected_confirm,
            "explicit_confirmation_required")
    require(TEMP == ROOT / ".temp", "repo_temp_redirected")
    username = os.environ.pop("STAGING_E2E_B_USERNAME", "")
    password = os.environ.pop("STAGING_E2E_B_PASSWORD", "")
    from staging_identity_cdp import native_login, registration, route
    account, token, before, baseline = inspect_state(username, password)
    preflight_contacts(mode, before, username)
    binary = ROOT / "target" / "debug" / "amail.exe"
    require(binary.is_file(), "hosted_cli_binary_missing")
    TEMP.mkdir(exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="staging-second-principal-", dir=TEMP)).resolve()
    try:
        copied = run_dir / "amail.exe"
        shutil.copy2(binary, copied)
        require(route("--apply", ADDRESS) in ("created", "enabled"), "route_create_failed")
        if mode == "provision":
            registration(run_dir, ADDRESS, credential=(username, password),
                         code_source=lambda started: guarded_code(account, token, baseline, started))
        else:
            from staging_identity_cdp import store_credential
            store_credential(run_dir, username, password, ADDRESS)
            recover_contact(run_dir, username, password, account, token, baseline)
        require(route(address=ADDRESS) == "absent", "route_cleanup_unverified")
        native_login(run_dir, copied, expected_address=ADDRESS)
        after = identity_contacts(account, token)
        require(ADDRESS in after and after[ADDRESS][2] == "verified"
                and after[ADDRESS][3] == username
                and after[ADDRESS][0] != before[FIRST][0]
                and after[ADDRESS][1] and before[FIRST][1]
                and after[ADDRESS][1] != before[FIRST][1],
                "independent_subject_unverified")
    finally:
        cleanup_failed = False
        try:
            if route(address=ADDRESS) == "enabled":
                route("--remove", ADDRESS)
            cleanup_failed |= route(address=ADDRESS) != "absent"
        except Exception:
            cleanup_failed = True
        # All post-baseline objects are run-window deliveries to this private
        # synthetic inbox. Remove even ambiguous/late ones, never baseline keys.
        for settle_seconds in (0, 60):
            if settle_seconds:
                time.sleep(settle_seconds)
            try:
                fresh = object_inventory(account, token) - baseline
                for key in fresh:
                    deleted = request(
                        "DELETE", f"/accounts/{account}/r2/buckets/{BUCKET}/objects/{key}", token
                    )
                    if deleted:
                        json_result(deleted)
            except ProvisionFailure:
                cleanup_failed = True
        try:
            cleanup_failed |= bool(object_inventory(account, token) - baseline)
        except ProvisionFailure:
            cleanup_failed = True
        try:
            shutil.rmtree(run_dir)
        except OSError:
            cleanup_failed = True
        require(not cleanup_failed, "private_principal_cleanup_required")
    print("staging_second_principal_recovered_distinct_native_subject" if mode == "recover"
          else "staging_second_principal_provisioned_distinct_native_subject")


def main() -> int:
    """Emit only fixed labels, never provider responses or exception reprs."""

    try:
        if os.environ.get("AMAIL_SECOND_PRINCIPAL_MODE") == "preflight":
            read_only_preflight()
        else:
            execute()
        return 0
    except ProvisionFailure as error:
        label = str(error)
        print("staging_second_principal_failed:" +
              (label if re.fullmatch(r"[a-z][a-z0-9_]{2,100}", label)
               else "unexpected_failure"), file=sys.stderr)
    except Exception:
        print("staging_second_principal_failed:unexpected_failure", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
