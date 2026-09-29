"""Bounded, opt-in hosted staging address and two-owner acceptance probe.

Supply two independently verified native-login homes, a CI-built CLI, and a
run-private nonce. This module never provisions Identity accounts or secrets.
It consumes up to ten temporary literal routes; do not invoke on push.
"""

from __future__ import annotations

from email.message import EmailMessage
import os
from pathlib import Path
import re
import smtplib
import ssl
import subprocess
import sys
import time

import staging_mail_e2e as mail


# The deployed Worker list at crates/mail-worker/src/lib.rs. Keep this oracle
# explicit: a narrower sample must not be called full reserved-name coverage.
RESERVED = (
    "admin", "administrator", "amail", "moesegfault", "mail", "login",
    "identity", "account", "api", "auth", "support", "security",
    "postmaster", "abuse", "noreply", "no-reply", "billing", "status",
    "cdn", "www", "root", "hostmaster", "webmaster", "help", "contact",
)


class IsolationFailure(Exception):
    """A source-owned, nonsensitive diagnostic label."""


def safe_error(error: Exception) -> str:
    """Retain only static harness-owned labels, never provider exception text."""

    if not isinstance(error, (IsolationFailure, mail.ProbeFailure)):
        return "unexpected_failure"
    label = str(error)
    return label if re.fullmatch(r"[a-z][a-z0-9_]{2,80}", label) else "unexpected_failure"


def require(ok: bool, label: str) -> None:
    """Fail closed without interpolating private input or provider output."""

    if not ok:
        raise IsolationFailure(label)


def cli_error(binary: Path, env: dict[str, str], code: str, *args: str) -> None:
    """Check the native CLI's stable HTTP code, never echoing its stderr."""

    try:
        result = subprocess.run([str(binary), *args], env=env, capture_output=True,
                                timeout=90, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise IsolationFailure("negative_cli_unavailable") from None
    require(len(result.stderr) < 65_536, "negative_cli_output_oversized")
    require(result.returncode != 0 and re.search(
        rb"(?:^|[, ])code=" + code.encode("ascii") + rb"(?:[,\s]|$)", result.stderr
    ) is not None, "negative_cli_code_mismatch")


def owned(binary: Path, env: dict[str, str]) -> set[str]:
    """Read only live addresses owned by this authenticated principal."""

    values = mail.amail(binary, env, "address", "list", failure="address_list_failed")
    return {row["address"] for row in values if isinstance(row.get("address"), str)}


def active(binary: Path, env: dict[str, str], address: str) -> None:
    """Wait for active API state before independently auditing the exact route."""

    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        values = mail.amail(binary, env, "address", "list", failure="address_readback_failed")
        if any(row.get("address") == address and row.get("state") == "active" for row in values):
            return
        time.sleep(3)
    raise IsolationFailure("address_activation_timeout")


def rejected_smtp(token: str, address: str, nonce: str) -> None:
    """Require permanent RCPT refusal; acceptance or transient 4xx is not proof."""

    msg = EmailMessage()
    msg["From"] = mail.SENDER
    msg["To"] = address
    msg["Subject"] = f"AMAIL-RETIRED-{nonce}"
    msg.set_content("Synthetic retired-alias probe.")
    try:
        with smtplib.SMTP_SSL("smtp.mx.cloudflare.net", 465, timeout=30,
                              context=ssl.create_default_context()) as smtp:
            smtp.login("api_token", token)
            refused = smtp.sendmail(mail.SENDER, [address], msg.as_bytes())
        refusal = refused.get(address)
        require(refusal is not None, "retired_smtp_accepted_inconclusive")
        require_permanent_refusal(refusal)
    except smtplib.SMTPRecipientsRefused as error:
        refusal = error.recipients.get(address)
        require(refusal is not None, "retired_smtp_rejection_unattributed")
        require_permanent_refusal(refusal)
    except IsolationFailure:
        raise
    except (OSError, smtplib.SMTPException):
        raise IsolationFailure("retired_smtp_transport_failure") from None


def require_permanent_refusal(refusal: object) -> None:
    """Classify only a 5xx recipient response as permanent rejection."""

    require(isinstance(refusal, tuple) and len(refusal) == 2,
            "retired_smtp_refusal_unclassified")
    code = refusal[0]
    require(type(code) is int and 500 <= code <= 599,
            "retired_smtp_transient_or_unknown_refusal")


def route_snapshot(zone: str, token: str, addresses: set[str]) -> dict[str, list[dict]]:
    """Capture exact candidate rules before mutations, including operator routes."""

    rules = mail.cf_rules(zone, token)
    return {address: mail.route_for(rules, address) for address in addresses}


def reconcile_candidates(binary: Path, env_a: dict[str, str], env_b: dict[str, str],
                         zone: str, token: str, attempted: dict[str, set[str]],
                         baseline: dict[str, list[dict]]) -> None:
    """Retire only newly owned candidates; preserve preexisting operator rules.

    A candidate is tracked *before* every mutating request, including negative
    probes and the post-retirement re-add. Preexisting-route candidates are
    never automatically deleted because that could remove an operator route.
    Any unexpected ownership or route change there requires manual review.
    """

    for address, owners in attempted.items():
        if baseline[address]:
            continue
        for owner, env in (("b", env_b), ("a", env_a)):
            if owner not in owners:
                continue
            try:
                if address in owned(binary, env):
                    mail.amail(binary, env, "address", "delete", address,
                               failure="candidate_retire_failed")
            except Exception:
                # An uncertain request or eventual list can fail. The final
                # owner/provider readback below decides reconciliation.
                pass
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            current_a, current_b = owned(binary, env_a), owned(binary, env_b)
            current_rules = route_snapshot(zone, token, set(attempted))
            if all(address not in current_a and address not in current_b
                   and current_rules[address] == baseline[address]
                   for address in attempted):
                return
        except Exception:
            pass
        time.sleep(3)
    raise IsolationFailure("candidate_reconciliation_required")


def execute(binary: Path, home_a: Path, home_b: Path, nonce: str,
            zone: str, route_token: str, smtp_token: str) -> None:
    """Check quota, reserved/collision names, isolation, and exact retirement."""

    require(os.environ.get("AMAIL_ADDRESS_E2E_CONFIRM") == "RUN_STAGING_ADDRESS_E2E",
            "explicit_confirmation_required")
    require(re.fullmatch(r"[a-f0-9]{16}", nonce) is not None, "nonce_invalid")
    require(re.fullmatch(r"[a-f0-9]{32}", zone) is not None, "zone_invalid")
    require(bool(route_token and smtp_token), "provider_credentials_missing")
    binary, home_a, home_b = (mail.inside_temp(str(path)) for path in (binary, home_a, home_b))
    require(binary.is_file() and home_a.is_dir() and home_b.is_dir() and home_a != home_b,
            "principal_homes_invalid")
    a, b = mail.cli_env(home_a), mail.cli_env(home_b)
    for env in (a, b):
        status = mail.amail(binary, env, "auth", "status", failure="auth_status_failed")
        require(len(status) == 1 and status[0].get("authenticated") is True,
                "principal_not_authenticated")
    # Distinct homes alone do not prove distinct subjects: B must be unable to
    # see an address A owns, and the operator must attest separate principals.
    require(not owned(binary, a) and not owned(binary, b), "principal_not_empty")
    mail.assert_staging_sender(zone, smtp_token)
    parts = [f"q{index}-{nonce}" for index in range(10)]
    addresses = [f"{part}@{mail.DOMAIN}" for part in parts]
    reserved_addresses = {f"{part}@{mail.DOMAIN}" for part in RESERVED}
    candidates = set(addresses) | reserved_addresses | {f"q10-{nonce}@{mail.DOMAIN}"}
    baseline = route_snapshot(zone, route_token, candidates)
    require(all(not baseline[address] for address in addresses), "candidate_route_preexists")
    require(not baseline[f"q10-{nonce}@{mail.DOMAIN}"], "quota_candidate_route_preexists")
    attempted: dict[str, set[str]] = {}

    def track(address: str, owner: str) -> None:
        """Record intent before invoking any mutating CLI request."""

        attempted.setdefault(address, set()).add(owner)

    primary: Exception | None = None
    cleanup: Exception | None = None
    message_id: str | None = None
    foreign_path = home_b / f"foreign-{nonce}.zip"
    require(not foreign_path.exists(), "foreign_probe_output_preexists")
    try:
        for reserved in RESERVED:
            track(f"{reserved}@{mail.DOMAIN}", "a")
            cli_error(binary, a, "reserved_or_invalid_name", "address", "add", reserved)
        require(not owned(binary, a), "reserved_name_created")
        for part, address in zip(parts, addresses):
            track(address, "a")
            row = mail.amail(binary, a, "address", "add", part,
                             failure="address_add_failed")
            require(len(row) == 1 and row[0].get("address") == address,
                    "address_add_mismatch")
            active(binary, a, address)
            mail.assert_route(zone, route_token, address, True)
        require(owned(binary, a) == set(addresses), "ten_address_readback_mismatch")
        require(not owned(binary, b), "cross_principal_address_visible")
        track(addresses[0], "a")
        retry = mail.amail(binary, a, "address", "add", parts[0],
                           failure="address_retry_failed")
        require(len(retry) == 1 and retry[0].get("address") == addresses[0],
                "idempotent_add_mismatch")
        mail.assert_route(zone, route_token, addresses[0], True)
        track(f"q10-{nonce}@{mail.DOMAIN}", "a")
        cli_error(binary, a, "address_limit", "address", "add", f"q10-{nonce}")
        track(addresses[0], "b")
        cli_error(binary, b, "address_unavailable", "address", "add", parts[0])
        track(addresses[0], "b")
        cli_error(binary, b, "not_found", "address", "delete", addresses[0])
        require(not owned(binary, b), "cross_principal_address_mutated")
        mail.assert_route(zone, route_token, addresses[0], True)

        # One real delivery is enough for B's read/mutation/ZIP isolation; the
        # existing inbound harness owns deep MIME and semantic coverage.
        time.sleep(60)
        mail.assert_route(zone, route_token, addresses[0], True)
        msg = EmailMessage()
        msg["From"] = mail.SENDER
        msg["To"] = addresses[0]
        msg["Subject"] = f"AMAIL-ISOLATION-{nonce}"
        msg.set_content("Synthetic principal isolation check.")
        mail.smtp_send(smtp_token, addresses[0], [msg])
        found = mail.await_messages(binary, a, {msg["Subject"]})
        message_id = found[msg["Subject"]].get("id")
        require(isinstance(message_id, str) and bool(message_id), "message_id_missing")
        require(not [row for row in mail.rows(mail.amail(binary, b, "sync", "--limit", "100",
                    failure="b_sync_failed")) if row.get("subject") == msg["Subject"]],
                "cross_principal_message_visible")
        cli_error(binary, b, "not_found", "get", message_id)
        cli_error(binary, b, "not_found", "read", message_id, "-o", str(foreign_path))
        cli_error(binary, b, "not_found", "mark", message_id, "--read")
        cli_error(binary, b, "not_found", "delete", message_id)
        detail = mail.amail(binary, a, "get", message_id, failure="owner_message_lost")
        require(len(detail) == 1 and detail[0].get("read") is False,
                "foreign_mutation_changed_owner_state")
        require(not [row for row in mail.rows(mail.amail(binary, b, "search", "--title",
                    msg["Subject"], failure="b_search_failed"))
                    if row.get("subject") == msg["Subject"]], "cross_principal_search_visible")
        print("address_quota_reserved_routing_and_isolation_verified")
        mail.amail(binary, a, "delete", message_id, failure="message_delete_failed")
        message_id = None
        mail.amail(binary, a, "address", "delete", addresses[0],
                   failure="first_address_retire_failed")
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if addresses[0] not in owned(binary, a) and not mail.route_for(
                    mail.cf_rules(zone, route_token), addresses[0]):
                break
            time.sleep(3)
        else:
            raise IsolationFailure("first_address_retirement_timeout")
        track(addresses[0], "a")
        cli_error(binary, a, "address_retired", "address", "add", parts[0])
        rejected_smtp(smtp_token, addresses[0], nonce)
        print("retired_alias_and_smtp_rejection_verified")
    except Exception as error:
        primary = error
    finally:
        try:
            foreign_path.unlink(missing_ok=True)
        except OSError as error:
            cleanup = error
        if message_id:
            try:
                mail.amail(binary, a, "delete", message_id, failure="message_cleanup_failed")
            except Exception as error:
                cleanup = error
        try:
            reconcile_candidates(binary, a, b, zone, route_token, attempted, baseline)
        except Exception as error:
            cleanup = cleanup or error
    if primary or cleanup:
        label = safe_error(primary) if primary else "probe_passed"
        if cleanup:
            label += "_cleanup_" + safe_error(cleanup)
        raise IsolationFailure(label)


def main() -> int:
    """Provide a fixed-label CLI wrapper; raw exceptions never reach Actions logs."""

    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--amail", required=True)
    parser.add_argument("--home-a", required=True)
    parser.add_argument("--home-b", required=True)
    parser.add_argument("--nonce", required=True)
    args = parser.parse_args()
    try:
        execute(Path(args.amail), Path(args.home_a), Path(args.home_b), args.nonce,
                os.environ.get("CLOUDFLARE_ZONE_ID", ""),
                os.environ.get("CF_EMAIL_ROUTING_TOKEN", ""),
                os.environ.get("AMAIL_TEST_SMTP_TOKEN", ""))
    except IsolationFailure as error:
        print(f"staging_address_isolation_failed:{error}", file=sys.stderr)
        return 1
    except Exception:
        print("staging_address_isolation_failed:unexpected_failure", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
