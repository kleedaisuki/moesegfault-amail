"""One bounded Wrangler submit with typed diagnostics and an ambiguous recovery pin."""

from pathlib import Path
import re
import subprocess

from control_plane_trace import span

UUID = r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}"
LIMIT = 1_048_576


class DeploymentFailure(ValueError):
    """A failed submit may carry an exact observed version, never an acceptance pin."""

    def __init__(self, reason: str, version: str | None = None):
        """Only source-owned reasons and validated UUIDs leave the provider boundary."""
        super().__init__(reason)
        self.version = version


def submit(command: list[str], realm: str, component: str, *, cwd: Path | None = None) -> str:
    """Attempt once, retain exit/version facts, and never expose raw output or retry.

    A version printed on a failing exit is useful for readback/manual recovery.
    It does not prove the submit failed remotely or justify replay/rollback.
    """
    with span("workers.deploy", "submit", realm=realm, component=component) as facts:
        try:
            result = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                                    check=False, timeout=600)
        except subprocess.TimeoutExpired:
            facts.reason = "submit_timeout_ambiguous"
            raise
        except OSError:
            facts.reason = "process_unavailable"
            raise
        facts.process_exit_code = result.returncode
        if len(result.stdout) + len(result.stderr) > LIMIT:
            facts.reason = "output_limit"
            raise DeploymentFailure(facts.reason)
        versions = re.findall(r"Current Version ID:\s*(" + UUID + r")(?=\s|$)", result.stdout + result.stderr)
        facts.version_count = len(versions)
        version = versions[0] if len(versions) == 1 else None
        facts.version = version
        if result.returncode or version is None:
            facts.reason = "process_exit" if result.returncode else "version_count"
            raise DeploymentFailure(facts.reason, version)
        return version
