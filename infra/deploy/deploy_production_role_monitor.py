"""One production role deploy; suppress private Wrangler output and persist recovery pin."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).parent))
import deploy_staging_role_monitor as staging


def main() -> int:
    """Reuse restricted secret handling, but require production-only exact confirmation."""
    if (os.getenv("AMAIL_ROLE_ROLLOUT_CONFIRM") != "RUN_PRODUCTION_UNROUTED_ROLE_ROLLOUT"
            or os.getenv("GITHUB_REF") != "refs/heads/main"):
        print("production_role_deployment=UNVERIFIED")
        return 1
    try:
        output = os.getenv("GITHUB_OUTPUT", "")
        if not output:
            raise ValueError("outputs_missing")
        version = staging.deploy(target="production")
        with open(output, "a", encoding="utf-8") as destination:
            destination.write(f"version={version}\n")
        print(f"production_role_deployment=version_captured version={version}")
    except (ValueError, OSError, subprocess.TimeoutExpired):
        print("production_role_deployment=UNVERIFIED")
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
