/** Synthetic HTTPS Identity -> real daemon CLI -> browser -> protected session.
 * This is native integration acceptance, not a deployed Identity/Billing receipt.
 */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createHash, generateKeyPairSync, randomUUID, sign } from 'node:crypto';
import { mkdir, mkdtemp, readFile, realpath, readdir, rm, stat, writeFile } from 'node:fs/promises';
import https from 'node:https';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const { values } = parseArgs({ options: {
  binary: { type: 'string' }, 'browser-module': { type: 'string' }, output: { type: 'string' },
  certificate: { type: 'string' }, 'private-key': { type: 'string' },
} });
for (const name of ['binary', 'browser-module', 'output', 'certificate', 'private-key']) {
  assert.ok(values[name], `Missing --${name}`);
}
const binary = await realpath(values.binary);
const output = path.resolve(values.output);
const scratch = path.join(root, '.temp');
assert.ok(path.relative(scratch, output) && !path.relative(scratch, output).startsWith('..'));
await mkdir(output, { recursive: true });
await rm(path.join(output, 'acceptance.json'), { force: true });
const workspace = await mkdtemp(path.join(scratch, 'device-journey-'));
const certificate = await realpath(values.certificate);
const { privateKey, publicKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
const jwk = { ...publicKey.export({ format: 'jwk' }), kid: 'synthetic-device-key', alg: 'RS256', use: 'sig' };
const grants = new Map();
const credentials = new Set();
const refreshes = [];
const revocations = [];
const clients = new Map();
let issuer;
let fixtureError;
let browser;
let context;
let phase = 'setup';
let active;
const homes = [];
const clock = () => Math.floor(Date.now() / 1000);

function jwt(client, audience = client) {
  const header = Buffer.from(JSON.stringify({ alg: 'RS256', kid: jwk.kid })).toString('base64url');
  const body = Buffer.from(JSON.stringify({ iss: issuer, aud: audience, sub: 'synthetic-person',
    iat: clock(), exp: clock() + 600, token_use: 'id' })).toString('base64url');
  const payload = `${header}.${body}`;
  return `${payload}.${sign('RSA-SHA256', Buffer.from(payload), privateKey).toString('base64url')}`;
}
function tokens(client, refreshed = false) {
  const access = `access-${randomUUID()}`;
  const refresh = `refresh-${randomUUID()}`;
  credentials.add(access); credentials.add(refresh);
  clients.set(refresh, client);
  const id = jwt(client, client.endsWith('-wrong-audience') ? 'another-client' : client);
  credentials.add(id);
  return { access_token: access, refresh_token: refresh, token_type: 'Bearer',
    expires_in: refreshed ? 600 : 0,
    id_token: id,
    scope: 'openid profile offline_access' };
}
function json(response, status, body) {
  response.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store',
    'x-moesegfault-correlation-id': 'synthetic-correlation-id' });
  response.end(JSON.stringify(body));
}
async function body(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  return new URLSearchParams(Buffer.concat(chunks).toString());
}
const server = https.createServer({ cert: await readFile(certificate), key: await readFile(values['private-key']) },
  async (request, response) => {
    try {
      const url = new URL(request.url, issuer);
      if (url.pathname === '/.well-known/openid-configuration') {
        return json(response, 200, { issuer, authorization_endpoint: `${issuer}/authorize`,
          token_endpoint: `${issuer}/token`, jwks_uri: `${issuer}/jwks`,
          revocation_endpoint: `${issuer}/revoke`, device_authorization_endpoint: `${issuer}/device_authorization`,
          grant_types_supported: ['authorization_code', 'refresh_token', 'urn:ietf:params:oauth:grant-type:device_code'],
          code_challenge_methods_supported: ['S256'], authorization_response_iss_parameter_supported: true });
      }
      if (url.pathname === '/jwks') return json(response, 200, { keys: [jwk] });
      if (url.pathname === '/device_authorization') {
        const form = await body(request);
        assert.equal(form.get('scope'), 'openid profile offline_access');
        const client = form.get('client_id');
        const mode = client.slice('amail-device-test-'.length);
        const id = randomUUID();
        const code = randomUUID().slice(0, 8).toUpperCase();
        const grant = { id, code, client, mode, decision: null, started: Date.now(), polls: [] };
        grants.set(id, grant);
        return json(response, 200, { device_code: id, user_code: code,
          verification_uri: `${issuer}/device`, verification_uri_complete: `${issuer}/device?user_code=${code}`,
          expires_in: mode === 'local-expiry' ? 1 : 60, interval: mode === 'local-expiry' ? 2 : 1 });
      }
      if (url.pathname === '/device') {
        const code = url.searchParams.get('user_code');
        const grant = [...grants.values()].find((item) => item.code === code);
        assert.ok(grant);
        response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
        response.end(`<!doctype html><title>Synthetic Identity</title><h1>Confirm device login</h1>
          <p>Application: amail device test</p><p>Code: <strong>${grant.code}</strong></p>
          <p>Compare this code with your own terminal. Viewing does not approve.</p>
          <form method=post action=/decision><input type=hidden name=code value=${grant.code}>
          <button name=decision value=approve>Approve</button><button name=decision value=deny>Deny</button></form>`);
        return;
      }
      if (url.pathname === '/decision') {
        const form = await body(request);
        const grant = [...grants.values()].find((item) => item.code === form.get('code'));
        assert.ok(grant && !grant.decision);
        grant.decision = form.get('decision');
        response.writeHead(200, { 'Content-Type': 'text/html' });
        response.end(`<h1>${grant.decision === 'approve' ? 'Approved' : 'Denied'}</h1>`);
        return;
      }
      if (url.pathname === '/token') {
        const form = await body(request);
        if (form.get('grant_type') === 'refresh_token') {
          const previous = form.get('refresh_token');
          assert.equal(clients.get(previous), form.get('client_id'));
          clients.delete(previous);
          const reply = tokens(form.get('client_id'), true);
          refreshes.push({ previous, current: reply.refresh_token });
          return json(response, 200, reply);
        }
        assert.equal(form.get('grant_type'), 'urn:ietf:params:oauth:grant-type:device_code');
        assert.equal(form.has('redirect_uri'), false);
        assert.equal(form.has('code_verifier'), false);
        const grant = grants.get(form.get('device_code'));
        assert.equal(grant?.client, form.get('client_id'));
        grant.polls.push(Date.now());
        if (grant.mode === 'server-expiry') return json(response, 400, { error: 'expired_token' });
        if (grant.mode === 'success' && grant.polls.length === 2) return json(response, 400, { error: 'slow_down' });
        if (grant.decision === 'deny') return json(response, 400, { error: 'access_denied' });
        if (!grant.decision) return json(response, 400, { error: 'authorization_pending' });
        assert.equal(grant.consumed, undefined);
        grant.consumed = true;
        return json(response, 200, tokens(grant.client));
      }
      if (url.pathname === '/revoke') {
        const form = await body(request);
        assert.ok(clients.has(form.get('token')));
        clients.delete(form.get('token'));
        revocations.push(form.get('token'));
        return json(response, 200, {});
      }
      if (url.pathname === '/v1/profiles/activate') {
        assert.ok(credentials.has(request.headers.authorization?.slice('Bearer '.length)));
        return json(response, 200, { profile_id: 'b8253038-1adf-4f57-a2eb-95a887442130',
          session_token: 'e2d6f8c4-4f13-4e66-b972-ec7be185d3ea', expires_at: clock() + 3600 });
      }
      if (url.pathname === '/v1/billing') return json(response, 200, { plan: 'free', synthetic: true });
      throw new Error('Unexpected fixture endpoint');
    } catch (error) {
      fixtureError = error;
      if (!response.headersSent) json(response, 500, { error: 'fixture_error' });
      else response.end();
    }
  });
await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
issuer = `https://localhost:${server.address().port}`;

function launch(home, mode, args) {
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.toUpperCase().startsWith('AMAIL_')));
  Object.assign(env, { AMAIL_HOME: home, AMAIL_TERMINAL_ID: `device-${path.basename(home)}`,
    AMAIL_TELEMETRY: 'off', AMAIL_API_BASE: issuer, AMAIL_ISSUER: issuer,
    AMAIL_CLIENT_ID: `amail-device-test-${mode}`, AMAIL_REDIRECT_URI: '', SSL_CERT_FILE: certificate,
    NO_PROXY: 'localhost,127.0.0.1', no_proxy: 'localhost,127.0.0.1' });
  const child = spawn(binary, ['--machine', ...args], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] });
  const state = { child, stdout: '', stderr: '', lines: [], settled: false, env };
  state.done = new Promise((resolve, reject) => {
    child.on('error', reject);
    child.on('close', (code) => { state.settled = true; resolve(code); });
  });
  state.done.catch(() => {});
  child.stdout.on('data', (chunk) => {
    state.stdout += chunk.toString();
    state.lines = state.stdout.trim().split('\n').filter(Boolean).map((line) => {
      try { return JSON.parse(line); } catch { return null; }
    }).filter(Boolean);
  });
  child.stderr.on('data', (chunk) => { state.stderr += chunk.toString(); });
  return state;
}
async function until(predicate, label, timeout = 20000) {
  const deadline = Date.now() + timeout;
  while (!predicate()) {
    if (fixtureError) throw fixtureError;
    if (Date.now() > deadline) throw new Error(label);
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
}
async function finish(state, expected) {
  await until(() => state.settled, 'CLI did not complete');
  assert.equal(await state.done, expected, `Unexpected CLI status in ${phase}: ${state.stderr}`);
  for (const credential of [...credentials, ...grants.keys()]) {
    assert.ok(!state.stdout.includes(credential) && !state.stderr.includes(credential), 'Private protocol value in output');
  }
  assert.ok(!fixtureError, 'Fixture request failed');
  active = null;
  return state.lines;
}
async function localCommand(home, mode, args) {
  active = launch(home, mode, args);
  await until(() => /http:\/\/127\.0\.0\.1:\d+\/authorize\/[0-9a-f-]+/.test(active.stderr) || active.settled,
    'Expected operation approval');
  const url = active.stderr.match(/http:\/\/127\.0\.0\.1:\d+\/authorize\/[0-9a-f-]+/)?.[0];
  assert.ok(url, `Expected ordinary user-profile approval in ${phase}`);
  const page = await context.newPage();
  await page.goto(url);
  await page.getByRole('button', { name: 'Approve', exact: true }).click();
  await page.close();
  return finish(active, 0);
}
async function home(mode) {
  const value = path.join(workspace, mode);
  await mkdir(value);
  await writeFile(path.join(value, 'config.toml'), 'yolo = false\n', { mode: 0o600 });
  homes.push({ home: value, mode });
  return value;
}
async function startLogin(mode) {
  const directory = await home(mode);
  active = launch(directory, mode, ['auth', 'login', '--device-code', '--no-browser']);
  await until(() => active.lines.some((line) => line.user_code) || active.settled, 'Device instructions missing');
  const instruction = active.lines.find((line) => line.user_code);
  assert.ok(instruction, `Device instructions missing in ${phase}: ${active.stderr}`);
  assert.ok(!active.stderr.includes('/authorize/'), 'Remote login must not require loopback approval');
  const grant = [...grants.values()].find((item) => item.code === instruction.user_code);
  assert.ok(grant);
  return { directory, instruction, grant };
}
async function noSavedTokens(directory) {
  const names = await readdir(directory);
  assert.ok(!names.includes('auth.sqlite3'), 'Failed login must not persist credentials');
}

try {
  const { chromium } = await import(pathToFileURL(await realpath(values['browser-module'])).href);
  browser = await chromium.launch({ headless: true });
  context = await browser.newContext({ ignoreHTTPSErrors: true });
  context.setDefaultTimeout(15000);
  phase = 'approval-and-backoff';
  const success = await startLogin('success');
  const page = await context.newPage();
  await page.goto(success.instruction.verification_uri_complete);
  await page.getByText(`Code: ${success.instruction.user_code}`, { exact: true }).waitFor();
  assert.equal(success.grant.decision, null, 'Viewing must not approve');
  await until(() => success.grant.polls.length >= 2, 'Pending/slow_down polls missing');
  assert.ok(!active.settled);
  await page.screenshot({ path: path.join(output, 'synthetic-device-confirmation.png'), fullPage: true });
  await page.getByRole('button', { name: 'Approve', exact: true }).click();
  const result = await finish(active, 0);
  assert.equal(result.at(-1).authenticated, true);
  const polls = success.grant.polls;
  assert.ok(polls[0] - success.grant.started >= 950, 'First poll was early');
  assert.ok(polls[1] - polls[0] >= 950, 'Pending poll interval was shortened');
  assert.ok(polls[2] - polls[1] >= 5950, 'slow_down must add five seconds');
  const authPath = path.join(success.directory, 'auth.sqlite3');
  if (process.platform !== 'win32') assert.equal((await stat(authPath)).mode & 0o777, 0o600);
  for (const name of (await readdir(success.directory)).filter((name) => name.startsWith('auth.sqlite3'))) {
    const bytes = await readFile(path.join(success.directory, name));
    for (const value of credentials) assert.ok(!bytes.includes(Buffer.from(value)), 'Token persisted in plaintext');
  }
  phase = 'refresh-and-revoke';
  active = launch(success.directory, 'success', ['billing', 'status']);
  const billingState = active;
  const billing = await finish(active, 0);
  assert.ok(!billingState.stderr.includes('/authorize/'), 'Hosted billing must not need a loopback gate');
  assert.equal(billing.at(-1).synthetic, true);
  assert.equal(refreshes.length, 1, 'Expired access token must rotate once');
  const logout = await localCommand(success.directory, 'success', ['auth', 'logout']);
  assert.equal(logout.at(-1).authenticated, false);
  assert.deepEqual(revocations, [refreshes[0].current], 'Logout must revoke rotated refresh token');
  const status = await localCommand(success.directory, 'success', ['auth', 'status']);
  assert.equal(status.at(-1).authenticated, false);
  await page.close();

  phase = 'denial';
  const denial = await startLogin('denial');
  const deniedPage = await context.newPage();
  await deniedPage.goto(denial.instruction.verification_uri_complete);
  await deniedPage.getByRole('button', { name: 'Deny', exact: true }).click();
  await finish(active, 1);
  await noSavedTokens(denial.directory);
  await deniedPage.close();

  phase = 'server-expiry';
  const expired = await startLogin('server-expiry');
  const expiredState = active;
  await finish(active, 1);
  assert.ok(expiredState.stderr.includes('expired_token'));
  assert.ok(expiredState.stderr.includes('synthetic-correlation-id'));
  await noSavedTokens(expired.directory);

  phase = 'local-expiry';
  const deadline = await startLogin('local-expiry');
  await finish(active, 1);
  assert.equal(deadline.grant.polls.length, 0, 'No token request after local deadline');
  await noSavedTokens(deadline.directory);

  phase = 'cancellation';
  const cancelled = await startLogin('cancellation');
  const cancelledState = active;
  cancelledState.child.kill('SIGINT');
  await until(() => cancelledState.settled, 'Cancelled frontend did not stop');
  active = null;
  await new Promise((resolve) => setTimeout(resolve, 1250));
  const cancelledPage = await context.newPage();
  await cancelledPage.goto(cancelled.instruction.verification_uri_complete);
  await cancelledPage.getByRole('button', { name: 'Approve', exact: true }).click();
  await new Promise((resolve) => setTimeout(resolve, 1250));
  assert.equal(cancelled.grant.polls.length, 0, 'Disconnected frontend must stop daemon device polling');
  await noSavedTokens(cancelled.directory);
  await cancelledPage.close();

  phase = 'wrong-audience';
  const wrong = await startLogin('wrong-audience');
  const wrongPage = await context.newPage();
  await wrongPage.goto(wrong.instruction.verification_uri_complete);
  await wrongPage.getByRole('button', { name: 'Approve', exact: true }).click();
  await finish(active, 1);
  await noSavedTokens(wrong.directory);
  await wrongPage.close();
  phase = 'cleanup';
} finally {
  if (active && !active.settled) {
    active.child.kill();
    await active.done.catch(() => {});
  }
  for (const item of homes) {
    const stopped = launch(item.home, item.mode, ['daemon', 'stop']);
    await until(() => stopped.settled, 'Synthetic daemon cleanup timed out').catch(() => stopped.child.kill());
  }
  await context?.close();
  await browser?.close();
  await new Promise((resolve) => server.close(resolve));
  await rm(workspace, { recursive: true, force: true });
}
assert.equal(phase, 'cleanup');
await writeFile(path.join(output, 'acceptance.json'), JSON.stringify({
  schema: 'amail-device-acceptance/v1', outcome: 'passed', fixture: 'synthetic-https-identity',
  binary_sha256: createHash('sha256').update(await readFile(binary)).digest('hex'),
  checks: ['remote-device-login-no-loopback', 'explicit-browser-approval', 'first-poll-delay',
    'persistent-slow-down', 'nonce-free-rs256-id-token', 'encrypted-session', 'refresh-rotation',
    'rotated-refresh-revocation', 'denial', 'server-expiry-correlation', 'local-deadline', 'cancellation', 'wrong-audience'],
}, null, 2));
console.log('Synthetic native device journey passed; no deployed Identity or payment claim.');
