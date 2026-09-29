/** Verify static copy and navigation for one explicitly selected release state. */
import { readFileSync } from 'node:fs';

const state = process.argv[2];
if (state !== 'candidate' && state !== 'published') {
  throw new Error('Usage: node scripts/check-release-state.mjs candidate|published');
}

const pages = ['index', 'manual/index', 'changelog/index'].map((path) =>
  readFileSync(new URL(`../dist/${path}.html`, import.meta.url), 'utf8'),
);
const joined = pages.join('\n');
const candidateClaims = ['v0.1.0 尚未发布', 'v0.1.0 尚未开放下载', 'v0.1.0 仍在验收'];
const publishedClaims = ['v0.1.0 已发布', 'v0.1.0 已正式发布'];

for (const page of pages) {
  if (!page.includes('href="/manual/"') || !page.includes('href="/changelog/"')) {
    throw new Error('Required three-page navigation is missing');
  }
}
if (!pages[1].includes('aria-label="用户手册目录"') || !pages[2].includes('aria-label="更新日志目录"')) {
  throw new Error('Manual or changelog table of contents is missing');
}
for (const claim of candidateClaims) {
  if ((state === 'candidate') !== joined.includes(claim)) {
    throw new Error(`Incorrect candidate claim: ${claim}`);
  }
}
for (const claim of publishedClaims) {
  if ((state === 'published') !== joined.includes(claim)) {
    throw new Error(`Incorrect published claim: ${claim}`);
  }
}
if (state === 'published' && !joined.includes('releases/tag/v0.1.0')) {
  throw new Error('Published release link is missing');
}
console.log(`release_site_state=${state} pages=3 toc=2`);
