"""Scoped temporary-domain provisioning contracts; no provider calls or secrets."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
from typing import Any
import unittest
import urllib.parse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/provider"))
import ensure_tmpaddr_staging as provision


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self.records: list[dict[str, Any]] = []
        self.domain: dict[str, Any] | None = None
        self.required: list[dict[str, Any]] = [
            {"name": "cf-bounce." + provision.DOMAIN, "type": "MX", "priority": 10, "content": "a.mx.cloudflare.net"},
            {"name": "cf-bounce." + provision.DOMAIN, "type": "MX", "priority": 20, "content": "b.mx.cloudflare.net"},
            {"name": "selector._domainkey." + provision.DOMAIN, "type": "TXT", "content": "v=DKIM1; p=synthetic"},
        ]
        self.reject: str | None = None

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((method, path, copy.deepcopy(body)))
        if self.reject == path:
            raise provision.ProvisionError("mutation_unknown_inspect_before_retry")
        if "/dns_records?" in path:
            name = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)["name"][0]
            result = [row for row in self.records if row["name"] == name]
            return {"result": copy.deepcopy(result), "result_info": {"page": 1, "count": len(result), "total_count": len(result)}}
        if method == "POST" and path.endswith("/dns_records"):
            assert body is not None
            self.records.append(body)
            return {"result": copy.deepcopy(body)}
        if method == "POST" and path.endswith("/email/routing/dns"):
            assert body == {"name": provision.DOMAIN}
            self.records.extend([
                {"name": provision.DOMAIN, "type": "MX", "content": "route1.mx.cloudflare.net", "priority": 10},
                {"name": provision.DOMAIN, "type": "TXT", "content": "v=spf1 include:_spf.mx.cloudflare.net ~all"},
            ])
            return {"result": {"name": provision.DOMAIN, "enabled": True}}
        if "/email/sending/subdomains?" in path:
            return {"result": [copy.deepcopy(self.domain)] if self.domain else []}
        if method == "POST" and path.endswith("/email/sending/subdomains"):
            self.domain = {"name": provision.DOMAIN, "enabled": True, "tag": "a" * 32, "preview_enabled": True, "drop_suppressed_recipients": False}
            return {"result": copy.deepcopy(self.domain)}
        if method == "PATCH":
            assert self.domain is not None and body is not None
            self.domain.update(body)
            return {"result": copy.deepcopy(self.domain)}
        if path.endswith("/dns"):
            return {"result": copy.deepcopy(self.required)}
        return {"result": copy.deepcopy(self.domain)}


class TemporaryDomainTests(unittest.TestCase):
    def test_fresh_domain_and_repeat_are_scoped_and_idempotent(self) -> None:
        provider = FakeProvider()
        provision.ensure_routing(provider, provider, True)
        provision.ensure_sending(provider, True)
        writes = [call for call in provider.calls if call[0] != "GET"]
        self.assertEqual(6, len(writes))
        self.assertTrue(all(provision.DOMAIN in str(body) or "/" + "a" * 32 in path for _, path, body in writes))
        provider.calls.clear()
        provision.ensure_routing(provider, provider, True)
        provision.ensure_sending(provider, True)
        self.assertTrue(all(method == "GET" for method, _, _ in provider.calls))

    def test_read_only_missing_does_not_mutate(self) -> None:
        provider = FakeProvider()
        with self.assertRaisesRegex(provision.ProvisionError, "routing_onboarding_required"):
            provision.ensure_routing(provider, provider, False)
        self.assertTrue(all(method == "GET" for method, _, _ in provider.calls))

    def test_existing_foreign_mx_is_not_replaced(self) -> None:
        provider = FakeProvider()
        provider.records = [{"name": provision.DOMAIN, "type": "MX", "content": "foreign.example.invalid", "priority": 10}]
        with self.assertRaisesRegex(provision.ProvisionError, "routing_existing_mx_conflict"):
            provision.ensure_routing(provider, provider, True)
        self.assertTrue(all(method == "GET" for method, _, _ in provider.calls))

    def test_provider_cannot_request_production_dns(self) -> None:
        provider = FakeProvider()
        provider.required.append({"name": "tmpaddr.moesegfault.dev", "type": "TXT", "content": "out of scope"})
        with self.assertRaisesRegex(provision.ProvisionError, "dns_outside_staging"):
            provision.ensure_sending(provider, True)
        self.assertFalse(any(path.endswith("/dns_records") for _, path, _ in provider.calls))

    def test_ambiguous_create_never_retries(self) -> None:
        provider = FakeProvider()
        provider.reject = provision.PREFIX + "/email/sending/subdomains"
        with self.assertRaisesRegex(provision.ProvisionError, "mutation_unknown"):
            provision.ensure_sending(provider, True)
        self.assertEqual(1, sum(method == "POST" for method, _, _ in provider.calls))

    def test_staging_authority_is_exact(self) -> None:
        environment = {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/codex/v0.3.0-multitenant", "AMAIL_STAGING_CONFIRM": "RUN_STAGING_V030", "AMAIL_STAGING_ENVIRONMENT": "staging", "GITHUB_RUN_ATTEMPT": "1"}
        provision.authorize_apply(environment)
        for key in environment:
            with self.subTest(key=key), self.assertRaisesRegex(provision.ProvisionError, "staging_writer_required"):
                provision.authorize_apply({**environment, key: "wrong"})

    def test_existing_dkim_is_never_replaced(self) -> None:
        provider = FakeProvider()
        provider.required = provider.required[2:]
        provider.records = [{**provider.required[0], "content": "old-key"}]
        with self.assertRaisesRegex(provision.ProvisionError, "sending_existing_dns_conflict"):
            provision.ensure_sending(provider, True)
        self.assertFalse(any(path.endswith("/dns_records") for _, path, _ in provider.calls))


if __name__ == "__main__":
    unittest.main()
