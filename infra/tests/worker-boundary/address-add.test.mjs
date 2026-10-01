/**
 * Execute the production Rust/Wasm Worker through workerd with fake OIDC and
 * Routing HTTP responses and local D1. No request can reach a real provider.
 */
import assert from "node:assert/strict";
import { generateKeyPairSync, sign } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { Miniflare } from "miniflare";
import { applyMigrations } from "./migration-fixture.mjs";
import { workerModuleRules } from "./worker-module-rules.mjs";

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
        source: "api",
        enabled: typeof item === "string" ? true : item.enabled,
        name: `amail ${recipient}`,
        actions: [{ type: "worker", value: ["synthetic-ingress"] }],
        matchers: [{ type: "literal", field: "to", value: recipient }],
      })),
      result_info: { total_pages: 1 },
    });
  add("GET", `${provider}${rulePath}?per_page=50&page=1`, 200, ruleListBody(listedRuleIds));
  if (runCron) {
    const cronRules = JSON.parse(ruleListBody(cronRuleIds)).result;
    for (let n = 0; n < backlogCount; n++) {
      const recipient = `backlog-${String(n).padStart(2, "0")}@mail-staging.moesegfault.dev`;
      cronRules.push(JSON.parse(ruleListBody([{ id: `backlog-rule-${n}`, enabled: false }], recipient)).result[0]);
    }
    add("GET", `${provider}${rulePath}?per_page=50&page=1`, 200,
      JSON.stringify({ success: true, result: cronRules, result_info: { total_pages: 1 } }));
    for (const rule of cronRules) {
      add("GET", `${provider}${rulePath}/${rule.id}`, 200, JSON.stringify({ success: true, result: rule }));
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
      modulesRoot: path.join(worker, "build"),
      modulesRules: workerModuleRules,
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
    await applyMigrations(db, path.join(worker, "migrations"));
    if (failActivation) {
      // Fail only the post-provider activation, not allocation or claiming.
      await db.exec("CREATE TRIGGER fail_activation BEFORE UPDATE ON addresses " +
        "WHEN NEW.state='active' BEGIN SELECT RAISE(FAIL, 'synthetic activation failure'); END;");
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
/** Construct one strictly single-purpose API-managed synthetic route. */
function managedRule(id, recipient = address, overrides = {}) {
  return {
    id, source: "api", enabled: true, name: `amail ${recipient}`,
    actions: [{ type: "worker", value: ["synthetic-ingress"] }],
    matchers: [{ type: "literal", field: "to", value: recipient }],
    ...overrides,
  };
}

/**
 * Run real scheduled Rust/Wasm against a persistent, entirely synthetic provider.
 * Routes can materialize independently of a creator continuation; every DELETE
 * asserts that an immediately preceding scoped GET validated the same provider ID.
 */
async function withProvider({ rules = [], listPage, getRule, beforeDelete, createRule, deleteReply } = {}, body) {
  const store = new Map(rules.map((rule) => [rule.id, structuredClone(rule)]));
  const calls = [];
  let unexpected = 0;
  const jwk = publicKey.export({ format: "jwk" });
  let lastGet = null;
  const json = (value, status = 200) => new Response(JSON.stringify(value), {
    status, headers: { "content-type": "application/json" },
  });
  const outboundService = async (request) => {
    const url = new URL(request.url);
    calls.push({ method: request.method, path: url.pathname, page: url.searchParams.get("page") });
    if (request.method === "GET" && request.url === `${issuer}/.well-known/openid-configuration`)
      return json({ issuer, jwks_uri: `${issuer}/jwks` });
    if (request.method === "GET" && request.url === `${issuer}/jwks`)
      return json({ keys: [{ ...jwk, kid: "synthetic", alg: "RS256", use: "sig" }] });
    if (url.origin === provider && url.pathname === rulePath && request.method === "POST" && createRule)
      return await createRule(request, store, json);
    if (url.origin === provider && url.pathname === rulePath && request.method === "GET") {
      assert.equal(url.searchParams.get("per_page"), "50");
      const page = Number(url.searchParams.get("page"));
      assert.ok(page >= 1 && page <= 10, "inventory never fetches an eleventh page");
      lastGet = null;
      if (listPage) return await listPage(page, store, json);
      const items = [...store.values()];
      const result = items.slice((page - 1) * 50, page * 50);
      return json({ success: true, result, result_info: {
        page, per_page: 50, count: result.length, total_count: items.length,
        total_pages: Math.max(1, Math.ceil(items.length / 50)),
      } });
    }
    if (url.origin === provider && url.pathname.startsWith(`${rulePath}/`)) {
      const id = decodeURIComponent(url.pathname.slice(rulePath.length + 1));
      if (request.method === "GET") {
        lastGet = id;
        if (getRule) return await getRule(id, store, json);
        return store.has(id) ? json({ success: true, result: store.get(id) }) :
          json({ success: false, errors: [{ code: 1002 }] }, 404);
      }
      if (request.method === "DELETE") {
        assert.equal(lastGet, id, "every destructive ID request follows its scoped GET");
        lastGet = null;
        if (beforeDelete) await beforeDelete(id);
        if (deleteReply) return await deleteReply(id, store, json);
        assert.ok(store.delete(id), "a synthetic ID cannot be blindly deleted twice");
        return json({ success: true, result: { id } });
      }
    }
    unexpected++;
    throw new Error("unmatched synthetic provider egress");
  };
  const mf = new Miniflare({
    cf: false,
    workers: [{
      name: "amail-synthetic", modules: true,
      scriptPath: path.join(worker, "build/worker/shim.mjs"),
      modulesRoot: path.join(worker, "build"), modulesRules: workerModuleRules,
      compatibilityDate: "2026-08-06",
      bindings: {
        IDENTITY_ISSUER: issuer, OIDC_CLIENT_ID: "amail-cli-staging",
        CF_ZONE_ID: "synthetic-zone", CF_EMAIL_ROUTING_TOKEN: "synthetic-token",
        MAIL_DOMAIN: "mail-staging.moesegfault.dev",
        EMAIL_INGRESS_WORKER_NAME: "synthetic-ingress", ADDRESS_DIAGNOSTICS: "v1",
      },
      d1Databases: ["MAIL_DB"], outboundService,
    }],
  });
  try {
    const { MAIL_DB: db } = await mf.getBindings();
    await applyMigrations(db, path.join(worker, "migrations"));
    const insert = async (recipient, { state = "retired", marker = 0, saved = null, due = 0, ownerSub } = {}) => {
      const local = recipient.split("@")[0];
      await db.prepare("INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,state,created_at,cf_rule_id,needs_reconcile,next_reconcile_at) VALUES(?1,?2,?3,?4,0,?5,0,?6,?7,?8)")
        .bind(recipient, local, issuer, ownerSub ?? `owner-${local}`, state, saved, marker, due).run();
    };
    const row = async (recipient = address) => await db.prepare(
      "SELECT state,cf_rule_id,needs_reconcile,next_reconcile_at FROM addresses WHERE address=?1",
    ).bind(recipient).first();
    const tick = async () => {
      const start = calls.length;
      await (await mf.getWorker()).scheduled();
      const current = calls.slice(start).filter((call) => call.path.startsWith(rulePath));
      assert.ok(current.length <= 20, "all inventory, scoped GET and DELETE share twenty address calls");
      assert.equal(unexpected, 0, "no fixture forwards unmatched requests to real services");
      return current;
    };
    const add = async () => await mf.dispatchFetch("https://mail-staging.moesegfault.dev/v1/addresses", {
      method: "POST", headers: { Authorization: `Bearer ${accessToken()}`, "Content-Type": "application/json" },
      body: JSON.stringify({ local_part: "synthetic-only" }),
    });
    const remove = async (recipient = address) => await mf.dispatchFetch("https://mail-staging.moesegfault.dev/v1/addresses", {
      method: "DELETE", headers: { Authorization: `Bearer ${accessToken()}`, "Content-Type": "application/json" },
      body: JSON.stringify({ address: recipient }),
    });
    await body({ db, insert, row, tick, store, calls, add, remove });
    assert.equal(unexpected, 0);
  } finally {
    await waitForPhase(mf.dispose(), "synthetic provider disposal", 10000);
  }
}

test("zero due rows still discover a late route for a clean permanent retired lifetime", async () => {
  await withProvider({}, async ({ insert, row, tick, store }) => {
    await insert(address);
    const empty = await tick();
    assert.equal(empty.length, 1, "empty inventory costs one GET, not a tombstone loop");
    assert.equal((await row()).needs_reconcile, 0);
    // Model a previously canceled POST's provider side effect, with no caller rearm.
    store.set("late-old-version", managedRule("late-old-version"));
    const found = await tick();
    assert.deepEqual(found.map((call) => call.method), ["GET", "GET", "DELETE"]);
    assert.equal(store.size, 0);
    assert.equal((await row()).state, "retired");
    assert.equal((await row()).needs_reconcile, 0);
  });
});

test("route materializing after an absence-based marker clear is found on the next independent tick", async () => {
  await withProvider({}, async ({ insert, row, tick, store }) => {
    await insert(address, { marker: 1, due: -1 });
    await tick();
    assert.equal((await row()).needs_reconcile, 0);
    store.set("late-after-clear", managedRule("late-after-clear", address, { enabled: false }));
    await tick();
    assert.equal(store.size, 0);
    assert.equal((await row()).state, "retired");
  });
});

for (const [label, overrides] of [
  ["unknown source", { source: "unknown" }],
  ["missing source", { source: undefined }],
  ["foreign name", { name: "operator-owned" }],
  ["extra matcher", { matchers: [...managedRule("x").matchers, { type: "literal", field: "to", value: "other@example.test" }] }],
  ["extra action", { actions: [...managedRule("x").actions, { type: "drop" }] }],
  ["other ingress", { actions: [{ type: "worker", value: ["foreign-ingress"] }] }],
  ["multiple worker values", { actions: [{ type: "worker", value: ["synthetic-ingress", "foreign-ingress"] }] }],
]) {
  test(`retired discovery never deletes ${label} scope`, async () => {
    await withProvider({ rules: [managedRule("foreign-scope", address, overrides)] }, async ({ insert, tick, store }) => {
      await insert(address, { marker: 1, due: -1, saved: "foreign-scope" });
      const calls = await tick();
      assert.equal(calls.filter((call) => call.method === "DELETE").length, 0);
      assert.equal(store.size, 1);
    });
  });
}

test("unknown lifetimes, production realm and apex operator routes stay untouched", async () => {
  const foreign = [
    managedRule("unknown-lifetime"),
    managedRule("production-realm", "synthetic-only@mail.moesegfault.dev"),
    managedRule("apex-operator", "mail@moesegfault.dev"),
  ];
  await withProvider({ rules: foreign }, async ({ tick, store }) => {
    assert.equal((await tick()).filter((call) => call.method === "DELETE").length, 0);
    assert.equal(store.size, 3);
  });
});

for (const enabled of [false, undefined]) {
  test(`strict retired route permits cleanup with enabled=${enabled}`, async () => {
    await withProvider({ rules: [managedRule("retired-owned", address, { enabled })] }, async ({ insert, tick, store, row }) => {
      await insert(address);
      await tick();
      assert.equal(store.size, 0);
      assert.equal((await row()).state, "retired");
    });
  });
}

test("scoped ID GET that reveals repurposing prevents DELETE and retains repair intent", async () => {
  await withProvider({
    rules: [managedRule("repurposed")],
    getRule: async (id, _store, json) => json({ success: true, result: managedRule(id, "other@mail-staging.moesegfault.dev") }),
  }, async ({ insert, tick, store, row }) => {
    await insert(address);
    const calls = await tick();
    assert.equal(calls.filter((call) => call.method === "DELETE").length, 0);
    assert.equal(store.size, 1);
    assert.equal((await row()).needs_reconcile, 1);
  });
});

for (const [label, reply] of [
  ["malformed envelope", { success: true }],
  ["false success", { success: false, result: [] }],
  ["short intermediate page", { success: true, result: [managedRule("partial")], result_info: { total_pages: 2 } }],
  ["over-cap page count", { success: true, result: [], result_info: { total_pages: 11 } }],
]) {
  test(`incomplete inventory (${label}) cannot delete or clear retired repair`, async () => {
    await withProvider({ listPage: async (_page, _store, json) => json(reply) }, async ({ insert, tick, row }) => {
      await insert(address, { marker: 1, due: -1 });
      const calls = await tick();
      assert.equal(calls.filter((call) => call.method === "DELETE").length, 0);
      assert.equal((await row()).needs_reconcile, 1);
    });
  });
}

for (const count of [50, 51, 404, 500, 501]) {
  test(`complete inventory admits at most 500 rules (${count} fixture)`, async () => {
    const filler = Array.from({ length: count }, (_, n) => managedRule(`rule-${n}`, `foreign-${n}@mail-staging.moesegfault.dev`));
    await withProvider({ rules: filler }, async ({ tick, store }) => {
      const calls = await tick();
      const pages = calls.filter((call) => call.path === rulePath);
      assert.equal(pages.length, count > 500 ? 1 : Math.ceil(count / 50));
      assert.equal(store.size, count, "unallocated provider rules are never garbage-collected");
    });
  });
}

for (const kind of ["duplicate", "malformed", "403"]) {
  test(`a ${kind} second page invalidates the entire inventory prefix`, async () => {
    const first = Array.from({ length: 50 }, (_, n) => managedRule(`page-rule-${n}`, n === 0 ? address : `foreign-${n}@mail-staging.moesegfault.dev`));
    await withProvider({ listPage: async (page, _store, json) => {
      if (page === 1) return json({ success: true, result: first, result_info: { total_pages: 2 } });
      if (kind === "403") return json({ success: false }, 403);
      if (kind === "malformed") return json({ success: true, result: "not-an-array" });
      return json({ success: true, result: [first[0]], result_info: { total_pages: 2 } });
    } }, async ({ insert, tick, row }) => {
      await insert(address, { marker: 1, due: -1 });
      const calls = await tick();
      assert.equal(calls.filter((call) => call.method === "DELETE").length, 0);
      assert.equal((await row()).needs_reconcile, 1);
    });
  });
}

test("forty due lifetimes rotate fairly while scoped cleanup stays within twenty shared calls", async () => {
  const rules = Array.from({ length: 40 }, (_, n) => {
    const recipient = `fair-${String(n).padStart(2, "0")}@mail-staging.moesegfault.dev`;
    return managedRule(`fair-rule-${n}`, recipient);
  });
  await withProvider({ rules }, async ({ insert, tick, db, store }) => {
    for (const rule of rules) await insert(rule.matchers[0].value, { marker: 1 });
    const first = await tick();
    assert.ok(first.filter((call) => call.method === "DELETE").length <= 9);
    assert.ok(store.size > 0, "budget exhaustion preserves unfinished provider rules");
    assert.ok((await db.prepare("SELECT COUNT(*) AS n FROM addresses WHERE needs_reconcile=1").first()).n > 0);
    for (let n = 0; n < 8 && store.size > 0; n++) {
      // Make claimed rows due without moving them ahead of never-claimed rows.
      await db.prepare("UPDATE addresses SET next_reconcile_at=?1 WHERE next_reconcile_at>0")
        .bind(Date.now() - 1).run();
      await tick();
    }
    assert.equal(store.size, 0, "every eligible retired provider rule eventually receives cleanup budget");
  });
});

test("persistent nine-failure prefix cannot starve a healthy budget-skipped tail", async () => {
  const rules = Array.from({ length: 10 }, (_, n) => managedRule(
    n < 9 ? `poison-${n}` : "healthy-tail",
    `turn-${String(n).padStart(2, "0")}@mail-staging.moesegfault.dev`,
  ));
  await withProvider({ rules, deleteReply: async (id, store, json) => {
    if (id.startsWith("poison-")) return json({ success: false });
    assert.ok(store.delete(id));
    return json({ success: true });
  } }, async ({ insert, tick, db, store, row }) => {
    for (const rule of rules) await insert(rule.matchers[0].value, { marker: 1 });
    const first = await tick();
    assert.equal(first.filter((call) => call.method === "DELETE").length, 9);
    assert.ok(store.has("healthy-tail"), "tail was denied pair admission on its first turn");
    const tail = await row(rules[9].matchers[0].value);
    const poison = await row(rules[0].matchers[0].value);
    assert.ok(tail.next_reconcile_at < poison.next_reconcile_at,
      "durable scheduling distinguishes skipped work from attempted failure backoff");
    // Admit every cohort, retaining relative due order rather than flattening it.
    await db.prepare("UPDATE addresses SET next_reconcile_at=next_reconcile_at-360000 WHERE next_reconcile_at>0").run();
    const second = await tick();
    assert.equal(second.find((call) => call.method === "DELETE").path, `${rulePath}/healthy-tail`);
    assert.ok(!store.has("healthy-tail"), "a permanent failure prefix cannot consume every future healthy turn");
    assert.equal(store.size, 9);
    assert.equal((await row(rules[0].matchers[0].value)).needs_reconcile, 1);
  });
});

test("failed complete inventories rotate forty due records before external work", async () => {
  let inventories = 0;
  const rules = Array.from({ length: 40 }, (_, n) => managedRule(
    `recover-rule-${n}`, `recover-${String(n).padStart(2, "0")}@mail-staging.moesegfault.dev`,
  ));
  await withProvider({ rules, listPage: async (_page, store, json) => {
    inventories++;
    if (inventories <= 2) return json({ success: false }, 503);
    return json({ success: true, result: [...store.values()], result_info: { total_pages: 1 } });
  } }, async ({ insert, tick, db, store }) => {
    for (const rule of rules) await insert(rule.matchers[0].value, { marker: 1 });
    await tick();
    assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM addresses WHERE next_reconcile_at>0").first()).n, 30);
    await tick();
    assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM addresses WHERE next_reconcile_at>0").first()).n, 40,
      "second failed inventory claims the never-claimed cohort, not the same thirty records");
    assert.equal(store.size, 40);
    for (let n = 0; n < 8 && store.size; n++) {
      await db.prepare("UPDATE addresses SET next_reconcile_at=next_reconcile_at-360000 WHERE next_reconcile_at>0").run();
      await tick();
    }
    assert.equal(store.size, 0, "eventual provider recovery lets both rotated cohorts converge");
  });
});

test("poisoned first current GET does not suppress later cleanup or state-only repair", async () => {
  const poison = managedRule("first-poison", "continue-00@mail-staging.moesegfault.dev");
  const healthy = managedRule("later-healthy", "continue-01@mail-staging.moesegfault.dev");
  const empty = "continue-02@mail-staging.moesegfault.dev";
  await withProvider({ rules: [poison, healthy], getRule: async (id, store, json) => {
    return json({ success: true, result: id === poison.id ?
      managedRule(id, "foreign@mail-staging.moesegfault.dev") : store.get(id) });
  } }, async ({ insert, tick, row, store }) => {
    await insert(poison.matchers[0].value, { marker: 1 });
    await insert(healthy.matchers[0].value, { marker: 1 });
    await insert(empty, { state: "deleting", marker: 1 });
    await tick();
    assert.ok(store.has(poison.id));
    assert.ok(!store.has(healthy.id));
    assert.equal((await row(poison.matchers[0].value)).needs_reconcile, 1);
    assert.equal((await row(empty)).state, "retired");
  });
});

/** Bound each synthetic phase, clear its timer, and retain an actionable label. */
async function waitForPhase(promise, phase, timeoutMs = 20000) {
  let timer;
  try {
    return await Promise.race([promise, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(`synthetic phase timed out: ${phase}`)), timeoutMs);
    })]);
  } finally {
    clearTimeout(timer);
  }
}

test("an unfulfilled synthetic barrier fails with a finite phase deadline", async () => {
  await assert.rejects(waitForPhase(new Promise(() => {}), "never-submitted", 50),
    /synthetic phase timed out: never-submitted/);
});

test("a real pre-POST refusal produces a bounded submission diagnostic", async () => {
  await withProvider({ listPage: async (_page, _store, json) => json({ success: false }, 503) },
    async ({ add, calls }) => {
      const submitted = barrier();
      const creator = add().then((response) => ({ response }), (error) => ({ error }));
      await assert.rejects(waitForPhase(Promise.race([submitted.promise, creator.then(() => {
        throw new Error("creator settled before synthetic POST submission");
      })]), "refused POST submission", 1000), /creator settled before synthetic POST submission/);
      const outcome = await waitForPhase(creator, "refused creator cleanup", 1000);
      assert.equal(outcome.response.status, 503);
      assert.equal(calls.filter((call) => call.method === "POST").length, 0);
    });
});

/** Create deterministic promise barriers without timers or live provider traffic. */
function barrier() {
  let release;
  const promise = new Promise((resolve) => { release = resolve; });
  return { promise, release };
}

test("provider POST may commit after two retire ticks while the creator remains blocked", { timeout: 60000 }, async () => {
  const submitted = barrier();
  const commit = barrier();
  const committed = barrier();
  const respond = barrier();
  let creates = 0;
  await withProvider({ createRule: async (_request, store, json) => {
    creates++;
    submitted.release();
    await commit.promise;
    store.set("delayed-post", managedRule("delayed-post"));
    committed.release();
    await respond.promise;
    return json({ success: true, result: { id: "delayed-post", enabled: true } });
  } }, async ({ add, db, row, tick, store, calls }) => {
    // Observe both success and rejection immediately, so failed pre-POST
    // authentication cannot become an unhandled rejection or a hanging barrier.
    const creator = add().then((response) => ({ response }), (error) => ({ error }));
    try {
      await waitForPhase(Promise.race([submitted.promise, creator.then(() => {
        throw new Error("creator settled before synthetic POST submission");
      })]), "POST submitted");
      await db.prepare("UPDATE addresses SET state='deleting',needs_reconcile=1,next_reconcile_at=-1 WHERE address=?1")
        .bind(address).run();
      await tick();
      assert.equal((await row()).state, "retired");
      await tick();
      assert.equal((await row()).needs_reconcile, 0);
      commit.release();
      await waitForPhase(committed.promise, "late provider side effect committed");
      // The HTTP continuation is still suspended: correctness cannot use rearm.
      assert.equal((await row()).needs_reconcile, 0);
      await tick();
      assert.equal(store.size, 0);
      assert.equal((await row()).state, "retired");
      assert.equal(creates, 1, "no duplicate POST is needed to discover the late provider side effect");
      assert.equal(calls.filter((call) => call.method === "DELETE").length, 1);
    } finally {
      commit.release();
      respond.release();
      const outcome = await waitForPhase(creator, "creator cleanup", 10000);
      if (outcome.error) throw outcome.error;
    }
    assert.equal((await row()).state, "retired", "late activation cannot resurrect the lifetime");
  });
});
for (const [label, getReply, status] of [
  ["malformed", { success: true }, 200],
  ["false-success", { success: false, result: managedRule("uncertain-get") }, 200],
  ["provider failure", { success: false }, 503],
]) {
  test(`unverified current ID GET (${label}) cannot authorize cleanup`, async () => {
    await withProvider({
      rules: [managedRule("uncertain-get")],
      getRule: async (_id, _store, json) => json(getReply, status),
    }, async ({ insert, tick, row, store }) => {
      await insert(address);
      assert.equal((await tick()).filter((call) => call.method === "DELETE").length, 0);
      assert.equal(store.size, 1);
      assert.equal((await row()).needs_reconcile, 1);
    });
  });
}

test("D1 state changing during scoped GET prevents deletion of a now-committed active route", async () => {
  let database;
  await withProvider({
    rules: [managedRule("now-active")],
    getRule: async (id, store, json) => {
      await database.prepare("UPDATE addresses SET state='active',cf_rule_id=?1 WHERE address=?2")
        .bind(id, address).run();
      return json({ success: true, result: store.get(id) });
    },
  }, async ({ db, insert, tick, row, store }) => {
    database = db;
    await insert(address, { state: "deleting", marker: 1, due: -1 });
    assert.equal((await tick()).filter((call) => call.method === "DELETE").length, 0);
    assert.equal(store.size, 1);
    assert.equal((await row()).state, "active");
    assert.equal((await row()).cf_rule_id, "now-active");
  });
});

test("one thousand historical tombstones still require just one empty provider inventory", async () => {
  await withProvider({}, async ({ db, tick }) => {
    // Single synthetic SQL statement avoids a fixture-side per-row network loop.
    await db.exec("WITH RECURSIVE n(x) AS (SELECT 0 UNION ALL SELECT x+1 FROM n WHERE x<999) " +
      "INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,state,created_at) " +
      "SELECT 'old-'||x||'@mail-staging.moesegfault.dev','old-'||x,'synthetic-issuer','owner-'||x,0,'retired',0 FROM n;");
    const calls = await tick();
    assert.equal(calls.length, 1);
    assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM addresses WHERE needs_reconcile=1").first()).n, 0);
  });
});
test("aged provisioning uses a fresh complete inventory before an absence-based pending transition", async () => {
  let lists = 0;
  await withProvider({ listPage: async (_page, _store, json) => {
    lists++;
    return json({ success: true, result: lists === 1 ? [] : [managedRule("fresh-disabled", address, { enabled: false })],
      result_info: { total_pages: 1 } });
  } }, async ({ insert, tick, row }) => {
    await insert(address, { state: "provisioning" });
    const calls = await tick();
    assert.equal(calls.filter((call) => call.path === rulePath).length, 2);
    assert.equal((await row()).state, "provisioning", "early shared absence must not enlarge the creation-lease race");
    assert.equal(calls.filter((call) => call.method === "DELETE").length, 0);
  });
});
for (const [label, reply] of [
  ["false success", { success: false }],
  ["malformed result", {}],
]) {
  test(`DELETE HTTP 200 with ${label} preserves retired repair intent`, async () => {
    await withProvider({
      rules: [managedRule("uncertain-delete")],
      deleteReply: async (_id, _store, json) => json(reply),
    }, async ({ insert, tick, row, store }) => {
      await insert(address);
      assert.equal((await tick()).filter((call) => call.method === "DELETE").length, 1);
      assert.equal((await row()).needs_reconcile, 1);
      assert.equal(store.size, 1, "an unacknowledged DELETE does not establish provider absence");
    });
  });
}

test("ten full pages without terminal pagination metadata remain incomplete", async () => {
  await withProvider({ listPage: async (page, _store, json) => json({
    success: true,
    result: Array.from({ length: 50 }, (_, n) => managedRule(`no-meta-${page}-${n}`,
      page === 1 && n === 0 ? address : `unknown-${page}-${n}@mail-staging.moesegfault.dev`)),
  }) }, async ({ insert, tick, row }) => {
    await insert(address, { marker: 1, due: -1 });
    const calls = await tick();
    assert.equal(calls.length, 10);
    assert.equal(calls.filter((call) => call.method === "DELETE").length, 0);
    assert.equal((await row()).needs_reconcile, 1);
  });
});

test("a streamed page exceeding 256 KiB fails closed without Content-Length", async () => {
  await withProvider({ listPage: async () => {
    const payload = new TextEncoder().encode(JSON.stringify({
      success: true, result: [managedRule("oversized-page")],
      result_info: { total_pages: 1 }, padding: "x".repeat(256 * 1024),
    }));
    let offset = 0;
    return new Response(new ReadableStream({
      pull(controller) {
        if (offset === payload.length) { controller.close(); return; }
        const end = Math.min(offset + 8192, payload.length);
        controller.enqueue(payload.slice(offset, end));
        offset = end;
      },
    }), { headers: { "content-type": "application/json" } });
  } }, async ({ insert, tick, row }) => {
    await insert(address, { marker: 1, due: -1 });
    assert.equal((await tick()).filter((call) => call.method === "DELETE").length, 0);
    assert.equal((await row()).needs_reconcile, 1);
  });
});

test("request DELETE never follows a saved ID repurposed to a foreign lifetime", async () => {
  await withProvider({ rules: [managedRule("saved-repurposed", "foreign@mail-staging.moesegfault.dev")] },
    async ({ insert, remove, row, calls, store }) => {
      await insert(address, { state: "active", saved: "saved-repurposed", ownerSub: "synthetic-subject" });
      const response = await remove();
      assert.equal(response.status, 503, "provider scope conflicts preserve the existing failure vocabulary");
      assert.equal((await response.json()).code, "service_unavailable");
      assert.equal((await row()).state, "deleting");
      assert.equal(calls.filter((call) => call.method === "DELETE").length, 0);
      assert.equal(store.size, 1);
    });
});

test("request DELETE returns 202 with deleting state when twenty-call cleanup budget is exhausted", async () => {
  const rules = Array.from({ length: 15 }, (_, n) => managedRule(`partial-delete-${n}`));
  await withProvider({ rules }, async ({ insert, remove, row, calls, store }) => {
    await insert(address, { state: "active", saved: "partial-delete-0", ownerSub: "synthetic-subject" });
    const response = await remove();
    assert.equal(response.status, 202);
    assert.equal((await response.json()).state, "deleting");
    assert.equal((await row()).state, "deleting");
    const addressCalls = calls.filter((call) => call.path.startsWith(rulePath));
    assert.ok(addressCalls.length <= 20);
    assert.equal(addressCalls.filter((call) => call.method === "DELETE").length, 9);
    assert.equal(store.size, 6, "remaining owned provider rules persist for scheduled continuation");
  });
});
test("complete shared inventory absence never turns a saved ID into blind DELETE authority", async () => {
  const { response, rows, routeDeletesPending } = await exercise({
    status: 200,
    body: JSON.stringify({ success: true, result: { id: "synthetic-rule", enabled: true } }),
  }, { markDeleting: true, runCron: true, cronRuleIds: [] });
  assert.equal(response.status, 201);
  assert.deepEqual(rows, [{ state: "retired", cf_rule_id: null, needs_reconcile: 1 }]);
  assert.equal(routeDeletesPending, 2, "saved IDs absent from a complete inventory are not blindly deleted");
});
