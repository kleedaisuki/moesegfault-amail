"""Mock-only negative authorization and no-local-archive tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from workflow_source import job_block


TESTS = Path(__file__).parent
sys.path.insert(0, str(TESTS))
SPEC = importlib.util.spec_from_file_location(
    "staging_two_principal_isolation", TESTS / "staging_two_principal_isolation.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class IsolationContracts(unittest.TestCase):
    """A foreign 404 is valid only if no bytes or archive escape."""

    def test_owner_projection_ignores_only_fresh_request_id(self) -> None:
        """Repeated GETs differ in correlation ID, not message semantics."""

        prior = {"id": "m1", "read": False, "request_id": "first"}
        later = {"id": "m1", "read": False, "request_id": "second"}
        self.assertEqual(MODULE.stable_owner_row(prior), MODULE.stable_owner_row(later))
        self.assertNotEqual(MODULE.stable_owner_row(prior), MODULE.stable_owner_row({
            **later, "read": True,
        }))

    def test_typed_404_requires_empty_stdout(self) -> None:
        """Reject 200, leaked JSON and untyped errors with fixed labels."""

        denied = subprocess.CompletedProcess(
            ["amail"], 1, b"",
            b"amail: mail API messages.get failed: HTTP 404, code=not_found\n",
        )
        with patch.object(MODULE.subprocess, "run", return_value=denied):
            MODULE.foreign_denied(Path("amail"), {}, "get", "foreign-id")
        leaked = subprocess.CompletedProcess(denied.args, 1, b"{}\n", denied.stderr)
        with patch.object(MODULE.subprocess, "run", return_value=leaked):
            with self.assertRaises(MODULE.mail.ProbeFailure):
                MODULE.foreign_denied(Path("amail"), {}, "get", "foreign-id")
        accepted = subprocess.CompletedProcess(denied.args, 0, b"", denied.stderr)
        with patch.object(MODULE.subprocess, "run", return_value=accepted):
            with self.assertRaises(MODULE.mail.ProbeFailure):
                MODULE.foreign_denied(Path("amail"), {}, "get", "foreign-id")

    def test_written_archive_is_removed_and_fails(self) -> None:
        """Do not leave a B-local ZIP even when CLI erroneously returns 404."""

        MODULE.mail.TEMP.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=MODULE.mail.TEMP) as directory:
            path = Path(directory) / "foreign.zip"

            def writes(*args, **kwargs):
                path.write_bytes(b"private-mail")
                return subprocess.CompletedProcess(
                    ["amail"], 1, b"",
                    b"amail: mail API messages.read failed: HTTP 404, code=not_found\n",
                )

            with patch.object(MODULE.subprocess, "run", side_effect=writes):
                with self.assertRaises(MODULE.mail.ProbeFailure) as caught:
                    MODULE.foreign_denied(Path("amail"), {}, "read", "foreign-id", output=path)
            self.assertEqual(str(caught.exception), "foreign_archive_created")
            self.assertFalse(path.exists())

    def test_rejected_mutation_still_requires_owner_unchanged(self) -> None:
        """A 404 alone cannot pass when the owner row changed as a side effect."""

        MODULE.mail.TEMP.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=MODULE.mail.TEMP) as directory:
            home_a, home_b = Path(directory) / "a", Path(directory) / "b"
            home_a.mkdir()
            home_b.mkdir()
            address = "e2e-0123456789abcdef@mail-staging.moesegfault.dev"
            signal = "signal_id"
            distractor = "distractor_id"
            subjects = ("AMAIL-E2E-0123456789abcdef-Signal",
                        "AMAIL-E2E-0123456789abcdef-Distractor")
            prior = {"id": signal, "read": False, "request_id": "r1", "mailbox": address,
                     "subject": subjects[0], "metadata": {"message_id": "receipt"}}
            other = {"id": distractor, "read": False, "request_id": "r2", "mailbox": address,
                     "subject": subjects[1]}

            def fake_amail(binary, env, *args, failure):
                return [{"authenticated": True}] if args == ("auth", "status") else []

            with patch.object(MODULE.mail, "cli_env", side_effect=lambda home: {"home": str(home)}), \
                    patch.object(MODULE.mail, "amail", side_effect=fake_amail), \
                    patch.object(MODULE, "owner_row", side_effect=[prior, other,
                                                                   {**prior, "read": True}]), \
                    patch.object(MODULE, "foreign_denied"):
                with self.assertRaises(MODULE.mail.ProbeFailure) as caught:
                    MODULE.assert_foreign_isolation(
                        Path("amail"), home_a, home_b, address, signal, distractor,
                        subjects, "receipt", "zone", "token",
                    )
            self.assertEqual(str(caught.exception), "owner_state_changed_by_foreign")

    def test_second_confirmation_is_independent(self) -> None:
        """The A SMTP confirmation must not silently enable B operations."""

        workflow = (TESTS.parents[1] / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job = job_block(workflow, "staging-e2e")
        self.assertIn("AMAIL_STAGING_ISOLATION_CONFIRM: ${{ inputs.isolation_confirm }}", job)
        self.assertIn("AMAIL_STAGING_ISOLATION_E2E: ${{ inputs.isolation && '1' || '0' }}", job)


if __name__ == "__main__":
    unittest.main()
