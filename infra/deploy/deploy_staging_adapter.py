"""Submit one reviewed staging adapter once and retain its exact version output.

The hosted workflow restores tested bytes and owns preflight/readback admission.
This helper cannot deploy production, retry, or treat a failed submit as absence.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from check_staging_adapters import ROOT, source_configs
from worker_deploy_result import DeploymentFailure, submit
from tested_worker_artifact import require_artifact


def deploy(component: str) -> str:
    """Use only the candidate's two source-owned adapters and a private secret file."""
    if (component not in ("ingress", "events") or os.getenv("GITHUB_ACTIONS") != "true"
            or os.getenv("GITHUB_REF") != "refs/heads/codex/v0.1.2-agent-first-performance"
            or os.getenv("AMAIL_STAGING_DEPLOY_CONFIRM") != "RUN_STAGING_V012"
            or not os.getenv("CLOUDFLARE_ACCOUNT_ID") or not os.getenv("CLOUDFLARE_API_TOKEN")):
        raise ValueError("adapter_deploy_coordinates_unverified")
    source_configs()
    require_artifact(f"mail_{component}")
    command = ["wrangler", "deploy", "--env", "staging"]
    path = None
    try:
        if component == "ingress":
            secret = os.getenv("INGRESS_SECRET", "")
            if not secret:
                raise ValueError("adapter_secret_unverified")
            temporary = ROOT / ".temp"
            temporary.mkdir(exist_ok=True)
            fd, name = tempfile.mkstemp(prefix="staging-ingress-secrets-", suffix=".json", dir=temporary)
            path = Path(name)
            with os.fdopen(fd, "w", encoding="utf-8") as destination:
                os.chmod(path, 0o600)
                json.dump({"INGRESS_SECRET": secret}, destination)
            command.extend(["--secrets-file", str(path)])
        return submit(command, "staging", f"mail-{component}", cwd=ROOT / "workers" / f"mail-{component}")
    finally:
        if path is not None:
            path.unlink(missing_ok=True)


def record(version: str) -> None:
    """Expose a validated non-secret UUID for later exact readback or recovery."""
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as destination:
        destination.write(f"version={version}\n")


def main() -> int:
    """A failing submit may record an observed recovery pin, never success/replay."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--component", choices=("ingress", "events"), required=True)
    args = parser.parse_args()
    try:
        if not os.getenv("GITHUB_OUTPUT"):
            raise ValueError("adapter_output_missing")
        version = deploy(args.component)
        record(version)
    except DeploymentFailure as error:
        if error.version is not None:
            record(error.version)
            print("staging_adapter_deploy=recovery_version_captured")
        print("staging_adapter_deploy=UNVERIFIED")
        return 1
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired):
        print("staging_adapter_deploy=UNVERIFIED")
        return 1
    print("staging_adapter_deploy=version_captured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
