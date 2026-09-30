"""Perform one guarded outbound canary after native PKCE on hosted Windows.

Only fixed stage labels reach Actions logs. The synthetic credential, sender,
recipient, control-plane token, DPAPI blob, session, ZIP and MIME never become
workflow inputs or artifacts. The one-use grant is issued separately, not here.
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
import shutil
import sys
import tempfile
import time

from staging_hosted_e2e import BUILT_BINARY, ROOT, TEMP, safe_stage_code, unique_auth_home
from staging_canary_recovery import RecoveryError, hosted_material
from staging_outbound_canary import (
    GrantWatermark, ProbeFailure, config, execute as canary_execute, grant_ready, grant_watermark,
    inbox_ready, preflight_controls, privacy_ready,
)


CONFIRM = "RUN_STAGING_OUTBOUND_CANARY"
SENDER = re.compile(r"[a-z0-9._+-]+@mail-staging\.moesegfault\.dev\Z")


class HostedOutboundError(Exception):
    """A source-owned, bounded failure label safe for the public job log."""


def await_operator_grant(sender: str) -> GrantWatermark:
    """Wait for a post-login, exact one-use grant without ever creating one."""

    values = config()
    privacy_ready(values)
    inbox_ready(values)
    preflight_controls(values, sender)
    watermark = grant_watermark(values, os.environ.get("GITHUB_RUN_ID", ""),
                                os.environ.get("GITHUB_RUN_ATTEMPT", ""))
    print("staging_outbound_ready_for_one_use_grant")
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        preflight_controls(values, sender)
        if grant_ready(values, after=watermark):
            return watermark
        time.sleep(5)
    raise HostedOutboundError("fresh_one_use_grant_timeout")


def validate() -> tuple[str, str, str]:
    """Deny unconfirmed/nonhosted runs and incomplete private capabilities."""

    if os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise HostedOutboundError("hosted_windows_required")
    if os.environ.get("AMAIL_OUTBOUND_CONFIRM") != CONFIRM:
        raise HostedOutboundError("explicit_staging_confirmation_required")
    if not BUILT_BINARY.is_file():
        raise HostedOutboundError("hosted_cli_binary_missing")
    sender = os.environ.get("AMAIL_CANARY_SENDER", "").lower()
    if not SENDER.fullmatch(sender):
        raise HostedOutboundError("canary_sender_invalid")
    try:
        config()
    except ProbeFailure as error:
        raise HostedOutboundError("capability_" + safe_stage_code(error)) from None
    try:
        hosted_material()
    except RecoveryError:
        raise HostedOutboundError("recovery_material_invalid") from None
    username = os.environ.pop("STAGING_E2E_USERNAME", "")
    password = os.environ.pop("STAGING_E2E_PASSWORD", "")
    if not re.fullmatch(r"[a-z0-9_]{3,32}", username) or not 15 <= len(password) <= 128:
        raise HostedOutboundError("staging_credential_invalid")
    return username, password, sender


def run() -> None:
    """Log in privately, run exactly one canary, and remove only this run's files."""

    username, password, sender = validate()
    if TEMP != ROOT / ".temp":
        raise HostedOutboundError("repo_temp_redirected")
    TEMP.mkdir(exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="staging-outbound-canary-", dir=TEMP)).resolve()
    if TEMP not in run_dir.parents:
        raise HostedOutboundError("run_path_outside_repo_temp")
    try:
        from staging_identity_cdp import ProbeError as IdentityError, native_login, store_credential

        binary = run_dir / "amail.exe"
        shutil.copy2(BUILT_BINARY, binary)
        try:
            store_credential(run_dir, username, password)
            del username, password
            native_login(run_dir, binary)
        except IdentityError as error:
            raise HostedOutboundError("identity_" + safe_stage_code(error)) from None
        try:
            watermark = await_operator_grant(sender)
        except ProbeFailure as error:
            raise HostedOutboundError("rendezvous_" + safe_stage_code(error)) from None
        args = argparse.Namespace(
            confirm_staging=True,
            home=str(unique_auth_home(run_dir)),
            amail=str(binary),
            run_dir=str(run_dir / "outbound"),
            sender=sender,
            grant_watermark=watermark,
        )
        try:
            canary_execute(args)
        except ProbeFailure as error:
            raise HostedOutboundError("canary_" + safe_stage_code(error)) from None
    finally:
        if TEMP not in run_dir.parents or not run_dir.name.startswith("staging-outbound-canary-"):
            raise HostedOutboundError("run_cleanup_path_invalid")
        try:
            shutil.rmtree(run_dir)
        except OSError:
            raise HostedOutboundError("run_cleanup_failed") from None


def main() -> int:
    """Emit only reviewed, fixed labels, including for unexpected exceptions."""

    try:
        run()
    except HostedOutboundError as error:
        print("staging_hosted_outbound_canary_failed:" + safe_stage_code(error), file=sys.stderr)
        return 1
    except Exception:
        print("staging_hosted_outbound_canary_failed:unexpected_failure", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
