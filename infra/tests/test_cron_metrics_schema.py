"""Synthetic privacy, schema and hosted-job contracts; no live provider access."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "provider"))
import probe_cron_metrics_schema as subject
from workflow_source import job_block


def payload():
    """Make synthetic exact-type metadata; no resource or private mail data."""
    return {"data": {alias: {"name": name,
        "kind": "INPUT_OBJECT" if member == "inputFields" else "OBJECT",
        member: [{"name": field} for field in selected.split()]}
        for alias, (name, member, selected) in subject.TYPES.items()}, "errors": None}


class SchemaContracts(unittest.TestCase):
    """Schema membership never admits runtime, privacy or release state."""

    def test_fixed_query_and_categorical_projection(self):
        """Even complete membership yields no runtime admission."""
        self.assertEqual(subject.QUERY.count("__type(name:"), 8)
        for term in ("__schema", "viewer", "accounts", "description", "mutation", "$", "telemetry"):
            self.assertNotIn(term, subject.QUERY)
        lines = subject.classify(payload())
        self.assertIn("schema_adaptive_quantiles_memoryUsageBytesP99=present", lines)
        self.assertEqual(lines[-4:], ["schema_result=classified_only", "cron_resource_admission=UNVERIFIED",
                                     "runtime_measurement=not_performed", "issues_privacy_gate=unchanged"])
        value = payload()
        value["data"]["scheduled"] = None
        value["data"]["adaptive_filter"]["inputFields"] = [{"name": "PRIVATE_FIELD"}]
        lines = subject.classify(value)
        self.assertIn("schema_scheduled_cpuTimeUs=unavailable", lines)
        self.assertIn("schema_adaptive_filter_scriptVersion=absent", lines)
        self.assertNotIn("PRIVATE_FIELD", "\n".join(lines))

    def test_bad_schema_and_json_fail_closed(self):
        """Partial/hostile shapes discard all bins before output."""
        bad = [{}, {**payload(), "errors": [{"message": "PRIVATE"}]}]
        for key, replacement in (("name", "PRIVATE"), ("kind", "INPUT_OBJECT"), ("fields", None),
                                 ("fields", [{"name": "PRIVATE\nvalue"}]),
                                 ("fields", [{"name": "duplicate"}] * 2),
                                 ("fields", [{"name": "x"}] * (subject.MAX_FIELDS + 1))):
            value = payload()
            value["data"]["scheduled"][key] = replacement
            bad.append(value)
        value = payload()
        del value["data"]["d1_sum"]
        bad.append(value)
        for value in bad:
            with self.assertRaises(subject.Unverified):
                subject.classify(value)
        for raw in ('{"data":{},"data":{}}', '{"data":NaN}'):
            with self.assertRaises(subject.Unverified):
                json.loads(raw, object_pairs_hook=subject.unique_object, parse_constant=subject.reject_constant)

    def test_confirmation_transport_and_failure_privacy(self):
        """No credential-free request, bearer redirect, retry or raw failure text."""
        for confirm, token in (("wrong", "secret"), (subject.CONFIRM, ""), (subject.CONFIRM, "secret\n")):
            with patch.object(subject, "fetch") as fetch, self.assertRaises(subject.Unverified):
                subject.run(confirm, token)
            fetch.assert_not_called()
        response, opener = MagicMock(), MagicMock()
        response.getcode.return_value = 200
        response.read.return_value = json.dumps(payload()).encode()
        opener.open.return_value.__enter__.return_value = response
        with patch.object(subject, "build_opener", return_value=opener):
            self.assertEqual(subject.fetch("secret"), payload())
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.full_url, subject.ENDPOINT)
        self.assertEqual(json.loads(request.data), {"query": subject.QUERY})
        self.assertEqual(opener.open.call_args.kwargs, {"timeout": 20})
        response.read.assert_called_once_with(subject.MAX_BODY + 1)
        response.read.return_value = b"x" * (subject.MAX_BODY + 1)
        with patch.object(subject, "build_opener", return_value=opener), self.assertRaises(subject.Unverified):
            subject.fetch("secret")
        response.getcode.return_value = 503
        with patch.object(subject, "build_opener", return_value=opener), self.assertRaises(subject.Unverified):
            subject.fetch("secret")
        self.assertIsNone(subject.NoRedirect().redirect_request(None, None, 302, "PRIVATE", {}, "PRIVATE"))
        for error in (RuntimeError("PRIVATE"), subject.Unverified("PRIVATE"), subject.Unverified(["PRIVATE"])):
            output = StringIO()
            with patch.object(subject, "run", side_effect=error), redirect_stdout(output):
                self.assertEqual(subject.main(), 1)
            self.assertEqual(output.getvalue(), "schema_result=UNVERIFIED reason=internal\n")

    def test_hosted_contracts_precede_main_only_secret_job(self):
        """Standalone schema metadata read cannot trigger an existing deploy job."""
        source = (Path(__file__).resolve().parents[2] / ".github/workflows/cron-metrics-schema.yml").read_text()
        self.assertNotIn("secrets.", job_block(source, "contracts"))
        live = job_block(source, "schema")
        for term in ("needs: contracts", "workflow_dispatch", "refs/heads/main", subject.CONFIRM,
                     "environment: staging", "cancel-in-progress: false"):
            self.assertIn(term, live)
        self.assertEqual(live.count("secrets."), 1)
        for term in ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "wrangler", "cargo", "upload-artifact"):
            self.assertNotIn(term, source)


if __name__ == "__main__":
    unittest.main()
