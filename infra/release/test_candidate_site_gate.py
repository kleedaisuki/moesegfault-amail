"""Candidate preflight metadata regressions; every HTTP request is mocked."""

import unittest
from unittest.mock import patch

import check_candidate_site_gate as gate


SHA = "a" * 40
ENV = {
    "GITHUB_REF": "refs/heads/main",
    "GITHUB_SHA": SHA,
    "GITHUB_REPOSITORY": "kleedaisuki/moesegfault-amail",
    "GH_TOKEN": "synthetic-not-a-secret",
    "SOURCE_CI_RUN_ID": "42",
}


def run():
    """Model a trusted, completed exact-source CI run, not a site deploy."""
    return dict(workflow_id=7, head_sha=SHA, head_branch="main", event="push", status="completed", conclusion="success")


class CandidateGateTests(unittest.TestCase):
    """Never infer CI from a run ID alone or Release absence from transport errors."""

    def test_exact_source_run(self):
        """Only successful source evidence for the exact immutable SHA passes."""
        gate.check_run(run(), 7, SHA)
        for key, value in (
            ("workflow_id", 8), ("head_sha", "b" * 40), ("head_branch", "untrusted"),
            ("event", "pull_request"), ("status", "in_progress"), ("conclusion", "failure"),
        ):
            modified = run()
            modified[key] = value
            with self.assertRaises(ValueError):
                gate.check_run(modified, 7, SHA)

    def test_gate_rejects_existing_tag_release_or_skipped_site(self):
        """Existing publication state blocks a downgrade even if Mail is held."""
        jobs = {"jobs": [{"name": "Astro release site", "conclusion": "success"}]}
        for responses, passes in (
            ([{"id": 7}, run(), jobs, None, None], True),
            ([{"id": 7}, run(), jobs, {"ref": "refs/tags/v0.1.0"}], False),
            ([{"id": 7}, run(), jobs, None, {"draft": False}], False),
            ([{"id": 7}, run(), {"jobs": []}], False),
            ([{"id": 7}, run(), {"jobs": [{"name": "Astro release site", "conclusion": "skipped"}]}], False),
        ):
            with patch.dict(gate.os.environ, ENV, clear=True), patch.object(gate, "github", side_effect=responses):
                if passes:
                    gate.main()
                else:
                    with self.assertRaises(SystemExit):
                        gate.main()

    def test_main_only_and_bad_metadata(self):
        """Dispatch source/ID errors are rejected before any HTTP access."""
        for key, value in (("GITHUB_REF", "refs/heads/codex/amail-v0.1.0"), ("SOURCE_CI_RUN_ID", "not-a-run"), ("GITHUB_SHA", "short")):
            with patch.dict(gate.os.environ, {**ENV, key: value}, clear=True), patch.object(gate, "github") as request:
                with self.assertRaises(SystemExit):
                    gate.main()
                request.assert_not_called()

    def test_api_failure_never_means_absent(self):
        """A denied/unavailable metadata read is an error, not candidate authority."""
        with patch.dict(gate.os.environ, ENV, clear=True), patch.object(gate, "github", side_effect=ValueError("GitHub preflight request unavailable")):
            with self.assertRaises(SystemExit):
                gate.main()


if __name__ == "__main__":
    unittest.main()
