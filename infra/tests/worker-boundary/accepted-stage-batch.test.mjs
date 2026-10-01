/** Hosted-only native workerd staging transactions; no provider or production hooks. */
import assert from "node:assert/strict";
import test from "node:test";
import { createHash, generateKeyPairSync, sign } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Miniflare } from "miniflare";
import { applyMigrations } from "./migration-fixture.mjs";
import { workerModuleRules } from "./worker-module-rules.mjs";
import { draftZip } from "./accepted-race-zip.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const issuer = "https://identity-staging.moesegfault.dev", owner = "synthetic-stage-owner";
const sender = "stage-synthetic@mail-staging.moesegfault.dev";
const maximum = "q".repeat(4_000_000), groups = [8, 8, 8, 8, 8, 8, 8, 8, 2];
const outboundSlot = 1_680_000_300_000;
const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });

/** Explicit barriers detect interleavings without scheduling sleeps. */
function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}

/** Real local RSA authentication preserves the public owner-scoped DELETE path. */
function bearer(subject = owner) {
  const head = Buffer.from(JSON.stringify({ alg: "RS256", kid: "stage" })).toString("base64url");
  const body = Buffer.from(JSON.stringify({ iss: issuer, sub: subject, aud: "amail-cli-staging", token_use: "access", exp: Math.floor(Date.now() / 1000) + 600 })).toString("base64url");
  const input = `${head}.${body}`;
  return `Bearer ${input}.${sign("RSA-SHA256", Buffer.from(input), privateKey).toString("base64url")}`;
}

/** Bound acquisition distinguishes a missing observer hook from product behavior. */
async function arrived(barrier, pending) {
  let timer;
  try {
    await Promise.race([barrier.promise, pending.then(() => { throw new Error("scheduled completed before stage barrier"); }),
      new Promise((_, reject) => { timer = setTimeout(() => reject(new Error("stage barrier timed out")), 15_000); })]);
  } finally { clearTimeout(timer); }
}

/** Native schema, storage, Wasm and authentication; every network destination is local. */
async function fixture(run, control = async () => new Response(null, { status: 204 })) {
  let unexpected = 0;
  const jwk = publicKey.export({ format: "jwk" });
  const mf = new Miniflare({ cf: false, workers: [{
    name: "amail-stage-synthetic", modules: true, modulesRoot: root, modulesRules: workerModuleRules,
    scriptPath: path.join(root, "infra/tests/worker-boundary/accepted-stage-observer.mjs"), compatibilityDate: "2026-08-06",
    bindings: { IDENTITY_ISSUER: issuer, OIDC_CLIENT_ID: "amail-cli-staging", CF_ZONE_ID: "synthetic-zone", CF_EMAIL_ROUTING_TOKEN: "synthetic-token",
      MAIL_DOMAIN: "mail-staging.moesegfault.dev", EMAIL_INGRESS_WORKER_NAME: "synthetic-ingress" },
    d1Databases: ["MAIL_DB"], r2Buckets: ["MAIL_BODIES"],
    serviceBindings: { TEST_CONTROL: async request => {
      if (request.method !== "POST" || !["https://test.invalid/after-stage", "https://test.invalid/before-publication"].includes(request.url)) {
        unexpected++; throw new Error("unexpected synthetic stage control");
      }
      return control(new URL(request.url).pathname, (await request.json()).call);
    } },
    outboundService(request) {
      if (request.method === "GET" && request.url === `${issuer}/.well-known/openid-configuration`) return Response.json({ issuer, jwks_uri: `${issuer}/jwks` });
      if (request.method === "GET" && request.url === `${issuer}/jwks`) return Response.json({ keys: [{ ...jwk, kid: "stage", alg: "RS256", use: "sig" }] });
      if (request.method === "GET" && request.url === "https://api.cloudflare.com/client/v4/zones/synthetic-zone/email/routing/rules?per_page=50&page=1") return Response.json({ success: true, result: [], result_info: { total_pages: 1 } });
      unexpected++; throw new Error("unexpected synthetic stage egress");
    },
  }] });
  try {
    const { MAIL_DB: db, MAIL_BODIES: bucket } = await mf.getBindings();
    await applyMigrations(db, path.join(root, "crates/mail-worker/migrations"));
    await db.prepare("INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,state,created_at) VALUES(?1,'stage-synthetic',?2,?3,0,'active',?4)").bind(sender, issuer, owner, Date.now()).run();
    await db.prepare("UPDATE embedding_dependency SET blocked_until=?1 WHERE id=1").bind(Date.now() + 86_400_000).run();
    const configure = async policy => { assert.equal((await mf.dispatchFetch("https://synthetic.invalid/stage-policy", { method: "POST", body: JSON.stringify(policy) })).status, 200); };
    const tick = async () => {
      const result = await (await mf.getWorker()).scheduled({ scheduledTime: new Date(outboundSlot) });
      assert.equal(result.outcome, "ok"); assert.equal(unexpected, 0);
    };
    const stats = async () => (await mf.dispatchFetch("https://synthetic.invalid/stage-stats")).json();
    await configure({});
    await run({ db, bucket, mf, configure, tick, stats });
    assert.equal(unexpected, 0);
  } finally { await mf.dispose(); }
}

/** Seed through the production held-canary trigger, then revoke the consumed grant. */
async function accepted(db, bucket, id, body = maximum) {
  const bytes = draftZip(body, sender), now = Date.now();
  await db.prepare("UPDATE send_release_gates SET canary_owner_iss=?1,canary_owner_sub=?2,canary_recipient_sha256=?3,canary_expires_at=unixepoch()+600,canary_used_by=NULL,actor='synthetic-fixture',case_ref='synthetic-stage',updated_at=unixepoch() WHERE id=1")
    .bind(issuer, owner, createHash("sha256").update("synthetic@example.invalid").digest("hex")).run();
  await db.prepare("INSERT INTO send_requests(owner_iss,owner_sub,idem_key,payload_hash,message_id,provider_id,quota_reserved,state,created_at) VALUES(?1,?2,?3,?4,?3,?5,1,'accepted',?6)")
    .bind(issuer, owner, id, createHash("sha256").update(bytes).digest("hex"), `synthetic-provider-${id}`, now).run();
  assert.equal((await db.prepare("SELECT canary_used_by FROM send_release_gates WHERE id=1").first()).canary_used_by, id);
  assert.equal((await db.prepare("SELECT state FROM send_policy WHERE scope='global' AND owner_iss='*' AND owner_sub='*'").first()).state, "held");
  await db.prepare("UPDATE send_release_gates SET canary_expires_at=unixepoch() WHERE id=1").run();
  await db.prepare("INSERT INTO storage_reservations(id,owner_iss,owner_sub,bytes,state,created_at) VALUES(?1,?2,?3,?4,'reserved',?5)").bind(id, issuer, owner, bytes.length, now).run();
  await bucket.put(`messages/${id}.zip`, bytes);
}

/** Direct native readback avoids trusting production reconstruction or result metadata. */
async function journal(db, id) {
  return db.prepare("SELECT state,index_projection_token,index_projection_lease_until FROM send_requests WHERE message_id=?1").bind(id).first();
}

/** Exact ordered UTF-8 reconstruction, with compact assertions for maximum bodies. */
async function complete(db, id, expected) {
  assert.equal((await journal(db, id)).state, "sent");
  const row = await db.prepare("SELECT body_text FROM messages WHERE id=?1 AND deleted_at IS NULL").bind(id).first();
  assert.ok(row, "published live row exists");
  const { results } = await db.prepare("SELECT chunk_index,body FROM message_text_chunks WHERE message_id=?1 ORDER BY chunk_index").bind(id).all();
  results.forEach((chunk, index) => { assert.equal(chunk.chunk_index, index + 1); assert.ok(Buffer.byteLength(chunk.body) <= 60_000); });
  assert.ok(row.body_text + results.map(chunk => chunk.body).join("") === expected, "byte-exact complete projection");
}

/** Retrying keeps the archive and durable owner fence, but makes this synthetic item due. */
async function retry(db, id, configure, tick) {
  await db.prepare("UPDATE send_requests SET index_next_attempt_at=0 WHERE message_id=?1").bind(id).run();
  await configure({}); await tick();
}

test("maximum text uses nine actual bounded staging batches and exact replay", async () => fixture(async ({ db, bucket, configure, tick, stats }) => {
  await accepted(db, bucket, "stage-max"); await tick(); await complete(db, "stage-max", maximum);
  const before = await stats();
  assert.equal(before.chunkRuns, 0);
  assert.deepEqual(before.stage.map(group => group.size), groups);
  before.stage.forEach((group, index) => {
    assert.equal(group.first, index * 8 + 1); assert.equal(group.last, Math.min(index * 8 + 8, 66));
    assert.ok(group.commonClock); assert.ok(group.bytes <= 480_000);
  });
  const ledger = await db.prepare("SELECT bytes,state FROM storage_reservations WHERE id='stage-max'").first();
  await configure({}); await tick();
  assert.deepEqual((await stats()).stage, []);
  assert.deepEqual(await db.prepare("SELECT bytes,state FROM storage_reservations WHERE id='stage-max'").first(), ledger);
  await complete(db, "stage-max", maximum);
}));

test("chunk boundary counts never submit an empty staging transaction", async () => fixture(async ({ db, bucket, configure, tick, stats }) => {
  for (const count of [0, 1, 7, 8, 9, 65, 66]) {
    const id = `stage-boundary-${count}`, body = "q".repeat(count * 60_000 + 1);
    await accepted(db, bucket, id, body); await configure({}); await tick(); await complete(db, id, body);
    assert.deepEqual((await stats()).stage.map(group => group.size), Array.from({ length: Math.ceil(count / 8) }, (_, index) => Math.min(8, count - index * 8)));
  }
}));

test("maximum mixed-width UTF-8 remains exact across group boundaries", async () => fixture(async ({ db, bucket, tick, stats }) => {
  const body = "火🔥".repeat(571_428) + "xxxx";
  assert.equal(Buffer.byteLength(body), 4_000_000);
  await accepted(db, bucket, "stage-utf8", body); await tick(); await complete(db, "stage-utf8", body);
  assert.deepEqual((await stats()).stage.map(group => group.size), groups);
}));

test("native group failure rolls back all eight members but preserves earlier groups", async () => fixture(async ({ db, bucket, configure, tick, stats }) => {
  await accepted(db, bucket, "stage-rollback");
  await db.exec("CREATE TRIGGER synthetic_stage_fault BEFORE INSERT ON message_text_chunks WHEN NEW.message_id='stage-rollback' AND NEW.chunk_index=20 BEGIN SELECT RAISE(ABORT,'synthetic group fault'); END;");
  await tick();
  assert.deepEqual((await stats()).stage.map(group => group.size), [8, 8, 8]);
  assert.equal((await journal(db, "stage-rollback")).state, "accepted");
  assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM messages WHERE id='stage-rollback'").first()).n, 0);
  assert.deepEqual((await db.prepare("SELECT chunk_index FROM message_text_chunks WHERE message_id='stage-rollback' ORDER BY chunk_index").all()).results.map(row => row.chunk_index), Array.from({ length: 16 }, (_, index) => index + 1));
  assert.ok(await bucket.get("messages/stage-rollback.zip"));
  await db.exec("DROP TRIGGER synthetic_stage_fault;");
  await retry(db, "stage-rollback", configure, tick); await complete(db, "stage-rollback", maximum);
}));

for (const fault of ["rejectAfterStage", "shortAfterStage", "falseAfterStage"]) {
  test(`${fault}: committed group cannot authorize publication until exact fresh retry`, async () => fixture(async ({ db, bucket, configure, tick }) => {
    const id = `stage-${fault}`;
    await accepted(db, bucket, id); await configure({ [fault]: 3 }); await tick();
    assert.equal((await journal(db, id)).state, "accepted");
    assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM messages WHERE id=?1").bind(id).first()).n, 0);
    assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM message_text_chunks WHERE message_id=?1").bind(id).first()).n, 24);
    assert.ok(await bucket.get(`messages/${id}.zip`));
    await retry(db, id, configure, tick); await complete(db, id, maximum);
  }));
}

test("expired old token cannot stage or publish while new owner remains accepted", { timeout: 60_000 }, async () => {
  const oldArrived = deferred(), oldRelease = deferred(), newArrived = deferred(), newRelease = deferred();
  await fixture(async ({ db, bucket, configure, tick }) => {
    let oldPending, newPending;
    try {
      await accepted(db, bucket, "stage-stale"); await configure({ pauseAfterStage: 1, pausePublication: true });
      oldPending = tick(); await arrived(oldArrived, oldPending);
      const first = await journal(db, "stage-stale"); assert.ok(first.index_projection_token);
      await db.prepare("UPDATE send_requests SET index_projection_lease_until=0,index_next_attempt_at=0 WHERE message_id='stage-stale'").run();
      newPending = tick(); await arrived(newArrived, newPending);
      const second = await journal(db, "stage-stale");
      assert.equal(second.state, "accepted"); assert.ok(second.index_projection_token); assert.notEqual(second.index_projection_token, first.index_projection_token);
      // Corrupt a staged value only in this isolated fixture. A stale token must
      // not overwrite it even while the new token is accepted and owns publication.
      await db.prepare("UPDATE message_text_chunks SET body='synthetic-new-owner-marker' WHERE message_id='stage-stale' AND chunk_index=9").run();
      oldRelease.resolve(); await oldPending;
      assert.equal((await journal(db, "stage-stale")).index_projection_token, second.index_projection_token);
      assert.equal((await journal(db, "stage-stale")).state, "accepted");
      assert.equal((await db.prepare("SELECT body FROM message_text_chunks WHERE message_id='stage-stale' AND chunk_index=9").first()).body, "synthetic-new-owner-marker");
      assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM messages WHERE id='stage-stale'").first()).n, 0);
      // Restore only the test marker before releasing the legitimately prepared
      // publication; production ready() checks indices, not fixture corruption.
      await db.prepare("UPDATE message_text_chunks SET body=?1 WHERE message_id='stage-stale' AND chunk_index=9").bind("q".repeat(60_000)).run();
      newRelease.resolve(); await newPending; await complete(db, "stage-stale", maximum);
    } finally { oldRelease.resolve(); newRelease.resolve(); await Promise.allSettled([oldPending, newPending].filter(Boolean)); }
  }, async (kind, call) => {
    if (kind === "/after-stage" && call === 1) { oldArrived.resolve(); await oldRelease.promise; }
    if (kind === "/before-publication" && call === 1) { newArrived.resolve(); await newRelease.promise; }
    return new Response(null, { status: 204 });
  });
});

test("public DELETE during grouped repair preserves tombstone and eventual real GC", { timeout: 60_000 }, async () => {
  const paused = deferred(), release = deferred();
  await fixture(async ({ db, bucket, mf, configure, tick }) => {
    let pending;
    try {
      await accepted(db, bucket, "stage-delete"); await tick(); await complete(db, "stage-delete", maximum);
      await db.prepare("UPDATE send_requests SET state='accepted',index_next_attempt_at=0 WHERE message_id='stage-delete'").run();
      await configure({ pauseAfterStage: 1 }); pending = tick(); await arrived(paused, pending);
      const url = "https://mail-staging.moesegfault.dev/v1/messages/stage-delete";
      assert.equal((await mf.dispatchFetch(url, { headers: { Authorization: bearer() } })).status, 404, "accepted legacy row stays hidden");
      assert.equal((await mf.dispatchFetch(url, { method: "DELETE", headers: { Authorization: bearer("synthetic-foreign") } })).status, 404);
      assert.equal((await mf.dispatchFetch(url, { method: "DELETE", headers: { Authorization: bearer() } })).status, 204);
      assert.ok((await db.prepare("SELECT deleted_at FROM messages WHERE id='stage-delete'").first()).deleted_at > 0);
      assert.equal((await mf.dispatchFetch(url, { method: "DELETE", headers: { Authorization: bearer() } })).status, 404);
      release.resolve(); await pending;
      assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM messages WHERE id='stage-delete' AND deleted_at IS NULL").first()).n, 0);
      await configure({}); await tick();
      assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM messages WHERE id='stage-delete'").first()).n, 0);
      assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM message_text_chunks WHERE message_id='stage-delete'").first()).n, 0);
      assert.equal(await bucket.get("messages/stage-delete.zip"), null);
    } finally { release.resolve(); if (pending) await Promise.allSettled([pending]); }
  }, async (kind, call) => {
    if (kind === "/after-stage" && call === 1) { paused.resolve(); await release.promise; }
    return new Response(null, { status: 204 });
  });
});
