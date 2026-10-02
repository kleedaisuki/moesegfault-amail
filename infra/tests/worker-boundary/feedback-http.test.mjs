/** Real Rust/Wasm progressive feedback reads against synthetic owner-scoped D1. */
import assert from "node:assert/strict";
import { generateKeyPairSync, sign } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { Miniflare } from "miniflare";
import { applyMigrations } from "./migration-fixture.mjs";
import { workerModuleRules } from "./worker-module-rules.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const worker = path.join(root, "crates/mail-worker");
const issuer = "https://identity-staging.moesegfault.dev";
const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
const id = "a0000000-0000-4000-8000-000000000001";
const key = "b0000000-0000-4000-8000-000000000001";

/** Authenticate actual APIs through the production verifier with local signed tokens. */
function token(sub) {
  const header = Buffer.from(JSON.stringify({ alg: "RS256", kid: "synthetic" })).toString("base64url");
  const payload = Buffer.from(JSON.stringify({ iss: issuer, sub, aud: "amail-cli-staging",
    token_use: "access", exp: Math.floor(Date.now() / 1000) + 300 })).toString("base64url");
  const input = `${header}.${payload}`;
  return `${input}.${sign("RSA-SHA256", Buffer.from(input), privateKey).toString("base64url")}`;
}

test("feedback spaces preserve owner isolation, bounded discovery and stable continuation", async () => {
  let unexpected = 0;
  const jwk = publicKey.export({ format: "jwk" });
  const mf = new Miniflare({ cf: false, workers: [{
    name: "feedback-synthetic", modules: true, scriptPath: path.join(worker, "entry/api.mjs"),
    modulesRoot: root, modulesRules: workerModuleRules, compatibilityDate: "2026-08-06",
    d1Databases: ["MAIL_DB"], bindings: { IDENTITY_ISSUER: issuer,
      OIDC_CLIENT_ID: "amail-cli-staging", MAIL_DOMAIN: "mail-staging.moesegfault.dev" },
    async outboundService(request) {
      if (request.url === `${issuer}/.well-known/openid-configuration`) {
        return Response.json({ issuer, jwks_uri: `${issuer}/jwks` });
      }
      if (request.url === `${issuer}/jwks`) {
        return Response.json({ keys: [{ ...jwk, kid: "synthetic", alg: "RS256", use: "sig" }] });
      }
      unexpected++;
      throw new Error("unmatched feedback egress");
    },
  }] });
  try {
    const db = await mf.getD1Database("MAIL_DB", "feedback-synthetic");
    await applyMigrations(db, path.join(worker, "migrations"));
    await db.prepare("INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,state,created_at) VALUES('owner@mail-staging.moesegfault.dev','owner',?1,'owner',0,'active',0)").bind(issuer).run();
    await db.prepare("INSERT INTO messages(id,address,owner_iss,owner_sub,direction,sender,recipients_json,subject,body_text,metadata_json,received_at,has_html,has_text,attachment_count,r2_key,size_bytes) VALUES(?1,'owner@mail-staging.moesegfault.dev',?2,'owner','outbound','owner@mail-staging.moesegfault.dev','[\"recipient@example.invalid\"]','private subject','private body','{}',1,0,1,0,'synthetic',1)").bind(id, issuer).run();
    // SQL admission is a separately exercised mutation boundary. Seed synthetic
    // preexisting receipts without authorizing any provider send in this read test.
    await db.exec("DROP TRIGGER send_request_policy_guard");
    await db.prepare("INSERT INTO send_requests(owner_iss,owner_sub,idem_key,payload_hash,message_id,state,created_at) VALUES(?1,'owner',?2,'private-payload-hash',?3,'sent',1)").bind(issuer, key, id).run();
    const at = Math.floor(Date.now() / 1000);
    const event = async (eventId, kind, owner = "owner", message = id) => db.prepare("INSERT INTO provider_events(event_id,provider_id,local_message_id,owner_iss,owner_sub,recipient,kind,occurred_at,received_at) VALUES(?1,'private-provider-id',?2,?3,?4,'recipient@example.invalid',?5,?6,?6)").bind(eventId, message, issuer, owner, kind, at).run();
    await event("event-a", "deferred");
    await event("event-b", "delivered");
    await event("foreign-event", "failed", "foreign");

    /** Dispatch JSON reads and preserve HTTP status for typed-error assertions. */
    const get = async (url, owner = "owner") => {
      const response = await mf.dispatchFetch(`https://mail.invalid${url}`, {
        headers: { authorization: `Bearer ${token(owner)}` },
      });
      return { status: response.status, body: await response.json() };
    };
    const receipt = await get(`/v1/sends/${key}`);
    assert.equal(receipt.status, 200);
    assert.equal(receipt.body.state, "accepted", "internal archived state is not delivery confirmation");
    assert.equal(receipt.body.projection_state, "archived");
    assert.equal(receipt.body.links.outcomes, `/v1/messages/${id}/outcomes`);
    assert.equal((await get(`/v1/sends/${key}`, "foreign")).status, 404);
    assert.equal((await get("/v1/sends/not-a-uuid")).body.code, "invalid_idempotency_key");
    const known = await get(`/v1/messages/${id}/outcomes`);
    assert.equal(known.body.outcomes[0].kind, "delivered", "deferred does not regress known delivery");
    assert.equal((await get(`/v1/messages/${id}/outcomes`, "foreign")).status, 404);
    const details = await get(`/v1/messages/${id}`);
    assert.ok(details.body.links.events);
    assert.equal(details.body.events, undefined, "get advertises the space without embedding history");
    // Synthetic storage permits a body above a normal D1 response-row budget.
    // Feedback visibility must project SELECT 1, never retrieve this content.
    const largeBody = "unrelated-body-".repeat(170000);
    await db.prepare("UPDATE messages SET body_text=?1 WHERE id=?2").bind(largeBody, id).run();
    assert.equal((await get(`/v1/sends/${key}`)).body.links.outcomes, `/v1/messages/${id}/outcomes`);
    assert.equal((await get(`/v1/messages/${id}/outcomes`)).status, 200);
    assert.equal((await get(`/v1/messages/${id}/events`)).status, 200);
    // Incomplete projection and undeleted inbound rows must not authorize reads.
    await db.prepare("UPDATE send_requests SET state='accepted' WHERE idem_key=?1").bind(key).run();
    assert.equal((await get(`/v1/sends/${key}`)).body.links, undefined);
    assert.equal((await get(`/v1/messages/${id}/outcomes`)).status, 404);
    await db.prepare("UPDATE send_requests SET state='sent' WHERE idem_key=?1").bind(key).run();
    await db.prepare("UPDATE messages SET direction='inbound' WHERE id=?1").bind(id).run();
    assert.equal((await get(`/v1/messages/${id}/events`)).status, 404);
    await db.prepare("UPDATE messages SET direction='outbound' WHERE id=?1").bind(id).run();
    const first = await get("/v1/events?limit=1");
    assert.equal(first.status, 200);
    assert.deepEqual(first.body.events.map((e) => e.event_id), ["event-b"]);
    assert.ok(first.body.next_cursor);
    assert.deepEqual(Object.keys(first.body.events[0]).sort(),
      ["event_id", "kind", "message_id", "occurred_at", "received_at", "recipient"]);
    await event("event-c", "failed");
    const second = await get(`/v1/events?limit=1&cursor=${encodeURIComponent(first.body.next_cursor)}`);
    assert.deepEqual(second.body.events.map((e) => e.event_id), ["event-a"], "same-second append stays outside the original page fence");
    assert.equal(second.body.next_cursor, null);
    const filtered = await get(`/v1/events?kind=failed&message_id=${id}&since=${encodeURIComponent(new Date(at * 1000).toISOString())}`);
    assert.deepEqual(filtered.body.events.map((e) => e.event_id), ["event-c"]);
    assert.equal((await get(`/v1/events?kind=failed&cursor=${encodeURIComponent(first.body.next_cursor)}`)).body.code, "invalid_events_cursor");
    assert.equal((await get(`/v1/events?cursor=${encodeURIComponent(first.body.next_cursor)}`, "foreign")).body.code, "invalid_events_cursor");
    for (const query of ["limit=0", "limit=101", "kind=arbitrary", "limit=1&limit=2", "unknown=1", "since=yesterday"]) {
      assert.equal((await get(`/v1/events?${query}`)).body.code, "invalid_events_query");
    }
    const status = await get("/v1/sending/status");
    assert.equal(status.status, 200);
    assert.equal(status.body.policy.state, "held");
    assert.equal(status.body.quotas.length, 3);
    const sensitive = JSON.stringify([receipt.body, status.body, first.body]);
    for (const sentinel of ["private-provider-id", "private-payload-hash", "private subject", "private body"]) {
      assert.equal(sensitive.includes(sentinel), false, "read contract excludes unrelated sensitive fields");
    }
    await db.prepare("UPDATE messages SET deleted_at=1 WHERE id=?1").bind(id).run();
    assert.deepEqual((await get("/v1/events")).body.events, []);
    assert.equal((await get(`/v1/messages/${id}/events`)).status, 404);
    await db.prepare("DELETE FROM messages WHERE id=?1").bind(id).run();
    assert.deepEqual((await get("/v1/events")).body.events, [], "GC does not revive deleted feedback");
    assert.equal((await get(`/v1/sends/${key}`)).body.links, undefined);
    assert.equal(unexpected, 0);
  } finally { await mf.dispose(); }
});
