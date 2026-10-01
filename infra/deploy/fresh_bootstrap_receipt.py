"""Closed v2 first-paused receipt with protected same-run origin admission.

V1 receipts/readers are unchanged. JSON, resource construction and a local graph
witness are not provider authority. Only the reviewed protected executor may
produce this record; load admits its exact main/first-attempt CI job artifact.
Fresh storage isolation never establishes shared external old-work termination.
"""

from dataclasses import asdict, dataclass
import io
import json
import os
from pathlib import Path
import stat
import zipfile

from fresh_bootstrap_contract import Epoch, Scope, ORIGINAL_BUCKET, ORIGINAL_DATABASE, REPO, RUN
from fresh_bootstrap_readback import VerifiedGraph, canonical
from mail_lifecycle_receipt import LIMIT, checked_graph, github, inventory, scripts, unique_object
from pin_staging_mail import ACCOUNT

WORKFLOW = ".github/workflows/ci.yml"
JOB = "Fresh held production bootstrap"
SCHEMA = "mail-lifecycle-observation/v2"
RESUMED_SCHEMA = "mail-lifecycle-observation/v3"
CREATION = "SUCCESSFUL_CREATE_AND_EXACT_READBACK"
ROOT = Path(__file__).resolve().parents[2]


def validate(value: object) -> dict:
    """Require exact fresh paused metadata; no active/drain/source-adoption grant."""
    fields = {"schema", "realm", "state", "source_epoch", "run_attempt", "scope", "creation",
              "graph", "resources", "sendHeld", "originalstores", "source_adoption", "activation", "old_work_end"}
    resumed = isinstance(value, dict) and value.get("schema") == RESUMED_SCHEMA
    if resumed:
        fields.add("creation_epoch")
        if "retained_sink" in value:
            fields.add("retained_sink")
        if "retained_workers" in value:
            fields.add("retained_workers")
    if (not isinstance(value, dict) or set(value) != fields or value["schema"] not in (SCHEMA, RESUMED_SCHEMA)
            or value["realm"] != "production" or value["state"] != "paused"
            or type(value["run_attempt"]) is not int or value["run_attempt"] != 1
            or value["sendHeld"] is not True or value["source_adoption"] != "REQUIRED"
            or value["activation"] != "NOT_GRANTED" or value["old_work_end"] != "UNVERIFIED"
            or value["creation"] != {"database": CREATION, "bucket": CREATION}
            or value["originalstores"] != {"database": ORIGINAL_DATABASE, "bucket": ORIGINAL_BUCKET, "retained": True}
            or value["originalstores"].get("retained") is not True):
        raise ValueError("fresh_receipt_unreviewed")
    source = value["source_epoch"]
    if not isinstance(source, dict) or set(source) != {"source_sha", "run_id", "artifact_id", "manifest_sha256", "rust", "worker_build"}:
        raise ValueError("fresh_receipt_source_unreviewed")
    epoch = Epoch(**source)
    if resumed:
        creation = value["creation_epoch"]
        if not isinstance(creation, dict) or set(creation) != set(source):
            raise ValueError("fresh_receipt_creation_epoch_unreviewed")
        epoch = Epoch(**creation)
    stores = value["scope"]
    if not isinstance(stores, dict) or set(stores) != {"database", "database_name", "database_created_at", "bucket", "bucket_created_at"}:
        raise ValueError("fresh_receipt_scope_unreviewed")
    scope = Scope(epoch, stores["database"], stores["database_created_at"], stores["bucket_created_at"])
    if stores["database_name"] != scope.database_name or stores["bucket"] != scope.bucket:
        raise ValueError("fresh_receipt_scope_mismatch")
    graph = checked_graph(value["graph"], "production")
    if "retained_sink" in value and "retained_workers" in value:
        raise ValueError("fresh_receipt_retained_workers_unreviewed")
    if "retained_sink" in value:
        retained = value["retained_sink"]
        if (not isinstance(retained, dict) or set(retained) != {"source_epoch", "version"}
                or not isinstance(retained["source_epoch"], dict)
                or set(retained["source_epoch"]) != set(source)
                or retained["version"] != graph["pins"]["amail-trace-sink"]["version"]):
            raise ValueError("fresh_receipt_retained_sink_unreviewed")
        sink_epoch = Epoch(**retained["source_epoch"])
        if sink_epoch.run_id in {source["run_id"], epoch.run_id}:
            raise ValueError("fresh_receipt_retained_sink_unreviewed")
    if "retained_workers" in value:
        retained = value["retained_workers"]
        if not isinstance(retained, dict) or set(retained) != scripts("production"):
            raise ValueError("fresh_receipt_retained_workers_unreviewed")
        for script, worker in retained.items():
            if (not isinstance(worker, dict) or set(worker) != {"source_epoch", "version"}
                    or not isinstance(worker["source_epoch"], dict) or set(worker["source_epoch"]) != set(source)
                    or worker["version"] != graph["pins"][script]["version"]):
                raise ValueError("fresh_receipt_retained_workers_unreviewed")
            worker_epoch = Epoch(**worker["source_epoch"])
            if worker_epoch.run_id in {source["run_id"], epoch.run_id}:
                raise ValueError("fresh_receipt_retained_workers_unreviewed")
    if graph["api_crons"] != [] or graph["maintenance_crons"] != []:
        raise ValueError("fresh_receipt_schedule_unreviewed")
    resources = value["resources"]
    if (not isinstance(resources, dict) or set(resources) != {"database", "bucket", "queue", "dlq"}
            or resources["database"] != scope.database or resources["bucket"] != scope.bucket
            or any(not isinstance(resources[key], str) or ACCOUNT.fullmatch(resources[key]) is None for key in ("queue", "dlq"))
            or resources["queue"] == resources["dlq"]):
        raise ValueError("fresh_receipt_resources_unreviewed")
    return value


@dataclass(frozen=True)
class Receipt:
    """Immutable admitted operational record; .value always returns an isolated copy."""

    payload: str
    artifact_id: int

    def __post_init__(self):
        """Closed validation prevents mutable backing and invalid archive identities."""
        if (not isinstance(self.payload, str) or len(self.payload.encode()) > LIMIT
                or type(self.artifact_id) is not int or self.artifact_id <= 0):
            raise ValueError("fresh_receipt_storage_unreviewed")
        validate(self.value)

    @property
    def value(self) -> dict:
        """Decode without permitting duplicate-key overwrite of source/pin fields."""
        return json.loads(self.payload, object_pairs_hook=unique_object)


def persist(scope: Scope, graph: dict, queue: str, dlq: str, path: Path,
            *, deployment_epoch: Epoch | None = None, retained_sink: dict | None = None,
            retained_workers: dict | None = None) -> dict:
    """Persist once only after exact readback, inside the repository's .temp tree.

    Example: ``persist(scope, verify(scope, pins, queue, dlq, provider), queue,
    dlq, ROOT / '.temp/fresh-bootstrap/receipt.json')``. No automatic retry,
    overwrite, activation, old-store deletion or source-resource adoption occurs.
    ``retained_workers`` records exact prior source/version pairs for all three
    observed scripts when this run only adjusts settings; it excludes ``retained_sink``.
    """
    if not isinstance(scope, Scope) or type(graph) is not VerifiedGraph:
        raise ValueError("fresh_successful_readback_required")
    if deployment_epoch is not None and not isinstance(deployment_epoch, Epoch):
        raise ValueError("fresh_receipt_source_unreviewed")
    source = deployment_epoch or scope.epoch
    creation = {"creation_epoch": asdict(scope.epoch)} if deployment_epoch is not None else {}
    if retained_sink is not None:
        if deployment_epoch is None:
            raise ValueError("fresh_receipt_retained_sink_unreviewed")
        creation["retained_sink"] = retained_sink
    if retained_workers is not None:
        if deployment_epoch is None:
            raise ValueError("fresh_receipt_retained_workers_unreviewed")
        creation["retained_workers"] = retained_workers
    value = validate({"schema": RESUMED_SCHEMA if creation else SCHEMA, "realm": "production", "state": "paused",
                      "source_epoch": asdict(source), "run_attempt": 1, **creation,
                      "scope": {"database": scope.database, "database_name": scope.database_name,
                                "database_created_at": scope.database_created_at,
                                "bucket": scope.bucket, "bucket_created_at": scope.bucket_created_at},
                      "creation": {"database": CREATION, "bucket": CREATION},
                      "graph": graph.checked(scope, queue, dlq),
                      "resources": {"database": scope.database, "bucket": scope.bucket, "queue": queue, "dlq": dlq},
                      "sendHeld": True,
                      "originalstores": {"database": ORIGINAL_DATABASE, "bucket": ORIGINAL_BUCKET, "retained": True},
                      "source_adoption": "REQUIRED", "activation": "NOT_GRANTED", "old_work_end": "UNVERIFIED"})
    if (os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("GITHUB_REF") != "refs/heads/main"
            or os.getenv("GITHUB_REPOSITORY") != REPO or os.getenv("GITHUB_RUN_ATTEMPT") != "1"
            or os.getenv("GITHUB_EVENT_NAME") != "workflow_dispatch"
            or os.getenv("GITHUB_JOB") != "production-fresh-bootstrap"
            or os.getenv("GITHUB_WORKFLOW_REF") != f"{REPO}/{WORKFLOW}@refs/heads/main"
            or os.getenv("GITHUB_RUN_ID") != source.run_id or os.getenv("GITHUB_SHA") != source.source_sha):
        raise ValueError("fresh_receipt_protected_context_required")
    target = Path(path)
    temp = ROOT / ".temp"
    if target.name != "receipt.json" or not target.absolute().is_relative_to(temp.absolute()):
        raise ValueError("fresh_receipt_path_unreviewed")
    if not target.resolve().is_relative_to(temp.resolve()) or any(folder.is_symlink() for folder in (temp, target.parent, *target.parent.parents)):
        raise ValueError("fresh_receipt_path_unreviewed")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical(value)
    if len(payload.encode()) > LIMIT:
        raise ValueError("fresh_receipt_size_unreviewed")
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(payload + "\n")
        output.flush()
        os.fsync(output.fileno())
    return json.loads(payload)


def origin(run: object, jobs: object, run_id: str) -> str:
    """Only successful exact repository/main/first-attempt protected CI producer."""
    if (not isinstance(run, dict) or type(run.get("id")) is not int or str(run["id"]) != run_id
            or type(run.get("run_attempt")) is not int or run["run_attempt"] != 1
            or run.get("status") != "completed" or run.get("conclusion") != "success"
            or run.get("event") != "workflow_dispatch" or run.get("head_branch") != "main"
            or run.get("path") != WORKFLOW or not isinstance(run.get("repository"), dict)
            or run["repository"].get("full_name") != REPO):
        raise ValueError("fresh_receipt_protected_origin_required")
    from fresh_bootstrap_contract import SHA
    if not isinstance(run.get("head_sha"), str) or SHA.fullmatch(run["head_sha"]) is None:
        raise ValueError("fresh_receipt_protected_origin_required")
    matches = [row for row in inventory(jobs, "jobs") if row.get("name") == JOB]
    if (len(matches) != 1 or matches[0].get("status") != "completed" or matches[0].get("conclusion") != "success"
            or type(matches[0].get("run_id")) is not int or matches[0]["run_id"] != int(run_id)
            or matches[0].get("head_sha") != run["head_sha"]):
        raise ValueError("fresh_receipt_protected_job_required")
    return run["head_sha"]


def load(run_id: str) -> Receipt:
    """Admit provenance before decoding one bounded immutable receipt ZIP member."""
    if not isinstance(run_id, str) or RUN.fullmatch(run_id) is None:
        raise ValueError("fresh_receipt_run_unreviewed")
    sha = origin(github(f"runs/{run_id}"), github(f"runs/{run_id}/attempts/1/jobs?per_page=100"), run_id)
    name = f"mail-fresh-bootstrap-{run_id}-1"
    matches = [row for row in inventory(github(f"runs/{run_id}/artifacts?per_page=100"), "artifacts") if row.get("name") == name]
    if (len(matches) != 1 or matches[0].get("expired") is not False
            or type(matches[0].get("id")) is not int or matches[0]["id"] <= 0
            or type(matches[0].get("size_in_bytes")) is not int or not 0 < matches[0]["size_in_bytes"] <= LIMIT * 2):
        raise ValueError("fresh_receipt_unique_artifact_required")
    raw = github(f"artifacts/{matches[0]['id']}/zip", binary=True)
    if not isinstance(raw, bytes) or not 0 < len(raw) <= LIMIT * 2:
        raise ValueError("fresh_receipt_archive_unreviewed")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        if (len(members) != 1 or members[0].filename != "receipt.json" or members[0].is_dir()
                or not 0 < members[0].file_size <= LIMIT or members[0].flag_bits & 1
                or stat.S_IFMT(members[0].external_attr >> 16) not in (0, stat.S_IFREG)):
            raise ValueError("fresh_receipt_archive_member_unreviewed")
        value = validate(json.loads(archive.read(members[0]), object_pairs_hook=unique_object))
    if value["source_epoch"]["source_sha"] != sha or value["source_epoch"]["run_id"] != run_id:
        raise ValueError("fresh_receipt_origin_mismatch")
    return Receipt(canonical(value), matches[0]["id"])
