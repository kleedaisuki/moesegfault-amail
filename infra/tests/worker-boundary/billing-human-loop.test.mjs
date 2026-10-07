/** Real Rust/Wasm Billing boundary; synthetic Identity/Billing, no external egress. */
import assert from "node:assert/strict";
import { generateKeyPairSync, sign, createHash } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { Miniflare } from "miniflare";
import { applyMigrations } from "./migration-fixture.mjs";
import { apiVersionHeaders } from "./api-version.mjs";
import { workerModuleRules } from "./worker-module-rules.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const issuer = "https://identity-staging.moesegfault.dev";
const billing = "https://billing-staging.moesegfault.dev";
const origin = "https://mail-staging.moesegfault.dev";
const subject = "synthetic-billing-owner";
const key = "9e227a38-a729-420e-b50a-503f854e553d";
const remote = "abcdefghijklmnopqrstuvwx01234567";
const authorizationUrl = `https://subscribe-staging.moesegfault.dev/amail/authorize/${remote}`;
const traceId = "0123456789abcdef0123456789abcdef";
const cliSpan = "abcdef0123456789";
const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });

/** The real verifier checks a locally signed, audience-bound access credential. */
function token(owner) {
  const encode = value => Buffer.from(JSON.stringify(value)).toString("base64url");
  const input = `${encode({ alg: "RS256", kid: "billing-fixture", typ: "JWT" })}.${encode({
    iss: issuer, sub: owner, aud: "amail-cli-staging", token_use: "access",
    exp: Math.floor(Date.now() / 1000) + 600,
  })}`;
  return `${input}.${sign("RSA-SHA256", Buffer.from(input), privateKey).toString("base64url")}`;
}

/** Independent encoding of the public domain-separated immutable owner contract. */
function ownerId() {
  const hash = createHash("sha256").update("amail-owner-v020\0");
  for (const value of [issuer, subject]) {
    const length = Buffer.alloc(8); length.writeBigUInt64BE(BigInt(Buffer.byteLength(value)));
    hash.update(length).update(value);
  }
  return hash.digest("hex");
}

/** A fresh native Worker/database with a closed, inspectable service transport. */
async function fixture(run, { traceCapture = false } = {}) {
  const calls = [], records = [], waiters = [];
  let remoteState = "pending", failure = false, incorrectOwner = false, legacyCurrency = false;
  const jwk = publicKey.export({ format: "jwk" });
  const binding = () => ({ owner_id: incorrectOwner ? "foreign-owner" : ownerId(), product_id: "amail",
    plan_id: "amail-lite", currency: legacyCurrency ? "CNY" : "USD",
    contract_version: legacyCurrency ? "amail-v0.2.0" : "amail-v0.2.0-usd-v1",
    overage_budget_micros: 5_000_000, valid_until: Math.floor(Date.now() / 1000) + 86400,
    updated_at: Math.floor(Date.now() / 1000), authorization_id: remote });
  const workers = [{
    name: "api", modules: true, compatibilityDate: "2026-08-06",
    scriptPath: path.join(root, "crates/mail-worker/entry/api.mjs"), modulesRoot: root,
    modulesRules: workerModuleRules, d1Databases: ["MAIL_DB"],
    ...(traceCapture ? { queueProducers: { TRACE_EVENTS: "billing-fixture-traces" } } : {}),
    bindings: { IDENTITY_ISSUER: issuer, OIDC_CLIENT_ID: "amail-cli-staging",
      BILLING_BASE_URL: billing, BILLING_SUBSCRIBE_ORIGIN: "https://subscribe-staging.moesegfault.dev",
      BILLING_RETURN_URL: "https://amail-staging.moesegfault.dev/billing/return",
      BILLING_SERVICE_KEY: "synthetic-service-credential" },
    async outboundService(request) {
      if (request.url === `${issuer}/.well-known/openid-configuration` && request.method === "GET") {
        return Response.json({ issuer, jwks_uri: `${issuer}/jwks` });
      }
      if (request.url === `${issuer}/jwks` && request.method === "GET") {
        return Response.json({ keys: [{ ...jwk, kid: "billing-fixture", alg: "RS256", use: "sig" }] });
      }
      assert.equal(new URL(request.url).origin, billing, "no unexpected real provider egress");
      assert.equal(request.headers.get("Authorization"), "Bearer synthetic-service-credential");
      assert.match(request.headers.get("traceparent"), /^00-0123456789abcdef0123456789abcdef-[0-9a-f]{16}-01$/);
      const body = request.method === "POST" ? await request.json() : null;
      calls.push({ method: request.method, path: new URL(request.url).pathname,
        key: request.headers.get("Idempotency-Key"), body, traceparent: request.headers.get("traceparent") });
      if (failure) return Response.json({ private: "SYNTHETIC_PRIVATE_PROVIDER_ERROR" }, { status: 503 });
      if (request.method === "POST" && request.url === `${billing}/v1/service/amail/authorizations`) {
        assert.equal(body.owner_id, ownerId());
        assert.equal(body.currency, "USD");
        assert.equal(body.overage_budget_micros, 0, "agent cannot grant itself spending consent");
        return Response.json({ authorization_id: remote, authorization_url: authorizationUrl,
          expires_at: Math.floor(Date.now() / 1000) + 1800 });
      }
      if (request.method === "GET" && request.url === `${billing}/v1/service/amail/authorizations/${remote}`) {
        return Response.json({ authorization: { id: remote, owner_id: ownerId(), status: remoteState },
          binding: remoteState === "approved" ? binding() : null });
      }
      if (request.method === "GET" && request.url === `${billing}/v1/service/amail/accounts/${ownerId()}`) {
        return Response.json({ binding: binding() });
      }
      assert.fail("unexpected synthetic Billing route");
    },
  }];
  if (traceCapture) workers.push({
    name: "capture", modules: true, compatibilityDate: "2026-08-06",
    script: `export default { async queue(batch, env) {
      await env.CAPTURE.fetch("https://synthetic.invalid/traces", {
        method: "POST", body: JSON.stringify(batch.messages.map(message => message.body)) });
      batch.ackAll();
    } };`,
    queueConsumers: { "billing-fixture-traces": { maxBatchSize: 1, maxBatchTimeout: 1, maxRetries: 0 } },
    serviceBindings: { CAPTURE: async request => {
      records.push(...await request.json());
      for (const notify of waiters) notify();
      return new Response(null, { status: 204 });
    } },
    outboundService() { throw new Error("synthetic observer forbids network egress"); },
  });
  const mf = new Miniflare({ cf: false, workers });
  try {
    const { MAIL_DB: db } = await mf.getBindings();
    await applyMigrations(db, path.join(root, "crates/mail-worker/migrations"));
    const request = (pathname, { method = "GET", body, owner = subject, idem = key } = {}) =>
      mf.dispatchFetch(`${origin}${pathname}`, { method,
        headers: { ...apiVersionHeaders, Authorization: `Bearer ${token(owner)}`,
          "Content-Type": "application/json", "Idempotency-Key": idem,
          traceparent: `00-${traceId}-${cliSpan}-01` },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
    const create = () => request("/v1/billing/sessions", { method: "POST", body: { action: "subscribe", plan: "lite" } });
    const account = () => db.prepare("SELECT plan,overage_budget_micros FROM resource_accounts WHERE owner_iss=?1 AND owner_sub=?2")
      .bind(issuer, subject).first();
    const traces = async () => {
      let timer;
      try {
        await Promise.race([new Promise(resolve => {
          const check = () => {
            if (records.some(row => row.phase === "billing_http") && records.some(row => row.phase === "request_exit")) resolve();
          };
          waiters.push(check); check();
        }), new Promise((_, reject) => { timer = setTimeout(() => reject(new Error("native Billing trace delivery missing")), 10000); })]);
      } finally { clearTimeout(timer); }
      return records;
    };
    await run({ request, create, account, db, calls, traces,
      state: value => { remoteState = value; }, fail: value => { failure = value; },
      wrongOwner: value => { incorrectOwner = value; },
      legacyCurrency: value => { legacyCurrency = value; } });
  } finally { await mf.dispose(); }
}

test("agent proposal stays Free until authoritative human receipt, and replay is stable", async () => fixture(async ({ create, request, account, calls, state }) => {
  const response = await create();
  assert.equal(response.status, 200);
  const intent = await response.json();
  assert.equal(intent.session_id, key);
  assert.equal(intent.state, "pending");
  assert.equal(intent.authorization_url, authorizationUrl);
  assert.deepEqual(await account(), { plan: "free", overage_budget_micros: 0 });
  assert.equal((await create()).status, 200);
  assert.equal(calls.filter(call => call.method === "POST").length, 1);
  assert.equal((await request(`/v1/billing/sessions/${key}`)).status, 200);
  assert.deepEqual(await account(), { plan: "free", overage_budget_micros: 0 });
  state("approved");
  assert.equal((await (await request(`/v1/billing/sessions/${key}`)).json()).state, "completed");
  assert.deepEqual(await account(), { plan: "lite", overage_budget_micros: 5_000_000 });
  const count = calls.length;
  assert.equal((await (await request(`/v1/billing/sessions/${key}`)).json()).state, "completed");
  assert.equal(calls.length, count, "terminal replay never creates a second financial action");
  assert.equal(calls[0].key, key);
}));

test("denied and expired human intents cannot grant paid resource allowances", async () => {
  for (const terminal of ["denied", "expired"]) await fixture(async ({ create, request, account, state }) => {
    assert.equal((await create()).status, 200);
    state(terminal);
    const response = await request(`/v1/billing/sessions/${key}`);
    assert.equal(response.status, 200);
    assert.equal((await response.json()).state, terminal === "denied" ? "cancelled" : terminal);
    assert.deepEqual(await account(), { plan: "free", overage_budget_micros: 0 });
  });
});

test("cross-owner polling and forged receipt never transfer an entitlement", async () => fixture(async ({ create, request, account, calls, state, wrongOwner }) => {
  assert.equal((await create()).status, 200);
  const count = calls.length;
  assert.equal((await request(`/v1/billing/sessions/${key}`, { owner: "foreign-owner" })).status, 404);
  assert.equal(calls.length, count, "unknown local owner never queries another receipt");
  state("approved"); wrongOwner(true);
  assert.equal((await request(`/v1/billing/sessions/${key}`)).status, 503);
  assert.deepEqual(await account(), { plan: "free", overage_budget_micros: 0 });
}));

test("uncertain service failure retains intent and reuses the original creation key", async () => fixture(async ({ create, account, calls, fail }) => {
  fail(true);
  const response = await create();
  assert.equal(response.status, 503);
  assert.doesNotMatch(await response.text(), /SYNTHETIC_PRIVATE_PROVIDER_ERROR|synthetic-service-credential/);
  fail(false);
  assert.equal((await create()).status, 200);
  assert.equal(calls.length, 2);
  assert.equal(calls[0].key, calls[1].key);
  assert.deepEqual(calls[0].body, calls[1].body);
  assert.deepEqual(await account(), { plan: "free", overage_budget_micros: 0 });
}));

test("CLI-to-Mail-to-Billing causality uses the exact native retained client span", async () => fixture(async ({ create, calls, traces }) => {
  assert.equal((await create()).status, 200);
  const records = await traces();
  const dependency = records.find(row => row.phase === "billing_http");
  const server = records.find(row => row.phase === "request_exit");
  assert.equal(server.trace_id, traceId);
  assert.equal(server.parent_span_id, cliSpan);
  assert.equal(dependency.trace_id, traceId);
  assert.equal(dependency.parent_span_id, server.span_id);
  assert.notEqual(dependency.span_id, server.span_id);
  assert.equal(calls[0].traceparent, `00-${traceId}-${dependency.span_id}-01`);
  assert.equal(dependency.operation, "billing_session_create");
  for (const record of [server, dependency]) {
    assert.ok(Number.isInteger(record.occurred_at_ms));
    assert.ok(Number.isInteger(record.duration_ms) && record.duration_ms >= 0);
  }
  assert.doesNotMatch(JSON.stringify(records), /synthetic-service-credential|amail\/authorize|synthetic-billing-owner|SYNTHETIC_PRIVATE/);
}, { traceCapture: true }));

/** Historical paid rights remain usable; a CNY approval never grants USD spending. */
test("legacy CNY authority preserves Lite access but requires fresh USD spending consent", async () => fixture(async ({ create, request, account, state, legacyCurrency }) => {
  assert.equal((await create()).status, 200);
  state("approved"); legacyCurrency(true);
  assert.equal((await request(`/v1/billing/sessions/${key}`)).status, 200);
  assert.deepEqual(await account(), { plan: "lite", overage_budget_micros: 0 });
  const response = await request("/v1/billing");
  assert.equal(response.status, 200);
  const status = await response.json();
  assert.equal(status.account.currency, "USD");
  assert.equal(status.rates.currency, "USD");
  assert.equal(status.rates.outbound_micros, 1000);
  assert.equal(status.rates.storage_gb_month_micros, 150000);
  assert.equal(status.rates.address_month_micros, 500000);
}));
