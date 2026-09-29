"""Run the reviewed retained-log canary on a hosted staging-only Windows runner.

The preflight mode reads only effective Worker settings and Observability key
metadata. The full mode requires a fresh native PKCE login using the existing
verified synthetic account, then delegates to the reviewed no-mail-mutation
canary. Raw credentials, CLI output, log rows, and provider errors never reach
the job log or an artifact.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
TEMP = (ROOT / ".temp").resolve()
BUILT_BINARY = ROOT / "target" / "debug" / "amail.exe"
CANARY = Path(__file__).with_name("staging_trace_canary.py")
CONFIRMATION = "RUN_STAGING_TRACE_CANARY"
HEX32 = re.compile(r"[0-9a-f]{32}\Z")
USERNAME = re.compile(r"[a-z0-9_]{3,32}\Z")
PREFLIGHT_CODES = frozenset({
    "deployed_privacy_settings_unverified",
    "observability_permission_denied",
    "observability_http_unavailable",
    "observability_network_unavailable",
    "observability_response_too_large",
    "observability_response_malformed",
    "observability_query_failed",
    "observability_keys_malformed",
    "service_filter_key_unverified",
})


class HostedTraceError(Exception):
    """A fixed, privacy-safe failure code for hosted job output."""


def preflight_live() -> tuple[str, str, str]:
    """Fail before login unless deployed privacy and service-key access pass."""

    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    deploy_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    obs_token = os.environ.get("CF_OBSERVABILITY_TOKEN", "")
    if not HEX32.fullmatch(account):
        raise HostedTraceError("account_id_missing_or_invalid")
    if not deploy_token:
        raise HostedTraceError("deploy_token_missing")
    if not obs_token:
        raise HostedTraceError("observability_secret_missing")
    from staging_trace_canary import CanaryError, preflight

    try:
        preflight(account, obs_token, deploy_token)
    except CanaryError as error:
        code = str(error)
        raise HostedTraceError(code if code in PREFLIGHT_CODES else "privacy_preflight_unverified") from None
    except Exception:
        raise HostedTraceError("privacy_preflight_unverified") from None
    return account, deploy_token, obs_token


def validated_credential() -> tuple[str, str]:
    """Consume only the staging synthetic account, never a human credential."""

    username = os.environ.pop("STAGING_E2E_USERNAME", "")
    password = os.environ.pop("STAGING_E2E_PASSWORD", "")
    if not USERNAME.fullmatch(username) or not 15 <= len(password) <= 128:
        raise HostedTraceError("staging_credential_missing_or_invalid")
    return username, password


def unique_auth_home(run_dir: Path) -> Path:
    """Accept only the one fresh home created by this run's native login."""

    homes = [path for path in run_dir.glob("amail-home-*") if path.is_dir()]
    if len(homes) != 1 or homes[0].is_symlink():
        raise HostedTraceError("authenticated_home_ambiguous")
    return homes[0]


def canary_environment(account: str, deploy_token: str, obs_token: str) -> dict[str, str]:
    """Pass only OS basics and the two query capabilities to the canary."""

    from staging_identity_cdp import browser_environment

    environment = browser_environment()
    environment.update({
        "CLOUDFLARE_ACCOUNT_ID": account,
        "CLOUDFLARE_API_TOKEN": deploy_token,
        "CF_OBSERVABILITY_TOKEN": obs_token,
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    return environment


def remove_run_dir(run_dir: Path) -> None:
    """Delete only this run's directory after verifying its absolute boundary."""

    try:
        resolved = run_dir.resolve(strict=True)
        if (TEMP != ROOT / ".temp" or resolved.parent != TEMP
                or not resolved.name.startswith("staging-hosted-trace-")
                or resolved.is_symlink()):
            raise HostedTraceError("run_cleanup_path_invalid")
        shutil.rmtree(resolved)
    except HostedTraceError:
        raise
    except OSError:
        raise HostedTraceError("run_cleanup_failed") from None


def execute(mode: str, confirmation: str) -> None:
    """Preflight first; only explicit full mode may start a browser or API probe."""

    if mode not in ("preflight", "canary"):
        raise HostedTraceError("invalid_mode")
    if mode == "canary" and confirmation != CONFIRMATION:
        raise HostedTraceError("explicit_staging_confirmation_required")
    account, deploy_token, obs_token = preflight_live()
    if mode == "preflight":
        print("staging_trace_hosted: preflight_verified")
        return
    if os.name != "nt":
        raise HostedTraceError("windows_runner_required")
    if TEMP != ROOT / ".temp":
        raise HostedTraceError("repo_temp_redirected")
    if not BUILT_BINARY.is_file():
        raise HostedTraceError("hosted_cli_binary_missing")
    username, password = validated_credential()
    TEMP.mkdir(exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="staging-hosted-trace-", dir=TEMP)).resolve()
    if run_dir.parent != TEMP:
        raise HostedTraceError("run_path_outside_repo_temp")
    try:
        from staging_identity_cdp import ProbeError, native_login, store_credential

        binary = run_dir / "amail.exe"
        shutil.copy2(BUILT_BINARY, binary)
        try:
            store_credential(run_dir, username, password)
            del username, password
            native_login(run_dir, binary)
        except ProbeError:
            raise HostedTraceError("native_pkce_login_failed") from None
        home = unique_auth_home(run_dir)
        result = subprocess.run(
            [sys.executable, str(CANARY), "--confirm", CONFIRMATION,
             "--amail", str(binary), "--home", str(home)],
            env=canary_environment(account, deploy_token, obs_token),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=240, check=False,
        )
        if result.returncode:
            raise HostedTraceError("retained_canary_unverified")
    except subprocess.TimeoutExpired:
        raise HostedTraceError("retained_canary_timed_out") from None
    finally:
        # No raw contents may survive the ephemeral runner or become an artifact.
        remove_run_dir(run_dir)
    print("staging_trace_hosted: retained_canary_verified")


def main() -> int:
    """Print only fixed stage labels regardless of third-party exception text."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("preflight", "canary"), required=True)
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    try:
        execute(args.mode, args.confirm)
    except HostedTraceError as error:
        print(f"staging_trace_hosted: UNVERIFIED ({error})", file=sys.stderr)
        return 1
    except Exception:
        print("staging_trace_hosted: UNVERIFIED (unexpected_failure)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
