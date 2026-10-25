"""A backend checkpoint is usable only with actual accepted unchanged producer input."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/ci"))
import changes
import mail_backend_artifact as backend


class BackendCheckpointTests(unittest.TestCase):
    def test_pending_checkpoint_does_not_skip_source_admission(self) -> None:
        (ROOT / ".temp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder:
            root = Path(folder)
            record = root / "infra/ci/accepted-backend.json"
            record.parent.mkdir(parents=True)
            record.write_text(json.dumps({"schema": "amail-accepted-backend/v1", "source_run": None, "source_sha": None}), encoding="utf-8")
            with patch.object(changes, "ROOT", root), patch.object(backend, "producer") as producer:
                self.assertIsNone(changes.backend_base("a" * 40))
                producer.assert_not_called()

    def test_changed_runtime_cannot_reuse_an_accepted_backend(self) -> None:
        (ROOT / ".temp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder:
            root = Path(folder)
            record = root / "infra/ci/accepted-backend.json"
            record.parent.mkdir(parents=True)
            record.write_text(json.dumps({"schema": "amail-accepted-backend/v1", "source_run": "123", "source_sha": "a" * 40}), encoding="utf-8")
            with patch.object(changes, "ROOT", root), \
                 patch.object(backend, "producer", return_value={"source_sha": "a" * 40}), \
                 patch.object(backend.accepted, "runtime_closure", side_effect=ValueError("accepted_source_runtime_changed")):
                self.assertIsNone(changes.backend_base("b" * 40))


if __name__ == "__main__":
    unittest.main()
