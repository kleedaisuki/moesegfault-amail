/** Regression tests for route-local release-state acceptance. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { checkReleaseState } from './check-release-state.mjs';

const tagUrl = 'https://github.com/kleedaisuki/moesegfault-amail/releases/tag/v0.1.0';
const releasesUrl = 'https://github.com/kleedaisuki/moesegfault-amail/releases';
const headers = readFileSync(new URL('../public/_headers', import.meta.url), 'utf8');
const claims = {
  index: ['v0.1.0 尚未发布', 'v0.1.0 已发布'],
  'manual/index': ['v0.1.0 尚未开放下载', 'v0.1.0 已发布'],
  'changelog/index': ['v0.1.0 仍在验收', 'v0.1.0 已正式发布'],
};

/** Build minimal rendered-page fixtures, including each page's release link. */
function fixture(state) {
  return Object.fromEntries(Object.entries(claims).map(([path, [candidate, published]]) => [
    path,
    `<a href="/manual/">Manual</a><a href="/changelog/">Changelog</a>
     ${path === 'manual/index' ? '<nav aria-label="用户手册目录"></nav>' : ''}
     ${path === 'changelog/index' ? '<nav aria-label="更新日志目录"></nav>' : ''}
     <p>${state === 'candidate' ? candidate : published}</p>
     ${state === 'published' || path !== 'index' ? `<a href="${state === 'published' ? tagUrl : releasesUrl}">Release</a>` : ''}`,
  ]));
}

for (const state of ['candidate', 'published']) {
  test(`${state} pages pass independently`, () => {
    assert.doesNotThrow(() => checkReleaseState(state, fixture(state), headers));
  });

  for (const path of Object.keys(claims)) {
    test(`${state} ${path}: missing status fails even when other pages have it`, () => {
      const pages = fixture(state);
      pages[path] = pages[path].replace(claims[path][state === 'candidate' ? 0 : 1], 'status removed');
      assert.throws(() => checkReleaseState(state, pages, headers), /incorrect .* release copy/);
    });

    test(`${state} ${path}: wrong link fails`, () => {
      const pages = fixture(state);
      if (state === 'published') {
        pages[path] = pages[path].replace(`href="${tagUrl}"`, `href="${tagUrl}-wrong"`);
        assert.throws(() => checkReleaseState(state, pages, headers), /exact v0.1.0 Release link/);
      } else if (path === 'index') {
        pages[path] += `<a href="${tagUrl}">premature</a>`;
        assert.throws(() => checkReleaseState(state, pages, headers), /unpublished v0.1.0 Release link/);
      } else {
        pages[path] = pages[path].replace(`href="${releasesUrl}"`, `href="${releasesUrl}/wrong"`);
        assert.throws(() => checkReleaseState(state, pages, headers), /generic candidate Releases link/);
      }
    });

    if (state === 'published' || path !== 'index') {
      test(`${state} ${path}: data-href cannot substitute for href`, () => {
        const pages = fixture(state);
        const url = state === 'published' ? tagUrl : releasesUrl;
        pages[path] = pages[path].replace(`href="${url}"`, `data-href="${url}"`);
        assert.throws(() => checkReleaseState(state, pages, headers), /Release link is missing/);
      });
    }
  }
}

test('published HTML noindex fails on any page', () => {
  for (const path of Object.keys(claims)) {
    const pages = fixture('published');
    pages[path] += '<meta name="robots" content="noindex">';
    assert.throws(() => checkReleaseState('published', pages, headers), /HTML noindex/);
  }
});

test('staging-only noindex header rule cannot expand to production', () => {
  assert.throws(() => checkReleaseState('published', fixture('published'), headers.replace('amail-staging', 'amail')), /staging-only noindex/);
});
