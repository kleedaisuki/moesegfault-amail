"""Source contracts separating cancelable checks from shared-state promotion."""

from pathlib import Path
import re
import unittest


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml"


def jobs(source: str) -> dict[str, str]:
    """Extract job blocks without importing a YAML parser or executing a workflow."""
    body = source.split("\njobs:\n", 1)[1]
    starts = list(re.finditer(r"^  ([a-z][a-z0-9-]+):\n", body, re.MULTILINE))
    return {
        item.group(1): body[item.end():starts[index + 1].start() if index + 1 < len(starts) else len(body)]
        for index, item in enumerate(starts)
    }


def condition(block: str) -> str:
    """Return the job predicate, including its folded continuation lines."""
    match = re.search(r"^    if: (.*)(?:\n((?:      .*\n)*))?", block, re.MULTILINE)
    if not match:
        raise ValueError("job predicate missing")
    return match.group(1) + "\n" + (match.group(2) or "")


class IterationContractTests(unittest.TestCase):
    """No optimization can make pushes mutate provider or staging state."""

    @classmethod
    def setUpClass(cls) -> None:
        """Read the source once; all fixtures remain synthetic and non-executing."""
        cls.source = WORKFLOW.read_text(encoding="utf-8")
        cls.blocks = jobs(cls.source)

    def test_check_and_state_lanes_are_distinct(self) -> None:
        """Only obsolete non-mutating checks may be canceled by newer revisions."""
        header = self.source.split("\njobs:\n", 1)[0]
        selector = "github.event_name != 'workflow_dispatch' || inputs.target == 'checks'"
        self.assertIn(f"({selector}) && 'checks-' || ''", header)
        self.assertIn("cancel-in-progress: ${{ " + selector + " }}", header)
        self.assertIn("format('ci-{0}{1}',", header)
        self.assertIn("github.ref)", header)
        self.assertIn("inputs.target == 'production-api-only-maintenance'", header)
        self.assertIn("'amail-production-graph-writer'", header)

    def test_protected_jobs_require_manual_invocation(self) -> None:
        """All staging and production jobs remain unreachable from push or PR."""
        for name, block in self.blocks.items():
            if re.search(r"^    environment: (staging|production)$", block, re.MULTILINE):
                with self.subTest(job=name):
                    guard = condition(block)
                    self.assertIn("github.event_name == 'workflow_dispatch'", guard)
                    self.assertNotIn("github.event_name == 'push'", guard)
                    self.assertNotIn("github.event_name == 'pull_request'", guard)
                    self.assertNotIn("inputs.target == 'checks'", guard)

    def test_checks_keep_full_contracts_without_provider_calls(self) -> None:
        """The new explicit checks target still covers every original source suite."""
        for name in ("cli", "worker", "site", "dns"):
            with self.subTest(job=name):
                self.assertIn("inputs.target == 'checks'", condition(self.blocks[name]))
        provider = condition(self.blocks["provider-live"])
        self.assertIn("github.event_name == 'workflow_dispatch'", provider)
        self.assertNotIn("github.event_name == 'push'", provider)
        self.assertNotIn("inputs.target == 'checks'", provider)
        self.assertIn("RUN_STAGING_TRACE_SINK_ROLLOUT", condition(self.blocks["staging-worker"]))
        self.assertIn("RUN_STAGING_TRACE_SINK_ROLLOUT", condition(self.blocks["staging-trace-sink"]))

    def test_exact_check_caches_cannot_be_saved_by_pr_or_promotion(self) -> None:
        """Cache writes occur only after trusted push contracts, never with secrets."""
        worker = self.blocks["worker"]
        self.assertNotIn("restore-keys:", worker)
        self.assertNotIn("secrets.", worker)
        self.assertIn('python infra/ci/worker_cache_key.py >> "$GITHUB_OUTPUT"', worker)
        self.assertIn("rustc --version --verbose; cc --version; ldd --version;", worker)
        self.assertIn("key: worker-check-v2-", worker)
        self.assertIn("steps.worker-cache-key.outputs.cacheable == 'true'", worker)
        self.assertIn('cargo install worker-build --version 0.8.5 --locked --root "$GITHUB_WORKSPACE/.cache/worker-build-check"', worker)
        saves = re.findall(r"      - name: Save trusted .*?(?=\n      - name:|\Z)", worker, re.DOTALL)
        self.assertEqual(len(saves), 2)
        for save in saves:
            self.assertIn("if: github.event_name == 'push'", save)
            self.assertIn("github.ref == 'refs/heads/main'", save)
            self.assertIn("github.ref == 'refs/heads/codex/amail-v0.1.0'", save)
            self.assertIn("uses: actions/cache/save@v4", save)
            self.assertIn("outputs.cache-primary-key", save)
        self.assertLess(worker.index("Run built Rust Worker address-add boundary tests in workerd"), worker.index("Save trusted"))
        for name, block in self.blocks.items():
            if name != "worker":
                with self.subTest(job=name):
                    self.assertNotIn("actions/cache/", block)


if __name__ == "__main__":
    unittest.main()
