"""Mock contracts for the manual hosted private-R2 capability gate."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "staging_r2_object_capability", Path(__file__).with_name("staging_r2_object_capability.py")
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
ENV = {
    "AMAIL_R2_CAPABILITY_CONFIRM": "RUN_STAGING_R2_OBJECT_CAPABILITY",
    "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
    "CLOUDFLARE_API_TOKEN": "private-token-not-for-output",
    "CF_EMAIL_ROUTING_TOKEN": "private-route-token-not-for-output",
}


class R2ObjectCapabilityTests(unittest.TestCase):
    """Pin phase handling, exact cleanup and fixed-label privacy."""

    def run_probe(self, replies: list[tuple[int, bytes] | Exception]) -> tuple[int, str, str, list[str]]:
        """Execute against a deterministic UUID and synthetic REST responses."""

        calls: list[str] = []

        def fake_call(method, path, token, data=None, content_type=None):
            self.assertEqual(token, ENV["CLOUDFLARE_API_TOKEN"])
            self.assertIn("/verification/12345678-1234-4123-8123-123456789abc.eml", path)
            calls.append(method)
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply

        out, err = StringIO(), StringIO()
        with patch.dict(os.environ, ENV, clear=True), \
                patch.object(MODULE, "audit") as audit, \
                patch.object(MODULE, "object_inventory", return_value=set()), \
                patch.object(MODULE.uuid, "uuid4", return_value="12345678-1234-4123-8123-123456789abc"), \
                patch.object(MODULE, "call", side_effect=fake_call), \
                redirect_stdout(out), redirect_stderr(err):
            result = MODULE.main()
        self.assertEqual(audit.call_count, 2)
        return result, out.getvalue(), err.getvalue(), calls

    @staticmethod
    def put_ok() -> tuple[int, bytes]:
        """Return a matching Cloudflare multipart-upload envelope."""

        return 200, json.dumps({"success": True, "result": {
            "key": "verification/12345678-1234-4123-8123-123456789abc.eml",
            "size": str(len(MODULE.SENTINEL)),
        }}).encode()

    def test_success_exercises_put_get_delete_get_and_final_readback(self) -> None:
        """A green marker requires byte equality and two absence observations."""

        code, out, err, calls = self.run_probe([
            self.put_ok(), (200, MODULE.SENTINEL), (200, b'{"success":true,"result":{}}'),
            (404, b""), (404, b""),
        ])
        self.assertEqual((code, out.strip(), err),
                         (0, "staging_r2_object_capability_verified", ""))
        self.assertEqual(calls, ["PUT", "GET", "DELETE", "GET", "GET"])

    def test_put_403_is_inconclusive_and_never_retried(self) -> None:
        """Write denial does not claim read/delete permission was tested."""

        code, out, err, calls = self.run_probe([(403, b"private-provider-body"), (404, b"")])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertEqual(err.strip(), "staging_r2_object_capability_failed:r2_put_denied")
        self.assertEqual(calls, ["PUT", "GET"])

    def test_ambiguous_put_reconciles_then_deletes_without_put_retry(self) -> None:
        """A lost PUT response triggers GET before exact-key cleanup."""

        code, _, err, calls = self.run_probe([
            MODULE.ProbeFailure("r2_outcome_ambiguous"), (200, MODULE.SENTINEL),
            (200, b'{"success":true,"result":{}}'), (404, b""),
        ])
        self.assertEqual(code, 1)
        self.assertEqual(err.strip(), "staging_r2_object_capability_failed:r2_outcome_ambiguous")
        self.assertEqual(calls, ["PUT", "GET", "DELETE", "GET"])

    def test_ambiguous_delete_reads_back_before_conditional_cleanup(self) -> None:
        """Never blindly repeat DELETE when its first result is unknown."""

        code, _, err, calls = self.run_probe([
            self.put_ok(), (200, MODULE.SENTINEL),
            MODULE.ProbeFailure("r2_outcome_ambiguous"), (200, MODULE.SENTINEL),
            (200, b'{"success":true,"result":{}}'), (404, b""),
        ])
        self.assertEqual(code, 1)
        self.assertEqual(err.strip(), "staging_r2_object_capability_failed:r2_outcome_ambiguous")
        self.assertEqual(calls, ["PUT", "GET", "DELETE", "GET", "DELETE", "GET"])

    def test_cleanup_failure_is_fail_closed_and_leaks_nothing(self) -> None:
        """Even a provider exception cannot print token, key or response body."""

        code, out, err, calls = self.run_probe([
            self.put_ok(), (200, MODULE.SENTINEL), (403, b"private-provider-body"),
            (200, MODULE.SENTINEL), (403, b"private-provider-body"),
            (200, MODULE.SENTINEL),
        ])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertEqual(err.strip(), "staging_r2_object_capability_failed:r2_cleanup_unverified")
        self.assertEqual(calls, ["PUT", "GET", "DELETE", "GET", "DELETE", "GET"])
        for private in ("private-token", "private-route-token", "verification/", "provider-body",
                        MODULE.SENTINEL.decode()):
            self.assertNotIn(private, out + err)

    def test_workflow_is_manual_branch_only_and_secret_final_step(self) -> None:
        """No push, PR, or B registration path can execute the probe."""

        workflow = (MODULE.ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job = workflow.split("  staging-r2-object-capability:\n", 1)[1].split(
            "\n  staging-second-principal-preflight:", 1
        )[0]
        self.assertIn("github.event_name == 'workflow_dispatch'", job)
        self.assertIn("github.ref == 'refs/heads/codex/amail-v0.1.0'", job)
        self.assertIn("environment: staging", job)
        self.assertIn("group: staging-native-mail-acceptance", job)
        self.assertIn("RUN_STAGING_R2_OBJECT_CAPABILITY", job)
        self.assertEqual(job.count("secrets.CLOUDFLARE_API_TOKEN"), 1)
        self.assertLess(job.index("Require explicit object-operation confirmation"),
                        job.index("secrets.CLOUDFLARE_API_TOKEN"))
        self.assertNotIn("STAGING_E2E_B_PASSWORD", job)
        self.assertNotIn("--apply", job)


if __name__ == "__main__":
    unittest.main()
