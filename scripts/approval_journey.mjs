/** Hosted-only native approval regression; never uses a real account or home.
 * Install the existing pinned Playwright harness under .temp, then run:
 * node scripts/approval_journey.mjs --binary PATH --browser-module PATH --output .temp/approval-evidence
 */
import assert from 'node:assert/strict';
import { execFile, spawn } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { mkdir, mkdtemp, readFile, realpath, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { parseArgs, promisify } from 'node:util';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const run = promisify(execFile);
const { values } = parseArgs({ options: {
  binary: { type: 'string' }, 'browser-module': { type: 'string' }, output: { type: 'string' },
} });
assert.ok(values.binary && values['browser-module'] && values.output, 'All three path arguments are required');
const binary = await realpath(values.binary);
const modulePath = await realpath(values['browser-module']);
const output = path.resolve(values.output);
const scratch = path.join(root, '.temp');
const relative = path.relative(scratch, output);
assert.ok(relative && !relative.startsWith('..') && !path.isAbsolute(relative), 'Evidence must be below repository .temp');
await mkdir(scratch, { recursive: true });
await mkdir(output, { recursive: true });
await rm(path.join(output, 'acceptance.json'), { force: true });
const home = await mkdtemp(path.join(scratch, 'approval-home-'));
const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.toUpperCase().startsWith('AMAIL_')));
Object.assign(env, {
  AMAIL_HOME: home, AMAIL_TERMINAL_ID: `approval-test-${randomUUID()}`, AMAIL_TELEMETRY: 'off',
  AMAIL_API_BASE: 'https://mail.example.test', AMAIL_ISSUER: 'https://identity.example.test',
  AMAIL_CLIENT_ID: 'synthetic',
});
await writeFile(path.join(home, 'config.toml'), 'yolo = false\n', { mode: 0o600 });
const { chromium } = await import(pathToFileURL(modulePath).href);
let browser;
let context;
let pending;
let phase = 'launch';

function start(args) {
  const child = spawn(binary, args, { cwd: root, env, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
  const state = { child, stdout: '', stderr: '', url: null, settled: false };
  state.done = new Promise((resolve, reject) => {
    child.on('error', reject);
    child.on('close', (code) => { state.settled = true; resolve(code); });
  });
  state.done.catch(() => {});
  state.prompt = new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Native approval prompt timed out')), 25_000);
    child.stderr.on('data', (chunk) => {
      state.stderr += chunk.toString();
      const match = state.stderr.match(/http:\/\/127\.0\.0\.1:\d+\/authorize\/[0-9a-f-]{36}/);
      if (match) { clearTimeout(timer); state.url = match[0]; resolve(state.url); }
    });
    state.done.then(() => { clearTimeout(timer); reject(new Error('CLI exited before approval prompt')); }, reject);
  });
  child.stdout.on('data', (chunk) => { state.stdout += chunk.toString(); });
  return state;
}

async function bounded(promise, label) {
  let timer;
  try {
    return await Promise.race([promise, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(label)), 25_000);
    })]);
  } finally { clearTimeout(timer); }
}

async function decide(args, decision, name, rejectForged = false) {
  phase = name;
  pending = start(args);
  const url = await pending.prompt;
  const origin = new URL(url).origin;
  const page = await context.newPage();
  const view = await page.goto(url, { waitUntil: 'domcontentloaded' });
  assert.ok(view?.status() === 200, 'Approval form must load');
  assert.ok(view.headers()['referrer-policy'] === 'same-origin', 'Form must preserve same-origin POST Origin');
  assert.ok(!pending.settled && pending.stdout === '', 'Viewing must not execute the operation');
  if (rejectForged) {
    const nonce = await page.locator('input[name=nonce]').inputValue();
    for (const forged of ['null', 'https://attacker.example.test']) {
      const response = await fetch(url, {
        method: 'POST', headers: { Origin: forged, 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ nonce, decision: 'approve' }), signal: AbortSignal.timeout(3000),
      });
      assert.ok(response.status === 400, 'Forged Origin must be rejected');
      assert.ok((await response.text()).includes('Invalid authorization request.'), 'Reject must remain explicit');
      assert.ok(!pending.settled && pending.stdout === '', 'Rejected requests must not consume a decision');
    }
  }
  const [request, reply] = await Promise.all([
    page.waitForRequest((request) => request.url() === url && request.method() === 'POST'),
    page.waitForResponse((response) => response.url() === url && response.request().method() === 'POST'),
    page.getByRole('button', { name: decision === 'approve' ? 'Approve' : 'Deny', exact: true }).click(),
  ]);
  assert.ok((await request.allHeaders()).origin === origin, 'Native browser form POST must carry exact loopback Origin');
  assert.ok(reply.status() === 200, 'Native form decision must succeed');
  const heading = decision === 'approve' ? 'Approved' : 'Denied';
  await page.getByRole('heading', { name: heading, exact: true }).waitFor();
  await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true });
  const code = await bounded(pending.done, 'Native operation did not finish after decision');
  const stdout = pending.stdout;
  if (decision === 'approve') assert.ok(code === 0, 'Approved local operation must succeed');
  else {
    assert.ok(code !== 0 && stdout === '', 'Denied operation must fail without result');
    assert.ok(pending.stderr.includes('the amail operation was denied'), 'Denial must reach the CLI');
  }
  pending = null;
  await page.close();
  return decision === 'approve' ? JSON.parse(stdout) : null;
}

async function cancelPending() {
  if (!pending || pending.settled) return;
  if (pending.url) {
    const html = await (await fetch(pending.url, { signal: AbortSignal.timeout(3000) })).text();
    const nonce = html.match(/name=nonce value="([^"]+)"/)?.[1];
    if (nonce) await fetch(pending.url, {
      method: 'POST', headers: { Origin: new URL(pending.url).origin, 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ nonce, decision: 'deny' }), signal: AbortSignal.timeout(3000),
    });
  }
  await bounded(pending.done, 'Pending synthetic operation did not stop');
}

let complete = false;
try {
  browser = await chromium.launch({ headless: true });
  context = await browser.newContext();
  context.setDefaultTimeout(15_000);
  const config = await decide(['config'], 'approve', 'initial-approved', true);
  assert.ok(config.yolo === false && config.telemetry_enabled === false, 'Approval must not require YOLO or telemetry');
  assert.ok(config.issuer === env.AMAIL_ISSUER && config.client_id === 'synthetic', 'Test must remain in synthetic realm');
  await decide(['profile', 'deactivate'], 'deny', 'operation-denied');
  const status = await decide(['profile', 'status'], 'approve', 'profile-approved');
  assert.ok(status.profile?.name === 'user', 'Denied deactivation must preserve the active user profile');
  await assert.rejects(readFile(path.join(home, 'auth.sqlite3')), { code: 'ENOENT' });
  complete = true;
} catch (error) {
  error.message = `${phase}: ${error.message}`;
  throw error;
} finally {
  phase = `cleanup-after-${phase}`;
  try { await cancelPending(); }
  finally {
    await browser?.close();
    const status = JSON.parse((await run(binary, ['daemon', 'status'], { cwd: root, env, timeout: 10_000, windowsHide: true })).stdout);
    if (status.running) await run(binary, ['daemon', 'stop'], { cwd: root, env, timeout: 20_000, windowsHide: true });
    const stopped = JSON.parse((await run(binary, ['daemon', 'status'], { cwd: root, env, timeout: 10_000, windowsHide: true })).stdout);
    assert.ok(stopped.running === false, 'Owned daemon must stop before removing synthetic state');
    await rm(home, { recursive: true });
  }
}
assert.ok(complete, 'Native browser acceptance must complete');
const version = (await run(binary, ['--version'], { cwd: root, env, timeout: 5000, windowsHide: true })).stdout.trim();
const receipt = {
  schema: 'amail-approval-acceptance/v1', source_sha: process.env.GITHUB_SHA ?? null,
  run_id: process.env.GITHUB_RUN_ID ?? null, version,
  binary_sha256: createHash('sha256').update(await readFile(binary)).digest('hex'),
  cases: ['get-does-not-execute', 'null-origin-rejected', 'cross-origin-rejected',
    'native-approve', 'native-deny', 'denied-deactivation-preserves-profile', 'owned-daemon-stopped'],
};
await writeFile(path.join(output, 'acceptance.json'), `${JSON.stringify(receipt, null, 2)}\n`);
console.log('PASS native browser approval, denial, origin rejection and cleanup');
