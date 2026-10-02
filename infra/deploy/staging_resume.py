"""Recover immutable ownership of three reviewed staging interruption boundaries.

This is provenance admission, not a provider mutation or live graph attestation.
The caller must separately bracket the unchanged legacy API, private exact sink,
phase-specific Queue producers and held sending before continuing with tested bytes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/ci"))
from inbox_worker_artifact import required_jobs, rows
from fresh_bootstrap_recovery import artifact, decode, members
from mail_lifecycle_receipt import github, REPO

ORIGIN_RUN = "37053907751"
ORIGIN_SHA = "b2dbd66d786a5a790dc55486ee27ae578690f0ea"
ACTIVE_RUN = "37058617870"
ACTIVE_SHA = "4732325020ffc7447242a1601d08ebfd8e47d6b2"
ADAPTER_RUN = "37065145834"
ADAPTER_SHA = "4f30e0274827c934feea57b75f8a29a9fbc9b597"
ADAPTER_INGRESS = "09c34d0f-1147-467c-85f0-e7711d96d8fd"
ADAPTER_EVENTS = "63733c7c-6238-4522-be0f-befb5e8c4799"
INGRESS_JOB = "Deploy isolated Rust staging SMTP ingress"
EVENTS_JOB = "Deploy isolated Rust staging lifecycle consumer"
INGRESS_STEP = "Deploy staging Rust Email-event Worker with exact recovery pin"
EVENTS_STEP = "Deploy staging lifecycle consumer with exact recovery pin"
SUBSCRIPTION_STEP = "Ensure staging Email Sending Event Subscription"
ADAPTER_CHECK_STEP = "Read back immutable ingress and lifecycle realm isolation"
ACTIVE_API = "01f14a8e-d5b1-41f9-9f8c-325c2e288ba7"
PAUSED_MAINTENANCE = "bc616834-035f-4bb7-88d6-e29ce1ab5867"
ACTIVE_MAINTENANCE = "3d23d537-6379-4fcb-84c2-2c1b8a9f4857"
API_JOB = "Deploy isolated staging mail API"
API_STEP = "Deploy staging Worker with redacted output and exact recovery version"
CUTOVER_STEP = "Replace scheduled-only maintenance with bounded legacy cutover"
GRAPH_STEP = "Verify exact active API and scheduled-maintenance trace producer graph"
BRANCH = "codex/v0.1.2-agent-first-performance"
API_VERSION = "c3f6401a-1e84-4f51-91df-ae77d90683e9"
API_DEPLOYMENT = "8dc8ba02-5c4f-4c53-b0a9-f04b6a25a5cb"
SINK_VERSION = "be786239-402d-4e72-89c9-0acbe88b0b86"
QUEUE = "fcee510036af42c189e28c0b6ff9508e"
DLQ = "f023f804b7bd4d8691fbfcb60416a001"
SINK_JOB = "Deploy private staging privacy trace sink"
DEPLOY_STEP = "Deploy Queue-only trace consumer without secrets or HTTP route"
SKIPPED = {"Deploy isolated staging mail API", "Deploy isolated Rust staging SMTP ingress",
           "Deploy isolated Rust staging lifecycle consumer", "Deploy isolated staging release site",
           "Deploy private staging Identity verification inbox"}
RUNTIME = ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "rust-toolchain", ".cargo",
           "crates", "workers", "site", "infra/tests/worker-boundary")
BROWSER_HARNESS = "site/scripts/browser-acceptance.mjs"
CONTROL = {".github/workflows/ci.yml", "infra/deploy/staging_rollout.py",
           "infra/deploy/inspect_staging.py", "infra/deploy/staging_resume.py",
           "infra/deploy/check_mail_split_graph.py",
           "infra/deploy/check_staging_adapters.py", "infra/tests/test_staging_adapters.py",
           "infra/release/candidate_site.py", "infra/tests/test_candidate_site_staging.py", BROWSER_HARNESS,
           "infra/tests/staging_owned_send.py", "infra/tests/test_staging_owned_send.py",
           "infra/tests/test_staging_resume.py", "infra/tests/test_staging_rollout.py"}
STATE = ROOT / ".temp/staging-resume.json"
LIMIT = 65_536
LOG_LIMIT = 8 * 1024 * 1024


class NoLogRedirect(HTTPRedirectHandler):
    """Keep the API bearer token out of the separately signed blob request."""

    def redirect_request(self, request, response, code, message, headers, new_url):
        """Reject automatic redirects; the caller validates the single Location."""
        return None


def job_log(job_id: int) -> bytes:
    """Read the reviewed job log with separate authenticated and signed requests.

    GitHub returns a short-lived 302 URL. Only its observed Actions log Azure
    account family is admitted, and the download never carries the API token.
    Neither URL, response body nor transport exception is copied into diagnostics.
    This read does not retry or weaken the unique typed-submit ownership proof.
    """
    token = os.getenv("GH_TOKEN", "")
    if type(job_id) is not int or job_id <= 0 or not token:
        raise ValueError("staging_resume_log_credentials_unverified")
    opener = build_opener(NoLogRedirect())
    request = Request(f"https://api.github.com/repos/{REPO}/actions/jobs/{job_id}/logs",
                      headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                               "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with opener.open(request, timeout=30):
            raise ValueError("staging_resume_log_redirect_unverified")
    except HTTPError as error:
        if error.code in (401, 403):
            error.close()
            raise ValueError("staging_resume_log_permission_denied") from None
        if error.code != 302:
            error.close()
            raise ValueError("staging_resume_log_http_unverified") from None
        location = error.headers.get("Location", "")
        error.close()
    except (URLError, TimeoutError, OSError):
        raise ValueError("staging_resume_log_transport_unverified") from None
    parsed = urlsplit(location)
    if (parsed.scheme != "https" or parsed.username is not None or parsed.password is not None
            or parsed.port not in (None, 443) or parsed.fragment
            or not re.fullmatch(r"productionresultssa[0-9]+\.blob\.core\.windows\.net", parsed.hostname or "")
            or not parsed.path.startswith("/") or not parsed.query):
        raise ValueError("staging_resume_log_redirect_unverified")
    try:
        # No bearer header crosses this boundary; additional redirects fail shut.
        with opener.open(Request(location), timeout=30) as response:
            if response.status != 200:
                raise ValueError("staging_resume_log_http_unverified")
            raw = response.read(LOG_LIMIT + 1)
    except HTTPError as error:
        reason = "staging_resume_log_signed_url_expired" if error.code in (401, 403) else "staging_resume_log_http_unverified"
        error.close()
        raise ValueError(reason) from None
    except (URLError, TimeoutError, OSError):
        raise ValueError("staging_resume_log_transport_unverified") from None
    if not 0 < len(raw) <= LOG_LIMIT:
        raise ValueError("staging_resume_log_unverified")
    return raw


def git(*arguments: str) -> bytes:
    """Read the tracked tree with bounded output; missing history fails closed."""
    result = subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True,
                            timeout=30, check=False)
    if result.returncode or len(result.stdout) > 1_048_576:
        raise ValueError("staging_resume_tree_unverified")
    return result.stdout


def exact_tree(current_sha: str, source_sha: str = ORIGIN_SHA) -> None:
    """Permit only reviewed orchestration/docs/tests changes, never ancestor trust."""
    if (not isinstance(current_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", current_sha)
            or git("rev-parse", "HEAD").decode().strip() != current_sha):
        raise ValueError("staging_resume_checkout_unverified")
    if source_sha not in (ORIGIN_SHA, ACTIVE_SHA, ADAPTER_SHA):
        raise ValueError("staging_resume_source_unreviewed")
    git("cat-file", "-e", source_sha + "^{commit}")
    runtime = git("diff", "--name-only", "-z", source_sha, current_sha, "--", *RUNTIME).decode().split("\0")
    # This exact hosted-only harness imports Node/Playwright and is not bundled
    # into Astro output. No product source, asset or other site script is exempt.
    if any(name and name != BROWSER_HARNESS for name in runtime):
        raise ValueError("staging_resume_runtime_changed")
    changed = git("diff", "--name-only", "-z", source_sha, current_sha).decode().split("\0")
    if any(name and name not in CONTROL and not (name.startswith("docs/") and name.endswith(".md"))
           for name in changed):
        raise ValueError("staging_resume_unreviewed_change")
    if git("diff", "--name-only", "-z", "HEAD"):
        raise ValueError("staging_resume_dirty_tracked_tree")


def origin(run: object, jobs: object, run_id: str) -> dict:
    """Admit only the terminal failed reviewed run at the sink-only boundary."""
    source_sha = {ORIGIN_RUN: ORIGIN_SHA, ACTIVE_RUN: ACTIVE_SHA, ADAPTER_RUN: ADAPTER_SHA}.get(run_id)
    active = run_id == ACTIVE_RUN
    if (run_id not in (ORIGIN_RUN, ACTIVE_RUN, ADAPTER_RUN) or not isinstance(run, dict) or type(run.get("id")) is not int
            or str(run["id"]) != run_id or type(run.get("run_attempt")) is not int
            or run["run_attempt"] != 1 or run.get("status") != "completed"
            or run.get("conclusion") != "failure" or run.get("event") != "workflow_dispatch"
            or run.get("head_branch") != BRANCH or run.get("head_sha") != source_sha
            or run.get("path") != ".github/workflows/ci.yml"
            or not isinstance(run.get("repository"), dict) or run["repository"].get("full_name") != REPO):
        raise ValueError("staging_resume_origin_unverified")
    listing = rows(jobs, "jobs")
    if run_id == ADAPTER_RUN:
        return adapters_origin(listing)
    skipped = SKIPPED - {API_JOB} if active else SKIPPED
    for name in required_jobs(listing) | skipped | {SINK_JOB} | ({API_JOB} if active else set()):
        matches = [row for row in listing if row.get("name") == name]
        failed = API_JOB if active else SINK_JOB
        expected = "skipped" if name in skipped else "failure" if name == failed else "success"
        if (len(matches) != 1 or matches[0].get("status") != "completed"
                or matches[0].get("conclusion") != expected):
            raise ValueError("staging_resume_job_boundary_unverified")
    selected_job = API_JOB if active else SINK_JOB
    sink = next(row for row in listing if row["name"] == selected_job)
    if active:
        require_step(sink, CUTOVER_STEP, "success")
        require_step(sink, GRAPH_STEP, "failure")
        sink_row = next(row for row in listing if row["name"] == SINK_JOB)
        require_step(sink_row, DEPLOY_STEP, "skipped")
    deploy_step = API_STEP if active else DEPLOY_STEP
    steps = sink.get("steps")
    matches = [row for row in steps if isinstance(row, dict) and row.get("name") == deploy_step] if isinstance(steps, list) else []
    if (len(matches) != 1 or matches[0].get("status") != "completed"
            or matches[0].get("conclusion") != "success" or type(sink.get("id")) is not int
            or sink["id"] <= 0 or sink.get("run_id") != int(run_id) or sink.get("head_sha") != source_sha):
        raise ValueError("staging_resume_sink_submit_unverified")
    return sink



def adapters_origin(listing: list[dict]) -> dict:
    """Admit reused active graph plus submitted adapters, before the site writer."""
    skipped = SKIPPED - {API_JOB, INGRESS_JOB, EVENTS_JOB}
    selected = {}
    for name in required_jobs(listing) | skipped | {SINK_JOB, API_JOB, INGRESS_JOB, EVENTS_JOB}:
        matches = [row for row in listing if row.get("name") == name]
        expected = "skipped" if name in skipped else "failure" if name == EVENTS_JOB else "success"
        if len(matches) != 1 or matches[0].get("status") != "completed" or matches[0].get("conclusion") != expected:
            raise ValueError("staging_resume_adapter_boundary_unverified")
        selected[name] = matches[0]
    for name in (SINK_JOB, API_JOB, INGRESS_JOB, EVENTS_JOB):
        row = selected[name]
        if (type(row.get("id")) is not int or row["id"] <= 0
                or row.get("run_id") != int(ADAPTER_RUN) or row.get("head_sha") != ADAPTER_SHA):
            raise ValueError("staging_resume_adapter_job_unverified")
    for job, step, conclusion in ((SINK_JOB, DEPLOY_STEP, "skipped"), (API_JOB, API_STEP, "skipped"),
                                  (API_JOB, CUTOVER_STEP, "skipped"), (API_JOB, GRAPH_STEP, "success"),
                                  (INGRESS_JOB, INGRESS_STEP, "success"), (EVENTS_JOB, EVENTS_STEP, "success"),
                                  (EVENTS_JOB, SUBSCRIPTION_STEP, "success"), (EVENTS_JOB, ADAPTER_CHECK_STEP, "failure")):
        require_step(selected[job], step, conclusion)
    return {**selected[EVENTS_JOB], "ingress_job_id": selected[INGRESS_JOB]["id"]}


def adapter_log(raw: bytes, component: str) -> str:
    """Require one exact successful adapter submit in its original reviewed job."""
    if component not in ("ingress", "events"):
        raise ValueError("staging_resume_adapter_component_unreviewed")
    version = ADAPTER_INGRESS if component == "ingress" else ADAPTER_EVENTS
    records = submit_records(raw)
    if len(records) != 1 or not submit_matches(records[0], ADAPTER_RUN, ADAPTER_SHA,
                                              "mail-" + component, version, "staging-" + component):
        raise ValueError("staging_resume_adapter_submit_unverified")
    return version


def submit_records(raw: bytes) -> list[dict]:
    """Extract one typed successful submit only; raw GitHub logs never leave here."""
    if not isinstance(raw, bytes) or not 0 < len(raw) <= 8 * 1024 * 1024:
        raise ValueError("staging_resume_log_unverified")
    records = []
    for line in raw.splitlines():
        start = line.find(b'{')
        if start < 0:
            continue
        try:
            row = decode(line[start:])
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("operation") == "workers.deploy" and row.get("event") == "control_plane_end" and row.get("phase") == "submit":
            records.append(row)
    return records


def submit_matches(row: dict, run_id: str, source_sha: str, component: str, version: str, job: str) -> bool:
    """Keep exact typed coordinates and results shared across reviewed phases."""
    expected = {"schema": "control-plane-span/v1", "event": "control_plane_end",
                "operation": "workers.deploy", "phase": "submit", "realm": "staging",
                "component": component, "outcome": "success", "version": version,
                "version_count": 1, "process_exit_code": 0, "source_sha": source_sha,
                "run_id": run_id, "run_attempt": "1", "job": job}
    return all(row.get(key) == value and type(row.get(key)) is type(value)
               for key, value in expected.items())


def sink_log(raw: bytes) -> str:
    """Extract the original single successful submit, without exposing raw logs."""
    records = submit_records(raw)
    if len(records) != 1 or not submit_matches(records[0], ORIGIN_RUN, ORIGIN_SHA,
                                              "trace_sink", SINK_VERSION, "staging-trace-sink"):
        raise ValueError("staging_resume_typed_submit_unverified")
    return records[0]["version"]


def require_step(job: dict, name: str, conclusion: str) -> None:
    """Positive exact step state identifies the reviewed interruption boundary."""
    steps = job.get("steps")
    found = [row for row in steps if isinstance(row, dict) and row.get("name") == name] if isinstance(steps, list) else []
    if len(found) != 1 or found[0].get("status") != "completed" or found[0].get("conclusion") != conclusion:
        raise ValueError("staging_resume_phase_step_unverified")


def active_log(raw: bytes) -> None:
    """Require precisely API, paused maintenance and active maintenance submits."""
    records = submit_records(raw)
    versions = (ACTIVE_API, PAUSED_MAINTENANCE, ACTIVE_MAINTENANCE)
    if len(records) != 3 or any(not submit_matches(row, ACTIVE_RUN, ACTIVE_SHA, "mail_api", version,
                                                  "staging-worker") for row, version in zip(records, versions)):
        raise ValueError("staging_resume_active_submits_unverified")


def cutover_witness(value: object) -> dict:
    """Admit the immutable observed platform window, not elapsed wall-clock age."""
    expected = {"schema": "staging-platform-cutover/v1", "source_sha": ACTIVE_SHA, "run_id": ACTIVE_RUN,
                "old_api_version": API_VERSION, "api_version": ACTIVE_API,
                "paused_maintenance_version": PAUSED_MAINTENANCE, "old_usage_model": "standard",
                "propagation_limit_seconds": 900, "invocation_limit_seconds": 900}
    fields = set(expected) | {"observed_monotonic_seconds", "pin_samples", "execution_leases_preserved"}
    if (not isinstance(value, dict) or set(value) != fields
            or any(value.get(key) != item or type(value.get(key)) is not type(item) for key, item in expected.items())
            or type(value.get("observed_monotonic_seconds")) not in (int, float)
            or not 1860 <= value["observed_monotonic_seconds"] < float("inf")
            or type(value.get("pin_samples")) is not int or value["pin_samples"] < 2):
        raise ValueError("staging_resume_cutover_witness_unverified")
    leases = value["execution_leases_preserved"]
    if (not isinstance(leases, dict) or set(leases) != {"embedding_leases", "projection_leases"}
            or any(type(count) is not int or count < 0 for count in leases.values())):
        raise ValueError("staging_resume_cutover_leases_unverified")
    return value


def predecessor(value: object) -> dict:
    """Require original absent resources and the exact legacy API capability pins."""
    if (not isinstance(value, dict) or set(value) != {"schema", "source_sha", "run_id", "scripts", "queues", "rollout", "old_usage_model"}
            or value.get("schema") != "staging-predecessor/v1" or value.get("source_sha") != ORIGIN_SHA
            or value.get("run_id") != ORIGIN_RUN or value.get("rollout") != "legacy"
            or value.get("old_usage_model") not in ("standard", "unbound")
            or not isinstance(value.get("scripts"), dict) or not isinstance(value.get("queues"), dict)):
        raise ValueError("staging_resume_predecessor_unverified")
    scripts = value["scripts"]
    if set(scripts) != {"amail-mail-staging", "amail-mail-maintenance-staging", "amail-inbound-staging", "amail-events-staging", "amail-trace-sink-staging"}:
        raise ValueError("staging_resume_predecessor_unverified")
    api = scripts["amail-mail-staging"]
    expected = {"present": True, "deployment": API_DEPLOYMENT, "version": API_VERSION,
                "handlers": ["fetch", "scheduled"], "crons": ["*/5 * * * *"], "capture_off": True,
                "usage_model": "standard"}
    if (not isinstance(api, dict) or api != expected
            or api.get("present") is not True or api.get("capture_off") is not True):
        raise ValueError("staging_resume_legacy_api_unverified")
    if any(scripts[name] != {"present": False} for name in ("amail-mail-maintenance-staging", "amail-trace-sink-staging")):
        raise ValueError("staging_resume_preexisting_resource")
    if value["queues"] != {name: {"present": False} for name in ("amail-trace-events-staging", "amail-trace-dlq-staging")}:
        raise ValueError("staging_resume_preexisting_resource")
    return value


def provision(value: object) -> None:
    """Accept exactly the two newly created distinct reviewed staging Queue IDs."""
    expected = [{"target": "staging", "queue_name": name, "queue_id": identity} for name, identity in
                (("amail-trace-events-staging", QUEUE), ("amail-trace-dlq-staging", DLQ))]
    if not isinstance(value, list) or len(value) != 2 or any(row not in expected for row in value) or value[0] == value[1]:
        raise ValueError("staging_resume_queue_ownership_unverified")


def artifact_value(listing: list[dict], name: str, filename: str) -> object:
    """Read one immutable named ZIP member without extraction or path aliases."""
    selected = artifact(listing, name, LIMIT * 2)
    raw = github(f"artifacts/{selected['id']}/zip", binary=True)
    admitted = members(raw, {filename}, LIMIT * 2, 1)
    if set(admitted) != {filename} or len(admitted[filename]) > LIMIT:
        raise ValueError("staging_resume_artifact_unverified")
    return decode(admitted[filename])


def original_ownership() -> dict:
    """Re-read the original creator; later continuation cannot mint sink ownership."""
    sink = origin(github(f"runs/{ORIGIN_RUN}"),
                  github(f"runs/{ORIGIN_RUN}/attempts/1/jobs?per_page=100"), ORIGIN_RUN)
    listing = rows(github(f"runs/{ORIGIN_RUN}/artifacts?per_page=100"), "artifacts")
    old = predecessor(artifact_value(listing, f"staging-rollout-predecessor-{ORIGIN_RUN}", "staging-rollout-predecessor.json"))
    provision(artifact_value(listing, f"trace-queue-provision-staging-{ORIGIN_RUN}-1", "trace-queue-provision-staging.json"))
    version = sink_log(job_log(sink["id"]))
    return {"predecessor": old, "queue": QUEUE, "dlq": DLQ, "sink_version": version}


def active_ownership() -> dict:
    """Extend original sink ownership with the observed immutable cutover epoch."""
    value = original_ownership()
    api = origin(github(f"runs/{ACTIVE_RUN}"), github(f"runs/{ACTIVE_RUN}/attempts/1/jobs?per_page=100"), ACTIVE_RUN)
    active_log(job_log(api["id"]))
    listing = rows(github(f"runs/{ACTIVE_RUN}/artifacts?per_page=100"), "artifacts")
    value["cutover"] = cutover_witness(artifact_value(listing, f"staging-cutover-{ACTIVE_RUN}", "staging-cutover.json"))
    value.update({"api_version": ACTIVE_API, "maintenance_version": ACTIVE_MAINTENANCE})
    return value


def recover(run_id: str) -> dict:
    """Resolve reviewed phase ownership; current full gates remain caller-owned."""
    if run_id not in (ORIGIN_RUN, ACTIVE_RUN, ADAPTER_RUN):
        raise ValueError("staging_resume_run_unreviewed")
    current_sha = os.getenv("GITHUB_SHA", "")
    source_sha = {ORIGIN_RUN: ORIGIN_SHA, ACTIVE_RUN: ACTIVE_SHA, ADAPTER_RUN: ADAPTER_SHA}[run_id]
    if run_id != ORIGIN_RUN:
        exact_tree(current_sha, source_sha)
    else:
        exact_tree(current_sha)
    phase = {ORIGIN_RUN: "legacy", ACTIVE_RUN: "active", ADAPTER_RUN: "adapters"}[run_id]
    value = {"origin_run": run_id, "source_sha": source_sha, "current_sha": current_sha, "phase": phase,
             **(original_ownership() if run_id == ORIGIN_RUN else active_ownership())}
    if run_id == ADAPTER_RUN:
        events = origin(github(f"runs/{run_id}"), github(f"runs/{run_id}/attempts/1/jobs?per_page=100"), run_id)
        value["ingress_version"] = adapter_log(job_log(events["ingress_job_id"]), "ingress")
        value["events_version"] = adapter_log(job_log(events["id"]), "events")
    return value


def load_resume(run_id: str) -> dict:
    """Persist fresh provenance under repository scratch, not operator supplied JSON."""
    value = recover(run_id)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    return value
