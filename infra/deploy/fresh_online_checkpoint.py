"""Admit the observed two-adapter online failure without replaying any write."""

from dataclasses import dataclass
from pathlib import Path

from fresh_bootstrap_contract import Epoch, ORIGINAL_DATABASE, STAGING_DATABASE
import fresh_bootstrap_recovery as recovery
from pin_staging_mail import UUID


@dataclass(frozen=True)
class OnlineCheckpoint:
    """Immutable coordinates; the caller separately proves paused scope ownership."""

    epoch: Epoch
    """Protected failed online attempt and its verified original module artifact."""
    creation_epoch: Epoch
    """Original storage creator, not the online adapter deployment source."""
    resources: dict[str, str]
    """Captured database/bucket coordinates to match against the admitted receipt."""
    adapter_versions: dict[str, str]
    """Observed mail_ingress/mail_events versions; never mutate or redeploy them."""


def journal(raw: bytes, sha: str, run_id: str) -> OnlineCheckpoint:
    """Require the exact 22-row prefix ending before capture-off could be observed."""
    rows = recovery.lines(raw, 22)
    fields = {"source_sha", "run_id", "artifact_id", "manifest_sha256", "rust", "worker_build"}
    if len(rows) != 22:
        raise ValueError("fresh_online_checkpoint_unreviewed")
    source, creation = rows[2].get("source_epoch"), rows[4].get("creation_epoch")
    resources = rows[4].get("resources")
    if (not isinstance(source, dict) or set(source) != fields
            or not isinstance(creation, dict) or set(creation) != fields
            or not isinstance(resources, dict) or set(resources) != {"database", "bucket"}):
        raise ValueError("fresh_online_checkpoint_unreviewed")
    epoch, creation_epoch = Epoch(**source), Epoch(**creation)
    if epoch.source_sha != sha or epoch.run_id != run_id or creation_epoch.run_id == run_id:
        raise ValueError("fresh_online_checkpoint_origin_mismatch")
    database = resources["database"]
    if (not isinstance(database, str) or UUID.fullmatch(database) is None
            or database in {ORIGINAL_DATABASE, STAGING_DATABASE}
            or resources["bucket"] != creation_epoch.bucket_name):
        raise ValueError("fresh_online_checkpoint_scope_unreviewed")
    phases = ("admission", "receipt_origin", "source_adoption", "capabilities", "paused_readback",
              "sending_dns", "sending_privacy", "email_queues", "mail_ingress", "mail_events",
              "mail_ingress_capture_off")
    expected = []
    for index, phase in enumerate(phases):
        base = {"schema": "mail-fresh-online-controller/v1", "phase": phase}
        if index >= 1:
            base["source_epoch"] = source
        if index >= 2:
            base.update(creation_epoch=creation, resources=resources)
        expected.extend({**base, "state": state} for state in ("intent", "observed"))
    versions = {"mail_ingress": rows[17].get("version"), "mail_events": rows[19].get("version")}
    if (any(not isinstance(version, str) or UUID.fullmatch(version) is None for version in versions.values())
            or len(set(versions.values())) != 2):
        raise ValueError("fresh_online_checkpoint_versions_unreviewed")
    expected[17].update(version=versions["mail_ingress"])
    expected[19].update(version=versions["mail_events"])
    expected[-1].update(state="failed", error_type="ValueError")
    if rows != expected:
        raise ValueError("fresh_online_checkpoint_unreviewed")
    return OnlineCheckpoint(epoch, creation_epoch, resources, versions)


def load(run_id: str, folder: Path) -> OnlineCheckpoint:
    """Verify protected immutable evidence and exclusively persist its closed journal.

    Example: ``checkpoint = load(prior_online_run, recovery.ROOT / '.temp/online/prior')``.
    The caller matches resources to a protected paused receipt and independently
    reads these exact versions. No provider read, PATCH or deployment is performed.
    """
    sha, rows = recovery.origin(run_id, job=recovery.ONLINE_JOB)
    artifact = recovery.artifact(rows, f"mail-fresh-online-recovery-{run_id}-1", recovery.LIMIT * 2)
    files = recovery.members(recovery.github(f"artifacts/{artifact['id']}/zip", binary=True),
                             {"controller.jsonl"}, recovery.LIMIT * 2, 1)
    checkpoint = journal(files["controller.jsonl"], sha, run_id)
    build = recovery.artifact(rows, f"worker-native-modules-{sha}", recovery.MODULE_LIMIT)
    if build["id"] != checkpoint.epoch.artifact_id:
        raise ValueError("fresh_recovery_original_artifact_id_mismatch")
    recovery.original(recovery.module_zip(build["id"]), checkpoint.epoch)
    folder = Path(folder)
    owned, resolved = (recovery.ROOT / ".temp").resolve(), folder.resolve()
    if not resolved.is_relative_to(owned) or resolved == owned or folder.exists() or folder.is_symlink():
        raise ValueError("fresh_recovery_destination_unreviewed")
    folder.mkdir(parents=True, exist_ok=False, mode=0o700)
    path = folder / "controller.jsonl"
    with path.open("xb") as output:
        output.write(files["controller.jsonl"])
    path.chmod(0o600)
    return checkpoint
