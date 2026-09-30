"""Synthetic candidate acceptance regressions; no provider or local build needed."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import candidate_site as site


SHA = "a" * 40


def fixture(route):
    """Create route-local links/status and two real heading-fragment TOCs."""
    _, candidate, _, label = site.PAGES[route]
    toc = f'<nav aria-label="{label}"><a href="#section">Section</a></nav><h2 id="section">Heading</h2>' if label else ""
    date = "候选记录日期" if route == "changelog" else ""
    return (
        f'<a href="/">Home</a><a href="/manual/">Manual</a><a href="/changelog/">Changelog</a>'
        f'<p>{candidate}</p><p>{site.SERVICE_NOTICE}</p>{toc}{date}'
        '<a href="https://github.com/kleedaisuki/moesegfault-amail/releases">Releases</a>'
    )


def headers():
    """Model one actual static-assets response, including the opaque source pin."""
    return f"HTTP/2 200\r\nContent-Type: text/html; charset=utf-8\r\nX-Robots-Tag: noindex, nofollow\r\nX-Amail-Candidate-Revision: {SHA}\r\n\r\n"


class CandidateSiteTests(unittest.TestCase):
    """Check every route independently and test fail-closed header preparation."""

    def test_all_pages(self):
        """Truthful status and real fragment targets pass for all three routes."""
        for route in site.PAGES:
            with self.subTest(route=route):
                site.check_page(route, fixture(route))
                site.check_response_headers(route, headers(), SHA)

    def test_route_local_copy_and_links(self):
        """Other pages cannot hide missing status or a premature download link."""
        for route, (_, candidate, published, _) in site.PAGES.items():
            cases = [
                fixture(route).replace(candidate, "missing"),
                fixture(route).replace(site.SERVICE_NOTICE, "missing"),
                fixture(route) + published,
                fixture(route).replace('href="/manual/"', 'data-href="/manual/"'),
                fixture(route) + '<a href="https://github.com/kleedaisuki/moesegfault-amail/releases/tag/v0.1.0">Tag</a>',
                fixture(route) + '<a href="https://github.com/kleedaisuki/moesegfault-amail/releases/download/v0.1.0/amail.zip">Download</a>',
            ]
            for html in cases:
                with self.subTest(route=route):
                    with self.assertRaises(ValueError):
                        site.check_page(route, html)

    def test_toc_and_candidate_date(self):
        """A label without links or links without targets is not a working TOC."""
        for route in ("manual", "changelog"):
            for html in (
                fixture(route).replace('href="#section"', 'href="#missing"'),
                fixture(route).replace('href="#section"', 'data-href="#section"'),
                fixture(route).replace('id="section"', 'id="missing"'),
            ):
                with self.assertRaises(ValueError):
                    site.check_page(route, html)
        with self.assertRaises(ValueError):
            site.check_page("changelog", fixture("changelog").replace("候选记录日期", "Release"))

    def test_live_headers_fail_closed(self):
        """Redirects, indexability, wrong content types and stale source all fail."""
        for route in site.PAGES:
            for response in (
                headers().replace("200", "302", 1),
                headers().replace("noindex, nofollow", "index, follow"),
                headers().replace("noindex, nofollow", "noindex"),
                headers().replace(SHA, "b" * 40),
                headers().replace("text/html", "application/json"),
            ):
                with self.assertRaises(ValueError):
                    site.check_response_headers(route, response, SHA)
        site.check_response_headers("home", "HTTP/1.1 200 Connection established\r\n\r\n" + headers(), SHA)

    def test_prepare_only_changes_generated_headers(self):
        """Temporary fixture files stay inside the repository's .temp directory."""
        temporary_root = site.ROOT / ".temp"
        temporary_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root) as directory:
            root = Path(directory)
            public = root / "site" / "public"
            dist = root / "site" / "dist"
            public.mkdir(parents=True)
            dist.mkdir(parents=True)
            source = "# Staging only\n" + site.STAGING_HEADERS
            (public / "_headers").write_text(source, encoding="utf-8")
            (dist / "_headers").write_text(source, encoding="utf-8")
            for route, (path, _, _, _) in site.PAGES.items():
                target = dist / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(fixture(route), encoding="utf-8")
            with patch.object(site, "ROOT", root):
                site.prepare(SHA)
                self.assertEqual((public / "_headers").read_text(encoding="utf-8"), source)
                self.assertEqual((dist / "_headers").read_text(encoding="utf-8"), site.revision_headers(SHA))
                with self.assertRaisesRegex(ValueError, "clean Astro build"):
                    site.prepare(SHA)


if __name__ == "__main__":
    unittest.main()
