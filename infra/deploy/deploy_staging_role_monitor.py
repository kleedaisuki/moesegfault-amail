"""Deploy only the staging role Worker, suppressing private Wrangler output.

The workflow supplies an absent-route/exact-phase1 gate immediately before this
one non-retried operation. A newly parsed version is a recovery pin, not proof
that later phase2 privacy/capability readback succeeded.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
UUID = r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}"
CONFIRM = "RUN_STAGING_ROLE_TRACE_ROLLOUT"


def deploy() -> str:
    """Use a restricted temporary secrets file and never print/retry raw output."""
    if os.getenv("AMAIL_ROLE_ROLLOUT_CONFIRM") != CONFIRM:
        raise ValueError("confirmation_unverified")
    names = {"ROLE_FORWARD_DESTINATION": "ROLE_FORWARD_DESTINATION",
             "CF_EMAIL_ROUTING_TOKEN": "CF_EMAIL_ROUTING_TOKEN",
             "CF_ACCOUNT_ID": "CLOUDFLARE_ACCOUNT_ID"}
    secrets = {key: os.getenv(source, "") for key, source in names.items()}
    if not all(secrets.values()):
        raise ValueError("protected_config_unverified")
    temporary = ROOT / ".temp"
    temporary.mkdir(exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="role-monitor-secrets-", suffix=".json", dir=temporary)
    path = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as destination:
            os.chmod(path, 0o600)
            json.dump(secrets, destination)
        result = subprocess.run(["wrangler", "deploy", "--env", "staging", "--secrets-file", str(path)],
                                cwd=ROOT / "workers/role-monitor", capture_output=True,
                                text=True, check=False, timeout=600)
        if result.returncode or len(result.stdout) + len(result.stderr) > 1_048_576:
            raise ValueError("deployment_unverified")
        versions = re.findall(r"Current Version ID:\s*(" + UUID + r")(?=\s|$)", result.stdout + result.stderr)
        if len(versions) != 1:
            raise ValueError("deployment_unverified")
        return versions[0]
    finally:
        path.unlink(missing_ok=True)


def main() -> int:
    """Record a non-secret exact deployment pin for readback and ambiguous recovery."""
    try:
        output = os.getenv("GITHUB_OUTPUT", "")
        if not output:
            raise ValueError("outputs_missing")
        version = deploy()
        with open(output, "a", encoding="utf-8") as destination:
            destination.write(f"version={version}\n")
        print(f"staging_role_deployment=version_captured version={version}")
    except (ValueError, OSError, subprocess.TimeoutExpired):
        print("staging_role_deployment=UNVERIFIED")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
