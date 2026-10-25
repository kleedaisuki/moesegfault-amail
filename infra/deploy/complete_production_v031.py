"""Read-only completion of one named rollout whose final health type check failed.

The original controller completed its mutations and preservation checks before
checking public health. Its API contract returns api_version as the string "2";
the original checker incorrectly required integer 2. This adapter never deploys,
migrates, changes schedules, repeats the completed Cron boundary, or relabels the
failed original workflow as successful.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

import production_v031 as deploy
from staging_resume import job_log

ROOT = deploy.ROOT
sys.path.insert(0, str(ROOT / "infra/ci"))
import accepted_staging_artifact as accepted

ORIGIN_RUN = "40196627612"
ORIGIN_SOURCE = "b4c34664bfc59bd2c6611c5507f5e7b73784a93b"
INSPECTION_RUN = "40196506986"
WRITER = "Upgrade exact production graph to consent-gated v0.3.1"
WRITE_STEP = "Replace sink and fail-closed API pause maintenance migrate and resume"
FAILURE = "production_v031_health_unverified"
FOLDER = ROOT / ".temp/v031-completion"
ADMISSION = FOLDER / "admission.json"
PARTIAL = FOLDER / "partial/production-upgrade-partial.jsonl"
INSPECTION = FOLDER / "inspection/production-v031.json"
RECEIPT = ROOT / ".temp/production-v031-completion.json"
FAILURES = frozenset({"production_v031_completion_context_unverified",
                     "production_v031_completion_origin_unverified",
                     "production_v031_completion_failure_unverified",
                     "production_v031_completion_journal_unverified",
                     "production_v031_completion_inspection_unverified",
                     "production_v031_completion_policy_changed",
                     "production_v031_completion_retained_changed",
                     "production_v031_completion_preferences_unverified",
                     "staging_resume_log_credentials_unverified", "staging_resume_log_permission_denied",
                     "staging_resume_log_http_unverified", "staging_resume_log_redirect_unverified",
                     "staging_resume_log_transport_unverified", "staging_resume_log_signed_url_expired",
                     "staging_resume_log_unverified"})


def context() -> None:
    expected = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": accepted.REPO,
                "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch",
                "GITHUB_RUN_ATTEMPT": "1", "AMAIL_PRODUCTION_ENVIRONMENT": "production",
                "AMAIL_PRODUCTION_CONFIRM": "COMPLETE_PRODUCTION_V031",
                "AMAIL_PRODUCTION_GRAPH_FREEZE": "FREEZE_PRODUCTION_GRAPH_WRITERS",
                "AMAIL_PRODUCTION_COMPLETION_RUN": ORIGIN_RUN}
    if (any(os.getenv(key) != value for key, value in expected.items())
            or re.fullmatch(r"[0-9a-f]{40}", os.getenv("GITHUB_SHA", "")) is None
            or re.fullmatch(r"[1-9][0-9]{0,19}", os.getenv("GITHUB_RUN_ID", "")) is None):
        raise ValueError("production_v031_completion_context_unverified")
    accepted.runtime_closure(ORIGIN_SOURCE, os.environ["GITHUB_SHA"])


def run_identity(value: dict[str, Any], run_id: str, conclusion: str) -> None:
    if (type(value.get("id")) is not int or str(value["id"]) != run_id
            or value.get("head_sha") != ORIGIN_SOURCE or value.get("head_branch") != "main"
            or value.get("repository", {}).get("full_name") != accepted.REPO
            or value.get("path") != ".github/workflows/ci.yml" or value.get("event") != "workflow_dispatch"
            or value.get("status") != "completed" or value.get("conclusion") != conclusion
            or type(value.get("run_attempt")) is not int or value["run_attempt"] != 1):
        raise ValueError("production_v031_completion_origin_unverified")


def writer_identity(jobs: list[dict[str, Any]]) -> int:
    failed = [row for row in jobs if row.get("conclusion") == "failure"]
    if (len(failed) != 1 or failed[0].get("name") != WRITER
            or type(failed[0].get("id")) is not int or failed[0]["id"] <= 0
            or any(row.get("status") != "completed" or row.get("conclusion") not in ("success", "failure", "skipped") for row in jobs)):
        raise ValueError("production_v031_completion_failure_unverified")
    steps = failed[0].get("steps")
    if (not isinstance(steps, list)
            or [step.get("name") for step in steps if step.get("conclusion") == "failure"] != [WRITE_STEP]):
        raise ValueError("production_v031_completion_failure_unverified")
    return failed[0]["id"]


def closed_failure(log: str) -> None:
    found = re.findall(r"production_v031=UNVERIFIED reason=([a-z0-9_]+) class=([A-Za-z]+)", log)
    if found != [(FAILURE, "ValueError")]:
        raise ValueError("production_v031_completion_failure_unverified")


def prepare() -> None:
    """Admit only the completed named failure and exact successful pre-inspection."""
    context()
    run_identity(accepted.github(f"runs/{ORIGIN_RUN}"), ORIGIN_RUN, "failure")
    jobs = accepted.rows(accepted.github(f"runs/{ORIGIN_RUN}/jobs?per_page=100"), "jobs")
    job_id = writer_identity(jobs)
    # The existing reader validates the signed blob redirect and never forwards
    # the GitHub API bearer to the log-storage host.
    closed_failure(job_log(job_id).decode("utf-8-sig"))
    run_identity(accepted.github(f"runs/{INSPECTION_RUN}"), INSPECTION_RUN, "success")
    partial_id = accepted.unique_artifact(ORIGIN_RUN, ORIGIN_SOURCE, f"production-v031-partial-{ORIGIN_RUN}")
    inspection_id = accepted.unique_artifact(INSPECTION_RUN, ORIGIN_SOURCE, f"production-v031-inspect-{INSPECTION_RUN}")
    value = {"schema": "production-v031-completion-admission/v1", "origin_run": ORIGIN_RUN,
             "origin_source": ORIGIN_SOURCE, "origin_job": job_id, "partial_artifact_id": partial_id,
             "inspection_run": INSPECTION_RUN, "inspection_artifact_id": inspection_id,
             "completion_run": os.environ["GITHUB_RUN_ID"], "completion_source": os.environ["GITHUB_SHA"]}
    FOLDER.mkdir(parents=True, exist_ok=True)
    with ADMISSION.open("x", encoding="utf-8") as file:
        json.dump(value, file, sort_keys=True)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"origin_run={ORIGIN_RUN}\npartial_artifact_id={partial_id}\n"
                     f"inspection_run={INSPECTION_RUN}\ninspection_artifact_id={inspection_id}\n")


def journal(text: str) -> dict[str, str]:
    """A single ordered original control flow proves completed prerequisite checks."""
    if len(text.encode()) > 262_144:
        raise ValueError("production_v031_completion_journal_unverified")
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    expected = [(role, state) for role in ("sink", "api", "maintenance_pause", "migration", "maintenance")
                for state in ("intent", "observed" if role == "migration" else "version_captured")]
    if len(rows) != len(expected):
        raise ValueError("production_v031_completion_journal_unverified")
    versions: dict[str, str] = {}
    base = {"schema", "source_sha", "run_id", "run_attempt", "phase", "state"}
    for row, (phase, state) in zip(rows, expected, strict=True):
        fields = base | ({"version"} if state == "version_captured" else set())
        if (not isinstance(row, dict) or set(row) != fields
                or row.get("schema") != "production-upgrade-partial/v1"
                or row.get("source_sha") != ORIGIN_SOURCE or row.get("run_id") != ORIGIN_RUN
                or type(row.get("run_attempt")) is not int or row["run_attempt"] != 1
                or row.get("phase") != phase or row.get("state") != state):
            raise ValueError("production_v031_completion_journal_unverified")
        if state == "version_captured":
            if not isinstance(row.get("version"), str) or deploy.legacy.UUID.fullmatch(row["version"]) is None:
                raise ValueError("production_v031_completion_journal_unverified")
            versions[phase] = row["version"]
    if len(set(versions.values())) != 4:
        raise ValueError("production_v031_completion_journal_unverified")
    return versions


def inspection(value: dict[str, Any]) -> None:
    if (value.get("schema") != "production-v031/v1" or value.get("run_id") != INSPECTION_RUN
            or value.get("source_sha") != ORIGIN_SOURCE or value.get("schema_migration_applied") is not False
            or value.get("graph", {}).get("pins") != {key: list(pin) for key, pin in deploy.PINS.items()}
            or value.get("policy_state") not in ("allowed", "held")
            or any(not isinstance(value.get(key), str) or re.fullmatch(r"[0-9a-f]{64}", value[key]) is None
                   for key in ("policy_fingerprint", "retained_fingerprint"))):
        raise ValueError("production_v031_completion_inspection_unverified")


def complete() -> None:
    """Read existing state only; no provider writer, schedule wait, retry or rollback."""
    context()
    admission = json.loads(ADMISSION.read_text(encoding="utf-8"))
    if (admission.get("origin_run") != ORIGIN_RUN or admission.get("origin_source") != ORIGIN_SOURCE
            or admission.get("completion_run") != os.environ["GITHUB_RUN_ID"]
            or admission.get("completion_source") != os.environ["GITHUB_SHA"]):
        raise ValueError("production_v031_completion_origin_unverified")
    versions = journal(PARTIAL.read_text(encoding="utf-8"))
    before = json.loads(INSPECTION.read_text(encoding="utf-8"))
    inspection(before)
    deploy.unchanged_adapters()
    deploy.prior.retained.check_configs(deploy.prior.SCOPE)
    provider = deploy.FreshProvider(os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"])
    deploy.prior.readback.complete(provider, f"accounts/{provider.account}/queues", "queue_id", 100)
    pins = {"amail-mail": (None, versions["api"]),
            "amail-mail-maintenance": (None, versions["maintenance"]),
            "amail-trace-sink": (None, versions["sink"])}
    result, policy, anchors = deploy.observe(provider, pins)
    if deploy.prior.digest(policy) != before["policy_fingerprint"]:
        raise ValueError("production_v031_completion_policy_changed")
    if deploy.prior.digest(anchors) != before["retained_fingerprint"]:
        raise ValueError("production_v031_completion_retained_changed")
    deploy.recorded_schema(provider, 18)
    enabled = deploy.database(provider).query("SELECT COUNT(*) AS enabled FROM semantic_preferences WHERE enabled=1").get("results")
    if enabled != [{"enabled": 0}]:
        raise ValueError("production_v031_completion_preferences_unverified")
    ownership_count = len(deploy.usd.ownership(provider))
    deploy.health_ready()
    deploy.observe(provider, pins, policy=policy, retained=anchors)
    value = {"schema": "production-v031-completion/v1", "origin_run": ORIGIN_RUN,
             "origin_source": ORIGIN_SOURCE, "origin_workflow_conclusion": "failure",
             "origin_failure": FAILURE, "source_sha": os.environ["GITHUB_SHA"],
             "run_id": os.environ["GITHUB_RUN_ID"], "inspection_run": INSPECTION_RUN,
             **result, "policy_state": policy["state"], "policy_fingerprint": deploy.prior.digest(policy),
             "retained_fingerprint": deploy.prior.digest(anchors), "schema_migration_applied": True,
             "semantic_default_after_upgrade": "disabled", "embedding_model_after_upgrade": "voyageai/voyage-4",
             "quiescence_proof": "original_controller_control_flow",
             "ownership_preservation_proof": "original_controller_control_flow",
             "embedding_preservation_proof": "original_controller_control_flow",
             "live_address_records": ownership_count,
             "origin_journal_sha256": hashlib.sha256(PARTIAL.read_bytes()).hexdigest(),
             "old_http_drain": "NOT_CLAIMED"}
    with RECEIPT.open("x", encoding="utf-8") as file:
        json.dump(value, file, sort_keys=True)
        file.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "complete"))
    args = parser.parse_args()
    try:
        prepare() if args.mode == "prepare" else complete()
    except Exception as error:
        reason = str(error) if isinstance(error, ValueError) and str(error) in FAILURES else "unknown"
        print(f"production_v031_completion=UNVERIFIED reason={reason} class={type(error).__name__}")
        return 1
    print(f"production_v031_completion={args.mode}_verified read_only=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
