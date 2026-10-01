"""Hosted synthetic diagnostics contracts; no credentials/provider calls required."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, Mock, patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).parents[1] / "deploy"))
import control_plane_trace as trace
import deploy_trace_sink as sink
import inspect_held_production as inspector


class ControlPlaneTraceTests(unittest.TestCase):
    """Useful timing/source/error causes survive without dumping private inputs."""

    def test_nested_source_context_and_safe_exception_type(self):
        """Trace identity joins nested operations; exception text is not a field."""
        output = io.StringIO()
        with patch.dict("os.environ", {"GITHUB_SHA": "a"*40, "GITHUB_RUN_ID": "123",
                        "GITHUB_RUN_ATTEMPT": "1", "PRIVATE_TOKEN": "secret"}), redirect_stdout(output):
            with self.assertRaises(ValueError):
                with trace.span("deploy", "prepare"):
                    with trace.span("provider", "read"):
                        raise ValueError("private-body-and-token")
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        outer, inner, inner_end, outer_end = events
        self.assertEqual(inner["parent_span_id"], outer["span_id"])
        self.assertEqual(outer["trace_id"], inner["trace_id"])
        self.assertEqual(inner_end["error_type"], "ValueError")
        self.assertEqual(outer_end["outcome"], "failure")
        self.assertEqual(outer_end["source_sha"], "a"*40)
        self.assertGreaterEqual(outer_end["duration_ms"], 0)
        self.assertNotIn("private-body", output.getvalue())
        self.assertNotIn("secret", output.getvalue())

    def test_endpoint_coordinates_exclude_query_and_unreviewed_paths(self):
        """Harmless infrastructure IDs are retained rather than globally hidden."""
        account = "a"*32
        actual = trace.endpoint(f"/accounts/{account}/workers/scripts/amail-mail/settings?private=secret")
        self.assertEqual(actual, {"endpoint": "workers.settings", "account_id": account, "script_name": "amail-mail"})
        self.assertEqual(trace.endpoint("/unknown/private-address@example.test"), {"endpoint": "unclassified"})

    def test_deployment_error_has_exit_and_phase_but_no_raw_output(self):
        """One failed invocation is observable and never replayed."""
        output = io.StringIO()
        response = subprocess.CompletedProcess([], 2, "private-output", "private-secret")
        with redirect_stdout(output), patch.object(sink.subprocess, "run", return_value=response) as call:
            with self.assertRaises(ValueError):
                sink.deploy("production")
        event = json.loads(output.getvalue().splitlines()[-1])
        self.assertEqual(event["process_exit_code"], 2)
        self.assertEqual(event["reason"], "process_exit")
        self.assertEqual(event["phase"], "submit")
        self.assertNotIn("private-", output.getvalue())
        self.assertEqual(call.call_count, 1)

    def test_diagnostic_output_failure_does_not_change_operation_result(self):
        """A broken log stream cannot create an ambiguous operation retry."""
        with patch("builtins.print", side_effect=BrokenPipeError):
            with trace.span("provider", "read") as facts:
                facts.http_status = 200
        with self.assertRaises(ValueError), trace.span("provider", "read", body="private"):
            self.fail("unreviewed field must fail before provider execution")

    def test_provider_http_failure_preserves_status_and_request_id(self):
        """HTTP error body, credentials and URL query never enter diagnostics."""
        provider = object.__new__(inspector.Provider)
        provider.token = "private-token"
        provider.opener = Mock()
        provider.opener.open.side_effect = HTTPError("https://private.example/?private-query", 403,
            "private-message", {"cf-ray": "1234567890abcdef-SIN"}, io.BytesIO(b"private-body"))
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(ValueError):
            provider.envelope("/accounts/" + "a"*32 + "/workers/domains?private-query")
        event = json.loads(output.getvalue().splitlines()[-1])
        self.assertEqual(event["http_status"], 403)
        self.assertEqual(event["cf_ray"], "1234567890abcdef-SIN")
        self.assertEqual(event["error_type"], "HTTPError")
        self.assertEqual(event["endpoint"], "workers.domains")
        self.assertNotIn("private-", output.getvalue())
        provider.opener.open.assert_called_once()

    def test_provider_schema_failure_retains_types_and_numeric_codes_only(self):
        """Schema diagnostics describe expected/actual structure, never its content."""
        for body, expected in [(b'[]', "list"),
                              (b'{"success":false,"errors":[{"code":10000,"message":"private-body"}]}', "bool")]:
            provider = object.__new__(inspector.Provider)
            provider.token = "private-token"
            response = Mock(status=200, headers={})
            response.read.return_value = body
            provider.opener = MagicMock()
            provider.opener.open.return_value.__enter__.return_value = response
            output = io.StringIO()
            with redirect_stdout(output), self.assertRaises(ValueError):
                provider.envelope("/accounts/" + "a"*32 + "/workers/domains")
            event = json.loads(output.getvalue().splitlines()[-1])
            self.assertEqual(event["schema_actual_type"], expected)
            self.assertEqual(event["http_status"], 200)
            if expected == "bool":
                self.assertEqual(event["provider_error_codes"], [10000])
            self.assertNotIn("private-", output.getvalue())


if __name__ == "__main__":
    unittest.main()
