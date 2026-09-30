"""Synthetic contracts for the five-GET staging Worker resource discriminator."""
import contextlib
import io
import json
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import staging_worker_resource_readback as subject

from workflow_source import job_block

VERSION = "759906b4-bdb9-488a-a980-a4bada8ba83e"
DEPLOYMENT = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def deployment(version=VERSION, identifier=DEPLOYMENT):
    """Build a single synthetic 100-percent deployment."""
    return {"deployments": [{"id": identifier, "strategy": "percentage",
        "versions": [{"version_id": version, "percentage": 100}]}]}


def worker(**values):
    """Build the identity-bearing reviewed Worker response."""
    return {"name": subject.SCRIPT, "id": "PRIVATE_ID", **values}


class ResourceReadbackTests(unittest.TestCase):
    """Verify bounded reads, categorical privacy, and fail-closed attribution."""

    def test_type_bins_and_booleans(self):
        """Missing, null, booleans and numeric subclasses remain distinct."""
        for value, expected in [(subject.MISSING, "missing"), (None, "null"),
            ({}, "object"), (False, "boolean"), (0, "number"), (1.0, "number"),
            ("PRIVATE", "string"), ([], "array"), (object(), "other")]:
            self.assertEqual(subject.shape(value), expected)
        self.assertEqual(subject.boolean(None), "null")
        self.assertEqual(subject.boolean(0), "other")
        self.assertEqual(subject.sampling(False), "other")
        self.assertEqual(subject.sampling(0), "zero")
        self.assertEqual(subject.sampling(1.0), "one")
        self.assertEqual(subject.sampling(float("nan")), "other")
        self.assertEqual(set(subject.classify({}).values()), {"missing"})
        values = subject.classify({"observability": {"logs": None,
            "traces": False, "issues": {"enabled": True}}})
        self.assertEqual(values["logs_shape"], "null")
        self.assertEqual(values["traces_shape"], "boolean")
        self.assertEqual(values["issues"], "true")

    def test_collections_validate_every_member(self):
        """Malformed exports never masquerade as Cloudflare-only or empty."""
        for value, expected in [(subject.MISSING, "missing"), (None, "null"),
            (False, "malformed"), ([], "empty"), (["cloudflare"], "cloudflare_only"),
            (["PRIVATE"], "external"), (["cloudflare", {}], "malformed"),
            (["cloudflare", ""], "malformed"), ([" "], "malformed")]:
            self.assertEqual(subject.collection(value, True), expected)
        self.assertEqual(subject.collection([{"service": "PRIVATE"}]), "populated")
        self.assertEqual(subject.collection([{"service": "PRIVATE", "environment": None}]), "malformed")
        self.assertEqual(subject.collection([{"service": "PRIVATE"}, {}]), "malformed")
        self.assertEqual(subject.collection_shape(None), "null")
        self.assertEqual(subject.collection_shape([]), "list")

    def test_exact_five_read_order(self):
        """No API invocation, list discovery or version-detail fallback occurs."""
        with patch.object(subject, "fetch", side_effect=[deployment(), {}, {}, worker(), deployment()]) as fetch:
            reason, result = subject.probe("account", "token", VERSION)
        self.assertEqual(reason, "stable100")
        self.assertEqual([x.args[2] for x in fetch.call_args_list],
            [subject.DEPLOYMENTS, *(path for _, path in subject.ENDPOINTS), subject.DEPLOYMENTS])
        self.assertEqual(result["worker"]["worker_name"], "match")
        self.assertEqual(result["worker"]["worker_id"], "valid")

    def test_deployment_change_discards_all_bins(self):
        """Same version with a different deployment ID is still a change."""
        with patch.object(subject, "fetch", side_effect=[deployment(), {}, {}, worker(),
            deployment(identifier=VERSION)]):
            self.assertEqual(subject.probe("a", "t", VERSION), ("deployment_changed", {}))
        with patch.object(subject, "fetch", return_value=deployment()) as fetch:
            self.assertEqual(subject.probe("a", "t", DEPLOYMENT), ("version_mismatch", {}))
            self.assertEqual(fetch.call_count, 1)

    def test_endpoint_unavailable_still_brackets(self):
        """403/404 or malformed representations are unavailable, not disabled."""
        for value in [RuntimeError("PRIVATE"), worker(name="PRIVATE"),
            worker(id=None), worker(id=""), worker(id=12)]:
            with patch.object(subject, "fetch", side_effect=[deployment(), {}, {}, value, deployment()]) as fetch:
                reason, result = subject.probe("a", "t", VERSION)
            self.assertEqual(reason, "representation_unavailable")
            self.assertEqual(result["worker"]["read"], "unavailable")
            self.assertNotIn("enabled", result["worker"])
            self.assertEqual(fetch.call_count, 5)

    def test_output_is_closed_and_private(self):
        """IDs, secrets, arbitrary keys/values and exception strings never escape."""
        env = {"CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "SECRET",
            "AMAIL_EXPECTED_WORKER_VERSION": VERSION, "AMAIL_WORKER_RESOURCE_CONFIRM": subject.CONFIRM}
        data = {"observability": {"enabled": "PRIVATE", "logs": {"destinations": ["PRIVATE"]}},
            "tail_consumers": [{"service": "PRIVATE"}], "PRIVATE_KEY": "PRIVATE"}
        out = io.StringIO()
        with patch.dict(os.environ, env, clear=True), patch.object(subject, "fetch",
            side_effect=[deployment(), data, data, worker(**data), deployment()]), contextlib.redirect_stdout(out):
            self.assertEqual(subject.main(), 0)
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[0], "staging_worker_resource_readback=stable100")
        self.assertEqual(len(lines), 2 + 3 * (1 + len(subject.FIELDS)) + 2)
        for secret in ["PRIVATE", "SECRET", VERSION, DEPLOYMENT]:
            self.assertNotIn(secret, out.getvalue())
        allowed = {"stable100", "missing", "null", "object", "boolean", "number",
            "string", "array", "other", "true", "false", "zero", "one", "list",
            "malformed", "empty", "cloudflare_only", "external", "populated",
            "available", "match", "valid"}
        self.assertTrue(all(line.split("=", 1)[1] in allowed for line in lines))

    def test_invalid_input_and_exception_output(self):
        """Pre-network input guards and failures expose only reviewed labels."""
        with patch.dict(os.environ, {}, clear=True), patch.object(subject, "fetch") as fetch, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(subject.main(), 1)
            fetch.assert_not_called()
        env = {"CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "SECRET",
            "AMAIL_EXPECTED_WORKER_VERSION": VERSION, "AMAIL_WORKER_RESOURCE_CONFIRM": subject.CONFIRM}
        out = io.StringIO()
        with patch.dict(os.environ, env, clear=True), patch.object(subject, "fetch",
            side_effect=RuntimeError("PRIVATE")), contextlib.redirect_stdout(out):
            self.assertEqual(subject.main(), 1)
        self.assertEqual(out.getvalue(), "staging_worker_resource_readback=UNVERIFIED\nstaging_worker_resource_reason=unavailable\n")

    def test_transport_bounds_success_envelope_and_no_redirect(self):
        """Each response is bounded, successful, typed, and obtained by GET."""
        cases = [
            (200, json.dumps({"success": True, "result": {}}).encode(), True),
            (200, json.dumps({"success": False, "result": {}}).encode(), False),
            (200, json.dumps({"success": True, "result": []}).encode(), False),
            (200, b"PRIVATE", False), (403, b"PRIVATE", False),
            (200, b"x" * (subject.LIMIT + 1), False),
        ]
        for status, raw, valid in cases:
            response = MagicMock()
            response.__enter__.return_value = response
            response.getcode.return_value = status
            response.read.return_value = raw
            opener = MagicMock()
            opener.open.return_value = response
            with patch.object(subject, "build_opener", return_value=opener):
                if valid:
                    self.assertEqual(subject.fetch("a", "t", subject.ENDPOINTS[2][1]), {})
                else:
                    with self.assertRaises((ValueError, UnicodeDecodeError)):
                        subject.fetch("a", "t", subject.ENDPOINTS[2][1])
            request = opener.open.call_args.args[0]
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(opener.open.call_args.kwargs, {"timeout": 15})
            if status == 200:
                response.read.assert_called_once_with(subject.LIMIT + 1)
        self.assertIsNone(subject.NoRedirect().redirect_request(None, None, 302, None, None, "PRIVATE"))

    def test_workflow_is_branch_only_and_tests_precede_secrets(self):
        """Only the distinct manually confirmed target receives credentials."""
        text = (Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml").read_text()
        job = job_block(text, "staging-worker-resource-readback")
        for clause in ["github.event_name == 'workflow_dispatch'",
            "inputs.target == 'staging-worker-resource-readback'",
            "github.ref == 'refs/heads/codex/amail-v0.1.0'", subject.CONFIRM,
            "environment: staging"]:
            self.assertIn(clause, job)
        self.assertLess(job.index("test_staging_worker_resource_readback.py"),
            job.index("secrets.CLOUDFLARE_API_TOKEN"))
        self.assertNotIn("CF_OBSERVABILITY_TOKEN", job)
        self.assertNotIn("wrangler", job)


if __name__ == "__main__":
    unittest.main()
