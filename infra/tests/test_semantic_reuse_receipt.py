"""Only cleaned same-run semantic reuse acceptance leaves the live harness."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT: Path = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/tests"))
import staging_semantic_e2e as semantic


class SemanticReuseReceiptTests(unittest.TestCase):
    def runtime(self) -> dict[str, str]:
        return {"schema": "semantic-index-reuse/v1", "realm": "staging",
            "run_id": "123", "source_sha": "a" * 40,
            "api_version": "12345678-1234-1234-1234-123456789abc",
            "maintenance_version": "12345678-1234-1234-1234-123456789abd",
            "sink_version": "12345678-1234-1234-1234-123456789abe"}

    def test_same_run_pins_are_preserved_without_claiming_a_new_cli_build(self) -> None:
        receipt: dict[str, str] = semantic.reuse_receipt(self.runtime(), run_id="123", checkout_sha="a" * 40)
        self.assertEqual(receipt, {**self.runtime(), "schema": "semantic-index-reuse-acceptance/v1",
                                  "cli_release": "v0.3.1"})

    def test_foreign_realm_run_source_or_malformed_pin_is_rejected(self) -> None:
        for key, value in {"schema": "unknown", "realm": "production", "run_id": "456",
                           "source_sha": "b" * 40, "api_version": "unknown",
                           "maintenance_version": "unknown", "sink_version": "unknown"}.items():
            with self.subTest(key=key), self.assertRaisesRegex(semantic.mail.ProbeFailure, "runtime_unverified"):
                semantic.reuse_receipt({**self.runtime(), key: value}, run_id="123", checkout_sha="a" * 40)
        with self.assertRaisesRegex(semantic.mail.ProbeFailure, "identity_invalid"):
            semantic.reuse_receipt(self.runtime(), run_id="", checkout_sha="a" * 40)

    def test_operator_facts_cannot_leak_into_the_closed_acceptance_receipt(self) -> None:
        receipt: dict[str, str] = semantic.reuse_receipt({**self.runtime(), "private_note": "never export"},
                                                       run_id="123", checkout_sha="a" * 40)
        self.assertEqual(set(receipt), {"schema", "realm", "run_id", "source_sha", "api_version",
                                      "maintenance_version", "sink_version", "cli_release"})
        self.assertNotIn("never export", str(receipt))


if __name__ == "__main__":
    unittest.main()
