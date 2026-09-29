"""Test the non-mutating routing Write policy diagnostic without Cloudflare calls."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import pathlib
import sys
import unittest
from unittest.mock import patch


PROVIDER = pathlib.Path(__file__).resolve().parents[1] / "provider"
sys.path.insert(0, str(PROVIDER))
SPEC = importlib.util.spec_from_file_location("probe_routing_write", PROVIDER / "probe_routing_write.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

ENV = {
    "CF_ZONE_ID": "a" * 32,
    "CLOUDFLARE_ACCOUNT_ID": "b" * 32,
    "CF_EMAIL_ROUTING_TOKEN": "private-routing-secret",
    "CLOUDFLARE_API_TOKEN": "private-reader-secret",
}
TOKEN_ID = "c" * 32


def policy(effect: str, resources: dict, name: str = "Email Routing Rules Write") -> dict:
    """Build one minimal Cloudflare token policy fixture."""

    return {"effect": effect, "resources": resources, "permission_groups": [{"name": name}]}


class RoutingWriteProbeTest(unittest.TestCase):
    """Require GET-only calls, exact-zone matching, and redacted diagnostics."""

    def _run(self, policies: list[dict]) -> tuple[int, str, list]:
        """Run the script against mocked user-token verification and details."""

        replies = [
            (200, {"success": True, "result": {"id": TOKEN_ID, "status": "active"}}),
            (200, {"success": True, "result": {"id": TOKEN_ID, "status": "active", "policies": policies}}),
        ]
        output = io.StringIO()
        with patch.dict("os.environ", ENV), patch.object(MODULE, "_request", side_effect=replies) as request, contextlib.redirect_stdout(output):
            code = MODULE.main()
        return code, output.getvalue(), request.call_args_list

    def test_exact_zone_grant_is_configured_only(self) -> None:
        """A policy grant is not misrepresented as effective POST authorization."""

        code, output, calls = self._run([policy("allow", {f"com.cloudflare.api.account.zone.{ENV['CF_ZONE_ID']}": "*"})])
        self.assertEqual(code, 0)
        self.assertEqual(output, "routing_write_check=configured_grant scope=configured_policy_only\n")
        self.assertEqual(calls[0].args, ("/user/tokens/verify", ENV["CF_EMAIL_ROUTING_TOKEN"]))
        self.assertEqual(calls[1].args, (f"/user/tokens/{TOKEN_ID}", ENV["CLOUDFLARE_API_TOKEN"]))

    def test_other_zone_does_not_grant_target(self) -> None:
        """A grant for another zone is not sufficient for the target zone."""

        code, output, _ = self._run([policy("allow", {"com.cloudflare.api.account.zone." + "d" * 32: "*"})])
        self.assertEqual(code, 0)
        self.assertIn("routing_write_check=no_grant", output)

    def test_explicit_deny_overrides_wildcard_allow(self) -> None:
        """Cloudflare's explicit-deny precedence is reflected in the result."""

        policies = [
            policy("allow", {"com.cloudflare.api.account.zone.*": "*"}),
            policy("deny", {f"com.cloudflare.api.account.zone.{ENV['CF_ZONE_ID']}": "*"}),
        ]
        code, output, _ = self._run(policies)
        self.assertEqual(code, 0)
        self.assertIn("routing_write_check=explicit_deny", output)

    def test_nested_account_scope(self) -> None:
        """Recognize Cloudflare's documented all-zones-in-one-account form."""

        resources = {f"com.cloudflare.api.account.{ENV['CLOUDFLARE_ACCOUNT_ID']}": {"com.cloudflare.api.account.zone.*": "*"}}
        code, output, _ = self._run([policy("allow", resources)])
        self.assertEqual(code, 0)
        self.assertIn("routing_write_check=configured_grant", output)

    def test_account_owned_token_uses_account_details(self) -> None:
        """Fallback to account verification and use its matching detail endpoint."""

        replies = [
            (403, {"errors": [{"code": 10000}]}),
            (200, {"success": True, "result": {"id": TOKEN_ID, "status": "active"}}),
            (200, {"success": True, "result": {"id": TOKEN_ID, "status": "active", "policies": [policy("allow", {"com.cloudflare.api.account.zone.*": "*"})]}}),
        ]
        output = io.StringIO()
        with patch.dict("os.environ", ENV), patch.object(MODULE, "_request", side_effect=replies) as request, contextlib.redirect_stdout(output):
            self.assertEqual(MODULE.main(), 0)
        self.assertEqual(request.call_args_list[1].args, (f"/accounts/{ENV['CLOUDFLARE_ACCOUNT_ID']}/tokens/verify", ENV["CF_EMAIL_ROUTING_TOKEN"]))
        self.assertEqual(request.call_args_list[2].args, (f"/accounts/{ENV['CLOUDFLARE_ACCOUNT_ID']}/tokens/{TOKEN_ID}", ENV["CLOUDFLARE_API_TOKEN"]))
        self.assertIn("routing_write_check=configured_grant", output.getvalue())

    def test_unrecognized_policy_is_inconclusive(self) -> None:
        """Do not promote incomplete provider metadata to a no-grant claim."""

        code, output, _ = self._run([{"effect": "allow", "permission_groups": [{"id": "private"}], "resources": {}}])
        self.assertEqual(code, 1)
        self.assertIn("routing_write_check=unknown", output)

    def test_denied_details_never_leak_response(self) -> None:
        """Expose only bounded provider status and numeric code on read denial."""

        replies = [
            (200, {"success": True, "result": {"id": TOKEN_ID, "status": "active"}}),
            (403, {"errors": [{"code": 10000, "message": "private-address@example.com private-reader-secret"}]}),
        ]
        output = io.StringIO()
        with patch.dict("os.environ", ENV), patch.object(MODULE, "_request", side_effect=replies), contextlib.redirect_stdout(output):
            self.assertEqual(MODULE.main(), 1)
        self.assertEqual(output.getvalue(), "routing_write_check=unavailable detail_http=403 codes=10000\n")


if __name__ == "__main__":
    unittest.main()
