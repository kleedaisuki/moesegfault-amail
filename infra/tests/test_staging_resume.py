"""Bounded immutable staging interruption provenance, with no provider operations."""
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import staging_resume as resume


class StagingResumeTests(unittest.TestCase):
    """Reject broader recovery epochs, changed runtime and forged ownership."""

    def run_metadata(self):
        """Return the one synthetic reviewed origin's public coordinates."""
        return {"id": int(resume.ORIGIN_RUN), "run_attempt": 1, "status": "completed",
                "conclusion": "failure", "event": "workflow_dispatch", "head_branch": resume.BRANCH,
                "head_sha": resume.ORIGIN_SHA, "path": ".github/workflows/ci.yml",
                "repository": {"full_name": resume.REPO}}

    def jobs(self):
        """Construct complete successful source gates plus the failed sink boundary."""
        listing = [{"name": name, "status": "completed", "conclusion": "success"}
                   for name in resume.required_jobs([])]
        listing += [{"name": name, "status": "completed", "conclusion": "skipped"} for name in resume.SKIPPED]
        listing.append({"name": resume.SINK_JOB, "status": "completed", "conclusion": "failure",
                        "id": 234, "run_id": int(resume.ORIGIN_RUN), "head_sha": resume.ORIGIN_SHA,
                        "steps": [{"name": resume.DEPLOY_STEP, "status": "completed", "conclusion": "success"}]})
        return {"total_count": len(listing), "jobs": listing}

    def predecessor(self):
        """The reviewed origin includes immutable runtime-model projection."""
        return {"schema": "staging-predecessor/v1", "source_sha": resume.ORIGIN_SHA,
                "run_id": resume.ORIGIN_RUN, "rollout": "legacy", "old_usage_model": "standard",
                "scripts": {"amail-mail-staging": {"present": True, "deployment": resume.API_DEPLOYMENT,
                            "version": resume.API_VERSION, "handlers": ["fetch", "scheduled"],
                            "crons": ["*/5 * * * *"], "capture_off": True, "usage_model": "standard"},
                            "amail-mail-maintenance-staging": {"present": False},
                            "amail-trace-sink-staging": {"present": False},
                            "amail-inbound-staging": {"present": True}, "amail-events-staging": {"present": True}},
                "queues": {name: {"present": False} for name in ("amail-trace-events-staging", "amail-trace-dlq-staging")}}

    def log(self):
        """Provider prose surrounding a typed span is not copied to the result."""
        row = {"schema": "control-plane-span/v1", "event": "control_plane_end", "operation": "workers.deploy",
               "phase": "submit", "realm": "staging", "component": "trace_sink", "outcome": "success",
               "version": resume.SINK_VERSION, "version_count": 1, "process_exit_code": 0,
               "source_sha": resume.ORIGIN_SHA, "run_id": resume.ORIGIN_RUN,
               "run_attempt": "1", "job": "staging-trace-sink"}
        return b"private arbitrary log prose\n2026-10-03T00:00:00Z " + json.dumps(row).encode() + b"\n"

    def zip(self, names):
        """Produce small in-memory ZIP fixtures without touching provider state."""
        destination = io.BytesIO()
        with zipfile.ZipFile(destination, "w") as archive:
            for name, content in names:
                archive.writestr(name, content)
        return destination.getvalue()

    def test_only_reviewed_terminal_failed_origin(self):
        """Success, reruns, other branches/repositories cannot grant partial authority."""
        self.assertEqual(resume.origin(self.run_metadata(), self.jobs(), resume.ORIGIN_RUN)["id"], 234)
        for key, value in (("conclusion", "success"), ("status", "in_progress"), ("run_attempt", 2),
                           ("head_branch", "main"), ("head_sha", "a" * 40), ("event", "push"),
                           ("repository", {"full_name": "other/repo"})):
            run = dict(self.run_metadata(), **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                resume.origin(run, self.jobs(), resume.ORIGIN_RUN)

    def test_complete_full_gates_and_no_later_writer(self):
        """Every source lane and skipped later deploy is mandatory, not inferred."""
        for name in resume.required_jobs([]) | resume.SKIPPED | {resume.SINK_JOB}:
            jobs = self.jobs()
            row = next(row for row in jobs["jobs"] if row["name"] == name)
            row["conclusion"] = "success" if name in resume.SKIPPED or name == resume.SINK_JOB else "skipped"
            with self.subTest(name=name), self.assertRaises(ValueError):
                resume.origin(self.run_metadata(), jobs, resume.ORIGIN_RUN)
        jobs = self.jobs()
        jobs["total_count"] += 1
        with self.assertRaises(ValueError):
            resume.origin(self.run_metadata(), jobs, resume.ORIGIN_RUN)

    def test_sink_step_positive_success_required(self):
        """A failed or duplicate submit step cannot be reconstructed from a UUID."""
        for conclusion in ("failure", "skipped", None):
            jobs = self.jobs()
            jobs["jobs"][-1]["steps"][0]["conclusion"] = conclusion
            with self.assertRaises(ValueError):
                resume.origin(self.run_metadata(), jobs, resume.ORIGIN_RUN)

    def test_typed_single_successful_sink_submit(self):
        """Repeated submit and ambiguous exit remain manual recovery, not replay."""
        self.assertEqual(resume.sink_log(self.log()), resume.SINK_VERSION)
        for raw in (self.log() * 2, b"Version ID: " + resume.SINK_VERSION.encode(),
                    self.log().replace(b'"success"', b'"failure"'),
                    self.log().replace(b'"version_count": 1', b'"version_count": true'),
                    self.log().replace(resume.ORIGIN_SHA.encode(), b"a" * 40)):
            with self.assertRaises(ValueError):
                resume.sink_log(raw)

    def test_exact_legacy_predecessor_before_any_write(self):
        """Existing maintenance, queues or changed API capabilities forbid adoption."""
        self.assertEqual(resume.predecessor(self.predecessor())["rollout"], "legacy")
        for path, value in (("rollout", "split"), ("old_usage_model", "bundled"), ("run_id", "12")):
            old = self.predecessor()
            old[path] = value
            with self.assertRaises(ValueError):
                resume.predecessor(old)
        for key, value in (("version", "a" * 36), ("crons", []), ("capture_off", False)):
            old = self.predecessor()
            old["scripts"]["amail-mail-staging"][key] = value
            with self.assertRaises(ValueError):
                resume.predecessor(old)
        old = self.predecessor()
        old["queues"]["amail-trace-dlq-staging"] = {"present": True}
        with self.assertRaises(ValueError):
            resume.predecessor(old)

    def test_exact_two_distinct_owned_queues(self):
        """Names, realm, IDs and multiplicity all belong to the immutable intent."""
        expected = [{"target": "staging", "queue_name": name, "queue_id": identity} for name, identity in
                    (("amail-trace-events-staging", resume.QUEUE), ("amail-trace-dlq-staging", resume.DLQ))]
        resume.provision(expected)
        resume.provision(expected[::-1])
        for invalid in (expected[:1], expected + expected[:1], [expected[0], expected[0]],
                        [dict(expected[0], target="production"), expected[1]],
                        [dict(expected[0], queue_id="a" * 32), expected[1]]):
            with self.assertRaises(ValueError):
                resume.provision(invalid)

    def test_bounded_exact_archive_member(self):
        """Traversal, extra members, duplicates and duplicate JSON keys fail closed."""
        listing = [{"name": "owned", "id": 1, "expired": False, "size_in_bytes": 250}]
        raw = self.zip([("receipt.json", b'{"good": true}')])
        with patch.object(resume, "github", return_value=raw):
            self.assertEqual(resume.artifact_value(listing, "owned", "receipt.json"), {"good": True})
        for entries in ([('../receipt.json', b'{}')], [('receipt.json', b'{}'), ('extra.json', b'{}')],
                        [('receipt.json', b'{"x":1,"x":2}')]):
            with patch.object(resume, "github", return_value=self.zip(entries)), self.assertRaises(ValueError):
                resume.artifact_value(listing, "owned", "receipt.json")
        for field, value in (("expired", True), ("size_in_bytes", 1_000_000), ("id", True)):
            with self.assertRaises(ValueError):
                resume.artifact_value([dict(listing[0], **{field: value})], "owned", "receipt.json")

    def test_exact_runtime_tree_not_ancestry(self):
        """Only reviewed controller/docs/test paths may differ in tracked commits."""
        current = "a" * 40
        def values(changed=b"infra/deploy/staging_resume.py\0docs/operations.md\0", runtime=b"", dirty=b""):
            return [current.encode() + b"\n", b"", runtime, changed, dirty]
        with patch.object(resume, "git", side_effect=values()):
            resume.exact_tree(current)
        for outputs in (values(runtime=b"workers/trace-sink/src/lib.rs\0"),
                        values(changed=b"infra/operator/check_send_hold.py\0"),
                        values(dirty=b"Cargo.toml\0"), values(changed=b".cargo/config.toml\0")):
            with patch.object(resume, "git", side_effect=outputs), self.assertRaises(ValueError):
                resume.exact_tree(current)

    def test_recover_composes_immutable_evidence(self):
        """The returned receipt retains original epoch separately from orchestration."""
        artifacts = {"total_count": 0, "artifacts": []}
        queues = [{"target": "staging", "queue_name": name, "queue_id": identity} for name, identity in
                  (("amail-trace-events-staging", resume.QUEUE), ("amail-trace-dlq-staging", resume.DLQ))]
        with patch.dict(os.environ, {"GITHUB_SHA": "a" * 40}), patch.object(resume, "exact_tree") as tree, \
             patch.object(resume, "github", side_effect=[self.run_metadata(), self.jobs(), artifacts]), \
             patch.object(resume, "artifact_value", side_effect=[self.predecessor(), queues]), \
             patch.object(resume.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, self.log(), b"")):
            value = resume.recover(resume.ORIGIN_RUN)
        tree.assert_called_once_with("a" * 40)
        self.assertEqual(value["source_sha"], resume.ORIGIN_SHA)
        self.assertEqual(value["current_sha"], "a" * 40)
        self.assertEqual(value["sink_version"], resume.SINK_VERSION)
        self.assertNotIn("private arbitrary", json.dumps(value))


if __name__ == "__main__":
    unittest.main()
