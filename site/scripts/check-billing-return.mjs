/** Verify the built human-return surface without consuming browser query data. */
import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
const html = await readFile(new URL('../dist/billing/return/index.html', import.meta.url), 'utf8');
assert.ok(html.includes('amail billing status'), 'return must direct a fresh authoritative read');
assert.ok(html.includes('不代表付款成功'), 'return must not assert payment success');
assert.ok(html.includes('/manual/#订阅与用量'), 'return must expose a useful next action');
assert.ok(!/<(?:script|form|iframe)\b/i.test(html), 'return must remain inert and script-free');
assert.ok(!/https:\/\/[^"\s<>]+[?&](?:token|code|session)=/i.test(html), 'no credential-bearing link');
console.log('billing_return=static_authority_boundary_verified');
