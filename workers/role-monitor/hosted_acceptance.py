"""Gate one GitHub-hosted staging SMTP probe on an audited deployed Worker.

This wrapper never mutates routing itself. The reviewed acceptance harness owns
the one disposable rule and its ID-bound cleanup; this wrapper keeps the
deployment provenance, private Worker checks, and post-run drift visible as
fixed labels without exporting mail, credentials, or provider response bodies.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from uuid import UUID

import acceptance as probe


ROOT = Path(__file__).resolve().parents[2]
GITHUB_API = "https://api.github.com"
MAX_RESPONSE = 262_144
JOB_NAME = "Deploy isolated staging role monitor"
DEPLOY_STEP = "Deploy staging Worker with private destination and provider audit secrets"
CONFIRM = "RUN_STAGING_ROLE_SMTP"
FREEZE = "FREEZE_STAGING_ROLE_DEPLOYS"
MAX_JOB_LOG = 4_194_304
VERSION_LINE = re.compile(
    r"(?:^|\t)(?P<time>\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z) "
    r"Current Version ID: (?P<version>[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\s*$"
)


class GateError(Exception):
    """A fixed label safe to print in an Actions log."""


@dataclass(frozen=True)
class DeployedJob:
    """One successful job and the exact step that emitted a Worker version."""

    started: datetime
    ended: datetime
    job_id: int
    step_started: datetime
    step_ended: datetime


def require(ok: bool, label: str) -> None:
    """Reject unsafe or unverifiable state without rendering it."""

    if not ok:
        raise GateError(label)


def parse_time(value: object, label: str) -> datetime:
    """Parse a provider UTC timestamp without interpolating its raw value."""

    require(isinstance(value, str), label)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise GateError(label) from None
    require(result.tzinfo is not None, label)
    return result.astimezone(timezone.utc)


def github_get(path: str, token: str) -> dict:
    """Read a bounded GitHub Actions object without logging response content."""

    request = urllib.request.Request(
        GITHUB_API + path,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "amail-staging-role-acceptance",
        },
    )
    try:
        with _NO_REDIRECT.open(request, timeout=30) as response:
            status, raw = response.status, response.read(MAX_RESPONSE + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        raise GateError("github_read_unavailable") from None
    require(status == 200 and len(raw) <= MAX_RESPONSE, "github_read_unavailable")
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise GateError("github_read_invalid") from None
    require(isinstance(value, dict), "github_read_invalid")
    return value


def successful_deploy_job(repo: str, run_id: int, token: str, branch: str) -> DeployedJob:
    """Identify the successful staging job and its exact deploy step."""

    run = github_get(f"/repos/{repo}/actions/runs/{run_id}", token)
    require(run.get("conclusion") == "success" and run.get("status") == "completed", "deploy_run_not_successful")
    require(run.get("head_branch") == branch and run.get("event") in ("push", "workflow_dispatch"),
            "deploy_run_wrong_branch")
    # GitHub returns a bare path for some completed runs and a path@ref for
    # others; compare the path component, never an arbitrary prefix.
    require(isinstance(run.get("path"), str)
            and run["path"].split("@", 1)[0] == ".github/workflows/ci.yml",
            "deploy_run_wrong_workflow")
    sha = run.get("head_sha")
    require(isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha) is not None,
            "deploy_run_sha_invalid")
    jobs = github_get(f"/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100", token)
    listed = jobs.get("jobs")
    require(isinstance(listed, list) and jobs.get("total_count") == len(listed), "deploy_jobs_incomplete")
    matched = [job for job in listed if isinstance(job, dict) and job.get("name") == JOB_NAME]
    require(len(matched) == 1 and matched[0].get("head_sha") == sha
            and matched[0].get("status") == "completed"
            and matched[0].get("conclusion") == "success", "deploy_job_not_successful")
    started = parse_time(matched[0].get("started_at"), "deploy_job_time_invalid")
    ended = parse_time(matched[0].get("completed_at"), "deploy_job_time_invalid")
    require(started <= ended, "deploy_job_time_invalid")
    job_id = matched[0].get("id")
    require(type(job_id) is int and job_id > 0, "deploy_job_id_invalid")
    steps = matched[0].get("steps")
    require(isinstance(steps, list), "deploy_step_unavailable")
    selected = [step for step in steps if isinstance(step, dict) and step.get("name") == DEPLOY_STEP]
    require(len(selected) == 1 and selected[0].get("conclusion") == "success",
            "deploy_step_not_successful")
    step_started = parse_time(selected[0].get("started_at"), "deploy_step_time_invalid")
    step_ended = parse_time(selected[0].get("completed_at"), "deploy_step_time_invalid")
    require(started <= step_started <= step_ended <= ended, "deploy_step_time_invalid")
    return DeployedJob(started, ended, job_id, step_started, step_ended)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Keep GitHub bearer tokens off every redirect target."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        """Return the 302 to the caller for a tokenless second request."""

        return None


_NO_REDIRECT = urllib.request.build_opener(NoRedirect)


def github_job_log(repo: str, job_id: int, token: str) -> str:
    """Privately read one bounded job log; never persist or print its content."""

    request = urllib.request.Request(
        f"{GITHUB_API}/repos/{repo}/actions/jobs/{job_id}/logs",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "amail-staging-role-acceptance",
        },
    )
    try:
        _NO_REDIRECT.open(request, timeout=30)
    except urllib.error.HTTPError as error:
        require(error.code == 302, "deploy_log_unavailable")
        location = error.headers.get("Location", "")
    except (urllib.error.URLError, TimeoutError):
        raise GateError("deploy_log_unavailable") from None
    else:
        raise GateError("deploy_log_redirect_missing")
    target = urllib.parse.urlparse(location)
    host = target.hostname or ""
    require(target.scheme == "https" and not target.username and not target.password
            and (host.endswith(".actions.githubusercontent.com")
                 or host.endswith(".blob.core.windows.net")), "deploy_log_redirect_invalid")
    try:
        with urllib.request.urlopen(urllib.request.Request(location), timeout=30) as response:
            status, raw = response.status, response.read(MAX_JOB_LOG + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        raise GateError("deploy_log_unavailable") from None
    require(status == 200 and len(raw) <= MAX_JOB_LOG, "deploy_log_unavailable")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise GateError("deploy_log_invalid") from None


def logged_version(repo: str, job: DeployedJob, token: str) -> str:
    """Extract exactly one version line emitted during the deploy step only."""

    candidates: list[str] = []
    for line in github_job_log(repo, job.job_id, token).splitlines():
        match = VERSION_LINE.search(line)
        if match is None:
            continue
        emitted = parse_time(match.group("time"), "deploy_log_time_invalid")
        # Actions step API times are second-resolution while log lines include
        # fractions; a terminal line at 00.839 belongs to a step ending 00Z.
        if job.step_started - timedelta(seconds=1) <= emitted <= job.step_ended + timedelta(seconds=1):
            candidates.append(match.group("version"))
    require(len(candidates) == 1 and valid_uuid(candidates[0]), "deploy_log_version_ambiguous")
    return candidates[0]


def active_version(account: str, token: str) -> tuple[str, datetime]:
    """Read the single latest 100%-serving staging Worker version."""

    path = f"/accounts/{account}/workers/scripts/amail-role-monitor-staging/deployments?per_page=1"
    try:
        value = probe.AUDIT.api_get(path, token)
    except Exception:
        raise GateError("worker_deployment_unavailable") from None
    require(isinstance(value, dict) and isinstance(value.get("deployments"), list)
            and len(value["deployments"]) == 1, "worker_deployment_invalid")
    deployment = value["deployments"][0]
    require(isinstance(deployment, dict) and isinstance(deployment.get("versions"), list)
            and len(deployment["versions"]) == 1, "worker_deployment_invalid")
    version = deployment["versions"][0]
    require(isinstance(version, dict) and version.get("percentage") == 100,
            "worker_version_not_full_traffic")
    version_id = version.get("version_id")
    require(isinstance(version_id, str) and valid_uuid(version_id), "worker_version_invalid")
    return version_id, parse_time(deployment.get("created_on"), "worker_deployment_time_invalid")


def valid_uuid(value: str) -> bool:
    """Require a canonical provider UUID before embedding it in a comparison."""

    try:
        return str(UUID(value)) == value.lower()
    except ValueError:
        return False


def gates() -> tuple[str, str, str, str]:
    """Verify explicit operator action, proven CI deployment, and privacy readback."""

    require(os.environ.get("AMAIL_STAGING_ROLE_CONFIRM") == CONFIRM, "confirmation_required")
    require(os.environ.get("AMAIL_STAGING_ROLE_FREEZE") == FREEZE, "external_freeze_not_attested")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    branch = os.environ.get("GITHUB_REF_NAME", "")
    require(repo == "kleedaisuki/moesegfault-amail"
            and branch in ("main", "codex/amail-v0.1.0"), "github_context_invalid")
    raw_run = os.environ.get("AMAIL_STAGING_ROLE_DEPLOY_RUN", "")
    require(re.fullmatch(r"[1-9][0-9]{0,19}", raw_run) is not None, "deploy_run_id_invalid")
    expected = os.environ.get("AMAIL_STAGING_ROLE_VERSION", "").lower()
    require(valid_uuid(expected), "expected_version_invalid")
    gh_token = os.environ.get("GITHUB_TOKEN", "")
    require(bool(gh_token), "github_credential_unavailable")
    try:
        zone, routing, account = probe.credentials(send=True)
    except Exception:
        raise GateError("provider_credentials_unavailable") from None
    job = successful_deploy_job(repo, int(raw_run), gh_token, branch)
    emitted_version = logged_version(repo, job, gh_token)
    require(emitted_version == expected, "deploy_log_version_not_expected")
    version, created = active_version(account, os.environ["CLOUDFLARE_API_TOKEN"])
    require(version == expected, "worker_version_not_expected")
    require(job.started - timedelta(minutes=2) <= created <= job.ended + timedelta(minutes=2),
            "worker_deployment_not_from_successful_job")
    try:
        probe.preflight(zone, routing, account)
    except Exception:
        raise GateError("private_worker_or_route_preflight_failed") from None
    return zone, routing, account, expected


def main() -> int:
    """Run once and classify cleanup/version drift without unsafe auto-recovery."""

    try:
        zone, routing, account, expected = gates()
    except GateError as error:
        print(f"role_probe=blocked; stage={error}", file=sys.stderr)
        return 1
    print("role_probe_gates=passed; deployed_version=pinned; external_freeze=attested", flush=True)
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "workers/role-monitor/acceptance.py"), "--confirm-staging-smtp"],
            cwd=ROOT,
            check=False,
        )
        harness_ok = result.returncode == 0
    except OSError:
        harness_ok = False
    marker = probe.MARKER.exists()
    try:
        route = probe.ROUTE.reconcile(zone, routing, "audit")
    except Exception:
        route = "unavailable"
    try:
        current, _ = active_version(account, os.environ["CLOUDFLARE_API_TOKEN"])
        version_stable = current == expected
    except GateError:
        version_stable = False
    if marker or route != "absent":
        print("role_probe=failed; stage=route_recovery_required; "
              "freeze_staging_deploys=keep_until_restricted_exact_rule_readback", file=sys.stderr)
        return 1
    if not version_stable:
        print("role_probe=failed; stage=worker_version_drift", file=sys.stderr)
        return 1
    if not harness_ok:
        print("role_probe=failed; stage=acceptance_harness_failed; route=absent", file=sys.stderr)
        return 1
    print("role_probe=machine_d1_only; route=absent; worker_version=stable; "
          "cron_past_events=not_checked; provider_delivery=not_checked; external_inbox=not_checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
