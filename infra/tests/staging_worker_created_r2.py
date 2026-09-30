"""One-shot hosted GET/DELETE proof using a private Email-Worker-created object.

The probe sends one synthetic, non-OTP message to the existing A test alias.
Recovery closes that exact route before inspecting the prior run's candidate.
Neither mode registers Identity B or calls R2 REST PUT. Both emit fixed labels.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from enum import Enum
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from staging_r2_object_capability import (API, MAX_REPLY, OPENER, ProbeFailure as R2ProbeFailure,
                                          audit, call, object_path)
from staging_second_principal import (ADDRESS, BUCKET, FIRST, KEY, ProvisionFailure,
                                      identity_contacts, json_result, object_inventory, request)


ROOT = Path(__file__).resolve().parents[2]
ROUTE_HELPER = ROOT / "workers" / "identity-test-inbox" / "ensure_route.py"
REPOSITORY = "kleedaisuki/moesegfault-amail"
BRANCH = "codex/amail-v0.1.0"
JOB_NAME = "One-shot Worker-created R2 GET/DELETE"
PROBE_STEP_NAME = "Probe Worker-created private R2 object"
SENDER = "mail@moesegfault.dev"
TEMPLATE = "amail private R2 capability v1 "
MAX_MIME = 8_192
MAX_GITHUB = 524_288


class ProbeFailure(Exception):
    """Carry only a fixed source-owned stage label to Actions output."""


class Submission(Enum):
    """Separate fixed provider-submission evidence from object observation."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    UNVERIFIED = "unverified"


@dataclass
class CleanupState:
    """Make a definite DELETE denial an irreversible read-only cleanup mode."""

    may_delete: bool = True
    # Cleanup can settle after an uncertain DELETE without proving its acceptance.
    delete_unverified: bool = False


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
    """Bound the reviewed exact-route scan without forwarding bearer on 30x."""

    require(action in ("apply", "audit", "remove"), "route_action_invalid")
    spec = importlib.util.spec_from_file_location("staging_worker_r2_route", ROUTE_HELPER)
    require(spec is not None and spec.loader is not None, "route_helper_unavailable")
    module = importlib.util.module_from_spec(spec)
    prior = urllib.request.urlopen
    deadline = time.monotonic() + 45
    previous_alarm = None

    def expire(_signum, _frame):
        """Interrupt even a trickling response after the total action budget."""

        raise TimeoutError()

    def bounded_open(req, timeout=20):
        """Cap all pages in one route action to a single 45-second budget."""

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError()
        return OPENER.open(req, timeout=min(timeout, remaining))

    try:
        urllib.request.urlopen = bounded_open
        if hasattr(signal, "setitimer"):
            previous_alarm = signal.signal(signal.SIGALRM, expire)
            signal.setitimer(signal.ITIMER_REAL, 45)
        spec.loader.exec_module(module)
        state = module.reconcile(os.environ["CLOUDFLARE_ZONE_ID"],
                                 os.environ["CF_EMAIL_ROUTING_TOKEN"], action, FIRST)
    except Exception:
        raise ProbeFailure("exact_route_control_failed") from None
    finally:
        if previous_alarm is not None:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_alarm)
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
            and run.get("path") in (
                ".github/workflows/staging-worker-r2-capability.yml",
                ".github/workflows/staging-worker-r2-capability.yml@refs/heads/" + BRANCH,
            )
            and start <= end <= now + timedelta(minutes=2)
            and now - start <= timedelta(hours=24), "prior_run_metadata_invalid")
    jobs = github_json(base + "/jobs?per_page=100", token)
    entries = jobs.get("jobs")
    require(type(jobs.get("total_count")) is int and jobs["total_count"] <= 100
            and isinstance(entries, list) and len(entries) == jobs["total_count"],
            "prior_run_job_invalid")
    matches = [job for job in entries if isinstance(job, dict)
               and job.get("name") == JOB_NAME]
    require(len(matches) == 1, "prior_run_job_invalid")
    job = matches[0]
    require(job.get("run_id") == int(value) and job.get("head_sha") == source_sha
            and job.get("status") == "completed"
            and job.get("conclusion") in ("failure", "cancelled", "timed_out")
            and start - timedelta(minutes=2) <= parse_time(job.get("started_at"))
            <= parse_time(job.get("completed_at")) <= end + timedelta(minutes=2),
            "prior_run_job_invalid")
    steps = job.get("steps")
    require(isinstance(steps, list), "prior_run_job_invalid")
    probe_steps = [step for step in steps if isinstance(step, dict)
                   and step.get("name") == PROBE_STEP_NAME]
    require(len(probe_steps) == 1 and probe_steps[0].get("status") == "completed"
            and probe_steps[0].get("conclusion") in ("success", "failure", "cancelled", "timed_out")
            and start - timedelta(minutes=2)
            <= parse_time(probe_steps[0].get("started_at")) <= end + timedelta(minutes=2),
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


def submission_result(status: int, raw: bytes) -> Submission:
    """Recognize exact recipient evidence; unknown errors remain uncertain.

    Only documented schema/auth/request rejection codes are definite rejection.
    Server errors and throttling never establish that no submission occurred.
    No provider strings are returned or emitted.
    """

    try:
        envelope = json.loads(raw)
    except (ValueError, UnicodeError):
        return Submission.UNVERIFIED
    if not isinstance(envelope, dict):
        return Submission.UNVERIFIED
    result = envelope.get("result")
    if status == 200 and envelope.get("success") is True and isinstance(result, dict):
        groups = [result.get(name, []) for name in
                  ("delivered", "queued", "permanent_bounces", "suppressed_recipients")]
        if not all(isinstance(group, list) and all(isinstance(item, str) for item in group)
                   for group in groups):
            return Submission.UNVERIFIED
        delivered, queued, bounced, suppressed = groups
        accepted = FIRST in delivered + queued
        rejected = FIRST in bounced + suppressed
        if accepted and not bounced and not suppressed:
            return Submission.ACCEPTED
        if rejected and not delivered and not queued:
            return Submission.REJECTED
        return Submission.UNVERIFIED
    errors = envelope.get("errors")
    rejection_codes = {400: {10001, 10200, 10201, 10202},
                       401: {10101, 10103}, 403: {10102, 10105, 10203}, 404: {10000}}
    if (envelope.get("success") is False and envelope.get("result") is None
            and isinstance(errors, list) and errors
            and all(isinstance(error, dict) and type(error.get("code")) is int
                    and error["code"] in rejection_codes.get(status, set())
                    for error in errors)):
        return Submission.REJECTED
    return Submission.UNVERIFIED


def send_request(account: str, token: str, payload: bytes) -> tuple[int, bytes]:
    """Read bounded send-only error envelopes privately, without redirect/retry.

    The shared R2 reader deliberately discards HTTP error bodies. Submission
    classification needs documented numeric rejection codes, so preserve bytes
    only in this synchronous call and never emit or persist them.
    """

    request = urllib.request.Request(
        API + f"/accounts/{account}/email/sending/send", data=payload, method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    try:
        try:
            response = OPENER.open(request, timeout=25)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read(MAX_REPLY + 1)
            if len(raw) > MAX_REPLY:
                raise R2ProbeFailure("send_response_unverified")
            return response.code, raw
    except (urllib.error.URLError, TimeoutError, OSError):
        raise R2ProbeFailure("send_outcome_unverified") from None


def send_once(account: str, token: str, value: str, attempt: str) -> Submission:
    """Submit once, retaining acceptance/rejection/uncertainty without retry."""

    nonce = marker(value, attempt)
    content = TEMPLATE + nonce
    payload = json.dumps({"to": FIRST, "from": SENDER, "subject": content,
                          "text": content}, separators=(",", ":")).encode()
    try:
        status, raw = send_request(account, token, payload)
        return submission_result(status, raw)
    except R2ProbeFailure:
        return Submission.UNVERIFIED


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
    """Prove a complete 0/1-key inventory with at most two requests."""

    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    token = os.environ["CLOUDFLARE_API_TOKEN"]
    base = f"/accounts/{account}/r2/buckets/{BUCKET}/objects"

    def info_valid(value: dict) -> bool:
        """Accept absent REST pagination metadata, not malformed present data."""

        if "result_info" not in value:
            return True
        info = value["result_info"]
        return (isinstance(info, dict) and
                ("is_truncated" not in info or type(info["is_truncated"]) is bool))

    try:
        first = json_result(request("GET", base + "?prefix=verification/&per_page=2", token))
        require(info_valid(first), "private_inventory_invalid")
        batch = first.get("result")
        require(isinstance(batch, list) and len(batch) <= 2,
                "private_inventory_invalid")
        require(len(batch) <= 1, "private_inventory_ambiguous")
        if not batch:
            info = first.get("result_info")
            require(not (isinstance(info, dict) and info.get("is_truncated") is True),
                    "private_inventory_invalid")
            return None
        require(isinstance(batch[0], dict) and isinstance(batch[0].get("key"), str)
                and KEY.fullmatch(batch[0]["key"]) is not None,
                "private_inventory_invalid")
        key = batch[0]["key"]
        query = "?prefix=verification/&per_page=2&start_after=" + urllib.parse.quote(key, safe="")
        second = json_result(request("GET", base + query, token))
        require(info_valid(second), "private_inventory_invalid")
        info = second.get("result_info")
        require(second.get("result") == [] and
                not (isinstance(info, dict) and info.get("is_truncated") is True),
                "private_inventory_ambiguous")
        return key
    except ProvisionFailure:
        raise ProbeFailure("private_inventory_unavailable") from None


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
                 window: tuple[datetime, datetime],
                 cleanup: CleanupState | None = None) -> None:
    """Delete only proven synthetic bytes, read back before uncertain retry."""

    from staging_r2_object_capability import delete

    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    token = os.environ["CLOUDFLARE_API_TOKEN"]
    cleanup = cleanup or CleanupState()
    require(cleanup.may_delete, "object_delete_denied")
    require(get_owned(key, value, attempt, window) == "present", "object_not_present")
    try:
        delete(account, key, token)
    except R2ProbeFailure as error:
        cleanup.delete_unverified = True
        if str(error) == "r2_delete_denied":
            cleanup.may_delete = False
            raise ProbeFailure("object_delete_denied") from None
        # A failed/ambiguous DELETE might already have taken effect. Never
        # issue another write until exact-key GET has proved the same bytes.
        state = get_owned(key, value, attempt, window)
        if state == "present":
            try:
                delete(account, key, token)
            except R2ProbeFailure as error:
                if str(error) == "r2_delete_denied":
                    cleanup.may_delete = False
                label = ("object_delete_denied" if not cleanup.may_delete
                         else "object_delete_unverified")
                raise ProbeFailure(label) from None
    require(get_owned(key, value, attempt, window) == "absent"
            and key not in object_inventory(account, token), "object_cleanup_unverified")


def reconcile(value: str, attempt: str, window: tuple[datetime, datetime],
              settle: bool, cleanup: CleanupState | None = None) -> bool:
    """After route closure, remove owned MIME unless DELETE was denied."""

    cleanup = cleanup or CleanupState()
    key = one_key()
    if key is None and settle:
        time.sleep(60)
        key = one_key()
    if key is None:
        return False
    if not cleanup.may_delete:
        require(get_owned(key, value, attempt, window) == "absent",
                "object_delete_denied_cleanup_unverified")
        if settle:
            time.sleep(60)
            require(one_key() is None, "late_delivery_unverified")
        return False
    delete_owned(key, value, attempt, window, cleanup)
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
    opened = time.monotonic()  # Include create/readback, not only settle/send.
    open_deadline = opened + 420
    route_possible = True  # Installed before an ambiguous route-create response.
    route_closed = False
    send_possible = False
    failure: ProbeFailure | None = None
    cleanup = CleanupState()
    proved = False
    submission = Submission.UNVERIFIED
    late_observed = False
    candidate = None
    try:
        require(route("apply") == "created" and route("audit") == "enabled",
                "route_create_unverified")
        time.sleep(60)
        require(route("audit") == "enabled", "route_settle_unverified")
        require(time.monotonic() + 70 < open_deadline, "route_window_expired")
        send_possible = True
        submission = send_once(account, token, value, attempt)
        deadline = min(open_deadline - 90, time.monotonic() + 150)
        candidate = None
        while candidate is None and time.monotonic() + 50 < deadline:
            candidate = one_key()
            if candidate is None:
                time.sleep(5)
        close_route()
        route_closed = True
        require(candidate is not None, "synthetic_delivery_missing")
        window = (started, datetime.now(timezone.utc) + timedelta(minutes=2))
        delete_owned(candidate, value, attempt, window, cleanup)
        proved = True
        require(submission is Submission.ACCEPTED,
                "synthetic_send_rejected" if submission is Submission.REJECTED
                else "synthetic_send_unverified")
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
                                     settle=True, cleanup=cleanup)
                    late_observed = late
                    if proved and late:
                        failure = ProbeFailure("late_delivery_unverified")
                else:
                    require(one_key() is None, "private_object_cleanup_unverified")
            except Exception:
                label = ("object_delete_denied_cleanup_unverified"
                         if not cleanup.may_delete
                         else "private_object_cleanup_unverified")
                failure = ProbeFailure(label)
    if send_possible:
        print("synthetic_submission=" + submission.value +
              " object_candidate=" + ("observed" if candidate is not None or late_observed else "not_observed"))
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
    cleanup = CleanupState()
    observed = reconcile(value, attempt, window, settle=True, cleanup=cleanup)
    require(one_key() is None and route("audit") == "absent", "recovery_unverified")
    require(not cleanup.delete_unverified, "object_delete_unverified")
    print("staging_worker_created_r2_recovered_absent")
    print("existing_object_get_delete=" + ("verified" if observed else "not_observed"))


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
