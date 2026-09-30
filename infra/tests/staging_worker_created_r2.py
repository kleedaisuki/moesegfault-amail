"""One-shot hosted GET/DELETE proof using a private Email-Worker-created object.

The probe sends one synthetic, non-OTP message to the existing A test alias.
Recovery closes that exact route before inspecting the prior run's candidate.
Neither mode registers Identity B or calls R2 REST PUT. Both emit fixed labels.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

from staging_r2_object_capability import (OPENER, ProbeFailure as R2ProbeFailure,
                                          audit, call, object_path)
from staging_second_principal import (ADDRESS, FIRST, identity_contacts,
                                      object_inventory)


ROOT = Path(__file__).resolve().parents[2]
ROUTE_HELPER = ROOT / "workers" / "identity-test-inbox" / "ensure_route.py"
REPOSITORY = "kleedaisuki/moesegfault-amail"
BRANCH = "codex/amail-v0.1.0"
JOB_NAME = "One-shot Worker-created R2 GET/DELETE"
SENDER = "mail@moesegfault.dev"
TEMPLATE = "amail private R2 capability v1 "
MAX_MIME = 8_192
MAX_GITHUB = 524_288


class ProbeFailure(Exception):
    """Carry only a fixed source-owned stage label to Actions output."""


def require(condition: bool, label: str) -> None:
    """Fail closed without interpolating private values into a label."""

    if not condition:
        raise ProbeFailure(label)


def run_id(value: str) -> str:
    """Accept one positive decimal GitHub run or attempt identifier."""

    require(re.fullmatch(r"[1-9][0-9]{0,19}", value) is not None,
            "run_identity_invalid")
    return value


def marker(value: str, attempt: str) -> str:
    """Create a reproducible, non-secret MIME marker for crash recovery."""

    identity = (run_id(value) + ":" + run_id(attempt)).encode("ascii")
    return hashlib.sha256(b"amail/staging/worker-created-r2/v1\0" + identity).hexdigest()


def route(action: str) -> str:
    """Use the reviewed exact-route helper without forwarding bearer on redirects."""

    require(action in ("apply", "audit", "remove"), "route_action_invalid")
    spec = importlib.util.spec_from_file_location("staging_worker_r2_route", ROUTE_HELPER)
    require(spec is not None and spec.loader is not None, "route_helper_unavailable")
    module = importlib.util.module_from_spec(spec)
    prior = urllib.request.urlopen
    try:
        urllib.request.urlopen = OPENER.open
        spec.loader.exec_module(module)
        state = module.reconcile(os.environ["CLOUDFLARE_ZONE_ID"],
                                 os.environ["CF_EMAIL_ROUTING_TOKEN"], action, FIRST)
    except Exception:
        raise ProbeFailure("exact_route_control_failed") from None
    finally:
        urllib.request.urlopen = prior
    require(state in ("created", "enabled", "removed", "absent"),
            "exact_route_state_invalid")
    return state


def close_route() -> None:
    """Remove only the owned A rule and require absence before object deletion."""

    require(route("remove") in ("removed", "absent") and route("audit") == "absent",
            "route_cleanup_unverified")


def github_json(path: str, token: str) -> dict:
    """Read bounded GitHub run metadata without redirects, logs or raw output."""

    request = urllib.request.Request(
        "https://api.github.com" + path,
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"},
    )
    try:
        with OPENER.open(request, timeout=20) as response:
            raw = response.read(MAX_GITHUB + 1)
            require(response.status == 200 and len(raw) <= MAX_GITHUB,
                    "prior_run_metadata_unavailable")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        raise ProbeFailure("prior_run_metadata_unavailable") from None
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise ProbeFailure("prior_run_metadata_invalid") from None
    require(isinstance(value, dict), "prior_run_metadata_invalid")
    return value


def parse_time(value: object) -> datetime:
    """Require a timezone-aware GitHub timestamp without exposing its text."""

    require(isinstance(value, str), "prior_run_metadata_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ProbeFailure("prior_run_metadata_invalid") from None
    require(parsed.tzinfo is not None, "prior_run_metadata_invalid")
    return parsed.astimezone(timezone.utc)


def prior_window(value: str, attempt: str) -> tuple[datetime, datetime]:
    """Validate exact prior run/attempt, job identity and a 24-hour window."""

    run_id(value)
    run_id(attempt)
    require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY and
            int(value) < int(run_id(os.environ.get("GITHUB_RUN_ID", ""))),
            "prior_run_identity_invalid")
    token = os.environ.get("GITHUB_TOKEN", "")
    require(bool(token), "github_token_missing")
    source_sha = os.environ.get("AMAIL_WORKER_R2_PRIOR_SHA", "")
    require(re.fullmatch(r"[0-9a-f]{40}", source_sha) is not None,
            "prior_run_source_unreviewed")
    base = f"/repos/{REPOSITORY}/actions/runs/{value}/attempts/{attempt}"
    run = github_json(base, token)
    start = parse_time(run.get("created_at"))
    end = parse_time(run.get("updated_at"))
    now = datetime.now(timezone.utc)
    require(run.get("id") == int(value) and run.get("run_attempt") == int(attempt)
            and run.get("event") == "workflow_dispatch" and run.get("status") == "completed"
            and run.get("conclusion") in ("failure", "cancelled", "timed_out")
            and run.get("head_branch") == BRANCH
            and run.get("head_sha") == source_sha
            and isinstance(run.get("path"), str)
            and run["path"].startswith(".github/workflows/ci.yml@")
            and start <= end <= now + timedelta(minutes=2)
            and now - start <= timedelta(hours=24), "prior_run_metadata_invalid")
    jobs = github_json(base + "/jobs?per_page=100", token)
    entries = jobs.get("jobs")
    require(type(jobs.get("total_count")) is int and jobs["total_count"] <= 100
            and isinstance(entries, list) and len(entries) == jobs["total_count"]
            and any(isinstance(job, dict) and job.get("name") == JOB_NAME
                    and job.get("status") == "completed" for job in entries),
            "prior_run_job_invalid")
    return start, end + timedelta(minutes=10)


def synthetic_mail(raw: bytes, value: str, attempt: str,
                   window: tuple[datetime, datetime]) -> bool:
    """Recognize only this run's one tiny text-only, non-OTP MIME message."""

    if not 0 < len(raw) <= MAX_MIME:
        return False
    try:
        message = BytesParser(policy=policy.default).parsebytes(raw)
        if any(part.defects for part in message.walk()):
            return False
        headers = ("From", "To", "Subject", "Date")
        if any(len(message.get_all(name, [])) != 1 for name in headers):
            return False
        senders = getaddresses([str(message["From"])])
        recipients = getaddresses([str(message["To"])])
        sent = parsedate_to_datetime(str(message["Date"]))
        if (len(senders) != 1 or senders[0][1].lower() != SENDER
                or len(recipients) != 1 or recipients[0][1].lower() != FIRST
                or sent.tzinfo is None):
            return False
        if not window[0] - timedelta(minutes=2) <= sent.astimezone(timezone.utc) <= window[1]:
            return False
        nonce = marker(value, attempt)
        if str(message["Subject"]) != TEMPLATE + nonce:
            return False
        leaves = [part for part in message.walk() if not part.is_multipart()]
        if (len(leaves) != 1 or leaves[0].get_content_type() != "text/plain"
                or leaves[0].get_content_disposition() is not None):
            return False
        return leaves[0].get_content().strip() == TEMPLATE + nonce
    except (ValueError, TypeError, UnicodeError, KeyError):
        return False


def send_once(account: str, token: str, value: str, attempt: str) -> bool:
    """Submit one synthetic message; never retry an uncertain provider result."""

    nonce = marker(value, attempt)
    content = TEMPLATE + nonce
    payload = json.dumps({"to": FIRST, "from": SENDER, "subject": content,
                          "text": content}, separators=(",", ":")).encode()
    try:
        status, raw = call("POST", f"/accounts/{account}/email/sending/send", token,
                           payload, "application/json")
        value_json = json.loads(raw) if status == 200 else {}
        result = value_json.get("result")
        accepted = (status == 200 and value_json.get("success") is True
                    and isinstance(result, dict)
                    and FIRST in (result.get("delivered") or []) + (result.get("queued") or [])
                    and not result.get("permanent_bounces") and not result.get("suppressed_recipients"))
        return bool(accepted)
    except (ValueError, TypeError, AttributeError, R2ProbeFailure):
        return False


def sender_ready() -> None:
    """Require the exact apex sender domain enabled before opening A's route."""

    zone = os.environ["CLOUDFLARE_ZONE_ID"]
    token = os.environ["CLOUDFLARE_API_TOKEN"]
    try:
        status, raw = call("GET", f"/zones/{zone}/email/sending/subdomains", token)
    except R2ProbeFailure:
        raise ProbeFailure("sender_read_unavailable") from None
    require(status == 200, "sender_read_unavailable")
    try:
        value = json.loads(raw)
        rows = value.get("result")
        info = value.get("result_info")
        good = (value.get("success") is True and isinstance(rows, list)
                and len(rows) <= 100 and
                (info is None or isinstance(info, dict) and
                 info.get("total_pages") in (None, 1)))
    except (ValueError, TypeError, AttributeError):
        good = False
        rows = []
    require(good, "sender_read_invalid")
    matches = [row for row in rows if isinstance(row, dict)
               and row.get("name") == "moesegfault.dev"]
    require(len(matches) == 1 and matches[0].get("enabled") is True,
            "apex_sender_not_enabled")


def one_key() -> str | None:
    """Require at most one object in the otherwise-empty private inbox."""

    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    token = os.environ["CLOUDFLARE_API_TOKEN"]
    keys = object_inventory(account, token)
    require(len(keys) <= 1, "private_inventory_ambiguous")
    return next(iter(keys)) if keys else None


def get_owned(key: str, value: str, attempt: str,
              window: tuple[datetime, datetime]) -> str:
    """Read an existing object and reject any byte-unowned or denied result."""

    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    token = os.environ["CLOUDFLARE_API_TOKEN"]
    try:
        status, raw = call("GET", object_path(account, key), token)
    except R2ProbeFailure:
        raise ProbeFailure("object_get_unverified") from None
    if status == 200:
        require(synthetic_mail(raw, value, attempt, window), "synthetic_mime_mismatch")
        return "present"
    if status == 404:
        require(key not in object_inventory(account, token), "object_absence_ambiguous")
        return "absent"
    raise ProbeFailure("object_get_denied" if status == 403 else "object_get_unverified")


def delete_owned(key: str, value: str, attempt: str,
                 window: tuple[datetime, datetime]) -> None:
    """Delete only proven synthetic bytes, read back before uncertain retry."""

    from staging_r2_object_capability import delete

    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    token = os.environ["CLOUDFLARE_API_TOKEN"]
    require(get_owned(key, value, attempt, window) == "present", "object_not_present")
    try:
        delete(account, key, token)
    except R2ProbeFailure as error:
        if str(error) == "r2_delete_denied":
            raise ProbeFailure("object_delete_denied") from None
        # A failed/ambiguous DELETE might already have taken effect. Never
        # issue another write until exact-key GET has proved the same bytes.
        state = get_owned(key, value, attempt, window)
        if state == "present":
            try:
                delete(account, key, token)
            except R2ProbeFailure:
                raise ProbeFailure("object_delete_unverified") from None
    require(get_owned(key, value, attempt, window) == "absent"
            and key not in object_inventory(account, token), "object_cleanup_unverified")


def reconcile(value: str, attempt: str, window: tuple[datetime, datetime],
              settle: bool) -> bool:
    """After route closure, remove one owned MIME or prove empty inventory."""

    key = one_key()
    if key is None and settle:
        time.sleep(60)
        key = one_key()
    if key is None:
        return False
    delete_owned(key, value, attempt, window)
    if settle:
        time.sleep(60)
        require(one_key() is None, "late_delivery_unverified")
    return True


def probe() -> None:
    """Open one A route, submit one message, then prove GET/DELETE or clean up."""

    require(os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "probe_rerun_forbidden")
    value = run_id(os.environ.get("GITHUB_RUN_ID", ""))
    attempt = "1"
    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    token = os.environ["CLOUDFLARE_API_TOKEN"]
    audit("check_config.py", "--live", "--deployed")
    audit("ensure_route.py", "--all-absent")
    try:
        contacts = identity_contacts(account, token)
    except Exception:
        raise ProbeFailure("identity_contact_preflight_failed") from None
    require(FIRST in contacts and contacts[FIRST][2] == "verified" and ADDRESS not in contacts,
            "identity_contact_preflight_failed")
    sender_ready()
    require(os.environ.get("AMAIL_SENDING_GRANT_ATTEST") ==
            "ATTEST_ONE_SYNTHETIC_APEX_SEND", "sending_grant_attestation_missing")
    require(one_key() is None, "private_inbox_not_empty")
    started = datetime.now(timezone.utc)
    route_possible = True  # Installed before an ambiguous route-create response.
    route_closed = False
    send_possible = False
    failure: ProbeFailure | None = None
    proved = False
    try:
        require(route("apply") == "created" and route("audit") == "enabled",
                "route_create_unverified")
        opened = time.monotonic()
        time.sleep(60)
        require(route("audit") == "enabled", "route_settle_unverified")
        require(time.monotonic() - opened <= 240, "route_window_expired")
        send_possible = True
        accepted = send_once(account, token, value, attempt)
        deadline = min(opened + 240, time.monotonic() + 150)
        candidate = one_key()
        while candidate is None and time.monotonic() < deadline:
            time.sleep(5)
            candidate = one_key()
        close_route()
        route_closed = True
        require(candidate is not None, "synthetic_delivery_missing")
        window = (started, datetime.now(timezone.utc) + timedelta(minutes=2))
        delete_owned(candidate, value, attempt, window)
        proved = True
        require(accepted, "synthetic_send_unverified")
    except ProbeFailure as error:
        failure = error
    except Exception:
        failure = ProbeFailure("probe_outcome_unverified")
    finally:
        if route_possible and not route_closed:
            try:
                close_route()
                route_closed = True
            except Exception:
                failure = ProbeFailure("route_cleanup_unverified")
        if route_closed:
            try:
                if send_possible:
                    late = reconcile(value, attempt,
                                     (started, datetime.now(timezone.utc) + timedelta(minutes=10)),
                                     settle=True)
                    if proved and late:
                        failure = ProbeFailure("late_delivery_unverified")
                else:
                    require(one_key() is None, "private_object_cleanup_unverified")
            except Exception:
                failure = ProbeFailure("private_object_cleanup_unverified")
    if failure:
        raise failure
    require(proved, "object_capability_unverified")
    print("staging_worker_created_r2_get_delete_verified")


def recover() -> None:
    """Close A first; validate the prior failed run; remove only its own MIME."""

    value = run_id(os.environ.get("AMAIL_WORKER_R2_PRIOR_RUN_ID", ""))
    attempt = run_id(os.environ.get("AMAIL_WORKER_R2_PRIOR_RUN_ATTEMPT", ""))
    close_route()
    require(attempt == "1", "prior_run_attempt_invalid")
    window = prior_window(value, attempt)
    reconcile(value, attempt, window, settle=True)
    require(one_key() is None and route("audit") == "absent", "recovery_unverified")
    print("staging_worker_created_r2_recovered_absent")


def execute() -> None:
    """Dispatch exactly one guarded probe or route-first exact recovery."""

    mode = os.environ.get("AMAIL_WORKER_R2_MODE", "")
    require(mode in ("probe", "recover"), "mode_invalid")
    expected = ("RUN_STAGING_WORKER_R2_GET_DELETE" if mode == "probe"
                else "RECOVER_STAGING_WORKER_R2_GET_DELETE")
    require(os.environ.get("AMAIL_WORKER_R2_CONFIRM") == expected,
            "explicit_confirmation_required")
    require(re.fullmatch(r"[a-f0-9]{32}", os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""))
            is not None and bool(os.environ.get("CLOUDFLARE_API_TOKEN"))
            and bool(os.environ.get("CF_EMAIL_ROUTING_TOKEN"))
            and re.fullmatch(r"[a-f0-9]{32}", os.environ.get("CLOUDFLARE_ZONE_ID", ""))
            is not None, "provider_credentials_missing")
    if mode == "recover":
        recover()
    else:
        probe()


def main() -> int:
    """Emit only fixed labels, never provider, message or credential material."""

    try:
        execute()
        return 0
    except ProbeFailure as error:
        label = str(error)
        print("staging_worker_created_r2_failed:" +
              (label if re.fullmatch(r"[a-z][a-z0-9_]{2,100}", label)
               else "unexpected_failure"), file=sys.stderr)
    except Exception:
        print("staging_worker_created_r2_failed:unexpected_failure", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
