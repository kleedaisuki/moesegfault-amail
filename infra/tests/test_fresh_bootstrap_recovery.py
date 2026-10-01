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


if __name__ == "__main__":
    unittest.main()
