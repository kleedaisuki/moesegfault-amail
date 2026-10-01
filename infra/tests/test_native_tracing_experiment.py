"""Hosted synthetic canary lifecycle/collection tests; never contact a provider."""

from pathlib import Path
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from urllib.error import HTTPError
from unittest.mock import Mock, patch
from email.message import Message
from types import SimpleNamespace
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import native_tracing_experiment as experiment

NONCE="a"*32


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
