"""Guard the direct-forward-only Mail API deployment contract without provider I/O."""

from __future__ import annotations

import pathlib
import tomllib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class DirectForwardApiConfigTests(unittest.TestCase):
    """Keep contact state in Mail D1 and preserve the existing privacy graph."""

    def setUp(self) -> None:
        """Read committed deployment intent, not effective provider settings."""
        self.api = tomllib.loads(
            (ROOT / "crates/mail-worker/wrangler.toml").read_text(encoding="utf-8")
        )
        self.sink = tomllib.loads(
            (ROOT / "workers/trace-sink/wrangler.toml").read_text(encoding="utf-8")
        )

    def test_only_mail_database_is_bound_in_each_realm(self) -> None:
        """A dormant role lease must not become an optional runtime dependency."""
        ids = []
        for realm in (self.api, self.api["env"]["staging"]):
            with self.subTest(worker=realm["name"]):
                self.assertEqual(len(realm["d1_databases"]), 1)
                database = realm["d1_databases"][0]
                self.assertEqual(database["binding"], "MAIL_DB")
                self.assertEqual(database["migrations_dir"], "migrations")
                ids.append(database["database_id"])
        self.assertNotEqual(*ids)

    def test_trace_queue_shape_stays_api_to_private_sink(self) -> None:
        """Source attachment intent does not grant acceptance to a role producer."""
        for api, sink, suffix in (
            (self.api, self.sink, ""),
            (self.api["env"]["staging"], self.sink["env"]["staging"], "-staging"),
        ):
            with self.subTest(worker=api["name"]):
                self.assertEqual(api["queues"], {"producers": [{
                    "binding": "TRACE_EVENTS", "queue": "amail-trace-events" + suffix,
                }]})
                self.assertEqual(sink["queues"], {"consumers": [{
                    "queue": "amail-trace-events" + suffix,
                    "max_batch_size": 10, "max_batch_timeout": 1,
                    "max_retries": 3, "retry_delay": 30, "max_concurrency": 2,
                    "dead_letter_queue": "amail-trace-dlq" + suffix,
                }]})
                self.assertIs(sink["workers_dev"], False)
                self.assertIs(sink["preview_urls"], False)
                for surface in ("routes", "services", "d1_databases", "r2_buckets",
                                "send_email", "triggers", "tail_consumers"):
                    self.assertNotIn(surface, sink)

    def test_no_role_route_or_contact_destination_is_managed_by_api(self) -> None:
        """Wrangler must not replace four independently managed direct forwards."""
        for realm, host in (
            (self.api, "mail.moesegfault.dev"),
            (self.api["env"]["staging"], "mail-staging.moesegfault.dev"),
        ):
            with self.subTest(worker=realm["name"]):
                self.assertEqual(realm["routes"], [{"pattern": host, "custom_domain": True}])
                self.assertNotIn("addresses", realm)
                self.assertNotIn("ROLE_FORWARD_DESTINATION", realm["vars"])
                self.assertIs(realm["observability"]["enabled"], False)
                for section in ("logs", "traces", "issues"):
                    self.assertIs(realm["observability"][section]["enabled"], False)


if __name__ == "__main__":
    unittest.main()
