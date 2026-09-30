"""Hosted native-PKCE wrapper for the explicitly guarded Queue-sink privacy canary.

The owner must supply both independently observed serving version IDs. Secrets
are environment-only, login output is suppressed, and no archive is published.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import tempfile

import staging_hosted_trace_canary as hosted
import staging_trace_canary as legacy
import staging_trace_sink_canary as sink


def execute(mode: str, confirm: str, source_version: str, sink_version: str) -> None:
    """Preflight before credentials; clean the sole isolated home after every outcome."""
    legacy.need(mode in ("preflight", "canary"), "invalid_mode")
    legacy.need(mode == "preflight" or confirm == sink.CONFIRM, "explicit_staging_confirmation_required")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    deploy, obs = os.environ.get("CLOUDFLARE_API_TOKEN", ""), os.environ.get("CF_OBSERVABILITY_TOKEN", "")
    legacy.need(legacy.HEX32.fullmatch(account) is not None and bool(deploy and obs), "sink_capability_missing")
    sink.preflight(account, obs, deploy, source_version, sink_version)
    if mode == "preflight":
        print("staging_trace_sink_hosted: preflight_verified")
        return
    legacy.need(os.name == "nt", "windows_runner_required")
    legacy.need(hosted.TEMP == legacy.ROOT / ".temp" and hosted.BUILT_BINARY.is_file(),
                "hosted_cli_binary_or_temp_unverified")
    username, password = hosted.validated_credential()
    hosted.TEMP.mkdir(exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="staging-hosted-trace-", dir=hosted.TEMP)).resolve()
    legacy.need(run_dir.parent == hosted.TEMP, "run_path_outside_repo_temp")
    try:
        from staging_identity_cdp import ProbeError, native_login, store_credential
        binary = run_dir / "amail.exe"
        shutil.copy2(hosted.BUILT_BINARY, binary)
        try:
            store_credential(run_dir, username, password)
            del username, password
            native_login(run_dir, binary)
        except ProbeError:
            raise legacy.CanaryError("native_pkce_login_failed") from None
        sink.execute(binary, hosted.unique_auth_home(run_dir), source_version, sink_version)
    finally:
        hosted.remove_run_dir(run_dir)
    print("staging_trace_sink_hosted: bounded_retained_canary_verified")


def main() -> int:
    """Expose no arbitrary traceback/provider text, including malformed cleanup errors."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("preflight", "canary"), required=True)
    parser.add_argument("--confirm", default="")
    parser.add_argument("--source-version", required=True)
    parser.add_argument("--sink-version", required=True)
    args = parser.parse_args()
    try:
        execute(args.mode, args.confirm, args.source_version, args.sink_version)
    except legacy.CanaryError as error:
        print(f"staging_trace_sink_hosted: UNVERIFIED ({error.args[0]})")
        return 1
    except hosted.HostedTraceError:
        print("staging_trace_sink_hosted: UNVERIFIED (hosted_login_or_cleanup_unverified)")
        return 1
    except Exception:
        print("staging_trace_sink_hosted: UNVERIFIED (unexpected_failure)")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
