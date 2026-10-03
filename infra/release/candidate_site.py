"""Prepare and verify a non-indexable fixed-realm candidate, never a release.

Usage (repository root):
    python infra/release/candidate_site.py prepare <40-character-source-sha>
    python infra/release/candidate_site.py smoke .temp/site-smoke <source-sha>
Use --realm staging for the isolated staging site; production remains the default.
Only prepare mutates generated site/dist files; source/public stays unchanged.
"""

import argparse
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[2]
STAGING_HEADERS = "https://amail-staging.moesegfault.dev/*\n  X-Robots-Tag: noindex, nofollow\n"
SERVICE_NOTICE = "这是 v0.1.2 staging 候选版本说明，尚未发布，不表示邮件服务或发送已开放。"
PAGES = {
    "home": ("index.html", "v0.1.2 尚未发布", "v0.1.0 已发布", None),
    "manual": ("manual/index.html", "v0.1.2 尚未开放下载", "v0.1.0 已发布", "用户手册目录"),
    "changelog": ("changelog/index.html", "v0.1.2 仍在验收", "v0.1.0 已正式发布", "更新日志目录"),
}


class Page(HTMLParser):
    """Collect real links, IDs, text and the designated navigation's fragments."""

    def __init__(self, toc_label):
        """Select the route-local TOC rather than any unrelated navigation."""
        super().__init__(convert_charrefs=True)
        self.toc_label = toc_label
        self.hrefs = set()
        self.ids = set()
        self.text = []
        self.toc_links = []
        self.nav_depth = 0
        self.toc_depth = None
        self.toc_count = 0

    def handle_starttag(self, tag, attrs):
        """Read exact attributes; data-href never counts as a navigable link."""
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"])
        if tag == "nav":
            self.nav_depth += 1
            if values.get("aria-label") == self.toc_label:
                self.toc_count += 1
                self.toc_depth = self.nav_depth
        if tag != "a" or not values.get("href"):
            return
        href = values["href"]
        self.hrefs.add(href)
        if self.toc_depth is not None:
            self.toc_links.append(href)

    def handle_endtag(self, tag):
        """Stop collecting fragments at the matching navigation boundary."""
        if tag == "nav":
            if self.nav_depth == self.toc_depth:
                self.toc_depth = None
            self.nav_depth -= 1

    def handle_data(self, data):
        """Collect decoded text so attributes and comments cannot assert status."""
        self.text.append(data)


def revision_headers(revision, realm="production"):
    """Pin public responses to an opaque source revision and prohibit indexing."""
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("candidate revision must be a full lowercase source SHA")
    if realm == "staging":
        # The provider must serve the tested static bytes, not inject its browser
        # analytics runtime. Preserve freshness; this rule never targets production.
        return STAGING_HEADERS + "  Cache-Control: public, max-age=0, must-revalidate, no-transform\n" + f"  X-Amail-Candidate-Revision: {revision}\n"
    if realm != "production":
        raise ValueError("candidate realm must be production or staging")
    return STAGING_HEADERS + (
        "\nhttps://amail.moesegfault.dev/*\n"
        "  X-Robots-Tag: noindex, nofollow\n"
        f"  X-Amail-Candidate-Revision: {revision}\n"
    )


def check_page(route, html):
    """Require route-local candidate status, real navigation and valid TOC links."""
    _, candidate, published, label = PAGES[route]
    page = Page(label)
    page.feed(html)
    text = "".join(page.text)
    if candidate not in text or published in text:
        raise ValueError(f"{route}: candidate status missing or published claim present")
    if SERVICE_NOTICE not in text:
        raise ValueError(f"{route}: candidate service-availability boundary missing")
    if not {"/", "/manual/", "/changelog/"}.issubset(page.hrefs):
        raise ValueError(f"{route}: three-page navigation missing")
    for href in page.hrefs:
        path = urlsplit(href).path
        if re.search(r"/releases/(?:tag|download)/", path):
            raise ValueError(f"{route}: version-specific Release/download link present")
    if route != "home" and "https://github.com/kleedaisuki/moesegfault-amail/releases" not in page.hrefs:
        raise ValueError(f"{route}: generic Releases link missing")
    if label is None:
        return
    if page.toc_count != 1 or not page.toc_links:
        raise ValueError(f"{route}: nonempty route-local TOC missing")
    if any(not href.startswith("#") or unquote(href[1:]) not in page.ids for href in page.toc_links):
        raise ValueError(f"{route}: TOC fragment has no local target")
    if route == "changelog" and "候选记录日期" not in text:
        raise ValueError("changelog: candidate date must not imply publication")
    if route == "changelog" and ("v0.1.2" not in page.ids or "#v0.1.2" not in page.toc_links):
        raise ValueError("changelog: current candidate entry or TOC target missing")
    if route == "manual" and (not all(command in text for command in
            ("amail discover", "amail send-status", "amail events"))
            or "#从小入口探索完整工作流" not in {unquote(href) for href in page.toc_links}):
        raise ValueError("manual: exploration commands or current section anchor missing")


def check_response_headers(route, headers, revision):
    """Verify actual HTTP 200, HTML MIME, noindex/nofollow and exact source pin."""
    blocks = re.split(r"\r?\n\r?\n", headers.strip())
    response = blocks[-1].splitlines()
    if not response or not re.fullmatch(r"HTTP/\S+ 200(?: .*|)", response[0]):
        raise ValueError(f"{route}: exact-route response must be HTTP 200")
    fields = {}
    for line in response[1:]:
        name, separator, value = line.partition(":")
        if separator:
            fields.setdefault(name.lower(), []).append(value.strip())
    robots = ",".join(fields.get("x-robots-tag", [])).lower().split(",")
    if not {"noindex", "nofollow"}.issubset({value.strip() for value in robots}):
        raise ValueError(f"{route}: candidate response must be noindex, nofollow")
    if fields.get("x-amail-candidate-revision") != [revision]:
        raise ValueError(f"{route}: stale or missing candidate source revision")
    if not any(value.lower().split(";")[0] == "text/html" for value in fields.get("content-type", [])):
        raise ValueError(f"{route}: response must be HTML")


def prepare(revision, realm="production"):
    """Add fixed-realm candidate headers after checking a clean generated bundle."""
    expected = revision_headers(revision, realm)
    dist = ROOT / "site" / "dist"
    source = (ROOT / "site" / "public" / "_headers").read_text(encoding="utf-8")
    rules = "\n".join(line for line in source.splitlines() if line.strip() and not line.startswith("#")) + "\n"
    if rules != STAGING_HEADERS:
        raise ValueError("source header rules must remain staging-only")
    if (dist / "_headers").read_text(encoding="utf-8") != source:
        raise ValueError("candidate preparation requires a clean Astro build")
    for route, (path, _, _, _) in PAGES.items():
        check_page(route, (dist / path).read_text(encoding="utf-8"))
    (dist / "_headers").write_text(expected, encoding="utf-8")


def smoke(directory, revision, realm="production"):
    """Inspect curl's three fixed-route responses without printing public bodies."""
    revision_headers(revision, realm)
    for route in PAGES:
        check_page(route, (directory / f"{route}.html").read_text(encoding="utf-8"))
        check_response_headers(route, (directory / f"{route}.headers").read_text(encoding="utf-8"), revision)


def main():
    """Expose fixed preparation and verification modes with sanitized failures."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "smoke"))
    parser.add_argument("--realm", choices=("production", "staging"), default="production")
    parser.add_argument("arguments", nargs="+")
    args = parser.parse_args()
    try:
        if args.mode == "prepare" and len(args.arguments) == 1:
            prepare(args.arguments[0], args.realm)
        elif args.mode == "smoke" and len(args.arguments) == 2:
            smoke(Path(args.arguments[0]), args.arguments[1], args.realm)
        else:
            parser.error("prepare requires revision; smoke requires directory and revision")
    except (OSError, UnicodeError, ValueError) as error:
        raise SystemExit(f"candidate_site: {error}") from None
    print(f"candidate_site={args.mode} pages=3 toc=2 state=candidate")


if __name__ == "__main__":
    main()
