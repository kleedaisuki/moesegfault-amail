"""Synthetic endpoint and privacy contracts for the role token discriminator."""

from __future__ import annotations

from contextlib import redirect_stdout
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import sys
import unittest
import urllib.error
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import staging_role_token_phase_probe as probe


DEST = "private@example.net"
TOKEN = "secret-never-print"
ACCOUNT = "a" * 32
VERSION = "b5269cce-6384-444e-9cf3-81e360fec6c3"


class Response:
    """Act like a bounded successful Cloudflare JSON response."""

    status = 200

    def __init__(self, result: list[dict], *, page: int = 1):
        """Encode one complete provider inventory page."""

        self.data = BytesIO(json.dumps({
            "success": True,
            "result": result,
            "result_info": {
                "page": page, "per_page": 50, "count": len(result),
                "total_count": len(result), "total_pages": 1,
            },
        }).encode())

    def __enter__(self):
        """Support urllib's response context manager."""

        return self

    def __exit__(self, *_args):
        """Do not suppress exceptions."""

        return False

    def read(self, size: int) -> bytes:
        """Respect the caller's maximum response size."""

        return self.data.read(size)


def role_rules() -> list[dict]:
    """Return exactly four synthetic standard direct forwards."""

    return [{
        "enabled": True, "source": "api",
        "matchers": [{"type": "literal", "field": "to", "value": role}],
        "actions": [{"type": "forward", "value": [DEST]}],
    } for role in probe.forwarding.ROLES]


class RoleTokenPhaseProbeTests(unittest.TestCase):
    """Ensure provider reads cannot become writes, redirects, or private output."""

    def test_exact_200_pages_and_destination_verified(self) -> None:
        """Both endpoint inventories must be complete before claiming a pass."""

        def answer(request, timeout):
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(request.get_header("Authorization"), "Bearer " + TOKEN)
            self.assertEqual(timeout, 25)
            if "/addresses?" in request.full_url:
                return Response([{"email": DEST, "verified": "2026-09-01T00:00:00Z"}])
            self.assertIn("/email/routing/rules?", request.full_url)
            return Response(role_rules())

        env = {"CF_EMAIL_ROUTING_TOKEN": TOKEN, "CLOUDFLARE_ACCOUNT_ID": ACCOUNT,
               "CF_ZONE_ID": probe.ZONE, "ROLE_FORWARD_DESTINATION": DEST,
               "CLOUDFLARE_API_TOKEN": "separate-secret", "AMAIL_STAGING_ROLE_VERSION": VERSION}
        with patch.dict(os.environ, env, clear=True), patch.object(sys, "argv", ["probe", probe.CONFIRM, probe.RUN]), \
                patch.object(probe._NO_REDIRECT, "open", side_effect=answer) as opened, \
                patch.object(probe, "version_state", return_value="match"), \
                redirect_stdout(StringIO()) as output:
            self.assertEqual(probe.main(), 0)
        self.assertEqual(opened.call_count, 2)
        rendered = output.getvalue()
        self.assertIn("role_token_probe=read_only_pass", rendered)
        self.assertIn("role_token_destination=verified", rendered)
        self.assertIn("role_token_disposable_route=absent", rendered)
        for secret in (DEST, TOKEN, ACCOUNT, probe.RUN):
            self.assertNotIn(secret, rendered)

    def test_403_on_addresses_still_checks_rules(self) -> None:
        """Distinguish Addresses permission from Rules permission independently."""

        failure = urllib.error.HTTPError("https://api.cloudflare.com/", 403, "Forbidden", {}, BytesIO(b"private"))
        with patch.object(probe._NO_REDIRECT, "open", side_effect=[failure, Response(role_rules())]) as opened:
            addresses, status_a = probe.inventory(probe.Client(TOKEN), f"/accounts/{ACCOUNT}/email/routing/addresses")
            rules, status_r = probe.inventory(probe.Client(TOKEN), f"/zones/{probe.ZONE}/email/routing/rules")
        self.assertEqual((addresses, status_a), ([], "forbidden"))
        self.assertEqual(status_r, "accessible")
        self.assertEqual(probe.rule_state(rules, DEST), "four_direct")
        self.assertEqual(opened.call_count, 2)

    def test_403_on_rules_is_independent(self) -> None:
        """A readable destination does not imply Rules permission."""

        failure = urllib.error.HTTPError("https://api.cloudflare.com/", 403, "Forbidden", {}, BytesIO(b"private"))
        with patch.object(probe._NO_REDIRECT, "open", side_effect=[
            Response([{"email": DEST, "verified": "now"}]), failure,
        ]):
            addresses, status_a = probe.inventory(probe.Client(TOKEN), f"/accounts/{ACCOUNT}/email/routing/addresses")
            rules, status_r = probe.inventory(probe.Client(TOKEN), f"/zones/{probe.ZONE}/email/routing/rules")
        self.assertEqual(status_a, "accessible")
        self.assertEqual(probe.destination_state(addresses, DEST), "verified")
        self.assertEqual((rules, status_r), ([], "forbidden"))

    def test_redirect_is_rejected_without_following_bearer(self) -> None:
        """A provider 302 must never reissue an authenticated request."""

        request = probe.urllib.request.Request(probe.forwarding.API + "/test")
        self.assertIsNone(probe.RejectRedirect().redirect_request(
            request, None, 302, "Found", {}, "https://other.example/"))
        redirect = urllib.error.HTTPError(request.full_url, 302, "Found",
                                           {"Location": "https://other.example/"}, BytesIO(b"private"))
        with patch.object(probe._NO_REDIRECT, "open", side_effect=redirect) as opened:
            _items, status = probe.inventory(probe.Client(TOKEN), f"/accounts/{ACCOUNT}/email/routing/addresses")
        self.assertEqual(status, "redirect")
        self.assertEqual(opened.call_count, 1)

    def test_missing_pending_duplicate_and_mismatch(self) -> None:
        """Neither incomplete destination verification nor rule drift can pass."""

        self.assertEqual(probe.destination_state([], DEST), "missing")
        self.assertEqual(probe.destination_state([{"email": DEST, "verified": None}], DEST), "pending")
        self.assertEqual(probe.destination_state([
            {"email": DEST, "verified": "now"}, {"email": DEST, "verified": "now"},
        ], DEST), "duplicate")
        self.assertEqual(probe.rule_state(role_rules()[:-1], DEST), "incomplete")
        wrong = role_rules()
        wrong[0]["actions"] = [{"type": "forward", "value": ["wrong@example.net"]}]
        self.assertEqual(probe.rule_state(wrong, DEST), "contract_mismatch")
        self.assertEqual(probe.route_state(role_rules()), "absent")
        self.assertEqual(probe.route_state(role_rules() + [{
            "matchers": [{"type": "literal", "field": "to", "value": probe.staging_route.ALIAS}],
        }]), "present")

    def test_serving_version_must_be_current_and_single(self) -> None:
        """A changed or unreadable serving deployment cannot certify the probe."""

        with patch.object(probe.hosted, "active_version", return_value=(VERSION, None)):
            self.assertEqual(probe.version_state(ACCOUNT, "api-secret", VERSION), "match")
            self.assertEqual(probe.version_state(ACCOUNT, "api-secret", "00000000-0000-4000-8000-000000000000"), "drift")
        with patch.object(probe.hosted, "active_version", side_effect=RuntimeError("private")):
            self.assertEqual(probe.version_state(ACCOUNT, "api-secret", VERSION), "unavailable")

    def test_incomplete_pagination_fails_closed(self) -> None:
        """A truncated provider page is not a missing destination."""

        response = Response([{"email": DEST, "verified": "now"}])
        payload = json.loads(response.data.getvalue())
        payload["result_info"]["total_count"] = 2
        response.data = BytesIO(json.dumps(payload).encode())
        with patch.object(probe._NO_REDIRECT, "open", return_value=response):
            items, status = probe.inventory(probe.Client(TOKEN), f"/accounts/{ACCOUNT}/email/routing/addresses")
        self.assertEqual((items, status), ([], "invalid_response"))

    def test_workflow_secret_scope_and_exact_coordinates(self) -> None:
        """Only a confirmed manual staging job receives provider secrets."""

        workflow = (HERE.parents[1] / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job = workflow.split("  staging-role-token-phase-probe:\n", 1)[1].split("\n  staging-trace-canary:", 1)[0]
        self.assertIn("inputs.target == 'staging-role-token-phase-probe'", job)
        self.assertIn("READ_FIRST_ROLE_TOKEN_PERMISSIONS", job)
        self.assertIn(probe.RUN, job)
        self.assertNotIn("\n    env:", job)
        self.assertNotIn("secrets.", job.split("      - name: Read bounded provider inventories", 1)[0])
        self.assertEqual(job.count("secrets.CF_EMAIL_ROUTING_TOKEN"), 1)
        self.assertEqual(job.count("secrets.ROLE_FORWARD_DESTINATION"), 1)
        self.assertEqual(job.count("secrets.CLOUDFLARE_API_TOKEN"), 1)
        self.assertIn("AMAIL_STAGING_ROLE_VERSION: ${{ inputs.role_version }}", job)
        self.assertNotIn("wrangler", job.lower())


if __name__ == "__main__":
    unittest.main()
