"""Offline contract checks for the narrow staging browser extension; no network."""

import importlib.util
from pathlib import Path
import unittest


FILE = Path(__file__).with_name("staging_billing_e2e.py")
SPEC = importlib.util.spec_from_file_location("staging_billing_e2e", FILE)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class BillingHarnessTests(unittest.TestCase):
    """Reject private/misrouted input before the owned browser can navigate."""

    def test_only_fixed_opaque_staging_authorization_path_is_accepted(self):
        """A URL containing credentials, query capabilities or a foreign host is invalid."""
        good = "https://subscribe-staging.moesegfault.dev/amail/authorize/abcdefghijklmnopqrstuvwxyz012345"
        self.assertEqual(probe.validate_url(good), good)
        for bad in [None, good + "?code=private", good + "#private", good.replace("staging", "production"),
                    good.replace("https://", "http://"), good.replace("https://", "https://user:secret@"),
                    "https://subscribe-staging.moesegfault.dev/amail/authorize/short"]:
            with self.subTest(value=bad), self.assertRaises(probe.BillingProbeError):
                probe.validate_url(bad)

    def test_cli_jsonl_requires_objects_and_bounded_response(self):
        """The two creation projections remain distinct; malformed output is not reflected."""
        self.assertEqual(probe.rows('{"idempotency_key":"fixture"}\n{"state":"pending"}\n'),
                         [{"idempotency_key": "fixture"}, {"state": "pending"}])
        for invalid in ["", "private body", "[]", "null", '"private"', "x" * 65537]:
            with self.assertRaises(probe.BillingProbeError) as error:
                probe.rows(invalid)
            self.assertEqual(str(error.exception), "billing_cli_response_invalid")


if __name__ == "__main__":
    unittest.main()
