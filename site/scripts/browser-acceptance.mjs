/** Hosted-only Chromium contract checks; screenshots require human visual review. */
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { releaseDownloads, releaseVersion, releaseTagUrl } from '../src/releaseDownloads.mjs';
import { checkPublishedRelease } from './check-release-state.mjs';

const { chromium } = await import(pathToFileURL(process.env.SITE_BROWSER_MODULE).href);
const base = process.env.SITE_BROWSER_BASE;
const output = process.env.SITE_BROWSER_OUTPUT;
const published = process.env.TARGET === 'live-published';
assert.ok(['http://127.0.0.1:4321', 'https://amail.moesegfault.dev', 'https://amail-staging.moesegfault.dev'].includes(base));
await mkdir(output, { recursive: true });
const report = { source: process.env.EVIDENCE_SHA, target: process.env.TARGET,
  deployedRevision: process.env.CANDIDATE_REVISION || null,
  base, started: new Date().toISOString(), cases: [] };

if (published) {
  assert.equal(base, 'https://amail.moesegfault.dev');
  assert.match(process.env.CANDIDATE_REVISION ?? '', /^[0-9a-f]{40}$/);
  const response = await fetch(`https://api.github.com/repos/kleedaisuki/moesegfault-amail/releases/tags/${releaseVersion}`, {
    headers: { Accept: 'application/vnd.github+json', 'User-Agent': 'amail-site-acceptance',
      ...(process.env.GITHUB_TOKEN ? { Authorization: `Bearer ${process.env.GITHUB_TOKEN}` } : {}) },
    signal: AbortSignal.timeout(15000),
  });
  assert.equal(response.status, 200, 'published GitHub Release must exist');
  const release = await response.json();
  checkPublishedRelease(release);
  report.release = { tag: release.tag_name, publishedAt: release.published_at,
    expectedAssets: releaseDownloads.map((asset) => asset.name) };
}

/** Record independent assertions without hiding later defects after one failure. */
async function check(result, name, fn) {
  try {
    await fn();
    result.checks.push({ name, passed: true });
  } catch (error) {
    result.checks.push({ name, passed: false, error: String(error) });
  }
}

/** Require actual visible focus, not only an element's presence in the DOM. */
async function focusedOutline(page) {
  // Keyboard dispatch can precede :focus-visible style resolution. Wait for
  // the same observable contract, never replace it with a sleep or weaker ring.
  await page.waitForFunction(() => {
    const style = getComputedStyle(document.activeElement);
    return style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) >= 2;
  }, null, { polling: 'raf', timeout: 1000 }).catch(() => {});
  return page.evaluate(() => {
    const el = document.activeElement;
    const style = getComputedStyle(el);
    return { tag: el.tagName, id: el.id, className: el.className,
      focusVisible: el.matches(':focus-visible'), outlineStyle: style.outlineStyle,
      outlineWidth: style.outlineWidth, outlineColor: style.outlineColor,
      passes: style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) >= 2 };
  });
}

/** Check CTA bounds including hidden/scrolling ancestors, without following downloads. */
async function unclipped(locator) {
  await locator.scrollIntoViewIfNeeded();
  assert.ok(await locator.isVisible());
  const issue = await locator.evaluate((el) => {
    const rect = el.getBoundingClientRect();
    if (rect.left < -1 || rect.right > innerWidth + 1) return 'outside viewport';
    const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
    if (!hit || !el.contains(hit)) return 'CTA center obscured or outside viewport';
    for (let parent = el.parentElement; parent; parent = parent.parentElement) {
      const style = getComputedStyle(parent);
      if (!['hidden', 'clip', 'auto', 'scroll'].includes(style.overflowX)) continue;
      const bounds = parent.getBoundingClientRect();
      if (rect.left < bounds.left - 1 || rect.right > bounds.right + 1) return 'ancestor clipping';
    }
    return null;
  });
  assert.equal(issue, null);
}

/** Exercise every generated TOC link and reject targets hidden behind the sticky header. */
async function toc(page, stem, result) {
  const links = page.locator('.toc a');
  assert.ok(await links.count() > 0, 'TOC must not be empty');
  result.tocGeometry = [];
  const failures = [];
  for (let index = 0; index < await links.count(); index++) {
    const link = links.nth(index);
    const href = await link.getAttribute('href');
    assert.ok(href?.startsWith('#'));
    const id = decodeURIComponent(href.slice(1));
    assert.equal(await page.evaluate((value) => document.querySelectorAll('[id]').length > 0 &&
      [...document.querySelectorAll('[id]')].filter((el) => el.id === value).length, id), 1);
    await link.click();
    assert.equal(decodeURIComponent(new URL(page.url()).hash.slice(1)), id);
    const position = await page.evaluate((value) => {
      const heading = document.getElementById(value);
      const target = heading.getBoundingClientRect();
      const header = document.querySelector('.site-header').getBoundingClientRect();
      const ancestors = [];
      for (let parent = heading.parentElement; parent; parent = parent.parentElement) {
        const style = getComputedStyle(parent);
        if (!['auto', 'scroll', 'hidden'].includes(style.overflowY)) continue;
        ancestors.push({ tag: parent.tagName, className: parent.className,
          overflowY: style.overflowY, scrollTop: parent.scrollTop,
          clientHeight: parent.clientHeight, scrollHeight: parent.scrollHeight });
      }
      return { id: value, top: target.top, bottom: target.bottom, header: header.bottom,
        height: innerHeight, margin: getComputedStyle(heading).scrollMarginTop, ancestors };
    }, id);
    result.tocGeometry.push(position);
    if (position.top >= position.header - 1 && position.top < position.height) continue;
    await page.screenshot({ path: `${output}/${stem}-toc-${index}-failure.png` });
    failures.push(`${id}: heading obscured or outside viewport: ${JSON.stringify(position)}`);
  }
  assert.equal(failures.length, 0, failures.join('\n'));
}

/** Preserve table evidence and verify content can be reached in its horizontal scroller. */
async function tables(page, stem) {
  const tables = page.locator('.manual-prose table');
  assert.ok(await tables.count() > 0);
  for (let index = 0; index < await tables.count(); index++) {
    const table = tables.nth(index);
    await table.scrollIntoViewIfNeeded();
    const details = await table.evaluate((el) => {
      const cells = [...el.querySelectorAll('th, td')];
      const small = cells.some((cell) => parseFloat(getComputedStyle(cell).fontSize) < 14);
      let scroller = el.parentElement;
      while (scroller && scroller.scrollWidth <= scroller.clientWidth + 1) scroller = scroller.parentElement;
      if (!scroller) return { small, reachable: true };
      const style = getComputedStyle(scroller);
      if (!['auto', 'scroll'].includes(style.overflowX)) return { small, reachable: false };
      scroller.scrollLeft = scroller.scrollWidth;
      const last = cells.at(-1).getBoundingClientRect();
      const bounds = scroller.getBoundingClientRect();
      // A wide cell may exceed the viewport; its far edge must remain reachable.
      const reachable = last.right <= bounds.right + 1 && last.right > bounds.left;
      scroller.scrollLeft = 0;
      return { small, reachable };
    });
    await page.screenshot({ path: `${output}/${stem}-table-${index}.png` });
    assert.equal(details.small, false, 'table text below 14 CSS pixels');
    assert.equal(details.reachable, true, 'rightmost table cell cannot be reached');
  }
}

/** Require mobile table columns to be discoverable without horizontal scrolling. */
async function mobileTableColumns(page, stem, result) {
  const tables = page.locator('.manual-prose table');
  assert.ok(await tables.count() > 0);
  result.mobileTableGeometry = [];
  const failures = [];
  for (let index = 0; index < await tables.count(); index++) {
    const table = tables.nth(index);
    await table.scrollIntoViewIfNeeded();
    await table.evaluate((el) => {
      // Measure the initial horizontal presentation, not the previous reachability probe.
      for (let parent = el; parent; parent = parent.parentElement) parent.scrollLeft = 0;
    });
    const geometry = await table.evaluate((el) => {
      const headers = [...el.querySelectorAll('th')];
      const lastCells = [...el.querySelectorAll('tr')].map((row) =>
        [...row.children].filter((cell) => cell.matches('th, td')).at(-1)).filter(Boolean);
      return { headers: headers.length, cells: [...new Set([...headers, ...lastCells])].map((cell) => {
        const rect = cell.getBoundingClientRect();
        const style = getComputedStyle(cell);
        let visible = rect.width > 0 && rect.height > 0 && style.visibility === 'visible' &&
          rect.left >= -1 && rect.right <= innerWidth + 1;
        for (let parent = cell.parentElement; parent; parent = parent.parentElement) {
          if (!['hidden', 'clip', 'auto', 'scroll'].includes(getComputedStyle(parent).overflowX)) continue;
          const bounds = parent.getBoundingClientRect();
          const left = bounds.left + parent.clientLeft;
          visible &&= rect.left >= left - 1 && rect.right <= left + parent.clientWidth + 1;
        }
        return { text: cell.textContent.trim().slice(0, 80), left: rect.left, right: rect.right, visible };
      }) };
    });
    result.mobileTableGeometry.push({ index, ...geometry });
    await page.screenshot({ path: `${output}/${stem}-table-${index}-initial-columns.png` });
    if (!geometry.headers || geometry.cells.some((cell) => !cell.visible)) {
      failures.push(`table ${index}: initial header/last-column clipping: ${JSON.stringify(geometry)}`);
    }
  }
  assert.equal(failures.length, 0, failures.join('\n'));
}

const browser = await chromium.launch();
try {
  for (const width of [320, 390, 768, 1440]) {
    for (const route of ['/', '/manual/', '/changelog/']) {
      const stem = `${width}-${route === '/' ? 'home' : route.split('/')[1]}`;
      const result = { width, route, checks: [] };
      report.cases.push(result);
      const context = await browser.newContext({ viewport: { width, height: 900 },
        reducedMotion: 'reduce', colorScheme: 'light', locale: 'zh-CN' });
      const page = await context.newPage();
      page.setDefaultTimeout(10000);
      await check(result, 'exact route and publication identity', async () => {
        const response = await page.goto(`${base}${route}`, { waitUntil: 'networkidle' });
        assert.equal(response.status(), 200);
        assert.equal(page.url(), `${base}${route}`, 'unexpected redirect');
        assert.match(response.headers()['content-type'], /text\/html/);
        if (published) {
          assert.equal(response.headers()['x-amail-release-revision'], process.env.CANDIDATE_REVISION);
          assert.doesNotMatch(response.headers()['x-robots-tag'] ?? '', /noindex|nofollow/i);
          assert.equal(response.headers()['x-amail-candidate-revision'], undefined);
          assert.equal(await page.locator('meta[name="robots"][content*="noindex"]').count(), 0);
        }
        if (['live-candidate', 'live-staging'].includes(process.env.TARGET)) {
          assert.equal(response.headers()['x-amail-candidate-revision'], process.env.CANDIDATE_REVISION);
          assert.match(response.headers()['x-robots-tag'], /noindex/);
          assert.match(response.headers()['x-robots-tag'], /nofollow/);
        }
        await page.evaluate(() => document.fonts.ready);
        assert.equal(await page.locator('main#main').count(), 1);
        const text = await page.locator('main').innerText();
        const state = published
          ? { '/': 'v0.2.0 已发布', '/manual/': 'v0.2.0 已发布', '/changelog/': 'v0.2.0 已正式发布' }
          : { '/': 'v0.2.0 尚未发布', '/manual/': 'v0.2.0 尚未开放下载', '/changelog/': 'v0.2.0 仍在验收' };
        assert.ok(text.includes(state[route]), 'route-local publication status missing');
        if (published) {
          assert.doesNotMatch(text, /staging 候选|v0\.2\.0 尚未|v0\.2\.0 仍在验收|候选记录日期/);
          assert.ok(await page.locator(`a[href="${releaseTagUrl}"]`).count() > 0);
          if (route === '/manual/') {
            for (const asset of releaseDownloads) {
              assert.equal(await page.locator(`a[href="${asset.href}"]`).count(), 1,
                `exact published download missing: ${asset.name}`);
            }
          }
        } else {
          assert.ok(text.includes('这是 v0.2.0 staging 候选版本说明，尚未发布，不表示邮件服务或发送已开放。'));
          for (const asset of releaseDownloads) assert.equal(await page.locator(`a[href="${asset.href}"]`).count(), 0);
        }
        if (route === '/manual/') {
          for (const command of ['amail discover', 'amail send-status', 'amail events']) {
            assert.ok(text.includes(command), `candidate exploration missing: ${command}`);
          }
        }
        if (route === '/changelog/') {
          assert.equal(await page.locator('h2[id="v0.2.0"]').count(), 1,
            'candidate changelog entry must exist independently of page status');
          assert.equal(await page.locator('.toc a[href="#v0.2.0"]').count(), 1);
          assert.equal(await page.locator('h2[id="v0.1.0"]').count(), 1);
          assert.equal(await page.locator('.toc a[href="#v0.1.0"]').count(), 1);
        }
      });
      await check(result, 'route-local CSS and zero client runtime', async () => {
        result.loading = await page.evaluate(() => ({
          styles: [...document.styleSheets].map((sheet) => sheet.href).filter(Boolean),
          scripts: document.querySelectorAll('script').length,
        }));
        const components = result.loading.styles.some((href) =>
          new URL(href).pathname === '/vendor/moesegfault-style/v0.1.2/css/components.css');
        assert.equal(components, route === '/', 'unused component CSS must not block guide routes');
        assert.equal(result.loading.scripts, 0, 'static guide must not ship a client runtime');
      });
      await check(result, 'no page horizontal overflow', async () => {
        const bounds = await page.evaluate(() => ({ width: innerWidth,
          content: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) }));
        assert.ok(bounds.content <= bounds.width + 1, JSON.stringify(bounds));
      });
      await check(result, 'skip link keyboard focus and main continuation', async () => {
        await page.goto(`${base}${route}`);
        await page.keyboard.press('Tab');
        assert.equal(await page.locator('.skip-link').evaluate((el) => el === document.activeElement), true);
        result.skipFocus = await focusedOutline(page);
        assert.ok(result.skipFocus.passes, `skip focus: ${JSON.stringify(result.skipFocus)}`);
        const box = await page.locator('.skip-link').boundingBox();
        assert.ok(box.y >= 0 && box.x >= 0 && box.x + box.width <= width);
        await page.screenshot({ path: `${output}/${stem}-skip-focus.png` });
        await page.keyboard.press('Enter');
        // A remote browser may acknowledge the key before the fragment commit.
        // Wait for the real navigation contract, without relaxing focus assertions.
        await page.waitForURL((url) => url.hash === '#main', { timeout: 2000 });
        assert.equal(new URL(page.url()).hash, '#main');
        await page.keyboard.press('Tab');
        result.mainContinuationFocus = await focusedOutline(page);
        await page.screenshot({ path: `${output}/${stem}-main-continuation-focus.png` });
        assert.ok(await page.locator('main').evaluate((el) => el.contains(document.activeElement)),
          'keyboard continuation must bypass header navigation');
        assert.ok(result.mainContinuationFocus.passes,
          `main continuation focus: ${JSON.stringify(result.mainContinuationFocus)}`);
      });
      await check(result, 'unclipped CTAs and local installation/privacy destinations', async () => {
        const ctas = page.locator('.header-cta, .button, .release-link');
        assert.ok(await ctas.count() > 0);
        for (let index = 0; index < await ctas.count(); index++) await unclipped(ctas.nth(index));
        const anchors = page.locator('a[href^="/manual/#"]');
        const hrefs = await anchors.evaluateAll((links) => [...new Set(links.map((link) => link.getAttribute('href')))]);
        assert.ok(hrefs.length > 0);
        for (const href of hrefs) {
          await page.goto(`${base}${href}`);
          const id = decodeURIComponent(new URL(page.url()).hash.slice(1));
          assert.ok(await page.evaluate((value) => !!document.getElementById(value), id), href);
        }
        await page.goto(`${base}${route}`);
      });
      if (route !== '/') await check(result, 'TOC activation and heading visibility', () => toc(page, stem, result));
      if (route === '/manual/') await check(result, 'privacy introduction renders semantic emphasis', async () => {
        // The pre-use warning must render as emphasis, not raw Markdown syntax.
        const label = '使用前的隐私提示：';
        const count = await page.locator('.manual-prose strong').evaluateAll((elements, text) =>
          elements.filter((el) => el.textContent.trim() === text).length, label);
        assert.equal(count, 1, 'privacy introduction must have exactly one strong label');
        assert.ok(!(await page.locator('.manual-prose').innerText()).includes(`**${label}**`),
          'privacy introduction must not expose literal Markdown markers');
      });
      if (route === '/manual/') await check(result, 'human Billing return is inert and non-authoritative', async () => {
        const response = await page.goto(`${base}/billing/return?code=synthetic-untrusted-return`);
        assert.equal(response.status(), 200);
        const text = await page.locator('main').innerText();
        assert.ok(text.includes('不代表付款成功'));
        assert.ok(text.includes('amail billing status'));
        assert.ok(!text.includes('synthetic-untrusted-return'));
        assert.equal(await page.locator('script, form, iframe').count(), 0);
        await page.goto(`${base}/manual/`);
      });
      if (route === '/manual/' && width <= 390) await check(result,
        'mobile table columns visible without horizontal scrolling', () => mobileTableColumns(page, stem, result));
      if (route === '/manual/') await check(result, 'manual table readability and reachability', () => tables(page, stem));
      await check(result, 'review screenshots', async () => {
        await page.goto(`${base}${route}`);
        await page.screenshot({ path: `${output}/${stem}-viewport.png` });
        await page.screenshot({ path: `${output}/${stem}-full.png`, fullPage: true });
      });
      await context.close();
    }
  }
} finally {
  await browser.close();
  report.finished = new Date().toISOString();
  await writeFile(`${output}/report.json`, `${JSON.stringify(report, null, 2)}\n`);
}
const failures = report.cases.flatMap((result) => result.checks.filter((item) => !item.passed)
  .map((item) => `${result.width} ${result.route} ${item.name}: ${item.error}`));
console.log(failures.length ? failures.join('\n') : 'PASS: 12 route/viewport cases; human screenshot review remains required.');
process.exitCode = failures.length ? 1 : 0;
