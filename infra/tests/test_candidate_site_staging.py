"""Fixed-realm candidate source headers and current-version live smoke fixtures."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/release"))
import candidate_site as site

SHA = "a" * 40


class StagingSiteTests(unittest.TestCase):
    """Old copy or wrong revision cannot be accepted as the current staging site."""

    def page(self, route: str) -> str:
        """Render a minimal public-only candidate page with true links and IDs."""
        _, candidate, _, label = site.PAGES[route]
        links = '<a href="/">Home</a><a href="/manual/">Manual</a><a href="/changelog/">Changelog</a>'
        if label is not None:
            links += '<a href="https://github.com/kleedaisuki/moesegfault-amail/releases">Releases</a>'
            links += f'<nav aria-label="{label}"><a href="#从小入口探索完整工作流">Workflow</a></nav><h2 id="从小入口探索完整工作流">Workflow</h2>'
            if route == "changelog":
                links = links.replace('</nav>', '<a href="#v0.2.0">v0.2.0</a></nav>')
                links += '<h2 id="v0.2.0">v0.2.0</h2>'
        return links + f'<p>{candidate}</p><p>{site.SERVICE_NOTICE}</p>' + (
            '<pre>amail discover\namail send-status\namail events</pre>' if route == "manual" else
            '<p>候选记录日期</p>' if route == "changelog" else '')

    def test_staging_revision_headers_never_add_production_rules(self):
        """Only generated staging assets receive the source pin; default stays production."""
        staging = site.revision_headers(SHA, "staging")
        self.assertIn(f"X-Amail-Candidate-Revision: {SHA}", staging)
        self.assertNotIn("https://amail.moesegfault.dev", staging)
        self.assertIn("https://amail.moesegfault.dev", site.revision_headers(SHA))
        self.assertIn("Cache-Control: public, max-age=0, must-revalidate, no-transform", staging)
        self.assertNotIn("no-transform", site.revision_headers(SHA))

    def test_current_candidate_routes_and_manual_exploration_pass(self):
        """Check real navigation and the candidate section in all three routes."""
        for route in site.PAGES:
            site.check_page(route, self.page(route))

    def test_old_copy_or_missing_discovery_is_not_current_acceptance(self):
        """HTTP 200 cannot mask a stale v0.1.0 candidate or incomplete manual."""
        with self.assertRaises(ValueError):
            site.check_page("home", self.page("home").replace("v0.2.0 尚未发布", "v0.1.0 尚未发布"))
        with self.assertRaises(ValueError):
            site.check_page("manual", self.page("manual").replace("amail discover", "removed"))

    def test_live_headers_reject_wrong_or_missing_revision(self):
        """Actual response status, MIME and source pin supplement content checks."""
        header = f"HTTP/2 200\nContent-Type: text/html; charset=utf-8\nX-Robots-Tag: noindex, nofollow\nX-Amail-Candidate-Revision: {SHA}\n"
        site.check_response_headers("home", header, SHA)
        for changed in (header.replace(SHA, "b" * 40), header.replace("HTTP/2 200", "HTTP/2 301"),
                        header.replace("noindex, nofollow", "noindex")):
            with self.assertRaises(ValueError):
                site.check_response_headers("home", changed, SHA)


if __name__ == "__main__":
    unittest.main()
