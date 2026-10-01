"""Hosted synthetic canary lifecycle/collection tests; never contact a provider."""

from pathlib import Path
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from urllib.error import HTTPError
from unittest.mock import MagicMock, Mock, patch
from email.message import Message
from types import SimpleNamespace
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import native_tracing_experiment as experiment
from test_native_route_lifecycle_contract import FakeProvider

NONCE="a"*32


class NativeReceiptDurabilityTests(unittest.TestCase):
    """Hosted filesystem fault fixtures; no real provider or deployment process."""

    def setUp(self):
        """Keep synthetic public receipts inside this checkout's temporary root."""
        folder = ROOT / ".temp"
        folder.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="native-receipt-", dir=folder)
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.receipt = self.folder / "experiment.json"
        self.previous = {"schema": "native-tracing-experiment/v1", "probe_id": NONCE,
                         "versions": {experiment.CALLER: "known-version"},
                         "ingress": {"dns": {"id": "known-dns"}, "route": {"id": "known-route"}}}
        self.original = json.dumps(self.previous, sort_keys=True).encode()
        self.receipt.write_bytes(self.original)
        for name, value in (("FOLDER", self.folder), ("RECEIPT", self.receipt)):
            replacement = patch.object(experiment, name, value)
            replacement.start()
            self.addCleanup(replacement.stop)

    def assert_previous_intact(self):
        """Known nonce and resource coordinates survive byte-for-byte, without debris."""
        self.assertEqual(self.receipt.read_bytes(), self.original)
        self.assertEqual(json.loads(self.receipt.read_text()), self.previous)
        self.assertEqual(list(self.folder.iterdir()), [self.receipt])

    def test_success_replaces_closed_same_directory_file_with_identical_json(self):
        """The sole visibility boundary occurs after file fsync and close."""
        create = experiment.tempfile.NamedTemporaryFile
        replace = experiment.os.replace
        outputs = []
        events = []

        def temporary(**kwargs):
            output = create(**kwargs)
            outputs.append(output)
            return output

        def install(source, target):
            self.assertTrue(outputs[-1].closed)
            self.assertEqual(Path(source).parent, self.receipt.parent)
            self.assertNotEqual(Path(source), self.receipt)
            self.assertEqual(Path(target), self.receipt)
            self.assertEqual(self.receipt.read_bytes(), self.original)
            self.assertEqual(events, ["file_sync"])
            replace(source, target)
            events.append("replace")

        value = {**self.previous, "extra": "synthetic"}
        with patch.object(experiment.tempfile, "NamedTemporaryFile", side_effect=temporary), \
             patch.object(experiment.os, "fsync", side_effect=lambda _: events.append("file_sync")), \
             patch.object(experiment.os, "replace", side_effect=install), \
             patch.object(experiment, "sync_receipt_directory", side_effect=lambda: events.append("directory_sync")):
            experiment.write_receipt(value)
        self.assertEqual(events, ["file_sync", "replace", "directory_sync"])
        self.assertEqual(self.receipt.read_bytes(), json.dumps(value, sort_keys=True).encode())
        self.assertEqual(list(self.folder.iterdir()), [self.receipt])

    def test_partial_write_failure_preserves_previous_receipt(self):
        """Even a partially filled pending file never truncates the recovery boundary."""
        create = experiment.tempfile.NamedTemporaryFile

        def temporary(**kwargs):
            output = create(**kwargs)
            write = output.write

            def interrupted(value):
                write(value[:12])
                raise OSError("synthetic_write_failure")

            output.write = interrupted
            return output

        with patch.object(experiment.tempfile, "NamedTemporaryFile", side_effect=temporary), \
             patch.object(experiment.os, "replace") as replace:
            with self.assertRaisesRegex(OSError, "synthetic_write_failure"):
                experiment.write_receipt({**self.previous, "next": True})
        replace.assert_not_called()
        self.assert_previous_intact()

    def test_file_sync_and_replace_failures_preserve_previous_receipt(self):
        """Disk durability and atomic installation failures stop advancement."""
        for boundary in ("fsync", "replace"):
            with self.subTest(boundary=boundary), \
                 patch.object(experiment.os, boundary, side_effect=OSError("synthetic_failure")), \
                 patch.object(experiment, "sync_receipt_directory") as directory:
                with self.assertRaisesRegex(OSError, "synthetic_failure"):
                    experiment.write_receipt({**self.previous, "next": True})
                directory.assert_not_called()
                self.assert_previous_intact()

    def test_serialization_failure_never_opens_temporary_file(self):
        """An invalid value cannot disturb the existing receipt or staging area."""
        with patch.object(experiment.tempfile, "NamedTemporaryFile") as create:
            with self.assertRaises(TypeError):
                experiment.write_receipt({"unsupported": object()})
        create.assert_not_called()
        self.assert_previous_intact()

    def test_directory_sync_failure_keeps_complete_new_receipt_and_raises(self):
        """Post-replace failure is not falsely described as an old-receipt rollback."""
        value = {**self.previous, "next": True}
        with patch.object(experiment, "sync_receipt_directory", side_effect=OSError("synthetic_directory_sync")):
            with self.assertRaisesRegex(OSError, "synthetic_directory_sync"):
                experiment.write_receipt(value)
        self.assertEqual(json.loads(self.receipt.read_text()), value)
        self.assertEqual(list(self.folder.iterdir()), [self.receipt])

    def test_initial_receipt_failure_stops_before_provider_construction(self):
        """No provider read/write is admitted without the durable initial boundary."""
        build = MagicMock()
        build.__truediv__ = Mock(return_value=build)
        build.read_text.return_value = "{}"
        with patch.object(experiment, "ROOT", build), \
             patch.object(experiment, "Provider") as provider, \
             patch.object(experiment.os, "replace", side_effect=OSError("synthetic_replace")), \
             patch.object(experiment.subprocess, "run") as process, \
             patch.dict(experiment.os.environ, {"GITHUB_SHA": "b" * 40, "GITHUB_RUN_ID": "123"}):
            with self.assertRaisesRegex(OSError, "synthetic_replace"):
                experiment.deploy(route=True)
        provider.assert_not_called()
        process.assert_not_called()
        self.assert_previous_intact()

    def test_verified_receipt_failure_admits_no_dns_route_or_worker_write(self):
        """A successful GET-only preflight cannot bypass failed persisted admission."""
        build = MagicMock()
        build.__truediv__ = Mock(return_value=build)
        build.read_text.return_value = "{}"
        replace = experiment.os.replace
        calls = []

        def install(source, target):
            calls.append(source)
            if len(calls) == 2:
                raise OSError("synthetic_admission_replace")
            replace(source, target)

        with patch.object(experiment, "ROOT", build), \
             patch.object(experiment, "Provider") as provider, \
             patch.object(experiment.ingress, "preflight", return_value={"accepted": True}), \
             patch.object(experiment.ingress, "create_dns") as dns, \
             patch.object(experiment.ingress, "create_route") as route, \
             patch.object(experiment.os, "replace", side_effect=install), \
             patch.object(experiment.subprocess, "run") as process, \
             patch.dict(experiment.os.environ, {"GITHUB_SHA": "b" * 40, "GITHUB_RUN_ID": "123"}):
            with self.assertRaisesRegex(OSError, "synthetic_admission_replace"):
                experiment.deploy(route=True)
        provider.return_value.request.assert_not_called()
        for operation in (dns, route, process):
            operation.assert_not_called()
        retained = json.loads(self.receipt.read_text())
        self.assertEqual(retained["preflight_state"]["phase"], "attempted")
        self.assertFalse(retained["preflight_state"]["mutation_admitted"])
        self.assertEqual(list(self.folder.iterdir()), [self.receipt])


class NativeTracingExperimentTests(unittest.TestCase):
    """No hidden build, foreign cleanup, raw provider dump or partial privacy verdict."""

    def test_configs_package_tested_bytes_without_custom_build_or_mail_binding(self):
        for name in experiment.NAMES:
            value=experiment.config(name,NONCE)
            self.assertNotIn("build",value)
            self.assertNotIn("env",value)
            self.assertEqual(value["vars"]["PROBE_ID"],NONCE)
            self.assertTrue(value["main"].endswith("build/worker/shim.mjs"))
            for key in ("r2_buckets","d1_databases","queues","send_email","secrets"):
                self.assertNotIn(key,value)
        self.assertFalse(experiment.config(experiment.PROBE,NONCE)["workers_dev"])
        self.assertFalse(experiment.config(experiment.CALLER,NONCE)["observability"]["enabled"])

    def test_disabled_capture_accepts_optional_omission_but_not_unknown_or_enabled(self):
        for observation in ({"enabled": False},
                            {"enabled": False, "logs": {"enabled": False}, "traces": {"enabled": False}}):
            self.assertTrue(experiment.capture_accepted({"observability": observation}, experiment.CALLER))
        for observation in ({}, {"enabled": True}, {"enabled": 0},
                            {"enabled": False, "logs": {"enabled": True}},
                            {"enabled": False, "traces": {}},
                            {"enabled": False, "logs": None}):
            self.assertFalse(experiment.capture_accepted({"observability": observation}, experiment.CALLER))
        self.assertTrue(experiment.capture_accepted({}, experiment.CALLER))
        self.assertTrue(experiment.capture_accepted({"observability": None}, experiment.CALLER))
        self.assertFalse(experiment.capture_accepted({"observability": None}, experiment.PROBE))
        self.assertTrue(experiment.capture_accepted({"observability": {"traces": {"enabled": True}}}, experiment.PROBE))
        self.assertFalse(experiment.capture_accepted({"observability": {"enabled": True}}, experiment.PROBE))
        self.assertEqual(experiment.capture_readback({"observability": {"enabled": False}}),
                         {"observability": "dict", "enabled": False, "logs.enabled": "missing", "traces.enabled": "missing"})
        self.assertEqual(experiment.capture_readback({"observability": {"enabled": "private-text", "logs": None}}),
                         {"observability": "dict", "enabled": "str", "logs.enabled": "parent_NoneType", "traces.enabled": "missing"})

    def test_route_config_uses_identical_module_and_private_pair(self):
        """Route configuration changes ingress, never compiled Rust/service topology."""
        for name in experiment.NAMES:
            before = experiment.config(name, NONCE)
            after = experiment.config(name, NONCE, route=True)
            self.assertEqual(after, {**before, "workers_dev": False})

    def test_route_deploy_checks_all_prerequisites_then_first_dns_write(self):
        """Denied bounded DNS creation cannot deploy scripts or create a route."""
        events = []
        provider = Mock(account="a" * 32)
        preflight = {"accepted": True}
        def refuse(*args):
            events.append("dns")
            raise ValueError("synthetic_dns_denied")
        build = MagicMock()
        build.read_text.return_value = "{}"
        with patch.object(experiment, "Provider", return_value=provider), \
             patch.object(experiment.ingress, "preflight", side_effect=lambda _: events.append("preflight") or preflight), \
             patch.object(experiment.ingress, "create_dns", side_effect=refuse), \
             patch.object(experiment.ingress, "create_route") as route, \
             patch.object(experiment, "write_receipt", side_effect=lambda _: events.append("persist")), \
             patch.object(experiment.subprocess, "run") as process, \
             patch.object(experiment, "ROOT", build), \
             patch.dict(experiment.os.environ, {"GITHUB_SHA": "b" * 40, "GITHUB_RUN_ID": "123"}):
            # Path composition is intercepted only for checked artifact identity.
            build.__truediv__ = Mock(return_value=build)
            with self.assertRaisesRegex(ValueError, "synthetic_dns_denied"):
                experiment.deploy(route=True)
        self.assertEqual(events, ["persist", "preflight", "persist", "dns"])
        process.assert_not_called()
        route.assert_not_called()

    def assert_preflight_refusal_retained(self, provider, error_type):
        """Exercise real preread admission and prove refused cleanup is provider-free."""
        retained = []
        build = MagicMock()
        build.__truediv__ = Mock(return_value=build)
        build.read_text.return_value = '{"source_sha":"original-build"}'
        receipt = Mock()
        receipt.exists.return_value = True
        receipt.read_text.side_effect = lambda: json.dumps(retained[-1])
        provider.last_request = getattr(provider, "last_request", None)
        with patch.object(experiment, "Provider", return_value=provider) as constructor, \
             patch.object(experiment, "ROOT", build), \
             patch.object(experiment, "RECEIPT", receipt), \
             patch.object(experiment, "write_receipt", side_effect=lambda value: retained.append(deepcopy(value))), \
             patch.object(experiment.ingress, "create_dns") as dns, \
             patch.object(experiment.ingress, "create_route") as route, \
             patch.object(experiment.ingress, "cleanup_ingress") as cleanup, \
             patch.object(experiment.subprocess, "run") as process, \
             patch.dict(experiment.os.environ, {"GITHUB_SHA": "b" * 40, "GITHUB_RUN_ID": "123"}):
            with self.assertRaises(error_type):
                experiment.deploy(route=True)
            self.assertEqual(retained[0]["preflight_state"]["phase"], "attempted")
            self.assertFalse(retained[0]["preflight_state"]["mutation_admitted"])
            self.assertEqual(retained[-1]["preflight_state"]["phase"], "refused")
            self.assertFalse(retained[-1]["preflight_state"]["mutation_admitted"])
            self.assertEqual(retained[-1]["build_identity"], {"source_sha": "original-build"})
            self.assertEqual(retained[-1]["source_sha"], "b" * 40)
            self.assertEqual(retained[-1]["versions"], {})
            if provider.last_request is not None:
                self.assertEqual(retained[-1]["preflight_state"]["last_request"], provider.last_request)
            self.assertNotIn("private-provider-prose", json.dumps(retained))
            before = deepcopy(provider.calls)
            experiment.cleanup()
            self.assertEqual(provider.calls, before)
            constructor.assert_called_once()
            for operation in (dns, route, cleanup, process):
                operation.assert_not_called()
        self.assertEqual(retained[-1]["cleanup"]["outcome"], "not_needed_no_mutation_admitted")
        self.assertFalse(retained[-1]["cleanup"]["resource_absence_verified"])
        self.assertNotIn("cleaned_at", retained[-1])

    def test_each_failed_route_preread_retains_no_write_receipt(self):
        """Any denied or interrupted preread stays a refusal, never absence/recovery."""
        sample = FakeProvider()
        endpoints = [experiment.ingress.ZONE, experiment.ingress.ZONE + "/ssl/universal/settings",
                     experiment.ingress.ZONE + "/ssl/certificate_packs",
                     experiment.ingress.ZONE + "/dns_records", experiment.ingress.ZONE + "/workers/routes",
                     f"/accounts/{sample.account}/workers/domains",
                     sample.script(experiment.PROBE), sample.script(experiment.CALLER)]
        for endpoint in endpoints:
            for error in (HTTPError("https://synthetic.invalid", 403, "private-provider-prose", {}, None),
                          TimeoutError("private-provider-prose")):
                with self.subTest(endpoint=endpoint, error_type=type(error).__name__):
                    provider = FakeProvider()
                    provider.overrides[("GET", endpoint)] = error
                    self.assert_preflight_refusal_retained(provider, type(error))

    def test_schema_and_conflict_preflight_refusals_retain_no_write_receipt(self):
        """Malformed inventories and positive conflicts cannot admit mutation."""
        variants = (lambda p: p.zone.update(paused=True),
                    lambda p: p.ssl.update(enabled=False),
                    lambda p: p.packs[0].update(status="pending_validation"),
                    lambda p: p.overrides.update({("GET", experiment.ingress.ZONE + "/dns_records"): {}}),
                    lambda p: p.overrides.update({("GET", experiment.ingress.ZONE + "/workers/routes"): {}}),
                    lambda p: p.overrides.update({("GET", f"/accounts/{p.account}/workers/domains"): {}}),
                    lambda p: p.dns.append({"id": "foreign", "name": experiment.ingress.HOST}),
                    lambda p: p.routes.append({"id": "foreign", "pattern": experiment.ingress.PATTERN}),
                    lambda p: p.domains.append({"id": "foreign", "hostname": experiment.ingress.HOST}),
                    lambda p: setattr(p, "live", True))
        for index, mutate in enumerate(variants):
            with self.subTest(variant=index):
                provider = FakeProvider()
                mutate(provider)
                self.assert_preflight_refusal_retained(provider, ValueError)

    def test_provider_ssl_403_preserves_typed_facts_without_provider_prose(self):
        """The observed SSL refusal shape survives error-body consumption safely."""
        headers = Message()
        headers["cf-ray"] = "a43d0cd0f97267c5-DFW"
        headers["set-cookie"] = "private-provider-prose"
        error = HTTPError("https://synthetic.invalid/private-provider-prose", 403,
                          "private-provider-prose", headers,
                          io.BytesIO(b'{"errors":[{"code":9109,"message":"private-provider-prose"}]}'))
        with patch.dict(experiment.os.environ, {"CLOUDFLARE_ACCOUNT_ID": "a" * 32,
                                                "CLOUDFLARE_API_TOKEN": "private-provider-prose"}), \
             redirect_stdout(io.StringIO()):
            provider = experiment.Provider()
            provider.opener = Mock()
            provider.opener.open.side_effect = error
            with self.assertRaises(HTTPError):
                provider.request("GET", experiment.ingress.ZONE + "/ssl/universal/settings")
        facts = provider.last_request
        self.assertEqual(facts["endpoint"], "workers.canary.existing_tls")
        self.assertEqual(facts["resource"], "universal_ssl_settings")
        self.assertEqual(facts["method"], "GET")
        self.assertEqual(facts["http_status"], 403)
        self.assertEqual(facts["provider_error_codes"], [9109])
        self.assertEqual(facts["cf_ray"], "a43d0cd0f97267c5-DFW")
        self.assertGreaterEqual(facts["duration_ms"], 0)
        self.assertNotIn("private-provider-prose", json.dumps(facts))
        fixture = FakeProvider()
        fixture.last_request = facts
        fixture.overrides[("GET", experiment.ingress.ZONE + "/ssl/universal/settings")] = error
        self.assert_preflight_refusal_retained(fixture, HTTPError)

    def test_missing_provider_context_is_retained_before_any_preread(self):
        """Missing configuration is a no-write refusal, not a missing artifact."""
        retained = []
        build = MagicMock()
        build.__truediv__ = Mock(return_value=build)
        build.read_text.return_value = "{}"
        with patch.object(experiment, "Provider", side_effect=KeyError("private-provider-prose")), \
             patch.object(experiment, "ROOT", build), \
             patch.object(experiment, "write_receipt", side_effect=lambda value: retained.append(deepcopy(value))), \
             patch.dict(experiment.os.environ, {"GITHUB_SHA": "b" * 40, "GITHUB_RUN_ID": "123"}):
            with self.assertRaises(KeyError):
                experiment.deploy(route=True)
        self.assertEqual([value["preflight_state"]["phase"] for value in retained], ["attempted", "refused"])
        self.assertEqual(retained[-1]["preflight_state"]["error_type"], "KeyError")
        self.assertNotIn("private-provider-prose", json.dumps(retained))

    def test_legacy_workers_dev_preread_failure_is_also_retained(self):
        """The compatibility ingress keeps its absence gate and gains safe receipts."""
        retained = []
        build = MagicMock()
        build.__truediv__ = Mock(return_value=build)
        build.read_text.return_value = "{}"
        provider = Mock(last_request=None)
        provider.request.side_effect = HTTPError("https://synthetic.invalid", 403,
                                               "private-provider-prose", {}, None)
        with patch.object(experiment, "Provider", return_value=provider), \
             patch.object(experiment, "ROOT", build), \
             patch.object(experiment, "write_receipt", side_effect=lambda value: retained.append(deepcopy(value))), \
             patch.object(experiment.subprocess, "run") as process, \
             patch.dict(experiment.os.environ, {"GITHUB_SHA": "b" * 40, "GITHUB_RUN_ID": "123"}):
            with self.assertRaises(HTTPError):
                experiment.deploy()
        self.assertEqual(retained[-1]["preflight_state"]["phase"], "refused")
        self.assertFalse(retained[-1]["preflight_state"]["mutation_admitted"])
        self.assertNotIn("transport", retained[-1])
        process.assert_not_called()

    def test_no_write_cleanup_refuses_contradictory_receipt(self):
        """An unknown mutation can never be hidden by a preflight refusal label."""
        base = {"versions": {}, "preflight_state": {"phase": "refused", "mutation_admitted": False}}
        for fields in ({"versions": {experiment.PROBE: "owned-version"}},
                       {"ingress": {"dns": {"phase": "unknown"}}},
                       {"ingress": {"route": {"phase": "attempted"}}},
                       {"url": "https://synthetic.invalid"},
                       {"preflight_state": {"phase": "refused", "mutation_admitted": True}}):
            receipt = Mock()
            receipt.exists.return_value = True
            receipt.read_text.return_value = json.dumps({**base, **fields})
            with patch.object(experiment, "RECEIPT", receipt), \
                 patch.object(experiment, "Provider") as provider, \
                 patch.object(experiment, "write_receipt") as persist:
                with self.assertRaisesRegex(ValueError, "canary_preflight_no_write_state_invalid"):
                    experiment.cleanup()
            provider.assert_not_called()
            persist.assert_not_called()

    def test_route_cleanup_refusal_prevents_any_script_deletion(self):
        """An unresolved ingress cannot leave a live route pointing at no Worker."""
        receipt = Mock()
        receipt.exists.return_value = True
        receipt.read_text.return_value = json.dumps({"transport": "owned_zone_route_v1", "probe_id": NONCE})
        provider = Mock()
        with patch.object(experiment, "RECEIPT", receipt), \
             patch.object(experiment, "Provider", return_value=provider), \
             patch.object(experiment.ingress, "cleanup_ingress", side_effect=ValueError("synthetic_ownership_conflict")):
            with self.assertRaisesRegex(ValueError, "synthetic_ownership_conflict"):
                experiment.cleanup()
        provider.request.assert_not_called()

    def test_cleanup_ownership_requires_exact_run_and_role(self):
        settings={"bindings":[{"type":"plain_text","name":"PROBE_ID","text":NONCE},
                              {"type":"plain_text","name":"CANARY_ROLE","text":"probe"}]}
        self.assertTrue(experiment.owned(settings,NONCE,"probe"))
        self.assertFalse(experiment.owned(settings,"b"*32,"probe"))
        self.assertFalse(experiment.owned(settings,NONCE,"caller"))
        self.assertFalse(experiment.owned({"bindings":[]},NONCE,"probe"))

    def test_whole_record_marker_paths_and_native_public_parentage(self):
        report={"case":{"run":NONCE,"mode":"redacted","kind":"success"},"available":True,"stage":"complete"}
        records=[{"$metadata":{"service":experiment.PROBE,"requestId":"opaque-request-id","spanId":"parent","traceId":"trace"},
                  "source":{"message":report},"$workers":{"event":{"request":{"url":"amail_native_path_"+NONCE}}}},
                 {"$metadata":{"service":experiment.PROBE,"requestId":"opaque-request-id","spanId":"child","parentSpanId":"parent",
                                 "traceId":"trace","spanName":"amail.canary.operation"},"source":{}}]
        summary=experiment.summarize(records,NONCE)
        self.assertEqual(summary["spans"][1]["parentSpanId"],"parent")
        self.assertEqual(summary["cases"]["redacted.success"]["marker_locations"]["path"],["$workers.event.request.url"])
        self.assertNotIn("amail_native_path_",str(summary))
        with self.assertRaises(ValueError):experiment.summarize([{"$metadata":{"service":"foreign-worker"}}],NONCE)

    def test_trigger_failure_facts_do_not_retain_challenge_tokens_or_prose(self):
        headers = Message()
        for key, value in (("Content-Type", "text/html; charset=utf-8"), ("CF-Ray", "public-ray-IAD"),
                           ("CF-Mitigated", "challenge"), ("Server", "cloudflare"),
                           ("Set-Cookie", "SYNTHETIC_PRIVATE_COOKIE"), ("Location", "https://private.invalid/token")):
            headers[key] = value
        result = experiment.trigger_facts(SimpleNamespace(code=403, headers=headers), b"SYNTHETIC_CHALLENGE_TOKEN")
        self.assertEqual(result["http_status"], 403)
        self.assertEqual(result["cf_ray"], "public-ray-IAD")
        self.assertTrue(result["cloudflare_challenge"])
        self.assertEqual(result["media_type"], "text/html")
        self.assertNotIn("SYNTHETIC", str(result))
        self.assertNotIn("private.invalid", str(result))
        self.assertEqual(experiment.trigger_facts(SimpleNamespace(code=403, headers=headers), b"Forbidden")["body_class"], "bare_forbidden")

    def test_standard_public_provider_error_code_is_retained_without_prose(self):
        headers = Message()
        for code in (1010, 1020):
            result = experiment.trigger_facts(SimpleNamespace(code=403, headers=headers), f"error code: {code}\n".encode())
            self.assertEqual(result["provider_error_code"], code)
            self.assertEqual(result["body_class"], "cloudflare_error_code")
        self.assertNotIn("provider_error_code", experiment.trigger_facts(
            SimpleNamespace(code=403, headers=headers), b"error code: private-address"))

    def test_absent_endpoint_probe_never_creates_or_posts_and_refuses_live_scripts(self):
        provider = Mock(account="a" * 32)
        provider.script.side_effect = lambda name: "/scripts/" + name + "/settings"
        provider.request.side_effect = [HTTPError("https://api.synthetic.invalid", 404, "missing", {}, None),
            HTTPError("https://api.synthetic.invalid", 404, "missing", {}, None), {"subdomain": "synthetic"}]
        opener = Mock()
        opener.open.side_effect = HTTPError("https://caller.synthetic.invalid", 403, "refused", Message(),
                                           io.BytesIO(b"error code: 1020\n"))
        with patch.object(experiment, "Provider", return_value=provider), \
             patch.object(experiment, "build_opener", return_value=opener), \
             patch.object(experiment, "write_receipt") as write, \
             patch.dict(experiment.os.environ, {"GITHUB_SHA": "b" * 40, "GITHUB_RUN_ID": "123"}), redirect_stdout(io.StringIO()):
            experiment.diagnose_endpoint()
            self.assertTrue(write.call_args.args[0]["scripts_absent"])
            self.assertEqual(write.call_args.args[0]["response"]["provider_error_code"], 1020)
        self.assertEqual([call.args[0] for call in provider.request.call_args_list], ["GET"] * 3)
        self.assertEqual(opener.open.call_args.args[0].get_method(), "GET")
        self.assertNotIn("Authorization", opener.open.call_args.args[0].headers)
        provider.request.side_effect = None
        provider.request.return_value = {}
        opener.open.reset_mock()
        with patch.object(experiment, "Provider", return_value=provider), patch.object(experiment, "build_opener", return_value=opener):
            with self.assertRaises(ValueError): experiment.diagnose_endpoint()
        opener.open.assert_not_called()

    def test_client_signature_diagnostic_changes_only_one_public_header(self):
        """The fixed variant stays credential-free and cannot invoke an existing pair."""
        for client_signature in (False, True):
            provider = Mock(account="a" * 32)
            provider.script.side_effect = lambda name: "/scripts/" + name + "/settings"
            provider.request.side_effect = [HTTPError("https://api.synthetic.invalid", 404, "missing", {}, None),
                HTTPError("https://api.synthetic.invalid", 404, "missing", {}, None), {"subdomain": "synthetic"}]
            opener = Mock()
            opener.open.side_effect = HTTPError("https://caller.synthetic.invalid", 404, "missing", Message(), io.BytesIO(b""))
            with patch.object(experiment, "Provider", return_value=provider), \
                 patch.object(experiment, "build_opener", return_value=opener), \
                 patch.object(experiment, "write_receipt") as write, \
                 patch.dict(experiment.os.environ, {"GITHUB_SHA": "b" * 40, "GITHUB_RUN_ID": "123"}), redirect_stdout(io.StringIO()):
                experiment.diagnose_endpoint(client_signature=client_signature)
            request = opener.open.call_args.args[0]
            self.assertEqual(request.header_items(), [("User-agent", experiment.CLIENT_USER_AGENT)] if client_signature else [])
            self.assertEqual(request.get_method(), "GET")
            self.assertIsNone(request.data)
            opener.open.assert_called_once()
            self.assertEqual(write.call_args.args[0]["client_profile"],
                             experiment.CLIENT_PROFILE if client_signature else "python_urllib_default")
            self.assertEqual([call.args[0] for call in provider.request.call_args_list], ["GET"] * 3)
            provider.request.side_effect = None
            provider.request.return_value = {}
            opener.open.reset_mock()
            with patch.object(experiment, "Provider", return_value=provider), patch.object(experiment, "build_opener", return_value=opener):
                with self.assertRaises(ValueError): experiment.diagnose_endpoint(client_signature=client_signature)
            opener.open.assert_not_called()

    def test_client_signature_diagnostic_refuses_failed_provider_read(self):
        """A denied or failed read never becomes absence, including the new profile."""
        provider = Mock()
        provider.request.side_effect = HTTPError("https://api.synthetic.invalid", 403, "denied", {}, None)
        opener = Mock()
        with patch.object(experiment, "Provider", return_value=provider), patch.object(experiment, "build_opener", return_value=opener):
            with self.assertRaises(HTTPError): experiment.diagnose_endpoint(client_signature=True)
        opener.open.assert_not_called()

    def test_client_signature_operation_requires_its_own_confirmation(self):
        """An endpoint diagnosis cannot accidentally admit deployment or a live trigger."""
        context = {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main", "GITHUB_RUN_ATTEMPT": "1",
                   "CANARY_CONFIRM": "DIAGNOSE_NATIVE_TRACING_CLIENT_SIGNATURE"}
        with patch.dict(experiment.os.environ, context), patch.object(experiment, "diagnose_endpoint") as diagnose:
            with patch.object(experiment.sys, "argv", ["canary", "diagnose-client-signature"]):
                experiment.main()
            diagnose.assert_called_once_with(client_signature=True)
            for operation in ("deploy", "trigger", "collect", "cleanup", "diagnose"):
                with patch.object(experiment.sys, "argv", ["canary", operation]):
                    with self.assertRaises(SystemExit): experiment.main()

    def _trigger_case(self, kind):
        """Hosted transport fixture: never open a network socket or write outside the repo."""
        report = {"available": kind != "unsupported", "sampled": True,
                  "stage": "complete" if kind != "unsupported" else "getter",
                  "case": {"run": NONCE, "mode": "baseline", "kind": "success"}}
        rows = []
        for mode in ("baseline", "redacted"):
            for case_kind in ("success", "failure"):
                row_report = deepcopy(report)
                row_report["case"].update(mode=mode, kind=case_kind)
                rows.append({"status": 200 if case_kind == "success" else 500, "report": row_report})
        if kind == "duplicate":
            rows[-1] = deepcopy(rows[0])
        if kind == "unknown":
            rows[0]["report"]["case"]["mode"] = "unknown"
        headers = Message(); headers["Content-Type"] = "application/json"
        body = b"not-json" if kind == "invalid_json" else json.dumps({"receipts": rows}).encode()
        response = io.BytesIO(body)
        response.code = response.status = 200
        response.headers = headers
        opener = Mock()
        if kind == "http_error":
            opener.open.side_effect = HTTPError("https://caller.synthetic.invalid", 403,
                                                "SYNTHETIC_PRIVATE_ERROR_PROSE", headers, io.BytesIO(b"Forbidden"))
        else:
            opener.open.return_value = response
        writes = []
        receipt = Mock()
        receipt.read_text.return_value = json.dumps({"url": "https://caller.synthetic.invalid", "probe_id": NONCE})
        with patch.object(experiment, "RECEIPT", receipt), patch.object(experiment, "build_opener", return_value=opener), \
             patch.object(experiment, "write_receipt", side_effect=lambda value: writes.append(deepcopy(value))), \
             patch.object(experiment.time, "time", return_value=1_790_000_000), redirect_stdout(io.StringIO()):
            if kind == "success":
                experiment.trigger()
            else:
                with self.assertRaises(ValueError): experiment.trigger()
        opener.open.assert_called_once()
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.data, b"")
        self.assertEqual(request.header_items(), [("User-agent", experiment.CLIENT_USER_AGENT)])
        final = writes[-1]
        self.assertEqual(final["client_profile"], experiment.CLIENT_PROFILE)
        self.assertEqual(final["to"] - final["from"], 4000)
        self.assertEqual(final["trigger"]["http_status"], 403 if kind == "http_error" else 200)
        self.assertNotIn("SYNTHETIC_PRIVATE_ERROR_PROSE", str(final))
        if kind in ("success", "unsupported"):
            self.assertEqual(final["receipts"], rows)

    def test_trigger_http_failure_persists_boundary_without_retry(self):
        self._trigger_case("http_error")

    def test_trigger_invalid_json_persists_boundary_without_retry(self):
        self._trigger_case("invalid_json")

    def test_trigger_unavailable_native_reports_survive_rejection(self):
        self._trigger_case("unsupported")

    def test_trigger_success_persists_reports_and_window(self):
        self._trigger_case("success")

    def test_trigger_refuses_duplicate_case_receipts(self):
        self._trigger_case("duplicate")

    def test_trigger_refuses_unknown_case_receipts(self):
        self._trigger_case("unknown")

    def test_each_case_has_one_child_and_its_own_same_trace_parent(self):
        """Global counts cannot substitute for per-invocation native causal evidence."""
        cases = {}
        for mode in ("baseline", "redacted"):
            for kind in ("success", "failure"):
                key = mode + "." + kind
                cases[key] = {"spans": [{"spanId": key + ".root", "traceId": key + ".trace"},
                    {"spanId": key + ".child", "parentSpanId": key + ".root", "traceId": key + ".trace",
                     "spanName": "amail.canary.operation"}]}
        summary = {"cases": cases}
        experiment.verify_case_parentage(summary)
        for broken in ("missing_child", "duplicate_child", "foreign_parent", "wrong_trace", "missing_trace", "self_parent"):
            value = deepcopy(summary)
            spans = value["cases"]["baseline.success"]["spans"]
            if broken == "missing_child":
                spans.pop()
            elif broken == "duplicate_child":
                spans.append(deepcopy(spans[1]))
            elif broken == "foreign_parent":
                spans[1]["parentSpanId"] = "redacted.success.root"
            elif broken == "wrong_trace":
                spans[1]["traceId"] = "wrong"
            elif broken == "missing_trace":
                spans[1].pop("traceId")
            else:
                spans[1]["parentSpanId"] = spans[1]["spanId"]
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                experiment.verify_case_parentage(value)
        value = deepcopy(summary)
        value["cases"]["unknown.success"] = value["cases"].pop("baseline.success")
        with self.assertRaises(ValueError): experiment.verify_case_parentage(value)

    def test_workflow_never_builds_or_injects_mail_capabilities(self):
        source=(ROOT/".github/workflows/native-tracing-canary.yml").read_text()
        for forbidden in ("worker-build --release","cargo install","INGRESS_SECRET","OPENROUTER_API_KEY","CF_EMAIL_ROUTING_TOKEN"):
            self.assertNotIn(forbidden,source)
        self.assertIn("validated_worker_build.py restore",source)
        self.assertLess(source.index("python -m unittest discover -s infra/tests -v"),
                        source.index("validated_worker_build.py prepare"))
        self.assertLess(source.index("validated_worker_build.py restore"),
                        source.index("${{ secrets.CLOUDFLARE_API_TOKEN }}"))
        self.assertIn("cancel-in-progress: false",source)
        self.assertIn("if: always()",source)
        self.assertIn("native_tracing_experiment.py cleanup",source)
        self.assertIn("github.run_attempt == 1",source)
        diagnostic = source.split("\n  diagnose:", 1)[1]
        self.assertIn("DIAGNOSE_NATIVE_TRACING_ENDPOINT", diagnostic)
        self.assertIn("DIAGNOSE_NATIVE_TRACING_CLIENT_SIGNATURE", diagnostic)
        self.assertIn("native_tracing_experiment.py diagnose-client-signature", diagnostic)
        self.assertIn("native_tracing_experiment.py diagnose", diagnostic)
        for forbidden in ("native_tracing_experiment.py deploy", "native_tracing_experiment.py trigger",
                          "worker_artifact.py restore", "wrangler", "cargo"):
            self.assertNotIn(forbidden, diagnostic)


if __name__ == "__main__":unittest.main()
