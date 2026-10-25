"""Compose the narrow journey's receipt for the existing promotion consumer."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
from typing import Any
import unittest
from unittest.mock import patch

ROOT: Path = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/tests"))
sys.path.insert(0, str(ROOT / "infra/ci"))
import accepted_staging_artifact as promotion
import staging_semantic_e2e as semantic


class SemanticReceiptTests(unittest.TestCase):
    def runtime(self) -> dict[str, str]:
        return {"schema": "staging-semantic-acceptance/v1",
            "source_run_id": semantic.SOURCE_RUN, "source_sha": semantic.SOURCE_SHA,
            "run_id": "456", "checkout_sha": "b" * 40,
            "api_version": semantic.API_VERSION, "sink_version": semantic.SINK_VERSION,
            "maintenance_version": "12345678-1234-1234-1234-123456789abc"}

    def test_composed_receipt_is_accepted_without_relabeling_the_producer(self) -> None:
        receipt: dict[str, str] = semantic.acceptance_receipt(self.runtime(), run_id="456", checkout_sha="b" * 40)
        self.assertEqual(receipt, self.runtime())
        state: dict[str, Any] = {"producer": {"run_id": semantic.SOURCE_RUN, "source_sha": semantic.SOURCE_SHA},
            "acceptance": {"run_id": "456", "source_sha": "b" * 40, "artifact_id": 12}}
        (ROOT / ".temp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder:
            path: Path = Path(folder) / "staging-semantic-acceptance.json"
            path.write_text(json.dumps(receipt), encoding="utf-8")
            with patch.object(promotion, "ACCEPTANCE", path):
                self.assertEqual(promotion.verify_acceptance_receipt(state), receipt)

    def test_foreign_producer_checkout_or_runtime_pin_cannot_be_certified(self) -> None:
        changes: dict[str, str] = {"source_run_id": "999", "source_sha": "c" * 40,
            "run_id": "999", "checkout_sha": "c" * 40,
            "api_version": "12345678-1234-1234-1234-123456789abc",
            "sink_version": "12345678-1234-1234-1234-123456789abc",
            "maintenance_version": "not-a-runtime-version"}
        for key, value in changes.items():
            runtime: dict[str, str] = {**self.runtime(), key: value}
            with self.subTest(key=key), self.assertRaisesRegex(semantic.mail.ProbeFailure, "runtime_unverified"):
                semantic.acceptance_receipt(runtime, run_id="456", checkout_sha="b" * 40)

    def test_receipt_has_only_the_consumers_closed_public_shape(self) -> None:
        runtime: dict[str, str] = self.runtime()
        runtime["private_mail_body"] = "synthetic must not be published"
        with self.assertRaisesRegex(semantic.mail.ProbeFailure, "runtime_unverified"):
            semantic.acceptance_receipt(runtime, run_id="456", checkout_sha="b" * 40)
        for run_id, sha in (("", "b" * 40), ("456", "unknown")):
            with self.subTest(run_id=run_id), self.assertRaisesRegex(semantic.mail.ProbeFailure, "identity_invalid"):
                semantic.acceptance_receipt(self.runtime(), run_id=run_id, checkout_sha=sha)


if __name__ == "__main__":
    unittest.main()
