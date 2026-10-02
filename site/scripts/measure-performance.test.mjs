/** Focused regressions for rendered-route performance measurement and invariants. */
import assert from 'node:assert/strict';
import test from 'node:test';
import { gzipSync } from 'node:zlib';
import { measurePage, checkLoadingContract } from './measure-performance.mjs';

test('counts unique linked styles, inline CSS and actual UTF-8 bytes', () => {
  const css = Buffer.from('body { color: red; }');
  const html = `<link href='/base.css' rel='stylesheet'><link rel="stylesheet" href="/base.css">
    <link rel="icon" href="/icon.svg"><style>h1{color:blue}</style>中文`;
  const page = measurePage(html, (path) => {
    assert.equal(path, '/base.css');
    return css;
  });
  assert.equal(page.stylesheetRequests, 1);
  assert.equal(page.externalCssBytes, css.length);
  assert.equal(page.externalCssGzipBytes, gzipSync(css).length);
  assert.equal(page.inlineCssBytes, Buffer.byteLength('h1{color:blue}'));
  assert.equal(page.htmlBytes, Buffer.byteLength(html));
  assert.equal(page.scriptElements, 0);
});

test('rejects external styles rather than silently excluding their loading cost', () => {
  for (const href of ['https://other.test/style.css', '//other.test/style.css', '/../style.css']) {
    assert.throws(() => measurePage(`<link rel="stylesheet" href="${href}">`, () => Buffer.alloc(0)));
  }
});

test('homepage keeps components while guide routes omit them', () => {
  const base = { scriptElements: 0, styles: [] };
  const home = { ...base, styles: [{ path: '/vendor/moesegfault-style/v0.1.2/css/components.css' }] };
  assert.doesNotThrow(() => checkLoadingContract('/', home));
  for (const route of ['/manual/', '/changelog/']) {
    assert.doesNotThrow(() => checkLoadingContract(route, base));
    assert.throws(() => checkLoadingContract(route, home));
  }
  assert.throws(() => checkLoadingContract('/', base));
  assert.throws(() => checkLoadingContract('/manual/', { ...base, scriptElements: 1 }));
});
