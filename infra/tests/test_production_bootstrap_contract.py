"""Mock-only production state and inventory contracts; never access a provider."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import production_bootstrap_contract as contract
import inspect_held_production as inspect
sys.path.insert(0, str(ROOT / "crates/mail-worker"))
import check_trace_sink_isolation as isolation

SHA = "a" * 40
DATABASE = "00000000-0000-0000-0000-000000000001"
BUCKET = "moesegfault-mail-raw-production"


def resources() -> contract.ProductionResources:
    """Select synthetic identifiers with real first-party public coordinates."""
    return contract.ProductionResources(DATABASE, BUCKET, SHA)


def held_gates() -> list[dict]:
    """No release latch or one-use send grant is enabled in a first inspection."""
    return [{"feedback_verified": 0, "abuse_contact_verified": 0,
             "delivery_canary_verified": 0, "preview_reviewed": 0, "live_grant": 0}]


def page(*, truncated=False, contents=None, cursor=None) -> dict:
    """Use complete SDK-shaped metadata; no object bodies or actual addresses."""
    values = [] if contents is None else contents
    result = {"Name": BUCKET, "IsTruncated": truncated, "KeyCount": len(values), "Contents": values}
    if cursor is not None:
        result["NextContinuationToken"] = cursor
    return result


class BootstrapInspectionTests(unittest.TestCase):
    """Current facts are bounded, explicit and never universal historical absence."""

    def test_resource_types_and_origins_fail_closed(self):
        """No arbitrary issuer, bucket or wrong-typed capability reaches the transport."""
        resources().validate()
        for name, value in (("database", None), ("source_sha", 1), ("bucket", None),
                            ("bucket", "moesegfault-mail-raw-staging"),
                            ("issuer", "https://identity.foreign.example"), ("client", "amail-cli-staging")):
            with self.subTest(name=name), self.assertRaises(ValueError):
                replace(resources(), **{name: value}).validate()

    def test_held_empty_state_and_material_negative_controls(self):
        """Any object, journal, reservation, enabled gate or live grant refuses first-bootstrap facts."""
        args = ([{"state": "held"}], held_gates(), [{"n": 0}], [{"n": 0}], 0)
        contract.held_state(*args)
        for index, value in ((0, [{"state": "enabled"}]), (2, [{"n": 1}]), (3, [{"n": 1}]),
                             (4, 1), (4, False), (2, [{"n": False}])):
            changed = list(args)
            changed[index] = value
            with self.subTest(index=index, value=value), self.assertRaises(ValueError):
                contract.held_state(*changed)
        for field in held_gates()[0]:
            changed = deepcopy(args)
            changed[1][0][field] = 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                contract.held_state(*changed)

    def test_s3_empty_whole_bucket_has_no_prefix_or_delimiter(self):
        """Only a complete whole-bucket page proves zero current objects."""
        client = Mock()
        client.list_objects_v2.return_value = page()
        self.assertEqual(inspect.r2_count(client, BUCKET), 0)
        client.list_objects_v2.assert_called_once_with(Bucket=BUCKET, MaxKeys=1000)

    def test_s3_multiple_pages_count_without_fetching_objects(self):
        """Continuation is explicit; existing object metadata never triggers GET or DELETE."""
        client = Mock()
        client.list_objects_v2.side_effect = [page(truncated=True, contents=[{"Key": "one", "Size": 1}], cursor="next"),
                                             page(contents=[{"Key": "two", "Size": 2}])]
        self.assertEqual(inspect.r2_count(client, BUCKET), 2)
        self.assertEqual(client.list_objects_v2.call_args.kwargs["ContinuationToken"], "next")
        client.get_object.assert_not_called()
        client.delete_object.assert_not_called()

    def test_s3_partial_or_malformed_pages_fail(self):
        """A prefix, duplicate key, missing cursor or forged count cannot prove empty."""
        bad = ({**page(), "Prefix": "messages/"}, {**page(), "Delimiter": "/"},
               {**page(), "KeyCount": False}, {**page(), "Name": "other"}, page(truncated=True),
               page(contents=[{"Key": "one", "Size": -1}]))
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                inspect.r2_count(Mock(list_objects_v2=Mock(return_value=value)), BUCKET)
        client = Mock()
        client.list_objects_v2.side_effect = [page(truncated=True, contents=[{"Key": "one", "Size": 0}], cursor="next"),
                                             page(contents=[{"Key": "one", "Size": 0}])]
        with self.assertRaises(ValueError):
            inspect.r2_count(client, BUCKET)

    def test_complete_inventory_rejects_duplicates_and_overflow(self):
        """Never truncate or silently overwrite provider inventory records."""
        self.assertEqual(inspect.exact_rows([{"id": "b"}, {"id": "a"}], "id", 2), [{"id": "a"}, {"id": "b"}])
        for values in ([{"id": "a"}] * 2, [{"id": "a"}, {"id": "b"}], [{"id": None}], None):
            with self.subTest(values=values), self.assertRaises(ValueError):
                inspect.exact_rows(values, "id", 1)

    def test_current_script_binding_capabilities_cannot_target_production(self):
        """Direct storage writers or service callers refuse the absent-first-API path."""
        provider = Mock(account="a" * 32, resources=resources())
        provider.envelope.return_value = {"success": True, "result": [{"id": "unrelated-worker"}]}
        provider.get.return_value = {"bindings": []}
        self.assertEqual(set(inspect.script_inventory(provider)), {"unrelated-worker"})
        for binding in ({"name": "DB", "type": "d1", "database_id": DATABASE},
                        {"name": "BODY", "type": "r2_bucket", "bucket_name": BUCKET},
                        {"name": "CALL", "type": "service", "service": "amail-mail"}):
            provider.get.return_value = {"bindings": [binding]}
            with self.subTest(binding=binding), self.assertRaises(ValueError):
                inspect.script_inventory(provider)

    def test_current_mail_role_or_maintenance_refuses_initial_inspection(self):
        """An existing Worker means recovery, not automatic bootstrap replay."""
        provider = Mock(account="a" * 32, resources=resources())
        for script in ("amail-mail", "amail-role-monitor", "amail-mail-maintenance"):
            provider.envelope.return_value = {"success": True, "result": [{"id": script}]}
            with self.subTest(script=script), self.assertRaises(ValueError):
                inspect.script_inventory(provider)
        provider.get.assert_not_called()

    def test_retained_fresh_workers_never_admit_original_store_or_service_callers(self):
        """A known completed checkpoint changes name absence, not original-store protection."""
        provider = Mock(account="a" * 32, resources=resources())
        owned = frozenset({"amail-mail", "amail-mail-maintenance"})
        provider.envelope.return_value = {"success": True, "result": [{"id": name} for name in sorted(owned)]}
        provider.get.return_value = {"bindings": []}
        self.assertEqual(set(inspect.script_inventory(provider, owned_scripts=owned)), owned)
        for binding in ({"name": "DB", "type": "d1", "database_id": DATABASE},
                        {"name": "BODY", "type": "r2_bucket", "bucket_name": BUCKET},
                        {"name": "CALL", "type": "service", "service": "amail-mail"}):
            provider.get.return_value = {"bindings": [binding]}
            with self.assertRaisesRegex(ValueError, "production_unexpected_store_or_service_caller"):
                inspect.script_inventory(provider, owned_scripts=owned)

    def test_query_rejects_mutations_before_any_transport(self):
        """The inspection D1 method exposes only fixed SELECT and PRAGMA reads."""
        provider = object.__new__(inspect.Provider)
        provider.envelope = Mock()
        for sql in ("UPDATE messages SET read=1", "DELETE FROM send_requests", "SELECT 1; DELETE FROM messages"):
            with self.subTest(sql=sql), self.assertRaises(ValueError):
                provider.query(sql)
        provider.envelope.assert_not_called()

    def test_main_guard_rejects_before_sdk_or_network(self):
        """No PR, accidental default dispatch or local environment can access production."""
        with patch.dict(inspect.os.environ, {}, clear=True), patch.object(inspect, "Provider") as provider, \
                patch("builtins.print"):
            self.assertEqual(inspect.main(), 1)
        provider.assert_not_called()

    def test_failure_bins_reject_exception_prose_and_arbitrary_sdk_codes(self):
        """Diagnostic output can be useful without leaking SDK tokens, object keys or mail."""
        self.assertEqual(inspect.failure_reason(ValueError("production_scripts_completeness_unverified")),
                         "production_scripts_completeness_unverified")
        self.assertEqual(inspect.failure_reason(ValueError("private-address@example.invalid secret-token")), "unexpected")
        error = Exception("private provider prose")
        error.response = {"Error": {"Code": "AccessDenied", "Message": "private-address@example.invalid"}}
        self.assertEqual(inspect.failure_reason(error), "r2_access_denied")
        error.response["Error"]["Code"] = "private-address@example.invalid"
        self.assertEqual(inspect.failure_reason(error), "unexpected")
        error.response = {"Error": {"Code": ["unsafe-type"]}}
        self.assertEqual(inspect.failure_reason(error), "unexpected")

    def test_legacy_domain_reader_classification_is_bounded_and_private(self):
        """A reused checker preserves status/contract bins without returning cause prose."""
        from urllib.error import HTTPError
        error = ValueError("sink_readback_unavailable")
        error.__cause__ = HTTPError("https://private.invalid/token", 403, "private-body", {}, None)
        self.assertEqual(inspect.failure_reason(error), "production_provider_http_403")
        self.assertEqual(inspect.failure_reason(ValueError("sink_domains_unverified")), "custom_domain_inventory_unverified")
        self.assertEqual(inspect.failure_reason(ImportError("private module name")), "domain_reader_dependency_missing")
        error.__cause__ = error
        self.assertEqual(inspect.failure_reason(error), "custom_domain_read_unavailable")
        unknown = ValueError("private-address@example.invalid")
        unknown.__cause__ = unknown
        self.assertEqual(inspect.failure_reason(unknown), "unexpected")
        self.assertEqual(inspect.http_reason("private-code"), "unexpected")

    def test_provider_http_denial_has_no_url_or_body_in_reason(self):
        """A documented status category is sufficient to distinguish permission failures."""
        from urllib.error import HTTPError
        provider = object.__new__(inspect.Provider)
        provider.token = "synthetic-secret"
        provider.opener = Mock()
        provider.opener.open.side_effect = HTTPError("https://private.invalid/path", 403, "private prose", {}, None)
        with self.assertRaisesRegex(ValueError, "^production_provider_http_403$") as result:
            provider.envelope("/accounts/" + "a" * 32 + "/workers/scripts")
        self.assertEqual(inspect.failure_reason(result.exception), "production_provider_http_403")

    def test_domain_structural_bins_preserve_strict_acceptance(self):
        """Distinguish failed schema rules without admitting incomplete domain lists."""
        row = {"id": "a" * 32, "service": "fixture", "hostname": "private.invalid"}
        valid = {"success": True, "result": [row], "result_info": {"count": 1, "page": 1, "total_pages": 1}}
        self.assertEqual(isolation.worker_domain_rows(valid), [row])
        cases = (
            ({**valid, "result": None}, "rows"),
            ({**valid, "result": [None]}, "row"),
            ({**valid, "result": [{**row, "id": None}]}, "id_type"),
            ({**valid, "result": [{**row, "id": "private\nidentifier"}]}, "id_format"),
            ({**valid, "result": [row, row]}, "id_duplicate"),
            ({**valid, "result": [{**row, "service": None}]}, "service"),
            ({**valid, "result_info": {"count": None}}, "count_type"),
            ({**valid, "result_info": {"count": 2}}, "count_mismatch"),
            ({**valid, "result_info": {"total_count": False}}, "total_count_type"),
            ({**valid, "result_info": {"total_count": 2}}, "total_count_mismatch"),
            ({**valid, "result_info": {"page": "private"}}, "page_type"),
            ({**valid, "result_info": {"page": 2}}, "page_mismatch"),
            ({**valid, "result_info": {"total_pages": None}}, "pages_type"),
            ({**valid, "result_info": {"total_pages": 2}}, "pages_mismatch"),
            ({**valid, "result_info": {"per_page": None}}, "per_page_type"),
            ({**valid, "result_info": {"per_page": 0}}, "per_page_mismatch"),
            ({**valid, "result_info": {"unexpected": "private"}}, "info"),
            ({**valid, "unexpected": "private"}, "envelope"),
        )
        for value, reason in cases:
            with self.subTest(reason=reason), self.assertRaises(isolation.DomainInventoryError) as result:
                isolation.worker_domain_rows(value)
            self.assertEqual(str(result.exception), "sink_domains_unverified")
            self.assertEqual(inspect.failure_reason(result.exception), "custom_domain_" + reason)
        error = ValueError("sink_domains_unverified")
        error.domain_reason = "private-address@example.invalid"
        self.assertEqual(inspect.failure_reason(error), "custom_domain_inventory_unverified")

    def test_domain_identifiers_are_opaque_not_account_hex(self):
        """Documented string IDs retain uniqueness/completeness regardless of encoding."""
        for identifier in ("opaque-domain-v2:one", "00000000-0000-0000-0000-000000000001", "A" * 32, "x" * 256, "domain/opaque?value#part", "域名:One"):
            row = {"id": identifier, "service": "fixture", "hostname": "fixture.invalid"}
            value = {"success": True, "result": [row], "result_info": {"count": 1, "total_count": 1}}
            with self.subTest(identifier=identifier):
                self.assertIs(isolation.worker_domain_rows(value)[0], row)
                self.assertEqual(row["id"], identifier)
            with self.assertRaises(isolation.DomainInventoryError):
                isolation.worker_domain_rows({**value, "result": [row, row]})
            with self.assertRaises(isolation.DomainInventoryError):
                isolation.worker_domain_rows({**value, "result_info": {"total_count": 2}})
        for identifier in ("", "x" * 257, "with space", "control\x7f", "c1\x85", "unicode\u2003space", "format\u200b", "surrogate\ud800"):
            with self.subTest(identifier=identifier), self.assertRaises(isolation.DomainInventoryError):
                isolation.worker_domain_rows({"success": True, "result": [
                    {"id": identifier, "service": "fixture", "hostname": "fixture.invalid"}]})

    def test_existing_domain_case_or_trailing_dot_cannot_hide_attachment(self):
        """The target host is case-insensitive DNS data, not opaque identity data."""
        provider = Mock(account="a" * 32, resources=resources())
        provider.get.return_value = {"name": "moesegfault.dev", "account": {"id": provider.account}}
        provider.envelope.side_effect = [{"success": True, "result": []}, {"success": True, "result": [
            {"id": "opaque:one", "hostname": "MAIL.MOESEGFAULT.DEV.", "service": "fixture"}]}]
        with self.assertRaisesRegex(ValueError, "^production_domain_already_attached$"):
            inspect.unattached_route(provider, "b" * 32)

    def test_domain_host_required_for_mail_attachment_inspection(self):
        """Sink service-only checks stay compatible; Mail host absence needs a host."""
        provider = Mock(account="a" * 32, resources=resources())
        provider.get.return_value = {"name": "moesegfault.dev", "account": {"id": provider.account}}
        provider.envelope.side_effect = [{"success": True, "result": []}, {"success": True, "result": [
            {"id": "opaque:one", "service": "fixture"}]}]
        with self.assertRaisesRegex(ValueError, "^production_domain_hostname_unverified$"):
            inspect.unattached_route(provider, "b" * 32)

    def test_domain_identity_is_exact_and_hostname_validation_is_fail_closed(self):
        """Case-distinct IDs remain distinct; malformed DNS rows cannot prove absence."""
        rows = [{"id": identifier, "service": "fixture", "hostname": "FIXTURE.INVALID."}
                for identifier in ("Opaque:One", "opaque:one")]
        self.assertEqual(isolation.worker_domain_rows({"success": True, "result": rows}), rows)
        for hostname in (None, "", " leading.invalid", "two..invalid", "bad-.invalid",
                         "bad.invalid..", "line\n.invalid", "x" * 64 + ".invalid"):
            provider = Mock(account="a" * 32, resources=resources())
            provider.get.return_value = {"name": "moesegfault.dev", "account": {"id": provider.account}}
            provider.envelope.side_effect = [{"success": True, "result": []}, {"success": True,
                                            "result": [{**rows[0], "hostname": hostname}]}]
            with self.subTest(hostname=hostname), self.assertRaisesRegex(
                    ValueError, "^production_domain_hostname_unverified$"):
                inspect.unattached_route(provider, "b" * 32)
        provider = Mock(account="a" * 32, resources=resources())
        provider.get.return_value = {"name": "moesegfault.dev", "account": {"id": provider.account}}
        provider.envelope.side_effect = [{"success": True, "result": []}, {"success": True, "result": rows}]
        self.assertEqual(inspect.unattached_route(provider, "b" * 32)["domains"], rows)
        self.assertEqual(rows[0]["hostname"], "FIXTURE.INVALID.")

    def test_domain_read_uses_one_no_redirect_provider_envelope(self):
        """Reuse validation, not a second transport or a raw provider artifact."""
        provider = Mock(account="a" * 32, resources=resources())
        provider.get.return_value = {"name": "moesegfault.dev", "account": {"id": provider.account}}
        provider.envelope.side_effect = [{"success": True, "result": []}, {"success": True, "result": []}]
        with patch.object(isolation, "worker_domains") as old_transport:
            result = inspect.unattached_route(provider, "b" * 32)
        self.assertEqual(result, {"routes": [], "domains": []})
        self.assertEqual(provider.envelope.call_count, 2)
        self.assertEqual(provider.envelope.call_args.args[0], f"/accounts/{provider.account}/workers/domains")
        old_transport.assert_not_called()

    def test_summary_excludes_raw_provider_configs(self):
        """Persist only approved aggregate facts and canonical digests, not arbitrary settings."""
        snapshot = {"scripts": {"unrelated": {"private": "not-for-artifacts"}}, "source_sha": SHA,
                    "schema_prefix": 10, "objects": 0}
        captured = Mock()
        with patch.dict(inspect.os.environ, {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
                                             "GITHUB_REPOSITORY": "kleedaisuki/moesegfault-amail"}, clear=True), \
                patch.object(inspect.Path, "mkdir"), patch.object(inspect.Path, "is_symlink", return_value=False), \
                patch.object(inspect.os, "open", return_value=7), patch.object(inspect.os, "fdopen") as file, \
                patch.object(inspect.json, "dump", captured):
            inspect.write_summary(snapshot)
        value = captured.call_args.args[0]
        self.assertNotIn("not-for-artifacts", json.dumps(value))
        self.assertNotIn("scripts", value)
        self.assertEqual(value["admission"], "NOT_GRANTED")
        self.assertEqual(value["historical_absence"], "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
