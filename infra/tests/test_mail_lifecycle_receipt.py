"""Hosted protected receipt provenance, closed graph semantics and hostile data tests."""

from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import mail_lifecycle_receipt as record

SHA = "a" * 40
VERSION = "11111111-1111-4111-8111-111111111111"
DEPLOYMENT = "22222222-2222-4222-8222-222222222222"


def fixture(realm="staging", state="paused"):
    """Only operational metadata is used; no user/resource mutation or mailbox exists."""
    database, bucket = record.mail_resources(record.api_config(realm))
    return {"schema": "mail-lifecycle-observation/v1", "realm": realm,
            "orchestration_sha": SHA, "run_id": "123", "run_attempt": 1, "state": state,
            "predecessor_run": None, "observed_at": "2026-10-01T10:00:00Z", "stop": None,
            "drain": {"status": "UNVERIFIED"}, "graph": {
                "pins": {script: {"version": VERSION, "deployment": DEPLOYMENT} for script in record.scripts(realm)},
                "topology": "api-scheduled", "api_crons": [],
                "maintenance_crons": list(record.CADENCE) if state == "active" else []},
            "resources": {"database": database, "bucket": bucket, "queue": "a" * 32, "dlq": "b" * 32}}


def origin_fixture():
    """A successful selected protected producer remains necessary, not sufficient drain."""
    run = {"id": 123, "run_attempt": 1, "status": "completed", "conclusion": "success",
           "event": "workflow_dispatch", "head_branch": "main", "path": record.WORKFLOW,
           "head_sha": SHA, "repository": {"full_name": record.REPO}}
    jobs = {"jobs": [{"name": "Mail lifecycle staging", "run_id": 123, "head_sha": SHA,
                     "status": "completed", "conclusion": "success"}], "total_count": 1}
    return run, jobs


def archive(value, name="receipt.json"):
    """Construct a tiny ZIP in memory only; no extraction or external files exist."""
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as zipped:
        zipped.writestr(name, json.dumps(value))
    return stream.getvalue()


class MailLifecycleReceiptTests(unittest.TestCase):
    """Correct-looking JSON does not waive origin, complete read or unknown drain."""

    def test_paused_and_observed_active_keep_drain_unknown(self):
        """Observed activity is not newly admitted old-work completion."""
        for state in ("paused", "active"):
            value = fixture(state=state)
            self.assertEqual(record.validate(value, "staging")["drain"], {"status": "UNVERIFIED"})
            receipt = record.Receipt(json.dumps(value), 456)
            changed = receipt.value
            changed["graph"]["pins"].clear()
            self.assertEqual(receipt.value, value)

    def test_origin_rejects_research_pr_rerun_foreign_and_missing_job(self):
        """The bootstrap inspector is current facts, never a lifecycle/drain authority."""
        run, jobs = origin_fixture()
        self.assertEqual(record.origin(run, jobs, "123", "staging"), SHA)
        for field, value in (("path", ".github/workflows/held-production-inspection.yml"),
                             ("head_branch", "branch"), ("event", "pull_request"),
                             ("run_attempt", 2), ("run_attempt", True),
                             ("conclusion", "failure"), ("repository", {"full_name": "foreign/repo"})):
            changed = {**run, field: value}
            with self.subTest(field=field), self.assertRaises(ValueError):
                record.origin(changed, jobs, "123", "staging")
        for key, value in (("conclusion", "skipped"), ("name", "Mail lifecycle production"), ("head_sha", "b" * 40)):
            changed = deepcopy(jobs)
            changed["jobs"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                record.origin(run, changed, "123", "staging")
        with self.assertRaises(ValueError):
            record.origin(run, {**jobs, "total_count": 2}, "123", "staging")

    def test_closed_schema_trigger_resource_and_self_attestation_refuse(self):
        """Unknown/cross-realm fields and named admission strings do not create proof."""
        mutations = (
            lambda value: value.update(extra="private-provider-poison"),
            lambda value: value.update(drain={"status": "provider-attested-old-work-end"}),
            lambda value: value.update(drain={"status": "UNVERIFIED", "elapsed_minutes": 30}),
            lambda value: value.update(state="legacy-recovery"),
            lambda value: value.update(predecessor_run="123"),
            lambda value: value["resources"].update(database=record.mail_resources(record.api_config("production"))[0]),
            lambda value: value["resources"].update(dlq=value["resources"]["queue"]),
            lambda value: value["graph"].update(api_crons=list(record.CADENCE)),
            lambda value: value["graph"].update(maintenance_crons=list(record.CADENCE)),
            lambda value: value["graph"]["pins"].update(unknown={"version": VERSION, "deployment": DEPLOYMENT}),
            lambda value: value["graph"]["pins"][next(iter(value["graph"]["pins"]))].update(deployment=None),
            lambda value: value.update(observed_at="2026-10-01T1:00:00Z"),
        )
        for mutate in mutations:
            value = fixture()
            mutate(value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                record.validate(value, "staging")
        with self.assertRaises(ValueError):
            record.unique_object([("realm", "staging"), ("realm", "production")])

    def test_draining_requires_exact_acknowledged_stop_and_predecessor(self):
        """An empty trigger list alone cannot become an acknowledged drain barrier."""
        for state, maintenance in (("old-draining", False), ("new-draining", True)):
            value = fixture(state=state)
            with self.assertRaises(ValueError):
                record.validate(value, "staging")
            value.update(predecessor_run="122", stop={"script": record.script_name("staging", maintenance=maintenance),
                                                      "acknowledged_at": "2026-10-01T09:59:00Z"})
            record.validate(value, "staging")
            value["stop"]["acknowledged_at"] = "2026-10-01T10:01:00Z"
            with self.assertRaises(ValueError):
                record.validate(value, "staging")

    def test_load_admits_unique_fixed_member_with_original_source_identity(self):
        """Artifact ID/protected origin first, closed content second; no manual hash Secret."""
        run, jobs = origin_fixture()
        listing = {"artifacts": [{"name": "mail-lifecycle-state-staging-123-1", "id": 456,
                                   "expired": False, "size_in_bytes": 2048}], "total_count": 1}
        with patch.object(record, "github", side_effect=[run, jobs, listing, archive(fixture())]) as read:
            receipt = record.load("123", "staging")
        self.assertEqual((receipt.artifact_id, receipt.value), (456, fixture()))
        self.assertEqual(read.call_args.args[0], "artifacts/456/zip")
        self.assertTrue(read.call_args.kwargs["binary"])

    def test_wrong_zip_member_expired_truncated_and_wrong_source_refuse(self):
        """No alternate path, partial artifact inventory or moved source can qualify."""
        for mode in ("wrong_member", "expired", "truncated", "wrong_source"):
            run, jobs = origin_fixture()
            listing = {"artifacts": [{"name": "mail-lifecycle-state-staging-123-1", "id": 456,
                                       "expired": mode == "expired", "size_in_bytes": 2048}], "total_count": 1}
            if mode == "truncated":
                listing["total_count"] = 2
            value = fixture()
            if mode == "wrong_source":
                value["orchestration_sha"] = "b" * 40
            raw = archive(value, "../receipt.json" if mode == "wrong_member" else "receipt.json")
            with self.subTest(mode=mode), patch.object(record, "github", side_effect=[run, jobs, listing, raw]), self.assertRaises(ValueError):
                record.load("123", "staging")


if __name__ == "__main__":
    unittest.main()
