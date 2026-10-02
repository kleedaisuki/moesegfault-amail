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
from unittest.mock import Mock
from urllib.error import HTTPError
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

    def log_transport(self, location: str, content: bytes = b"typed log"):
        """Mock one API redirect and one signed download without retaining secrets."""
        redirect = HTTPError("https://api.github.com/reviewed", 302, "redirect",
                             {"Location": location}, io.BytesIO())
        response = Mock()
        response.status = 200
        response.read.return_value = content
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.side_effect = [redirect, response]
        return opener

    def test_log_redirect_download_never_forwards_bearer(self):
        """A validated Azure log authority gets a separate unauthenticated request."""
        opener = self.log_transport("https://productionresultssa15.blob.core.windows.net/logs/fixture?sig=synthetic")
        with patch.dict(os.environ, {"GH_TOKEN": "synthetic"}), patch.object(resume, "build_opener", return_value=opener):
            self.assertEqual(resume.job_log(123), b"typed log")
        first, second = [call.args[0] for call in opener.open.call_args_list]
        self.assertEqual(first.get_header("Authorization"), "Bearer synthetic")
        self.assertIsNone(second.get_header("Authorization"))

    def test_log_redirect_rejects_unreviewed_authorities_and_oversized_bytes(self):
        """No plaintext, credential URL, off-host redirect or second-hop expansion."""
        for location in ("http://productionresultssa15.blob.core.windows.net/logs?sig=x",
                         "https://unowned.blob.core.windows.net/logs?sig=x",
                         "https://productionresultssa15.blob.core.windows.net.evil.invalid/logs?sig=x",
                         "https://user@productionresultssa15.blob.core.windows.net/logs?sig=x",
                         "https://productionresultssa15.blob.core.windows.net:444/logs?sig=x"):
            opener = self.log_transport(location)
            with patch.dict(os.environ, {"GH_TOKEN": "synthetic"}), \
                 patch.object(resume, "build_opener", return_value=opener), self.assertRaises(ValueError):
                resume.job_log(123)
            self.assertEqual(opener.open.call_count, 1)
        opener = self.log_transport("https://productionresultssa15.blob.core.windows.net/logs?sig=x", b"x" * 17)
        with patch.dict(os.environ, {"GH_TOKEN": "synthetic"}), \
             patch.object(resume, "build_opener", return_value=opener), patch.object(resume, "LOG_LIMIT", 16), \
             self.assertRaisesRegex(ValueError, "^staging_resume_log_unverified$"):
            resume.job_log(123)

    def test_log_api_denial_has_fixed_reason_and_never_retries(self):
        """GITHUB_TOKEN permission failures are actionable without provider prose."""
        opener = Mock()
        opener.open.side_effect = HTTPError("https://api.github.com/reviewed", 403,
                                            "private transport prose", {}, io.BytesIO(b"private body"))
        with patch.dict(os.environ, {"GH_TOKEN": "synthetic"}), \
             patch.object(resume, "build_opener", return_value=opener), \
             self.assertRaisesRegex(ValueError, "^staging_resume_log_permission_denied$"):
            resume.job_log(123)
        self.assertEqual(opener.open.call_count, 1)

    def test_recover_composes_immutable_evidence(self):
        """The returned receipt retains original epoch separately from orchestration."""
        artifacts = {"total_count": 0, "artifacts": []}
        queues = [{"target": "staging", "queue_name": name, "queue_id": identity} for name, identity in
                  (("amail-trace-events-staging", resume.QUEUE), ("amail-trace-dlq-staging", resume.DLQ))]
        with patch.dict(os.environ, {"GITHUB_SHA": "a" * 40}), patch.object(resume, "exact_tree") as tree, \
             patch.object(resume, "github", side_effect=[self.run_metadata(), self.jobs(), artifacts]), \
             patch.object(resume, "artifact_value", side_effect=[self.predecessor(), queues]), \
             patch.object(resume, "job_log", return_value=self.log()):
            value = resume.recover(resume.ORIGIN_RUN)
        tree.assert_called_once_with("a" * 40)
        self.assertEqual(value["source_sha"], resume.ORIGIN_SHA)
        self.assertEqual(value["current_sha"], "a" * 40)
        self.assertEqual(value["sink_version"], resume.SINK_VERSION)
        self.assertNotIn("private arbitrary", json.dumps(value))

    def active_jobs(self):
        """The second interruption followed successful reuse and completed cutover."""
        jobs = self.jobs()
        sink = jobs["jobs"][-1]
        sink.update({"conclusion": "success", "run_id": int(resume.ACTIVE_RUN), "head_sha": resume.ACTIVE_SHA})
        sink["steps"][0]["conclusion"] = "skipped"
        api = next(row for row in jobs["jobs"] if row["name"] == resume.API_JOB)
        api.update({"conclusion": "failure", "id": 456, "run_id": int(resume.ACTIVE_RUN),
                    "head_sha": resume.ACTIVE_SHA, "steps": [
                        {"name": name, "status": "completed", "conclusion": state} for name, state in
                        ((resume.API_STEP, "success"), (resume.CUTOVER_STEP, "success"),
                         (resume.GRAPH_STEP, "failure"))]})
        return jobs

    def active_run(self):
        """Keep the second reviewed source epoch distinct from the original creator."""
        return dict(self.run_metadata(), id=int(resume.ACTIVE_RUN), head_sha=resume.ACTIVE_SHA)

    def active_log(self):
        """Model three submits and the separate outer non-submit deployment span."""
        base = resume.decode(self.log().splitlines()[1].split(b" ", 1)[1])
        base.update({"source_sha": resume.ACTIVE_SHA, "run_id": resume.ACTIVE_RUN,
                     "component": "mail_api", "job": "staging-worker"})
        outer = dict(base, phase="startup")
        records = [outer] + [dict(base, version=version) for version in
                            (resume.ACTIVE_API, resume.PAUSED_MAINTENANCE, resume.ACTIVE_MAINTENANCE)]
        return b"\n".join(json.dumps(row).encode() for row in records)

    def witness(self):
        """Recorded monotonic samples are independent of present wall-clock age."""
        return {"schema": "staging-platform-cutover/v1", "source_sha": resume.ACTIVE_SHA,
                "run_id": resume.ACTIVE_RUN, "old_api_version": resume.API_VERSION,
                "api_version": resume.ACTIVE_API, "paused_maintenance_version": resume.PAUSED_MAINTENANCE,
                "old_usage_model": "standard", "propagation_limit_seconds": 900,
                "invocation_limit_seconds": 900, "observed_monotonic_seconds": 1864.6,
                "pin_samples": 30, "execution_leases_preserved": {"embedding_leases": 0, "projection_leases": 1}}

    def test_active_origin_requires_completed_cutover_and_failed_final_graph(self):
        """No earlier ambiguous submit or later writer fits the active boundary."""
        self.assertEqual(resume.origin(self.active_run(), self.active_jobs(), resume.ACTIVE_RUN)["id"], 456)
        for name, invalid in ((resume.API_STEP, "failure"), (resume.CUTOVER_STEP, "failure"),
                              (resume.GRAPH_STEP, "success")):
            jobs = self.active_jobs()
            api = next(row for row in jobs["jobs"] if row["name"] == resume.API_JOB)
            next(row for row in api["steps"] if row["name"] == name)["conclusion"] = invalid
            with self.subTest(name=name), self.assertRaises(ValueError):
                resume.origin(self.active_run(), jobs, resume.ACTIVE_RUN)
        jobs = self.active_jobs()
        jobs["jobs"][-1]["steps"][0]["conclusion"] = "success"
        with self.assertRaises(ValueError):
            resume.origin(self.active_run(), jobs, resume.ACTIVE_RUN)

    def test_active_full_gates_and_all_later_deploys_remain_mandatory(self):
        """A successful sink is insufficient without complete full-source evidence."""
        for name in resume.required_jobs([]) | (resume.SKIPPED - {resume.API_JOB}) | {resume.SINK_JOB}:
            jobs = self.active_jobs()
            row = next(row for row in jobs["jobs"] if row["name"] == name)
            row["conclusion"] = "success" if name in resume.SKIPPED else "failure"
            with self.subTest(name=name), self.assertRaises(ValueError):
                resume.origin(self.active_run(), jobs, resume.ACTIVE_RUN)

    def test_active_submit_triplet_has_exact_order_and_epoch(self):
        """Outer spans are not submits; duplicate, failed or mixed submits are rejected."""
        raw = self.active_log()
        resume.active_log(raw)
        for invalid in (raw + b"\n" + raw, raw.replace(resume.ACTIVE_API.encode(), resume.API_VERSION.encode()),
                        raw.replace(resume.ACTIVE_RUN.encode(), resume.ORIGIN_RUN.encode()),
                        raw.replace(b'"process_exit_code": 0', b'"process_exit_code": 1'),
                        raw.replace(b'"version_count": 1', b'"version_count": true')):
            with self.assertRaises(ValueError):
                resume.active_log(invalid)
        records = resume.submit_records(raw)
        with self.assertRaises(ValueError):
            resume.active_log(b"\n".join(json.dumps(row).encode() for row in records[::-1]))

    def test_witness_requires_actual_bounded_window_samples_and_pins(self):
        """Short age, nonfinite time, missing sample or incompatible runtime fail."""
        self.assertEqual(resume.cutover_witness(self.witness())["pin_samples"], 30)
        for key, invalid in (("observed_monotonic_seconds", 1859.9), ("observed_monotonic_seconds", float("inf")),
                             ("observed_monotonic_seconds", float("nan")), ("pin_samples", 1),
                             ("pin_samples", True), ("old_usage_model", "bundled"),
                             ("api_version", resume.API_VERSION), ("source_sha", resume.ORIGIN_SHA),
                             ("propagation_limit_seconds", True)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                resume.cutover_witness(dict(self.witness(), **{key: invalid}))
        for leases in ({"embedding_leases": -1, "projection_leases": 0},
                       {"embedding_leases": True, "projection_leases": 0}, {"embedding_leases": 0}):
            with self.assertRaises(ValueError):
                resume.cutover_witness(dict(self.witness(), execution_leases_preserved=leases))

    def test_active_recover_retains_original_ownership_and_separate_phase(self):
        """No current producer bytes or synthesized predecessor can grant adoption."""
        owned = {"predecessor": self.predecessor(), "queue": resume.QUEUE,
                 "dlq": resume.DLQ, "sink_version": resume.SINK_VERSION}
        with patch.dict(os.environ, {"GITHUB_SHA": "a" * 40}), patch.object(resume, "exact_tree") as tree, \
             patch.object(resume, "original_ownership", return_value=owned), \
             patch.object(resume, "github", side_effect=[self.active_run(), self.active_jobs(), {"total_count": 0, "artifacts": []}]), \
             patch.object(resume, "job_log", return_value=self.active_log()), \
             patch.object(resume, "artifact_value", return_value=self.witness()):
            value = resume.recover(resume.ACTIVE_RUN)
        tree.assert_called_once_with("a" * 40, resume.ACTIVE_SHA)
        self.assertEqual(value["phase"], "active")
        self.assertEqual(value["predecessor"]["source_sha"], resume.ORIGIN_SHA)
        self.assertEqual(value["source_sha"], resume.ACTIVE_SHA)
        self.assertEqual(value["api_version"], resume.ACTIVE_API)
        self.assertEqual(value["maintenance_version"], resume.ACTIVE_MAINTENANCE)



if __name__ == "__main__":
    unittest.main()
