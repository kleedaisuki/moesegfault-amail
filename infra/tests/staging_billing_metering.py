"""Explicit synthetic staging address overage, using normal CLI/UI mutations only.

The only provider SQL is a fixed SELECT allowlist. No mail is sent, usage is never
seeded, and the private owner/address/authorization values stay in process memory.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time
import urllib.request
import uuid


CONFIRMATION = "RUN_STAGING_BILLING_METERING_V020"
BUDGET_MICROS = 3_000_000
MAX_ACTUAL_MICROS = 10_000
DELIVERY_SECONDS = 660
# Two bounded network reads (25 seconds each) and the parent's final flush (60).
# Poll admission must leave this room inside the 810-second evidence envelope.
FINALIZATION_SECONDS = 110
CAPACITY_SQL = "SELECT COUNT(*) AS n FROM addresses WHERE state!='retired'"
OWNER_SQL = ("SELECT owner_iss,owner_sub,COUNT(*) AS n FROM addresses "
             "WHERE address IN (?1,?2,?3,?4) GROUP BY owner_iss,owner_sub")
EVENT_SQL = ("SELECT event_id,billing_owner_id,meter,quantity,amount_micros,occurred_at,"
             "period_start,period_end,delivered_at,origin_traceparent FROM resource_outbox "
             "WHERE owner_iss=?1 AND owner_sub=?2 AND period_start=?3 ORDER BY occurred_at,event_id LIMIT 65")
READ_QUERIES = {CAPACITY_SQL, OWNER_SQL, EVENT_SQL}


class MeteringError(Exception):
    """Only a fixed safe phase label can reach the hosted runner's diagnostics."""


def check(condition: bool, label: str) -> None:
    """Stop on a missing positive witness without reflecting private response data."""
    if not condition:
        raise MeteringError(label)


def read_json(request: urllib.request.Request, maximum: int = 131072) -> dict:
    """Use fixed first-party/provider endpoints, no redirect and bounded JSON output."""
    from staging_trace_witness import RejectRedirect
    try:
        with urllib.request.build_opener(RejectRedirect).open(request, timeout=25) as response:
            check(response.status == 200, "metering_read_status")
            raw = response.read(maximum + 1)
        check(len(raw) <= maximum, "metering_read_oversized")
        result = json.loads(raw)
        check(isinstance(result, dict), "metering_read_shape")
        return result
    except MeteringError:
        raise
    except Exception:
        raise MeteringError("metering_read_unavailable") from None


def d1_read(sql: str, params: list) -> list[dict]:
    """Read only three reviewed SELECTs against the fixed staging Mail database."""
    from acceptance_realm import STAGING
    from staging_trace_witness import USER_AGENT
    check(sql in READ_QUERIES, "metering_query_not_allowlisted")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    check(bool(re.fullmatch(r"[0-9a-f]{32}", account)) and bool(token), "metering_read_credentials_missing")
    request = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{account}/d1/database/{STAGING.mail_database_id}/query",
        data=json.dumps({"sql": sql, "params": params}).encode(), method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": USER_AGENT})
    data = read_json(request)
    batches = data.get("result")
    check(data.get("success") is True and isinstance(batches, list) and len(batches) == 1,
          "metering_d1_read_shape")
    batch = batches[0]
    result = batch.get("results") if isinstance(batch, dict) and batch.get("success") is True else None
    check(isinstance(result, list) and len(result) <= 64 and all(isinstance(row, dict) for row in result),
          "metering_d1_read_truncated")
    return result


def usage_read(owner: str, period: int) -> dict:
    """Read actual Billing liabilities; the service credential never enters the CLI."""
    from staging_trace_witness import USER_AGENT
    check(isinstance(owner, str) and bool(re.fullmatch(r"[0-9a-f]{64}", owner)) and type(period) is int,
          "metering_usage_scope_invalid")
    key = os.environ.get("BILLING_SERVICE_KEY", "")
    check(bool(key), "metering_service_key_missing")
    request = urllib.request.Request(
        f"https://billing-staging.moesegfault.dev/v1/service/amail/accounts/{owner}/usage?period_start={period}",
        headers={"Authorization": f"Bearer {key}", "User-Agent": USER_AGENT})
    return read_json(request)


def preflight(account: dict, addresses: list[dict], registered: int, provider_rules: int) -> None:
    """Admit only an empty synthetic Lite account with four genuinely available slots."""
    check(account.get("plan") == "lite" and account.get("included_addresses") == 3
          and account.get("grandfathered_addresses") == 0 and account.get("address_count") == 0
          and account.get("overage_budget_micros") == 0 and not addresses,
          "metering_account_not_pristine_lite")
    check(type(account.get("storage_bytes")) is int and type(account.get("included_storage_bytes")) is int
          and 0 <= account["storage_bytes"] <= account["included_storage_bytes"]
          and account.get("outbound_reserved") == 0, "metering_other_resource_exposure")
    check(type(registered) is int and 0 <= registered <= 194
          and type(provider_rules) is int and 0 <= provider_rules <= 196,
          "metering_four_slots_unavailable")
    check(type(account.get("period_start")) is int and type(account.get("period_end")) is int
          and account["period_end"] - int(time.time()) > 1200
          and type(account.get("valid_until")) is int and account["valid_until"] - int(time.time()) > 1200,
          "metering_period_boundary_too_close")


def verify_delivery(events: list[dict], usage: dict, started: int, period: int) -> dict:
    """Compare actual durable outbox totals to actual pending-settlement Billing totals."""
    check(0 < len(events) <= 64, "metering_outbox_empty")
    ids = set()
    total = task_total = task_quantity = 0
    trace_ids = set()
    for event in events:
        identity = event.get("event_id")
        check(isinstance(identity, str) and identity not in ids, "metering_event_identity_invalid")
        ids.add(identity)
        amount = event.get("amount_micros")
        check(type(amount) is int and amount >= 0 and type(event.get("delivered_at")) is int,
              "metering_event_not_delivered")
        check(event.get("period_start") == period, "metering_event_period_invalid")
        total += amount
        if event.get("occurred_at", 0) >= started and event.get("meter") == "address_seconds":
            check(type(event.get("quantity")) is int and event["quantity"] > 0, "metering_quantity_invalid")
            task_total += amount
            task_quantity += event["quantity"]
            context = event.get("origin_traceparent")
            check(isinstance(context, str) and re.fullmatch(r"00-[0-9a-f]{32}-[0-9a-f]{16}-01", context),
                  "metering_original_trace_missing")
            trace_ids.add(context[3:35])
    check(0 < task_total <= MAX_ACTUAL_MICROS, "metering_actual_charge_out_of_bounds")
    check(usage.get("owner_id") == events[0].get("billing_owner_id")
          and usage.get("period_start") == period and type(usage.get("amount_micros")) is int
          and usage.get("amount_micros") == total and type(usage.get("events_count")) is int
          and usage.get("events_count") == len(events)
          and usage.get("overage_budget_micros") == 0
          and usage.get("settlement_status") == "pending_settlement", "metering_billing_totals_mismatch")
    return {"schema_version": 1, "address_seconds": task_quantity, "amount_micros": task_total,
            "events_delivered": len(events), "budget_restored_micros": 0,
            "settlement_status": "pending_settlement", "payment_collection_verified": False,
            "trace_ids": sorted(trace_ids)}


def execute(binary: Path, home: Path, run_dir: Path, *, evidence_started_at_ms: int | None = None) -> dict:
    """Authorize 3 CNY ceiling, briefly occupy one extra slot, retire all, restore zero."""
    check(os.environ.get("AMAIL_STAGING_BILLING_METERING_CONFIRM") == CONFIRMATION
          and os.environ.get("AMAIL_STAGING_BILLING_CONFIRM") == "RUN_STAGING_BILLING_V020"
          and os.environ.get("AMAIL_STAGING_BILLING_PLAN") == "lite"
          and os.environ.get("AMAIL_STAGING_BILLING_TRACE") == "true", "metering_confirmation_required")
    # Leave 90 seconds for the existing retained reader's bounded 15-minute window.
    evidence_start = evidence_started_at_ms if evidence_started_at_ms is not None else int(time.time() * 1000)
    check(type(evidence_start) is int and 0 <= time.time() * 1000 - evidence_start < 810_000,
          "metering_evidence_window_invalid")
    from staging_billing_e2e import needs_activation, subscription_view, validate_url
    from staging_identity_cdp import Browser, load_credential, ProbeError
    import staging_mail_e2e as mail

    environment = mail.cli_env(home)
    environment["AMAIL_TELEMETRY"] = "on"
    # Only the earlier activation helper may consume this capability; never copy it.
    check(not os.environ.get("STAGING_E2E_AMAIL_ACTIVATION_CODE"), "metering_activation_material_present")

    def cli(*arguments: str) -> list[dict]:
        """Reuse the existing in-memory, allowlisted CLI subprocess adapter."""
        try:
            return mail.amail(binary, environment, *arguments, failure="metering_cli_failed")
        except Exception:
            raise MeteringError("metering_cli_failed") from None

    initial = cli("billing", "status")[-1].get("account", {})
    count = d1_read(CAPACITY_SQL, [])
    check(len(count) == 1, "metering_capacity_shape")
    preflight(initial, cli("address", "list"), count[0].get("n"),
              len(mail.cf_rules(os.environ.get("CLOUDFLARE_ZONE_ID", ""),
                                os.environ.get("CF_EMAIL_ROUTING_TOKEN", ""))))
    check(bool(os.environ.get("BILLING_SERVICE_KEY")), "metering_service_key_missing")
    username, password, _ = load_credential(run_dir)
    browser = Browser(run_dir / f"metering-browser-{uuid.uuid4().hex}")
    nonce = uuid.uuid4().hex[:16]
    targets = [f"meter-{nonce}-{n}@mail-staging.moesegfault.dev" for n in range(4)]
    attempted = []
    budget_attempted = False
    failure = None
    cleanup_failed = restore_failed = False
    owner = None
    started = int(time.time())

    def wait(expression: str, label: str, seconds: int = 60) -> None:
        """Observe positive DOM/server state; never replay a mutation to wait for it."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                if browser.evaluate(expression) is True:
                    return
            except ProbeError as error:
                if str(error) != "chrome_execution_context_changed":
                    raise
            time.sleep(0.2)
        raise MeteringError(label)

    def budget(micros: int) -> None:
        """Normal human-simulation Manage UI grants only the reviewed 3 or 0 CNY cap."""
        check(micros in {0, BUDGET_MICROS}, "metering_budget_invalid")
        intent = cli("billing", "manage", "--no-browser", "--idempotency-key", str(uuid.uuid4()))[-1]
        check(intent.get("state") == "pending", "metering_manage_not_pending")
        browser.call("Page.navigate", {"url": validate_url(intent.get("authorization_url"))})
        wait("location.origin==='https://subscribe-staging.moesegfault.dev' && "
             "(Boolean(document.querySelector('#amail-plan'))||Boolean(document.querySelector('a.moe-button')))",
             "metering_authorization_page_missing")
        if browser.evaluate("Boolean(document.querySelector('#amail-plan'))") is not True:
            browser.click("a.moe-button")
            wait("Boolean(document.querySelector('#amail-plan'))||Boolean(document.querySelector('input[name=login]'))",
                 "metering_sso_missing")
            if browser.evaluate("Boolean(document.querySelector('input[name=login]'))") is True:
                browser.require_login_origin()
                browser.fill('input[name="login"]', username)
                browser.fill('input[name="password"]', password)
                browser.click('form.auth-form button[type="submit"]')
                browser.wait_dom("#amail-plan", timeout=60)
        check(browser.evaluate("location.origin") == "https://subscribe-staging.moesegfault.dev"
              and browser.evaluate("document.querySelector('#amail-plan').value") == "amail-lite",
              "metering_authorization_plan_changed")
        check(not needs_activation(subscription_view(browser), "lite", int(time.time())),
              "metering_existing_lite_grant_required")
        browser.fill("#amail-budget", "3.00" if micros else "0")
        browser.click(".consent-check input[type=checkbox]")
        browser.click(".authorization-panel .form-footer button:not([type=button])")
        wait("!document.querySelector('#amail-plan')&&document.body.innerText.includes('授权已完成')",
             "metering_budget_approval_missing")
        check(cli("billing", "session", intent["session_id"], "--wait-seconds", "30")[-1].get("state") == "completed",
              "metering_budget_receipt_missing")
        state = cli("billing", "status")[-1].get("account", {})
        check(state.get("plan") == "lite" and state.get("overage_budget_micros") == micros,
              "metering_budget_readback_mismatch")

    try:
        budget_attempted = True
        budget(BUDGET_MICROS)
        for address in targets:
            attempted.append(address)
            result = cli("address", "add", address.split("@")[0])
            check(len(result) == 1 and result[0].get("address") == address, "metering_address_creation_unknown")
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            actual = cli("address", "list")
            if {row.get("address") for row in actual} == set(targets) and all(row.get("state") == "active" for row in actual):
                break
            time.sleep(2)
        else:
            raise MeteringError("metering_four_active_addresses_missing")
        owners = d1_read(OWNER_SQL, targets)
        check(len(owners) == 1 and owners[0].get("n") == 4
              and owners[0].get("owner_iss") == "https://identity-staging.moesegfault.dev"
              and isinstance(owners[0].get("owner_sub"), str), "metering_owned_identity_unverified")
        owner = (owners[0]["owner_iss"], owners[0]["owner_sub"])
        # The production meter uses integer seconds; two real seconds make the fee positive.
        time.sleep(2.1)
    except Exception as error:
        failure = str(error) if isinstance(error, MeteringError) else "metering_action_failed"
    finally:
        try:
            owned = {row.get("address") for row in cli("address", "list")}
            for address in attempted:
                if address in owned:
                    try:
                        cli("address", "delete", address)
                    except Exception:
                        cleanup_failed = True
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if not cli("address", "list"):
                    break
                time.sleep(3)
            else:
                cleanup_failed = True
        except Exception:
            cleanup_failed = True
        try:
            if budget_attempted:
                budget(0)
        except Exception:
            restore_failed = True
        try:
            browser.close()
        except Exception:
            cleanup_failed = True
    if failure or cleanup_failed or restore_failed:
        label = ("metering_cleanup_and_restore_failed" if cleanup_failed and restore_failed
                 else "metering_cleanup_failed" if cleanup_failed
                 else "metering_restore_failed" if restore_failed else failure)
        raise MeteringError(label)
    check(owner is not None, "metering_owned_identity_unverified")
    cli("_telemetry-flush")
    remaining = max(0, evidence_start / 1000 + 810 - FINALIZATION_SECONDS - time.time())
    deadline = time.monotonic() + min(DELIVERY_SECONDS, remaining)
    last = "metering_delivery_timeout"
    while time.monotonic() < deadline:
        try:
            events = d1_read(EVENT_SQL, [*owner, initial["period_start"]])
            check(bool(events), "metering_outbox_empty")
            billing_owner = events[0].get("billing_owner_id")
            check(all(row.get("billing_owner_id") == billing_owner for row in events), "metering_owner_changed")
            summary = verify_delivery(events, usage_read(billing_owner, initial["period_start"]), started,
                                      initial["period_start"])
            summary["addresses_created_and_retired"] = 4
            summary["human_simulation"] = "protected_synthetic_identity"
            print("staging_billing_real_address_overage_pending_settlement_verified")
            return summary
        except MeteringError as error:
            last = str(error)
        time.sleep(min(10, max(0, deadline - time.monotonic())))
    raise MeteringError(last)
