"""Deploy one explicit Mail realm with private secrets and an exact recovery pin.

Production remains the default. Staging is branch/confirmation guarded and
always uses its explicit Wrangler environment; neither path retries a write or
treats a returned version as proof of the later immutable binding/privacy pin.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
from check_production_role_graph import ROOT
from pin_staging_mail import expected_bindings
from control_plane_trace import span
from tested_worker_artifact import require_artifact
from worker_deploy_result import DeploymentFailure, submit


def require_context(target: str) -> None:
    """Reject a wrong realm before writing secrets or executing any deployment.

    GitHub's protected workflow environment owns credential selection. Staging
    also verifies reviewed isolated config and its strict Queue binding so a
    branch selection cannot silently deploy default production capabilities.
    """
    branch = {"production": "refs/heads/main", "staging": "refs/heads/codex/v0.1.2-agent-first-performance"}.get(target)
    if branch is None or os.getenv("GITHUB_REF") != branch or not os.getenv("GITHUB_OUTPUT"):
        raise ValueError("context_unverified")
    if target == "staging":
        if (os.getenv("AMAIL_STAGING_MAIL_DEPLOY_CONFIRM") != "RUN_STAGING_V012"
                or os.getenv("AMAIL_TRACE_TOPOLOGY") != "api-scheduled"):
            raise ValueError("staging_context_unverified")
        from check_staging import check
        check()
        expected_bindings("queue-api", os.getenv("AMAIL_TRACE_QUEUE_ID", ""), realm="staging")


def main(argv: list[str] | None = None) -> int:
    """Never replay or print an ambiguous deployment; cleanup secret material always."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("production", "staging"), default="production")
    target = parser.parse_args(argv).target
    path = None
    try:
        with span("workers.deploy", "precondition", realm=target, component="mail_api") as facts:
            facts.reason = "realm_context_required"
            require_context(target)
            facts.reason = "realm_context_verified"
        require_artifact("mail_api")
        names = ("OPENROUTER_API_KEY", "CF_EMAIL_ROUTING_TOKEN", "INGRESS_SECRET")
        secrets = {name: os.getenv(name, "") for name in names}
        if not all(secrets.values()):
            with span("workers.deploy", "precondition", realm=target, component="mail_api") as facts:
                facts.reason = "project_secrets_missing"
                facts.schema_field = "project_secrets"
                facts.schema_expected = "all_required_values_present"
                facts.schema_actual_type = "missing_value"
                raise ValueError("secrets_unverified")
        (ROOT / ".temp").mkdir(exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=f"{target}-mail-secrets-", suffix=".json", dir=ROOT / ".temp")
        path = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
            path.chmod(0o600)
            json.dump(secrets, destination)
        command = ["wrangler", "deploy"]
        if target == "staging":
            command.extend(["--env", "staging"])
        command.extend(["--secrets-file", str(path)])
        try:
            version = submit(command, target, "mail_api", cwd=ROOT / "crates/mail-worker")
        except DeploymentFailure as error:
            if error.version is not None:
                write_version(error.version)
                print(f"{target}_api_deployment=recovery_version_captured version={error.version}")
            raise
        write_version(version)
    except (ValueError, KeyError, TypeError, IndexError, OSError, subprocess.TimeoutExpired):
        print(f"{target}_api_deployment=UNVERIFIED")
        return 1
    finally:
        if path is not None:
            path.unlink(missing_ok=True)
    print(f"{target}_api_deployment=version_captured")
    return 0


def write_version(version: str) -> None:
    """Preserve an exact provider UUID for subsequent readback, not a readiness claim."""
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as destination:
        destination.write(f"version={version}\n")

if __name__ == "__main__":
    raise SystemExit(main())
