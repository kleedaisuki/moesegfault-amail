"""Read protected prior-bootstrap evidence without replaying a provider operation.

A failed or cancelled creator may have performed real writes. Its immutable GitHub artifact,
not current inventory or operator JSON, supplies the original recovery epoch.
"""

from dataclasses import asdict, dataclass
import hashlib
import io
import json
from pathlib import Path
import re
import stat
import subprocess
import sys
import zipfile

from fresh_bootstrap_contract import Epoch, Scope, REPO, RUN, SHA
from fresh_bootstrap_scope import _timestamp
from mail_lifecycle_receipt import github, inventory, unique_object
from pin_staging_mail import UUID

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/ci"))
from inbox_worker_artifact import REQUIRED
from worker_artifact import TREES, ENTRY_FILES

LIMIT = 65_536
MODULE_LIMIT = 32 * 1024 * 1024
JOB = "Fresh held production bootstrap"
ALLOWED = {"controller.jsonl", "controller.scope.jsonl", "trace-queue-provision-production.json", "preflight.jsonl"}
PHASES = ("admission", "old_scope", "create_scope", "render", "migrate", "queues", "sink",
          "sink_readback", "maintenance", "api", "readback", "receipt")
# A terminal conclusion is not ownership evidence; immutable journals still gate every read.
TERMINAL = {"success", "failure", "timed_out", "cancelled"}


def origin(run_id: str) -> tuple[str, list[dict]]:
    """Require a terminal protected creator, including interrupted ambiguous writes."""
    if not isinstance(run_id, str) or RUN.fullmatch(run_id) is None:
        raise ValueError("fresh_recovery_run_unreviewed")
    run = github(f"runs/{run_id}")
    if (not isinstance(run, dict) or type(run.get("id")) is not int or str(run["id"]) != run_id
            or type(run.get("run_attempt")) is not int or run["run_attempt"] != 1
            or run.get("status") != "completed" or run.get("event") != "workflow_dispatch"
            or run.get("head_branch") != "main" or run.get("path") != ".github/workflows/ci.yml"
            or run.get("conclusion") not in TERMINAL
            or not isinstance(run.get("head_sha"), str) or SHA.fullmatch(run["head_sha"]) is None
            or not isinstance(run.get("repository"), dict) or run["repository"].get("full_name") != REPO):
        raise ValueError("fresh_recovery_protected_origin_required")
    jobs = inventory(github(f"runs/{run_id}/attempts/1/jobs?per_page=100"), "jobs")
    selected = [row for row in jobs if row.get("name") == JOB]
    if (len(selected) != 1 or selected[0].get("status") != "completed"
            or selected[0].get("conclusion") not in TERMINAL
            or selected[0].get("run_id") != int(run_id) or selected[0].get("head_sha") != run["head_sha"]):
        raise ValueError("fresh_recovery_protected_job_required")
    for name in REQUIRED:
        matches = [row for row in jobs if row.get("name") == name]
        if (len(matches) != 1 or matches[0].get("status") != "completed"
                or matches[0].get("conclusion") != "success"):
            raise ValueError("fresh_recovery_full_source_required")
    return run["head_sha"], inventory(github(f"runs/{run_id}/artifacts?per_page=100"), "artifacts")


def artifact(rows: list[dict], name: str, limit: int) -> dict:
    """Select one nonexpired immutable ID with bounded declared download size."""
    matches = [row for row in rows if row.get("name") == name]
    if not matches:
        raise ValueError("fresh_recovery_artifact_unavailable")
    if (len(matches) != 1 or type(matches[0].get("id")) is not int or matches[0]["id"] <= 0
            or matches[0].get("expired") is not False or type(matches[0].get("size_in_bytes")) is not int
            or not 0 < matches[0]["size_in_bytes"] <= limit):
        raise ValueError("fresh_recovery_unique_artifact_required")
    return matches[0]


def module_zip(artifact_id: int) -> bytes:
    """Bound the larger original public module artifact; suppress arbitrary stderr."""
    result = subprocess.run(["gh", "api", f"repos/{REPO}/actions/artifacts/{artifact_id}/zip"],
                            capture_output=True, timeout=60, check=False)
    if result.returncode or not 0 < len(result.stdout) <= MODULE_LIMIT:
        raise ValueError("fresh_recovery_original_download_failed")
    return result.stdout


def members(raw: bytes, allowed: set[str] | None, limit: int, count: int) -> dict[str, bytes]:
    """Reject ZIP aliases, traversal, directories, encryption and expansion bombs."""
    if not isinstance(raw, bytes) or not 0 < len(raw) <= limit:
        raise ValueError("fresh_recovery_zip_unreviewed")
    result, size = {}, 0
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if not 1 <= len(entries) <= count:
                raise ValueError("fresh_recovery_zip_unreviewed")
            for entry in entries:
                name = entry.filename
                size += entry.file_size
                if (not name or entry.orig_filename != name or name in result or entry.is_dir() or entry.flag_bits & 1
                        or stat.S_IFMT(entry.external_attr >> 16) not in (0, stat.S_IFREG)
                        or name.startswith("/") or "\\" in name or any(part in {"", ".", ".."} for part in name.split("/"))
                        or allowed is not None and name not in allowed or size > limit
                        or entry.file_size < 0 or entry.file_size > limit):
                    raise ValueError("fresh_recovery_zip_unreviewed")
                result[name] = archive.read(entry)
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError):
        raise ValueError("fresh_recovery_zip_unreviewed") from None
    return result


def decode(raw: bytes) -> object:
    """Never permit duplicate keys or nonstandard NaN constants in admitted JSON."""
    def invalid(_):
        raise ValueError("fresh_recovery_json_unreviewed")
    try:
        return json.loads(raw, object_pairs_hook=unique_object, parse_constant=invalid)
    except (ValueError, UnicodeError):
        raise ValueError("fresh_recovery_json_unreviewed") from None


def lines(raw: bytes, count: int) -> list[dict]:
    """Bound journal rows and require objects before inspecting closed schemas."""
    if not 0 < len(raw) <= LIMIT:
        raise ValueError("fresh_recovery_journal_unreviewed")
    result = [decode(line) for line in raw.splitlines()]
    if not 1 <= len(result) <= count or not all(isinstance(row, dict) for row in result):
        raise ValueError("fresh_recovery_journal_unreviewed")
    return result


def controller(raw: bytes, sha: str, run_id: str) -> Epoch:
    """Require a closed original epoch and a positive admission prefix before recovery."""
    rows = lines(raw, 32)
    value = rows[0].get("epoch")
    if not isinstance(value, dict) or set(value) != {"source_sha", "run_id", "artifact_id", "manifest_sha256", "rust", "worker_build"}:
        raise ValueError("fresh_recovery_epoch_unreviewed")
    epoch = Epoch(**value)
    if epoch.source_sha != sha or epoch.run_id != run_id:
        raise ValueError("fresh_recovery_epoch_origin_mismatch")
    base = {"schema": "mail-fresh-controller/v1", "epoch": asdict(epoch)}
    if len(rows) < 2 or rows[:2] != [{**base, "phase": "admission", "state": state} for state in ("intent", "observed")]:
        raise ValueError("fresh_recovery_admission_unavailable")
    sequence = [(phase, state) for phase in PHASES for state in ("intent", "observed")]
    for index, row in enumerate(rows):
        phase, state = row.get("phase"), row.get("state")
        if index >= len(sequence) or row.get("schema") != base["schema"] or row.get("epoch") != value:
            raise ValueError("fresh_recovery_journal_unreviewed")
        extras = set()
        if state == "failed":
            if index != len(rows) - 1 or (phase, "observed") != sequence[index]:
                raise ValueError("fresh_recovery_journal_unreviewed")
            extras = {"error_type"} | ({"version"} if "version" in row else set())
            if not isinstance(row.get("error_type"), str) or re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,63}", row["error_type"]) is None:
                raise ValueError("fresh_recovery_journal_unreviewed")
        elif (phase, state) != sequence[index]:
            raise ValueError("fresh_recovery_journal_unreviewed")
        elif state == "observed":
            extras = {"create_scope": {"scope"}, "queues": {"queue", "dlq"}, "sink": {"version"},
                      "maintenance": {"version"}, "api": {"version"}}.get(phase, set())
        if set(row) != set(base) | {"phase", "state"} | extras:
            raise ValueError("fresh_recovery_journal_unreviewed")
        if "version" in row and (phase not in {"sink", "maintenance", "api"}
                                  or not isinstance(row["version"], str) or UUID.fullmatch(row["version"]) is None):
            raise ValueError("fresh_recovery_journal_unreviewed")
        if "scope" in row:
            scope = row["scope"]
            if not isinstance(scope, dict) or set(scope) != {"epoch", "database", "database_created_at", "bucket_created_at"} or scope["epoch"] != value:
                raise ValueError("fresh_recovery_journal_unreviewed")
            Scope(epoch, scope["database"], scope["database_created_at"], scope["bucket_created_at"])
        if "queue" in row and (any(not isinstance(row[k], str) or re.fullmatch(r"[0-9a-f]{32}", row[k]) is None for k in ("queue", "dlq")) or row["queue"] == row["dlq"]):
            raise ValueError("fresh_recovery_journal_unreviewed")
    return epoch


def original(raw: bytes, epoch: Epoch) -> None:
    """Verify original manifest coordinates and every original generated module byte."""
    files = members(raw, None, MODULE_LIMIT, 1001)
    manifest = files.pop("manifest.json", None)
    if manifest is None or len(manifest) > 262144 or hashlib.sha256(manifest).hexdigest() != epoch.manifest_sha256:
        raise ValueError("fresh_recovery_original_manifest_mismatch")
    value = decode(manifest)
    expected = {"schema": "worker-native-artifact/v1", "source_sha": epoch.source_sha,
                "run_id": epoch.run_id, "run_attempt": 1, "rust": epoch.rust, "worker_build": epoch.worker_build}
    if (not isinstance(value, dict) or set(value) != set(expected) | {"files"}
            or any(type(value[k]) is not type(v) or value[k] != v for k, v in expected.items())
            or value["files"] != {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
            or any(name not in ENTRY_FILES and not any(name.startswith(tree + "/") for tree in TREES) for name in files)
            or any(f"{tree}/{suffix}" not in files for tree in TREES for suffix in ("index.js", "worker/shim.mjs"))):
        raise ValueError("fresh_recovery_original_artifact_mismatch")


def scope_journal(raw: bytes, epoch: Epoch) -> None:
    """Check a closed creation prefix before persisting any provider coordinates."""
    rows = lines(raw, 12)
    if rows[0] != {"schema": "mail-fresh-scope-recovery/v1", "event": "ownership", "epoch": asdict(epoch),
                   "database_name": epoch.database_name, "bucket": epoch.bucket_name, "may_replay_write": False}:
        raise ValueError("fresh_recovery_scope_unreviewed")
    sequence = ("d1_submit_intent", "d1_created", "d1_readback_verified", "r2_submit_intent", "r2_created", "scope_readback_verified")
    database = None
    database_time = bucket_time = None
    if rows[0]["may_replay_write"] is not False:
        raise ValueError("fresh_recovery_scope_unreviewed")
    for index, row in enumerate(rows[1:]):
        event = row.get("event")
        if event == "recovery_only":
            if (index != len(rows) - 2 or set(row) != {"event", "may_replay_write", "reason"}
                    or row["may_replay_write"] is not False or not isinstance(row["reason"], str)
                    or re.fullmatch(r"[a-z][a-z_0-9]{0,95}", row["reason"]) is None):
                raise ValueError("fresh_recovery_scope_unreviewed")
            continue
        if index >= len(sequence) or event != sequence[index]:
            raise ValueError("fresh_recovery_scope_unreviewed")
        if event.endswith("submit_intent"):
            wanted = epoch.database_name if event.startswith("d1") else epoch.bucket_name
            if row != {"event": event, "name": wanted, "attempt": 1} or type(row["attempt"]) is not int:
                raise ValueError("fresh_recovery_scope_unreviewed")
        elif event == "d1_created":
            if set(row) != {"event", "database", "created_at"}:
                raise ValueError("fresh_recovery_scope_unreviewed")
            _timestamp(row["created_at"])
            Scope(epoch, row["database"], _timestamp(row["created_at"]), _timestamp(row["created_at"]))
            database = row["database"]
            database_time = _timestamp(row["created_at"])
        elif event == "d1_readback_verified":
            if row != {"event": event, "database": database}:
                raise ValueError("fresh_recovery_scope_unreviewed")
        elif event == "r2_created":
            if set(row) != {"event", "bucket", "creation_date"} or row["bucket"] != epoch.bucket_name:
                raise ValueError("fresh_recovery_scope_unreviewed")
            bucket_time = _timestamp(row["creation_date"])
        elif event == "scope_readback_verified":
            scope = row.get("scope")
            if set(row) != {"event", "scope"} or not isinstance(scope, dict) or set(scope) != {"epoch", "database", "database_created_at", "bucket_created_at"} or scope["epoch"] != asdict(epoch) or scope["database"] != database or scope["database_created_at"] != database_time or scope["bucket_created_at"] != bucket_time:
                raise ValueError("fresh_recovery_scope_unreviewed")
            Scope(epoch, scope["database"], scope["database_created_at"], scope["bucket_created_at"])


def queue_receipt(raw: bytes) -> None:
    """Accept only the existing two fixed Queue creation identities, never raw outputs."""
    value = decode(raw)
    if not isinstance(value, list) or not 1 <= len(value) <= 2:
        raise ValueError("fresh_recovery_queue_unreviewed")
    seen, identities = set(), set()
    for row in value:
        if (not isinstance(row, dict) or set(row) != {"target", "queue_name", "queue_id"}
                or row["target"] != "production" or not isinstance(row["queue_name"], str) or row["queue_name"] not in {"amail-trace-events", "amail-trace-dlq"}
                or row["queue_name"] in seen or not isinstance(row["queue_id"], str)
                or re.fullmatch(r"[0-9a-f]{32}", row["queue_id"]) is None or row["queue_id"] in identities):
            raise ValueError("fresh_recovery_queue_unreviewed")
        seen.add(row["queue_name"])
        identities.add(row["queue_id"])



def preflight(raw: bytes, sha: str, run_id: str) -> None:
    """Optional initial diagnostics never establish admitted artifact or write ownership."""
    rows = lines(raw, 3)
    states = [row.get("state") for row in rows]
    if states not in (["intent"], ["intent", "admitted"], ["intent", "failed"], ["intent", "admitted", "failed"]):
        raise ValueError("fresh_recovery_preflight_unreviewed")
    for row in rows:
        fields = {"schema", "state", "source_sha", "run_id", "activation", "replay"}
        if row["state"] == "failed":
            fields.add("error_type")
            if not isinstance(row.get("error_type"), str) or re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,63}", row["error_type"]) is None:
                raise ValueError("fresh_recovery_preflight_unreviewed")
        if (set(row) != fields or row["schema"] != "mail-fresh-preflight/v1"
                or not isinstance(row["source_sha"], str) or row["source_sha"] not in {sha, "UNVERIFIED"}
                or not isinstance(row["run_id"], str) or row["run_id"] not in {run_id, "UNVERIFIED"}
                or row["activation"] != "NOT_GRANTED" or row["replay"] != "NOT_GRANTED"):
            raise ValueError("fresh_recovery_preflight_unreviewed")

def load(run_id: str, folder: Path) -> tuple[Epoch, Path]:
    """Admit and exclusively persist original evidence; this function never contacts Cloudflare.

    Example: ``epoch, path = load(prior_run, ROOT / '.temp/recovery/prior')``.
    The caller may pass the returned journal to the existing read-only controller
    recovery method. Neither this admission nor recovery grants activation.
    """
    sha, rows = origin(run_id)
    recovery = artifact(rows, f"mail-fresh-bootstrap-recovery-{run_id}-1", LIMIT * 2)
    files = members(github(f"artifacts/{recovery['id']}/zip", binary=True), ALLOWED, LIMIT * 2, 4)
    if "preflight.jsonl" in files:
        preflight(files["preflight.jsonl"], sha, run_id)
    if "controller.jsonl" not in files:
        raise ValueError("fresh_recovery_controller_unavailable")
    epoch = controller(files["controller.jsonl"], sha, run_id)
    # Cancellation can stop before the scope journal exists; never infer its contents.
    intent = lines(files["controller.jsonl"], 32)
    if (any(row["phase"] == "create_scope" and row["state"] == "intent" for row in intent)
            and "controller.scope.jsonl" not in files):
        raise ValueError("fresh_recovery_scope_unavailable")
    build = artifact(rows, f"worker-native-modules-{sha}", MODULE_LIMIT)
    if build["id"] != epoch.artifact_id:
        raise ValueError("fresh_recovery_original_artifact_id_mismatch")
    original(module_zip(build["id"]), epoch)
    if "controller.scope.jsonl" in files:
        scope_journal(files["controller.scope.jsonl"], epoch)
    if "trace-queue-provision-production.json" in files:
        queue_receipt(files["trace-queue-provision-production.json"])
    folder = Path(folder)
    owned = (ROOT / ".temp").resolve()
    resolved = folder.resolve()
    if not resolved.is_relative_to(owned) or resolved == owned or folder.exists() or folder.is_symlink():
        raise ValueError("fresh_recovery_destination_unreviewed")
    folder.mkdir(parents=True, exist_ok=False, mode=0o700)
    for name, data in files.items():
        with (folder / name).open("xb") as output:
            output.write(data)
        (folder / name).chmod(0o600)
    return epoch, folder / "controller.jsonl"


@dataclass(frozen=True)
class Checkpoint:
    """Validated observed deployments; never permission to replay a Worker write."""

    creation_run: str
    """Original storage creator, independently proved by the caller."""
    deployment_epoch: Epoch
    """Latest protected attempt whose immutable modules are verified."""
    sink_epoch: Epoch
    """Source of the observed sink, which may predate the latest attempt."""
    pins: dict[str, str]
    """Observed role/version identities; consumers must not mutate this mapping."""
    queue: str
    """Observed trace-events Queue ID, not its display name."""
    dlq: str
    """Observed dead-letter Queue ID, distinct from the events Queue."""
    replace_sink: bool
    """Only the legacy sink prefix requires replacement."""
    worker_epochs: dict[str, Epoch] | None = None
    """Per-role binary sources when the latest attempt only changed settings."""


def _sink_checkpoint(raw: bytes, sha: str, run_id: str) -> Checkpoint:
    """Admit only observed deployments followed by a known readback failure.

    The captured creation scope is type-checked, not treated as creation proof.
    Callers must independently load the original creator's ownership journal.
    """
    rows = lines(raw, 10)
    fields = {"source_sha", "run_id", "artifact_id", "manifest_sha256", "rust", "worker_build"}
    value = rows[0].get("deployment_epoch")
    creation_run = rows[0].get("creation_run")
    if (not isinstance(value, dict) or set(value) != fields
            or not isinstance(creation_run, str) or RUN.fullmatch(creation_run) is None
            or creation_run == run_id):
        raise ValueError("fresh_recovery_sink_checkpoint_unreviewed")
    epoch = Epoch(**value)
    if epoch.source_sha != sha or epoch.run_id != run_id:
        raise ValueError("fresh_recovery_epoch_origin_mismatch")
    base = {"schema": "mail-fresh-resume/v1", "deployment_epoch": value, "creation_run": creation_run}
    # Only observed production prefixes are admitted; not a replay engine.
    prefixes = {
        ("ownership", "migrate", "queues", "sink", "sink_readback"): (0, 5, {"sink": 7}, True, "FreshError"),
        ("ownership", "retained_sink", "sink_replacement", "sink_readback"): (11, 3, {"sink": 5}, False, "FreshError"),
        ("ownership", "retained_sink", "maintenance", "api", "receipt"): (11, 3, {"sink": 3, "maintenance": 5, "api": 7}, False, "ValueError"),
        ("ownership", "retained_workers", "maintenance_capture_off"): (11, 3, {}, False, "ValueError"),
    }
    phases = tuple(row.get("phase") for row in rows[::2])
    if any(not isinstance(phase, str) for phase in phases) or phases not in prefixes:
        raise ValueError("fresh_recovery_sink_checkpoint_unreviewed")
    schema_prefix, queue_index, role_indices, replace_needed, error_type = prefixes[phases]
    expected = [{**base, "phase": phase, "state": state}
                for phase in phases
                for state in ("intent", "observed")]
    if len(rows) != len(expected):
        raise ValueError("fresh_recovery_sink_checkpoint_unreviewed")
    ownership = rows[1]
    creation_value, scope = ownership.get("creation_epoch"), ownership.get("scope")
    if (not isinstance(creation_value, dict) or set(creation_value) != fields
            or not isinstance(scope, dict)
            or set(scope) != {"epoch", "database", "database_created_at", "bucket_created_at"}
            or scope["epoch"] != creation_value or type(ownership.get("schema_prefix")) is not int
            or ownership["schema_prefix"] != schema_prefix):
        raise ValueError("fresh_recovery_sink_checkpoint_unreviewed")
    creation_epoch = Epoch(**creation_value)
    if creation_epoch.run_id != creation_run:
        raise ValueError("fresh_recovery_sink_checkpoint_unreviewed")
    Scope(creation_epoch, scope["database"], scope["database_created_at"], scope["bucket_created_at"])
    queue, dlq = rows[queue_index].get("queue"), rows[queue_index].get("dlq")
    pins = {role: rows[index].get("version") for role, index in role_indices.items()}
    worker_epochs = None
    if "retained_workers" in phases:
        workers = rows[queue_index].get("workers")
        roles = {"sink": "amail-trace-sink", "maintenance": "amail-mail-maintenance", "api": "amail-mail"}
        if not isinstance(workers, dict) or set(workers) != set(roles.values()):
            raise ValueError("fresh_recovery_sink_checkpoint_unreviewed")
        worker_epochs = {}
        for role, script in roles.items():
            worker = workers[script]
            if (not isinstance(worker, dict) or set(worker) != {"source_epoch", "version"}
                    or not isinstance(worker["source_epoch"], dict) or set(worker["source_epoch"]) != fields):
                raise ValueError("fresh_recovery_sink_checkpoint_unreviewed")
            source_epoch = Epoch(**worker["source_epoch"])
            if source_epoch.run_id in {run_id, creation_run}:
                raise ValueError("fresh_recovery_sink_checkpoint_unreviewed")
            worker_epochs[role], pins[role] = source_epoch, worker["version"]
        expected[queue_index].update(workers=workers)
        worker_id = rows[-2].get("worker_id")
        if not isinstance(worker_id, str) or re.fullmatch(r"[0-9a-f]{32}", worker_id) is None:
            raise ValueError("fresh_recovery_sink_checkpoint_unreviewed")
        expected[-2].update(worker_id=worker_id, version=pins["maintenance"])
    if (any(not isinstance(item, str) or re.fullmatch(r"[0-9a-f]{32}", item) is None
            for item in (queue, dlq)) or queue == dlq
            or any(not isinstance(version, str) or UUID.fullmatch(version) is None for version in pins.values())
            or len(set(pins.values())) != len(pins)):
        raise ValueError("fresh_recovery_sink_checkpoint_unreviewed")
    expected[1].update(creation_epoch=creation_value, scope=scope, schema_prefix=schema_prefix)
    expected[queue_index].update(queue=queue, dlq=dlq)
    for role, index in role_indices.items():
        expected[index].update(version=pins[role])
    expected[-1].update(state="failed", error_type=error_type)
    sink_epoch = worker_epochs["sink"] if worker_epochs is not None else epoch
    if not replace_needed and worker_epochs is None:
        retained = rows[queue_index]
        source_value, previous = retained.get("source_epoch"), retained.get("version")
        if (not isinstance(source_value, dict) or set(source_value) != fields
                or not isinstance(previous, str) or UUID.fullmatch(previous) is None):
            raise ValueError("fresh_recovery_sink_checkpoint_unreviewed")
        source_epoch = Epoch(**source_value)
        if source_epoch.run_id in {run_id, creation_run}:
            raise ValueError("fresh_recovery_sink_checkpoint_unreviewed")
        expected[queue_index].update(source_epoch=source_value, version=previous)
        if "sink_replacement" in phases:
            if previous == pins["sink"]:
                raise ValueError("fresh_recovery_sink_checkpoint_unreviewed")
            expected[role_indices["sink"] - 1].update(previous_version=previous)
        else:
            sink_epoch = source_epoch
    if rows != expected:
        raise ValueError("fresh_recovery_sink_checkpoint_unreviewed")
    return Checkpoint(creation_run, epoch, sink_epoch, pins, queue, dlq, replace_needed, worker_epochs)


def load_sink_checkpoint(run_id: str, folder: Path) -> Checkpoint | None:
    """Load protected observed deployments without granting replay or ownership.

    Example: ``checkpoint = load_sink_checkpoint(
    latest_attempt, ROOT / '.temp/recovery/sink')``. The caller separately proves
    original storage ownership and reads back this exact sink before proceeding.
    ``checkpoint.replace_sink`` distinguishes the legacy sink from an already observed
    replacement; the latter must be preserved, not redeployed.
    A fully downloaded original controller artifact returns ``None`` so the caller
    can use the existing original-creation admission path. Missing or ambiguous
    evidence never returns ``None``. No Cloudflare operation is performed; only
    validated checkpoint artifact members persist.
    """
    sha, rows = origin(run_id)
    recovery = artifact(rows, f"mail-fresh-bootstrap-recovery-{run_id}-1", LIMIT * 2)
    allowed = {"resume.jsonl", "preflight.jsonl", "trace-queue-provision-production.json"}
    files = members(github(f"artifacts/{recovery['id']}/zip", binary=True), allowed | ALLOWED, LIMIT * 2, 4)
    if "resume.jsonl" not in files:
        if "controller.jsonl" in files:
            return None
        raise ValueError("fresh_recovery_sink_checkpoint_unavailable")
    if not set(files) <= allowed:
        raise ValueError("fresh_recovery_sink_checkpoint_unreviewed")
    checkpoint = _sink_checkpoint(files["resume.jsonl"], sha, run_id)
    epoch = checkpoint.deployment_epoch
    if "preflight.jsonl" in files:
        preflight(files["preflight.jsonl"], sha, run_id)
    build = artifact(rows, f"worker-native-modules-{sha}", MODULE_LIMIT)
    if build["id"] != epoch.artifact_id:
        raise ValueError("fresh_recovery_original_artifact_id_mismatch")
    original(module_zip(build["id"]), epoch)
    if "trace-queue-provision-production.json" in files:
        raw = files["trace-queue-provision-production.json"]
        queue_receipt(raw)
        identities = {row["queue_name"]: row["queue_id"] for row in decode(raw)}
        expected = {"amail-trace-events": checkpoint.queue, "amail-trace-dlq": checkpoint.dlq}
        if any(identity != expected[name] for name, identity in identities.items()):
            raise ValueError("fresh_recovery_sink_queue_mismatch")
    folder = Path(folder)
    owned, resolved = (ROOT / ".temp").resolve(), folder.resolve()
    if not resolved.is_relative_to(owned) or resolved == owned or folder.exists() or folder.is_symlink():
        raise ValueError("fresh_recovery_destination_unreviewed")
    folder.mkdir(parents=True, exist_ok=False, mode=0o700)
    for name, data in files.items():
        with (folder / name).open("xb") as output:
            output.write(data)
        (folder / name).chmod(0o600)
    return checkpoint
