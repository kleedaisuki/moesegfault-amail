"""Regression checks for both production site's inline live-response validators."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
TAG_URL = "https://github.com/kleedaisuki/moesegfault-amail/releases/tag/v0.1.0"
PAGES = {
    "home": ("v0.1.0 已发布", "v0.1.0 尚未发布"),
    "manual": ("v0.1.0 已发布", "v0.1.0 尚未开放下载"),
    "changelog": ("v0.1.0 已正式发布", "v0.1.0 仍在验收"),
}


def smoke_script(workflow: str, step: str) -> str:
    """Extract the named workflow step's literal Bash block without a YAML dependency."""
    lines = (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8").splitlines()
    marker = f"      - name: {step}"
    start = lines.index(marker)
    run = lines.index("        run: |", start)
    body = []
    for line in lines[run + 1 :]:
        if line and not line.startswith("          "):
            break
        body.append(line[10:] if line else "")
    return "\n".join(body).rstrip("\n")


class SiteLiveSmokeSourceTests(unittest.TestCase):
    """Check CI/release parity and fail-closed per-route published-response checks."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.script = smoke_script("ci.yml", "Smoke test published pages")

    def test_both_production_workflows_use_same_single_fetch_contract(self) -> None:
        self.assertEqual(self.script, smoke_script("release.yml", "Smoke test public launch pages"))
        self.assertIn("for route in home manual changelog; do", self.script)
        self.assertEqual(self.script.count("status=$(curl"), 1)
        for flag in ("--retry 6", "--dump-header", "--output", "--write-out '%{http_code}'"):
            self.assertIn(flag, self.script)
        self.assertNotIn("--location", self.script)
        self.assertIn('"https://amail.moesegfault.dev$path"', self.script)
        self.assertIn('if [ "$status" != 200 ]; then', self.script)

    def test_inline_validator_accepts_only_route_local_published_responses(self) -> None:
        validator = self.script.split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as directory:
            root = Path(directory)

            def write_pages() -> None:
                for route, (published, _) in PAGES.items():
                    (root / f"{route}.html").write_text(
                        f'<html><p>{published}</p><a href="{TAG_URL}">Download</a></html>',
                        encoding="utf-8",
                    )
                    (root / f"{route}.headers").write_text(
                        "HTTP/2 200\r\ncontent-type: text/html\r\n", encoding="utf-8"
                    )

            def check(expected: str | None = None) -> None:
                result = subprocess.run(
                    [sys.executable, "-c", validator, str(root)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if expected is None:
                    self.assertEqual(result.returncode, 0, result.stderr)
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(f"::{expected}:", result.stderr)

            write_pages()
            check()
            for route, (published, candidate) in PAGES.items():
                write_pages()
                body = root / f"{route}.html"
                body.write_text(body.read_text(encoding="utf-8").replace(published, candidate), encoding="utf-8")
                check(route)

                write_pages()
                body.write_text(body.read_text(encoding="utf-8").replace("href=", "data-href="), encoding="utf-8")
                check(route)

                write_pages()
                body.write_text(body.read_text(encoding="utf-8") + "<!-- noindex -->", encoding="utf-8")
                check(route)

                write_pages()
                (root / f"{route}.headers").write_text("HTTP/2 200\r\nX-Robots-Tag: noindex, nofollow\r\n", encoding="utf-8")
                check(route)


if __name__ == "__main__":
    unittest.main()
