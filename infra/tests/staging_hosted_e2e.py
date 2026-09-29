"""Run native Identity login and real inbound-mail acceptance on a hosted Windows runner.

The already verified synthetic account is supplied through staging Environment
Secrets. This module never registers an account, accepts a person's credential,
or prints an authorization URL, token, address, or message. Invoke only through
the explicitly confirmed staging workflow.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
TEMP = (ROOT / ".temp").resolve()
BUILT_BINARY = ROOT / "target" / "debug" / "amail.exe"
CONFIRMATION = "RUN_STAGING_E2E"


class HostedProbeError(Exception):
    """A fixed, nonsensitive failure label safe for the hosted job log."""


def safe_stage_code(error: Exception) -> str:
    """Keep only bounded harness-owned snake-case diagnostic labels.

    The native and mail probes construct typed errors from fixed source-code
    labels, not provider response text. Reject any future exception payload
    that violates that contract rather than copying it into Actions logs.
    """

    label = str(error)
    return label if re.fullmatch(r"[a-z][a-z0-9_]{2,160}", label) else "unexpected_failure"


def validate_environment() -> tuple[str, str]:
    """Require the narrow staging capability set before any browser activity."""

    if os.name != "nt":
        raise HostedProbeError("windows_runner_required")
    if os.environ.get("AMAIL_STAGING_E2E_CONFIRM") != CONFIRMATION:
        raise HostedProbeError("explicit_staging_confirmation_required")
    username = os.environ.pop("STAGING_E2E_USERNAME", "")
    password = os.environ.pop("STAGING_E2E_PASSWORD", "")
    if not re.fullmatch(r"[a-z0-9_]{3,32}", username):
        raise HostedProbeError("staging_credential_invalid")
    if not 15 <= len(password) <= 128:
        raise HostedProbeError("staging_credential_invalid")
    if not re.fullmatch(r"[a-f0-9]{32}", os.environ.get("CLOUDFLARE_ZONE_ID", "")):
        raise HostedProbeError("staging_zone_missing")
    if not os.environ.get("CF_EMAIL_ROUTING_TOKEN"):
        raise HostedProbeError("staging_routing_token_missing")
    if not os.environ.get("CLOUDFLARE_API_TOKEN"):
        raise HostedProbeError("staging_smtp_token_missing")
    if not BUILT_BINARY.is_file():
        raise HostedProbeError("hosted_cli_binary_missing")
    return username, password


def unique_auth_home(run_dir: Path) -> Path:
    """Select only the fresh home created by this run's successful native login."""

    homes = [path for path in run_dir.glob("amail-home-*") if path.is_dir()]
    if len(homes) != 1:
        raise HostedProbeError("authenticated_home_ambiguous")
    return homes[0]


def recoverable_run_nonce(password: str) -> str:
    """Derive a private alias suffix from the protected synthetic password.

    An operator can reconstruct the exact orphaned alias after a runner crash
    with the staging secret and run coordinates, without making a live route
    guessable from the public Actions run URL alone.
    """

    run_id = os.environ.get("GITHUB_RUN_ID", "")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "")
    if not re.fullmatch(r"[0-9]{1,20}", run_id) or not re.fullmatch(r"[0-9]{1,3}", attempt):
        raise HostedProbeError("github_run_coordinates_missing")
    message = f"amail-staging-e2e/v1:{run_id}:{attempt}".encode("ascii")
    digest = hmac.new(password.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return digest[:16]


def execute() -> None:
    """Exercise deployed staging services while containing all data in one run dir."""

    username, password = validate_environment()
    nonce = recoverable_run_nonce(password)
    if TEMP != ROOT / ".temp":
        raise HostedProbeError("repo_temp_redirected")
    TEMP.mkdir(exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="staging-hosted-e2e-", dir=TEMP)).resolve()
    if TEMP not in run_dir.parents:
        raise HostedProbeError("run_path_outside_repo_temp")
    try:
        from staging_identity_cdp import ProbeError, native_login, store_credential
        import staging_mail_e2e

        binary = run_dir / "amail.exe"
        shutil.copy2(BUILT_BINARY, binary)
        try:
            store_credential(run_dir, username, password)
            del username, password
            native_login(run_dir, binary)
        except ProbeError as error:
            raise HostedProbeError(f"identity_{safe_stage_code(error)}") from None
        home = unique_auth_home(run_dir)

        # The SMTP harness receives this bearer capability, but its CLI child
        # processes use a strict environment allowlist and never inherit it.
        os.environ["AMAIL_TEST_SMTP_TOKEN"] = os.environ["CLOUDFLARE_API_TOKEN"]
        os.environ["AMAIL_TEST_RUN_NONCE"] = nonce
        argv = sys.argv
        try:
            sys.argv = [
                "staging_mail_e2e.py", "--confirm-staging",
                "--home", str(home), "--amail", str(binary),
            ]
            try:
                outcome = staging_mail_e2e.main()
            except staging_mail_e2e.ProbeFailure as error:
                raise HostedProbeError(f"mail_{safe_stage_code(error)}") from None
            if outcome != 0:
                raise HostedProbeError("inbound_acceptance_failed")
        finally:
            sys.argv = argv
            os.environ.pop("AMAIL_TEST_SMTP_TOKEN", None)
            os.environ.pop("AMAIL_TEST_RUN_NONCE", None)
    finally:
        # Only the freshly created, validated run directory is eligible.
        # This also removes the DPAPI blob, encrypted CLI session, Chrome
        # profile, ZIPs, and MIME extracted by the real-mail harness.
        if TEMP not in run_dir.parents or not run_dir.name.startswith("staging-hosted-e2e-"):
            raise HostedProbeError("run_cleanup_path_invalid")
        try:
            shutil.rmtree(run_dir)
        except OSError:
            raise HostedProbeError("run_cleanup_failed") from None


def main() -> int:
    """Report only static phase markers; never render a third-party exception."""

    try:
        execute()
    except HostedProbeError as error:
        print(f"staging_hosted_e2e_failed:{error}", file=sys.stderr)
        return 1
    except Exception:
        print("staging_hosted_e2e_failed:unexpected_failure", file=sys.stderr)
        return 1
    print("staging_hosted_native_login_and_inbound_mail_verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
