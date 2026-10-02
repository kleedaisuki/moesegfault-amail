"""Replace the existing staging Mail graph without touching production resources.

Legacy cutover combines a continuously pinned fetch-only API/empty Cron, the
documented provider propagation/invocation limits, and lease-fence readback.
Elapsed time alone is never admission. Pending work is retained, not drained or
deleted. A normal already-split replacement preserves its existing cadence.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import tomllib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "crates/mail-worker"))
sys.path.insert(0, str(ROOT / "infra/operator"))
import check_observability as capture
import check_mail_split_graph as graph
from check_mail_maintenance import CADENCE, maintenance_config, verify as verify_maintenance
from direct_contact_health import DatabaseClient, one_row
from inspect_staging import inspect
from pin_staging_mail import containment_bindings_match, serving_deployment, run as pin_api
from tested_worker_artifact import require_artifact
from worker_deploy_result import DeploymentFailure, submit

BRANCH = "refs/heads/codex/v0.1.2-agent-first-performance"
CONFIRM = "RUN_STAGING_V012"
INSPECT_CONFIRM = "INSPECT_STAGING_V012"
# Closed diagnostic vocabulary: arbitrary exception/provider text never escapes.
FAILURES = frozenset({
    "staging_context_unverified", "staging_api_privacy_unverified", "staging_legacy_graph_unverified",
    "staging_split_predecessor_unverified", "staging_old_invocation_bound_unverified",
    "staging_predecessor_unverified", "staging_predecessor_changed", "staging_predecessor_schedule_changed",
    "staging_cutover_api_changed", "staging_maintenance_secrets_missing", "staging_inspect_resume_unverified",
    "staging_resume_tree_unverified", "staging_resume_checkout_unverified", "staging_resume_runtime_changed",
    "staging_resume_unreviewed_change", "staging_resume_dirty_tracked_tree", "staging_resume_origin_unverified",
    "staging_resume_job_boundary_unverified", "staging_resume_sink_submit_unverified", "staging_resume_log_unverified",
    "staging_resume_typed_submit_unverified", "staging_resume_predecessor_unverified",
    "staging_resume_legacy_api_unverified", "staging_resume_preexisting_resource",
    "staging_resume_queue_ownership_unverified", "staging_resume_artifact_unverified",
    "staging_resume_run_unreviewed", "staging_resume_log_download_failed",
    "staging_resume_log_credentials_unverified", "staging_resume_log_redirect_unverified",
    "staging_resume_log_permission_denied", "staging_resume_log_http_unverified",
    "staging_resume_log_transport_unverified", "staging_resume_log_signed_url_expired",
    "staging_resume_source_unreviewed", "staging_resume_phase_step_unverified",
    "staging_resume_active_submits_unverified", "staging_resume_cutover_witness_unverified",
    "staging_resume_cutover_leases_unverified",
    "staging_resume_old_api_changed", "staging_resume_partial_graph_unverified", "staging_resume_phase_changed",
})
PREDECESSOR = ROOT / ".temp/staging-rollout-predecessor.json"
WITNESS = ROOT / ".temp/staging-cutover.json"
PROPAGATION_SECONDS = 15 * 60
INVOCATION_SECONDS = 15 * 60
MARGIN_SECONDS = 60
WINDOW_SECONDS = PROPAGATION_SECONDS + INVOCATION_SECONDS + MARGIN_SECONDS
API = "amail-mail-staging"
MAINTENANCE = "amail-mail-maintenance-staging"


def context(*, read_only: bool = False) -> None:
    """Require the fixed hosted branch, confirmation and realm before any mutation."""
    confirmed = (os.getenv("AMAIL_STAGING_INSPECT_CONFIRM") == INSPECT_CONFIRM if read_only
                 else os.getenv("AMAIL_STAGING_DEPLOY_CONFIRM") == CONFIRM)
    if (os.getenv("GITHUB_REF") != BRANCH or os.getenv("GITHUB_ACTIONS") != "true"
            or not confirmed or not os.getenv("GITHUB_OUTPUT")):
        raise ValueError("staging_context_unverified")
    if read_only and os.getenv("AMAIL_STAGING_RESUME_RUN") not in ("37053907751", "37058617870"):
        raise ValueError("staging_inspect_resume_unverified")


def write(path: Path, value: dict) -> None:
    """Persist public infrastructure coordinates only inside repository scratch."""
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def predecessor() -> dict:
    """Read only the successful same-run snapshot, never an arbitrary caller receipt."""
    value = json.loads(PREDECESSOR.read_text(encoding="utf-8"))
    if (value.get("source_sha") != os.getenv("GITHUB_SHA")
            or value.get("run_id") != os.getenv("GITHUB_RUN_ID")
            or value.get("rollout") not in ("legacy", "split")):
        raise ValueError("staging_predecessor_unverified")
    return value


def preflight(*, read_only: bool = False) -> None:
    """Admit either the exact historical predecessor or the current active split."""
    # This function has no provider writes; inspection confirmation never grants
    # entry to before_api(), cutover() or either deployment submit path.
    context(read_only=read_only)
    names = ("AMAIL_TRACE_QUEUE_ID", "AMAIL_TRACE_DLQ_ID", "AMAIL_TRACE_TOPOLOGY",
             "AMAIL_EXPECTED_TRACE_SINK_VERSION", "AMAIL_EXPECTED_WORKER_VERSION",
             "AMAIL_EXPECTED_MAINTENANCE_VERSION")
    reviewed = {name: os.getenv(name) for name in names}
    try:
        value = inspect()
    finally:
        # Diagnostic observed IDs must not silently replace reviewed ownership
        # pins in normal split admission. A resume binds its own immutable IDs.
        for name, original in reviewed.items():
            if original is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = original
    api = value["scripts"][API]
    maintenance = value["scripts"][MAINTENANCE]
    if not api.get("capture_off"):
        raise ValueError("staging_api_privacy_unverified")
    account, token = os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"]
    legacy = api["handlers"] == ["fetch", "scheduled"] and api["crons"] == list(CADENCE)
    if legacy:
        # Select the frozen source-provenance contract, not arbitrary mixed code.
        version = capture.readback(account, token, API, f"versions/{api['version']}")
        usage = bounded_usage_model(version)
        # Grandfathered Bundled Workers have no duration bound. Missing metadata
        # is not proof of the modern bound and must stop before the first write.
        value["old_usage_model"] = usage
        if not containment_bindings_match(version, api["version"]) or maintenance["present"]:
            raise ValueError("staging_legacy_graph_unverified")
        resume = os.getenv("AMAIL_STAGING_RESUME_RUN", "")
        if resume:
            from staging_resume import load_resume
            owned = load_resume(resume)
            original = owned["predecessor"]
            if any(value["scripts"][name] != original["scripts"][name] for name in
                   (API, "amail-inbound-staging", "amail-events-staging")):
                raise ValueError("staging_resume_old_api_changed")
            sink = value["scripts"]["amail-trace-sink-staging"]
            checks = value.get("sink_checks", {})
            if (checks.get("topology_checked") != "api-only"
                    or any(checks.get(name) is not True for name in
                           ("immutable_capabilities", "retained_settings", "private_surfaces", "queue_trigger"))
                    or not sink.get("present") or sink.get("version") != owned["sink_version"]
                    or sink.get("deployment") != "73892f24-1e84-406a-b025-3879580597e1"
                    or sink.get("privacy_safe") is not True or sink.get("handlers") != ["queue"] or sink.get("crons")
                    or value["queues"]["amail-trace-events-staging"].get("queue_id") != owned["queue"]
                    or value["queues"]["amail-trace-dlq-staging"].get("queue_id") != owned["dlq"]
                    or any(row.get("producers") != [] or row.get("bounded_retention") is not True
                           for row in value["queues"].values())):
                raise ValueError("staging_resume_partial_graph_unverified")
            # The immutable old snapshot remains provenance. Current orchestration
            # has its own source/run identity and never borrows an artifact epoch.
            value["resume_origin_run"] = resume
            output("reuse_sink", "true")
            output("queue_id", owned["queue"])
            output("dlq_id", owned["dlq"])
            output("sink_version", owned["sink_version"])
        elif (value["scripts"]["amail-trace-sink-staging"]["present"]
                or any(row["present"] for row in value["queues"].values())):
            raise ValueError("staging_legacy_graph_unverified")
        graph.held_send("staging")
        value["rollout"] = "legacy"
    else:
        if (api["handlers"] != ["fetch"] or api["crons"]
                or not maintenance["present"] or maintenance["crons"] != list(CADENCE)):
            raise ValueError("staging_split_predecessor_unverified")
        resume = os.getenv("AMAIL_STAGING_RESUME_RUN", "")
        if resume:
            from staging_resume import load_resume
            owned = load_resume(resume)
            if (any(value["scripts"][name] != owned["predecessor"]["scripts"][name]
                    for name in ("amail-inbound-staging", "amail-events-staging"))
                    or owned.get("phase") != "active" or api["version"] != owned["api_version"]
                    or api["deployment"] != "7c6c70e5-d617-4119-9dff-846f5f204a3c"
                    or maintenance["version"] != owned["maintenance_version"]
                    or maintenance["deployment"] != "ad083bc6-e1c0-4ee6-81af-d19c4261ec50"
                    or value["scripts"]["amail-trace-sink-staging"]["version"] != owned["sink_version"]
                    or value["scripts"]["amail-trace-sink-staging"]["deployment"] != "73892f24-1e84-406a-b025-3879580597e1"
                    or value["queues"]["amail-trace-events-staging"]["queue_id"] != owned["queue"]
                    or value["queues"]["amail-trace-dlq-staging"]["queue_id"] != owned["dlq"]):
                raise ValueError("staging_resume_partial_graph_unverified")
            os.environ.update({"AMAIL_TRACE_QUEUE_ID": owned["queue"], "AMAIL_TRACE_DLQ_ID": owned["dlq"]})
            value["resume_origin_run"] = resume
        os.environ.update({"AMAIL_EXPECTED_WORKER_VERSION": api["version"],
                           "AMAIL_EXPECTED_MAINTENANCE_VERSION": maintenance["version"],
                           "AMAIL_EXPECTED_TRACE_SINK_VERSION": value["scripts"]["amail-trace-sink-staging"]["version"],
                           "AMAIL_TRACE_TOPOLOGY": "api-scheduled"})
        graph.verify("staging", "active")
        if resume:
            output("reuse_sink", "true")
            output("reuse_api", "true")
            for key in ("api_version", "maintenance_version", "sink_version"):
                output(key, owned[key])
            output("queue_id", owned["queue"])
            output("dlq_id", owned["dlq"])
        value["rollout"] = "split"
    write(PREDECESSOR, value)
    output("rollout", value["rollout"])


def bounded_usage_model(version: dict) -> str:
    """Select the immutable runtime model; mutable settings cannot override it.

    Cloudflare's version schema places this under resources.script_runtime,
    separate from script handlers. Grandfathered Bundled Workers have no wall
    bound and missing metadata is not proof of Standard/Unbound execution.
    """
    usage = version.get("resources", {}).get("script_runtime", {}).get("usage_model")
    if usage not in ("standard", "unbound"):
        raise ValueError("staging_old_invocation_bound_unverified")
    return usage


def output(key: str, value: str) -> None:
    """Only helper-owned labels and provider UUIDs reach GitHub step outputs."""
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as destination:
        destination.write(f"{key}={value}\n")


def before_api() -> None:
    """Recheck the unchanged predecessor API immediately before schema/code writes."""
    context()
    value = predecessor()
    expected = value["scripts"][API]
    account, token = os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"]
    current = serving_deployment(capture.readback(account, token, API, "deployments?per_page=1&page=1"))
    if current != (expected["deployment"], expected["version"]):
        raise ValueError("staging_predecessor_changed")
    from check_mail_maintenance import schedules_match
    if not schedules_match(capture.readback(account, token, API, "schedules"), tuple(expected["crons"])):
        raise ValueError("staging_predecessor_schedule_changed")
    graph.held_send("staging")


def deploy_maintenance(active: bool) -> str:
    """Submit one private scheduled-only copy of the tested Mail artifact."""
    context()
    require_artifact("mail_api")
    maintenance_config("staging", active=True)
    names = ("OPENROUTER_API_KEY", "CF_EMAIL_ROUTING_TOKEN")
    secrets = {name: os.getenv(name, "") for name in names}
    if not all(secrets.values()):
        raise ValueError("staging_maintenance_secrets_missing")
    source = (ROOT / "crates/mail-worker/wrangler-maintenance.toml").read_text(encoding="utf-8")
    if not active:
        start = source.index("[env.staging.triggers]")
        before, after = source[:start], source[start:]
        after = after.replace('crons = ["*/5 * * * *"]', "crons = []", 1)
        source = before + after
    source = source.replace('main = "entry/maintenance.mjs"',
                            'main = "' + (ROOT / "crates/mail-worker/entry/maintenance.mjs").as_posix() + '"', 1)
    with tempfile.TemporaryDirectory(prefix="staging-maintenance-", dir=ROOT / ".temp") as folder:
        folder = Path(folder)
        config, secret = folder / "wrangler.toml", folder / "secrets.json"
        config.write_text(source, encoding="utf-8")
        secret.write_text(json.dumps(secrets), encoding="utf-8")
        secret.chmod(0o600)
        try:
            version = submit(["wrangler", "deploy", "--env", "staging", "--config", str(config),
                              "--secrets-file", str(secret)], "staging", "mail_api", cwd=ROOT / "crates/mail-worker")
        except DeploymentFailure as error:
            if error.version:
                output("maintenance_version", error.version)
            raise
    output("maintenance_version", version)
    verify_maintenance("staging", "active" if active else "paused",
                       os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"], version,
                       os.environ["AMAIL_TRACE_QUEUE_ID"])
    return version


def lease_fences() -> dict:
    """Observe execution leases only; a nonempty pending backlog is legitimate."""
    database = DatabaseClient(os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"], "staging")
    row = one_row(database.query("""SELECT
      (SELECT COUNT(*) FROM embedding_work WHERE lease_until>unixepoch()*1000) AS embedding_leases,
      (SELECT COUNT(*) FROM send_requests WHERE index_projection_lease_until>unixepoch()*1000) AS projection_leases
    """))
    if any(type(row.get(name)) is not int or row[name] < 0 for name in ("embedding_leases", "projection_leases")):
        raise ValueError("staging_lease_fences_unverified")
    return row


def cutover() -> None:
    """Bound the old scheduled cohort with stable provider capabilities and fences."""
    context()
    value = predecessor()
    if value["rollout"] == "split":
        deploy_maintenance(True)
        return
    version = deploy_maintenance(False)
    os.environ["AMAIL_EXPECTED_MAINTENANCE_VERSION"] = version
    os.environ["AMAIL_TRACE_TOPOLOGY"] = "api-scheduled"
    expected = os.environ["AMAIL_EXPECTED_WORKER_VERSION"]
    account, token = os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"]
    started = time.monotonic()
    samples = 0
    while True:
        # The new API cannot receive Cron dispatch; the old cohort cannot extend
        # beyond propagation + invocation wall limits. Re-pinning aborts on drift.
        if pin_api(account, token, expected, phase="queue-api", queue_id=os.environ["AMAIL_TRACE_QUEUE_ID"]) != "match":
            raise ValueError("staging_cutover_api_changed")
        verify_maintenance("staging", "paused", account, token, version, os.environ["AMAIL_TRACE_QUEUE_ID"])
        graph.held_send("staging")
        samples += 1
        elapsed = time.monotonic() - started
        if elapsed >= WINDOW_SECONDS:
            break
        time.sleep(min(60, WINDOW_SECONDS - elapsed))
    # Leases may still represent foreground projection, so preserve them rather
    # than clearing/stealing. Their opaque tokens are the normal runtime fence.
    fences = lease_fences()
    write(WITNESS, {"schema": "staging-platform-cutover/v1", "source_sha": os.getenv("GITHUB_SHA"),
                   "run_id": os.getenv("GITHUB_RUN_ID"), "old_api_version": value["scripts"][API]["version"],
                   "api_version": expected, "paused_maintenance_version": version,
                   "old_usage_model": value["old_usage_model"],
                   "propagation_limit_seconds": PROPAGATION_SECONDS,
                   "invocation_limit_seconds": INVOCATION_SECONDS,
                   "observed_monotonic_seconds": elapsed, "pin_samples": samples,
                   "execution_leases_preserved": fences})
    deploy_maintenance(True)


def main() -> int:
    """One closed phase; failures do not retry a submit or authorize recovery."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("preflight", "inspect-preflight", "before-api", "cutover"))
    args = parser.parse_args()
    try:
        if args.phase == "inspect-preflight":
            preflight(read_only=True)
        else:
            {"preflight": preflight, "before-api": before_api, "cutover": cutover}[args.phase]()
    except Exception as error:
        reason = str(error) if isinstance(error, ValueError) and str(error) in FAILURES else "unknown"
        print(f"staging_rollout_{args.phase}=UNVERIFIED reason={reason}")
        return 1
    print(f"staging_rollout_{args.phase}=verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
