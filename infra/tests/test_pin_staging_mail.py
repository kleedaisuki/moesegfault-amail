"""Synthetic tests for the read-only staging serving-version pin."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "crates/mail-worker"))
import pin_staging_mail as pin  # noqa: E402  pylint: disable=wrong-import-position


VERSION = "988a2f02-da5d-406d-9f60-2723e19c2398"
OTHER = "12345678-1234-1234-1234-123456789abc"


def deployment(version: str = VERSION, percentage: int = 100,
               deployment_id: str = OTHER) -> dict:
    """Create a provider-shaped current deployment."""

    return {"deployments": [{"id": deployment_id, "strategy": "percentage", "versions": [
        {"version_id": version, "percentage": percentage}
    ]}]}


def bindings() -> list[dict]:
    """Build exact staged bindings from the reviewed Wrangler config."""

    result = []
    for name, (kind, value) in pin.expected_bindings().items():
        item = {"name": name, "type": kind}
        if kind == "d1":
            item["database_id"] = value
        elif kind == "r2_bucket":
            item["bucket_name"] = value
        elif kind == "plain_text":
            item["text"] = value
        result.append(item)
    return result


def settings() -> dict:
    """Build the minimal accepted privacy settings."""

    return {"observability": {
        "enabled": True, "head_sampling_rate": 1.0, "redact_query_string": True,
        "logs": {"enabled": True, "invocation_logs": False},
        "traces": {"enabled": False},
    }}


class PinTests(unittest.TestCase):
    """Reject drift and unverified data without printing provider response bodies."""

    def test_exact_serving_version(self) -> None:
        """Only a single 100-percent version is a pin."""

        self.assertEqual(pin.serving_deployment(deployment()), (OTHER, VERSION))
        self.assertIsNone(pin.serving_deployment(deployment(percentage=99)))
        split = deployment()
        split["deployments"][0]["versions"].append({"version_id": OTHER, "percentage": 10})
        self.assertIsNone(pin.serving_deployment(split))
        self.assertIsNone(pin.serving_deployment({"deployments": []}))

    def test_binding_targets_and_secrets(self) -> None:
        """Production resource drift and unexpected bindings fail closed."""

        good = {"id": VERSION, "resources": {"bindings": bindings()}}
        self.assertTrue(pin.bindings_match(good, VERSION))
        wrapped = {"id": VERSION, "resources": {"bindings": {"result": bindings()}}}
        self.assertTrue(pin.bindings_match(wrapped, VERSION))
        wrong = {"id": VERSION, "resources": {"bindings": bindings()}}
        next(item for item in wrong["resources"]["bindings"] if item["name"] == "MAIL_DB")["database_id"] = OTHER
        self.assertFalse(pin.bindings_match(wrong, VERSION))
        wrong = {"id": VERSION, "resources": {"bindings": bindings()}}
        next(item for item in wrong["resources"]["bindings"] if item["name"] == "INGRESS_SECRET")["type"] = "plain_text"
        self.assertFalse(pin.bindings_match(wrong, VERSION))
        wrong = {"id": VERSION, "resources": {"bindings": bindings()}}
        wrong["resources"]["bindings"].append({"name": "UNREVIEWED", "type": "secret_text"})
        self.assertFalse(pin.bindings_match(wrong, VERSION))
        self.assertFalse(pin.bindings_match({"id": VERSION, "resources": {"bindings": {}}}, VERSION))
        self.assertFalse(pin.bindings_match({"id": VERSION, "resources": {"bindings": {"result": []}}}, VERSION))
        self.assertFalse(pin.bindings_match({"id": VERSION, "resources": {"bindings": {"result": bindings(), "unknown": True}}}, VERSION))

    @patch.object(pin, "fetch")
    def test_readback_is_bookended_by_deployment(self, fetch) -> None:
        """A rollout between initial and final GET cannot yield a match."""

        safe = settings()
        version = {"id": VERSION, "resources": {"bindings": bindings()}}
        fetch.side_effect = [deployment(), version, safe, safe, deployment()]
        self.assertEqual(pin.run("a" * 32, "private", VERSION), "match")
        self.assertEqual(fetch.call_count, 5)
        fetch.side_effect = [deployment(), version, safe, safe, deployment(OTHER)]
        self.assertEqual(pin.run("a" * 32, "private", VERSION), "deployment_changed")
        fetch.side_effect = [deployment(), version, safe, safe,
                             deployment(deployment_id=VERSION)]
        self.assertEqual(pin.run("a" * 32, "private", VERSION), "deployment_changed")
        fetch.side_effect = [deployment(OTHER)]
        self.assertEqual(pin.run("a" * 32, "private", VERSION), "version_mismatch")

    @patch.object(pin, "fetch")
    def test_inprocess_run_loads_sibling_privacy_check(self, fetch) -> None:
        """A guarded job may call run without this script's __main__ path setup."""

        safe = settings()
        version = {"id": VERSION, "resources": {"bindings": bindings()}}
        fetch.side_effect = [deployment(), version, safe, safe, deployment()]
        module_dir = pin.CONFIG.parent.resolve()
        without_sibling = [path for path in sys.path if Path(path).resolve() != module_dir]
        with patch.object(sys, "path", without_sibling), patch.dict(sys.modules):
            sys.modules.pop("check_observability", None)
            self.assertEqual(pin.run("a" * 32, "private", VERSION), "match")
        self.assertEqual(fetch.call_count, 5)

    @patch.object(pin, "fetch")
    def test_privacy_precedes_binding_claim(self, fetch) -> None:
        """Unsafe tracing blocks a passing configuration pin."""

        bad = settings()
        bad["observability"]["traces"]["enabled"] = True
        version = {"id": VERSION, "resources": {"bindings": bindings()}}
        fetch.side_effect = [deployment(), version, bad, settings()]
        self.assertEqual(pin.run("a" * 32, "private", VERSION), "privacy_unverified")


if __name__ == "__main__":
    unittest.main()
