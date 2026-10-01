"""Infrastructure canary capability/configuration contracts, hosted only."""

from pathlib import Path
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[2]
CANARY = ROOT / "workers/native-trace-canary"


class NativeTraceCanaryTests(unittest.TestCase):
    """A platform probe is not a disguised mailbox campaign or public traced endpoint."""

    def test_traced_probe_is_private_and_caller_has_no_observability(self):
        config = tomllib.loads((CANARY / "wrangler.toml").read_text())
        self.assertFalse(config["workers_dev"])
        self.assertFalse(config["preview_urls"])
        self.assertNotIn("routes", config)
        self.assertTrue(config["observability"]["traces"]["enabled"])
        caller = config["env"]["caller"]
        self.assertFalse(caller["observability"]["enabled"])
        self.assertFalse(caller["observability"]["logs"]["enabled"])
        self.assertFalse(caller["observability"]["traces"]["enabled"])
        self.assertEqual(caller["services"], [{"binding": "PROBE", "service": config["name"]}])
        for scope in [config, caller]:
            for forbidden in ("d1_databases", "r2_buckets", "queues", "send_email", "durable_objects", "kv_namespaces"):
                self.assertNotIn(forbidden, scope)

    def test_source_build_once_and_artifact_owns_the_canary(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("cargo test -p amail-native-trace-canary --locked --all-targets", workflow)
        self.assertIn("cargo check -p amail-native-trace-canary --locked --target wasm32-unknown-unknown", workflow)
        self.assertIn("working-directory: workers/native-trace-canary", workflow)
        artifact = (ROOT / "infra/ci/worker_artifact.py").read_text()
        self.assertIn('"workers/native-trace-canary/build"', artifact)
        native = (CANARY / "src/native.rs").read_text()
        self.assertIn('module = "cloudflare:workers"', native)
        self.assertIn('js_namespace = tracing', native)
        self.assertNotIn("console", native)


if __name__ == "__main__":
    unittest.main()
