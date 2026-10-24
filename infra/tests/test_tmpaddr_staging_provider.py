"""Scoped temporary-domain provisioning contracts; no provider calls or secrets."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
from typing import Any
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/provider"))
import ensure_tmpaddr_staging as provision
import verify_sending


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
    def test_authoritative_verifier_shares_provider_txt_semantics(self) -> None:
        name = "selector._domainkey." + provision.DOMAIN
        logical = "v=DKIM1; p=" + "A" * 350
        presentation = f'"{logical[:200]}" "{logical[200:]}"'
        with patch.object(verify_sending, "DOMAIN", provision.DOMAIN):
            record = verify_sending.normalize({"name": name, "type": "TXT", "content": presentation})
            self.assertEqual(logical, record.content)
            raw = " v=spf1  include:example.invalid ~all "
            record = verify_sending.normalize({"name": provision.DOMAIN, "type": "TXT", "content": raw})
            self.assertEqual(raw, record.content)

    def test_txt_presentation_uses_logical_chunk_concatenation(self) -> None:
        self.assertEqual("v=DKIM1; p=abcdef", provision.normalize_txt('"v=DKIM1; p=abc" "def"'))
        self.assertEqual("v=spf1 include:example.invalid ~all", provision.normalize_txt('"v=spf1 include:example.invalid ~all"'))
        self.assertEqual('quoted="value"; backslash=\\', provision.normalize_txt(r'"quoted=\"value\"; backslash=\\"'))

    def test_single_quoted_logical_txt_is_not_limited_to_one_wire_chunk(self) -> None:
        logical = "v=DKIM1; p=" + "A" * 350
        self.assertEqual(logical, provision.normalize_txt(f'"{logical}"'))
        self.assertEqual(logical, provision.normalize_txt(f'"{logical[:200]}" "{logical[200:]}"'))
        provider = FakeProvider()
        name = "selector._domainkey." + provision.DOMAIN
        provider.required = [{"name": name, "type": "TXT", "content": f'"{logical}"'}]
        provider.records = [{"name": name, "type": "TXT", "content": f'"{logical[:200]}" "{logical[200:]}"'}]
        provider.domain = {"name": provision.DOMAIN, "enabled": True, "tag": "a" * 32, "preview_enabled": False, "drop_suppressed_recipients": False}
        provision.ensure_sending(provider, True)
        report = provision.inspect(provider, provider)
        self.assertTrue(report["sending_dns"]["requirements"][0]["txt_sha256_equal"])
        self.assertTrue(all(method == "GET" for method, _, _ in provider.calls))

    def test_dns_tokenizer_handles_octet_escapes_without_double_encoding(self) -> None:
        self.assertEqual("abc def", provision.normalize_txt(r'"abc\032def"'))
        self.assertEqual("é", provision.normalize_txt(r'"\195\169"'))
        self.assertEqual("a\x00b", provision.normalize_txt(r'"a\000b"'))
        for presentation in (r'"\999"', r'"\1"', r'"\12x"', r'"\255"', '"closed" trailing', '"closed" ; private-comment'):
            with self.subTest(presentation_length=len(presentation)), self.assertRaisesRegex(provision.ProvisionError, "^dns_txt_presentation_invalid$"):
                provision.normalize_txt(presentation)

    def test_txt_raw_content_and_spaces_are_preserved(self) -> None:
        for content in (" v=spf1  include:example.invalid ~all ", 'v=DKIM1; n="quoted note"; p=abc', "v=DKIM1; p=" + "A" * 350):
            with self.subTest(length=len(content)):
                self.assertEqual(content, provision.normalize_txt(content))

    def test_long_segmented_dkim_is_equal_without_mutation_or_key_output(self) -> None:
        provider = FakeProvider()
        logical = "v=DKIM1; p=" + "A" * 350
        name = "selector._domainkey." + provision.DOMAIN
        provider.required = [{"name": name, "type": "TXT", "content": logical}]
        provider.records = [{"name": name, "type": "TXT", "content": f'"{logical[:200]}" "{logical[200:]}"'}]
        provider.domain = {"name": provision.DOMAIN, "enabled": True, "tag": "a" * 32, "preview_enabled": False, "drop_suppressed_recipients": False}
        provision.ensure_sending(provider, True)
        report = provision.inspect(provider, provider)
        facts = report["sending_dns"]["requirements"][0]
        self.assertTrue(facts["exact_present"])
        self.assertTrue(facts["txt_content_equal"])
        self.assertTrue(facts["txt_sha256_equal"])
        self.assertEqual(1, facts["txt_presentation_changed_count"])
        self.assertFalse(facts["conflict"])
        self.assertTrue(all(method == "GET" for method, _, _ in provider.calls))
        self.assertNotIn("A" * 100, str(report))

    def test_malformed_txt_is_a_closed_error(self) -> None:
        with self.assertRaisesRegex(provision.ProvisionError, "^dns_txt_presentation_invalid$"):
            provision.normalize_txt('"private-key-material-without-closing-quote')

    def test_verification_txt_coexists_with_generated_spf(self) -> None:
        provider = FakeProvider()
        name = "cf-bounce." + provision.DOMAIN
        verification = {"name": name, "type": "TXT", "content": "provider-verification=synthetic"}
        provider.records = [verification.copy()]
        provider.required = [{"name": name, "type": "TXT", "content": "v=spf1 include:_spf.mx.cloudflare.net ~all"}]
        provision.ensure_sending(provider, True)
        self.assertIn(verification, provider.records)
        self.assertEqual(2, len(provider.records))
        report = provision.inspect(provider, provider)
        facts = report["sending_dns"]["requirements"][0]
        self.assertEqual("spf", facts["purpose"])
        self.assertTrue(facts["exact_present"])
        self.assertFalse(facts["conflict"])
        self.assertFalse(facts["spf_merge_attempted"])

    def test_other_mx_values_are_retained_in_the_rrset(self) -> None:
        provider = FakeProvider()
        original = {"name": "cf-bounce." + provision.DOMAIN, "type": "MX", "content": "old.mx.cloudflare.net", "priority": 30}
        provider.records = [original.copy()]
        provision.ensure_sending(provider, True)
        self.assertIn(original, provider.records)
        self.assertTrue(all(method not in ("PUT", "DELETE") for method, _, _ in provider.calls))

    def test_conflicting_spf_and_dmarc_are_not_added_or_merged(self) -> None:
        for name, old, new in (
            ("cf-bounce." + provision.DOMAIN, "v=spf1 -all", "v=spf1 include:_spf.mx.cloudflare.net ~all"),
            ("_dmarc." + provision.DOMAIN, "v=DMARC1; p=reject", "v=DMARC1; p=none"),
        ):
            with self.subTest(name=name):
                provider = FakeProvider()
                original = {"name": name, "type": "TXT", "content": old}
                provider.records = [original.copy()]
                provider.required = [{"name": name, "type": "TXT", "content": new}]
                with self.assertRaisesRegex(provision.ProvisionError, "sending_existing_dns_conflict"):
                    provision.ensure_sending(provider, True)
                self.assertEqual([original], provider.records)
                self.assertFalse(any(path.endswith("/dns_records") for _, path, _ in provider.calls))

    def test_cname_is_exclusive_even_with_non_mail_records(self) -> None:
        cname = {"name": "selector._domainkey." + provision.DOMAIN, "type": "CNAME", "content": "target.example.invalid"}
        address = {"name": cname["name"], "type": "A", "content": "192.0.2.1"}
        self.assertTrue(provision.requirement_facts(cname, [address])["conflict"])
        txt = {"name": cname["name"], "type": "TXT", "content": "verification=synthetic"}
        self.assertTrue(provision.requirement_facts(txt, [cname])["conflict"])

    def test_apply_uses_deployment_credential_for_domain_onboarding(self) -> None:
        deployment = FakeProvider()
        runtime = FakeProvider()
        environment = {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/codex/v0.3.0-multitenant", "AMAIL_STAGING_CONFIRM": "RUN_STAGING_V030", "AMAIL_STAGING_ENVIRONMENT": "staging", "GITHUB_RUN_ATTEMPT": "1", "CLOUDFLARE_API_TOKEN": "synthetic-deployment"}
        with patch.dict(provision.os.environ, environment, clear=True), patch.object(sys, "argv", ["helper", "--apply"]), patch.object(provision, "Client", side_effect=[deployment, runtime]), patch.object(provision, "ensure_routing") as routing, patch.object(provision, "ensure_sending") as sending, patch("builtins.print"):
            self.assertEqual(0, provision.main())
        routing.assert_called_once_with(deployment, deployment, True)
        sending.assert_called_once_with(deployment, True)

    def test_inspection_of_missing_domain_is_get_only(self) -> None:
        provider = FakeProvider()
        report = provision.inspect(provider, provider)
        self.assertEqual({"state": "observed", "record_count": 0, "routing_ready": False}, report["dns"])
        self.assertEqual({"state": "observed", "present": False}, report["sending"])
        self.assertTrue(all(method == "GET" for method, _, _ in provider.calls))

    def test_inspection_failure_is_unknown_and_other_reads_continue(self) -> None:
        class DeniedDns(FakeProvider):
            def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
                if "/dns_records?" in path:
                    self.calls.append((method, path, body))
                    raise provision.ProviderError("permission_or_provider_rejection", method, path, "deployment", 403)
                return super().request(method, path, body)

        provider = DeniedDns()
        report = provision.inspect(provider, provider)
        self.assertEqual("unknown", report["dns"]["state"])
        self.assertNotIn("record_count", report["dns"])
        self.assertEqual("dns_records", report["dns"]["phase"])
        self.assertEqual(403, report["dns"]["http"])
        self.assertFalse(report["sending"]["present"])
        self.assertTrue(all(method == "GET" for method, _, _ in provider.calls))

    def test_inspection_of_ready_domain_omits_dns_content_and_tags(self) -> None:
        provider = FakeProvider()
        provision.ensure_routing(provider, provider, True)
        provision.ensure_sending(provider, True)
        provider.calls.clear()
        report = provision.inspect(provider, provider)
        self.assertTrue(report["sending_dns"]["ready"])
        self.assertTrue(all(method == "GET" for method, _, _ in provider.calls))
        self.assertNotIn("p=synthetic", str(report))
        self.assertNotIn("a" * 32, str(report))
        self.assertEqual("unverified", report["routing_token_read"]["write_permission"])
        self.assertEqual("unverified", report["deployment_routing_read"]["write_permission"])

    def test_deployment_and_runtime_routing_reads_are_independent(self) -> None:
        class DeniedRuntime(FakeProvider):
            def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
                self.calls.append((method, path, body))
                raise provision.ProviderError("permission_or_provider_rejection", method, path, "routing", 403)

        deployment = FakeProvider()
        deployment.domain = {"synthetic": True}
        runtime = DeniedRuntime()
        report = provision.inspect(deployment, runtime)
        self.assertEqual("observed", report["deployment_routing_read"]["state"])
        self.assertEqual("unknown", report["routing_token_read"]["state"])
        self.assertEqual("routing", report["routing_token_read"]["credential"])
        self.assertEqual(403, report["routing_token_read"]["http"])
        self.assertTrue(all(method == "GET" for method, _, _ in deployment.calls + runtime.calls))

    def test_http_diagnostics_have_closed_phase_method_status_and_role(self) -> None:
        client = provision.Client("synthetic-secret", "routing")
        error = urllib.error.HTTPError("https://private.invalid/secret", 403, "private provider prose", {}, None)
        with patch.object(provision.urllib.request, "urlopen", side_effect=error), self.assertRaises(provision.ProviderError) as raised:
            client.request("POST", provision.PREFIX + "/email/routing/dns", {"name": provision.DOMAIN})
        self.assertEqual({"code": "permission_or_provider_rejection", "phase": "routing_dns", "method": "POST", "http": 403, "credential": "routing"}, raised.exception.details)
        self.assertNotIn("synthetic-secret", repr(client))
        self.assertNotIn("private", str(raised.exception))

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
