"""Hosted, provider-free checks for reserved canary ingress lifecycle contracts.

Expected behavior comes from docs/native-route-dns-lifecycle.md: absent-only
creation, exact ownership, durable intent before writes, and no mutation replay
following an unknown result. These tests do not contact Cloudflare.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from urllib.error import HTTPError
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import native_route_lifecycle as lifecycle

ACCOUNT = "a" * 32
NONCE = "b" * 32
VERSION = "12345678-1234-4234-8234-123456789abc"


def missing():
    """Return an exact synthetic 404 without exposing provider prose."""
    return HTTPError("https://synthetic.invalid", 404, "missing", {}, None)


class FakeProvider:
    """Stateful independent API fixture; journal captures reads and side effects."""

    def __init__(self):
        self.account = ACCOUNT
        self.calls = []
        self.dns = []
        self.routes = []
        self.domains = []
        self.live = False
        self.zone = {"id": lifecycle.ZONE_ID, "name": "moesegfault.dev",
                     "account": {"id": ACCOUNT}, "status": "active",
                     "paused": False, "type": "full"}
        self.ssl = {"enabled": True}
        now = datetime.now(timezone.utc)
        self.packs = [{"id": "existing-pack", "type": "universal", "status": "active",
                       "hosts": ["moesegfault.dev", "*.moesegfault.dev"],
                       "certificates": [{"status": "active", "hosts": ["*.moesegfault.dev"],
                         "expires_on": (now + timedelta(days=30)).isoformat(),
                         "uploaded_on": (now - timedelta(days=1)).isoformat()}]}]
        self.overrides = {}
        self.fail_write = None
        self.bad_ack = False
        self.deny_post = False
        self.persisted = []

    def script(self, name, suffix="settings"):
        """Match the fixed account/script transport contract, not arbitrary names."""
        return f"/accounts/{ACCOUNT}/workers/scripts/{name}" + ("/" + suffix if suffix else "")

    def envelope(self, values, suffix):
        """A complete single-page API envelope with explicit count evidence."""
        page = int(parse_qs(urlsplit(suffix).query).get("page", [1])[0])
        return {"success": True, "result": deepcopy(values), "result_info": {
            "page": page, "per_page": 100, "count": len(values),
            "total_count": len(values), "total_pages": 1}}

    def request(self, method, suffix, data=None, *, envelope=False):
        """Implement fixed API families and optionally commit then lose a write ACK."""
        self.calls.append((method, suffix, deepcopy(data)))
        path = urlsplit(suffix).path
        if (method, path) in self.overrides:
            value = self.overrides[(method, path)]
            if isinstance(value, Exception):
                raise value
            return deepcopy(value)
        zone = "/zones/" + lifecycle.ZONE_ID
        if method == "GET":
            if path == zone:
                return deepcopy(self.zone)
            if path == zone + "/ssl/universal/settings":
                return deepcopy(self.ssl)
            if path == zone + "/ssl/certificate_packs":
                return self.envelope(self.packs, suffix) if envelope else deepcopy(self.packs)
            if path == zone + "/dns_records":
                return self.envelope(self.dns, suffix) if envelope else deepcopy(self.dns)
            if path == zone + "/workers/routes":
                return deepcopy(self.routes)
            if path == f"/accounts/{ACCOUNT}/workers/domains":
                return self.envelope(self.domains, suffix) if envelope else deepcopy(self.domains)
            for family, values in (("dns_records", self.dns), ("workers/routes", self.routes)):
                prefix = zone + "/" + family + "/"
                if path.startswith(prefix):
                    matches = [x for x in values if x["id"] == unquote(path[len(prefix):])]
                    if not matches:
                        raise missing()
                    return deepcopy(matches[0])
            for name, role in ((lifecycle.PROBE, "probe"), (lifecycle.CALLER, "caller")):
                if path == self.script(name):
                    if not self.live:
                        raise missing()
                    return {"bindings": [{"type": "plain_text", "name": "PROBE_ID", "text": NONCE},
                                         {"type": "plain_text", "name": "CANARY_ROLE", "text": role}]}
                if path == self.script(name, "deployments"):
                    return {"deployments": [{"versions": [{"version_id": VERSION, "percentage": 100}]}]}
        if method == "POST":
            family, values = ("dns_records", self.dns) if path.endswith("/dns_records") else ("workers/routes", self.routes)
            assert path == zone + "/" + family, "Unexpected write coordinate"
            phase_key = "dns" if family == "dns_records" else "route"
            assert self.persisted[-1]["ingress"][phase_key]["phase"] == "attempted", "Write before durable intent"
            if self.deny_post:
                raise HTTPError("https://synthetic.invalid", 403, "denied", {}, None)
            item = {"id": "opaque-owned-" + str(len(values)), **deepcopy(data)}
            values.append(item)
            if self.fail_write == method:
                raise TimeoutError("synthetic lost acknowledgement")
            return {} if self.bad_ack else deepcopy(item)
        if method == "DELETE":
            for family, values in (("dns_records", self.dns), ("workers/routes", self.routes)):
                prefix = zone + "/" + family + "/"
                if path.startswith(prefix):
                    target = unquote(path[len(prefix):])
                    values[:] = [x for x in values if x["id"] != target]
                    if self.fail_write == method:
                        raise TimeoutError("synthetic lost acknowledgement")
                    return {"id": target}
        raise AssertionError("Unexpected API family: " + method + " " + path)

    def persist(self, receipt):
        """Snapshot durable state rather than retaining the mutated object alias."""
        self.persisted.append(deepcopy(receipt))


class NativeRoutePreflightTests(unittest.TestCase):
    """Read-only admission refuses ambiguous absence and foreign infrastructure."""

    def test_complete_preflight_is_read_only_and_fixed(self):
        provider = FakeProvider()
        result = lifecycle.preflight(provider)
        self.assertEqual(result["hostname"], "amail-native-trace-canary.moesegfault.dev")
        self.assertTrue(result["inventory_absent"])
        self.assertTrue(result["scripts_absent"])
        self.assertTrue(all(call[0] == "GET" for call in provider.calls))

    def test_zone_identity_setup_and_ssl_fail_closed(self):
        variants = [{"status": "pending"}, {"paused": True}, {"type": "partial"},
                    {"account": {"id": "c" * 32}}, {"name": "other.invalid"}]
        for fields in variants:
            with self.subTest(fields=fields):
                provider = FakeProvider()
                provider.zone.update(fields)
                with self.assertRaises(ValueError):
                    lifecycle.preflight(provider)
        for mutate in (lambda p: p.ssl.update(enabled=False),
                       lambda p: p.packs[0].update(status="pending_validation"),
                       lambda p: p.packs[0]["certificates"][0].update(hosts=["elsewhere.invalid"]),
                       lambda p: p.packs[0]["certificates"][0].update(expires_on="2000-01-01T00:00:00Z")):
            provider = FakeProvider()
            mutate(provider)
            with self.assertRaises(ValueError):
                lifecycle.preflight(provider)

    def test_any_dns_type_at_reserved_host_refuses(self):
        for kind in ("A", "AAAA", "TXT", "MX", "CNAME"):
            provider = FakeProvider()
            provider.dns = [{"id": "foreign", "type": kind, "name": lifecycle.HOST, "content": "foreign"}]
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                lifecycle.preflight(provider)
            self.assertTrue(all(call[0] == "GET" for call in provider.calls))

    def test_route_overlap_and_unknown_pattern_refuse(self):
        for pattern in ("*.moesegfault.dev/*", lifecycle.HOST + "/private/*",
                        "https://" + lifecycle.HOST + "/*", "https://[unknown]/*"):
            provider = FakeProvider()
            provider.routes = [{"id": "foreign", "pattern": pattern, "script": "foreign"}]
            with self.subTest(pattern=pattern), self.assertRaises(ValueError):
                lifecycle.preflight(provider)

    def test_failed_script_read_is_not_absence(self):
        provider = FakeProvider()
        provider.overrides[("GET", provider.script(lifecycle.PROBE))] = HTTPError(
            "https://synthetic.invalid", 403, "refused", {}, None)
        with self.assertRaises(HTTPError):
            lifecycle.preflight(provider)
        self.assertTrue(all(call[0] == "GET" for call in provider.calls))

    def test_incomplete_inventory_is_not_absence(self):
        for malformed in ({"success": True, "result": []},
                          {"success": True, "result": [], "result_info": {"page": 1, "per_page": 100,
                            "count": 0, "total_count": 1, "total_pages": 1}}):
            provider = FakeProvider()
            provider.overrides[("GET", "/zones/" + lifecycle.ZONE_ID + "/dns_records")] = malformed
            with self.subTest(malformed=malformed), self.assertRaises(ValueError):
                lifecycle.preflight(provider)


class NativeRouteLifecycleTests(unittest.TestCase):
    """Mutation receipts must survive ambiguity without adopting foreign state."""

    def prepared(self):
        """Capture absent evidence before enabling the owned synthetic pair."""
        provider = FakeProvider()
        proof = lifecycle.preflight(provider)
        receipt = {"probe_id": NONCE, "source_sha": "d" * 40, "run_id": "123",
                   "versions": {lifecycle.PROBE: VERSION, lifecycle.CALLER: VERSION},
                   "ingress": {"schema": "native-route-ingress/v1", "zone_id": lifecycle.ZONE_ID,
                               "hostname": lifecycle.HOST, "preflight": proof}}
        return provider, receipt

    def owned(self):
        """Provision through the public contract, not direct fixture state adoption."""
        provider, receipt = self.prepared()
        lifecycle.create_dns(provider, receipt, provider.persist)
        provider.live = True
        lifecycle.create_route(provider, receipt, provider.persist)
        return provider, receipt

    def mutations(self, provider):
        """Return only actual mutation requests for causal order assertions."""
        return [x for x in provider.calls if x[0] != "GET"]

    def test_exact_bodies_and_intents_precede_mutations(self):
        provider, receipt = self.owned()
        writes = self.mutations(provider)
        self.assertEqual([x[0] for x in writes], ["POST", "POST"])
        self.assertEqual(writes[0][2], {"type": "AAAA", "name": lifecycle.HOST,
                                      "content": "100::", "proxied": True, "ttl": 1,
                                      "comment": "amail-native-tracing/" + NONCE})
        self.assertEqual(writes[1][2], {"pattern": "https://" + lifecycle.HOST + "/*",
                                      "script": lifecycle.CALLER})
        for family in ("dns", "route"):
            self.assertTrue(any(x["ingress"].get(family, {}).get("phase") == "attempted"
                                for x in provider.persisted))
            self.assertEqual(receipt["ingress"][family]["phase"], "verified")
        lifecycle.assert_ingress(provider, receipt)

    def test_lost_create_ack_never_retries_or_auto_adopts(self):
        provider, receipt = self.prepared()
        provider.fail_write = "POST"
        with self.assertRaises(TimeoutError):
            lifecycle.create_dns(provider, receipt, provider.persist)
        self.assertEqual(len(self.mutations(provider)), 1)
        self.assertEqual(receipt["ingress"]["dns"]["phase"], "unknown")
        self.assertEqual(len(provider.dns), 1)
        with self.assertRaises(ValueError):
            lifecycle.create_dns(provider, receipt, provider.persist)
        self.assertEqual(len(self.mutations(provider)), 1)

    def test_denied_write_does_not_promote_read_permission_or_retry(self):
        provider, receipt = self.prepared()
        provider.deny_post = True
        with self.assertRaises(HTTPError):
            lifecycle.create_dns(provider, receipt, provider.persist)
        self.assertEqual(len(self.mutations(provider)), 1)
        self.assertFalse(provider.dns)
        with self.assertRaises(ValueError):
            lifecycle.create_dns(provider, receipt, provider.persist)
        self.assertEqual(len(self.mutations(provider)), 1)

    def test_malformed_create_ack_is_unknown_not_verified(self):
        provider, receipt = self.prepared()
        provider.bad_ack = True
        with self.assertRaises(ValueError):
            lifecycle.create_dns(provider, receipt, provider.persist)
        self.assertEqual(receipt["ingress"]["dns"]["phase"], "unknown")
        self.assertEqual(len(self.mutations(provider)), 1)
        self.assertTrue(provider.dns)

    def test_unknown_dns_creation_cleanup_requires_exact_unique_nonce(self):
        provider, receipt = self.prepared()
        provider.fail_write = "POST"
        with self.assertRaises(TimeoutError):
            lifecycle.create_dns(provider, receipt, provider.persist)
        provider.fail_write = None
        provider.dns[0]["comment"] = "foreign"
        with self.assertRaises(ValueError):
            lifecycle.cleanup_ingress(provider, receipt, provider.persist)
        self.assertFalse(any(x[0] == "DELETE" for x in provider.calls))
        provider.dns[0]["comment"] = "amail-native-tracing/" + NONCE
        lifecycle.cleanup_ingress(provider, receipt, provider.persist)
        self.assertFalse(provider.dns)
        self.assertEqual(len([x for x in provider.calls if x[0] == "POST"]), 1)

    def test_equivalent_ipv6_and_opaque_ids_are_deliberate(self):
        provider, receipt = self.owned()
        provider.dns[0]["content"] = "0100:0000:0000:0000:0000:0000:0000:0000"
        provider.dns[0]["id"] = "opaque/id+value"
        receipt["ingress"]["dns"]["id"] = "opaque/id+value"
        lifecycle.assert_ingress(provider, receipt)
        lifecycle.cleanup_ingress(provider, receipt, provider.persist)
        deletes = [x[1] for x in provider.calls if x[0] == "DELETE"]
        self.assertTrue(any(x.endswith("opaque%2Fid%2Bvalue") for x in deletes))

    def test_dns_exact_nonce_proxy_and_content_required(self):
        for fields in ({"comment": "foreign"}, {"proxied": False}, {"content": "2001:db8::1"},
                       {"type": "A"}, {"name": "elsewhere.moesegfault.dev"}):
            provider, receipt = self.owned()
            provider.dns[0].update(fields)
            before = len(self.mutations(provider))
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                lifecycle.assert_ingress(provider, receipt)
            with self.assertRaises(ValueError):
                lifecycle.cleanup_ingress(provider, receipt, provider.persist)
            self.assertFalse(any(x[0] == "DELETE" and "/dns_records/" in x[1]
                                 for x in self.mutations(provider)[before:]))

    def test_route_foreign_target_pattern_or_pair_version_refuses_delete(self):
        for fields in ({"script": "foreign"}, {"pattern": "https://elsewhere.invalid/*"}):
            provider, receipt = self.owned()
            provider.routes[0].update(fields)
            before = len(self.mutations(provider))
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                lifecycle.cleanup_ingress(provider, receipt, provider.persist)
            self.assertEqual(len(self.mutations(provider)), before)
        provider, receipt = self.owned()
        provider.overrides[("GET", provider.script(lifecycle.CALLER, "deployments"))] = {"deployments": [
            {"versions": [{"version_id": "87654321-4321-4321-8321-cba987654321", "percentage": 100}]}]}
        before = len(self.mutations(provider))
        with self.assertRaises(ValueError):
            lifecycle.cleanup_ingress(provider, receipt, provider.persist)
        self.assertEqual(len(self.mutations(provider)), before)

    def test_cleanup_route_then_dns_and_exact_absence(self):
        provider, receipt = self.owned()
        lifecycle.cleanup_ingress(provider, receipt, provider.persist)
        deletes = [x for x in self.mutations(provider) if x[0] == "DELETE"]
        self.assertEqual(len(deletes), 2)
        self.assertIn("/workers/routes/", deletes[0][1])
        self.assertIn("/dns_records/", deletes[1][1])
        self.assertEqual(provider.routes, [])
        self.assertEqual(provider.dns, [])
        self.assertEqual(receipt["ingress"]["route"]["phase"], "deleted")
        self.assertEqual(receipt["ingress"]["dns"]["phase"], "deleted")

    def test_unknown_delete_stops_dns_and_cannot_replay(self):
        provider, receipt = self.owned()
        provider.fail_write = "DELETE"
        with self.assertRaises(TimeoutError):
            lifecycle.cleanup_ingress(provider, receipt, provider.persist)
        deletes = [x for x in self.mutations(provider) if x[0] == "DELETE"]
        self.assertEqual(len(deletes), 1)
        self.assertTrue(provider.dns)
        self.assertEqual(receipt["ingress"]["route"]["phase"], "delete_unknown")
        try:
            lifecycle.cleanup_ingress(provider, receipt, provider.persist)
        except ValueError:
            pass
        self.assertEqual(len([x for x in self.mutations(provider)
                              if x[0] == "DELETE" and "/workers/routes/" in x[1]]), 1)


if __name__ == "__main__":
    unittest.main()
