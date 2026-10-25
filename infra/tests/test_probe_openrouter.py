"""Synthetic-only provider admission shares the production Voyage wire shape."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/provider"))
import probe_openrouter as probe


class ProbeTests(unittest.TestCase):
    def test_both_input_roles_require_real_contract(self) -> None:
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "synthetic"}), \
             patch.object(probe, "probe") as request, patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(probe.main(), 0)
        self.assertEqual([call.args for call in request.call_args_list],
                         [("synthetic", "query"), ("synthetic", "document")])

    def test_payload_exact_model_float_dimensions_privacy_and_role(self) -> None:
        for role in ("query", "document"):
            opener = MagicMock()
            response = opener.open.return_value.__enter__.return_value
            response.read.return_value = json.dumps({"data": [{"embedding": [1.0] * 256}]}).encode()
            with patch.object(probe.urllib.request, "build_opener", return_value=opener) as build:
                probe.probe("synthetic", role)
            self.assertIsInstance(build.call_args.args[0], probe.NoRedirect)
            request = opener.open.call_args.args[0]
            self.assertEqual(json.loads(request.data), {
                "model": "voyageai/voyage-4", "input": probe.SYNTHETIC_INPUT,
                "dimensions": 256, "encoding_format": "float", "input_type": role,
                "provider": {"only": ["voyageai"], "allow_fallbacks": False, "data_collection": "deny"}})
            self.assertEqual(opener.open.call_args.kwargs["timeout"], 90)
            response.read.assert_called_once_with(64 * 1024 + 1)

    def test_oversize_body_is_not_parsed_or_printed(self) -> None:
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = b"x" * (64 * 1024 + 1)
        with patch.object(probe.urllib.request, "build_opener", return_value=opener):
            with self.assertRaisesRegex(ValueError, "embedding_response_too_large"):
                probe.probe("synthetic", "query")


if __name__ == "__main__":
    unittest.main()
