"""Production publication checks use exact links and source pins, not HTTP 200 alone."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/release"))
import published_site as site

SHA = "a" * 40
TAG = "v0.1.2"


class PublishedSiteTests(unittest.TestCase):
    """Minimal fixtures independently exercise each publication boundary."""

    def page(self, route):
        """Create actual anchors, visible status and complete current manual links."""
        _, status, label = site.PAGES[route]
        links = {"/", "/manual/", "/changelog/", f"{site.RELEASES}/tag/{TAG}"}
        if route == "manual":
            links |= {f"{site.RELEASES}/download/{TAG}/{name}" for name in site.expected_names(TAG) | {"SHA256SUMS"}}
        html = "".join(f'<a href="{href}">Link</a>' for href in sorted(links)) + f"<p>{TAG} {status}</p>"
        if label:
            html += f'<nav aria-label="{label}"><a href="#{TAG}">Current</a></nav><h2 id="{TAG}">Current</h2>'
        if route == "manual":
            html += "<pre>amail discover\namail send-status\namail events</pre>"
        return html

    def headers(self):
        """Return the final HTTP response block with strict source and cache headers."""
        return f"HTTP/2 200\nContent-Type: text/html; charset=utf-8\nCache-Control: public, no-transform\nX-Amail-Release-Revision: {SHA}\n"

    def test_complete_published_routes(self):
        """All three routes pass only their own visible and navigational contracts."""
        for route in site.PAGES:
            site.check_page(route, self.page(route), TAG)
            site.check_response_headers(route, self.headers(), SHA)

    def test_stale_candidate_and_script_rejected(self):
        """Attribute lookalikes, old tags, candidate text and injected JS never pass."""
        html = self.page("home")
        for changed in (html.replace(TAG, "v0.1.0"), html.replace("href=", "data-href="),
                        html + "staging 候选版本说明", html + '<script src="beacon.js"></script>',
                        html + '<meta name="robots" content="noindex">'):
            with self.assertRaises(ValueError):
                site.check_page("home", changed, TAG)

    def test_missing_download_and_broken_toc_rejected(self):
        """The manual requires checksums plus six archives and navigable local TOCs."""
        for changed in (self.page("manual").replace("SHA256SUMS", "missing"),
                        self.page("manual").replace(f'id="{TAG}"', 'id="other"')):
            with self.assertRaises(ValueError):
                site.check_page("manual", changed, TAG)

    def test_actual_headers_reject_stale_or_transformed(self):
        """Exact HTTP status, MIME and single source header are mandatory."""
        header = self.headers()
        for changed in (header.replace(SHA, "b" * 40), header.replace("200", "301"),
                        header.replace("text/html", "text/plain"), header.replace("no-transform", "public"),
                        header + "X-Robots-Tag: noindex\n", header + f"X-Amail-Release-Revision: {SHA}\n",
                        header + f"X-Amail-Candidate-Revision: {SHA}\n"):
            with self.assertRaises(ValueError):
                site.check_response_headers("home", changed, SHA)

    def test_prepare_only_generated_headers_and_clean_build(self):
        """Scratch stays inside .temp; source rules remain byte-identical and staging-only."""
        (ROOT / ".temp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as directory:
            root = Path(directory)
            (root / "site/public").mkdir(parents=True)
            (root / "site/dist").mkdir()
            source = "# staging-only\n" + site.STAGING_HEADERS
            (root / "site/public/_headers").write_text(source, encoding="utf-8")
            (root / "site/dist/_headers").write_text(source, encoding="utf-8")
            (root / "site/package.json").write_text('{"version":"0.1.2"}', encoding="utf-8")
            for route, (path, _, _) in site.PAGES.items():
                page = root / "site/dist" / path
                page.parent.mkdir(parents=True, exist_ok=True)
                page.write_text(self.page(route), encoding="utf-8")
            with patch.object(site, "ROOT", root):
                site.prepare(SHA, TAG)
                self.assertEqual((root / "site/public/_headers").read_text(encoding="utf-8"), source)
                with self.assertRaises(ValueError):
                    site.prepare(SHA, TAG)

    def test_unsafe_source_coordinates_rejected(self):
        """Neither arbitrary header text nor an unsafe tag reaches generated output."""
        for revision, tag in (("short", TAG), (SHA, "../../tag")):
            with self.assertRaises(Exception):
                site.revision_headers(revision, tag)


if __name__ == "__main__":
    unittest.main()
