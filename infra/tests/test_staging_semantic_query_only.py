"""Synthetic safety tests for the no-SMTP hosted semantic-query discriminator."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from workflow_source import job_block


sys.path.insert(0, str(Path(__file__).parent))
SPEC = importlib.util.spec_from_file_location(
    "staging_semantic_query_only", Path(__file__).with_name("staging_semantic_query_only.py")
)
assert SPEC and SPEC.loader
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


class SemanticQueryOnlyTests(unittest.TestCase):
    """The inventory and error classifier must fail closed without private output."""

    def test_workflow_is_manual_and_has_no_smtp_or_routing_secret(self) -> None:
        """The new job has only synthetic Identity credentials."""

        workflow = (PROBE.ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("staging-semantic-query-only", workflow.split("  workflow_dispatch:", 1)[1])
        job = job_block(workflow, "staging-semantic-query-only")
        self.assertIn("inputs.target == 'staging-semantic-query-only'", job)
        self.assertIn("group: staging-native-mail-acceptance", job)
        self.assertIn("RUN_STAGING_SEMANTIC_QUERY_ONLY", job)
        self.assertIn("STAGING_E2E_USERNAME: ${{ secrets.STAGING_E2E_USERNAME }}", job)
        self.assertIn("STAGING_E2E_PASSWORD: ${{ secrets.STAGING_E2E_PASSWORD }}", job)
        for forbidden in ("CLOUDFLARE_API_TOKEN:", "CF_EMAIL_ROUTING_TOKEN:",
                          "AMAIL_TEST_SMTP_TOKEN:", "CLOUDFLARE_ACCOUNT_ID:"):
            self.assertNotIn(forbidden, job)

    def test_empty_owner_inventory_requires_exactly_empty_final_page(self) -> None:
        """No mailbox filter means one empty, cursorless result proves empty active mail."""

        result = subprocess.CompletedProcess([], 0, b"", b"")
        with patch.object(PROBE, "run_cli", return_value=result) as call:
            PROBE.empty_owner_inventory(Path("binary"), Path("home"))
        self.assertEqual(call.call_args.args[2:],
                         ("search", "--limit", "100", "--wait-seconds", "30"))
        for raw in (b'{"id":"private-id"}\n', b'{"next_cursor":"private-cursor"}\n'):
            with patch.object(PROBE, "run_cli", return_value=subprocess.CompletedProcess([], 0, raw, b"")):
                with self.assertRaisesRegex(PROBE.ProbeError, "owner_mailbox_not_empty"):
                    PROBE.empty_owner_inventory(Path("binary"), Path("home"))

    def test_inventory_failure_never_spends_semantic_query(self) -> None:
        """Any existing active mail stops before the provider call."""

        with patch.object(PROBE, "empty_owner_inventory", side_effect=PROBE.ProbeError("owner_mailbox_not_empty")), \
             patch.object(PROBE, "run_cli") as call:
            with self.assertRaisesRegex(PROBE.ProbeError, "owner_mailbox_not_empty"):
                PROBE.probe(Path("binary"), Path("home"))
        call.assert_not_called()

    def test_semantic_query_success_has_no_results_or_cursor(self) -> None:
        """A success marker requires an empty semantic result, not just status zero."""

        with patch.object(PROBE, "empty_owner_inventory"), \
             patch.object(PROBE, "run_cli", return_value=subprocess.CompletedProcess([], 0, b"", b"")) as call:
            PROBE.probe(Path("binary"), Path("home"))
        self.assertEqual(call.call_args.args[2:],
                         ("search", "--semantic", PROBE.QUERY, "--limit", "100",
                          "--wait-seconds", "30"))
        with patch.object(PROBE, "empty_owner_inventory"), \
             patch.object(PROBE, "run_cli", return_value=subprocess.CompletedProcess(
                 [], 0, b'{"next_cursor":"private-cursor"}\n', b"")):
            with self.assertRaisesRegex(PROBE.ProbeError, "semantic_empty_result_unverified"):
                PROBE.probe(Path("binary"), Path("home"))

    def test_post_poll_and_unknown_error_labels_never_echo_identifiers(self) -> None:
        """A canonical typed error yields phase; arbitrary text remains unclassified."""

        job = b"123e4567-e89b-42d3-a456-426614174000"
        body = b"failed: HTTP 503 Service Unavailable, code=semantic_index_incomplete, correlation_id=private\n"
        post = b"amail: mail API messages.search " + body
        poll = (b"amail: search job " + job + b" running; polling\n"
                + b"amail: search job " + job + b": mail API messages.search.poll " + body)
        self.assertEqual(PROBE.classify_semantic_error(post),
                         "semantic_query_post_http_503_semantic_index_incomplete")
        self.assertEqual(PROBE.classify_semantic_error(poll),
                         "semantic_query_poll_http_503_semantic_index_incomplete")
        self.assertEqual(PROBE.classify_semantic_error(b"private body"),
                         "semantic_query_failed_unclassified")
        self.assertNotIn(job.decode(), PROBE.classify_semantic_error(poll))
        self.assertNotIn("private", PROBE.classify_semantic_error(poll))

    def test_environment_requires_exact_confirmation_before_credentials(self) -> None:
        """A push or wrong manual confirmation cannot open browser/login."""

        with patch.object(PROBE.os, "name", "nt"), \
             patch.dict(PROBE.os.environ, {"AMAIL_SEMANTIC_QUERY_CONFIRM": "wrong"}):
            with self.assertRaisesRegex(PROBE.ProbeError, "explicit_semantic_query_confirmation_required"):
                PROBE.validate()


if __name__ == "__main__":
    unittest.main()
