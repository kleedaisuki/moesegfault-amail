/** Verify every rendered route has the selected release state and its own links. */
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const tagUrl = 'https://github.com/kleedaisuki/moesegfault-amail/releases/tag/v0.1.0';
const releasesUrl = 'https://github.com/kleedaisuki/moesegfault-amail/releases';
const pages = [
  { path: 'index', label: 'home', candidate: 'v0.1.0 尚未发布', published: 'v0.1.0 已发布' },
  { path: 'manual/index', label: 'manual', candidate: 'v0.1.0 尚未开放下载', published: 'v0.1.0 已发布' },
  { path: 'changelog/index', label: 'changelog', candidate: 'v0.1.0 仍在验收', published: 'v0.1.0 已正式发布' },
];

/** Match an actual anchor destination, not URL text elsewhere in the document. */
function hasHref(html, href) {
  const anchors = html.matchAll(/<a\b((?:[^>"']|"[^"]*"|'[^']*')*)>/g);
  for (const [, attributes] of anchors) {
    const parsed = attributes.matchAll(/\s+([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g);
    for (const [, name, doubleQuoted, singleQuoted, bare] of parsed) {
      if (name === 'href' && (doubleQuoted ?? singleQuoted ?? bare) === href) return true;
    }
  }
  return false;
}

/** Assert source-managed staging noindex never targets the production hostname. */
export function checkHeaders(headers) {
  const rules = headers.split(/\r?\n/).filter((line) => line.trim() && !line.trimStart().startsWith('#'));
  if (rules.length !== 2 || rules[0] !== 'https://amail-staging.moesegfault.dev/*' ||
      rules[1].trim() !== 'X-Robots-Tag: noindex, nofollow') {
    throw new Error('Expected a staging-only noindex header rule');
  }
}

/** Check each route independently so one page cannot mask another's stale copy. */
export function checkReleaseState(state, htmlByPath, headers) {
  if (state !== 'candidate' && state !== 'published') {
    throw new Error('Usage: node scripts/check-release-state.mjs candidate|published');
  }
  checkHeaders(headers);

  for (const page of pages) {
    const html = htmlByPath[page.path];
    if (typeof html !== 'string') throw new Error(`${page.label}: rendered HTML is missing`);
    if (!hasHref(html, '/manual/') || !hasHref(html, '/changelog/')) {
      throw new Error(`${page.label}: required three-page navigation is missing`);
    }
    if (/noindex/i.test(html)) {
      throw new Error(`${page.label}: HTML noindex must be controlled by staging headers only`);
    }
    if (!html.includes(page[state]) || html.includes(page[state === 'candidate' ? 'published' : 'candidate'])) {
      throw new Error(`${page.label}: incorrect ${state} release copy`);
    }
    if (state === 'published' && !hasHref(html, tagUrl)) {
      throw new Error(`${page.label}: exact v0.1.0 Release link is missing`);
    }
    if (state === 'candidate' && hasHref(html, tagUrl)) {
      throw new Error(`${page.label}: unpublished v0.1.0 Release link is present`);
    }
    if (state === 'candidate' && page.path !== 'index' && !hasHref(html, releasesUrl)) {
      throw new Error(`${page.label}: generic candidate Releases link is missing`);
    }
  }
  if (!htmlByPath['manual/index'].includes('aria-label="用户手册目录"') ||
      !htmlByPath['changelog/index'].includes('aria-label="更新日志目录"')) {
    throw new Error('Manual or changelog table of contents is missing');
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const state = process.argv[2];
  if (state !== 'candidate' && state !== 'published') {
    throw new Error('Usage: node scripts/check-release-state.mjs candidate|published');
  }
  const htmlByPath = Object.fromEntries(pages.map(({ path }) => [
    path,
    readFileSync(new URL(`../dist/${path}.html`, import.meta.url), 'utf8'),
  ]));
  checkReleaseState(state, htmlByPath, readFileSync(new URL('../public/_headers', import.meta.url), 'utf8'));
  console.log(`release_site_state=${state} pages=3 toc=2`);
}
