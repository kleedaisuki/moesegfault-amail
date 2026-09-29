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
import { Miniflare } from "miniflare";

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
function fakeNetwork(createResponse, listedRuleIds = [], runCron = false, cronRuleIds = listedRuleIds, backlogCount = 0) {
  const exchanges = [];
  let unexpected = 0;
  const add = (method, url, status, body) => {
    exchanges.push({ method, url, status, body, used: false });
  };
  const jwk = publicKey.export({ format: "jwk" });
  add("GET", `${issuer}/.well-known/openid-configuration`, 200, JSON.stringify({ issuer, jwks_uri: `${issuer}/jwks` }));
  add("GET", `${issuer}/jwks`, 200, JSON.stringify({ keys: [{ ...jwk, kid: "synthetic", alg: "RS256", use: "sig" }] }));
  const ruleListBody = (rules, recipient = address) => JSON.stringify({
      success: true,
      result: rules.map((item) => ({
        id: typeof item === "string" ? item : item.id,
        enabled: typeof item === "string" ? true : item.enabled,
        name: `amail ${recipient}`,
        actions: [{ type: "worker", value: ["synthetic-ingress"] }],
        matchers: [{ type: "literal", field: "to", value: recipient }],
      })),
      result_info: { total_pages: 1 },
    });
  add("GET", `${provider}${rulePath}?per_page=50&page=1`, 200, ruleListBody(listedRuleIds));
  if (runCron) {
    add("GET", `${provider}${rulePath}?per_page=50&page=1`, 200, ruleListBody(cronRuleIds));
    for (let n = 0; n < backlogCount; n++) {
      const recipient = `backlog-${String(n).padStart(2, "0")}@mail-staging.moesegfault.dev`;
      add("GET", `${provider}${rulePath}?per_page=50&page=1`, 200,
        ruleListBody([{ id: `backlog-rule-${n}`, enabled: false }], recipient));
    }
  }
  add("POST", `${provider}${rulePath}`, createResponse.status, createResponse.body);
  add("DELETE", `${provider}${rulePath}/synthetic-rule`, 200, JSON.stringify({ success: true }));
  add("DELETE", `${provider}${rulePath}/synthetic-extra`, 200, JSON.stringify({ success: true }));
  return {
    /** The only egress service available to the Worker; never forwards to fetch. */
    outboundService(request) {
      const exchange = exchanges.find((item) => !item.used && item.method === request.method && item.url === request.url);
      if (!exchange) {
        unexpected++;
        throw new Error("unexpected synthetic outbound request");
      }
      exchange.used = true;
      return new Response(exchange.body, {
        status: exchange.status,
        headers: { "content-type": "application/json" },
      });
    },
    pendingInterceptors() {
      return exchanges.filter((item) => !item.used);
    },
    assertNoUnexpected() {
      assert.equal(unexpected, 0, "unmatched outbound requests are forbidden");
    },
  };
}

/** Build a fresh local database and dispatch one real address-add invocation. */
async function exercise(createResponse, { failActivation = false, listedRuleIds = [], runCron = false, cronRuleIds = listedRuleIds, stalePending = false, markDeleting = false, oldProvisioning = false, flagActive = false, backlogCount = 0 } = {}) {
  const mock = fakeNetwork(createResponse, listedRuleIds, runCron, cronRuleIds, backlogCount);
  const mf = new Miniflare({
    cf: false,
    workers: [{
      name: "amail-synthetic",
      modules: true,
      scriptPath: path.join(worker, "build/worker/shim.mjs"),
      modulesRules: [{ type: "CompiledWasm", include: ["**/*.wasm"] }],
      // Stable v4's workerd supports dates only through 2026-08-06.
      compatibilityDate: "2026-08-06",
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
      outboundService: mock.outboundService,
    }],
  });
  try {
    const { MAIL_DB: db } = await mf.getBindings();
    const names = await readdir(path.join(worker, "migrations"));
    const migrations = names.filter((name) => /^\d{4}_.*\.sql$/.test(name)).sort();
    assert.ok(migrations.length >= 8, "address scheduling migration is required");
    for (let n = 0; n < migrations.length; n++) {
      const name = migrations[n];
      assert.equal(name.slice(0, 4), String(n + 1).padStart(4, "0"), "migrations must be contiguous");
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
    if (markDeleting) {
      await db.prepare("UPDATE addresses SET state='deleting',needs_reconcile=1,next_reconcile_at=-1 WHERE address=?1")
        .bind(address).run();
    }
    if (oldProvisioning) {
      await db.prepare("UPDATE addresses SET created_at=0 WHERE address=?1 AND state='provisioning'")
        .bind(address).run();
    }
    if (flagActive) {
      await db.prepare("UPDATE addresses SET needs_reconcile=1 WHERE address=?1 AND state='active'")
        .bind(address).run();
    }
    for (let n = 0; n < backlogCount; n++) {
      const recipient = `backlog-${String(n).padStart(2, "0")}@mail-staging.moesegfault.dev`;
      await db.prepare("INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,state,created_at) VALUES(?1,?2,'synthetic-issuer',?3,0,'provisioning',0)")
        .bind(recipient, `backlog-${n}`, `backlog-subject-${n}`).run();
    }
    if (runCron) await (await mf.getWorker()).scheduled();
    const rows = await db.prepare("SELECT state, cf_rule_id, needs_reconcile FROM addresses WHERE address=?1")
      .bind(address).all();
    const backlogScheduled = backlogCount === 0 ? null :
      (await db.prepare("SELECT COUNT(*) AS n FROM addresses WHERE local_part LIKE 'backlog-%' AND next_reconcile_at>0")
        .first()).n;
    const routeDeletesPending = mock.pendingInterceptors().filter((item) => item.method === "DELETE").length;
    const routeCreatesPending = mock.pendingInterceptors().filter((item) => item.method === "POST").length;
    mock.assertNoUnexpected();
    return { response, body, rows: rows.results, routeDeletesPending, routeCreatesPending, backlogScheduled };
  } finally {
    await mf.dispose();
  }
}

test("a provider 200 body activates D1 and produces a complete API response", async () => {
  const { response, body, rows } = await exercise({
    status: 200,
    body: JSON.stringify({ success: true, result: { id: "synthetic-rule", enabled: true } }),
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

test("a create response naming a disabled rule never acknowledges activation", async () => {
  const { response, body, rows, routeDeletesPending } = await exercise({
    status: 200,
    body: JSON.stringify({ success: true, result: { id: "synthetic-rule", enabled: false } }),
  });
  assert.equal(response.status, 503);
  assert.equal(body.code, "routing_unavailable");
  assert.deepEqual(rows, [{ state: "provisioning", cf_rule_id: null, needs_reconcile: 0 }]);
  assert.equal(routeDeletesPending, 2, "uncertain create keeps the provider side effect");
});

test("a D1 activation error leaves the created provider route for reconciliation", async () => {
  const { response, body, rows, routeDeletesPending } = await exercise({
    status: 200,
    body: JSON.stringify({ success: true, result: { id: "synthetic-rule", enabled: true } }),
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
    body: JSON.stringify({ success: true, result: { id: "unused-create", enabled: true } }),
  }, { listedRuleIds: ["synthetic-rule", "synthetic-extra"] });
  assert.equal(response.status, 201);
  assert.deepEqual(rows, [{ state: "active", cf_rule_id: "synthetic-rule", needs_reconcile: 1 }]);
  assert.equal(routeDeletesPending, 2, "add must not delete either exact route before reconciliation");
});

test("Cron prunes only the extra exact rule after active ID confirmation", async () => {
  const { response, rows, routeDeletesPending } = await exercise({
    status: 200,
    body: JSON.stringify({ success: true, result: { id: "unused-create", enabled: true } }),
  }, { listedRuleIds: ["synthetic-rule", "synthetic-extra"], runCron: true });
  assert.equal(response.status, 201);
  assert.deepEqual(rows, [{ state: "active", cf_rule_id: "synthetic-rule", needs_reconcile: 0 }]);
  assert.equal(routeDeletesPending, 1, "Cron must retain the chosen active route");
});

test("Cron never deletes an exact route from a stale flagged pending row", async () => {
  const { response, rows, routeDeletesPending } = await exercise({
    status: 200,
    body: JSON.stringify({ success: true, result: { id: "unused-create", enabled: true } }),
  }, { listedRuleIds: ["synthetic-rule"], runCron: true, stalePending: true });
  assert.equal(response.status, 201);
  assert.deepEqual(rows, [{ state: "provisioning", cf_rule_id: null, needs_reconcile: 1 }]);
  assert.equal(routeDeletesPending, 2, "pending is never a route-deletion state");
});

test("a disabled exact rule blocks activation and duplicate POST even after provisioning ages", async () => {
  const { response, body, rows, routeCreatesPending, routeDeletesPending } = await exercise({
    status: 200,
    body: JSON.stringify({ success: true, result: { id: "unused-create", enabled: true } }),
  }, { listedRuleIds: [{ id: "synthetic-rule", enabled: false }], runCron: true, oldProvisioning: true });
  assert.equal(response.status, 503);
  assert.equal(body.code, "routing_unavailable");
  assert.equal(routeCreatesPending, 1, "an owned disabled rule must not trigger a second POST");
  assert.equal(routeDeletesPending, 2, "provisioning does not delete an owned rule");
  assert.deepEqual(rows, [{ state: "provisioning", cf_rule_id: null, needs_reconcile: 0 }]);
});

test("an exact rule with unknown enabled state is also not delivery evidence", async () => {
  const { response, body, rows, routeCreatesPending } = await exercise({
    status: 200,
    body: JSON.stringify({ success: true, result: { id: "unused-create", enabled: true } }),
  }, { listedRuleIds: [{ id: "synthetic-rule" }] });
  assert.equal(response.status, 503);
  assert.equal(body.code, "routing_unavailable");
  assert.equal(routeCreatesPending, 1);
  assert.deepEqual(rows, [{ state: "provisioning", cf_rule_id: null, needs_reconcile: 0 }]);
});

test("an enabled exact rule wins over disabled remnants and Cron prunes only the remnant", async () => {
  const { response, rows, routeCreatesPending, routeDeletesPending } = await exercise({
    status: 200,
    body: JSON.stringify({ success: true, result: { id: "unused-create", enabled: true } }),
  }, { listedRuleIds: [{ id: "synthetic-extra", enabled: false }, "synthetic-rule"], runCron: true });
  assert.equal(response.status, 201);
  assert.equal(routeCreatesPending, 1);
  assert.deepEqual(rows, [{ state: "active", cf_rule_id: "synthetic-rule", needs_reconcile: 0 }]);
  assert.equal(routeDeletesPending, 1, "the enabled committed rule must remain");
});

test("Cron retains a flagged active row whose committed rule has become disabled", async () => {
  const { response, rows, routeDeletesPending } = await exercise({
    status: 200,
    body: JSON.stringify({ success: true, result: { id: "unused-create", enabled: true } }),
  }, { listedRuleIds: ["synthetic-rule"], runCron: true, cronRuleIds: [{ id: "synthetic-rule", enabled: false }, "synthetic-extra"], flagActive: true });
  assert.equal(response.status, 201);
  assert.deepEqual(rows, [{ state: "active", cf_rule_id: "synthetic-rule", needs_reconcile: 1 }]);
  assert.equal(routeDeletesPending, 2, "drift must not delete either exact route until state-aware repair");
});

test("deletion still removes an owned disabled route before retiring its row", async () => {
  const { response, rows, routeDeletesPending, routeCreatesPending } = await exercise({
    status: 200,
    body: JSON.stringify({ success: true, result: { id: "unused-create", enabled: true } }),
  }, { listedRuleIds: [{ id: "synthetic-rule", enabled: false }], runCron: true, markDeleting: true });
  assert.equal(response.status, 503);
  assert.deepEqual(rows, [{ state: "retired", cf_rule_id: null, needs_reconcile: 1 }]);
  assert.equal(routeDeletesPending, 1, "Cron must remove the disabled owned rule");
  assert.equal(routeCreatesPending, 1);
});

test("thirty stalled provisioning rows cannot starve an urgent disabled-rule deletion", async () => {
  const { response, rows, routeDeletesPending, routeCreatesPending, backlogScheduled } = await exercise({
    status: 200,
    body: JSON.stringify({ success: true, result: { id: "unused-create", enabled: true } }),
  }, { listedRuleIds: [{ id: "synthetic-rule", enabled: false }], runCron: true, markDeleting: true, backlogCount: 30 });
  assert.equal(response.status, 503);
  assert.deepEqual(rows, [{ state: "retired", cf_rule_id: null, needs_reconcile: 1 }]);
  assert.equal(routeDeletesPending, 1, "the urgent deletion must execute in the same Cron batch");
  assert.equal(routeCreatesPending, 1, "stalled rows must never trigger duplicate POST");
  assert.equal(backlogScheduled, 29, "bounded batch advances only visited rows; the remaining row is next due");
});
