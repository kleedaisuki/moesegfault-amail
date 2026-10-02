"""Hosted source contracts for the narrow native documentation push filter.

Fixtures model only the fixed literal/``**`` patterns below, not GitHub's general
glob engine, event delivery, diff truncation, or Actions concurrency behavior.
"""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
IGNORE = ("README.md", "docs/**.md", ".agents/skills/**.md")


def event_block(source: str, event: str) -> str:
    """Read one block-style event without absorbing sibling events or jobs."""
    header = source.split("\npermissions:", 1)[0].split("\non:\n", 1)[1]
    match = re.search(rf"^  {re.escape(event)}:\n?", header, re.MULTILINE)
    if not match:
        raise ValueError("workflow event missing")
    body = header[match.end():]
    stop = re.search(r"^  [a-z_]+:", body, re.MULTILINE)
    return body[:stop.start()] if stop else body


def ignored(path: str) -> bool:
    """Match the exact allowlisted patterns for synthetic changed-path fixtures."""
    return any(
        re.fullmatch(re.escape(pattern).replace(r"\*\*", ".*"), path)
        for pattern in IGNORE
    )


class DocsPushFilterTests(unittest.TestCase):
    """No script, configuration, runtime, or published site content may skip CI."""

    def test_only_documentation_is_ignored_on_both_push_branches(self) -> None:
        """Require the reviewed fixed list rather than a broad Markdown glob."""
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        push = event_block(source, "push")
        self.assertIn("branches: [main, codex/amail-v0.1.0]", push)
        paths = tuple(re.findall(r"^      - '([^']+)'$", push, re.MULTILINE))
        self.assertEqual(paths, IGNORE)
        self.assertEqual(push.count("paths-ignore:"), 1)
        self.assertNotRegex(push, r"(?m)^    (paths|tags|tags-ignore):")

    def test_pr_dispatch_lint_and_release_are_not_path_filtered(self) -> None:
        """Keep PR event delivery and independent manual/tag evidence available."""
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertEqual(event_block(ci, "pull_request").strip(), "")
        self.assertNotIn("paths-ignore:", event_block(ci, "workflow_dispatch"))
        self.assertNotIn("paths:", event_block(ci, "workflow_dispatch"))
        self.assertIn("options: [checks, staging,", event_block(ci, "workflow_dispatch"))
        for name in ("workflow-lint.yml", "release.yml"):
            with self.subTest(workflow=name):
                source = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
                self.assertNotIn("paths-ignore:", source)
                self.assertNotRegex(source, r"(?m)^\s+paths:")
        release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
        self.assertIn("tags: ['v*.*.*']", event_block(release, "push"))
        release_dispatch = event_block(release, "workflow_dispatch")
        self.assertNotIn("paths:", release_dispatch)
        self.assertNotIn("paths-ignore:", release_dispatch)
        self.assertRegex(release_dispatch, r"(?m)^      recover_run_id:\n(?:        .+\n)*        required: false$")

    def test_synthetic_docs_only_and_mixed_changes(self) -> None:
        """One non-documentation path keeps automatic full source checks enabled."""
        docs = ("README.md", "docs/decision.md", "docs/nested/review.md",
                ".agents/skills/amail/SKILL.md",
                ".agents/skills/moesegfault-identity/references/login-failure-support.md")
        for path in docs:
            with self.subTest(path=path):
                self.assertTrue(ignored(path))
        self.assertTrue(all(map(ignored, docs)))
        checked = (".github/workflows/ci.yml", "Cargo.toml", "Cargo.lock",
                   "crates/mail-worker/src/lib.rs", "workers/mail-ingress/wrangler.toml",
                   "infra/tests/test_docs_push_filter_contract.py", "docs/probe.py",
                   "docs/config.toml", "docs/fixture.json", "docs/decision.MD",
                   ".agents/skills/amail/scripts/pack.py",
                   ".agents/skills/moesegfault-identity/agents/openai.yaml",
                   ".agents/settings.yaml", "site/src/content/manual/start.md",
                   "site/src/pages/index.astro", "site/package.json", "crates/amail/README.md")
        for path in checked:
            with self.subTest(path=path):
                self.assertFalse(ignored(path))
                self.assertFalse(all(map(ignored, (*docs, path))))


if __name__ == "__main__":
    unittest.main()
