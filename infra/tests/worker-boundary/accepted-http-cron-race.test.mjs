/**
 * Deterministic HTTP-vs-Cron regression using the real built Rust/Wasm Worker.
 * Synthetic provider only. Run separately in hosted CI after worker-build.
 */
import assert from "node:assert/strict";
import { createHash, generateKeyPairSync, sign } from "node:crypto";
import { copyFile, unlink } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { Miniflare } from "miniflare";
import { applyMigrations } from "./migration-fixture.mjs";
import { workerModuleRules } from "./worker-module-rules.mjs";
import { draftZip } from "./accepted-race-zip.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const worker = path.resolve(here, "../../../crates/mail-worker");
const issuer = "https://identity-staging.moesegfault.dev";
const owner = "synthetic-http-cron-owner";
const sender = "recovery-synthetic@mail-staging.moesegfault.dev";
const idem = "2532c8f9-0d85-48d6-ab90-751763ca4d0d";
const body = "synthetic race text ".repeat(8000);
const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });

/** Explicit barrier rather than timing sleeps to induce the interleaving. */
function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}

/** Sign a local token; real signature, issuer and ownership checks remain active. */
function bearer() {
  const header = Buffer.from(JSON.stringify({ alg: "RS256", typ: "JWT", kid: "race" })).toString("base64url");
  const payload = Buffer.from(JSON.stringify({ iss: issuer, sub: owner, aud: "amail-cli-staging", exp: Math.floor(Date.now() / 1000) + 600, token_use: "access" })).toString("base64url");
  const input = `${header}.${payload}`;
  return `Bearer ${input}.${sign("RSA-SHA256", Buffer.from(input), privateKey).toString("base64url")}`;
}

/** Bound acquisition; distinguish a wrong/missing SQL hook from product behavior. */
async function barrierArrived(arrived, pending) {
  let timer;
  try {
    await Promise.race([
      arrived.promise,
      pending.then(async response => { throw new Error(`HTTP completed before committed-acceptance barrier: ${response.status}`); }),
      new Promise((_, reject) => { timer = setTimeout(() => reject(new Error("committed-acceptance barrier timed out")), 15_000); }),
    ]);
  } finally { clearTimeout(timer); }
}

/** Exercise native HTTP admission, then Cron and optional public delete/real GC. */
async function race(deleteBeforeResume, expireClaim = false) {
  const entry = path.join(worker, "build/worker/accepted-race-test.mjs");
  await copyFile(path.join(here, "accepted-race-entry.mjs"), entry);
  const arrived = deferred(), release = deferred();
  let sends = 0, barriers = 0, claims = 0, unexpected = 0, pending;
  const jwk = publicKey.export({ format: "jwk" });
  const mf = new Miniflare({ cf: false, workers: [{
    name: "amail-accepted-race", modules: true, scriptPath: entry,
    modulesRoot: path.join(worker, "build"), modulesRules: workerModuleRules,
    compatibilityDate: "2026-08-06",
    bindings: { RACE_CLAIM_BARRIER: expireClaim ? "1" : "0", IDENTITY_ISSUER: issuer, OIDC_CLIENT_ID: "amail-cli-staging",
      CF_ZONE_ID: "synthetic-zone", CF_EMAIL_ROUTING_TOKEN: "synthetic-token",
      MAIL_DOMAIN: "mail-staging.moesegfault.dev", EMAIL_INGRESS_WORKER_NAME: "synthetic-ingress" },
    d1Databases: ["MAIL_DB"], r2Buckets: ["MAIL_BODIES"],
    serviceBindings: { TEST_CONTROL: async request => {
      if (request.method !== "POST" || !["https://test.invalid/send", "https://test.invalid/after-accepted", "https://test.invalid/after-claim"].includes(request.url)) {
        unexpected++;
        throw new Error("unexpected synthetic control method or URL");
      }
      if (request.url === "https://test.invalid/send") {
        sends++;
        return Response.json({ messageId: "synthetic-race-provider" });
      }
      if (request.url === "https://test.invalid/after-accepted") {
        barriers++;
        if (expireClaim) return new Response(null, { status: 204 });
        arrived.resolve();
        await release.promise;
        return new Response(null, { status: 204 });
      }
      if (request.url === "https://test.invalid/after-claim") {
        claims++;
        if (claims === 1) { arrived.resolve(); await release.promise; }
        return new Response(null, { status: 204 });
      }
      unexpected++;
      throw new Error("unexpected synthetic control request");
    } },
    outboundService(request) {
      if (request.method !== "GET" || ![
        `${issuer}/.well-known/openid-configuration`, `${issuer}/jwks`,
        "https://api.cloudflare.com/client/v4/zones/synthetic-zone/email/routing/rules?per_page=50&page=1",
      ].includes(request.url)) {
        unexpected++;
        throw new Error("unexpected synthetic external method or URL");
      }
      if (request.url === `${issuer}/.well-known/openid-configuration`) return Response.json({ issuer, jwks_uri: `${issuer}/jwks` });
      if (request.url === `${issuer}/jwks`) return Response.json({ keys: [{ ...jwk, kid: "race", alg: "RS256", use: "sig" }] });
      if (request.url === "https://api.cloudflare.com/client/v4/zones/synthetic-zone/email/routing/rules?per_page=50&page=1") return Response.json({ success: true, result: [], result_info: { total_pages: 1 } });
      unexpected++;
      throw new Error("unexpected synthetic external request");
    },
  }] });
  try {
    const { MAIL_DB: db, MAIL_BODIES: bucket } = await mf.getBindings();
    await applyMigrations(db, path.join(worker, "migrations"));
    await db.prepare("INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,state,created_at) VALUES(?1,'recovery-synthetic',?2,?3,0,'active',?4)").bind(sender, issuer, owner, Date.now()).run();
    await db.prepare("UPDATE embedding_dependency SET blocked_until=?1 WHERE id=1").bind(Date.now() + 86_400_000).run();
    // A synthetic one-recipient canary exercises normal SQL admission while global held.
    await db.prepare("UPDATE send_release_gates SET canary_owner_iss=?1,canary_owner_sub=?2,canary_recipient_sha256=?3,canary_expires_at=unixepoch()+600,actor='synthetic-fixture',case_ref='synthetic-race' WHERE id=1")
      .bind(issuer, owner, createHash("sha256").update("synthetic@example.invalid").digest("hex")).run();
    const bytes = draftZip(body, sender), authorization = bearer();
    const send = () => mf.dispatchFetch("https://mail-staging.moesegfault.dev/v1/messages/send", { method: "POST", headers: { Authorization: authorization, "Content-Type": "application/zip", "Idempotency-Key": idem }, body: bytes });
    pending = send();
    await barrierArrived(arrived, pending);
    assert.equal(barriers, 1, "exact committed acceptance SQL matched once");
    const journalColumns = expireClaim ? "message_id,provider_id,state,index_projection_token,index_projection_lease_until" : "message_id,provider_id,state";
    const journal = await db.prepare(`SELECT ${journalColumns} FROM send_requests WHERE idem_key=?1`).bind(idem).first();
    assert.equal(journal.state, "accepted");
    assert.equal(journal.provider_id, "synthetic-race-provider");
    assert.ok(await bucket.get(`messages/${journal.message_id}.zip`));
    assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM messages").first()).n, 0);
    assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM message_text_chunks").first()).n, 0);
    if (expireClaim) {
      assert.equal(claims, 1, "first HTTP lease acquisition committed before pause");
      assert.ok(journal.index_projection_token);
      assert.ok(journal.index_projection_lease_until > Date.now());
      await (await mf.getWorker()).scheduled();
      const stillOwned = await db.prepare("SELECT state,index_projection_token FROM send_requests WHERE idem_key=?1").bind(idem).first();
      assert.equal(stillOwned.state, "accepted");
      assert.equal(stillOwned.index_projection_token, journal.index_projection_token);
      assert.equal(claims, 1, "Cron cannot claim an unexpired HTTP lease");
      assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM messages").first()).n, 0);
      await db.prepare("UPDATE send_requests SET index_projection_lease_until=0 WHERE idem_key=?1").bind(idem).run();
    }
    await (await mf.getWorker()).scheduled();
    if (expireClaim) assert.equal(claims, 2, "Cron takes a fresh lease only after explicit expiry");
    assert.equal((await db.prepare("SELECT state FROM send_requests WHERE idem_key=?1").bind(idem).first()).state, "sent");
    assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM messages WHERE id=?1 AND deleted_at IS NULL").bind(journal.message_id).first()).n, 1);
    if (deleteBeforeResume) {
      const deleted = await mf.dispatchFetch(`https://mail-staging.moesegfault.dev/v1/messages/${journal.message_id}`, { method: "DELETE", headers: { Authorization: authorization } });
      assert.ok(deleted.ok, `owner delete failed: ${deleted.status}`);
      await (await mf.getWorker()).scheduled();
      assert.equal(await bucket.get(`messages/${journal.message_id}.zip`), null, "real GC removed the immutable archive");
      assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM messages").first()).n, 0);
    }
    // Native ledger snapshots prove resumed HTTP/replay do not recharge storage.
    const reservationBefore = (await db.prepare("SELECT id,owner_iss,owner_sub,bytes,state FROM storage_reservations ORDER BY id").all()).results;
    const usageBefore = (await db.prepare("SELECT owner_iss,owner_sub,used_bytes FROM storage_usage ORDER BY owner_iss,owner_sub").all()).results;
    release.resolve();
    const response = await pending;
    assert.equal(response.status, 202, "late same-journal writer returns accepted outcome without republishing");
    const result = await response.json();
    assert.equal(result.id, journal.message_id);
    const replay = await send();
    assert.equal(replay.status, 202);
    assert.equal((await replay.json()).id, journal.message_id);
    assert.equal(sends, 1, "neither resumed projection nor replay sends again");
    assert.equal(barriers, 1);
    await (await mf.getWorker()).scheduled();
    assert.deepEqual((await db.prepare("SELECT id,owner_iss,owner_sub,bytes,state FROM storage_reservations ORDER BY id").all()).results, reservationBefore);
    assert.deepEqual((await db.prepare("SELECT owner_iss,owner_sub,used_bytes FROM storage_usage ORDER BY owner_iss,owner_sub").all()).results, usageBefore);
    if (deleteBeforeResume) {
      for (const table of ["messages", "message_text_chunks", "storage_reservations", "embedding_work"]) {
        assert.equal((await db.prepare(`SELECT COUNT(*) AS n FROM ${table}`).first()).n, 0, `${table} must not resurrect`);
      }
      assert.equal((await db.prepare("SELECT used_bytes FROM storage_usage").first()).used_bytes, 0);
    } else {
      const row = await db.prepare("SELECT body_text FROM messages WHERE id=?1").bind(journal.message_id).first();
      const chunks = (await db.prepare("SELECT chunk_index,body FROM message_text_chunks WHERE message_id=?1 ORDER BY chunk_index").bind(journal.message_id).all()).results;
      chunks.forEach((chunk, n) => assert.equal(chunk.chunk_index, n + 1));
      assert.equal(row.body_text + chunks.map(chunk => chunk.body).join(""), body);
      assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM messages").first()).n, 1);
    }
    assert.equal(unexpected, 0);
  } finally {
    release.resolve();
    if (pending) await pending.catch(() => {});
    await mf.dispose();
    await unlink(entry);
  }
}

test("HTTP acceptance paused after commit converges with Cron's completed projection", { timeout: 90_000 }, async () => race(false));
test("late HTTP projector cannot resurrect after Cron, owner delete and real GC", { timeout: 90_000 }, async () => race(true));

/** A real paused HTTP projector loses its token after persisted deadline expiry. */
test("expired HTTP projection token cannot resurrect after fresh Cron lease and delete", { timeout: 90_000 }, async () => race(true, true));
