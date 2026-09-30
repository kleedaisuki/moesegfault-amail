"""One-shot native-PKCE semantic query against an empty synthetic staging mailbox.

This probe sends no SMTP, creates no address, and never prints a query, message,
job, token, or browser URL. Search itself may charge an OpenRouter embedding
and writes short-lived server-side job/quota accounting; it is not a D1 no-op.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from staging_hosted_e2e import BUILT_BINARY, ROOT, TEMP, safe_stage_code, unique_auth_home
from staging_mail_e2e import cli_env, cli_failure


CONFIRM = "RUN_STAGING_SEMANTIC_QUERY_ONLY"
JOB = rb"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}"
QUERY = "synthetic staging empty corpus check"


class ProbeError(Exception):
    """A fixed, public-safe failure label; never pass through third-party text."""


def require(condition: bool, label: str) -> None:
    """Fail with a source-owned label only."""

    if not condition:
        raise ProbeError(label)


def validate() -> tuple[str, str]:
    """Require one explicit hosted staging run and only Identity credentials."""

    require(os.name == "nt", "windows_runner_required")
    require(os.environ.get("AMAIL_SEMANTIC_QUERY_CONFIRM") == CONFIRM,
            "explicit_semantic_query_confirmation_required")
    require(re.fullmatch(r"[0-9]{1,20}", os.environ.get("GITHUB_RUN_ID", "")) is not None
            and re.fullmatch(r"[0-9]{1,3}", os.environ.get("GITHUB_RUN_ATTEMPT", "")) is not None,
            "github_run_coordinates_missing")
    username = os.environ.pop("STAGING_E2E_USERNAME", "")
    password = os.environ.pop("STAGING_E2E_PASSWORD", "")
    require(re.fullmatch(r"[a-z0-9_]{3,32}", username) is not None
            and 15 <= len(password) <= 128, "staging_credential_invalid")
    require(BUILT_BINARY.is_file(), "hosted_cli_binary_missing")
    return username, password


def run_cli(binary: Path, home: Path, *args: str, timeout: int = 45) -> subprocess.CompletedProcess:
    """Capture every CLI byte privately with bounded time/size and no inherited secrets."""

    try:
        result = subprocess.run([str(binary), *args], env=cli_env(home),
                                capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise ProbeError("cli_subprocess_timeout") from None
    except OSError:
        raise ProbeError("cli_process_error") from None
    require(len(result.stdout) <= 2_000_000 and len(result.stderr) <= 65_536,
            "cli_output_oversized")
    return result


def jsonl(raw: bytes) -> list[dict]:
    """Accept only compact JSONL objects, without rendering any field."""

    try:
        values = [json.loads(line) for line in raw.splitlines() if line.strip()]
    except (ValueError, UnicodeDecodeError):
        raise ProbeError("cli_output_invalid") from None
    require(all(isinstance(value, dict) for value in values), "cli_output_invalid")
    return values


def empty_owner_inventory(binary: Path, home: Path) -> None:
    """A complete unfiltered owner-scoped page must have no rows or cursor."""

    result = run_cli(binary, home, "search", "--limit", "100", "--wait-seconds", "30")
    require(result.returncode == 0, "inventory_search_unverified")
    require(not jsonl(result.stdout), "owner_mailbox_not_empty")


def classify_semantic_error(stderr: bytes) -> str:
    """Retain only POST/poll and reviewed status/code labels, never the job ID."""

    label = cli_failure(stderr, "semantic_query_failed")
    if not label.startswith("semantic_query_failed_http_"):
        return "semantic_query_failed_unclassified"
    poll = re.search(rb"(?:^|\n)amail: search job " + JOB
                     + rb": mail API messages\.search\.poll failed: HTTP ", stderr)
    post = re.search(rb"(?:^|\n)amail: mail API messages\.search failed: HTTP ", stderr)
    if bool(poll) == bool(post):
        return "semantic_query_failed_phase_unverified"
    return label.replace("semantic_query_failed_", "semantic_query_poll_" if poll
                         else "semantic_query_post_", 1)


def probe(binary: Path, home: Path) -> None:
    """Reject any pre-existing active mail before spending one semantic query."""

    empty_owner_inventory(binary, home)
    result = run_cli(binary, home, "search", "--semantic", QUERY,
                     "--limit", "100", "--wait-seconds", "30", timeout=45)
    if result.returncode:
        raise ProbeError(classify_semantic_error(result.stderr))
    require(not jsonl(result.stdout), "semantic_empty_result_unverified")


def execute() -> None:
    """Perform native login, one inventory read, one query, and scoped cleanup."""

    username, password = validate()
    require(TEMP == ROOT / ".temp", "repo_temp_redirected")
    TEMP.mkdir(exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="staging-semantic-query-", dir=TEMP)).resolve()
    require(TEMP in run_dir.parents, "run_path_outside_repo_temp")
    try:
        from staging_identity_cdp import ProbeError as IdentityError, native_login, store_credential

        binary = run_dir / "amail.exe"
        shutil.copy2(BUILT_BINARY, binary)
        try:
            store_credential(run_dir, username, password)
            del username, password
            native_login(run_dir, binary)
        except IdentityError as error:
            raise ProbeError("identity_" + safe_stage_code(error)) from None
        probe(binary, unique_auth_home(run_dir))
    finally:
        require(TEMP in run_dir.parents and run_dir.name.startswith("staging-semantic-query-"),
                "run_cleanup_path_invalid")
        try:
            shutil.rmtree(run_dir)
        except OSError:
            raise ProbeError("run_cleanup_failed") from None


def main() -> int:
    """Log only fixed labels; no traceback may expose captured private data."""

    try:
        execute()
    except ProbeError as error:
        print("staging_semantic_query_only=" + safe_stage_code(error))
        return 1
    except Exception:
        print("staging_semantic_query_only=unexpected_failure")
        return 1
    print("staging_semantic_query_only=empty_query_completed_and_local_cleanup_passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
