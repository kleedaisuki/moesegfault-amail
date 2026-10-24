"""Real staging native-profile, distributed ownership and temporary-mail journey.

Called only by the confirmed hosted staging harness after native browser login.
All CLI output, SMTP receipts and mailbox exports remain private in its run home.
"""

from __future__ import annotations

from collections.abc import Callable
from email.message import EmailMessage
import io
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any
import uuid
import zipfile

import staging_mail_e2e as mail

TMP_DOMAIN: str = "tmpaddr-staging.moesegfault.dev"
ANCHOR: str = "v030-probe-anchor"


class ProfileProbeError(mail.ProbeFailure):
    """Fixed nonsensitive failure label for the enclosing hosted harness."""


def check(condition: bool, label: str) -> None:
    if not condition:
        raise ProfileProbeError(label)


def command(binary: Path, env: dict[str, str], *args: str) -> list[dict[str, Any]]:
    return mail.amail(binary, env, *args, failure="profiles_cli_failed")


def one(binary: Path, env: dict[str, str], *args: str) -> dict[str, Any]:
    values: list[dict[str, Any]] = command(binary, env, *args)
    check(len(values) == 1, "profiles_response_shape")
    return values[0]


def rejected(binary: Path, env: dict[str, str], args: list[str], expected: str) -> None:
    try:
        result: subprocess.CompletedProcess[bytes] = subprocess.run(
            [str(binary), "--machine", *args], env=env, capture_output=True,
            timeout=90, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ProfileProbeError("profiles_rejection_process_failed") from None
    check(result.returncode != 0 and not result.stdout, "profiles_forbidden_operation_succeeded")
    check(len(result.stderr) <= 65_536, "profiles_rejection_output_oversized")
    try:
        records: list[Any] = [json.loads(line) for line in result.stderr.splitlines() if line.strip()]
    except (ValueError, UnicodeDecodeError):
        raise ProfileProbeError("profiles_rejection_output_invalid") from None
    errors: list[dict[str, Any]] = [record for record in records if isinstance(record, dict)
        and record.get("schema") == "amail.machine.v1" and record.get("event") == "error"]
    check(len(errors) == 1 and isinstance(errors[0].get("data"), dict)
          and errors[0]["data"].get("code") == expected, "profiles_rejection_code_mismatch")


def acquire(binary: Path, env: dict[str, str], address: str, mode: str) -> None:
    value: dict[str, Any] = one(binary, env, "mailbox", "acquire", address, "--mode", mode)
    check(value.get("address") == address and value.get("mode") == mode,
          "profiles_lease_response_mismatch")
    check("lease_token" not in value and "session_token" not in value,
          "profiles_private_capability_in_stdout")


def verify_export(path: Path, address: str, generation: str, message_id: str, phrase: str) -> None:
    try:
        with zipfile.ZipFile(path) as bundle:
            manifest: Any = json.loads(bundle.read("manifest.json"))
            check(isinstance(manifest, dict) and manifest.get("schema") == "amail.mailbox-export.v1"
                  and manifest.get("message_count") == 1, "profiles_export_manifest_invalid")
            snapshot: Any = manifest.get("mailbox")
            check(isinstance(snapshot, dict) and snapshot.get("address") == address
                  and snapshot.get("kind") == "tmpaddr" and snapshot.get("generation") == generation,
                  "profiles_export_generation_mismatch")
            check(set(bundle.namelist()) == {"manifest.json", f"messages/{message_id}.json",
                  f"messages/{message_id}.zip"}, "profiles_export_file_set_mismatch")
            with zipfile.ZipFile(io.BytesIO(bundle.read(f"messages/{message_id}.zip"))) as message:
                body: str = message.read("body.txt").decode("utf-8")
                check(phrase in body, "profiles_export_body_mismatch")
    except (OSError, KeyError, ValueError, UnicodeDecodeError, zipfile.BadZipFile):
        raise ProfileProbeError("profiles_export_archive_invalid") from None


def active_temporary(binary: Path, env: dict[str, str], address: str) -> dict[str, Any]:
    deadline: float = time.monotonic() + 90
    while time.monotonic() < deadline:
        rows: list[dict[str, Any]] = command(binary, env, "address", "list")
        matches: list[dict[str, Any]] = [row for row in rows if row.get("address") == address]
        check(len(matches) <= 1, "profiles_duplicate_temporary_address")
        if matches and matches[0].get("state") == "active":
            return matches[0]
        time.sleep(3)
    raise ProfileProbeError("profiles_temporary_activation_timeout")


def execute(binary: Path, home: Path, run_dir: Path, nonce: str) -> dict[str, bool | int | str]:
    check(os.environ.get("AMAIL_STAGING_E2E_CONFIRM") == "RUN_STAGING_E2E"
          and os.environ.get("GITHUB_REF") == "refs/heads/codex/v0.3.0-multitenant",
          "profiles_staging_confirmation_required")
    check(re.fullmatch(r"[a-f0-9]{16}", nonce) is not None, "profiles_nonce_invalid")
    check(mail.TEMP in run_dir.resolve().parents and home.resolve().parent == run_dir.resolve()
          and binary.resolve().parent == run_dir.resolve(), "profiles_private_path_invalid")
    env_a: dict[str, str] = mail.cli_env(home)
    env_b: dict[str, str] = dict(env_a, AMAIL_TERMINAL_ID=str(uuid.uuid5(
        uuid.NAMESPACE_URL, str(home.resolve()) + "/v030-terminal-b")))
    smtp_token: str = os.environ.get("AMAIL_TEST_SMTP_TOKEN", "")
    route_token: str = os.environ.get("CF_EMAIL_ROUTING_TOKEN", "")
    zone: str = os.environ.get("CLOUDFLARE_ZONE_ID", "")
    check(bool(smtp_token and route_token and zone), "profiles_staging_capability_missing")
    profile_a: str = "v030-a-" + nonce
    profile_b: str = "v030-b-" + nonce
    address: str = "v030-" + nonce + "@" + TMP_DOMAIN
    anchor_owned: bool = False
    created_a: bool = False
    created_b: bool = False
    creation_attempted: bool = False
    retired: bool = False
    activated_a: bool = False
    activated_b: bool = False
    primary: mail.ProbeFailure | None = None
    cleanup: mail.ProbeFailure | None = None
    evidence: dict[str, bool | int | str] = {"schema": "amail-staging-profiles/v1"}
    try:
        user: Any = one(binary, env_a, "profile", "status").get("profile")
        check(isinstance(user, dict) and user.get("name") == "user", "profiles_initial_user_required")
        listed: Any = one(binary, env_a, "profile", "list").get("profiles")
        check(isinstance(listed, list), "profiles_list_shape")
        anchors: list[dict[str, Any]] = [row for row in listed if isinstance(row, dict)
            and row.get("name") == ANCHOR]
        check(len(anchors) <= 1, "profiles_anchor_ambiguous")
        if not anchors:
            anchor: Any = one(binary, env_a, "profile", "create", ANCHOR).get("profile")
            check(isinstance(anchor, dict) and anchor.get("durable") is True,
                  "profiles_anchor_not_durable")
        else:
            check(anchors[0].get("durable") is True, "profiles_anchor_not_durable")
        one(binary, env_a, "profile", "deactivate")
        one(binary, env_a, "profile", "activate", ANCHOR)
        anchor_owned = True
        check(not any(isinstance(row, dict) and row.get("name") in (profile_a, profile_b)
                      for row in listed), "profiles_run_name_already_exists")
        for name in (profile_a, profile_b):
            row: Any = one(binary, env_a, "profile", "create", name).get("profile")
            if name == profile_a:
                created_a = True
            else:
                created_b = True
            check(isinstance(row, dict) and row.get("durable") is False,
                  "profiles_child_not_ephemeral")
        one(binary, env_a, "profile", "deactivate")
        one(binary, env_a, "profile", "activate", profile_a)
        activated_a = True
        one(binary, env_b, "profile", "activate", profile_b)
        activated_b = True
        evidence["ephemeral_profiles"] = 2
        print("staging_profiles_ephemeral_terminals_verified")

        rejected(binary, env_b, ["address", "add", "v030-permanent-" + nonce], "user_profile_required")
        creation_attempted = True
        added: dict[str, Any] = one(binary, env_a, "address", "add", "v030-" + nonce, "--tmp")
        check(added.get("address") == address and added.get("state") in ("active", "pending"),
              "profiles_temporary_registration_mismatch")
        temporary: dict[str, Any] = active_temporary(binary, env_a, address)
        generation: Any = temporary.get("generation")
        expires: Any = temporary.get("expires_at")
        check(temporary.get("kind") == "tmpaddr" and isinstance(generation, str)
              and re.fullmatch(r"[a-f0-9-]{36}", generation) is not None,
              "profiles_temporary_generation_missing")
        check(type(expires) is int and 0 < expires - int(time.time() * 1000) <= 21_600_000,
              "profiles_temporary_lifetime_invalid")
        mail.assert_route(zone, route_token, address, True)
        rejected(binary, env_b, ["mailbox", "acquire", address, "--mode", "read"], "mailbox_in_use")
        # Registration's automatic writer is releasable without a manual acquire.
        one(binary, env_a, "mailbox", "release", address)
        acquire(binary, env_a, address, "read")
        acquire(binary, env_b, address, "read")
        rejected(binary, env_a, ["mailbox", "acquire", address, "--mode", "write"], "mailbox_in_use")
        one(binary, env_b, "mailbox", "release", address)
        acquire(binary, env_a, address, "write")
        evidence["distributed_read_write_ownership"] = True
        evidence["agent_permanent_registration_denied"] = True
        evidence["temporary_lifetime_bounded"] = True
        print("staging_profiles_distributed_ownership_verified")

        # Match the existing real SMTP journey's routing propagation allowance.
        time.sleep(60)
        mail.assert_route(zone, route_token, address, True)
        message: EmailMessage
        oracle: dict[str, Any]
        message, oracle = mail.make_mail(address, nonce + "-profiles", False)
        mail.smtp_send_receipts(smtp_token, address, [(message, oracle)])
        found: dict[str, dict[str, Any]] = mail.await_messages(binary, env_a, {oracle["subject"]})
        message_id: Any = found[oracle["subject"]].get("id")
        check(isinstance(message_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", message_id)
              is not None, "profiles_message_id_invalid")
        detail: dict[str, Any] = one(binary, env_a, "get", message_id)
        mail.verify_fixture(detail, oracle, address, message_id)
        archive: Path = run_dir / ("profiles-export-" + nonce + ".zip")
        exported: dict[str, Any] = one(binary, env_a, "mailbox", "export", address, "-o", str(archive))
        check(exported.get("exported") is True and exported.get("messages") == 1,
              "profiles_export_failed")
        verify_export(archive, address, generation, message_id, oracle["phrase"])
        evidence["smtp_fixture_count"] = 1
        evidence["live_history_export"] = True
        print("staging_profiles_smtp_export_verified")

        one(binary, env_a, "address", "delete", address)
        retired = True
        check(not any(row.get("address") == address for row in command(binary, env_a, "address", "list")),
              "profiles_released_address_visible")
        check(not mail.rows(command(binary, env_a, "search", "--mailbox", address,
                                    "--title", oracle["subject"])), "profiles_released_search_visible")
        mail.amail_not_found(binary, env_a, "get", message_id)
        missing: Path = run_dir / ("profiles-released-" + nonce + ".zip")
        mail.amail_not_found(binary, env_a, "read", message_id, "-o", str(missing))
        check(not missing.exists(), "profiles_released_archive_created")
        mail.assert_route(zone, route_token, address, False)
        evidence["release_hides_history"] = True
        print("staging_profiles_release_visibility_verified")
    except Exception as error:
        primary = error if isinstance(error, mail.ProbeFailure) else ProfileProbeError("profiles_unexpected_failure")
    finally:
        def attempt(action: Callable[[], object]) -> None:
            nonlocal cleanup
            try:
                action()
            except Exception as error:
                if cleanup is None:
                    cleanup = error if isinstance(error, mail.ProbeFailure) else ProfileProbeError(
                        "profiles_cleanup_unexpected_failure")

        def release_child(env: dict[str, str], name: str, activated: bool) -> None:
            if not activated:
                if env is env_a:
                    one(binary, env, "profile", "deactivate")
                one(binary, env, "profile", "activate", name)
            one(binary, env, "profile", "release", name)

        def retire_owned_address() -> None:
            if not creation_attempted or retired:
                return
            rows: list[dict[str, Any]] = command(binary, env_a, "address", "list")
            own: list[dict[str, Any]] = [row for row in rows if row.get("address") == address]
            if own:
                check(len(own) == 1, "profiles_cleanup_address_ambiguous")
                active_temporary(binary, env_a, address)
                acquire(binary, env_a, address, "write")
                one(binary, env_a, "address", "delete", address)
                mail.assert_route(zone, route_token, address, False)

        def restore_user() -> None:
            current: Any = one(binary, env_a, "profile", "status").get("profile")
            if isinstance(current, dict) and current.get("name") != "user":
                one(binary, env_a, "profile", "deactivate")
            one(binary, env_a, "profile", "activate", "user")

        # Release the other reader first so cleanup never needs to preempt it.
        if created_b:
            attempt(lambda: release_child(env_b, profile_b, activated_b))
        attempt(retire_owned_address)
        if created_a:
            attempt(lambda: release_child(env_a, profile_a, activated_a))
        if anchor_owned:
            attempt(lambda: one(binary, env_a, "profile", "release", ANCHOR))
        attempt(restore_user)
    failure: mail.ProbeFailure | None = mail.acceptance_failure(primary, cleanup)
    if failure:
        raise failure
    evidence["ephemeral_profiles_released"] = True
    evidence["user_restored"] = True
    return evidence
