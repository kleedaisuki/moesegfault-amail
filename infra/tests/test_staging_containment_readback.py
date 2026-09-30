"""Synthetic contracts for the read-only containment discrepancy discriminator."""

import contextlib
import io
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import staging_containment_readback as subject

from workflow_source import job_block

VERSION = "759906b4-bdb9-488a-a980-a4bada8ba83e"
DEPLOYMENT = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def deployment(version=VERSION):
    """Build a minimal synthetic 100-percent deployment response."""
    return {"deployments": [{"id": DEPLOYMENT, "strategy": "percentage", "versions": [{"version_id": version, "percentage": 100}]}]}


class ReadbackTests(unittest.TestCase):
    """Keep diagnostics bounded and incapable of changing provider state."""

    def test_missing_wrong_types_and_numeric_boolean_distinction(self):
        """Unknown values remain unknown rather than implying containment."""
        self.assertEqual(set(subject.classify({}).values()), {"missing"})
        self.assertEqual(subject.boolean(None), "other")
        self.assertEqual(subject.boolean(0), "other")
        self.assertEqual(subject.sampling(True), "other")
        self.assertEqual(subject.sampling(1.0), "true")
        self.assertEqual(subject.sampling(0), "false")
        self.assertEqual(subject.sampling(.5), "other")
        self.assertEqual(subject.collection(None), "other")
        self.assertEqual(subject.collection([]), "false")
        self.assertEqual(subject.collection([{"private": "secret"}]), "true")
        self.assertEqual(subject.collection(["cloudflare"], True), "false")
        self.assertEqual(subject.collection(["secret"], True), "true")
        self.assertEqual(subject.collection([{}], True), "other")

    def test_exact_four_reads_bracket_settings(self):
        """Only the staging control plane is read, with no version-value output."""
        with patch.object(subject, "fetch", side_effect=[deployment(), {}, {}, deployment()]) as fetch:
            status, result = subject.probe("account", "token", VERSION)
        self.assertEqual(status, "stable100")
        self.assertEqual([x.args[2] for x in fetch.call_args_list], ["deployments?per_page=1&page=1", "settings", "script-settings", "deployments?per_page=1&page=1"])
        self.assertEqual(result["settings"]["read"], "available")

    def test_success_output_is_closed_categories(self):
        """Arbitrary provider strings are classified, never interpolated into logs."""
        settings = {"observability": {"enabled": "PRIVATE", "logs": {"destinations": ["PRIVATE"]}}, "tail_consumers": [{"service": "PRIVATE"}]}
        env = {"CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "SECRET", "AMAIL_EXPECTED_WORKER_VERSION": VERSION, "AMAIL_CONTAINMENT_CONFIRM": subject.CONFIRM}
        out = io.StringIO()
        with patch.dict(os.environ, env, clear=True), patch.object(subject, "fetch", side_effect=[deployment(), settings, settings, deployment()]), contextlib.redirect_stdout(out):
            self.assertEqual(subject.main(), 0)
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[0], "staging_containment_readback=stable100")
        self.assertEqual(len(lines), 1 + 2 * (1 + len(subject.FIELDS)))
        for line in lines[1:]:
            key, value = line.split("=")
            self.assertIn(value, {"missing", "false", "true", "other", "available"})
            self.assertTrue(key.startswith("staging_containment_"))
        self.assertNotIn("PRIVATE", out.getvalue())
        self.assertNotIn(VERSION, out.getvalue())
        self.assertNotIn("SECRET", out.getvalue())

    def test_change_discards_categories(self):
        """Concurrent deployment prevents attributing settings to the expected version."""
        with patch.object(subject, "fetch", side_effect=[deployment(), {}, {}, deployment("bbbbbbbb-bbbb-cccc-dddd-eeeeeeeeeeee")]):
            self.assertEqual(subject.probe("account", "token", VERSION), ("deployment_changed", {}))

    def test_mismatch_stops_before_settings(self):
        """A wrong version does not cause extra reads."""
        with patch.object(subject, "fetch", return_value=deployment()) as fetch:
            self.assertEqual(subject.probe("account", "token", DEPLOYMENT), ("version_mismatch", {}))
            self.assertEqual(fetch.call_count, 1)

    def test_endpoint_failure_still_checks_after(self):
        """Failed reads expose only a fixed status and do not skip deployment recheck."""
        with patch.object(subject, "fetch", side_effect=[deployment(), ValueError("PRIVATE"), {}, deployment()]) as fetch:
            status, result = subject.probe("account", "token", VERSION)
        self.assertEqual(status, "settings_unavailable")
        self.assertEqual(result["settings"], {"read": "unavailable"})
        self.assertEqual(fetch.call_count, 4)

    def test_main_never_prints_provider_payload_or_exception(self):
        """Malformed or sensitive provider values cannot escape the output contract."""
        env = {"CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "SECRET", "AMAIL_EXPECTED_WORKER_VERSION": VERSION, "AMAIL_CONTAINMENT_CONFIRM": subject.CONFIRM}
        out = io.StringIO()
        with patch.dict(os.environ, env, clear=True), patch.object(subject, "fetch", side_effect=RuntimeError("PRIVATE")), contextlib.redirect_stdout(out):
            self.assertEqual(subject.main(), 1)
        self.assertEqual(out.getvalue(), "staging_containment_readback=unavailable\n")
        with patch.dict(os.environ, {}, clear=True), patch.object(subject, "fetch") as fetch, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(subject.main(), 1)
            fetch.assert_not_called()

    def test_workflow_guard_and_secret_order(self):
        """Manual branch-only diagnostics run source contracts before credentials."""
        text = (Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml").read_text()
        job = job_block(text, "staging-containment-readback")
        self.assertIn("github.event_name == 'workflow_dispatch'", job)
        self.assertIn("github.ref == 'refs/heads/codex/amail-v0.1.0'", job)
        self.assertNotIn("refs/heads/main", job)
        self.assertIn(subject.CONFIRM, job)
        self.assertLess(job.index("test_staging_containment_readback.py"), job.index("secrets.CLOUDFLARE_API_TOKEN"))
        self.assertNotIn("CF_OBSERVABILITY_TOKEN", job)
        self.assertNotIn("wrangler", job)


if __name__ == "__main__":
    unittest.main()
