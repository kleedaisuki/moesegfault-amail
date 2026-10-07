"""Extend the existing controlled Windows staging journey with real Subscribe UI.

This simulates a human only for the protected synthetic staging identity. It is
not financial consent from an actual customer and never issues activation codes.
No URL, credential, activation code, browser body or provider prose is logged.
"""

from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import time
from urllib.parse import urlsplit
import uuid


CONFIRMATION = "RUN_STAGING_BILLING_V020"
SUBSCRIBE = "https://subscribe-staging.moesegfault.dev"


class BillingProbeError(Exception):
    """A fixed nonsensitive phase label for the existing hosted harness."""


def validate_url(value: object) -> str:
    """Accept only the deployed opaque staging navigation path, never credentials."""
    if not isinstance(value, str):
        raise BillingProbeError("billing_authorization_url_invalid")
    parsed = urlsplit(value)
    if (f"{parsed.scheme}://{parsed.netloc}" != SUBSCRIBE or parsed.query or parsed.fragment
            or not re.fullmatch(r"/amail/authorize/[A-Za-z0-9_-]{24,128}", parsed.path)):
        raise BillingProbeError("billing_authorization_url_invalid")
    return value


def rows(stdout: str) -> list[dict]:
    """Decode bounded CLI JSONL in memory, never reflect a malformed server reply."""
    try:
        if len(stdout.encode()) > 64 * 1024:
            raise ValueError()
        result = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        if not result or any(not isinstance(row, dict) for row in result):
            raise ValueError()
        return result
    except (ValueError, TypeError):
        raise BillingProbeError("billing_cli_response_invalid") from None


def execute(binary: Path, home: Path, run_dir: Path) -> dict:
    """Run proposal→browser cancel/approve→authoritative CLI receipt on one owner."""
    started_at_ms = int(time.time() * 1000)
    if os.environ.get("AMAIL_STAGING_BILLING_CONFIRM") != CONFIRMATION:
        raise BillingProbeError("billing_explicit_confirmation_required")
    plan = os.environ.get("AMAIL_STAGING_BILLING_PLAN", "free")
    if plan not in {"free", "lite"}:
        raise BillingProbeError("billing_test_plan_invalid")
    # Remove before any child is launched. Browser typing is the only consumer.
    code = os.environ.pop("STAGING_E2E_AMAIL_ACTIVATION_CODE", "")
    if plan == "lite" and not 16 <= len(code) <= 256:
        raise BillingProbeError("billing_legitimate_activation_code_required")
    if plan == "free" and code:
        raise BillingProbeError("billing_unexpected_activation_material")
    from staging_identity_cdp import Browser, load_credential, ProbeError
    from staging_mail_e2e import cli_env

    environment = cli_env(home)
    environment["AMAIL_TELEMETRY"] = "on"

    def cli(*arguments: str) -> list[dict]:
        """Run exact admitted bytes without inherited operator or activation secrets."""
        try:
            result = subprocess.run([str(binary), *arguments], env=environment,
                                    capture_output=True, text=True, timeout=90, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise BillingProbeError("billing_cli_execution_failed") from None
        if result.returncode:
            raise BillingProbeError("billing_cli_execution_failed")
        return rows(result.stdout)

    baseline = cli("billing", "status")[-1]
    if baseline.get("account", {}).get("plan") != "free":
        raise BillingProbeError("billing_synthetic_account_not_free")
    username, password, _ = load_credential(run_dir)
    browser = Browser(run_dir / f"billing-browser-{uuid.uuid4().hex}")

    def wait_for(predicate: str, label: str, seconds: int = 60) -> None:
        """Wait for a positive DOM condition, tolerating only navigation context races."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                if browser.evaluate(predicate) is True:
                    return
            except ProbeError as error:
                if str(error) != "chrome_execution_context_changed":
                    raise
            time.sleep(0.2)
        raise BillingProbeError(label)

    def open_intent(selected: str) -> str:
        """Each fresh logical approval has one UUID; the browser URL stays in memory."""
        key = str(uuid.uuid4())
        result = cli("billing", "subscribe", selected, "--no-browser", "--idempotency-key", key)
        intent = result[-1]
        if intent.get("session_id") != key or intent.get("state") != "pending":
            raise BillingProbeError("billing_pending_intent_missing")
        url = validate_url(intent.get("authorization_url"))
        browser.call("Page.navigate", {"url": url})
        wait_for("location.origin === " + json.dumps(SUBSCRIBE) +
                 " && (Boolean(document.querySelector('#amail-plan')) || Boolean(document.querySelector('a.moe-button')))",
                 "billing_hosted_authorization_missing")
        if browser.evaluate("Boolean(document.querySelector('#amail-plan'))") is not True:
            browser.click("a.moe-button")
            browser.wait_dom('input[name="login"]', timeout=60)
            browser.require_login_origin()
            browser.fill('input[name="login"]', username)
            browser.fill('input[name="password"]', password)
            browser.click('form.auth-form button[type="submit"]')
            browser.wait_dom("#amail-plan", timeout=60)
        if browser.evaluate("location.origin") != SUBSCRIBE:
            raise BillingProbeError("billing_first_party_origin_mismatch")
        return key

    try:
        cancelled = open_intent("free")
        browser.click(".authorization-panel .form-footer button[type=button]")
        wait_for("!document.querySelector('#amail-plan') && document.body.innerText.includes('请求已取消')",
                 "billing_browser_cancel_missing")
        if cli("billing", "session", cancelled)[-1].get("state") != "cancelled":
            raise BillingProbeError("billing_cancel_receipt_missing")
        session_id = open_intent(plan)
        if browser.evaluate("document.querySelector('#amail-plan').value") != f"amail-{plan}":
            raise BillingProbeError("billing_browser_plan_mismatch")
        if plan == "lite":
            browser.wait_dom("#activation-code")
            browser.fill("#activation-code", code)
            code = ""
            browser.click("#activation-code + button")
            wait_for("Boolean(document.querySelector('.notice-success'))", "billing_activation_not_confirmed")
        browser.fill("#amail-budget", "0")
        browser.click(".consent-check input[type=checkbox]")
        browser.click(".authorization-panel .form-footer button:not([type=button])")
        wait_for("!document.querySelector('#amail-plan') && document.body.innerText.includes('授权已完成')",
                 "billing_browser_approval_missing")
        browser.click('a[href="https://amail-staging.moesegfault.dev/billing/return"]')
        wait_for("location.origin === 'https://amail-staging.moesegfault.dev' "
                 "&& location.pathname === '/billing/return' "
                 "&& document.querySelector('h1')?.innerText.includes('回到你的 Agent')",
                 "billing_return_page_missing")
        if cli("billing", "session", session_id, "--wait-seconds", "30")[-1].get("state") != "completed":
            raise BillingProbeError("billing_authoritative_receipt_missing")
        final = cli("billing", "status")[-1]
        account = final.get("account", {})
        if (account.get("plan") != plan or account.get("overage_budget_micros") != 0
                or final.get("payment_collection_available") is not False):
            raise BillingProbeError("billing_entitlement_readback_invalid")
        try:
            flushed = subprocess.run([str(binary), "_telemetry-flush"], env=environment,
                                     capture_output=True, timeout=60, check=False)
            if flushed.returncode:
                raise BillingProbeError("billing_cli_telemetry_flush_failed")
        except (OSError, subprocess.TimeoutExpired):
            raise BillingProbeError("billing_cli_telemetry_flush_failed") from None
        with closing(sqlite3.connect(f"file:{home / 'telemetry.sqlite3'}?mode=ro", uri=True)) as db:
            traces = [row[0] for row in db.execute(
                "SELECT DISTINCT trace_id FROM events WHERE operation IN "
                "('billing.session.create','billing.session.status','billing.status') ORDER BY id")]
        if not traces or any(not re.fullmatch(r"[0-9a-f]{32}", trace) for trace in traces):
            raise BillingProbeError("billing_cli_trace_ids_missing")
        print(f"staging_billing_browser_cancel_and_{plan}_receipt_verified")
        return {"schema_version": 1, "plan": plan, "cancelled": True, "browser_return_verified": True,
                "human_simulation": "protected_synthetic_identity", "payment_collection_verified": False,
                "trace_ids": traces, "started_at_ms": started_at_ms, "ended_at_ms": int(time.time() * 1000)}
    finally:
        code = ""
        browser.close()
