/** Exercise profile and temporary-mail authority through the compiled Rust API. */
import assert from "node:assert/strict";
import { generateKeyPairSync, randomUUID, sign } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { setTimeout } from "node:timers/promises";
import { Miniflare } from "miniflare";
import { apiVersionHeaders } from "./api-version.mjs";
import { applyMigrations, seedResourceAccount } from "./migration-fixture.mjs";
import { workerModuleRules } from "./worker-module-rules.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const worker = path.join(root, "crates/mail-worker");
const issuer = "https://identity-staging.moesegfault.dev";
const mailDomain = "mail-staging.moesegfault.dev";
const temporaryDomain = "tmpaddr-staging.moesegfault.dev";
const routingPath = "/client/v4/zones/synthetic-zone/email/routing/rules";
const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });

function accessToken() {
  const header = Buffer.from(JSON.stringify({ alg: "RS256", kid: "synthetic" })).toString("base64url");
  const payload = Buffer.from(JSON.stringify({ iss: issuer, sub: "owner", aud: "amail-cli-staging",
    token_use: "access", exp: Math.floor(Date.now() / 1000) + 300 })).toString("base64url");
  const input = `${header}.${payload}`;
  return `${input}.${sign("RSA-SHA256", Buffer.from(input), privateKey).toString("base64url")}`;
}

/** No fixture egress is forwarded to a real network or mail provider. */
async function fixture(run, { ambiguousCreates = 0, maintenance = false } = {}) {
  const jwk = publicKey.export({ format: "jwk" });
  const rules = new Map();
  let unexpected = 0;
  let creates = 0;
  const name = "v030-multitenant";
  const options = { cf: false, workers: [{
    name, modules: true, scriptPath: path.join(worker, "entry/api.mjs"), modulesRoot: root,
    modulesRules: workerModuleRules, compatibilityDate: "2026-08-06",
    d1Databases: { MAIL_DB: "v030-shared-db" }, r2Buckets: { MAIL_BODIES: "v030-shared-r2" },
    bindings: { IDENTITY_ISSUER: issuer, OIDC_CLIENT_ID: "amail-cli-staging",
      MAIL_DOMAIN: mailDomain, MAIL_TMP_DOMAIN: temporaryDomain, CF_ZONE_ID: "synthetic-zone",
      CF_EMAIL_ROUTING_TOKEN: "synthetic-token", EMAIL_INGRESS_WORKER_NAME: "synthetic-ingress" },
    async outboundService(request) {
      if (request.method === "GET" && request.url === `${issuer}/.well-known/openid-configuration`) {
        return Response.json({ issuer, jwks_uri: `${issuer}/jwks` });
      }
      if (request.method === "GET" && request.url === `${issuer}/jwks`) {
        return Response.json({ keys: [{ ...jwk, kid: "synthetic", alg: "RS256", use: "sig" }] });
      }
      const url = new URL(request.url);
      if (url.origin === "https://api.cloudflare.com" && url.pathname === routingPath) {
        if (request.method === "GET") {
          assert.equal(url.search, "?per_page=50&page=1");
          return Response.json({ success: true, result: [...rules.values()], result_info: { total_pages: 1 } });
        }
        if (request.method === "POST") {
          const input = await request.json();
          assert.equal(input.enabled, true);
          assert.deepEqual(input.actions, [{ type: "worker", value: ["synthetic-ingress"] }]);
          const rule = { ...input, id: `synthetic-rule-${++creates}` };
          rules.set(rule.id, rule);
          if (creates <= ambiguousCreates) return Response.json({ success: true });
          return Response.json({ success: true, result: rule });
        }
      }
      if (url.origin === "https://api.cloudflare.com" && url.pathname.startsWith(`${routingPath}/`)) {
        const id = url.pathname.slice(routingPath.length + 1);
        if (request.method === "GET" && rules.has(id)) return Response.json({ success: true, result: rules.get(id) });
        if (request.method === "DELETE" && rules.delete(id)) return Response.json({ success: true });
      }
      unexpected++;
      throw new Error("unmatched multi-tenant fixture egress");
    },
  }] };
  if (maintenance) options.workers.push({ ...options.workers[0], name: `${name}-maintenance`,
    scriptPath: path.join(worker, "entry/maintenance.mjs") });
  const mf = new Miniflare(options);
  try {
    const db = await mf.getD1Database("MAIL_DB", name);
    const bucket = await mf.getR2Bucket("MAIL_BODIES", name);
    await applyMigrations(db, path.join(worker, "migrations"));
    await seedResourceAccount(db, issuer, "owner");
    const authorization = `Bearer ${accessToken()}`;
    const request = async (method, route, session, body) => mf.dispatchFetch(`https://mail.invalid${route}`, {
      method,
      headers: { ...apiVersionHeaders, authorization,
        ...(session ? { "x-amail-profile-session": session.session_token } : {}),
        ...(body === undefined ? {} : { "content-type": "application/json" }) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    const json = async (method, route, session, body) => {
      const response = await request(method, route, session, body);
      return { status: response.status, body: await response.json() };
    };
    const archiveStatus = async (id, session) => {
      const response = await request("GET", `/v1/messages/${id}/archive`, session);
      await response.arrayBuffer();
      return response.status;
    };
    const activate = async (profile, terminal = randomUUID()) => {
      const response = await json("POST", "/v1/profiles/activate", null, { name: profile, terminal_id: terminal });
      assert.equal(response.status, 200, JSON.stringify(response.body));
      return response.body;
    };
    const acquire = (session, address, mode) => json("POST", "/v1/leases/acquire", session, { address, mode });
    const releaseLease = (session, lease) => json("POST", "/v1/leases/release", session,
      { address: lease.address, lease_token: lease.lease_token });
    const message = async (address, generation = "", subject = "synthetic private body") => {
      const id = randomUUID();
      await db.prepare("INSERT INTO messages(id,address,owner_iss,owner_sub,direction,sender,recipients_json,subject,body_text,metadata_json,received_at,has_html,has_text,attachment_count,r2_key,size_bytes,mailbox_generation) VALUES(?1,?2,?3,'owner','inbound','sender@example.invalid','[]',?4,'private body','{}',?5,0,1,0,?6,4,?7)")
        .bind(id, address, issuer, subject, Date.now() - 2000, `messages/${id}.zip`, generation).run();
      await bucket.put(`messages/${id}.zip`, new Uint8Array([80, 75, 3, 4]));
      return id;
    };
    const scheduled = async () => (await mf.getWorker(`${name}-maintenance`)).scheduled();
    await run({ db, bucket, archiveStatus, json, activate, acquire, releaseLease, message, rules, scheduled });
    assert.equal(unexpected, 0);
  } finally { await mf.dispose(); }
}

test("profiles enroll once, reserve one terminal, and enforce shared-read/exclusive-write mail authority", async () => {
  await fixture(async ({ db, json, activate, acquire, releaseLease, message }) => {
    const address = `owned@${mailDomain}`;
    await db.prepare("INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,state,created_at) VALUES(?1,'owned',?2,'owner',0,'active',0)")
      .bind(address, issuer).run();
    const id = await message(address);
    assert.equal((await json("GET", `/v1/messages/${id}`)).status, 200, "unenrolled owners keep legacy access");
    const terminal = randomUUID();
    const user = await activate("user", terminal);
    const recovered = await activate("user", terminal);
    assert.equal(recovered.session_token, user.session_token, "same-terminal activation recovers its session");
    const competing = await json("POST", "/v1/profiles/activate", null, { name: "user", terminal_id: randomUUID() });
    assert.equal(competing.status, 409);
    assert.equal(competing.body.code, "profile_in_use");
    assert.equal((await json("GET", `/v1/messages/${id}`)).body.code, "profile_session_required");
    for (const name of ["alpha", "beta"]) {
      const created = await json("POST", "/v1/profiles", user, { name });
      assert.equal(created.status, 200);
      assert.equal(created.body.durable, true);
    }
    const alpha = await activate("alpha");
    const beta = await activate("beta");
    const createdChild = await json("POST", "/v1/profiles", alpha, { name: "child", durable: true });
    assert.equal(createdChild.body.durable, false, "an agent cannot elevate its child's durability");
    const child = await activate("child");
    assert.equal((await json("POST", "/v1/profiles/release", child)).status, 200);
    assert.equal((await json("POST", "/v1/profiles/activate", null,
      { name: "child", terminal_id: randomUUID() })).body.code, "profile_not_registered");
    const first = await acquire(alpha, address, "read");
    const second = await acquire(beta, address, "read");
    assert.equal(first.status, 200);
    assert.equal(second.status, 200);
    assert.equal((await acquire(user, address, "write")).body.code, "mailbox_in_use");
    assert.equal((await json("GET", `/v1/messages/${id}`, alpha)).status, 200);
    assert.equal((await json("PATCH", `/v1/messages/${id}`, alpha, { read: true })).status, 403);
    assert.equal((await db.prepare("SELECT is_read FROM messages WHERE id=?1").bind(id).first()).is_read, 0);
    assert.equal((await json("DELETE", `/v1/messages/${id}`, alpha)).status, 404);
    await releaseLease(alpha, first.body);
    assert.equal((await acquire(user, address, "write")).status, 409, "one surviving reader still prevents writes");
    await releaseLease(beta, second.body);
    const writer = await acquire(user, address, "write");
    assert.equal(writer.status, 200);
    assert.equal((await acquire(alpha, address, "read")).status, 409, "a reader cannot preempt a writer");
    assert.equal((await json("PATCH", `/v1/messages/${id}`, user, { read: true })).status, 200);
    assert.equal((await db.prepare("SELECT is_read FROM messages WHERE id=?1").bind(id).first()).is_read, 1);
    assert.equal((await json("POST", "/v1/addresses", alpha, { local_part: "forbidden", kind: "mail" })).body.code,
      "user_profile_required");
    await json("POST", "/v1/profiles/release", beta);
    const betaAgain = await activate("beta");
    assert.equal(betaAgain.profile_id, beta.profile_id, "user-created profiles survive release");
    await db.prepare("UPDATE mail_profiles SET session_expires_at=1 WHERE id=?1").bind(alpha.profile_id).run();
    assert.equal((await json("GET", `/v1/messages/${id}`, alpha)).body.code, "profile_session_expired");
    assert.equal((await json("GET", "/v1/profiles", user)).status, 200, "profile control opportunistically reclaims idle state");
    assert.equal((await activate("alpha")).profile_id, alpha.profile_id);
  });
});

test("tmpaddr registration auto-owns a six-hour generation; deadline and reuse never disclose predecessor mail", async () => {
  await fixture(async ({ db, json, archiveStatus, activate, acquire, message }) => {
    const user = await activate("user");
    await json("POST", "/v1/profiles", user, { name: "agent" });
    const agent = await activate("agent");
    const registered = await json("POST", "/v1/addresses", agent, { local_part: "quick-test", kind: "tmpaddr" });
    assert.equal(registered.status, 201, JSON.stringify(registered.body));
    const address = `quick-test@${temporaryDomain}`;
    assert.equal(registered.body.address, address);
    const current = (await json("GET", "/v1/addresses", agent)).body.addresses.find((row) => row.address === address);
    assert.equal(current.kind, "tmpaddr");
    assert.match(current.generation, /^[0-9a-f-]{36}$/);
    assert.ok(current.expires_at <= Date.now() + 6 * 60 * 60 * 1000);
    const id = await message(address, current.generation);
    assert.equal((await json("GET", `/v1/messages/${id}`, agent)).status, 200, "creation owns its writer lease");
    assert.equal((await json("GET", `/v1/messages/${id}`, user)).status, 404, "same account without possession cannot read");
    assert.equal((await acquire(user, address, "read")).status, 409);
    const firstPage = await json("POST", "/v1/messages/search", agent, { mailbox: address, limit: 1 });
    assert.equal(firstPage.status, 200);
    assert.deepEqual(firstPage.body.messages.map((row) => row.id), [id]);
    assert.equal(await archiveStatus(id, agent), 200);
    assert.equal((await json("DELETE", "/v1/addresses", agent, { address })).status, 202);
    assert.equal((await json("GET", `/v1/messages/${id}`, agent)).status, 404);
    assert.equal(await archiveStatus(id, agent), 404);
    assert.equal((await json("GET", "/v1/addresses", agent)).body.addresses.some((row) => row.address === address), false);
    assert.deepEqual((await json("POST", "/v1/messages/search", agent, { mailbox: address })).body.messages, []);
    // Complete this fixture's already-confirmed provider retirement/purge and advance
    // cooldown bookkeeping. Native lifecycle tests exercise the scheduled purger;
    // these HTTP reads check that recycled names cannot become authorization keys.
    await db.prepare("DELETE FROM messages WHERE id=?1").bind(id).run();
    await db.prepare("UPDATE addresses SET needs_reconcile=0,purged_at=1,cooldown_until=1 WHERE address=?1 AND state='retired' AND cf_rule_id IS NULL")
      .bind(address).run();
    const reused = await json("POST", "/v1/addresses", agent, { local_part: "quick-test", kind: "tmpaddr" });
    assert.equal(reused.status, 201, JSON.stringify(reused.body));
    const replacement = (await json("GET", "/v1/addresses", agent)).body.addresses.find((row) => row.address === address);
    assert.notEqual(replacement.generation, current.generation);
    const successor = await message(address, replacement.generation, "successor data");
    assert.equal((await json("GET", `/v1/messages/${id}`, agent)).status, 404);
    assert.equal(await archiveStatus(id, agent), 404);
    assert.deepEqual((await json("POST", "/v1/messages/search", agent, { mailbox: address })).body.messages.map((row) => row.id), [successor]);

    // A genuinely elapsed deadline must deny access before a maintenance invocation.
    const expiringAddress = `deadline@${temporaryDomain}`;
    const generation = randomUUID();
    const expires = Date.now() + 5000;
    await db.prepare("INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,state,created_at,kind,generation,expires_at) VALUES(?1,'deadline',?2,'owner',1,'active',?3,'tmpaddr',?4,?5)")
      .bind(expiringAddress, issuer, expires - 6 * 60 * 60 * 1000, generation, expires).run();
    assert.equal((await acquire(agent, expiringAddress, "write")).status, 200);
    const expiringId = await message(expiringAddress, generation);
    assert.equal((await json("GET", `/v1/messages/${expiringId}`, agent)).status, 200);
    await setTimeout(Math.max(0, expires - Date.now()) + 100);
    assert.equal((await json("GET", `/v1/messages/${expiringId}`, agent)).status, 404);
    assert.equal(await archiveStatus(expiringId, agent), 404);
    assert.equal((await json("GET", "/v1/addresses", agent)).body.addresses.some((row) => row.address === expiringAddress), false);
    assert.deepEqual((await json("POST", "/v1/messages/search", agent, { mailbox: expiringAddress })).body.messages, []);
  });
});

test("an uncertain provision preserves the creator's writer reservation through actual Cron activation", async () => {
  await fixture(async ({ db, json, activate, acquire, message, rules, scheduled }) => {
    const user = await activate("user");
    for (const name of ["creator", "rival"]) {
      assert.equal((await json("POST", "/v1/profiles", user, { name })).status, 200);
    }
    const creator = await activate("creator");
    const rival = await activate("rival");
    const address = `uncertain-provision@${temporaryDomain}`;
    const add = () => json("POST", "/v1/addresses", creator,
      { local_part: "uncertain-provision", kind: "tmpaddr" });
    assert.equal((await add()).status, 503, "a lost create acknowledgment must not claim activation");
    const pending = await db.prepare("SELECT state,generation,cf_rule_id FROM addresses WHERE address=?1").bind(address).first();
    assert.equal(pending.state, "provisioning");
    assert.equal(pending.cf_rule_id, null, "the uncertain provider result supplied no adopted route identity");
    const reservation = await db.prepare("SELECT profile_id,session_token,mode,address_generation FROM mailbox_leases WHERE address=?1")
      .bind(address).first();
    assert.deepEqual(reservation, { profile_id: creator.profile_id, session_token: creator.session_token,
      mode: "write", address_generation: pending.generation });
    assert.equal((await acquire(rival, address, "write")).status, 409);
    assert.equal((await add()).status, 202, "recovery consumes pending state, not a second provider create");
    assert.equal(rules.size, 1);
    await scheduled();
    const activated = await db.prepare("SELECT state,cf_rule_id FROM addresses WHERE address=?1").bind(address).first();
    assert.equal(activated.state, "active");
    assert.equal(activated.cf_rule_id, [...rules.keys()][0]);
    const id = await message(address, pending.generation);
    assert.equal((await json("GET", `/v1/messages/${id}`, creator)).status, 200,
      "Cron activation must not require the creator to retry acquire");
    for (const mode of ["read", "write"]) assert.equal((await acquire(rival, address, mode)).status, 409);
    assert.equal(rules.size, 1, "neither reconciliation nor pending recovery creates another route");
    await db.prepare("UPDATE mail_profiles SET session_expires_at=1 WHERE id=?1").bind(creator.profile_id).run();
    assert.equal((await acquire(rival, address, "write")).status, 200,
      "an expired creator session cannot retain an active mailbox reservation");
    assert.equal((await json("GET", `/v1/messages/${id}`, creator)).body.code, "profile_session_expired");
    assert.equal((await json("GET", `/v1/messages/${id}`, rival)).status, 200);
  }, { ambiguousCreates: 1, maintenance: true });
});
