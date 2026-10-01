"""Hosted synthetic canary lifecycle/collection tests; never contact a provider."""

from pathlib import Path
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

    def test_workflow_never_builds_or_injects_mail_capabilities(self):
        source=(ROOT/".github/workflows/native-tracing-canary.yml").read_text()
        for forbidden in ("worker-build --release","cargo install","INGRESS_SECRET","OPENROUTER_API_KEY","CF_EMAIL_ROUTING_TOKEN"):
            self.assertNotIn(forbidden,source)
        self.assertIn("validated_worker_build.py restore",source)
        self.assertIn("cancel-in-progress: false",source)
        self.assertIn("if: always()",source)
        self.assertIn("native_tracing_experiment.py cleanup",source)
        self.assertIn("github.run_attempt == 1",source)


if __name__ == "__main__":unittest.main()
