"""Hosted-only conservative path selection; no GitHub/provider or local test runs."""

import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "infra/ci"))
import pr_scope as scope


class PrScopeTests(unittest.TestCase):
    """Skip only proven unrelated compilation; release and unknown inputs stay full."""

    def test_component_consumers(self):
        """Selected Rust/Wasm/Astro consumers match their checked-in source inputs."""
        for path, component in (("crates/amail/src/main.rs","cli"),
                                ("crates/mail-worker/entry/api.mjs","worker"),
                                ("crates/trace-schema/src/lib.rs","worker"),
                                ("workers/trace-sink/src/lib.rs","worker"),
                                ("infra/tests/worker-boundary/mail-entry-split.test.mjs","worker"),
                                ("site/src/pages/manual.astro","site")):
            with self.subTest(path=path):
                self.assertEqual(scope.select([path]), {name:name==component for name in scope.COMPONENTS})

    def test_python_only_and_document_changes_do_not_compile(self):
        """Infrastructure still runs independently while unrelated builds may be skipped."""
        self.assertEqual(scope.select(["infra/tests/staging_mail_e2e.py", "infra/deploy/mail_schema_contract.py",
                                       "docs/notes.md", ".agents/skills/amail/SKILL.md"]),
                         dict.fromkeys(scope.COMPONENTS,False))

    def test_unknown_shared_workflow_and_selector_changes_are_full(self):
        """No new dependency surface can be silently omitted."""
        for path in ("Cargo.lock","Cargo.toml","rust-toolchain.toml",".cargo/config.toml",
                     ".github/workflows/ci.yml","crates/new-shared/src/lib.rs","docs/new-fixture.json",
                     "infra/ci/pr_scope.py","infra/tests/workflow_source.py","unknown"):
            with self.subTest(path=path):
                self.assertEqual(scope.select([path]),dict.fromkeys(scope.COMPONENTS,True))

    def test_union_is_not_last_component_wins(self):
        """A mixed change runs every actual consumer."""
        self.assertEqual(scope.select(["crates/amail/src/main.rs","site/src/layout.astro"]),
                         {"cli":True,"worker":False,"site":True})

    def test_exact_diagnostic_consumers_keep_source_checks(self):
        """Only audited non-build consumers skip PR compilation, not their contracts."""
        diagnostics = {".github/workflows/native-fixture.yml",
                       ".github/workflows/native-tracing-canary.yml",
                       "infra/ci/native_fixture.py"}
        for path in diagnostics:
            with self.subTest(path=path):
                self.assertEqual(scope.select([path]), dict.fromkeys(scope.COMPONENTS, False))
        # Reproduce PR 57's exact dependency shape: orchestration + its synthetic
        # tests/docs does not change any of the seven compiled module products.
        self.assertEqual(scope.select([".github/workflows/native-tracing-canary.yml",
                                       "infra/deploy/native_tracing_experiment.py",
                                       "infra/tests/test_native_tracing_experiment.py",
                                       "docs/native-cloudflare-tracing-canary.md"]),
                         dict.fromkeys(scope.COMPONENTS, False))
        from workflow_source import job_block
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        mandatory = job_block(source, "dns")
        self.assertNotIn("needs.changes", mandatory)
        self.assertIn("unittest discover -s infra/tests -v", mandatory)
        syntax = (ROOT / ".github/workflows/workflow-lint.yml").read_text(encoding="utf-8")
        self.assertIn("pull_request:", syntax)
        self.assertIn("python infra/workflow_lint/check.py", syntax)
        self.assertNotIn("paths-ignore", syntax)

    def test_diagnostic_exemptions_do_not_hide_real_consumers(self):
        """Mixed edits union consumers; nearby unknown/admission/build paths fail full."""
        diagnostic = ".github/workflows/native-tracing-canary.yml"
        for path in ("Cargo.lock", "rust-toolchain.toml", ".github/workflows/ci.yml",
                     ".github/workflows/release.yml", ".github/workflows/deploy-identity-test-inbox.yml",
                     ".github/workflows/native-new.yml", "infra/ci/pr_scope.py",
                     "infra/ci/validated_worker_build.py", "infra/ci/worker_artifact.py",
                     "infra/ci/native_suite.py", "infra/ci/cache_event.py", "infra/ci/new.py",
                     "infra/tests/workflow_source.py"):
            with self.subTest(path=path):
                self.assertEqual(scope.select([diagnostic, path]), dict.fromkeys(scope.COMPONENTS, True))
        for path in ("workers/native-trace-canary/src/lib.rs",
                     "workers/native-trace-canary/wrangler.toml",
                     "infra/tests/worker-boundary/native-trace-canary.test.mjs",
                     "infra/tests/worker-boundary/package.json",
                     "infra/tests/worker-boundary/pnpm-lock.yaml"):
            with self.subTest(path=path):
                self.assertEqual(scope.select([diagnostic, path]),
                                 {"cli": False, "worker": True, "site": False})
        self.assertEqual(scope.select([diagnostic, "crates/amail/src/main.rs", "site/src/pages/index.astro"]),
                         {"cli": True, "worker": False, "site": True})

    def test_exact_deployment_validator_is_not_a_compilation_input(self):
        """Only the audited file skips compilation; nearby inputs and mixed edits do not."""
        path = "crates/mail-worker/check_trace_sink_isolation.py"
        self.assertEqual(scope.select([path]), dict.fromkeys(scope.COMPONENTS, False))
        for nearby in ("crates/mail-worker/build.py", "crates/mail-worker/entry/api.mjs",
                       "crates/mail-worker/wrangler.toml", "crates/mail-worker/src/lib.rs"):
            with self.subTest(path=nearby):
                self.assertEqual(scope.select([path, nearby]), {"cli": False, "worker": True, "site": False})
        from workflow_source import job_block
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        mandatory = job_block(source, "dns")
        self.assertNotIn("needs.changes", mandatory)
        self.assertIn("unittest discover -s infra/tests", mandatory)
        self.assertIn("test_check_observability.py", mandatory)

    def test_non_pr_is_full_and_never_reads_event(self):
        """Push/main/manual/release use full source checks regardless of changed paths."""
        for event in ("push","workflow_dispatch","release",""):
            with patch.dict(scope.os.environ,{"GITHUB_EVENT_NAME":event},clear=True), patch.object(scope.subprocess,"run") as git:
                self.assertEqual(scope.current_scope(),dict.fromkeys(scope.COMPONENTS,True))
                git.assert_not_called()

    def test_complete_diff_and_failure_fallback(self):
        """Failed, oversized, malformed or missing metadata cannot request skips."""
        event=json.dumps({"pull_request":{"base":{"sha":"a"*40},"head":{"sha":"b"*40}}})
        with patch.dict(scope.os.environ,{"GITHUB_EVENT_NAME":"pull_request","GITHUB_EVENT_PATH":"mock"},clear=True), \
                patch.object(scope.Path,"read_text",return_value=event), patch.object(scope.subprocess,"run") as git:
            git.return_value=Mock(returncode=0,stdout=b"infra/tests/fixture.py\0")
            self.assertEqual(scope.current_scope(),dict.fromkeys(scope.COMPONENTS,False))
            self.assertEqual(git.call_args.args[0], ["git","diff","--name-only","-z","a"*40,"b"*40,"--"])
            for result in (Mock(returncode=1,stdout=b""), Mock(returncode=0,stdout=b"truncated"),
                           Mock(returncode=0,stdout=b"\xff\0")):
                git.return_value=result
                self.assertEqual(scope.current_scope(),dict.fromkeys(scope.COMPONENTS,True))
        with patch.dict(scope.os.environ,{"GITHUB_EVENT_NAME":"pull_request"},clear=True):
            self.assertEqual(scope.current_scope(),dict.fromkeys(scope.COMPONENTS,True))

    def test_workflow_keeps_infrastructure_full_and_manual_protected(self):
        """Selection changes only PR compilation guards, not dispatch or credentials."""
        from workflow_source import job_block
        source=(ROOT/".github/workflows/ci.yml").read_text(encoding="utf-8")
        for name in scope.COMPONENTS:
            block=job_block(source,name)
            self.assertIn("needs: [changes, worker-build, worker-native]" if name == "worker" else "needs: changes", block)
            self.assertIn("github.event_name == 'push' ||",block)
            self.assertIn("needs.changes.outputs."+name+" == 'true'",block)
            self.assertIn("inputs.target == 'checks'",block)
        self.assertNotIn("needs.changes",job_block(source,"dns"))
        self.assertNotIn("secrets.",job_block(source,"changes"))
        self.assertNotIn("environment:",job_block(source,"changes"))


if __name__ == "__main__":
    unittest.main()
