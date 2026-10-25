"""One protected synthetic-mail semantic-consent journey, not the legacy suite.

Native login and one temporary receive route are setup. The accepted candidate
binary is restored by Actions; this harness neither rebuilds nor deploys it.
"""

from __future__ import annotations

from collections.abc import Callable
from email.message import EmailMessage
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

import staging_hosted_e2e as hosted
import staging_mail_e2e as mail


BRANCH: str = "refs/heads/codex/v0.3.1-semantic-consent"
CONFIRMATION: str = "RUN_STAGING_SEMANTIC_V031"
TMP_DOMAIN: str = "tmpaddr-staging.moesegfault.dev"
POLICY: str = "voyage4_no_training_retention_v1"
EVIDENCE: Path = mail.TEMP / "staging-semantic-evidence.json"
RUNTIME: Path = mail.TEMP / "staging-semantic-runtime.json"
ACCEPTANCE: Path = mail.TEMP / "staging-semantic-acceptance.json"
SOURCE_RUN: str = "40188956353"
SOURCE_SHA: str = "f262e8e433ffeabb7d67d0fc26c363be7e4133f8"
API_VERSION: str = "d592cd2a-95a3-4c89-859a-18a191bd641a"
SINK_VERSION: str = "5e556087-9a75-40db-9eb5-869a4b56372e"
UUID: re.Pattern[str] = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")


def acceptance_receipt(runtime: object, *, run_id: str, checkout_sha: str) -> dict[str, str]:
    """Bind cleaned acceptance to the original producer and preflight's exact pins."""
    expected: dict[str, str] = {"schema": "staging-semantic-acceptance/v1",
        "source_run_id": SOURCE_RUN, "source_sha": SOURCE_SHA,
        "run_id": run_id, "checkout_sha": checkout_sha,
        "api_version": API_VERSION, "sink_version": SINK_VERSION}
    mail.check(re.fullmatch(r"[1-9][0-9]{0,19}", run_id) is not None
               and re.fullmatch(r"[0-9a-f]{40}", checkout_sha) is not None,
               "semantic_acceptance_identity_invalid")
    mail.check(isinstance(runtime, dict) and set(runtime) == set(expected) | {"maintenance_version"}
               and all(isinstance(value, str) for value in runtime.values())
               and all(runtime.get(key) == value for key, value in expected.items())
               and UUID.fullmatch(runtime["maintenance_version"]) is not None,
               "semantic_acceptance_runtime_unverified")
    return {**expected, "maintenance_version": runtime["maintenance_version"]}


def read_runtime() -> dict[str, str]:
    mail.check(not RUNTIME.is_symlink() and RUNTIME.is_file() and RUNTIME.stat().st_size <= 16_384
               and not ACCEPTANCE.exists() and not ACCEPTANCE.is_symlink(),
               "semantic_acceptance_runtime_file_invalid")
    try:
        value: object = json.loads(RUNTIME.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise mail.ProbeFailure("semantic_acceptance_runtime_file_invalid") from None
    return acceptance_receipt(value, run_id=os.environ.get("GITHUB_RUN_ID", ""),
                              checkout_sha=os.environ.get("GITHUB_SHA", ""))


def one(binary: Path, environment: dict[str, str], *args: str) -> dict[str, Any]:
    """Consume one CLI result without copying private output into diagnostics."""
    values: list[dict[str, Any]] = mail.amail(binary, environment, *args,
                                            failure="semantic_cli_failed")
    mail.check(len(values) == 1, "semantic_cli_shape_invalid")
    return values[0]


def status(binary: Path, environment: dict[str, str], action: str = "status") -> dict[str, Any]:
    value: dict[str, Any] = one(binary, environment, "semantic", action)
    mail.check(type(value.get("enabled")) is bool and type(value.get("generation")) is int
               and type(value.get("pending_messages")) is int
               and type(value.get("indexed_messages")) is int
               and value.get("model") == "voyageai/voyage-4"
               and value.get("dimensions") == 256 and value.get("policy_id") == POLICY,
               "semantic_status_contract_invalid")
    return value


def await_index(binary: Path, environment: dict[str, str], generation: int) -> None:
    """Poll local/server status only; never spend provider calls on readiness."""
    deadline: float = time.monotonic() + 420
    while time.monotonic() < deadline:
        current: dict[str, Any] = status(binary, environment)
        mail.check(current["enabled"] and current["generation"] == generation,
                   "semantic_generation_changed_during_index")
        if current["pending_messages"] == 0:
            mail.check(current["indexed_messages"] >= 1, "semantic_backfill_empty")
            return
        time.sleep(5)
    raise mail.ProbeFailure("semantic_background_backfill_timeout")


def search_once(binary: Path, environment: dict[str, str], *args: str) -> list[dict[str, Any]]:
    """Issue one search intent, never retry a provider-bound query for readiness."""
    try:
        result: subprocess.CompletedProcess[bytes] = subprocess.run(
            [str(binary), "search", *args], env=environment, capture_output=True,
            timeout=90, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise mail.ProbeFailure("semantic_search_process_failed") from None
    mail.check(result.returncode == 0, mail.cli_failure(result.stderr, "semantic_search_failed"))
    mail.check(len(result.stdout) <= 2_000_000, "semantic_search_output_oversized")
    try:
        rows: list[Any] = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    except (ValueError, UnicodeDecodeError):
        raise mail.ProbeFailure("semantic_search_output_invalid") from None
    mail.check(all(isinstance(row, dict) for row in rows), "semantic_search_output_invalid")
    return mail.rows(rows)


def await_address(binary: Path, environment: dict[str, str], address: str) -> None:
    deadline: float = time.monotonic() + 90
    while time.monotonic() < deadline:
        owned: list[dict[str, Any]] = mail.amail(binary, environment, "address", "list",
                                               failure="semantic_fixture_address_list_failed")
        if any(row.get("address") == address and row.get("state") == "active" for row in owned):
            return
        time.sleep(3)
    raise mail.ProbeFailure("semantic_fixture_address_timeout")


def execute() -> None:
    import staging_identity_cdp as identity

    mail.check(os.environ.get("GITHUB_REF") == BRANCH
               and os.environ.get("AMAIL_STAGING_SEMANTIC_CONFIRM") == CONFIRMATION
               and os.environ.get("AMAIL_SOURCE_RUN") == SOURCE_RUN,
               "semantic_staging_confirmation_required")
    runtime: dict[str, str] = read_runtime()
    username: str
    password: str
    username, password = hosted.validate_environment()
    nonce: str = hosted.recoverable_run_nonce(password)
    mail.TEMP.mkdir(exist_ok=True)
    run_dir: Path = Path(tempfile.mkdtemp(prefix="staging-hosted-e2e-semantic-", dir=mail.TEMP)).resolve()
    mail.check(mail.TEMP in run_dir.parents and not run_dir.is_symlink(), "semantic_private_path_invalid")
    binary: Path = run_dir / "amail.exe"
    environment: dict[str, str] | None = None
    address: str = "semantic-" + nonce + "@" + TMP_DOMAIN
    creation_attempted: bool = False
    semantic_cleanup_required: bool = False
    message_id: str | None = None
    primary: Exception | None = None
    cleanup: Exception | None = None
    try:
        shutil.copy2(hosted.selected_binary(), binary)
        identity.store_credential(run_dir, username, password)
        identity.native_login(run_dir, binary)
        del username, password
        home: Path = hosted.unique_auth_home(run_dir)
        environment = mail.cli_env(home)
        initial: dict[str, Any] = status(binary, environment)
        mail.check(initial["enabled"] is False, "semantic_default_not_disabled")

        creation_attempted = True
        added: dict[str, Any] = one(binary, environment, "address", "add", "semantic-" + nonce, "--tmp")
        mail.check(added.get("address") == address, "semantic_fixture_address_mismatch")
        await_address(binary, environment, address)
        zone: str = os.environ["CLOUDFLARE_ZONE_ID"]
        routing_token: str = os.environ["CF_EMAIL_ROUTING_TOKEN"]
        mail.assert_route(zone, routing_token, address, True)
        time.sleep(60)
        message: EmailMessage
        oracle: dict[str, Any]
        message, oracle = mail.make_mail(address, nonce + "-semantic", False)
        mail.smtp_send_receipts(os.environ["CLOUDFLARE_API_TOKEN"], address, [(message, oracle)])
        delivered: dict[str, dict[str, Any]] = mail.await_messages(binary, environment, {oracle["subject"]})
        candidate: Any = delivered[oracle["subject"]].get("id")
        mail.check(isinstance(candidate, str) and mail.MAIL_ID.fullmatch(candidate) is not None,
                   "semantic_fixture_message_id_invalid")
        message_id = candidate

        semantic_cleanup_required = True
        enabled: dict[str, Any] = status(binary, environment, "enable")
        mail.check(enabled["enabled"] and enabled["pending_messages"] >= 1,
                   "semantic_enable_did_not_backfill")
        await_index(binary, environment, enabled["generation"])
        semantic: list[dict[str, Any]] = search_once(binary, environment,
            "--mailbox", address, "--semantic", "synthetic harbor notification", "--limit", "100")
        mail.check(any(row.get("id") == message_id for row in semantic), "semantic_search_missing_fixture")
        disabled: dict[str, Any] = status(binary, environment, "disable")
        mail.check(disabled["enabled"] is False, "semantic_disable_failed")
        literal: list[dict[str, Any]] = search_once(binary, environment,
            "--mailbox", address, "--title", oracle["subject"], "--limit", "100")
        mail.check(any(row.get("id") == message_id for row in literal), "semantic_disabled_literal_missing_fixture")
        resumed: dict[str, Any] = status(binary, environment, "enable")
        mail.check(resumed["enabled"] and resumed["generation"] > disabled["generation"]
                   and resumed["pending_messages"] >= 1, "semantic_reenable_did_not_rebuild")
        await_index(binary, environment, resumed["generation"])
        mail.check(status(binary, environment, "disable")["enabled"] is False,
                   "semantic_final_disable_failed")
        semantic_cleanup_required = False
    except Exception as error:
        primary = error
    finally:
        def attempt(action: Callable[[], object]) -> None:
            nonlocal cleanup
            try:
                action()
            except Exception as error:
                if cleanup is None:
                    cleanup = error

        if environment is not None:
            if semantic_cleanup_required:
                attempt(lambda: mail.check(status(binary, environment, "disable")["enabled"] is False,
                                           "semantic_cleanup_not_disabled"))
            if message_id is not None:
                attempt(lambda: mail.amail(binary, environment, "delete", message_id,
                                           failure="semantic_fixture_delete_failed"))
            if creation_attempted:
                attempt(lambda: mail.amail(binary, environment, "address", "delete", address,
                                           failure="semantic_fixture_retire_failed"))
                attempt(lambda: mail.assert_route(os.environ["CLOUDFLARE_ZONE_ID"],
                    os.environ["CF_EMAIL_ROUTING_TOKEN"], address, False))
        try:
            private_cleanup: hosted.HostedProbeError | None = hosted.cleanup_run(run_dir, binary, release_user=True)
            if private_cleanup is not None and cleanup is None:
                cleanup = private_cleanup
        except Exception:
            if cleanup is None:
                cleanup = hosted.HostedProbeError("semantic_private_cleanup_failed")
    if primary is not None or cleanup is not None:
        labels: list[str] = [hosted.safe_stage_code(error) for error in (primary, cleanup) if error is not None]
        raise mail.ProbeFailure("_cleanup_".join(labels))
    receipt: dict[str, str] = acceptance_receipt(runtime,
        run_id=os.environ.get("GITHUB_RUN_ID", ""), checkout_sha=os.environ.get("GITHUB_SHA", ""))
    with ACCEPTANCE.open("x", encoding="utf-8") as file:
        json.dump(receipt, file, sort_keys=True)
    EVIDENCE.write_text(json.dumps({"schema": "amail-staging-semantic/v1",
        "source_run": "40188956353", "smtp_fixtures": 1, "semantic_query_intents": 1,
        "default_off": True, "background_backfill": True, "voyage4_query": True,
        "disable_literal_search": True, "reenable_full_rebuild": True,
        "left_disabled": True, "private_fixture_cleanup": True}, sort_keys=True), encoding="utf-8")
    print("staging_semantic_single_fixture_journey_verified")


def main() -> int:
    try:
        execute()
    except Exception as error:
        print("staging_semantic_e2e_failed:" + hosted.safe_stage_code(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
