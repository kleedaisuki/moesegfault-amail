/** Regression tests for route-local release-state acceptance. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { checkReleaseState, checkPublishedRelease } from './check-release-state.mjs';
import { releaseDownloads, releaseTagUrl as tagUrl } from '../src/releaseDownloads.mjs';

const releasesUrl = 'https://github.com/kleedaisuki/moesegfault-amail/releases';
const serviceNotice = '这是 v0.1.2 staging 候选版本说明，尚未发布，不表示邮件服务或发送已开放。';
const headers = readFileSync(new URL('../public/_headers', import.meta.url), 'utf8');
const claims = {
  index: ['v0.1.2 尚未发布', 'v0.1.2 已发布'],
  'manual/index': ['v0.1.2 尚未开放下载', 'v0.1.2 已发布'],
  'changelog/index': ['v0.1.2 仍在验收', 'v0.1.2 已正式发布'],
};

test('live release requires actual publication and all seven exact public assets', () => {
  const release = { tag_name: 'v0.1.2', draft: false, prerelease: false,
    published_at: '2026-10-03T00:00:00Z', html_url: tagUrl,
    assets: releaseDownloads.map((asset) => ({ name: asset.name, browser_download_url: asset.href, size: 1 })) };
  assert.doesNotThrow(() => checkPublishedRelease(release));
  for (const change of [{ draft: true }, { prerelease: true }, { published_at: null },
    { tag_name: 'v0.1.0' }, { assets: release.assets.slice(1) }]) {
    assert.throws(() => checkPublishedRelease({ ...release, ...change }));
  }
});

/** Build minimal rendered-page fixtures, including each page's release link. */
function fixture(state) {
  return Object.fromEntries(Object.entries(claims).map(([path, [candidate, published]]) => [
    path,
    `<a href="/manual/">Manual</a><a href="/changelog/">Changelog</a>
     ${path === 'manual/index' ? '<nav aria-label="用户手册目录"></nav>' : ''}
     ${path === 'changelog/index' ? '<nav aria-label="更新日志目录"></nav>' : ''}
     ${path === 'changelog/index' ? '<h2 id="v0.1.2">v0.1.2</h2><a href="#v0.1.2">v0.1.2</a><h2 id="v0.1.0">v0.1.0</h2><a href="#v0.1.0">v0.1.0</a>' : ''}
     <p>${state === 'candidate' ? candidate : published}</p>
     ${state === 'candidate' ? `<p>${serviceNotice}</p>` : ''}
     ${state === 'published' && path === 'manual/index' ? releaseDownloads.map((asset) => `<a href="${asset.href}">${asset.label}</a>`).join('') : ''}
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
        assert.throws(() => checkReleaseState(state, pages, headers), /exact v0.1.2 Release link/);
      } else if (path === 'index') {
        pages[path] += `<a href="${tagUrl}">premature</a>`;
        assert.throws(() => checkReleaseState(state, pages, headers), /unpublished v0.1.2 Release link/);
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
        assert.throws(() => checkReleaseState(state, pages, headers), /[Rr]elease[s]? link is missing/);
      });
    }
  }
}

test('current and historical changelog records and TOCs are required in both states', () => {
  for (const state of ['candidate', 'published']) {
    for (const version of ['v0.1.2', 'v0.1.0']) {
      for (const marker of [`id="${version}"`, `href="#${version}"`]) {
        const pages = fixture(state);
        pages['changelog/index'] = pages['changelog/index'].replace(marker, 'removed');
        assert.throws(() => checkReleaseState(state, pages, headers), /changelog entry/);
      }
    }
  }
});

test('published current changelog cannot retain staging claims', () => {
  const pages = fixture('published');
  pages['changelog/index'] += '<p>staging 候选</p>';
  assert.throws(() => checkReleaseState('published', pages, headers), /candidate claims/);
});

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

test('candidate service disclaimer is required locally and cannot leak into published output', () => {
  for (const path of Object.keys(claims)) {
    const candidate = fixture('candidate');
    candidate[path] = candidate[path].replace(serviceNotice, 'removed');
    assert.throws(() => checkReleaseState('candidate', candidate, headers), /service-availability boundary/);
    const published = fixture('published');
    published[path] += `<p>${serviceNotice}</p>`;
    assert.throws(() => checkReleaseState('published', published, headers), /service-availability boundary/);
  }
});

test('published manual exposes every CLI, Skill and checksum download', () => {
  assert.equal(releaseDownloads.length, 7);
  for (const asset of releaseDownloads) {
    const pages = fixture('published');
    pages['manual/index'] = pages['manual/index'].replace(`href="${asset.href}"`, 'href="#removed"');
    assert.throws(() => checkReleaseState('published', pages, headers), /published download is missing/);
  }
});

test('candidate pages never expose not-yet-published asset links', () => {
  for (const path of Object.keys(claims)) {
    for (const asset of releaseDownloads) {
      const pages = fixture('candidate');
      pages[path] += `<a href="${asset.href}">premature download</a>`;
      assert.throws(() => checkReleaseState('candidate', pages, headers), /unpublished asset download/);
    }
  }
});
