"""Hosted synthetic contracts for the unchanged manual Queue capability probe.

Workflow edits must not perform provider reads as an automatic source-check side
effect. The existing manual API and coarse helper output remain compatible; all
HTTP interactions below are mocked and disclose no real resources or tokens.
"""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/provider"))
sys.path.insert(0, str(ROOT / "infra/tests"))
import probe_queues as probe
from workflow_source import jobs


class QueueProbeTests(unittest.TestCase):
    """Retain the manual diagnostic without a push/PR/schedule/caller edge."""

    def test_only_the_compatible_no_input_manual_event_remains(self) -> None:
        """No renamed workflow or new required parameter may break operators."""
        source = (ROOT / ".github/workflows/probe-queues.yml").read_text(encoding="utf-8")
        events = source.split("\non:\n", 1)[1].split("\npermissions:\n", 1)[0]
        self.assertEqual(events.strip(), "workflow_dispatch:")
        self.assertIn("name: Probe Cloudflare Queues permission\n", source)
        active = jobs(source)
        self.assertEqual(set(active), {"probe"})
        job = active["probe"]
        self.assertNotIn("if:", job)
        self.assertNotIn("needs:", job)
        self.assertIn("timeout-minutes: 5", job)
        self.assertIn("run: python infra/provider/probe_queues.py", job)
        self.assertEqual(source.count("${{ secrets.CLOUDFLARE_ACCOUNT_ID }}"), 1)
        self.assertEqual(source.count("${{ secrets.CLOUDFLARE_API_TOKEN }}"), 1)

    def test_no_other_workflow_calls_the_provider_probe(self) -> None:
        """Source checks run its tests, not the credentialed live helper."""
        for path in (ROOT / ".github/workflows").glob("*.y*ml"):
            if path.name == "probe-queues.yml":
                continue
            source = path.read_text(encoding="utf-8")
            with self.subTest(workflow=path.name):
                self.assertNotIn("infra/provider/probe_queues.py", source)
                self.assertNotIn("uses: ./.github/workflows/probe-queues.yml", source)

    def test_missing_credentials_do_not_query_the_provider(self) -> None:
        """Keep the existing fixed error and exit status without secret output."""
        output = StringIO()
        with patch.dict(probe.os.environ, {}, clear=True), \
                patch.object(probe.urllib.request, "urlopen") as request, redirect_stdout(output):
            self.assertEqual(probe.main(), 2)
        request.assert_not_called()
        self.assertEqual(output.getvalue(), "queues_probe=missing_credentials\n")

    def test_read_available_is_the_same_body_free_single_get_signal(self) -> None:
        """Read availability is not Queue Write or resource admission evidence."""
        output = StringIO()
        response = MagicMock()
        response.status = 200
        env = {"CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "synthetic-token"}
        with patch.dict(probe.os.environ, env, clear=True), \
                patch.object(probe.urllib.request, "urlopen") as request, redirect_stdout(output):
            request.return_value.__enter__.return_value = response
            self.assertEqual(probe.main(), 0)
        request.assert_called_once()
        args, kwargs = request.call_args
        self.assertEqual(args[0].get_method(), "GET")
        self.assertEqual(args[0].full_url,
                         "https://api.cloudflare.com/client/v4/accounts/" + "a" * 32 + "/queues?per_page=1")
        self.assertEqual(kwargs, {"timeout": 15})
        response.read.assert_not_called()
        self.assertEqual(output.getvalue(), "queues_probe_http=200\nqueues_probe=read_available\n")

    def test_provider_failures_preserve_fixed_labels_without_retry_or_raw_text(self) -> None:
        """HTTP and network errors keep their historical output/exit contracts."""
        env = {"CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "synthetic-token"}
        cases = (
            (HTTPError("https://synthetic.invalid/private", 403, "private-token", {}, None),
             1, "queues_probe_http=403\nqueues_probe=not_available\n"),
            (URLError("private-token/resource"), 2, "queues_probe=network_error\n"),
        )
        for error, exit_code, expected in cases:
            with self.subTest(error=type(error).__name__):
                output = StringIO()
                with patch.dict(probe.os.environ, env, clear=True), \
                        patch.object(probe.urllib.request, "urlopen", side_effect=error) as request, \
                        redirect_stdout(output):
                    self.assertEqual(probe.main(), exit_code)
                request.assert_called_once()
                self.assertEqual(output.getvalue(), expected)


if __name__ == "__main__":
    unittest.main()
