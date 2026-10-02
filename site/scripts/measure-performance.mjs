/** Report deterministic route loading costs from an existing hosted Astro build.
 * Usage: node scripts/measure-performance.mjs > ../.temp/site-performance.json
 * Gzip sizes are reproducible estimates, not live transfer sizes or paint timings.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { gzipSync } from 'node:zlib';

const componentPath = '/vendor/moesegfault-style/v0.1.2/css/components.css';
const routes = ['/', '/manual/', '/changelog/'];

/** Read static HTML attributes independent of their order or quotation style. */
function attributes(tag) {
  return Object.fromEntries([...tag.matchAll(/\s+([\w:-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g)]
    .map(([, name, double, single, bare]) => [name.toLowerCase(), double ?? single ?? bare ?? '']));
}

/** Count the actual route's CSS, including inline Astro chunks, without a browser. */
export function measurePage(html, readAsset) {
  const links = [...html.matchAll(/<link\b[^>]*>/gi)].map(([tag]) => attributes(tag));
  const paths = [...new Set(links.filter((link) => link.rel?.split(/\s+/).includes('stylesheet'))
    .map((link) => link.href))];
  const styles = paths.map((path) => {
    assert.ok(path?.startsWith('/') && !path.startsWith('//') && !path.includes('..'),
      `Expected a self-hosted build asset: ${path}`);
    const bytes = readAsset(path);
    return { path, bytes: bytes.length, gzipBytes: gzipSync(bytes).length };
  });
  const inlineCss = [...html.matchAll(/<style\b[^>]*>([\s\S]*?)<\/style>/gi)]
    .map(([, css]) => css).join('\n');
  return { htmlBytes: Buffer.byteLength(html), htmlGzipBytes: gzipSync(html).length,
    stylesheetRequests: styles.length, externalCssBytes: styles.reduce((n, style) => n + style.bytes, 0),
    externalCssGzipBytes: styles.reduce((n, style) => n + style.gzipBytes, 0),
    inlineCssBytes: Buffer.byteLength(inlineCss),
    scriptElements: [...html.matchAll(/<script\b/gi)].length, styles };
}

/** Guard the zero-client-runtime guide and explicit component-library opt-in. */
export function checkLoadingContract(route, page) {
  assert.equal(page.scriptElements, 0, `${route}: static guide must not ship client scripts`);
  assert.equal(page.styles.some((style) => style.path === componentPath), route === '/',
    `${route}: component CSS belongs only to the homepage buttons`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const dist = new URL('../dist/', import.meta.url);
  const pages = Object.fromEntries(routes.map((route) => {
    const html = readFileSync(new URL(`${route.slice(1)}index.html`, dist), 'utf8');
    const page = measurePage(html, (path) => readFileSync(new URL(path.slice(1), dist)));
    checkLoadingContract(route, page);
    return [route, page];
  }));
  const omitted = readFileSync(new URL(`../public${componentPath}`, import.meta.url));
  console.log(JSON.stringify({ schemaVersion: 1, source: process.env.GITHUB_SHA ?? null,
    releaseState: process.env.AMAIL_RELEASE_STATE ?? 'candidate',
    method: 'built-assets; gzip defaults; no browser/network timing claim', pages,
    manualAndChangelogRemovedPerColdLoad: { stylesheetRequests: 1,
      cssBytes: omitted.length, cssGzipBytes: gzipSync(omitted).length } }, null, 2));
}
