"""Exercise only native permanent-mailbox lease persistence on staging."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

import staging_hosted_e2e as hosted
import staging_mail_e2e as mail
from staging_semantic_e2e import managed_baseline_local

ROOT: Path = Path(__file__).resolve().parents[2]
ACCEPTANCE: Path = ROOT / ".temp/permanent-acquire-acceptance.json"
CONFIRMATION: str = "RUN_STAGING_PERMANENT_ACQUIRE"
VERSION: str = "0.3.2"


def one(binary: Path, environment: dict[str, str], *args: str) -> dict[str, Any]:
    values: list[dict[str, Any]] = mail.amail(binary, environment, *args,
        failure="permanent_acquire_cli_failed")
    mail.check(len(values) == 1, "permanent_acquire_response_shape")
    value: dict[str, Any] = values[0]
    mail.check("lease_token" not in value and "session_token" not in value,
               "permanent_acquire_private_capability_in_stdout")
    return value


def require_baseline(inventory: list[dict[str, Any]], address: str) -> None:
    matches: list[dict[str, Any]] = [row for row in inventory if row.get("address") == address]
    mail.check(len(matches) == 1 and matches[0].get("kind") == "mail"
               and matches[0].get("state") == "active" and matches[0].get("generation") == ""
               and matches[0].get("expires_at") is None,
               "permanent_acquire_managed_baseline_missing")


def lease_journey(binary: Path, environment: dict[str, str], address: str) -> None:
    # Each call is a new CLI process. Release must consume the saved capability;
    # acquiring read after release must not retain the old writer's mode.
    for mode in ("read", "read", "write"):
        value: dict[str, Any] = one(binary, environment, "mailbox", "acquire", address, "--mode", mode)
        mail.check(value.get("address") == address and value.get("generation") == ""
                   and value.get("mode") == mode, "permanent_acquire_lease_contract")
    mail.check(one(binary, environment, "mailbox", "release", address).get("released") is True,
               "permanent_acquire_release_failed")
    value = one(binary, environment, "mailbox", "acquire", address, "--mode", "read")
    mail.check(value.get("address") == address and value.get("generation") == ""
               and value.get("mode") == "read", "permanent_acquire_reacquire_contract")
    mail.check(one(binary, environment, "mailbox", "release", address).get("released") is True,
               "permanent_acquire_final_release_failed")


def execute() -> None:
    mail.check(os.name == "nt" and os.environ.get("GITHUB_ACTIONS") == "true"
               and os.environ.get("GITHUB_RUN_ATTEMPT") == "1"
               and os.environ.get("GITHUB_REF") == "refs/tags/v0.3.2"
               and os.environ.get("AMAIL_STAGING_PERMANENT_ACQUIRE_CONFIRM") == CONFIRMATION,
               "permanent_acquire_confirmation_required")
    run_id: str = os.environ.get("GITHUB_RUN_ID", "")
    source_sha: str = os.environ.get("GITHUB_SHA", "")
    mail.check(re.fullmatch(r"[1-9][0-9]{0,19}", run_id) is not None
               and re.fullmatch(r"[0-9a-f]{40}", source_sha) is not None,
               "permanent_acquire_run_identity_invalid")
    mail.check(not ACCEPTANCE.exists() and not ACCEPTANCE.is_symlink(),
               "permanent_acquire_receipt_exists")
    username: str = os.environ.pop("STAGING_E2E_USERNAME", "")
    password: str = os.environ.pop("STAGING_E2E_PASSWORD", "")
    mail.check(re.fullmatch(r"[a-z0-9_]{3,32}", username) is not None and 15 <= len(password) <= 128,
               "permanent_acquire_credential_invalid")
    address: str = managed_baseline_local(username, password) + "@mail-staging.moesegfault.dev"
    selected: Path = hosted.selected_binary()
    mail.check(selected.is_file() and not selected.is_symlink(), "permanent_acquire_candidate_missing")
    with selected.open("rb") as file:
        digest: str = hashlib.file_digest(file, "sha256").hexdigest()
    mail.check(re.fullmatch(r"[0-9a-f]{64}", os.environ.get("AMAIL_STAGING_TEST_BINARY_SHA256", "")) is not None
               and digest == os.environ["AMAIL_STAGING_TEST_BINARY_SHA256"],
               "permanent_acquire_candidate_hash_mismatch")
    mail.TEMP.mkdir(exist_ok=True)
    run_dir: Path = Path(tempfile.mkdtemp(prefix="staging-hosted-e2e-permanent-", dir=mail.TEMP)).resolve()
    mail.check(mail.TEMP in run_dir.parents and not run_dir.is_symlink(), "permanent_acquire_private_path_invalid")
    binary: Path = run_dir / "amail.exe"
    primary: Exception | None = None
    cleanup: hosted.HostedProbeError | None = None
    try:
        import staging_identity_cdp as identity

        shutil.copy2(selected, binary)
        version: subprocess.CompletedProcess[bytes] = subprocess.run([str(binary), "--version"],
            capture_output=True, timeout=20, check=False)
        mail.check(version.returncode == 0 and version.stdout.strip() == ("amail " + VERSION).encode("ascii"),
                   "permanent_acquire_candidate_version_mismatch")
        identity.store_credential(run_dir, username, password)
        identity.native_login(run_dir, binary)
        del username, password
        environment: dict[str, str] = mail.cli_env(hosted.unique_auth_home(run_dir))
        require_baseline(mail.amail(binary, environment, "address", "list",
            failure="permanent_acquire_inventory_failed"), address)
        lease_journey(binary, environment, address)
    except Exception as error:
        primary = error
    finally:
        try:
            cleanup = hosted.cleanup_run(run_dir, binary, release_user=True)
        except Exception:
            cleanup = hosted.HostedProbeError("permanent_acquire_private_cleanup_failed")
    if primary is not None or cleanup is not None:
        labels: list[str] = [hosted.safe_stage_code(error) for error in (primary, cleanup) if error is not None]
        raise mail.ProbeFailure("_cleanup_".join(labels))
    receipt: dict[str, Any] = {"schema": "amail-permanent-acquire/v1", "run_id": run_id,
        "source_sha": source_sha, "version": VERSION, "binary_sha256": digest, "realm": "staging",
        "empty_generation": True, "read_write_repeated_acquire": True, "release_reacquire": True,
        "private_capability_redacted": True, "private_cleanup": True, "managed_baseline_retained": True}
    with ACCEPTANCE.open("x", encoding="utf-8") as file:
        json.dump(receipt, file, sort_keys=True)
    print("staging_permanent_mailbox_acquire_verified")


def main() -> int:
    try:
        execute()
    except Exception as error:
        print("staging_permanent_acquire_failed:" + hosted.safe_stage_code(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
