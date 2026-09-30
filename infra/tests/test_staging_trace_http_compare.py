"""Offline, privacy-focused fixtures for the staging transport comparison."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent))
import staging_trace_http_compare as compare  # noqa: E402


class HeaderBag:
    """Minimal email-style header collection with duplicate-header support."""

    def __init__(self, values: dict[str, list[str]]) -> None:
        self.values = values

    def get_all(self, key: str, default=None):
        """Return every matching header, not only the first value."""

        return self.values.get(key, default)


class CompareTests(unittest.TestCase):
    """Require closed labels, no raw provider text, and strict 401 acceptance."""

    def test_status_classes(self) -> None:
        """Keep 401 and 403 distinct while bucketing arbitrary status codes."""

        self.assertEqual([compare.status_label(status) for status in
                          (200, 302, 401, 403, 404, 503, 777)],
                         ["2xx", "3xx", "401", "403", "other_4xx", "5xx", "other"])

    def test_header_facts_reject_duplicate_or_malformed_ids(self) -> None:
        """An intermediary's malformed header cannot satisfy Worker contract."""

        valid = "11111111-1111-4111-8111-111111111111"
        self.assertEqual(compare.header_facts(HeaderBag({
            "x-amail-request-id": [valid], "cf-ray": ["private-ray"],
        })), (True, True))
        for ids in ([], [valid, valid], ["private-value"]):
            self.assertEqual(compare.header_facts(HeaderBag({
                "x-amail-request-id": ids, "cf-ray": ["private-ray", "private-ray"],
            })), (False, False))

    def test_comparison_never_promotes_403_or_redirect(self) -> None:
        """Only both 401 plus valid IDs without redirect observe the contract."""

        self.assertEqual(compare.compare(("401", True, False, False),
                                         ("401", True, True, False)),
                         "both_worker_contract_observed")
        self.assertEqual(compare.compare(("403", False, True, False),
                                         ("401", True, True, False)),
                         "transport_difference_unverified")
        self.assertEqual(compare.compare(("403", False, True, False),
                                         ("403", False, True, False)),
                         "same_noncontract_response_unverified")
        self.assertEqual(compare.compare(("401", True, True, True),
                                         ("401", True, True, False)),
                         "transport_difference_unverified")

    def test_child_environment_excludes_provider_capabilities(self) -> None:
        """Rust only inherits OS/proxy settings, not Cloudflare credentials."""

        with patch.dict(compare.os.environ, {
            "CLOUDFLARE_API_TOKEN": "private-token",
            "CF_OBSERVABILITY_TOKEN": "private-token",
            "HTTPS_PROXY": "http://private-proxy.invalid",
        }, clear=True):
            inherited = compare.reqwest_environment()
        self.assertEqual(set(inherited), {"HTTPS_PROXY"})
        self.assertNotIn("CLOUDFLARE_API_TOKEN", inherited)


if __name__ == "__main__":
    unittest.main()
