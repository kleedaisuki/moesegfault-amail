#!/usr/bin/env node
/** Real native amail -> staging Identity browser approval -> protected session.
 * Uses the existing deployment-owned staging principal; never authorizes spending.
 */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { mkdir, mkdtemp, readFile, realpath, readdir, rm, stat, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const { values } = parseArgs({ options: {
  binary: { type: 'string' }, 'browser-module': { type: 'string' }, output: { type: 'string' },
} });
for (const name of ['binary', 'browser-module', 'output']) assert.ok(values[name], `Missing --${name}`);
const binary = await realpath(values.binary);
const binarySha256 = createHash('sha256').update(await readFile(binary)).digest('hex');
const output = path.resolve(values.output);
const scratch = path.join(root, '.temp');
const relative = path.relative(scratch, output);
assert.ok(relative && !relative.startsWith('..') && !path.isAbsolute(relative), 'Evidence belongs under project .temp');
const username = process.env.STAGING_E2E_USERNAME;
const password = process.env.STAGING_E2E_PASSWORD;
assert.ok(username && password, 'Existing staging fixture credentials are required');
delete process.env.STAGING_E2E_USERNAME;
delete process.env.STAGING_E2E_PASSWORD;
const issuer = 'https://identity-staging.moesegfault.dev';
const loginOrigin = 'https://login-staging.moesegfault.dev';
const apiOrigin = 'https://mail-staging.moesegfault.dev';
const subscribeOrigin = 'https://subscribe-staging.moesegfault.dev';
const clientId = 'amail-cli-staging';
await mkdir(output, { recursive: true });
await rm(path.join(output, 'acceptance.json'), { force: true });
await rm(path.join(output, 'failure.json'), { force: true });
const workspace = await mkdtemp(path.join(scratch, 'device-staging-native-'));
const homes = [];
const children = new Set();
const checks = [];
const requests = [];
const privateValues = new Set([username, password]);
let browser;
let context;
let phase = 'setup';
let failure;
let savedHome;
let loggedOut = false;
let billingState = 'not_run';
let lastCli;
let failedCli;

function pass(check) {
  checks.push(check);
  console.log(`PASS: ${check}`);
}
function launch(home, args) {
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.toUpperCase().startsWith('AMAIL_')));
  Object.assign(env, { AMAIL_HOME: home, AMAIL_TERMINAL_ID: `staging-device-${path.basename(home)}`,
    AMAIL_TELEMETRY: 'off', AMAIL_API_BASE: apiOrigin, AMAIL_ISSUER: issuer,
    AMAIL_CLIENT_ID: clientId, AMAIL_REDIRECT_URI: '' });
  const child = spawn(binary, ['--machine', ...args], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] });
  const state = { child, stdout: '', stderr: '', rows: [], settled: false };
  children.add(state);
  state.done = new Promise((resolve, reject) => {
    child.on('error', reject);
    child.on('close', (code) => { state.settled = true; children.delete(state); resolve(code); });
  });
  state.done.catch(() => {});
  child.stdout.on('data', (chunk) => {
    state.stdout += chunk.toString();
    state.rows = state.stdout.split('\n').filter(Boolean).flatMap((line) => {
      try { return [JSON.parse(line)]; } catch { return []; }
    });
  });
  child.stderr.on('data', (chunk) => { state.stderr += chunk.toString(); });
  lastCli = state;
  return state;
}
async function until(predicate, label, timeout = 60_000) {
  const deadline = Date.now() + timeout;
  while (!predicate()) {
    if (Date.now() >= deadline) throw new Error(label);
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
}
async function finish(state, expected = 0) {
  await until(() => state.settled, 'native_cli_completion_timeout');
  assert.equal(await state.done, expected, 'native_cli_exit_status');
  assert.ok(!state.stdout.includes(password) && !state.stderr.includes(password), 'Credential appeared in native output');
  return state.rows;
}
async function command(home, args) {
  const state = launch(home, args);
  await until(() => state.settled || /http:\/\/127\.0\.0\.1:\d+\/authorize\/[0-9a-f-]+/.test(state.stderr), 'native_operation_start_timeout');
  const localApproval = state.stderr.match(/http:\/\/127\.0\.0\.1:\d+\/authorize\/[0-9a-f-]+/)?.[0];
  if (localApproval) {
    const page = await context.newPage();
    try {
      await page.goto(localApproval);
      await page.getByRole('button', { name: 'Approve', exact: true }).click();
    } finally { await page.close(); }
  }
  return finish(state);
}
async function home(name) {
  const directory = path.join(workspace, name);
  await mkdir(directory, { mode: 0o700 });
  await writeFile(path.join(directory, 'config.toml'), 'yolo = false\n', { mode: 0o600 });
  homes.push(directory);
  return directory;
}
async function beginLogin(name) {
  const directory = await home(name);
  const state = launch(directory, ['auth', 'login', '--device-code', '--no-browser']);
  await until(() => state.rows.some((row) => row.user_code) || state.settled, 'native_device_prompt_missing');
  const prompt = state.rows.find((row) => row.user_code);
  assert.ok(prompt, 'native_device_prompt_missing');
  privateValues.add(prompt.user_code);
  if (prompt.verification_uri_complete) privateValues.add(prompt.verification_uri_complete);
  assert.equal(prompt.verification_uri, `${loginOrigin}/device`);
  assert.ok(!state.stderr.includes('/authorize/'), 'Device login must not need a local callback or approval');
  return { directory, state, prompt };
}
async function review(page, prompt, authenticate) {
  await page.goto(prompt.verification_uri);
  await page.locator('input[name="user_code"]').fill(prompt.user_code);
  await page.locator('form').filter({ has: page.locator('input[name="user_code"]') }).locator('button[type="submit"]').click();
  if (authenticate) {
    await page.locator('main a[href^="/login?device_user_code="]').click();
    assert.equal(new URL(page.url()).origin, loginOrigin);
    await page.locator('input[name="login"]').fill(username);
    await page.locator('input[name="password"]').fill(password);
    await page.locator('form').filter({ has: page.locator('input[name="password"]') }).locator('button[type="submit"]').click();
  }
  await page.getByRole('button', { name: 'Confirm and allow sign-in', exact: true }).waitFor();
  assert.equal(new URL(page.url()).origin, loginOrigin);
  const text = await page.locator('main').innerText();
  assert.ok(text.includes(prompt.user_code) && text.includes(clientId) && text.includes(username), 'Device review must identify this code, client and account');
}
async function apiJson(response, expected = 200) {
  const url = new URL(response.url());
  const correlation = response.headers()['x-moesegfault-correlation-id'];
  requests.push({ origin: url.origin, path: url.pathname, status: response.status(), ...(correlation && { correlation_id: correlation }) });
  assert.equal(response.status(), expected, 'staging_identity_cleanup_http_status');
  return expected === 204 ? undefined : response.json();
}
async function cleanupBrowserSession() {
  if (!context) return;
  const response = await context.request.get(`${issuer}/v1/me`);
  if (response.status() === 401) return;
  const current = await apiJson(response);
  const sessions = await apiJson(await context.request.get(`${issuer}/v1/principals/self/sessions`));
  const own = sessions.items.find((item) => item.is_current && !item.revoked_at);
  assert.ok(own, 'own_staging_browser_session_missing');
  await apiJson(await context.request.delete(`${issuer}/v1/principals/self/sessions/${own.session_id}`, {
    headers: { origin: loginOrigin, 'x-moesegfault-csrf': current.csrf_token, 'idempotency-key': randomUUID() },
  }), 204);
}
async function billing(home) {
  const before = (await command(home, ['billing', 'status'])).at(-1);
  const key = randomUUID();
  const intent = (await command(home, ['billing', 'subscribe', 'free', '--device-code', '--no-browser', '--idempotency-key', key])).at(-1);
  for (const value of [intent.user_code, intent.verification_uri_complete, intent.authorization_url]) {
    if (value) privateValues.add(value);
  }
  assert.equal(intent.state, 'pending');
  assert.equal(intent.session_id, key);
  assert.equal(intent.verification_uri, `${apiOrigin}/billing/device`);
  assert.ok(intent.user_code && intent.expires_in > 0 && intent.interval > 0);
  const page = await context.newPage();
  try {
    await page.goto(intent.verification_uri);
    await page.locator('input[name="user_code"]').fill(intent.user_code);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL((url) => url.origin === subscribeOrigin);
    await page.locator('#amail-plan, a.moe-button').first().waitFor();
    if (!await page.locator('#amail-plan').count()) {
      await page.locator('a.moe-button').click();
      // Existing Identity SSO may resume immediately; type only if Login needs it.
      await Promise.race([
        page.locator('#amail-plan').waitFor(),
        page.locator('input[name="login"]').waitFor(),
      ]);
      if (await page.locator('input[name="login"]').isVisible()) {
        assert.equal(new URL(page.url()).origin, loginOrigin);
        await page.locator('input[name="login"]').fill(username);
        await page.locator('input[name="password"]').fill(password);
        await page.locator('form').filter({ has: page.locator('input[name="password"]') }).locator('button[type="submit"]').click();
      }
    }
    await page.locator('#amail-plan').waitFor();
    assert.equal(new URL(page.url()).origin, subscribeOrigin);
    const pending = (await command(home, ['billing', 'session', intent.session_id])).at(-1);
    assert.equal(pending.state, 'pending', 'Navigation must not approve billing');
    await page.locator('.authorization-panel .form-footer button[type=button]').click();
    await page.locator('#amail-plan').waitFor({ state: 'detached' });
    const cancelled = (await command(home, ['billing', 'session', intent.session_id, '--wait-seconds', '30'])).at(-1);
    assert.equal(cancelled.state, 'cancelled');
    const after = (await command(home, ['billing', 'status'])).at(-1);
    for (const field of ['plan', 'overage_budget_micros']) assert.equal(after.account[field], before.account[field], 'Cancelled handoff must preserve entitlement and spending');
    billingState = 'pending_handoff_then_cancelled';
    pass('billing_short_code_manual_entry_hosted_review_cancel_and_unchanged_entitlement');
  } finally { await page.close(); }
}

try {
  const { chromium } = await import(pathToFileURL(await realpath(values['browser-module'])).href);
  browser = await chromium.launch({ headless: true });
  context = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'en-US' });
  context.setDefaultTimeout(45_000);
  phase = 'native_device_approval';
  const approved = await beginLogin('approved');
  const page = await context.newPage();
  await review(page, approved.prompt, true);
  await page.waitForTimeout((approved.prompt.interval + 1) * 1000);
  assert.equal(approved.state.settled, false, 'Page visit and sign-in must not approve device access');
  await page.getByRole('button', { name: 'Confirm and allow sign-in', exact: true }).click();
  await page.getByRole('heading', { name: 'Device sign-in approved', exact: true }).waitFor();
  assert.equal((await finish(approved.state)).at(-1).authenticated, true);
  savedHome = approved.directory;
  assert.ok((await stat(path.join(savedHome, 'auth.sqlite3'))).size > 0);
  if (process.platform !== 'win32') assert.equal((await stat(path.join(savedHome, 'auth.sqlite3'))).mode & 0o777, 0o600);
  assert.equal((await command(savedHome, ['auth', 'status'])).at(-1).authenticated, true);
  pass('real_native_device_login_manual_code_explicit_approval_and_protected_session');
  phase = 'native_device_denial';
  const denied = await beginLogin('denied');
  await review(page, denied.prompt, false);
  await page.getByRole('button', { name: 'Deny sign-in', exact: true }).click();
  await page.getByRole('heading', { name: 'Sign-in denied', exact: true }).waitFor();
  await finish(denied.state, 1);
  assert.ok(denied.state.stderr.includes('access_denied'));
  assert.ok(!(await readdir(denied.directory)).includes('auth.sqlite3'));
  pass('real_browser_denial_leaves_no_native_session');
  await page.close();
  phase = 'billing_short_code';
  await billing(savedHome);
  phase = 'cleanup';
} catch (error) {
  failure = error;
  failedCli = lastCli;
} finally {
  for (const state of children) state.child.kill();
  await Promise.all([...children].map((state) => state.done.catch(() => {})));
  try {
    if (savedHome) {
      assert.equal((await command(savedHome, ['auth', 'logout'])).at(-1).authenticated, false);
      assert.equal((await command(savedHome, ['auth', 'status'])).at(-1).authenticated, false);
      loggedOut = true;
    }
    await cleanupBrowserSession();
    for (const directory of homes) await command(directory, ['daemon', 'stop']);
  } catch (error) { failure ??= error; phase = `${phase}_cleanup`; }
  await context?.close();
  await browser?.close();
  await rm(workspace, { recursive: true, force: true });
}
if (failure) {
  const machineErrors = failedCli?.stderr.split('\n').flatMap((line) => {
    try {
      const value = JSON.parse(line);
      return value.schema === 'amail.machine.v1' && value.event === 'error' ? [value] : [];
    } catch { return []; }
  }) ?? [];
  let detail = JSON.stringify({ phase, checks, requests,
    error: failure instanceof Error ? failure.message : 'journey_failed', machine_errors: machineErrors }, null, 2);
  for (const value of privateValues) detail = detail.replaceAll(value, '[private]');
  await writeFile(path.join(output, 'failure.json'), detail, { mode: 0o600 });
  throw new Error(`Staging native device journey failed at ${phase}; see private failure.json`);
}
assert.ok(loggedOut);
let backend;
const backendPath = process.env.AMAIL_DEVICE_STAGING_RECEIPT ?? path.join(root, '.temp/device-backend-staging.json');
try { backend = JSON.parse(await readFile(backendPath, 'utf8')); }
catch (error) { if (error.code !== 'ENOENT') throw error; }
const receipt = { schema: 'device-staging-acceptance/v1', outcome: 'passed',
  source_sha: process.env.GITHUB_SHA, run_id: process.env.GITHUB_RUN_ID, run_attempt: process.env.GITHUB_RUN_ATTEMPT,
  backend_artifact_id: process.env.AMAIL_DEVICE_ARTIFACT_ID ?? backend?.artifact_id,
  api_version: backend?.api_version, issuer, client_id: clientId,
  binary_sha256: binarySha256,
  login: 'persisted', billing: billingState, cleanup: 'complete', checks, requests };
assert.equal(createHash('sha256').update(await readFile(binary)).digest('hex'), binarySha256, 'Native candidate bytes changed during acceptance');
await writeFile(path.join(output, 'acceptance.json'), JSON.stringify(receipt, null, 2), { mode: 0o600, flag: 'wx' });
console.log('Real staging native device and billing handoff journey passed; owned credentials and browser session cleaned up.');
