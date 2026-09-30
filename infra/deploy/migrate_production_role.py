"""Apply one bounded additive role migration only after strict lifecycle readback."""
from __future__ import annotations
import os
import subprocess
from check_production_role_graph import ROOT, storage


def main() -> int:
    """Never print Wrangler responses or replay an ambiguous migration."""
    try:
        if (os.getenv("GITHUB_REF") != "refs/heads/main"
                or os.getenv("AMAIL_ROLE_ROLLOUT_CONFIRM") != "RUN_PRODUCTION_UNROUTED_ROLE_ROLLOUT"):
            raise ValueError("confirmation_unverified")
        lifecycle = os.getenv("AMAIL_ROLE_LIFECYCLE", "")
        storage(lifecycle)
        result = subprocess.run(["wrangler", "d1", "migrations", "apply", "ROLE_MONITOR", "--remote"],
                                cwd=ROOT / "workers/role-monitor", capture_output=True,
                                text=True, timeout=180, check=False)
        if result.returncode or len(result.stdout) + len(result.stderr) > 262144:
            raise ValueError("migration_unverified")
        storage("migrated" if lifecycle == "first-bootstrap" else "replacement")
    except (ValueError, RuntimeError, TypeError, KeyError, OSError, subprocess.TimeoutExpired):
        print("production_role_migration=UNVERIFIED")
        return 1
    print("production_role_migration=empty_expired_schema_verified")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
