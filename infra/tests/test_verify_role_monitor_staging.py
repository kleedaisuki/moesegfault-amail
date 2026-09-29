"""Check that the live role-monitor auditor rejects privacy regressions."""

from __future__ import annotations

import importlib.util
from io import BytesIO
from pathlib import Path
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch


PATH = Path(__file__).resolve().parents[1] / "deploy/verify_role_monitor_staging.py"
SPEC = importlib.util.spec_from_file_location("verify_role_monitor_staging", PATH)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class RoleMonitorLiveAuditTests(unittest.TestCase):
    """Reject leaked HTTP surfaces, unsafe observability and cross-realm D1."""

    def bindings(self) -> dict:
        """Return a representative sanitized provider shape, not real secrets."""

        return {"bindings": [
            {"type": "d1", "name": "ROLE_MONITOR", "database_id": audit.DATABASE},
            {"type": "send_email", "name": "ROLE_ALERT"},
            {"type": "plain_text", "name": "ROLE_REALM", "text": "staging"},
            {"type": "plain_text", "name": "CF_ZONE_ID", "text": audit.ZONE},
            {"type": "secret_text", "name": "ROLE_FORWARD_DESTINATION"},
        ]}

    def test_provider_redirect_does_not_forward_deployment_bearer(self) -> None:
        """A 302 is a fixed failed read, never a second-origin credential hop."""

        request = urllib.request.Request(audit.API + "/test")
        self.assertIsNone(audit.RejectRedirect().redirect_request(
            request, None, 302, "Found", {}, "https://other.example/"))
        redirect = urllib.error.HTTPError(request.full_url, 302, "Found",
                                            {"Location": "https://other.example/"}, BytesIO(b"private"))
        with patch.object(audit._NO_REDIRECT, "open", side_effect=redirect) as opener:
            with self.assertRaisesRegex(RuntimeError, "^Cloudflare API read failed: HTTP 302$"):
                audit.api_get("/test", "secret")
        self.assertEqual(opener.call_count, 1)

    def test_bindings_reject_production_database(self) -> None:
        """A correctly named binding must still target the isolated staging ID."""

        settings = self.bindings()
        audit.inspect_bindings(settings)
        settings["bindings"][0]["database_id"] = "production-db-id"
        with self.assertRaisesRegex(RuntimeError, "D1 database differs"):
            audit.inspect_bindings(settings)

    def test_bindings_reject_extra_storage_capability(self) -> None:
        """An unrelated storage binding broadens the private Worker's reach."""

        settings = self.bindings()
        settings["bindings"].append({"type": "r2_bucket", "name": "RAW_MAIL"})
        with self.assertRaisesRegex(RuntimeError, "unexpected capability binding"):
            audit.inspect_bindings(settings)

    def test_effective_observability_rejects_automatic_capture(self) -> None:
        """Either deployment-level setting can expose untrusted email envelopes."""

        obs = {"logs": {"enabled": True, "invocation_logs": False}, "traces": {"enabled": False}}
        audit.inspect_observability({"observability": obs}, {})
        for key, value in (("traces", True), ("invocation_logs", True)):
            changed = {"logs": dict(obs["logs"]), "traces": dict(obs["traces"])}
            if key == "traces":
                changed["traces"]["enabled"] = value
            else:
                changed["logs"][key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                audit.inspect_observability({"observability": obs}, {"observability": changed})

    def test_http_surface_rejects_each_exposure(self) -> None:
        """An Email/Cron-only Worker must be inaccessible through HTTP."""

        private = {"enabled": False, "previews_enabled": False}
        audit.inspect_surfaces(private, [], [])
        for subdomain, routes, domains in (
            ({"enabled": True, "previews_enabled": False}, [], []),
            ({"enabled": False, "previews_enabled": True}, [], []),
            (private, [{"script": audit.WORKER}], []),
            (private, [], [{"service": audit.WORKER}]),
        ):
            with self.subTest(subdomain=subdomain, routes=routes, domains=domains), self.assertRaises(RuntimeError):
                audit.inspect_surfaces(subdomain, routes, domains)


if __name__ == "__main__":
    unittest.main()
