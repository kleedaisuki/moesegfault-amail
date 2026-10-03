"""Prepare source-pinned production assets and verify actual published responses.

Usage from the repository root:
    python infra/release/published_site.py prepare <source-sha> v0.1.2
    python infra/release/published_site.py smoke .temp/site-smoke <source-sha> v0.1.2
Only prepare writes generated site/dist headers; source/public is never changed.
"""

import argparse
import json
from pathlib import Path
import re
from urllib.parse import unquote

from candidate_site import Page, STAGING_HEADERS
from verify_published_assets import AssetError, expected_names


ROOT = Path(__file__).resolve().parents[2]
RELEASES = "https://github.com/kleedaisuki/moesegfault-amail/releases"
PAGES = {
    "home": ("index.html", "已发布", None),
    "manual": ("manual/index.html", "已发布", "用户手册目录"),
    "changelog": ("changelog/index.html", "已正式发布", "更新日志目录"),
}


def revision_headers(revision, tag):
    """Scope freshness and no-transform to the production host, without noindex."""
    expected_names(tag)
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("release revision must be a full lowercase source SHA")
    return STAGING_HEADERS + (
        "\nhttps://amail.moesegfault.dev/*\n"
        "  Cache-Control: public, max-age=0, must-revalidate, no-transform\n"
        f"  X-Amail-Release-Revision: {revision}\n"
    )


def check_page(route, html, tag):
    """Require real current-release links, status, downloads and valid local TOCs."""
    _, status, label = PAGES[route]
    page = Page(label)
    page.feed(html)
    text = "".join(page.text)
    if f"{tag} {status}" not in text or any(value in text for value in
            (f"{tag} 尚未发布", f"{tag} 尚未开放下载", f"{tag} 仍在验收", "staging 候选版本说明")):
        raise ValueError(f"{route}: current published status missing or candidate copy remains")
    if re.search(r"noindex", html, re.I) or re.search(r"<script\b", html, re.I):
        raise ValueError(f"{route}: published page must be indexable and script-free")
    links = {"/", "/manual/", "/changelog/", f"{RELEASES}/tag/{tag}"}
    if not links.issubset(page.hrefs):
        raise ValueError(f"{route}: navigation or exact current Release href missing")
    if label is not None and (page.toc_count != 1 or not page.toc_links or any(
            not href.startswith("#") or unquote(href[1:]) not in page.ids for href in page.toc_links)):
        raise ValueError(f"{route}: nonempty valid route-local TOC missing")
    if route == "changelog" and (tag not in page.ids or f"#{tag}" not in page.toc_links):
        raise ValueError("changelog: current release entry or TOC target missing")
    if route == "manual":
        downloads = {f"{RELEASES}/download/{tag}/{name}" for name in expected_names(tag) | {"SHA256SUMS"}}
        if not downloads.issubset(page.hrefs):
            raise ValueError("manual: all seven exact published asset links are required")
        if not all(command in text for command in ("amail discover", "amail send-status", "amail events")):
            raise ValueError("manual: current agent exploration commands missing")


def check_response_headers(route, headers, revision):
    """Reject redirects, stale pins, indexing restrictions and transformed responses."""
    response = re.split(r"\r?\n\r?\n", headers.strip())[-1].splitlines()
    if not response or not re.fullmatch(r"HTTP/\S+ 200(?: .*|)", response[0]):
        raise ValueError(f"{route}: exact-route response must be HTTP 200")
    fields = {}
    for line in response[1:]:
        name, separator, value = line.partition(":")
        if separator:
            fields.setdefault(name.lower(), []).append(value.strip())
    if fields.get("x-amail-release-revision") != [revision] or "x-amail-candidate-revision" in fields:
        raise ValueError(f"{route}: stale or missing release source revision")
    if any("noindex" in value.lower() for value in fields.get("x-robots-tag", [])):
        raise ValueError(f"{route}: production response must be indexable")
    tokens = {token.strip().lower() for value in fields.get("cache-control", []) for token in value.split(",")}
    if "no-transform" not in tokens:
        raise ValueError(f"{route}: production response must prohibit provider script injection")
    if not any(value.lower().split(";")[0] == "text/html" for value in fields.get("content-type", [])):
        raise ValueError(f"{route}: response must be HTML")


def prepare(revision, tag):
    """Require a clean published build before writing host-specific generated headers."""
    expected = revision_headers(revision, tag)
    if tag != "v" + json.loads((ROOT / "site/package.json").read_text(encoding="utf-8"))["version"]:
        raise ValueError("release tag must match the site's current version")
    dist = ROOT / "site/dist"
    source = (ROOT / "site/public/_headers").read_text(encoding="utf-8")
    rules = "\n".join(line for line in source.splitlines() if line.strip() and not line.startswith("#")) + "\n"
    if rules != STAGING_HEADERS or (dist / "_headers").read_text(encoding="utf-8") != source:
        raise ValueError("published preparation requires staging-only source headers and a clean build")
    for route, (path, _, _) in PAGES.items():
        check_page(route, (dist / path).read_text(encoding="utf-8"), tag)
    (dist / "_headers").write_text(expected, encoding="utf-8")


def smoke(directory, revision, tag):
    """Read one complete three-route GET cycle; never mutate or retry deployment."""
    revision_headers(revision, tag)
    for route in PAGES:
        check_page(route, (directory / f"{route}.html").read_text(encoding="utf-8"), tag)
        check_response_headers(route, (directory / f"{route}.headers").read_text(encoding="utf-8"), revision)


def main():
    """Expose only generated preparation and public response verification."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "smoke"))
    parser.add_argument("arguments", nargs="+")
    args = parser.parse_args()
    try:
        if args.mode == "prepare" and len(args.arguments) == 2:
            prepare(*args.arguments)
        elif args.mode == "smoke" and len(args.arguments) == 3:
            smoke(Path(args.arguments[0]), *args.arguments[1:])
        else:
            parser.error("prepare requires revision/tag; smoke requires directory/revision/tag")
    except (OSError, UnicodeError, ValueError, AssetError) as error:
        raise SystemExit(f"published_site: {error}") from None
    print(f"published_site={args.mode} pages=3 state=published")


if __name__ == "__main__":
    main()
