"""Admit a protected lifecycle observation separately from old-work completion.

The fixed producer is a future reviewed lifecycle integration, not the existing
bootstrap inspector's current-inventory artifact. Missing producer/proof fails
closed; no record emitted by an arbitrary workflow can grant activation.
"""

from dataclasses import dataclass
from datetime import datetime
import io
import json
from pathlib import Path
import re
import stat
import subprocess
import zipfile

from check_mail_maintenance import CADENCE, REALMS, api_config, script_name
from mail_split_transition import State
from pin_staging_mail import ACCOUNT, UUID, mail_resources

ROOT = Path(__file__).resolve().parents[2]
REPO = "kleedaisuki/moesegfault-amail"
WORKFLOW = ".github/workflows/mail-lifecycle.yml"
LIMIT = 65_536
SHA = re.compile(r"[0-9a-f]{40}\Z")
RUN = re.compile(r"[1-9][0-9]{0,19}\Z")


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    """Duplicate keys must not overwrite a realm, pin, state or proof boundary."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("lifecycle_duplicate_json_key")
        result[key] = value
    return result


def inventory(value: object, field: str) -> list[dict]:
    """Require the entire bounded list; failed or truncated reads are never absence."""
    if (not isinstance(value, dict) or not isinstance(value.get(field), list)
            or type(value.get("total_count")) is not int or value["total_count"] != len(value[field])
            or len(value[field]) > 100 or not all(isinstance(row, dict) for row in value[field])):
        raise ValueError("lifecycle_complete_inventory_required")
    return value[field]


def scripts(realm: str) -> set[str]:
    """Only the exact API/maintenance/sink product names belong to a receipt."""
    if realm not in REALMS:
        raise ValueError("lifecycle_realm_unreviewed")
    return {script_name(realm), script_name(realm, maintenance=False),
            "amail-trace-sink" + ("-staging" if realm == "staging" else "")}


@dataclass(frozen=True)
class Receipt:
    """Validated observation with original provenance; drain remains explicitly unknown.

    Canonical JSON is immutable backing storage; each value access returns an
    isolated decoded copy rather than letting a caller mutate admitted pins.
    An orchestration SHA is not a claim about already deployed binary provenance.
    """

    payload: str
    artifact_id: int

    def __post_init__(self):
        """Reject invalid backing data and prevent mutable admitted metadata aliases."""
        if (not isinstance(self.payload, str) or len(self.payload.encode()) > LIMIT
                or type(self.artifact_id) is not int or self.artifact_id <= 0):
            raise ValueError("lifecycle_receipt_storage_unreviewed")
        value = self.value
        validate(value, value.get("realm") if isinstance(value, dict) else None)

    @property
    def value(self) -> dict:
        """Return independent closed metadata; caller edits cannot mutate this receipt."""
        return json.loads(self.payload, object_pairs_hook=unique_object)

    @property
    def realm(self) -> str:
        """Return the validated fixed product realm."""
        return self.value["realm"]

    @property
    def state(self) -> State:
        """Selected persistent state is not inferred from the latest inventory."""
        return State(self.value["state"])


def validate(value: object, realm: str) -> dict:
    """Closed v1 observation schema never promotes a self-authored drain string."""
    fields = {"schema", "realm", "orchestration_sha", "run_id", "run_attempt", "state",
              "predecessor_run", "graph", "resources", "observed_at", "stop", "drain"}
    if (realm not in REALMS or not isinstance(value, dict) or set(value) != fields
            or value["schema"] != "mail-lifecycle-observation/v1" or value["realm"] != realm
            or not isinstance(value["orchestration_sha"], str) or not SHA.fullmatch(value["orchestration_sha"])
            or not isinstance(value["run_id"], str) or not RUN.fullmatch(value["run_id"])
            or type(value["run_attempt"]) is not int or value["run_attempt"] != 1
            or not isinstance(value["state"], str)
            or value["state"] not in {state.value for state in
                (State.PREPARED, State.OLD_DRAINING, State.PAUSED, State.ACTIVE, State.NEW_DRAINING)}
            or value["drain"] != {"status": "UNVERIFIED"}):
        raise ValueError("lifecycle_receipt_unreviewed")
    predecessor = value["predecessor_run"]
    if predecessor is not None and (not isinstance(predecessor, str) or not RUN.fullmatch(predecessor)
                                    or predecessor == value["run_id"]):
        raise ValueError("lifecycle_predecessor_unreviewed")
    graph = checked_graph(value["graph"], realm)
    state = State(value["state"])
    wanted = list(CADENCE) if state == State.ACTIVE else []
    if (graph["maintenance_crons"] != wanted
            or state != State.PREPARED and graph["api_crons"] != []):
        raise ValueError("lifecycle_schedules_unreviewed")
    resources = value["resources"]
    if (not isinstance(resources, dict) or set(resources) != {"database", "bucket", "queue", "dlq"}
            or any(not isinstance(resources[key], str) or ACCOUNT.fullmatch(resources[key]) is None
                   for key in ("queue", "dlq")) or resources["queue"] == resources["dlq"]
            or (resources["database"], resources["bucket"]) != mail_resources(api_config(realm))):
        raise ValueError("lifecycle_resources_unreviewed")
    observed = timestamp(value["observed_at"])
    stop = value["stop"]
    if stop is not None:
        if (not isinstance(stop, dict) or set(stop) != {"script", "acknowledged_at"}
                or stop["script"] not in (script_name(realm), script_name(realm, maintenance=False))
                or timestamp(stop["acknowledged_at"]) > observed):
            raise ValueError("lifecycle_stop_unreviewed")
    if state in (State.OLD_DRAINING, State.NEW_DRAINING):
        expected = script_name(realm, maintenance=state == State.NEW_DRAINING)
        if stop is None or stop["script"] != expected or predecessor is None:
            raise ValueError("lifecycle_stop_unreviewed")
    return value


def checked_graph(graph: object, realm: str) -> dict:
    """Check a complete observation without choosing its persistent state from inventory."""
    if (not isinstance(graph, dict) or set(graph) != {"pins", "api_crons", "maintenance_crons", "topology"}
            or graph["topology"] != "api-scheduled" or not isinstance(graph["pins"], dict)
            or set(graph["pins"]) != scripts(realm)):
        raise ValueError("lifecycle_graph_unreviewed")
    for pin in graph["pins"].values():
        if (not isinstance(pin, dict) or set(pin) != {"deployment", "version"}
                or any(not isinstance(pin[key], str) or UUID.fullmatch(pin[key]) is None
                       for key in ("deployment", "version"))):
            raise ValueError("lifecycle_pins_unreviewed")
    if (graph["maintenance_crons"] not in ([], list(CADENCE))
            or graph["api_crons"] not in ([], list(CADENCE))
            or graph["api_crons"] and graph["maintenance_crons"]):
        raise ValueError("lifecycle_schedules_unreviewed")
    return graph


def timestamp(value: object) -> datetime:
    """Use exact UTC timestamps, never an elapsed-time old-work-end admission."""
    if not isinstance(value, str):
        raise ValueError("lifecycle_time_unreviewed")
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value) is None:
        raise ValueError("lifecycle_time_unreviewed")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ValueError("lifecycle_time_unreviewed") from None


def github(suffix: str, *, binary: bool = False) -> object:
    """Bound source-owned GitHub metadata/ZIP reads and suppress arbitrary error text."""
    result = subprocess.run(["gh", "api", f"repos/{REPO}/actions/{suffix}"],
                            capture_output=True, timeout=30, check=False)
    bound = LIMIT * 2 if binary else 1_048_576
    if result.returncode or len(result.stdout) > bound:
        raise ValueError("lifecycle_github_read_failed")
    return result.stdout if binary else json.loads(result.stdout, object_pairs_hook=unique_object)


def origin(run: object, jobs: object, run_id: str, realm: str) -> str:
    """Only the exact successful protected main producer, never a research/PR run."""
    scripts(realm)
    if (not RUN.fullmatch(run_id) or not isinstance(run, dict) or type(run.get("id")) is not int
            or str(run["id"]) != run_id or type(run.get("run_attempt")) is not int
            or run["run_attempt"] != 1 or run.get("status") != "completed"
            or run.get("conclusion") != "success" or run.get("event") != "workflow_dispatch"
            or run.get("head_branch") != "main" or run.get("path") != WORKFLOW
            or not isinstance(run.get("head_sha"), str) or not SHA.fullmatch(run["head_sha"])
            or not isinstance(run.get("repository"), dict) or run["repository"].get("full_name") != REPO):
        raise ValueError("lifecycle_protected_origin_required")
    matches = [row for row in inventory(jobs, "jobs") if row.get("name") == "Mail lifecycle " + realm]
    if (len(matches) != 1 or matches[0].get("status") != "completed"
            or matches[0].get("conclusion") != "success" or matches[0].get("run_id") != int(run_id)
            or matches[0].get("head_sha") != run["head_sha"]):
        raise ValueError("lifecycle_protected_job_required")
    return run["head_sha"]


def load(run_id: str, realm: str) -> Receipt:
    """Provenance precedes decoding; receipt is not current graph or drain proof."""
    if not isinstance(run_id, str) or RUN.fullmatch(run_id) is None:
        raise ValueError("lifecycle_run_id_unreviewed")
    sha = origin(github(f"runs/{run_id}"), github(f"runs/{run_id}/attempts/1/jobs?per_page=100"), run_id, realm)
    name = f"mail-lifecycle-state-{realm}-{run_id}-1"
    matches = [row for row in inventory(github(f"runs/{run_id}/artifacts?per_page=100"), "artifacts")
               if row.get("name") == name]
    if (len(matches) != 1 or matches[0].get("expired") is not False
            or type(matches[0].get("id")) is not int or matches[0]["id"] <= 0
            or type(matches[0].get("size_in_bytes")) is not int
            or not 0 < matches[0]["size_in_bytes"] <= LIMIT * 2):
        raise ValueError("lifecycle_unique_artifact_required")
    raw = github(f"artifacts/{matches[0]['id']}/zip", binary=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        if (len(members) != 1 or members[0].filename != "receipt.json" or members[0].is_dir()
                or members[0].file_size > LIMIT
                or stat.S_IFMT(members[0].external_attr >> 16) not in (0, stat.S_IFREG)):
            raise ValueError("lifecycle_artifact_member_unreviewed")
        value = validate(json.loads(archive.read(members[0]), object_pairs_hook=unique_object), realm)
    if value["orchestration_sha"] != sha or value["run_id"] != run_id:
        raise ValueError("lifecycle_record_origin_mismatch")
    return Receipt(json.dumps(value, sort_keys=True), matches[0]["id"])
