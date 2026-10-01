"""Hosted synthetic recovery admission; no provider writes or runtime deployment."""

from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import fresh_bootstrap_recovery as admission
import fresh_online_checkpoint as online_checkpoint
from fresh_mail_bootstrap import Bootstrap
from fresh_bootstrap_contract import Epoch


def zipped(files):
    """Build in-memory artifact bytes; duplicate member fixtures remain possible."""
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, data in files:
            archive.writestr(name, data)
    return output.getvalue()


def fixtures():
    """Return original protected coordinates with all seven generated tree entries."""
    sha, run = "a" * 40, "123456"
    modules = {f"{tree}/{suffix}": b"public module" for tree in admission.TREES
               for suffix in ("index.js", "worker/shim.mjs")}
    manifest = json.dumps({"schema": "worker-native-artifact/v1", "source_sha": sha, "run_id": run,
                           "run_attempt": 1, "rust": "1.98.1", "worker_build": "0.8.5",
                           "files": {k: hashlib.sha256(v).hexdigest() for k, v in modules.items()}}, sort_keys=True).encode()
    epoch = Epoch(sha, run, 88, hashlib.sha256(manifest).hexdigest(), "1.98.1")
    controller = [{"schema": "mail-fresh-controller/v1", "epoch": asdict(epoch),
                   "phase": "admission", "state": state} for state in ("intent", "observed")]
    raw = b"\n".join(json.dumps(row).encode() for row in controller) + b"\n"
    artifacts = [{"name": f"mail-fresh-bootstrap-recovery-{run}-1", "id": 77, "expired": False, "size_in_bytes": 1000},
                 {"name": f"worker-native-modules-{sha}", "id": 88, "expired": False, "size_in_bytes": 2000}]
    run_data = {"id": int(run), "run_attempt": 1, "status": "completed", "conclusion": "failure",
                "event": "workflow_dispatch", "head_branch": "main", "path": ".github/workflows/ci.yml",
                "head_sha": sha, "repository": {"full_name": admission.REPO}}
    jobs = [{"name": name, "status": "completed", "conclusion": "success", "run_id": int(run), "head_sha": sha}
            for name in admission.REQUIRED]
    jobs.append({"name": admission.JOB, "status": "completed", "conclusion": "failure", "run_id": int(run), "head_sha": sha})
    return epoch, raw, zipped([("manifest.json", manifest), *modules.items()]), artifacts, run_data, jobs


class RecoveryAdmissionTests(unittest.TestCase):
    """Original provenance precedes extraction and cannot promote write replay."""

    def setUp(self):
        """All test destinations stay under the repository's owned temporary root."""
        (ROOT / ".temp").mkdir(exist_ok=True)
        self.folder = tempfile.TemporaryDirectory(dir=ROOT / ".temp")
        self.addCleanup(self.folder.cleanup)
        self.destination = Path(self.folder.name) / "admitted"
        self.epoch, self.controller, self.modules, self.artifacts, self.run, self.jobs = fixtures()
        self.recovery = zipped([("controller.jsonl", self.controller)])

    def github(self, suffix, *, binary=False):
        """Expose only the exact fixed origin metadata and original recovery ZIP."""
        if suffix == f"runs/{self.epoch.run_id}":
            return self.run
        if suffix.endswith("/jobs?per_page=100"):
            return {"total_count": len(self.jobs), "jobs": self.jobs}
        if suffix.endswith("/artifacts?per_page=100"):
            return {"total_count": len(self.artifacts), "artifacts": self.artifacts}
        if suffix == "artifacts/77/zip" and binary:
            return self.recovery
        self.fail("Unexpected GitHub read")

    def load(self):
        """Only mocked GitHub downloads are allowed; no provider object exists."""
        with patch.object(admission, "github", side_effect=self.github), patch.object(admission, "module_zip", return_value=self.modules):
            return admission.load(self.epoch.run_id, self.destination)

    def test_failed_creator_is_recoverable_without_green_whole_run(self):
        """Failed writes must remain observable without requiring successful completion."""
        epoch, path = self.load()
        self.assertEqual(epoch, self.epoch)
        self.assertEqual(path.read_bytes(), self.controller)
        self.assertEqual(list(self.destination.iterdir()), [path])

    def test_terminal_creator_conclusions_allow_only_protected_observation(self):
        """Cancelled is terminal, but skipped or unfinished origins cannot grant reads."""
        for conclusion in ("success", "failure", "timed_out", "cancelled"):
            self.run["conclusion"] = self.jobs[-1]["conclusion"] = conclusion
            with patch.object(admission, "github", side_effect=self.github):
                self.assertEqual(admission.origin(self.epoch.run_id)[0], self.epoch.source_sha)
        for conclusion in ("skipped", None):
            self.jobs[-1]["conclusion"] = conclusion
            with patch.object(admission, "github", side_effect=self.github), self.assertRaises(ValueError):
                admission.origin(self.epoch.run_id)

    def cancel(self):
        """Model a manually cancelled original creator, not a rerun or new epoch."""
        self.run["conclusion"] = self.jobs[-1]["conclusion"] = "cancelled"

    def scope_intent(self):
        """Return a closed controller prefix interrupted while creating fresh storage."""
        rows = [{"schema": "mail-fresh-controller/v1", "epoch": asdict(self.epoch),
                 "phase": phase, "state": state}
                for phase, state in (("old_scope", "intent"), ("old_scope", "observed"),
                                     ("create_scope", "intent"))]
        return self.controller + b"\n".join(json.dumps(row).encode() for row in rows) + b"\n"

    def scope_prefix(self):
        """Bind a captured D1 response while leaving the R2 submission ambiguous."""
        database = "00000000-0000-0000-0000-000000000002"
        rows = [{"schema": "mail-fresh-scope-recovery/v1", "event": "ownership",
                 "epoch": asdict(self.epoch), "database_name": self.epoch.database_name,
                 "bucket": self.epoch.bucket_name, "may_replay_write": False},
                {"event": "d1_submit_intent", "name": self.epoch.database_name, "attempt": 1},
                {"event": "d1_created", "database": database, "created_at": "2026-10-01T00:00:00Z"},
                {"event": "d1_readback_verified", "database": database},
                {"event": "r2_submit_intent", "name": self.epoch.bucket_name, "attempt": 1}]
        return b"\n".join(json.dumps(row).encode() for row in rows) + b"\n"

    def test_cancelled_creator_observes_only_captured_identity_without_writes(self):
        """A valid immutable interruption prefix permits one GET, not guessed ownership."""
        self.cancel()
        self.recovery = zipped([("controller.jsonl", self.scope_intent()),
                                ("controller.scope.jsonl", self.scope_prefix())])
        epoch, path = self.load()
        database = "00000000-0000-0000-0000-000000000002"
        reads = []

        class ReadOnlyProvider:
            """No write methods exist; unexpected or guessed reads fail the fixture."""

            account = "a" * 32

            def get(inner, route):
                """Return only the original positively captured D1 identity."""
                reads.append(route)
                self.assertEqual(route, f"accounts/{inner.account}/d1/database/{database}")
                return {"uuid": database, "name": epoch.database_name,
                        "created_at": "2026-10-01T00:00:00Z"}

        receipt = self.destination / "never-receipt.json"
        result = Bootstrap(ReadOnlyProvider(), None, epoch, path, receipt).recover()
        self.assertEqual(len(reads), 1)
        self.assertEqual(result["scope"]["database"], "CREATED_IDENTITY_OBSERVED")
        self.assertEqual(result["scope"]["bucket"], "UNKNOWN")
        self.assertEqual(result["scope"]["adoption"], "NOT_GRANTED")
        self.assertIs(result["may_replay_write"], False)
        self.assertEqual(result["activation"], "NOT_GRANTED")
        self.assertEqual(result["receipt"], "NOT_GRANTED")
        self.assertEqual(result["pins"], {})
        self.assertFalse(receipt.exists())

    def test_cancelled_creator_without_recovery_artifact_is_typed_unavailable(self):
        """Cancellation before upload is unresolved, never a request to create again."""
        self.cancel()
        self.artifacts.pop(0)
        with self.assertRaisesRegex(ValueError, "artifact_unavailable"):
            self.load()
        self.assertFalse(self.destination.exists())

    def test_cancelled_creator_partial_admission_is_typed_unavailable(self):
        """A captured intent alone cannot replace original positive source admission."""
        self.cancel()
        self.recovery = zipped([("controller.jsonl", self.controller.splitlines()[0])])
        with self.assertRaisesRegex(ValueError, "admission_unavailable"):
            self.load()
        self.assertFalse(self.destination.exists())

    def test_cancelled_creator_missing_scope_prefix_is_typed_unavailable(self):
        """The controller's submit intent cannot reconstruct a missing scope journal."""
        self.cancel()
        self.recovery = zipped([("controller.jsonl", self.scope_intent())])
        with self.assertRaisesRegex(ValueError, "scope_unavailable"):
            self.load()
        self.assertFalse(self.destination.exists())

    def test_cancelled_creator_truncated_or_malformed_journals_are_rejected(self):
        """Incomplete bytes and forged prefixes are not repaired into owned evidence."""
        self.cancel()
        for raw in (self.scope_prefix()[:-3], self.scope_prefix().replace(b'"attempt": 1', b'"attempt": 2'),
                    self.scope_prefix().replace(self.epoch.run_id.encode(), b'123457')):
            self.recovery = zipped([("controller.jsonl", self.scope_intent()),
                                    ("controller.scope.jsonl", raw)])
            with self.subTest(scope=raw), self.assertRaises(ValueError):
                self.load()
            self.assertFalse(self.destination.exists())
        self.recovery = zipped([("controller.jsonl", self.scope_intent()[:-3])])
        with self.assertRaisesRegex(ValueError, "json_unreviewed"):
            self.load()

    def test_cancelled_creator_requires_all_original_successful_source_gates(self):
        """A terminal writer cannot bypass cancelled, missing or unfinished checks."""
        self.cancel()
        for conclusion in ("failure", "cancelled", "skipped", None):
            self.jobs[0]["conclusion"] = conclusion
            with self.subTest(conclusion=conclusion), self.assertRaisesRegex(ValueError, "full_source_required"):
                self.load()
        self.jobs[0]["conclusion"] = "success"
        self.jobs[0]["status"] = "in_progress"
        with self.assertRaisesRegex(ValueError, "full_source_required"):
            self.load()
        self.assertFalse(self.destination.exists())

    def test_unprotected_run_coordinates_are_rejected(self):
        """A PR, rerun, wrong workflow or mismatched repository cannot grant recovery."""
        self.cancel()
        for key, value in (("event", "push"), ("head_branch", "topic"), ("run_attempt", 2),
                           ("run_attempt", True), ("path", ".github/workflows/native-tracing-canary.yml"),
                           ("repository", {"full_name": "other/repo"}), ("status", "in_progress")):
            old = self.run[key]
            self.run[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.load()
            self.run[key] = old
        self.assertFalse(self.destination.exists())

    def test_duplicate_or_mismatched_creator_job_is_rejected(self):
        """Job name is unique and must independently bind source and run."""
        self.cancel()
        self.jobs.append(dict(self.jobs[-1]))
        with self.assertRaises(ValueError):
            self.load()
        self.jobs.pop()
        self.jobs[-1]["head_sha"] = "b" * 40
        with self.assertRaises(ValueError):
            self.load()

    def test_all_original_source_gates_must_have_succeeded(self):
        """The failed writer is distinct from failed or skipped prerequisite checks."""
        self.jobs[0]["conclusion"] = "failure"
        with self.assertRaises(ValueError):
            self.load()
        self.assertFalse(self.destination.exists())

    def test_original_artifact_id_cannot_be_replaced(self):
        """Matching names and source strings cannot replace the original immutable ID."""
        self.cancel()
        self.artifacts[1]["id"] += 1
        with self.assertRaisesRegex(ValueError, "artifact_id_mismatch"):
            self.load()

    def test_duplicate_expired_or_oversized_artifact_is_rejected(self):
        """Complete artifact listings prevent picking a convenient candidate."""
        self.cancel()
        for key, value in (("expired", True), ("size_in_bytes", admission.LIMIT * 2 + 1), ("id", True)):
            old = self.artifacts[0][key]
            self.artifacts[0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.load()
            self.artifacts[0][key] = old
        self.artifacts.append(dict(self.artifacts[0]))
        with self.assertRaises(ValueError):
            self.load()

    def test_missing_controller_and_early_admission_refusal_are_typed(self):
        """Preflight evidence cannot substitute for a positively admitted epoch."""
        self.recovery = zipped([("trace-queue-provision-production.json", b"[]")])
        with self.assertRaisesRegex(ValueError, "controller_unavailable"):
            self.load()
        self.recovery = zipped([("controller.jsonl", self.controller.splitlines()[0])])
        with self.assertRaisesRegex(ValueError, "admission_unavailable"):
            self.load()
        self.assertFalse(self.destination.exists())

    def test_preflight_is_closed_but_not_admission_authority(self):
        """A valid initial refusal without a controller remains typed unavailable."""
        row = {"schema": "mail-fresh-preflight/v1", "state": "intent", "source_sha": self.epoch.source_sha,
               "run_id": self.epoch.run_id, "activation": "NOT_GRANTED", "replay": "NOT_GRANTED"}
        raw = json.dumps(row).encode()
        self.recovery = zipped([("preflight.jsonl", raw)])
        with self.assertRaisesRegex(ValueError, "controller_unavailable"):
            self.load()
        self.recovery = zipped([("controller.jsonl", self.controller), ("preflight.jsonl", raw)])
        self.load()
        self.assertEqual((self.destination / "preflight.jsonl").read_bytes(), raw)
        for wrong in ({**row, "message": "private"}, {**row, "source_sha": "b" * 40}, {**row, "state": "failed"}):
            with self.assertRaises(ValueError):
                admission.preflight(json.dumps(wrong).encode(), self.epoch.source_sha, self.epoch.run_id)

    def test_closed_controller_refuses_payload_and_epoch_aliases(self):
        """Free-form error messages, credentials or extra fields never reach disk."""
        row = json.loads(self.controller.splitlines()[0])
        row["message"] = "private content"
        raw = json.dumps(row).encode() + b"\n" + self.controller.splitlines()[1]
        with self.assertRaises(ValueError):
            admission.controller(raw, self.epoch.source_sha, self.epoch.run_id)
        row.pop("message")
        row["epoch"]["source_sha"] = "b" * 40
        with self.assertRaises(ValueError):
            admission.controller(json.dumps(row).encode(), self.epoch.source_sha, self.epoch.run_id)

    def test_json_duplicate_keys_and_nonstandard_constants_are_rejected(self):
        """JSON parsing cannot erase conflicting provenance or permit NaN values."""
        for raw in (b'{"epoch":{},"epoch":{}}', b'{"value":NaN}'):
            with self.assertRaises(ValueError):
                admission.decode(raw)

    def test_zip_unknown_duplicates_traversal_and_directory_are_rejected(self):
        """Known flat artifact names are the extraction boundary."""
        for entries in ([('unknown.txt', b'x')], [('controller.jsonl', b'x'), ('controller.jsonl', b'y')],
                        [('../controller.jsonl', b'x')], [('controller.jsonl/', b'x')]):
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                admission.members(zipped(entries), admission.ALLOWED, admission.LIMIT * 2, 3)

    def test_zip_symlink_is_rejected(self):
        """Unix symlink metadata cannot redirect admitted writes."""
        info = zipfile.ZipInfo('controller.jsonl')
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaises(ValueError):
            admission.members(zipped([(info, b'target')]), admission.ALLOWED, admission.LIMIT * 2, 3)

    def test_original_manifest_and_module_bytes_are_verified(self):
        """An authentic artifact ID is not permission to ignore corrupted download bytes."""
        admission.original(self.modules, self.epoch)
        with zipfile.ZipFile(io.BytesIO(self.modules)) as archive:
            entries = [(row.filename, archive.read(row)) for row in archive.infolist()]
        entries[-1] = (entries[-1][0], b'changed')
        with self.assertRaises(ValueError):
            admission.original(zipped(entries), self.epoch)
        entries[0] = ('manifest.json', b'{}')
        with self.assertRaises(ValueError):
            admission.original(zipped(entries), self.epoch)

    def test_existing_destination_is_never_overwritten(self):
        """An admitted journal is persisted once; subsequent runs use another owned folder."""
        self.load()
        with self.assertRaisesRegex(ValueError, "destination_unreviewed"):
            self.load()
        self.assertEqual((self.destination / 'controller.jsonl').read_bytes(), self.controller)

    def test_destination_outside_owned_temp_is_rejected(self):
        """Do not put project evidence outside its repository temporary root."""
        self.destination = ROOT / 'unowned-recovery-fixture'
        with self.assertRaisesRegex(ValueError, "destination_unreviewed"):
            self.load()
        self.assertFalse(self.destination.exists())

    def test_closed_queue_receipt_rejects_private_fields_and_duplicate_names(self):
        """Only the existing fixed two source-owned Queue IDs are persisted."""
        row = {"target": "production", "queue_name": "amail-trace-events", "queue_id": "a" * 32}
        admission.queue_receipt(json.dumps([row]).encode())
        for rows in ([row, row], [row, {**row, "queue_name": "amail-trace-dlq"}], [{**row, 'body': 'private'}], [{**row, 'target': 'staging'}]):
            with self.assertRaises(ValueError):
                admission.queue_receipt(json.dumps(rows).encode())

    def test_scope_ownership_and_creation_prefix_are_closed(self):
        """The optional scope journal must bind this epoch, not a caller-supplied store."""
        row = {"schema": "mail-fresh-scope-recovery/v1", "event": "ownership", "epoch": asdict(self.epoch),
               "database_name": self.epoch.database_name, "bucket": self.epoch.bucket_name, "may_replay_write": False}
        admission.scope_journal(json.dumps(row).encode(), self.epoch)
        with self.assertRaises(ValueError):
            admission.scope_journal(json.dumps({**row, 'body': 'private'}).encode(), self.epoch)
        wrong = json.dumps(row).encode() + b'\n' + b'{"event":"r2_submit_intent","name":"other","attempt":1}'
        with self.assertRaises(ValueError):
            admission.scope_journal(wrong, self.epoch)

    def sink_checkpoint(self, replacement=False, all_workers=False):
        """Reproduce the three observed production prefixes with synthetic module bytes."""
        creation = Epoch("87acaaa4ddbc2c22233fb5e5fc74f1778f86f3aa", "36912824752",
                         11188385927, "ea687638b68ec1791c9754c92e0df9aad3105a909cf92163d1dc68140a4619ec",
                         "1.98.1")
        base = {"schema": "mail-fresh-resume/v1", "deployment_epoch": asdict(self.epoch),
                "creation_run": creation.run_id}
        rows = [{**base, "phase": phase, "state": state}
                for phase in ("ownership", "migrate", "queues", "sink", "sink_readback")
                for state in ("intent", "observed")]
        rows[1].update(creation_epoch=asdict(creation), schema_prefix=0,
                       scope={"epoch": asdict(creation), "database": "d9be9bb4-5a73-4223-85d6-b04763e6f03b",
                              "database_created_at": "2026-10-01T19:20:25Z",
                              "bucket_created_at": "2026-10-01T19:20:26Z"})
        rows[5].update(queue="e7a80fba65b0471aa4a267527d83d2d3", dlq="7eab75daab9345e9ad6d0c1fa6f0e37c")
        rows[7].update(version="c56c8062-ef7f-48ed-b91f-91394b03cd69")
        rows[9].update(state="failed", error_type="FreshError")
        if replacement or all_workers:
            rows[1]["schema_prefix"] = 11
            source = Epoch("b2b64ae76fb8096cc566f50b6510e2e6522822ec", "36916937613", 11190151442,
                           "ed1b076b54fbee527c33378021e5a391eea6ea7eff2fa371acbba4afa2cee7c3", "1.98.1")
            rows = [rows[0], rows[1], {**base, "phase": "retained_sink", "state": "intent"},
                    {**base, "phase": "retained_sink", "state": "observed", "source_epoch": asdict(source),
                     "version": rows[7]["version"], "queue": rows[5]["queue"], "dlq": rows[5]["dlq"]},
                    {**base, "phase": "sink_replacement", "state": "intent", "previous_version": rows[7]["version"]},
                    {**base, "phase": "sink_replacement", "state": "observed", "version": "d372b6f0-42ed-4536-b7ee-15273b50d6a3"},
                    rows[8], rows[9]]
        if all_workers:
            source = Epoch("56fdf41ffe5463fa211b9ce9807da3cae80d5959", "36925573432", 11194156308,
                           "dd02a72f7d20d2f15c8f4669c3bc0bc1088950bf858e361bb42d60ebfde83508", "1.98.1")
            rows[3].update(source_epoch=asdict(source), version=rows[5]["version"])
            rows = rows[:4] + [
                {**base, "phase": "maintenance", "state": "intent"},
                {**base, "phase": "maintenance", "state": "observed", "version": "d1f2946b-4001-4a82-bb75-3c30441b25a8"},
                {**base, "phase": "api", "state": "intent"},
                {**base, "phase": "api", "state": "observed", "version": "a2eba957-43e1-4ba1-af67-44d368f03b6f"},
                {**base, "phase": "receipt", "state": "intent"},
                {**base, "phase": "receipt", "state": "failed", "error_type": "ValueError"}]
        return rows

    def load_checkpoint(self, rows, queue=None):
        """Exercise protected admission using only existing mocked immutable reads."""
        raw = b"\n".join(json.dumps(row).encode() for row in rows) + b"\n"
        entries = [("resume.jsonl", raw)]
        if queue is not None:
            entries.append(("trace-queue-provision-production.json", json.dumps(queue).encode()))
        self.recovery = zipped(entries)
        with patch.object(admission, "github", side_effect=self.github), patch.object(
                admission, "module_zip", return_value=self.modules):
            return admission.load_sink_checkpoint(self.epoch.run_id, self.destination)

    def settings_checkpoint(self):
        """Reproduce the six actual rows after the maintenance settings PATCH."""
        rows = self.sink_checkpoint(all_workers=True)
        base = {key: rows[0][key] for key in ("schema", "deployment_epoch", "creation_run")}
        deployed = Epoch("024aae8cb31fe063ffe4581a85e8e9e8edbec097", "36927505375", 11194482853,
                         "ef9142f6ad30b37f7f9aab6a2e8cc286fea626e9474ec5d9c84d0ae10675c449", "1.98.1")
        workers = {"amail-trace-sink": {"source_epoch": rows[3]["source_epoch"], "version": rows[3]["version"]},
                   "amail-mail-maintenance": {"source_epoch": asdict(deployed), "version": rows[5]["version"]},
                   "amail-mail": {"source_epoch": asdict(deployed), "version": rows[7]["version"]}}
        return rows[:2] + [
            {**base, "phase": "retained_workers", "state": "intent"},
            {**base, "phase": "retained_workers", "state": "observed", "workers": workers,
             "queue": rows[3]["queue"], "dlq": rows[3]["dlq"]},
            {**base, "phase": "maintenance_capture_off", "state": "intent",
             "worker_id": "d7f826f3eba3497aae6c80ee771d6ca4", "version": rows[5]["version"]},
            {**base, "phase": "maintenance_capture_off", "state": "failed", "error_type": "ValueError"}]

    def test_settings_failure_retains_worker_sources_and_rejects_ambiguous_suffix(self):
        """The latest writer is admitted without attributing retained binaries to it."""
        rows = self.settings_checkpoint()
        checkpoint = self.load_checkpoint(rows)
        roles = {"sink": "amail-trace-sink", "maintenance": "amail-mail-maintenance", "api": "amail-mail"}
        self.assertEqual(checkpoint.deployment_epoch, self.epoch)
        self.assertEqual(checkpoint.worker_epochs, {role: Epoch(**rows[3]["workers"][script]["source_epoch"])
                                                  for role, script in roles.items()})
        self.assertEqual(checkpoint.pins, {role: rows[3]["workers"][script]["version"] for role, script in roles.items()})
        self.assertEqual(checkpoint.sink_epoch, checkpoint.worker_epochs["sink"])
        self.assertFalse(checkpoint.replace_sink)
        self.assertEqual(admission.lines((self.destination / "resume.jsonl").read_bytes(), 10), rows)
        self.destination = Path(self.folder.name) / "rejected-settings"
        for index, key, value in ((4, "worker_id", "wrong"), (4, "version", checkpoint.pins["api"]),
                                  (5, "state", "observed"), (5, "error_type", "FreshError"),
                                  (3, "source_epoch", asdict(self.epoch)), (1, "schema_prefix", True),
                                  (4, "phase", "receipt")):
            changed = self.settings_checkpoint()
            changed[index][key] = value
            with self.subTest(index=index, key=key), self.assertRaises(ValueError):
                self.load_checkpoint(changed)
        for source in (asdict(self.epoch), rows[1]["creation_epoch"]):
            changed = self.settings_checkpoint()
            changed[3]["workers"]["amail-mail"]["source_epoch"] = source
            with self.assertRaises(ValueError):
                self.load_checkpoint(changed)
        changed = self.settings_checkpoint()
        del changed[3]["workers"]["amail-mail"]
        with self.assertRaises(ValueError):
            self.load_checkpoint(changed)
        self.assertFalse(self.destination.exists())

    def test_online_checkpoint_admits_only_two_observed_adapters_before_capture_failure(self):
        """The actual 22-row prefix binds protected modules, original stores and pins."""
        creation = self.sink_checkpoint()[1]["creation_epoch"]
        resources = {"database": "d9be9bb4-5a73-4223-85d6-b04763e6f03b",
                     "bucket": Epoch(**creation).bucket_name}
        phases = ("admission", "receipt_origin", "source_adoption", "capabilities", "paused_readback",
                  "sending_dns", "sending_privacy", "email_queues", "mail_ingress", "mail_events", "mail_ingress_capture_off")
        rows = []
        for index, phase in enumerate(phases):
            base = {"schema": "mail-fresh-online-controller/v1", "phase": phase}
            if index >= 1:
                base["source_epoch"] = asdict(self.epoch)
            if index >= 2:
                base.update(creation_epoch=creation, resources=resources)
            rows.extend({**base, "state": state} for state in ("intent", "observed"))
        versions = {"mail_ingress": "5c296407-5048-43b3-aad6-ac106676e7f2",
                    "mail_events": "7fa0c130-d4bc-45c4-8c22-c16293821df8"}
        rows[17].update(version=versions["mail_ingress"])
        rows[19].update(version=versions["mail_events"])
        rows[-1].update(state="failed", error_type="ValueError")
        raw = b"\n".join(json.dumps(row).encode() for row in rows) + b"\n"
        self.jobs[-1]["name"] = admission.ONLINE_JOB
        self.artifacts[0]["name"] = f"mail-fresh-online-recovery-{self.epoch.run_id}-1"
        self.recovery = zipped([("controller.jsonl", raw)])
        with patch.object(admission, "github", side_effect=self.github), patch.object(admission, "module_zip", return_value=self.modules):
            result = online_checkpoint.load(self.epoch.run_id, self.destination)
        self.assertEqual(result, online_checkpoint.OnlineCheckpoint(self.epoch, Epoch(**creation), resources, versions))
        self.assertEqual((self.destination / "controller.jsonl").read_bytes(), raw)
        for index, key, value in ((17, "state", "failed"), (19, "version", versions["mail_ingress"]),
                                  (20, "worker_id", "a" * 32), (21, "state", "observed"),
                                  (21, "error_type", "FreshError"), (12, "phase", "unknown_write"),
                                  (0, "source_epoch", asdict(self.epoch))):
            changed = json.loads(json.dumps(rows))
            changed[index][key] = value
            with self.subTest(index=index, key=key), self.assertRaises(ValueError):
                online_checkpoint.journal(b"\n".join(json.dumps(row).encode() for row in changed),
                                          self.epoch.source_sha, self.epoch.run_id)
        for changed in (rows[:-1], rows + [rows[-1]]):
            with self.assertRaises(ValueError):
                online_checkpoint.journal(b"\n".join(json.dumps(row).encode() for row in changed),
                                          self.epoch.source_sha, self.epoch.run_id)
        self.run["conclusion"] = "success"
        with patch.object(admission, "github", side_effect=self.github), self.assertRaises(ValueError):
            online_checkpoint.load(self.epoch.run_id, Path(self.folder.name) / "rejected-online")

    def test_known_sink_readback_failure_admits_exact_observed_coordinates(self):
        """The actual failure shape yields sink coordinates, not replacement creation proof."""
        for replacement, all_workers, queue_index, sink_index in ((False, False, 5, 7), (True, False, 3, 5), (False, True, 3, 3)):
            rows = self.sink_checkpoint(replacement, all_workers)
            self.destination = Path(self.folder.name) / f"admitted-{replacement}-{all_workers}"
            queue = [{"target": "production", "queue_name": name, "queue_id": rows[queue_index][key]}
                     for name, key in (("amail-trace-events", "queue"), ("amail-trace-dlq", "dlq"))]
            result = self.load_checkpoint(rows, queue)
            pins = {"sink": rows[sink_index]["version"]}
            if all_workers:
                pins.update(maintenance=rows[5]["version"], api=rows[7]["version"])
            sink_epoch = Epoch(**rows[3]["source_epoch"]) if all_workers else self.epoch
            self.assertEqual(result, admission.Checkpoint("36912824752", self.epoch, sink_epoch, pins,
                             rows[queue_index]["queue"], rows[queue_index]["dlq"], not (replacement or all_workers)))
            self.assertEqual(admission.lines((self.destination / "resume.jsonl").read_bytes(), 10), rows)
            self.assertEqual({path.name for path in self.destination.iterdir()},
                             {"resume.jsonl", "trace-queue-provision-production.json"})
        self.assertNotIn("resume.jsonl", admission.ALLOWED)
        self.recovery = zipped([("controller.jsonl", self.controller)])
        with patch.object(admission, "github", side_effect=self.github):
            self.assertIsNone(admission.load_sink_checkpoint(self.epoch.run_id, self.destination))

    def test_sink_checkpoint_refuses_tamper_unknown_writes_and_missing_observation(self):
        """Closed checkpoints and immutable modules gate persistence before any replay."""
        mutations = ((7, "state", "failed"), (6, "phase", "maintenance"),
                     (7, "version", "not-a-version"), (9, "error_type", "OtherError"),
                     (1, "schema_prefix", True), (0, "creation_run", self.epoch.run_id),
                     (3, "message", "private payload"))
        for index, key, value in mutations:
            rows = self.sink_checkpoint()
            rows[index][key] = value
            with self.subTest(key=key, index=index), self.assertRaises(ValueError):
                self.load_checkpoint(rows)
            self.assertFalse(self.destination.exists())
        for index, key, value in ((1, "schema_prefix", 0), (4, "previous_version", "a" * 36),
                                  (5, "state", "failed"), (4, "phase", "sink"),
                                  (5, "version", "c56c8062-ef7f-48ed-b91f-91394b03cd69"),
                                  (3, "source_epoch", asdict(self.epoch))):
            rows = self.sink_checkpoint(replacement=True)
            rows[index][key] = value
            with self.subTest(replacement=True, index=index, key=key), self.assertRaises(ValueError):
                self.load_checkpoint(rows)
            self.assertFalse(self.destination.exists())
        for index, key, value in ((5, "state", "failed"), (7, "version", "d1f2946b-4001-4a82-bb75-3c30441b25a8"),
                                  (9, "error_type", "FreshError"), (6, "phase", "sink_replacement"),
                                  (3, "source_epoch", asdict(self.epoch)), (1, "schema_prefix", 0)):
            rows = self.sink_checkpoint(all_workers=True)
            rows[index][key] = value
            with self.subTest(all_workers=True, index=index, key=key), self.assertRaises(ValueError):
                self.load_checkpoint(rows)
            self.assertFalse(self.destination.exists())
        rows = self.sink_checkpoint()
        rows[1]["creation_epoch"]["run_id"] = "36912824753"
        rows[1]["scope"]["epoch"] = dict(rows[1]["creation_epoch"])
        with self.assertRaises(ValueError):
            self.load_checkpoint(rows)
        rows = self.sink_checkpoint()
        for changed in (rows[:7] + rows[8:], rows + [{**rows[-1], "phase": "api"}]):
            with self.assertRaises(ValueError):
                self.load_checkpoint(changed)
        bad_queue = [{"target": "production", "queue_name": "amail-trace-events", "queue_id": "a" * 32}]
        with self.assertRaisesRegex(ValueError, "sink_queue_mismatch"):
            self.load_checkpoint(rows, bad_queue)
        self.artifacts[1]["id"] += 1
        with self.assertRaisesRegex(ValueError, "artifact_id_mismatch"):
            self.load_checkpoint(rows)
        self.assertFalse(self.destination.exists())

        self.artifacts[1]["id"] -= 1
        for entries in ([("preflight.jsonl", b"{}")], [("unknown.jsonl", b"{}")],
                        [("controller.jsonl", self.controller), ("resume.jsonl", b"{}")]):
            self.recovery = zipped(entries)
            with patch.object(admission, "github", side_effect=self.github), self.assertRaises(ValueError):
                admission.load_sink_checkpoint(self.epoch.run_id, self.destination)
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
