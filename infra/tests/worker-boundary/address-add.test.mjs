/**
 * Execute the production Rust/Wasm Worker through workerd with fake OIDC and
 * Routing HTTP responses and local D1. No request can reach a real provider.
 */
import assert from "node:assert/strict";
import { generateKeyPairSync, sign } from "node:crypto";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { Miniflare, createFetchMock } from "miniflare";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../../..");
const worker = path.join(root, "crates/mail-worker");
const issuer = "https://identity-staging.moesegfault.dev";
const provider = "https://api.cloudflare.com";
const address = "synthetic-only@mail-staging.moesegfault.dev";
const rulePath = "/client/v4/zones/synthetic-zone/email/routing/rules";
const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });

/** Sign a local-only access token so the real OIDC verifier stays in the path. */
function accessToken() {
  const header = Buffer.from(JSON.stringify({ alg: "RS256", typ: "JWT", kid: "synthetic" })).toString("base64url");
  const payload = Buffer.from(JSON.stringify({
    iss: issuer,
    sub: "synthetic-subject",
    aud: "amail-cli-staging",
    exp: Math.floor(Date.now() / 1000) + 300,
    token_use: "access",
  })).toString("base64url");
  const input = `${header}.${payload}`;
  return `${input}.${sign("RSA-SHA256", Buffer.from(input), privateKey).toString("base64url")}`;
}

/** Register strict one-use network fixtures; unmatched egress is prohibited. */
function fakeNetwork(createResponse, listedRuleIds = [], runCron = false) {
  const mock = createFetchMock();
  mock.disableNetConnect();
  const jwk = publicKey.export({ format: "jwk" });
  mock.get(issuer).intercept({ method: "GET", path: "/.well-known/openid-configuration" })
    .reply(200, JSON.stringify({ issuer, jwks_uri: `${issuer}/jwks` }), { headers: { "content-type": "application/json" } });
  mock.get(issuer).intercept({ method: "GET", path: "/jwks" })
    .reply(200, JSON.stringify({ keys: [{ ...jwk, kid: "synthetic", alg: "RS256", use: "sig" }] }), { headers: { "content-type": "application/json" } });
  const ruleListBody = JSON.stringify({
      success: true,
      result: listedRuleIds.map((id) => ({
        id,
        name: `amail ${address}`,
        actions: [{ type: "worker", value: ["synthetic-ingress"] }],
        matchers: [{ type: "literal", field: "to", value: address }],
      })),
      result_info: { total_pages: 1 },
    });
  mock.get(provider).intercept({ method: "GET", path: `${rulePath}?per_page=50&page=1` })
    .reply(200, ruleListBody, { headers: { "content-type": "application/json" } });
  if (runCron) {
    mock.get(provider).intercept({ method: "GET", path: `${rulePath}?per_page=50&page=1` })
      .reply(200, ruleListBody, { headers: { "content-type": "application/json" } });
  }
  mock.get(provider).intercept({ method: "POST", path: rulePath })
    .reply(createResponse.status, createResponse.body, { headers: { "content-type": "application/json" } });
  mock.get(provider).intercept({ method: "DELETE", path: `${rulePath}/synthetic-rule` })
    .reply(200, JSON.stringify({ success: true }));
  mock.get(provider).intercept({ method: "DELETE", path: `${rulePath}/synthetic-extra` })
    .reply(200, JSON.stringify({ success: true }));
  return mock;
}

/** Build a fresh local database and dispatch one real address-add invocation. */
async function exercise(createResponse, { failActivation = false, listedRuleIds = [], runCron = false, stalePending = false } = {}) {
  const mock = fakeNetwork(createResponse, listedRuleIds, runCron);
  const mf = new Miniflare({
    modules: true,
    scriptPath: path.join(worker, "build/worker/shim.mjs"),
    modulesRules: [{ type: "CompiledWasm", include: ["**/*.wasm"] }],
    compatibilityDate: "2026-09-25",
    bindings: {
      IDENTITY_ISSUER: issuer,
      OIDC_CLIENT_ID: "amail-cli-staging",
      CF_ZONE_ID: "synthetic-zone",
      CF_EMAIL_ROUTING_TOKEN: "synthetic-token",
      MAIL_DOMAIN: "mail-staging.moesegfault.dev",
      EMAIL_INGRESS_WORKER_NAME: "synthetic-ingress",
      ADDRESS_DIAGNOSTICS: "v1",
    },
    d1Databases: ["MAIL_DB"],
    fetchMock: mock,
  });
  try {
    const { MAIL_DB: db } = await mf.getBindings();
    const names = await readdir(path.join(worker, "migrations"));
    for (let n = 1; n <= 7; n++) {
      const prefix = String(n).padStart(4, "0");
      const name = names.find((entry) => entry.startsWith(`${prefix}_`));
      assert.ok(name, `missing migration ${prefix}`);
      await db.exec(await readFile(path.join(worker, "migrations", name), "utf8"));
    }
    if (failActivation) {
      // Fail only the post-provider activation, not allocation or claiming.
      await db.exec(`CREATE TRIGGER fail_activation BEFORE UPDATE ON addresses
        WHEN NEW.state='active' BEGIN SELECT RAISE(FAIL, 'synthetic activation failure'); END`);
    }
    const response = await mf.dispatchFetch("https://mail-staging.moesegfault.dev/v1/addresses", {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken()}`, "Content-Type": "application/json" },
      body: JSON.stringify({ local_part: "synthetic-only" }),
    });
    const body = await response.json();
    if (stalePending) {
      await db.prepare("UPDATE addresses SET state='pending',cf_rule_id=NULL,needs_reconcile=1 WHERE address=?1")
        .bind(address).run();
    }
    if (runCron) await (await mf.getWorker()).scheduled();
    const rows = await db.prepare("SELECT state, cf_rule_id, needs_reconcile FROM addresses WHERE address=?1")
      .bind(address).all();
    const routeDeletesPending = mock.pendingInterceptors().filter((item) => item.method === "DELETE").length;
    return { response, body, rows: rows.results, routeDeletesPending };
  } finally {
    await mf.dispose();
    await mock.close();
  }
}

test("a provider 200 body activates D1 and produces a complete API response", async () => {
  const { response, body, rows } = await exercise({
    status: 200,
    body: JSON.stringify({ success: true, result: { id: "synthetic-rule" } }),
  });
  assert.equal(response.status, 201);
  assert.equal(response.headers.get("x-amail-address-diag"), "v1:success:none:0:0");
  assert.equal(body.address, address);
  assert.equal(body.state, "active");
  assert.deepEqual(rows, [{ state: "active", cf_rule_id: "synthetic-rule", needs_reconcile: 0 }]);
});

test("an ambiguous 200 body never acknowledges activation or blindly retries", async () => {
  const { response, body, rows } = await exercise({
    status: 200,
    body: JSON.stringify({ success: true }),
  });
  assert.equal(response.status, 503);
  assert.equal(response.headers.get("x-amail-address-diag"), "v1:routing_create:decode:200:0");
  assert.equal(body.code, "routing_unavailable");
  assert.deepEqual(rows, [{ state: "provisioning", cf_rule_id: null, needs_reconcile: 0 }]);
});

test("a D1 activation error leaves the created provider route for reconciliation", async () => {
  const { response, body, rows, routeDeletesPending } = await exercise({
    status: 200,
    body: JSON.stringify({ success: true, result: { id: "synthetic-rule" } }),
  }, { failActivation: true });
  assert.equal(response.status, 503);
  assert.equal(response.headers.get("x-amail-address-diag"), "v1:d1_readback:d1:0:0");
  assert.equal(body.code, "address_provision_unknown");
  assert.deepEqual(rows, [{ state: "provisioning", cf_rule_id: null, needs_reconcile: 0 }]);
  assert.equal(routeDeletesPending, 2, "activation uncertainty must not delete the route");
});

test("duplicate exact routes are preserved until the active rule is durable", async () => {
  const { response, rows, routeDeletesPending } = await exercise({
    status: 200,
    body: JSON.stringify({ success: true, result: { id: "unused-create" } }),
  }, { listedRuleIds: ["synthetic-rule", "synthetic-extra"] });
  assert.equal(response.status, 201);
  assert.deepEqual(rows, [{ state: "active", cf_rule_id: "synthetic-rule", needs_reconcile: 1 }]);
  assert.equal(routeDeletesPending, 2, "add must not delete either exact route before reconciliation");
});

test("Cron prunes only the extra exact rule after active ID confirmation", async () => {
  const { response, rows, routeDeletesPending } = await exercise({
    status: 200,
    body: JSON.stringify({ success: true, result: { id: "unused-create" } }),
  }, { listedRuleIds: ["synthetic-rule", "synthetic-extra"], runCron: true });
  assert.equal(response.status, 201);
  assert.deepEqual(rows, [{ state: "active", cf_rule_id: "synthetic-rule", needs_reconcile: 0 }]);
  assert.equal(routeDeletesPending, 1, "Cron must retain the chosen active route");
});

test("Cron never deletes an exact route from a stale flagged pending row", async () => {
  const { response, rows, routeDeletesPending } = await exercise({
    status: 200,
    body: JSON.stringify({ success: true, result: { id: "unused-create" } }),
  }, { listedRuleIds: ["synthetic-rule"], runCron: true, stalePending: true });
  assert.equal(response.status, 201);
  assert.deepEqual(rows, [{ state: "provisioning", cf_rule_id: null, needs_reconcile: 1 }]);
  assert.equal(routeDeletesPending, 2, "pending is never a route-deletion state");
});
