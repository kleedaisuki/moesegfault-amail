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
    "AMAIL_R2_CAPABILITY_MODE": "probe",
    "GITHUB_RUN_ID": "123456789",
    "GITHUB_RUN_ATTEMPT": "1",
    "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
    "CLOUDFLARE_API_TOKEN": "private-token-not-for-output",
    "CF_EMAIL_ROUTING_TOKEN": "private-route-token-not-for-output",
}


class R2ObjectCapabilityTests(unittest.TestCase):
    """Pin phase handling, exact cleanup and fixed-label privacy."""

    KEY, BODY = MODULE.sentinel_for(ENV["GITHUB_RUN_ID"], ENV["GITHUB_RUN_ATTEMPT"])

    def run_probe(self, replies: list[tuple[int, bytes] | Exception],
                  environment: dict[str, str] | None = None) -> tuple[int, str, str, list[str]]:
        """Execute against a deterministic run identity and synthetic REST responses."""

        calls: list[str] = []

        def fake_call(method, path, token, data=None, content_type=None):
            self.assertEqual(token, ENV["CLOUDFLARE_API_TOKEN"])
            self.assertIn("/" + self.KEY, path)
            calls.append(method)
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply

        out, err = StringIO(), StringIO()
        with patch.dict(os.environ, environment or ENV, clear=True), \
                patch.object(MODULE, "audit") as audit, \
                patch.object(MODULE, "object_inventory", return_value=set()), \
                patch.object(MODULE, "call", side_effect=fake_call), \
                redirect_stdout(out), redirect_stderr(err):
            result = MODULE.main()
        self.assertEqual(audit.call_count, 2)
        return result, out.getvalue(), err.getvalue(), calls

    @classmethod
    def put_ok(cls) -> tuple[int, bytes]:
        """Return a matching Cloudflare multipart-upload envelope."""

        return 200, json.dumps({"success": True, "result": {
            "key": cls.KEY,
            "size": str(len(cls.BODY)),
        }}).encode()

    def test_success_exercises_put_get_delete_get_and_final_readback(self) -> None:
        """A green marker requires byte equality and two absence observations."""

        code, out, err, calls = self.run_probe([
            self.put_ok(), (200, self.BODY), (200, b'{"success":true,"result":{}}'),
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
            MODULE.ProbeFailure("r2_outcome_ambiguous"), (200, self.BODY),
            (200, b'{"success":true,"result":{}}'), (404, b""),
        ])
        self.assertEqual(code, 1)
        self.assertEqual(err.strip(), "staging_r2_object_capability_failed:r2_outcome_ambiguous")
        self.assertEqual(calls, ["PUT", "GET", "DELETE", "GET"])

    def test_ambiguous_put_never_deletes_foreign_content(self) -> None:
        """Predictable keys are not permission to erase a racing writer's bytes."""

        code, _, err, calls = self.run_probe([
            MODULE.ProbeFailure("r2_outcome_ambiguous"),
            (200, b"different-object-that-is-not-our-sentinel"),
        ])
        self.assertEqual(code, 1)
        self.assertEqual(err.strip(), "staging_r2_object_capability_failed:r2_cleanup_unverified")
        self.assertEqual(calls, ["PUT", "GET"])

    def test_ambiguous_delete_reads_back_before_conditional_cleanup(self) -> None:
        """Never blindly repeat DELETE when its first result is unknown."""

        code, _, err, calls = self.run_probe([
            self.put_ok(), (200, self.BODY),
            MODULE.ProbeFailure("r2_outcome_ambiguous"), (200, self.BODY),
            (200, b'{"success":true,"result":{}}'), (404, b""),
        ])
        self.assertEqual(code, 1)
        self.assertEqual(err.strip(), "staging_r2_object_capability_failed:r2_outcome_ambiguous")
        self.assertEqual(calls, ["PUT", "GET", "DELETE", "GET", "DELETE", "GET"])

    def test_cleanup_failure_is_fail_closed_and_leaks_nothing(self) -> None:
        """Even a provider exception cannot print token, key or response body."""

        code, out, err, calls = self.run_probe([
            self.put_ok(), (200, self.BODY), (403, b"private-provider-body"),
            (200, self.BODY), (403, b"private-provider-body"),
            (200, self.BODY),
        ])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertEqual(err.strip(), "staging_r2_object_capability_failed:r2_cleanup_unverified")
        self.assertEqual(calls, ["PUT", "GET", "DELETE", "GET", "DELETE", "GET"])
        for private in ("private-token", "private-route-token", "verification/", "provider-body",
                        self.BODY.decode()):
            self.assertNotIn(private, out + err)

    def test_run_identity_is_reproducible_distinct_and_uuidv4(self) -> None:
        """A cancelled run can recover its exact key and bytes without logs."""

        key, body = MODULE.sentinel_for("123456789", "1")
        self.assertEqual((key, body), (self.KEY, self.BODY))
        self.assertRegex(key, MODULE.KEY)
        self.assertNotEqual(key, MODULE.sentinel_for("123456789", "2")[0])
        self.assertNotEqual(body, MODULE.sentinel_for("123456788", "1")[1])
        self.assertNotIn(b"123456789", body)
        for run_id, attempt in (("", "1"), ("0", "1"), ("1x", "1"), ("1", "0"),
                                ("1", "01"), ("1", "1x")):
            with self.assertRaises(MODULE.ProbeFailure):
                MODULE.sentinel_for(run_id, attempt)

    def test_recovery_never_puts_and_deletes_only_matching_bytes(self) -> None:
        """Prior run and attempt identify one disposable synthetic object."""

        env = {**ENV, "AMAIL_R2_CAPABILITY_MODE": "recover",
               "AMAIL_R2_CAPABILITY_CONFIRM": "RECOVER_STAGING_R2_OBJECT_CAPABILITY",
               "AMAIL_R2_PRIOR_RUN_ID": ENV["GITHUB_RUN_ID"],
               "AMAIL_R2_PRIOR_RUN_ATTEMPT": "1"}
        code, out, err, calls = self.run_probe([
            (200, self.BODY), (200, b'{"success":true,"result":{}}'),
            (404, b""), (404, b""),
        ], env)
        self.assertEqual((code, out.strip(), err),
                         (0, "staging_r2_object_capability_recovered_absent", ""))
        self.assertEqual(calls, ["GET", "DELETE", "GET", "GET"])

    def test_recovery_refuses_foreign_body_and_rerun_probe(self) -> None:
        """A wrong body or rerun attempt cannot overwrite or delete anything."""

        env = {**ENV, "AMAIL_R2_CAPABILITY_MODE": "recover",
               "AMAIL_R2_CAPABILITY_CONFIRM": "RECOVER_STAGING_R2_OBJECT_CAPABILITY",
               "AMAIL_R2_PRIOR_RUN_ID": ENV["GITHUB_RUN_ID"],
               "AMAIL_R2_PRIOR_RUN_ATTEMPT": "1"}
        code, _, err, calls = self.run_probe([(200, b"foreign-private-content")], env)
        self.assertEqual(code, 1)
        self.assertEqual(err.strip(), "staging_r2_object_capability_failed:r2_object_mismatch")
        self.assertEqual(calls, ["GET"])
        env = {**ENV, "GITHUB_RUN_ATTEMPT": "2"}
        code, _, err, calls = self.run_probe([], env)
        self.assertEqual(code, 1)
        self.assertEqual(err.strip(), "staging_r2_object_capability_failed:probe_rerun_forbidden")
        self.assertEqual(calls, [])

    def test_recovery_absent_or_denied_never_mutates(self) -> None:
        """Only a byte-matching existing object is a recovery delete target."""

        env = {**ENV, "AMAIL_R2_CAPABILITY_MODE": "recover",
               "AMAIL_R2_CAPABILITY_CONFIRM": "RECOVER_STAGING_R2_OBJECT_CAPABILITY",
               "AMAIL_R2_PRIOR_RUN_ID": ENV["GITHUB_RUN_ID"],
               "AMAIL_R2_PRIOR_RUN_ATTEMPT": "1"}
        code, out, err, calls = self.run_probe([(404, b""), (404, b"")], env)
        self.assertEqual((code, out.strip(), err),
                         (0, "staging_r2_object_capability_recovered_absent", ""))
        self.assertEqual(calls, ["GET", "GET"])
        code, out, err, calls = self.run_probe([(403, b"unlogged-provider-body")], env)
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertEqual(err.strip(), "staging_r2_object_capability_failed:r2_get_denied")
        self.assertEqual(calls, ["GET"])

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
        self.assertIn("RECOVER_STAGING_R2_OBJECT_CAPABILITY", job)
        self.assertIn("inputs.target == 'staging-r2-object-recover'", job)
        self.assertIn("AMAIL_R2_PRIOR_RUN_ID: ${{ inputs.r2_prior_run_id }}", job)
        self.assertIn("AMAIL_R2_PRIOR_RUN_ATTEMPT: ${{ inputs.r2_prior_run_attempt }}", job)
        self.assertEqual(job.count("secrets.CLOUDFLARE_API_TOKEN"), 1)
        self.assertLess(job.index("Require explicit object-operation confirmation"),
                        job.index("secrets.CLOUDFLARE_API_TOKEN"))
        self.assertNotIn("STAGING_E2E_B_PASSWORD", job)
        self.assertNotIn("--apply", job)


if __name__ == "__main__":
    unittest.main()
