/** Account consent is a persisted egress boundary in the actual Rust/Wasm entries. */
import assert from "node:assert/strict";
import { generateKeyPairSync, randomUUID, sign } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { Miniflare } from "miniflare";
import { apiVersionHeaders } from "./api-version.mjs";
import { applyMigrations, seedResourceAccount } from "./migration-fixture.mjs";
import { workerModuleRules } from "./worker-module-rules.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const worker = path.join(root, "crates/mail-worker");
const issuer = "https://identity-staging.moesegfault.dev";
const address = "consent@mail-staging.moesegfault.dev";
const model = "voyageai/voyage-4";
const policy = "voyage4_no_training_retention_v1";
const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });

function token() {
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString("base64url");
  const input = `${encode({ alg: "RS256", kid: "consent" })}.${encode({ iss: issuer,
    sub: "owner", aud: "amail-cli-staging", token_use: "access",
    exp: Math.floor(Date.now() / 1000) + 600 })}`;
  return `${input}.${sign("RSA-SHA256", Buffer.from(input), privateKey).toString("base64url")}`;
}

async function fixture(run, { legacy = false, through } = {}) {
  const jwk = publicKey.export({ format: "jwk" });
  const calls = [];
  let providerHook;
  const outboundService = async (request) => {
    if (request.url === `${issuer}/.well-known/openid-configuration`)
      return Response.json({ issuer, jwks_uri: `${issuer}/jwks` });
    if (request.url === `${issuer}/jwks`)
      return Response.json({ keys: [{ ...jwk, kid: "consent", alg: "RS256", use: "sig" }] });
    if (request.method === "GET" && request.url === "https://api.cloudflare.com/client/v4/zones/synthetic-zone/email/routing/rules?per_page=50&page=1")
      return Response.json({ success: true, result: [], result_info: { total_pages: 1 } });
    assert.equal(request.url, "https://openrouter.ai/api/v1/embeddings", "unmatched egress is never forwarded");
    assert.equal(request.method, "POST");
    const input = await request.json();
    assert.equal(input.model, model);
    assert.equal(input.dimensions, 256);
    assert.ok(["query", "document"].includes(input.input_type));
    assert.deepEqual(input.provider, { only: ["voyageai"], allow_fallbacks: false, data_collection: "deny" });
    assert.equal(request.headers.get("x-openrouter-cache"), "false");
    calls.push(input);
    if (providerHook) await providerHook(input);
    return Response.json({ data: [{ embedding: [1, ...Array(255).fill(0)] }] });
  };
  const base = { modules: true, modulesRoot: root, modulesRules: workerModuleRules,
    compatibilityDate: "2026-08-06", d1Databases: { MAIL_DB: "consent-shared-db" },
    r2Buckets: { MAIL_BODIES: "consent-shared-r2" }, outboundService,
    bindings: { IDENTITY_ISSUER: issuer, OIDC_CLIENT_ID: "amail-cli-staging",
      MAIL_DOMAIN: "mail-staging.moesegfault.dev", CF_ZONE_ID: "synthetic-zone",
      CF_EMAIL_ROUTING_TOKEN: "synthetic-routing", EMAIL_INGRESS_WORKER_NAME: "synthetic-ingress",
      OPENROUTER_API_KEY: "synthetic-key", OPENROUTER_EMBEDDING_MODEL: model } };
  const mf = new Miniflare({ cf: false, workers: [
    { ...base, name: "consent-api", scriptPath: path.join(worker, "entry/api.mjs") },
    { ...base, name: "consent-maintenance", scriptPath: path.join(worker, "entry/maintenance.mjs") },
  ] });
  try {
    const db = await mf.getD1Database("MAIL_DB", "consent-api");
    await applyMigrations(db, path.join(worker, "migrations"), legacy ? { through: 17 } : { through });
    await seedResourceAccount(db, issuer, "owner");
    await db.prepare("INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,state,created_at) VALUES(?1,'consent',?2,'owner',0,'active',0)")
      .bind(address, issuer).run();
    const authorization = `Bearer ${token()}`;
    const request = async (method, route, session, body, extraHeaders = {}) => {
      const response = await mf.dispatchFetch(`https://mail.invalid${route}`, { method,
        headers: { ...apiVersionHeaders, authorization, ...extraHeaders,
          ...(session ? { "x-amail-profile-session": session.session_token } : {}),
          ...(body === undefined ? {} : { "content-type": "application/json" }) },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
      return { status: response.status, body: await response.json() };
    };
    const activate = async (name) => {
      const response = await request("POST", "/v1/profiles/activate", null, { name, terminal_id: randomUUID() });
      assert.equal(response.status, 200, JSON.stringify(response.body));
      return response.body;
    };
    const message = async (id, direction = "inbound") => {
      await db.prepare("INSERT INTO messages(id,address,owner_iss,owner_sub,direction,sender,recipients_json,subject,body_text,metadata_json,received_at,has_html,has_text,attachment_count,r2_key,size_bytes) VALUES(?1,?2,?3,'owner',?4,'sender@example.invalid','[]',?5,'synthetic private content','{}',?6,0,1,0,?7,1)")
        .bind(id, address, issuer, direction, `synthetic subject ${id}`, Date.now(), `messages/${id}.zip`).run();
    };
    const tick = async () => (await mf.getWorker("consent-maintenance")).scheduled();
    const setting = async (session, enabled) => {
      const current = await request("GET", "/v1/semantic", session);
      assert.equal(current.body.policy_id, policy);
      return request("POST", "/v1/semantic", session, {
        enabled, expected_generation: current.body.generation, policy_id: policy,
      });
    };
    const vectors = async () => (await db.prepare("SELECT id,embedding_json,embedding_model,embedding_dimensions,embedding_consent_generation FROM messages ORDER BY id").all()).results;
    await run({ db, request, activate, message, tick, setting, vectors, calls,
      hook: (callback) => { providerHook = callback; } });
  } finally { await mf.dispose(); }
}

test("semantic default-off is enforced before query or background provider calls; only active user changes it", async () => fixture(async ({ db, request, activate, message, tick, setting, calls }) => {
  await message("incoming");
  await message("sent", "outbound");
  const initial = await request("GET", "/v1/semantic");
  assert.equal(initial.status, 200);
  assert.equal(initial.body.enabled, false);
  assert.equal(initial.body.policy_id, policy);
  assert.equal((await setting(null, true)).status, 403, "legacy owner tokens cannot authorize a privacy transition");
  assert.equal((await request("POST", "/v1/messages/search", null, { semantic: "synthetic query" })).body.code, "semantic_disabled");
  await tick();
  assert.equal(calls.length, 0, "new incoming and sent projections must not trigger default egress");
  const oldClaim = async () => db.prepare("UPDATE embedding_work SET lease_token='old-worker',lease_until=?1 WHERE message_id='incoming'")
    .bind(Date.now() + 60_000).run();
  assert.equal((await oldClaim()).meta.changes, 0, "pre-consent migration fences the old maintenance claim shape");
  const user = await activate("user");
  assert.equal((await request("POST", "/v1/profiles", user, { name: "agent" })).status, 200);
  const agent = await activate("agent");
  for (const enabled of [true, false]) {
    const denied = await request("POST", "/v1/semantic", agent,
      { enabled, expected_generation: 0, policy_id: policy, approved: true, profile: "user" },
      { "x-amail-user-approved": "true" });
    assert.equal(denied.status, 403);
    assert.equal(denied.body.code, "user_profile_required");
  }
  assert.equal((await request("GET", "/v1/semantic", agent)).body.enabled, false);
  for (const enabled of [true, false]) {
    const missing = await request("POST", "/v1/semantic", user, { enabled, expected_generation: 0 });
    assert.equal(missing.status, 400);
    assert.equal(missing.body.code, "invalid_semantic_preference");
    const changed = await request("POST", "/v1/semantic", user,
      { enabled, expected_generation: 0, policy_id: "obsolete_zdr_policy" });
    assert.equal(changed.status, 409);
    assert.equal(changed.body.code, "semantic_policy_changed");
    const unchanged = await request("GET", "/v1/semantic", user);
    assert.equal(unchanged.body.enabled, false);
    assert.equal(unchanged.body.generation, 0);
  }
  const enabled = await setting(user, true);
  assert.equal(enabled.status, 200, JSON.stringify(enabled.body));
  assert.equal(enabled.body.enabled, true);
  assert.equal((await oldClaim()).meta.changes, 0, "even a later opt-in cannot authorize an overlapping old Worker");
  await tick();
  assert.equal(calls.length, 2, "approval backfills both historical inbound and sent mail");
}));

test("re-enable reuses retained Voyage vectors and indexes only mail received while disabled", async () => fixture(async ({ request, activate, message, tick, setting, vectors, calls }) => {
  const user = await activate("user");
  await message("first");
  await message("second", "outbound");
  const enabled = await setting(user, true);
  await tick();
  const before = await vectors();
  assert.equal(before.length, 2);
  assert.ok(before.every((row) => row.embedding_json !== null && row.embedding_model === model));
  const repeated = await setting(user, true);
  assert.equal(repeated.body.generation, enabled.body.generation, "same-state retries cannot create a fresh rebuild");
  await tick();
  assert.equal(calls.length, 2);
  const disabled = await setting(user, false);
  assert.equal(disabled.status, 200);
  assert.equal(disabled.body.enabled, false);
  const stale = await request("POST", "/v1/semantic", user,
    { enabled: true, expected_generation: enabled.body.generation, policy_id: policy });
  assert.equal(stale.status, 409, "an approval for an old state must not undo a newer disable");
  assert.equal(stale.body.code, "semantic_state_changed");
  assert.deepEqual(await vectors(), before, "turning off does not destroy stored embeddings");
  await message("third");
  assert.equal((await request("POST", "/v1/messages/search", user, { semantic: "synthetic query" })).body.code, "semantic_disabled");
  await tick();
  assert.equal(calls.length, 2, "paused account sends neither new mail nor queries");
  const resumed = await setting(user, true);
  assert.ok(resumed.body.generation > disabled.body.generation);
  assert.deepEqual((await vectors()).slice(0, 2), before, "re-enable neither removes nor relabels retained compatible vectors");
  assert.equal(resumed.body.pending_messages, 1, "only the message received while disabled needs indexing");
  assert.equal(resumed.body.indexed_messages, 2, "prior consent generations do not invalidate compatible vectors");
  await tick();
  assert.equal(calls.length, 3, "only previously unindexed mail is sent to Voyage");
  assert.deepEqual((await vectors()).slice(0, 2), before, "successful catch-up preserves previous vector bytes and metadata");
  const acquired = await request("POST", "/v1/leases/acquire", user, { address, mode: "read" });
  assert.equal(acquired.status, 200);
  const queried = await request("POST", "/v1/messages/search", user, { semantic: "synthetic query" });
  assert.equal(queried.status, 200, "retained vectors remain searchable after the consent generation changes");
  assert.deepEqual(new Set(queried.body.messages.map((row) => row.id)), new Set(["first", "second", "third"]));
  assert.equal(calls.filter((call) => call.input_type === "document").length, 3);
  assert.equal(calls.filter((call) => call.input_type === "query").length, 1);
  assert.equal((await setting(user, false)).status, 200);
  const reused = await setting(user, true);
  assert.equal(reused.body.pending_messages, 0);
  assert.equal(reused.body.indexed_messages, 3);
  const completed = await vectors();
  await tick();
  assert.equal(calls.length, 4, "another off/on cycle sends no document or query by itself");
  assert.deepEqual(await vectors(), completed);
}));

test("0019 preserves approved settings and compatible vectors while converting Qwen only once", async () => fixture(async ({ db, request, activate, message, tick, setting, vectors, calls }) => {
  const user = await activate("user");
  for (const id of ["voyage", "qwen", "missing"]) await message(id);
  await db.prepare("INSERT INTO semantic_preferences(owner_iss,owner_sub,enabled,generation) VALUES(?1,'owner',1,1)")
    .bind(issuer).run();
  const enabledGeneration = 1;
  const vector = JSON.stringify([1, ...Array(255).fill(0)]);
  await db.prepare("UPDATE messages SET embedding_json=?1,embedding_model=?2,embedding_dimensions=256,embedding_input_version=1,embedding_truncated=0,embedding_consent_generation=?3 WHERE id='voyage'")
    .bind(vector, model, enabledGeneration).run();
  await db.prepare("UPDATE messages SET embedding_json=?1,embedding_model='qwen/qwen3-embedding-8b',embedding_dimensions=256,embedding_input_version=1,embedding_truncated=0,embedding_consent_generation=0 WHERE id='qwen'")
    .bind(vector).run();
  await db.prepare("INSERT INTO embedding_work(message_id,owner_iss,owner_sub,received_at,consent_generation) VALUES('voyage',?1,'owner',?2,?3)")
    .bind(issuer, Date.now(), enabledGeneration).run();
  const preferences = await db.prepare("SELECT enabled,generation FROM semantic_preferences WHERE owner_iss=?1 AND owner_sub='owner'").bind(issuer).first();
  const before = await vectors();
  await applyMigrations(db, path.join(worker, "migrations"), { from: 19 });
  assert.deepEqual(await vectors(), before, "the migration preserves all stored vector bytes and metadata");
  assert.deepEqual(await db.prepare("SELECT enabled,generation FROM semantic_preferences WHERE owner_iss=?1 AND owner_sub='owner'").bind(issuer).first(), preferences,
    "a backend-only upgrade must not grant, revoke, or replace existing consent");
  assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM embedding_work WHERE message_id='voyage'").first()).n, 0);
  await db.prepare("INSERT INTO embedding_work(message_id,owner_iss,owner_sub,received_at,consent_generation) VALUES('voyage',?1,'owner',?2,?3)")
    .bind(issuer, Date.now(), enabledGeneration).run();
  const oldClaim = await db.prepare("UPDATE embedding_work SET lease_until=?1,lease_token='old-v031',consent_lease_token='old-v031' WHERE message_id='voyage' AND state='pending'")
    .bind(Date.now() + 60_000).run();
  assert.equal(oldClaim.meta.changes, 0, "the shipped v0.3.1 claim cannot re-admit a retained compatible vector");
  const off = await setting(user, false);
  assert.equal(off.status, 200);
  const resumed = await setting(user, true);
  assert.equal(resumed.body.pending_messages, 2, "only missing and incompatible old-model projections remain work");
  assert.equal(resumed.body.indexed_messages, 1);
  await tick();
  assert.equal(calls.length, 2);
  assert.ok(calls.every((call) => call.input_type === "document"));
  const converted = await vectors();
  assert.ok(converted.every((row) => row.embedding_model === model && row.embedding_json !== null));
  assert.deepEqual(converted.find((row) => row.id === "voyage"), before.find((row) => row.id === "voyage"));
  assert.equal((await setting(user, false)).status, 200);
  assert.equal((await setting(user, true)).body.pending_messages, 0);
  await tick();
  assert.equal(calls.length, 2, "a successfully migrated Qwen vector is never retransmitted by later toggles");
  assert.deepEqual(await vectors(), converted);
}, { through: 18 }));

test("re-enable preserves backoff and quarantine instead of resetting supplier retry state", async () => fixture(async ({ db, activate, message, tick, setting, calls }) => {
  const user = await activate("user");
  await message("backoff");
  await message("quarantined");
  assert.equal((await setting(user, true)).status, 200);
  const future = Date.now() + 3_600_000;
  await db.prepare("UPDATE embedding_work SET attempts=2,next_attempt_at=?1,last_error_code='provider_transient' WHERE message_id='backoff'")
    .bind(future).run();
  await db.prepare("UPDATE embedding_work SET state='quarantined',attempts=3,next_attempt_at=?1,last_error_code='provider_malformed' WHERE message_id='quarantined'")
    .bind(future).run();
  const ledger = async () => (await db.prepare("SELECT message_id,state,attempts,next_attempt_at,last_error_code FROM embedding_work ORDER BY message_id").all()).results;
  const before = await ledger();
  assert.equal((await setting(user, false)).status, 200);
  const resumed = await setting(user, true);
  assert.equal(resumed.status, 200);
  assert.equal(resumed.body.pending_messages, 2);
  assert.deepEqual(await ledger(), before, "consent changes cannot evade backoff or erase quarantine evidence");
  assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM embedding_work WHERE consent_generation=?1 AND lease_token IS NULL AND consent_lease_token IS NULL").bind(resumed.body.generation).first()).n, 2);
  await tick();
  assert.equal(calls.length, 0, "neither future retry work nor quarantined input is submitted early");
}));

test("disable during provider await cannot publish an old generation or process the next document", async () => fixture(async ({ db, activate, message, tick, setting, vectors, calls, hook }) => {
  const user = await activate("user");
  await message("first");
  await message("second");
  await setting(user, true);
  let paused = false;
  hook(async () => {
    if (paused) return;
    paused = true;
    assert.equal((await setting(user, false)).status, 200);
  });
  await tick();
  assert.equal(calls.length, 1, "an in-flight transfer cannot be recalled, but no later transfer starts");
  assert.ok((await vectors()).every((row) => row.embedding_json === null), "late result cannot cross revoked consent");
  assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM embedding_work WHERE lease_token IS NOT NULL").first()).n, 0);
  hook(undefined);
  await setting(user, true);
  await tick();
  assert.equal(calls.length, 3, "the next approved generation rebuilds both messages");
  assert.ok((await vectors()).every((row) => row.embedding_json !== null));
}));

test("0018 preserves old Qwen vectors without remote migration and rebuilds only after user consent", async () => fixture(async ({ db, request, activate, message, tick, setting, vectors, calls }) => {
  await message("legacy");
  const old = JSON.stringify([1, ...Array(255).fill(0)]);
  await db.prepare("UPDATE messages SET embedding_json=?1,embedding_model='qwen/qwen3-embedding-8b',embedding_dimensions=256,embedding_input_version=1,embedding_truncated=0 WHERE id='legacy'")
    .bind(old).run();
  const beforeMigration = await request("POST", "/v1/messages/search", null, { semantic: "synthetic query" });
  assert.equal(beforeMigration.status, 503, "API-first cutover fails closed on a pre-consent schema");
  assert.equal(calls.length, 0);
  const literal = await request("POST", "/v1/messages/search", null, { title: "synthetic subject legacy" });
  assert.equal(literal.status, 200, "API-first cutover retains ordinary search before 0018");
  assert.deepEqual(literal.body.messages.map((row) => row.id), ["legacy"]);
  assert.equal((await request("GET", "/v1/messages/legacy")).status, 200);
  const listed = await request("GET", "/v1/messages");
  assert.equal(listed.status, 200);
  assert.ok(listed.body.messages.some((row) => row.id === "legacy"));
  await applyMigrations(db, path.join(worker, "migrations"), { from: 18 });
  const preserved = (await vectors())[0];
  assert.equal(preserved.embedding_json, old);
  assert.equal(preserved.embedding_model, "qwen/qwen3-embedding-8b");
  assert.equal((await request("GET", "/v1/semantic")).body.enabled, false);
  await tick();
  assert.equal(calls.length, 0, "schema migration is not permission to transfer historical mail");
  const user = await activate("user");
  const enabled = await setting(user, true);
  assert.deepEqual((await vectors())[0], preserved, "enable preserves incompatible old space until actual rebuild");
  assert.equal((await request("POST", "/v1/leases/acquire", user, { address, mode: "read" })).status, 200);
  const incomplete = await request("POST", "/v1/messages/search", user, { semantic: "synthetic query" });
  assert.equal(incomplete.body.code, "semantic_index_incomplete", "old 256D Qwen and new 256D Voyage cannot silently mix");
  const beforeIndex = calls.length;
  await tick();
  assert.equal(calls.length, beforeIndex + 1);
  const migrated = (await vectors())[0];
  assert.equal(migrated.embedding_model, model);
  assert.equal(migrated.embedding_consent_generation, enabled.body.generation);
}, { legacy: true }));

test("empty-corpus consent cycles never leave an orphan owner schedule or fail on re-enable", async () => fixture(async ({ db, activate, setting, calls }) => {
  const user = await activate("user");
  let generation = 0;
  for (const enabled of [true, false, true, false, true, false]) {
    const transition = await setting(user, enabled);
    const code = /^[a-z_]{1,64}$/.test(transition.body.code ?? "") ? transition.body.code : "none";
    assert.equal(transition.status, 200, `empty consent transition HTTP ${transition.status} code=${code}`);
    assert.equal(transition.body.enabled, enabled);
    assert.equal(transition.body.generation, ++generation);
    assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM embedding_work").first()).n, 0);
    assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM embedding_owner_schedule").first()).n, 0,
      "the scheduler represents actual work, not enabled account state");
  }
  assert.equal(calls.length, 0);
}));

for (const reenable of [false, true]) {
  test(`query provider-await ${reenable ? "off/on" : "disable"} cannot publish a vector or old search result`, async () => fixture(async ({ db, request, activate, setting, calls, hook }) => {
    const user = await activate("user");
    await setting(user, true);
    const transitions = [];
    hook(async (input) => {
      assert.equal(input.input_type, "query");
      transitions.push(await setting(user, false));
      if (reenable) transitions.push(await setting(user, true));
    });
    const response = await request("POST", "/v1/messages/search", user, { semantic: "synthetic private query" });
    for (const transition of transitions) {
      const code = /^[a-z_]{1,64}$/.test(transition.body.code ?? "") ? transition.body.code : "none";
      assert.equal(transition.status, 200, `consent transition HTTP ${transition.status} code=${code}`);
    }
    assert.equal(transitions.length, reenable ? 2 : 1);
    const code = /^[a-z_]{1,64}$/.test(response.body.code ?? "") ? response.body.code : "none";
    assert.equal(response.status, 409, `query boundary HTTP ${response.status} code=${code}`);
    assert.equal(response.body.code, reenable ? "search_job_stale" : "semantic_disabled");
    assert.equal(calls.length, 1);
    assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM search_jobs").first()).n, 0,
      "neither private query vector nor replayable results survive failed preparation");
  }));
}
