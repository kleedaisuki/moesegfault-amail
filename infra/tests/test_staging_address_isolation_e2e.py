"""Mock-only contract checks for the opt-in address isolation probe."""

from __future__ import annotations

from pathlib import Path
import subprocess
from unittest import mock
import unittest

import staging_address_isolation_e2e as probe


class AddressIsolationHarnessTests(unittest.TestCase):
    """Verify fail-closed observations without network, Identity, or routes."""

    def test_negative_cli_requires_expected_code(self) -> None:
        """A generic nonzero exit is not sufficient for an ownership claim."""

        with mock.patch.object(probe.subprocess, "run", return_value=subprocess.CompletedProcess(
            [], 1, b"", b"mail API addresses.add failed: HTTP 409, code=address_unavailable, correlation_id=x"
        )):
            probe.cli_error(Path("amail.exe"), {}, "address_unavailable", "address", "add", "x")
            with self.assertRaisesRegex(probe.IsolationFailure, "negative_cli_code_mismatch"):
                probe.cli_error(Path("amail.exe"), {}, "address_limit", "address", "add", "x")

    def test_confirmation_fails_before_any_provider_action(self) -> None:
        """No dispatch confirmation means even preflight must not consume routes."""

        with mock.patch.dict(probe.os.environ, {}, clear=True), mock.patch.object(
            probe.mail, "inside_temp", side_effect=AssertionError("should not read paths")
        ):
            with self.assertRaisesRegex(probe.IsolationFailure, "explicit_confirmation_required"):
                probe.execute(Path("x"), Path("a"), Path("b"), "0" * 16, "0" * 32, "t", "s")

    def test_accepted_smtp_is_not_rejection_evidence(self) -> None:
        """SMTP 250 cannot silently be reported as retired-address rejection."""

        connection = mock.MagicMock()
        connection.__enter__.return_value.sendmail.return_value = {}
        with mock.patch.object(probe.smtplib, "SMTP_SSL", return_value=connection):
            with self.assertRaisesRegex(probe.IsolationFailure, "retired_smtp_accepted_inconclusive"):
                probe.rejected_smtp("t", "x@mail-staging.moesegfault.dev", "0" * 16)

    def test_transient_smtp_refusal_is_not_pass(self) -> None:
        """Only a permanent recipient response establishes the narrow claim."""

        with self.assertRaisesRegex(probe.IsolationFailure, "retired_smtp_transient_or_unknown_refusal"):
            probe.require_permanent_refusal((450, b"try later"))
        probe.require_permanent_refusal((550, b"no such recipient"))

    def test_unexpected_negative_mutation_is_reconciled(self) -> None:
        """A successful eleventh-name request remains in the cleanup ledger."""

        address = "q10-0000000000000000@mail-staging.moesegfault.dev"
        current = {"a": {address}, "b": set()}

        def fake_owned(_binary: Path, env: dict[str, str]) -> set[str]:
            return set(current[env["owner"]])

        def fake_amail(_binary: Path, env: dict[str, str], *args: str, failure: str) -> list[dict]:
            self.assertEqual(args[:2], ("address", "delete"))
            current[env["owner"]].discard(args[2])
            return []

        with mock.patch.object(probe, "owned", side_effect=fake_owned), mock.patch.object(
            probe.mail, "amail", side_effect=fake_amail
        ), mock.patch.object(probe, "route_snapshot", return_value={address: []}):
            probe.reconcile_candidates(Path("amail.exe"), {"owner": "a"}, {"owner": "b"},
                                       "z", "t", {address: {"a"}}, {address: []})
        self.assertFalse(current["a"])

    def test_preexisting_operator_route_is_never_deleted(self) -> None:
        """A reserved-name regression with an existing rule needs manual repair."""

        address = "postmaster@mail-staging.moesegfault.dev"
        baseline = {address: [{"id": "operator-rule"}]}
        with mock.patch.object(probe, "owned", return_value={address}), mock.patch.object(
            probe.mail, "amail", side_effect=AssertionError("must not delete")
        ), mock.patch.object(probe, "route_snapshot", return_value=baseline), mock.patch.object(
            probe.time, "monotonic", side_effect=[0, 1, 100]
        ), mock.patch.object(probe.time, "sleep"):
            with self.assertRaisesRegex(probe.IsolationFailure, "candidate_reconciliation_required"):
                probe.reconcile_candidates(Path("amail.exe"), {}, {}, "z", "t",
                                           {address: {"a"}}, baseline)


if __name__ == "__main__":
    unittest.main()
