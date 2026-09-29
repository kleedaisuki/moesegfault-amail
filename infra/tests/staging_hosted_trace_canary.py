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
import time


ROOT = Path(__file__).resolve().parents[2]
TEMP = (ROOT / ".temp").resolve()
BUILT_BINARY = ROOT / "target" / "debug" / "amail.exe"
CANARY = Path(__file__).with_name("staging_trace_canary.py")
CONFIRMATION = "RUN_STAGING_TRACE_CANARY"
CHILD_SUCCESS = b"staging_trace_canary: retained_marker_absence_and_cli_api_parentage_verified"
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
RETAINED_CHILD_CODES = PREFLIGHT_CODES | frozenset({
    # Fixed local-probe and retained-assertion codes from staging_trace_canary.
    "account_id_missing_or_invalid", "observability_or_deploy_token_missing",
    "path_not_under_temp", "cli_or_home_missing", "cli_journal_missing",
    "cli_list_not_correlatable", "cli_trace_id_invalid", "cli_span_id_invalid",
    "cli_request_id_invalid", "cli_address_list_failed",
    "rejected_url_network_unavailable", "rejected_url_contract_failed",
    "local_probe_unavailable", "synthetic_url_marker_retained",
    "service_filter_not_enforced", "unreviewed_retained_payload",
    "application_event_schema_unallowlisted", "cli_api_root_missing_or_duplicate",
    "cli_api_parentage_invalid", "rejected_request_event_missing",
    "observability_permission_denied", "observability_http_unavailable",
    "observability_network_unavailable", "observability_response_too_large",
    "observability_response_malformed", "observability_query_failed",
    "observability_result_malformed", "observability_run_malformed",
    "observability_query_incomplete", "observability_query_status_unverified",
    "observability_query_echo_unverified",
    "observability_events_view_absent", "observability_events_malformed",
    "observability_count_malformed", "observability_window_too_busy",
    "observability_page_incomplete", "observability_cursor_missing",
    "observability_cursor_stalled", "retained_window_empty",
})
CLEANUP_RETRY_DELAYS = (0.2, 0.4, 0.8, 1.6)
WINDOWS_LOCK_ERRORS = frozenset({5, 32, 33, 145})


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


def child_failure_code(output: object) -> str:
    """Expose only an exact reviewed child code, never arbitrary child output."""

    if not isinstance(output, bytes) or len(output) > 160:
        return "retained_canary_unverified"
    try:
        line = output.decode("ascii").strip()
    except UnicodeDecodeError:
        return "retained_canary_unverified"
    match = re.fullmatch(r"staging_trace_canary: UNVERIFIED \(([a-z_]+)\)", line)
    if match and match.group(1) in RETAINED_CHILD_CODES:
        return match.group(1)
    return "retained_canary_unverified"


def child_success_verified(output: object) -> bool:
    """Require the child's exact fixed proof line before declaring success."""

    return isinstance(output, bytes) and len(output) <= 160 and output in (
        CHILD_SUCCESS + b"\n", CHILD_SUCCESS + b"\r\n",
    )


def remove_run_dir(run_dir: Path) -> None:
    """Delete only this run's directory, retrying bounded Windows lock races."""

    try:
        resolved = run_dir.resolve(strict=True)
        if (TEMP != ROOT / ".temp" or resolved.parent != TEMP
                or not resolved.name.startswith("staging-hosted-trace-")
                or run_dir.is_symlink()):
            raise HostedTraceError("run_cleanup_path_invalid")
        for delay in (*CLEANUP_RETRY_DELAYS, None):
            try:
                shutil.rmtree(resolved)
                return
            except OSError as error:
                # Windows may briefly hold files after the browser/CLI exits.
                # Retry only known lock-related errors; never report success
                # without a completed recursive removal.
                if delay is None or getattr(error, "winerror", None) not in WINDOWS_LOCK_ERRORS:
                    raise
                time.sleep(delay)
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
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=240, check=False,
        )
        if result.returncode:
            raise HostedTraceError(child_failure_code(getattr(result, "stdout", None)))
        if not child_success_verified(getattr(result, "stdout", None)):
            raise HostedTraceError("retained_canary_success_unconfirmed")
    except subprocess.TimeoutExpired:
        raise HostedTraceError("retained_canary_timed_out") from None
    finally:
        # Keep the primary failure visible if cleanup independently fails.
        # Both diagnostic labels are fixed; no private exception text escapes.
        primary = sys.exception()
        try:
            remove_run_dir(run_dir)
        except HostedTraceError as cleanup_error:
            if primary is not None:
                code = str(primary) if isinstance(primary, HostedTraceError) else "unexpected_failure"
                raise HostedTraceError(f"{code}; {cleanup_error}") from None
            raise
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
